"""C14 risk caps across VT midnight, using the committed host offset rule.

risk.py is deliberately stateless: the host must reconcile daily metrics into a
VT_SERVER_DAY snapshot. These are offline risk-boundary tests, not proof of a
host reconciler, broker-clock observation or execution authorization. No runtime
reset clock, counters, scope flags or timezone policy are replaced here.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml

from demo_execution.risk import RiskSnapshot, evaluate_risk_caps
from mt5.symbol_resolver import SymbolMeta

REPO = Path(__file__).resolve().parents[1]
UTC = timezone.utc
OFFSET_RULE = (
    "SERVER_MIDNIGHT_EQUALS_NEW_YORK_1700: server_utc_offset_hours = "
    "America/New_York UTC offset + 7"
)
# Independent expected UTC boundaries; the fixture below must derive these from
# committed metadata, never from the captured (summer-only) numeric offset of 3.
BOUNDARIES = [
    (datetime(2026, 10, 31, 21, tzinfo=UTC), date(2026, 10, 31), date(2026, 11, 1)),
    (datetime(2026, 11, 1, 22, tzinfo=UTC), date(2026, 11, 1), date(2026, 11, 2)),
]
CAPS = [
    ({"strategy_trades_today": 5}, "STRATEGY_DAILY_TRADE_LIMIT"),
    ({"strategy_daily_loss_pct": 1.0}, "STRATEGY_DAILY_LOSS_LIMIT"),
    ({"account_daily_loss_pct": 2.0}, "ACCOUNT_DAILY_LOSS_LIMIT"),
]


def _vt_day(at: datetime, metadata: dict) -> date:
    """Test-only snapshot adapter for the exact evidenced rule, without fallback."""
    assert metadata["schema"] == "AG_HOST_SYMBOL_METADATA_V2"
    assert metadata["server"] == "VTMarkets-Demo"
    assert metadata["server_utc_offset_rule"] == OFFSET_RULE
    ny_offset = at.astimezone(ZoneInfo("America/New_York")).utcoffset()
    assert ny_offset is not None
    return (at.astimezone(UTC) + ny_offset + timedelta(hours=7)).date()


@pytest.fixture(scope="module")
def inputs():
    config = yaml.safe_load((REPO / "config/demo_execution_s1.yaml").read_text())
    raw = config["scope"]
    assert raw["daily_reset_basis"] == "VT_SERVER_DAY"
    metadata = json.loads((REPO / f"config/symbol_metadata/host_captured/{raw['symbol']}.json").read_text())
    assert metadata["canonical_symbol"] == raw["symbol"]
    captured = datetime.fromisoformat(metadata["captured_at_utc"])
    captured_offset = captured.astimezone(ZoneInfo("America/New_York")).utcoffset()
    assert captured_offset + timedelta(hours=7) == timedelta(hours=metadata["server_utc_offset_hours"])
    # Only the fields consumed by pure risk evaluation; no test admission or READY
    # override. There are no positions, so the synthetic magic cannot grant anything.
    scope = SimpleNamespace(
        symbol=raw["symbol"], broker_symbol=metadata["broker_symbol"], magic_number=0,
        daily_reset_basis=raw["daily_reset_basis"],
        daily_reset_owner_confirm=raw["daily_reset_owner_confirm"],
    )
    fields = metadata["fields"]
    meta = SymbolMeta(
        symbol=scope.broker_symbol, tick_size=fields["trade_tick_size"],
        tick_value=fields["trade_tick_value"], contract_size=fields["trade_contract_size"],
        volume_min=fields["volume_min"], volume_max=fields["volume_max"],
        volume_step=fields["volume_step"], digits=fields["digits"], point=fields["point"],
        metadata_source="EXCHANGE_VERIFIED",
    )
    return scope, metadata, meta


def _snapshot(inputs, at, **metrics):
    scope, metadata, meta = inputs
    snapshot = RiskSnapshot(
        observed_at_utc=at, server_day=_vt_day(at, metadata), demo_equity=10000.0,
        strategy_daily_loss_pct=0.0, account_daily_loss_pct=0.0,
        strategy_trades_today=0, open_positions=(), positions_complete=True,
        daily_metrics_complete=True, symbol_meta=meta, daily_reset_basis=scope.daily_reset_basis,
    )
    return replace(snapshot, **metrics)


def _assess(inputs, at, snapshot):
    return evaluate_risk_caps(
        {"entry": 1.3000, "stop_loss": 1.2990}, inputs[0], snapshot, now_utc=at,
    )


def test_committed_rule_produces_a_25_hour_vt_day_at_us_dst_end(inputs):
    _, metadata, _ = inputs
    before, after = (row[0] for row in BOUNDARIES)
    assert after - before == timedelta(hours=25)
    for boundary, old_day, new_day in BOUNDARIES:
        assert _vt_day(boundary - timedelta(microseconds=1), metadata) == old_day
        assert _vt_day(boundary, metadata) == new_day
        assert _vt_day(boundary + timedelta(microseconds=1), metadata) == new_day


@pytest.mark.parametrize("boundary,old_day,new_day", BOUNDARIES)
@pytest.mark.parametrize("exhausted,reason", CAPS)
def test_reconciled_new_vt_day_releases_each_exhausted_daily_cap(
    inputs, boundary, old_day, new_day, exhausted, reason,
):
    before = boundary - timedelta(microseconds=1)
    prior = _snapshot(inputs, before, **exhausted)
    blocked = _assess(inputs, before, prior)
    assert (blocked.allowed, blocked.reason_code, blocked.server_day) == (False, reason, old_day)
    for at in (boundary, boundary + timedelta(microseconds=1)):
        # Only a complete reconciled new-day snapshot supplies cleared daily
        # metrics; elapsed wall time itself never zeroes them inside risk.py.
        fresh = _snapshot(inputs, at)
        allowed = _assess(inputs, at, fresh)
        assert (allowed.allowed, allowed.reason_code, allowed.server_day) == (
            True, "C14_RISK_CAPS_PASS", new_day,
        )
        assert allowed.planned_risk_pct == pytest.approx(0.5)
        assert allowed.daily_reset_owner_confirm is inputs[0].daily_reset_owner_confirm
        still_exhausted = _assess(inputs, at, replace(fresh, **exhausted))
        assert (still_exhausted.allowed, still_exhausted.reason_code) == (False, reason)


@pytest.mark.parametrize("exhausted,reason", CAPS)
@pytest.mark.parametrize("at", [
    datetime(2026, 11, 1, 0, tzinfo=UTC),    # UTC midnight is inside the same VT day.
    datetime(2026, 11, 1, 5, 59, 59, tzinfo=UTC),
    datetime(2026, 11, 1, 6, tzinfo=UTC),    # NY 01:59:59 -> 01:00:00, no VT reset.
    datetime(2026, 11, 1, 21, tzinfo=UTC),   # Yesterday's reset hour is now too early.
    datetime(2026, 11, 1, 21, 59, 59, tzinfo=UTC),
])
def test_no_early_reset_at_utc_midnight_dst_rollback_or_old_reset_hour(inputs, at, exhausted, reason):
    snapshot = _snapshot(inputs, at, **exhausted)
    assert snapshot.server_day == date(2026, 11, 1)
    result = _assess(inputs, at, snapshot)
    assert (result.allowed, result.reason_code) == (False, reason)


@pytest.mark.parametrize("boundary,old_day,new_day", BOUNDARIES)
@pytest.mark.parametrize("metrics,reason", [
    ({"strategy_trades_today": 4}, "C14_RISK_CAPS_PASS"),
    ({"strategy_trades_today": 5}, "STRATEGY_DAILY_TRADE_LIMIT"),
    # A new trade reserves 0.5%: existing loss plus that risk may equal, not
    # exceed, the 1% strategy or 2% account cap on either side of DST.
    ({"strategy_daily_loss_pct": 0.5}, "C14_RISK_CAPS_PASS"),
    ({"strategy_daily_loss_pct": 0.5001}, "STRATEGY_DAILY_LOSS_LIMIT"),
    ({"account_daily_loss_pct": 1.5}, "C14_RISK_CAPS_PASS"),
    ({"account_daily_loss_pct": 1.5001}, "ACCOUNT_DAILY_LOSS_LIMIT"),
])
def test_same_caps_apply_on_both_sides_of_dst(inputs, boundary, old_day, new_day, metrics, reason):
    for at, day in ((boundary - timedelta(microseconds=1), old_day), (boundary, new_day)):
        result = _assess(inputs, at, _snapshot(inputs, at, **metrics))
        assert (result.allowed, result.reason_code, result.server_day) == (
            reason == "C14_RISK_CAPS_PASS", reason, day,
        )


@pytest.mark.parametrize("boundary,old_day,new_day", BOUNDARIES)
@pytest.mark.parametrize("changes,reason", [
    ({"server_day": None}, "RISK_SERVER_DAY_UNAVAILABLE"),
    ({"server_day": "2026-11-02"}, "RISK_SERVER_DAY_UNAVAILABLE"),
    ({"daily_reset_basis": None}, "RISK_SERVER_DAY_UNAVAILABLE"),
    ({"daily_metrics_complete": False}, "RISK_SNAPSHOT_INCOMPLETE"),
])
def test_missing_day_or_unreconciled_metrics_never_become_a_dst_reset(inputs, boundary, old_day, new_day, changes, reason):
    for at in (boundary - timedelta(microseconds=1), boundary):
        result = _assess(inputs, at, replace(_snapshot(inputs, at), **changes))
        assert (result.allowed, result.reason_code) == (False, reason)
