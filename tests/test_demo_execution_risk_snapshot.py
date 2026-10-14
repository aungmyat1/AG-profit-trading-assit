"""C14 risk snapshot builder: read-only fake MT5 only, across the 2026-11-01 US DST reset.

Server-clock times in the fake are derived independently (+3h before 2026-11-01T06:00Z, +2h after),
never from the helper under test. No broker, no order call, no flag or scope change."""
from __future__ import annotations

import itertools
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from demo_execution import risk_snapshot as RS
from demo_execution import vt_day
from demo_execution.risk import evaluate_risk_caps

REPO = Path(__file__).resolve().parents[1]
UTC = timezone.utc
METADATA = json.loads((REPO / "config/symbol_metadata/host_captured/GBPUSD.json").read_text())
DST_END = datetime(2026, 11, 1, 6, tzinfo=UTC)


def _scope(magic, symbol="GBPUSD", session="ASIAN_LONDON"):
    return SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.2", symbol=symbol,
                           broker_symbol=f"{symbol}-VIP", session=session, magic_number=magic,
                           daily_reset_basis="VT_SERVER_DAY", daily_reset_owner_confirm=True)


S1, S2 = _scope(1001), _scope(1002, "EURUSD")


def _server_epoch(at_utc: datetime) -> int:
    offset = timedelta(hours=3 if at_utc < DST_END else 2)
    return int(((at_utc + offset).replace(tzinfo=None) - datetime(1970, 1, 1)).total_seconds())


_IDS = itertools.count(500)


def deal(at, magic, profit, *, entry=0, kind=0, pos=None, **extra):
    return SimpleNamespace(time=_server_epoch(at), magic=magic, profit=profit, entry=entry, type=kind,
                           position_id=next(_IDS) if pos is None else pos,
                           swap=extra.get("swap", 0.0), commission=extra.get("commission", 0.0), fee=0.0)


def position(at, magic, profit, symbol="GBPUSD-VIP"):
    return SimpleNamespace(time=_server_epoch(at), magic=magic, profit=profit, swap=0.0, symbol=symbol)


class FakeMT5:
    def __init__(self, deals=(), positions=(), equity=10_000.0, account=True):
        self.deals = None if deals is None else list(deals)
        self.positions = None if positions is None else list(positions)
        self.equity, self.account = equity, account
        self.calls = []

    def account_info(self):
        self.calls.append("account_info")
        return SimpleNamespace(equity=self.equity) if self.account else None

    def history_deals_get(self, date_from, date_to):
        self.calls.append(("history_deals_get", date_from, date_to))
        if self.deals is None:
            return None
        lo, hi = (int((d.replace(tzinfo=None) - datetime(1970, 1, 1)).total_seconds()) for d in (date_from, date_to))
        return tuple(d for d in self.deals if d.time is None or lo <= d.time <= hi)

    def positions_get(self):
        self.calls.append("positions_get")
        return None if self.positions is None else tuple(self.positions)

    def __getattr__(self, name):          # any other broker call is a test failure
        if name.startswith("__"):
            raise AttributeError(name)
        raise AssertionError(f"unexpected MT5 call {name}")


def build(mt5, now, scopes=(S1, S2), metadata=METADATA):
    return RS.build_risk_snapshots(mt5, list(scopes), metadata=metadata, now_utc=now)


# --------------------------------------------------------------------------- server day helper

@pytest.mark.parametrize("at, day, start", [
    (datetime(2026, 10, 31, 20, 59, tzinfo=UTC), date(2026, 10, 31), datetime(2026, 10, 30, 21, tzinfo=UTC)),
    (datetime(2026, 10, 31, 21, 0, tzinfo=UTC), date(2026, 11, 1), datetime(2026, 10, 31, 21, tzinfo=UTC)),
    (datetime(2026, 11, 1, 21, 59, tzinfo=UTC), date(2026, 11, 1), datetime(2026, 10, 31, 21, tzinfo=UTC)),
    (datetime(2026, 11, 1, 22, 0, tzinfo=UTC), date(2026, 11, 2), datetime(2026, 11, 1, 22, tzinfo=UTC)),
])
def test_vt_server_day_and_start_across_dst(at, day, start):
    assert vt_day.server_day(at, METADATA) == day
    assert vt_day.server_day_start_utc(day, METADATA) == start


def test_unknown_offset_rule_blocks():
    bad = {**METADATA, "server_utc_offset_rule": "FIXED_PLUS_3"}
    assert vt_day.server_day(datetime(2026, 11, 1, tzinfo=UTC), bad) is None
    result = build(FakeMT5(), datetime(2026, 11, 1, 12, tzinfo=UTC), metadata=bad)
    assert (result.status, result.reason_code) == ("BLOCKED", RS.SERVER_DAY_UNAVAILABLE)
    assert result.snapshot_for(S1) is None


# --------------------------------------------------------------------------- metrics

def test_per_scope_and_account_metrics_for_the_current_server_day():
    now = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)         # server day 2026-11-01
    mt5 = FakeMT5(deals=[
        deal(datetime(2026, 10, 31, 20, 0, tzinfo=UTC), 1001, -500.0, entry=1),   # previous day: excluded
        deal(datetime(2026, 10, 31, 21, 5, tzinfo=UTC), 1001, 0.0, pos=1),        # S1 entry
        deal(datetime(2026, 11, 1, 3, 0, tzinfo=UTC), 1001, -40.0, entry=1, commission=-2.0, pos=1),  # S1 exit
        deal(datetime(2026, 11, 1, 9, 0, tzinfo=UTC), 1001, 0.0, pos=2),          # S1 entry (after DST end)
        deal(datetime(2026, 11, 1, 10, 0, tzinfo=UTC), 7777, -30.0, entry=1),     # foreign close, carried
        deal(datetime(2026, 11, 1, 11, 0, tzinfo=UTC), 0, 1000.0, kind=2),        # balance: excluded
    ], positions=[position(datetime(2026, 11, 1, 9, 0, tzinfo=UTC), 1001, -8.0)])
    result = build(mt5, now)
    assert result.status == "OK" and result.server_day == date(2026, 11, 1)
    s1 = result.scopes[RS.scope_key(S1)]
    assert (s1["trades_today"], s1["realized_pnl"], s1["open_pnl"]) == (2, -42.0, -8.0)
    assert s1["total_R"] == -1.0 and s1["daily_loss_pct"] == 0.5      # 1R = 0.5% of 10k = 50
    assert result.scopes[RS.scope_key(S2)]["trades_today"] == 0
    assert result.account["realized_pnl"] == -42.0 and result.account["carried_adverse_pnl"] == -30.0
    assert result.account["daily_loss_pct"] == 0.8
    snap = result.snapshot_for(S1)
    assert snap.strategy_trades_today == 2 and snap.account_daily_loss_pct == 0.8
    assert snap.server_day == date(2026, 11, 1) and snap.daily_reset_basis == "VT_SERVER_DAY"
    assert [p.magic_number for p in snap.open_positions] == [1001]
    # read-only, one read each, day window on the server clock (midnight .. now)
    assert mt5.calls[0] == "account_info" and mt5.calls[2] == "positions_get" and len(mt5.calls) == 3
    _, lo, hi = mt5.calls[1]
    assert lo.replace(tzinfo=None) == datetime(2026, 11, 1) and hi.replace(tzinfo=None) == datetime(2026, 11, 1, 23, 30)


def test_counts_reset_at_the_winter_server_midnight():
    deals = [deal(datetime(2026, 11, 1, 21, 0, tzinfo=UTC) + timedelta(minutes=i), 1001, 0.0) for i in range(5)]
    before = build(FakeMT5(deals=deals), datetime(2026, 11, 1, 21, 59, tzinfo=UTC))
    after = build(FakeMT5(deals=deals), datetime(2026, 11, 1, 22, 0, tzinfo=UTC))
    assert before.scopes[RS.scope_key(S1)]["trades_today"] == 5
    assert after.server_day == date(2026, 11, 2) and after.scopes[RS.scope_key(S1)]["trades_today"] == 0


# --------------------------------------------------------------------------- carried positions, trade count

NOW = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)                  # server day 2026-11-01
YESTERDAY = datetime(2026, 10, 30, 12, tzinfo=UTC)               # before the 2026-10-31 21:00Z day start


def test_carried_gains_never_offset_carried_losses():
    # +1.5% carried gain (unknown midnight mark) and a -1.0% carried loss: the loss is reported in full.
    mt5 = FakeMT5(positions=[position(YESTERDAY, 1001, 150.0), position(YESTERDAY, 1001, -100.0)])
    s1 = build(mt5, NOW).scopes[RS.scope_key(S1)]
    assert s1["carried_adverse_pnl"] == -100.0 and s1["open_pnl"] == 0.0
    assert s1["daily_loss_pct"] == 1.0 and s1["daily_loss_R"] == 2.0


def test_carried_position_back_to_zero_reports_no_gain_and_no_offset():
    # A carried position worth +1.5% at midnight and 0 now: its intraday give-back is unknowable from
    # profit alone (conservative approximation, documented); it can never offset another loss.
    mt5 = FakeMT5(positions=[position(YESTERDAY, 1001, 0.0)],
                  deals=[deal(datetime(2026, 11, 1, 2, tzinfo=UTC), 1001, -50.0, entry=1)])
    s1 = build(mt5, NOW).scopes[RS.scope_key(S1)]
    assert s1["carried_adverse_pnl"] == -50.0 and s1["daily_loss_pct"] == 0.5


def test_today_gains_do_not_offset_carried_losses():
    mt5 = FakeMT5(deals=[deal(datetime(2026, 11, 1, 2, tzinfo=UTC), 1001, 0.0, pos=9),
                         deal(datetime(2026, 11, 1, 3, tzinfo=UTC), 1001, 200.0, entry=1, pos=9),   # today: +200
                         deal(datetime(2026, 11, 1, 4, tzinfo=UTC), 1001, -100.0, entry=1, pos=3),  # carried close
                         deal(datetime(2026, 11, 1, 5, tzinfo=UTC), 1001, 80.0, entry=1, pos=4)],   # carried gain
                  positions=[position(YESTERDAY, 1001, -20.0)])
    s1 = build(mt5, NOW).scopes[RS.scope_key(S1)]
    assert (s1["realized_pnl"], s1["carried_adverse_pnl"]) == (200.0, -120.0)
    assert s1["daily_loss_pct"] == 1.2 and s1["trades_today"] == 1


def test_trades_today_counts_distinct_positions_not_deals():
    fills = [deal(datetime(2026, 11, 1, 2, tzinfo=UTC), 1001, 0.0, pos=7),
             deal(datetime(2026, 11, 1, 2, 1, tzinfo=UTC), 1001, 0.0, pos=7),     # second fill, same trade
             deal(datetime(2026, 11, 1, 3, tzinfo=UTC), 1001, 0.0, pos=8)]
    assert build(FakeMT5(deals=fills), NOW).scopes[RS.scope_key(S1)]["trades_today"] == 2
    assert build(FakeMT5(deals=fills[:2]), NOW).scopes[RS.scope_key(S1)]["trades_today"] == 1


def test_duplicate_scope_magic_blocks():
    result = build(FakeMT5(), NOW, scopes=(S1, _scope(1001, "EURUSD")))
    assert (result.status, result.reason_code) == ("BLOCKED", RS.MAGIC_DUPLICATE)
    assert result.snapshot_for(S1) is None


# --------------------------------------------------------------------------- fail closed

@pytest.mark.parametrize("mt5, reason", [
    (FakeMT5(account=False), RS.ACCOUNT_UNAVAILABLE),
    (FakeMT5(equity=0.0), RS.EQUITY_INVALID),
    (FakeMT5(deals=None), RS.DEALS_UNAVAILABLE),
    (FakeMT5(positions=None), RS.POSITIONS_UNAVAILABLE),
    (FakeMT5(deals=[SimpleNamespace(time=None, magic=1, type=0, entry=0, profit=0.0)]), RS.DATA_INVALID),
    (FakeMT5(deals=[deal(datetime(2026, 11, 1, 2, tzinfo=UTC), 1001, 0.0, pos="x")]), RS.DATA_INVALID),
    (FakeMT5(positions=[position(datetime(2026, 11, 1, 23, tzinfo=UTC), 1001, 0.0)]), RS.CLOCK_AHEAD),
])
def test_missing_or_invalid_broker_data_blocks(mt5, reason):
    result = build(mt5, datetime(2026, 11, 1, 12, tzinfo=UTC))
    assert (result.status, result.reason_code) == ("BLOCKED", reason)
    assert result.snapshot_for(S1) is None


def test_no_scopes_or_naive_clock_blocks():
    assert build(FakeMT5(), datetime(2026, 11, 1, 12, tzinfo=UTC), scopes=()).reason_code == RS.SCOPES_MISSING
    assert build(FakeMT5(), datetime(2026, 11, 1, 12)).reason_code == RS.SERVER_DAY_UNAVAILABLE


# --------------------------------------------------------------------------- feeds admission

def _caps(result, now):
    return evaluate_risk_caps({}, S1, result.snapshot_for(S1), now_utc=now)


def test_built_snapshot_feeds_the_c14_caps():
    now = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)
    five = [deal(datetime(2026, 11, 1, 12, tzinfo=UTC) + timedelta(minutes=i), 1001, 0.0) for i in range(5)]
    assert _caps(build(FakeMT5(deals=five), now), now).reason_code == "STRATEGY_DAILY_TRADE_LIMIT"
    held = [position(datetime(2026, 11, 1, 12, tzinfo=UTC), 7777, 0.0)]       # foreign position on symbol
    assert _caps(build(FakeMT5(positions=held), now), now).reason_code == "INSTRUMENT_POSITION_LIMIT"


def test_blocked_or_stale_build_is_refused_by_admission():
    now = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)
    assert _caps(build(FakeMT5(deals=None), now), now).reason_code == "RISK_SNAPSHOT_MISSING"
    old = build(FakeMT5(), now - timedelta(hours=1))
    assert _caps(old, now).reason_code == "RISK_SNAPSHOT_STALE_OR_INVALID"
    # a snapshot built before the winter midnight is stale for the new server day as well
    assert old.server_day == date(2026, 11, 1)
