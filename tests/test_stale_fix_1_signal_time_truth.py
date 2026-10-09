"""STALE-FIX-1 funnel field: #94's signal-time provenance reaches the canonical ticket.

STALE-FIX-1 is merged (#94): fx.py no longer substitutes the first trade-session bar; a SIGNAL
without an engine signal time is DATA_ERROR / SIGNAL_TIME_UNAVAILABLE, and every FX ticket
records signal_time_source (ENGINE | MISSING | NOT_APPLICABLE). PR #95 (reconciled 2026-10-09)
passes that field through actionability and the canonical `trigger` block; consumers never
infer it (None / NOT_AVAILABLE when a source ticket carries none). Pure: no broker, no network.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import actionability as A  # noqa: E402
from v1_tickets import fx as v1_fx  # noqa: E402
from v1_tickets.canonical_ticket import NOT_AVAILABLE, build_canonical_ticket  # noqa: E402
from v1_tickets.policy_loader import POLICY_ID, POLICY_OK, ActionabilityPolicy  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)      # Monday; ASIAN_LONDON ref 00:00-07:00, trade from 07:00
M15 = dt.timedelta(minutes=15)

SIGNED_POLICY = ActionabilityPolicy(
    status=POLICY_OK, policy_id=POLICY_ID, version=1, min_remaining_r=0.1,
    signed_by="test-fixture", signed_at="2026-01-05", source_path="<fixture>", reason=None,
)


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    """Host captures must never leak in (matches tests/test_v1_tickets.py convention)."""
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def _c(h, m, o, hi, lo, cl):
    return Candle(dt.datetime(2026, 1, 5, h, m, tzinfo=UTC), o, hi, lo, cl)


def _fixtures():
    session = [_c(0, 0, 1.1000, 1.1050, 1.0950, 1.1010),
               _c(0, 15, 1.1010, 1.1040, 1.0960, 1.1005)]
    # First trade-session bar opens 07:00, closes 07:15.
    post = [_c(7, 0, 1.1005, 1.1006, 1.1004, 1.1005),
            _c(7, 15, 1.1005, 1.1060, 1.1000, 1.1048)]
    return session, post


def _signal(*, status="SIGNAL", setup="TREND", ts=None, direction="SHORT"):
    """Engine result shaped like strategy_engine.evaluate()'s TradeSignal."""
    return SimpleNamespace(
        status=status, reason_code="NO_QUALIFIED_SWEEP_IN_WINDOW" if status != "SIGNAL" else "ENGINE_REASON",
        regime="RANGE", setup=setup, signal_id="sig-fixture", box_high=1.1050, box_low=1.0950,
        box_mid=1.1000, signal_timestamp=ts, direction=direction, entry=1.1000,
        stop_loss=1.1060, risk_distance=0.0060,
    )


def _build(sig, post, *, evaluated_at, data_close, spread=0.0001, monkeypatch=None, mp=None):
    m = monkeypatch if monkeypatch is not None else mp
    m.setattr(v1_fx, "evaluate", lambda *a, **k: sig)
    session, _ = _fixtures()
    return v1_fx.build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, session, 2, post,
                                 data_source="FIXTURE", evaluated_at=evaluated_at,
                                 data_close=data_close, spread=spread)


AT = dt.datetime(2026, 1, 5, 7, 35, tzinfo=UTC)   # 5 min after an engine 07:15 bar closed
AT1 = dt.datetime(2026, 1, 5, 7, 16, tzinfo=UTC)  # 1 min after the derived 07:15 close (entry_1 fresh)


# ---- the merged #94 behaviour these pass-through tests rely on --------------------------

def test_no_engine_time_is_data_error_with_missing_source_and_no_substitution(monkeypatch):
    t = _build(_signal(ts=None), _fixtures()[1], evaluated_at=AT1, data_close=AT1, monkeypatch=monkeypatch)
    assert (t["decision"], t["reason_code"]) == ("DATA_ERROR", v1_fx.SIGNAL_TIME_UNAVAILABLE)
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_MISSING
    assert t["signal_timestamp"] is None and t.get("signal_close_utc") is None  # no first-bar substitute
    assert "signal_time_basis_utc" not in t


# ---- downstream funnel pass-through -----------------------------------------------------

def _action(t, now):
    return A.evaluate_actionability(t, now=now, current_price=1.1010,
                                    window_end=dt.datetime(2026, 1, 5, 11, tzinfo=UTC),
                                    policy=SIGNED_POLICY, policy_root="/nonexistent")


def _canon(t, now):
    return build_canonical_ticket(t, now=now, current_price=1.1010,
                                  window_end=dt.datetime(2026, 1, 5, 11, tzinfo=UTC),
                                  policy=SIGNED_POLICY, policy_root="/nonexistent")


def test_engine_source_passes_through_actionability_and_canonical(monkeypatch):
    ts = dt.datetime(2026, 1, 5, 7, 15, tzinfo=UTC)
    t = _build(_signal(ts=ts, setup="SWEEP"), _fixtures()[1], evaluated_at=AT, data_close=AT,
               monkeypatch=monkeypatch)
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_ENGINE
    assert _action(t, AT)["signal_time_source"] == v1_fx.SIGNAL_TIME_ENGINE
    assert _canon(t, AT)["trigger"]["signal_time_source"] == v1_fx.SIGNAL_TIME_ENGINE


def test_missing_source_passes_through_actionability(monkeypatch):
    t = _build(_signal(ts=None), _fixtures()[1], evaluated_at=AT1, data_close=AT1, monkeypatch=monkeypatch)
    assert _action(t, AT1)["signal_time_source"] == v1_fx.SIGNAL_TIME_MISSING


def test_no_trade_source_is_not_applicable_in_canonical(monkeypatch):
    t = _build(_signal(status="NO_TRADE", setup="NONE"), _fixtures()[1], evaluated_at=AT,
               data_close=AT, monkeypatch=monkeypatch)
    assert t["decision"] == "NO_TRADE" and "signal_close_utc" not in t
    assert _canon(t, AT)["trigger"]["signal_time_source"] == v1_fx.SIGNAL_TIME_NOT_APPLICABLE


def test_tickets_without_the_field_are_never_inferred():
    """Pre-fix archives and crypto/manual tickets: None / NOT_AVAILABLE, never a guess."""
    raw = {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1", "symbol": "EURUSD",
           "decision": "NO_TRADE", "reason_code": "NO_QUALIFIED_SWEEP_IN_WINDOW", "setup": "NONE",
           "signal_timestamp": None}
    assert _action(raw, AT)["signal_time_source"] is None
    canon = _canon(raw, AT)
    assert canon["trigger"]["signal_time_source"] == NOT_AVAILABLE
    assert "signal_time_basis_utc" not in canon["trigger"]
