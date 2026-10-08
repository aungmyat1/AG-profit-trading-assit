"""STALE-FIX-1: truthful signal time + funnel fields (fx.py:165 substitution recording).

Before this fix, `build_fx_ticket` substituted the first trade-session bar as the gate
input when the engine supplied no signal time (entry_1 box-based), and nothing on the
ticket said so -- the derived value was indistinguishable from an engine signal time.
The fix keeps gate math byte-identical but records explicit provenance:

    signal_time_source:   ENGINE_M15_SIGNAL_BAR | FIRST_TRADE_SESSION_BAR | NONE
    signal_time_basis_utc: the bar OPEN the gate close derives from (None if none)

and `signal_timestamp` stays exactly what the engine supplied (None for entry_1).
Consumers never infer: actionability passes the fields through; the canonical ticket
emits NOT_AVAILABLE when a source ticket carries none. Pure: no broker, no network.
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


# ---- ticket-level funnel fields --------------------------------------------------------

def test_entry1_derived_time_is_labeled_not_presented_as_engine_time(monkeypatch):
    """entry_1: engine signal time stays None; the substitute is labeled FIRST_TRADE_SESSION_BAR."""
    t = _build(_signal(ts=None), _fixtures()[1], evaluated_at=AT1, data_close=AT1, monkeypatch=monkeypatch)
    # Production D6 switch is OFF: the engine READY is archived as SHADOW_INFO_ONLY with the
    # READY kept as suppressed_decision -- exactly as before this patch (no authority change).
    assert t["decision"] == "SHADOW_INFO_ONLY" and t["suppressed_decision"] == "READY"
    assert t["signal_timestamp"] is None                  # engine truth not overwritten
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_FIRST_TRADE_BAR
    assert t["signal_time_basis_utc"] == "2026-01-05T07:00:00+00:00"
    # The gate value is what it always was (first bar open + 15m); now it is labeled.
    assert t["signal_close_utc"] == "2026-01-05T07:15:00+00:00"


def test_entry2_engine_time_is_labeled_engine(monkeypatch):
    ts = dt.datetime(2026, 1, 5, 7, 15, tzinfo=UTC)
    t = _build(_signal(ts=ts, setup="SWEEP"), _fixtures()[1], evaluated_at=AT, data_close=AT,
               monkeypatch=monkeypatch)
    assert t["signal_timestamp"] == "2026-01-05T07:15:00+00:00"
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_ENGINE_BAR
    assert t["signal_time_basis_utc"] == ts.isoformat()
    assert t["signal_close_utc"] == "2026-01-05T07:30:00+00:00"


def test_no_post_session_candles_source_none_and_gate_unchanged(monkeypatch):
    t = _build(_signal(ts=None), [], evaluated_at=AT, data_close=AT, monkeypatch=monkeypatch)
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_NONE
    assert t["signal_time_basis_utc"] is None
    # Pre-fix behavior, unchanged: a READY with no close time at all is withheld STALE.
    assert (t["decision"], t["reason_code"], t["suppressed_decision"]) == ("STALE", "STALE_SIGNAL", "READY")


def test_no_trade_fields_are_truthful_about_derivation(monkeypatch):
    t = _build(_signal(status="NO_TRADE", setup="NONE"), _fixtures()[1], evaluated_at=AT,
               data_close=AT, monkeypatch=monkeypatch)
    assert t["decision"] == "NO_TRADE" and t["reason_code"] == "NO_QUALIFIED_SWEEP_IN_WINDOW"
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_FIRST_TRADE_BAR
    assert t["signal_time_basis_utc"] == "2026-01-05T07:00:00+00:00"
    assert "signal_close_utc" not in t                    # gate adds no time to NO_TRADE (AGP-TTU-02)


def test_stale_withheld_ready_keeps_labeled_trigger_close(monkeypatch):
    """AGP-TTU-02 RC1 + STALE-FIX-1 compose: stale data withholds, real close kept, labeled."""
    stale_close = AT - dt.timedelta(minutes=16)
    t = _build(_signal(ts=None), _fixtures()[1], evaluated_at=AT, data_close=stale_close,
               monkeypatch=monkeypatch)
    assert (t["decision"], t["reason_code"], t["suppressed_decision"]) == ("STALE", "STALE_DATA", "READY")
    assert t["signal_close_utc"] == "2026-01-05T07:15:00+00:00"
    assert t["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_FIRST_TRADE_BAR
    assert t["signal_time_basis_utc"] == "2026-01-05T07:00:00+00:00"


# ---- downstream funnel pass-through -----------------------------------------------------

def test_actionability_passes_through_funnel_fields(monkeypatch):
    t = _build(_signal(ts=None), _fixtures()[1], evaluated_at=AT1, data_close=AT1, monkeypatch=monkeypatch)
    out = A.evaluate_actionability(t, now=AT1, current_price=1.1010,
                                   window_end=dt.datetime(2026, 1, 5, 11, tzinfo=UTC),
                                   policy=SIGNED_POLICY, policy_root="/nonexistent")
    assert out["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_FIRST_TRADE_BAR
    assert out["signal_time_basis_utc"] == "2026-01-05T07:00:00+00:00"
    assert out["trigger_bar_close_utc"] == "2026-01-05T07:15:00+00:00"


def test_actionability_silent_when_ticket_has_no_fields():
    """Pre-fix tickets (no provenance fields) stay truthful: pass-through is None, not invented."""
    raw = {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "symbol": "EURUSD", "decision": "NO_TRADE",
           "reason_code": "NO_QUALIFIED_SWEEP_IN_WINDOW", "setup": "NONE", "signal_timestamp": None}
    out = A.evaluate_actionability(raw, now=AT, current_price=1.1010,
                                   window_end=dt.datetime(2026, 1, 5, 11, tzinfo=UTC),
                                   policy=SIGNED_POLICY, policy_root="/nonexistent")
    assert out["actionability_decision"] == A.NO_TRADE
    assert out["signal_time_source"] is None and out["signal_time_basis_utc"] is None


def test_canonical_trigger_block_labels_derivation(monkeypatch):
    t = _build(_signal(ts=None), _fixtures()[1], evaluated_at=AT1, data_close=AT1, monkeypatch=monkeypatch)
    canon = build_canonical_ticket(t, now=AT1, current_price=1.1010,
                                   window_end=dt.datetime(2026, 1, 5, 11, tzinfo=UTC),
                                   policy=SIGNED_POLICY, policy_root="/nonexistent")
    assert canon["trigger"]["signal_time_source"] == v1_fx.SIGNAL_TIME_SOURCE_FIRST_TRADE_BAR
    assert canon["trigger"]["signal_time_basis_utc"] == "2026-01-05T07:00:00+00:00"
    # Engine supplied no signal time; canonical keeps its pre-fix fallback to the labeled
    # trigger close (unchanged semantics), and now records where that close came from.
    assert canon["trigger"]["trigger_timestamp"] is None or canon["trigger"]["trigger_timestamp"] == "2026-01-05T07:15:00+00:00"
    assert t["signal_timestamp"] is None


def test_canonical_trigger_block_not_available_without_fields():
    """Crypto/manual source tickets with no provenance fields emit NOT_AVAILABLE, never a guess."""
    raw = {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1", "symbol": "EURUSD",
           "decision": "NO_TRADE", "reason_code": "NO_QUALIFIED_SWEEP_IN_WINDOW", "setup": "NONE",
           "signal_timestamp": None}
    canon = build_canonical_ticket(raw, now=AT, current_price=1.1010,
                                   window_end=dt.datetime(2026, 1, 5, 11, tzinfo=UTC),
                                   policy=SIGNED_POLICY, policy_root="/nonexistent")
    assert canon["trigger"]["signal_time_source"] == NOT_AVAILABLE
    assert canon["trigger"]["signal_time_basis_utc"] == NOT_AVAILABLE


# ---- gate-parity pinning (no admission/staleness behavior change) -----------------------

def test_gate_decisions_identical_to_pre_fix_for_all_sources(monkeypatch):
    """The same inputs before and after this patch yield the same gate decisions; only the
    two provenance fields are new. These expectations are the pre-fix decisions."""
    post = _fixtures()[1]
    # Fresh data + spread PASS -> READY (all three sources classify identically in the gate).
    ts = dt.datetime(2026, 1, 5, 7, 15, tzinfo=UTC)
    for sig, when, source in ((_signal(ts=None), AT1, v1_fx.SIGNAL_TIME_SOURCE_FIRST_TRADE_BAR),
                              (_signal(ts=ts, setup="SWEEP"), AT, v1_fx.SIGNAL_TIME_SOURCE_ENGINE_BAR)):
        t = _build(sig, post, evaluated_at=when, data_close=when, monkeypatch=monkeypatch)
        # Pre-fix production behavior (D6 OFF): engine READY -> SHADOW_INFO_ONLY, READY kept.
        assert t["decision"] == "SHADOW_INFO_ONLY" and t["suppressed_decision"] == "READY"
        assert t["spread_check"] == "PASS" and t["signal_time_source"] == source
    # 16-min-old data -> STALE / STALE_DATA regardless of source.
    stale_close = AT - dt.timedelta(minutes=16)
    for sig in (_signal(ts=None), _signal(ts=ts, setup="SWEEP")):
        t = _build(sig, post, evaluated_at=AT, data_close=stale_close, monkeypatch=monkeypatch)
        assert (t["decision"], t["reason_code"]) == ("STALE", "STALE_DATA")
    # 16-min-late evaluation of an engine-timestamped signal -> STALE / STALE_SIGNAL (as pre-fix).
    t = _build(_signal(ts=ts, setup="SWEEP"), post, evaluated_at=AT + dt.timedelta(minutes=11),
               data_close=AT + dt.timedelta(minutes=11), monkeypatch=monkeypatch)
    assert (t["decision"], t["reason_code"]) == ("STALE", "STALE_SIGNAL")
    # Spread gate untouched.
    t = _build(_signal(ts=None), post, evaluated_at=AT1, data_close=AT1, spread=0.16 * 0.0060,
               monkeypatch=monkeypatch)
    assert (t["decision"], t["reason_code"]) == ("SPREAD_TOO_WIDE",) * 2
