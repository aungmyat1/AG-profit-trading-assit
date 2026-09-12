"""Focused tests for WP6 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the proposal
formation gate's REAL-market-mode enforcement. Builds CanonicalProposal fixtures
directly (formation_gate.py is adapter-agnostic) rather than going through a full
adapter, matching this repo's existing fixture style.
"""
from __future__ import annotations

import datetime as dt

import pytest

from strategy_engine.session import Candle
from strategy_contract.market_snapshot import (
    from_mt5_latest_closed,
    from_replay_candle,
    from_synthetic_candle,
)
import strategy_contract.market_snapshot as market_snapshot_module
from proposal_envelope.models import CanonicalProposal, PROPOSAL_BLOCKED, PROPOSAL_NO_TRADE, PROPOSAL_READY
from proposal_envelope.formation_gate import (
    REASON_MISSING_MARKET_SNAPSHOT,
    REASON_NON_REAL_MARKET_MODE,
    apply_formation_gate,
)

UTC = dt.timezone.utc


def _ready_envelope(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="FX:DECISION-1", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol="EURUSD", proposal_state=PROPOSAL_READY,
        direction="LONG", entry=1.0850, stop=1.0830, targets=(1.0900,),
    )
    base.update(overrides)
    return CanonicalProposal(**base)


def _candle() -> Candle:
    return Candle(time=dt.datetime(2026, 9, 1, 6, 15, tzinfo=UTC), open=1.085, high=1.086, low=1.084, close=1.0855)


def test_non_ready_envelope_passes_through_unchanged():
    envelope = _ready_envelope(proposal_state=PROPOSAL_NO_TRADE)
    result = apply_formation_gate(envelope, market_snapshot=None)
    assert result is envelope  # untouched, not even re-wrapped


def test_ready_without_market_snapshot_is_rejected():
    envelope = _ready_envelope()
    result = apply_formation_gate(envelope, market_snapshot=None)
    assert result.proposal_state == PROPOSAL_BLOCKED
    assert REASON_MISSING_MARKET_SNAPSHOT in result.reasons


def test_ready_with_synthetic_snapshot_is_rejected():
    envelope = _ready_envelope()
    snap = from_synthetic_candle("EURUSD", "M15", _candle())
    result = apply_formation_gate(envelope, market_snapshot=snap)
    assert result.proposal_state == PROPOSAL_BLOCKED
    assert REASON_NON_REAL_MARKET_MODE in result.reasons
    assert result.data_provenance.market_data_mode == "SYNTHETIC"  # provenance still recorded


def test_ready_with_replay_snapshot_is_rejected():
    envelope = _ready_envelope()
    snap = from_replay_candle("EURUSD", "M15", _candle(), source="fixture.json")
    result = apply_formation_gate(envelope, market_snapshot=snap)
    assert result.proposal_state == PROPOSAL_BLOCKED
    assert REASON_NON_REAL_MARKET_MODE in result.reasons


def test_ready_with_real_snapshot_passes_and_carries_provenance(monkeypatch):
    c = _candle()
    monkeypatch.setattr(market_snapshot_module, "get_latest_candles", lambda symbol, timeframe, count: [c])
    snap = from_mt5_latest_closed("EURUSD", "M15")

    envelope = _ready_envelope()
    result = apply_formation_gate(envelope, market_snapshot=snap)

    assert result.proposal_state == PROPOSAL_READY
    assert result.data_provenance.market_data_mode == "REAL"
    assert result.data_provenance.market_data_fingerprint == snap.fingerprint
    assert result.reasons == envelope.reasons  # nothing added on success


def test_gate_never_invents_geometry():
    # A REAL-mode pass-through must not touch entry/stop/targets at all -- gate is
    # provenance-only, geometry stays exactly what the adapter already produced.
    envelope = _ready_envelope(entry=1.2345, stop=1.2300, targets=(1.2400, 1.2450))

    def _raise(symbol, timeframe, count):
        raise AssertionError("should not be called in this test")

    snap = from_synthetic_candle("EURUSD", "M15", _candle())
    result = apply_formation_gate(envelope, market_snapshot=snap)
    assert result.entry == 1.2345
    assert result.stop == 1.2300
    assert result.targets == (1.2400, 1.2450)
