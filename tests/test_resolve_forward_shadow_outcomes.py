"""AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 P1A acceptance tests.

Owner-signed 2026-09-09: each ST_ASIAN_SWEEP_5R_V1 session_pair is an independently
bounded cycle -- ASIAN_LONDON resolves against its own 11:00 UTC trade_session end,
LONDON_NEWYORK against its own 15:00 UTC end, and neither may borrow a bar from beyond
its own cutoff (a hidden dependency where an Asian->London trade could be resolved using
market behavior belonging to the separate London->New York cycle). These tests prove the
session-isolation/no-lookahead invariant the sign-off requires: the cutoff is computed
correctly per cycle, and the candle-fetch window passed to market data never extends past
that cycle's own cutoff.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import resolve_forward_shadow_outcomes as resolver  # noqa: E402
from mt5.market_data import Candle  # noqa: E402


def _candle(hh, mm, o, h, l, c):
    return Candle(
        time=datetime(2026, 9, 8, hh, mm, tzinfo=timezone.utc),
        open=o, high=h, low=l, close=c,
    )


def test_asian_london_cutoff_is_its_own_session_end_not_the_global_cutoff():
    ready_at = datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc)
    cutoff = resolver._session_cutoff(ready_at, "ASIAN_LONDON")
    assert cutoff == datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc)
    assert cutoff != datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)


def test_london_newyork_cutoff_is_the_shared_global_mark():
    ready_at = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    cutoff = resolver._session_cutoff(ready_at, "LONDON_NEWYORK")
    assert cutoff == datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)


def test_asian_london_position_unresolved_at_own_cutoff_is_marked_session_exit_not_carried_forward(monkeypatch):
    """A position opened under ASIAN_LONDON that never hits SL/TP1 by 11:00 UTC must be
    marked RESOLVED_SESSION_EXIT at its own cutoff -- it must never remain open, and no
    bar at or after 11:00 UTC (which would belong to the separate LONDON_NEWYORK cycle's
    window) may be fetched or used to resolve it."""
    candles = [
        _candle(7, 11, 1.1602, 1.1610, 1.1602, 1.16050),  # inside window, no SL/TP1 hit
        _candle(10, 59, 1.1604, 1.1615, 1.1603, 1.16090),  # last candle before 11:00 cutoff
    ]
    requested_windows = []

    def fake_get_candles(symbol, timeframe, start_utc, end_utc):
        requested_windows.append((start_utc, end_utc))
        assert end_utc == datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc)
        return candles

    monkeypatch.setattr(resolver, "get_candles", fake_get_candles)

    rec = {
        "proposal_id": "TEST-1",
        "strategy_id": "ST_ASIAN_SWEEP_5R_V1",
        "strategy_version": "1.1.1",
        "symbol": "EURUSD",
        "cycle": "ASIAN_LONDON",
        "trading_date": "2026-09-08",
        "ready_at": "2026-09-08T07:00:00+00:00",
        "direction": "LONG",
        "entry": 1.1603,
        "stop_loss": 1.1601,
        "tp1": 1.1650,
        "tp2": 1.1700,
    }
    outcome = resolver.resolve_proposal(rec)

    assert requested_windows == [
        (datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc), datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc))
    ]
    assert outcome.session_exit_cutoff_utc == "2026-09-08T11:00:00+00:00"
    assert outcome.terminal_state == "RESOLVED_SESSION_EXIT"
    assert "owner-signed 2026-09-09" in outcome.session_exit_cutoff_interpretation


def test_london_newyork_position_uses_the_later_15_00_cutoff(monkeypatch):
    """The complementary case: a LONDON_NEWYORK position's own cycle end is 15:00 UTC,
    not 11:00 -- proving the two cycles' cutoffs are independently derived, not one
    global constant applied to both."""
    candles = [_candle(14, 59, 1.1700, 1.1701, 1.1699, 1.17005)]
    requested_windows = []

    def fake_get_candles(symbol, timeframe, start_utc, end_utc):
        requested_windows.append((start_utc, end_utc))
        assert end_utc == datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
        return candles

    monkeypatch.setattr(resolver, "get_candles", fake_get_candles)

    rec = {
        "proposal_id": "TEST-2",
        "strategy_id": "ST_ASIAN_SWEEP_5R_V1",
        "strategy_version": "1.1.1",
        "symbol": "EURUSD",
        "cycle": "LONDON_NEWYORK",
        "trading_date": "2026-09-08",
        "ready_at": "2026-09-08T12:00:00+00:00",
        "direction": "LONG",
        "entry": 1.1700,
        "stop_loss": 1.1690,
        "tp1": 1.1750,
        "tp2": 1.1800,
    }
    outcome = resolver.resolve_proposal(rec)

    assert requested_windows == [
        (datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc), datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc))
    ]
    assert outcome.session_exit_cutoff_utc == "2026-09-08T15:00:00+00:00"


def test_resolution_contract_version_is_signed_not_draft():
    assert resolver.RESOLUTION_CONTRACT_VERSION == "AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED"
    assert "DRAFT" not in resolver.RESOLUTION_CONTRACT_VERSION
