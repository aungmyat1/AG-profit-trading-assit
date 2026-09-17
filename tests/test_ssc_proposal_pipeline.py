"""AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2, WP9: narrow tests for the SSC
real-market proposal pipeline (ssc_adapter + session_sweep_continuation_pilot). Reuses
the exact fixture tests/test_session_sweep_continuation_replay_determinism.py already
established (one deterministic accepted S1 setup) rather than inventing a second one.
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta, timezone

import pytest

from market_intelligence.models import MarketBiasResult
from proposal_envelope.adapters.ssc_adapter import to_canonical_proposal
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import PROPOSAL_BLOCKED, PROPOSAL_READY
from proposal_envelope.strategy_authority import resolve_strategy_authority
from session_sweep_continuation import STRATEGY_ID, STRATEGY_VERSION
from session_sweep_continuation.config import load_config
from session_sweep_continuation.replay import run_replay
from strategy_contract.market_snapshot import from_real_candle, from_synthetic_candle
from strategy_engine.session.candles import Candle

PIP = 0.0001
DAY = date(2026, 9, 10)


def _bullish_bias(symbol="EURUSD"):
    decision_time = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    return MarketBiasResult(
        bias="BULLISH", confidence="EVIDENCE_BACKED",
        decision_cycle_id=f"{symbol}:{decision_time.date()}:ASIAN_LONDON",
        symbol=symbol, decision_time=decision_time,
        htf_structure="TEST_FIXTURE", mtf_alignment="NOT_EVALUATED_M1",
        liquidity_context="NOT_EVALUATED_M1", session_context="NOT_EVALUATED_M1",
        reason_codes=("TEST_FIXTURE",), model_version="TEST_FIXTURE", input_fingerprint="TEST_FIXTURE",
    )


def _build_synthetic_range_and_sweep_day():
    candles = []
    t0 = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    price = 1.1000
    for i in range(24):
        t = t0 + timedelta(minutes=15 * i)
        o = price
        h = price + 0.0004
        l = price - 0.0004
        c = price + (0.0001 if i % 2 == 0 else -0.0001)
        candles.append(Candle(t, o, h, l, c))
        price = c

    ref_low = min(c.low for c in candles)
    t_trade0 = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)
    for i in range(16):
        t = t_trade0 + timedelta(minutes=15 * i)
        if i == 0:
            o, h, l, c = 1.1000, 1.1005, ref_low - 0.0010, 1.1000
        else:
            o, h, l, c = 1.1000, 1.1006, 1.0994, 1.1000
        candles.append(Candle(t, o, h, l, c))
    return candles


def _config():
    cfg = dict(load_config(repo_root="."))
    cfg["regime"] = dict(cfg["regime"])
    cfg["regime"]["ema_fast_period"] = 3
    cfg["regime"]["ema_slow_period"] = 5
    cfg["regime"]["min_reference_candles"] = 8
    return cfg


def _accepted_setup_and_snapshot():
    candles = _build_synthetic_range_and_sweep_day()
    config = _config()
    result = run_replay(candles, config, "EURUSD", "ASIAN_LONDON", DAY, PIP, bias_result=_bullish_bias())
    assert len(result.accepted_setups) == 1
    snapshot = from_real_candle("EURUSD", "M15", candles[-1])
    return result, result.accepted_setups[0], snapshot


def _authority(**overrides):
    authority = resolve_strategy_authority(STRATEGY_ID, STRATEGY_VERSION)
    if overrides:
        import dataclasses
        authority = dataclasses.replace(authority, **overrides)
    return authority


# 1/4/6: real accepted setup -> PROPOSAL_READY; demo_authorized False still permits it;
# execution_eligible/proposal_only stay fail-closed regardless.
def test_accepted_setup_produces_ready_proposal_with_execution_blocked():
    result, accepted, snapshot = _accepted_setup_and_snapshot()
    envelope = to_canonical_proposal(
        accepted, symbol="EURUSD", session_pair_id="ASIAN_LONDON", trading_date=DAY,
        campaign_id=result.campaign.campaign_id, strategy_authority=_authority(),
    )
    gated = apply_formation_gate(envelope, market_snapshot=snapshot)

    assert gated.proposal_state == PROPOSAL_READY
    assert gated.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert gated.strategy_version == "1.0.1"
    assert gated.demo_authorized is False
    assert gated.live_authorized is False
    assert gated.economic_edge_established is False
    assert gated.proposal_only is True
    assert gated.execution_eligible is False
    assert gated.broker_mutation_blocked is True
    assert gated.setup_evidence["setup_model"] == accepted["setup_model"]  # S1/S2/S3 identity preserved


# 2: no accepted setups -> caller forms nothing (mirrors pipeline.py's own empty-list branch).
def test_no_accepted_setups_forms_no_proposal():
    candles = _build_synthetic_range_and_sweep_day()
    config = _config()
    result = run_replay(candles, config, "EURUSD", "ASIAN_LONDON", DAY, PIP)  # bias omitted -> BIAS_MISSING
    assert result.accepted_setups == []


# 9: synthetic candles can never produce a REAL_MARKET proposal.
def test_synthetic_snapshot_blocks_formation():
    result, accepted, _real_snapshot = _accepted_setup_and_snapshot()
    envelope = to_canonical_proposal(
        accepted, symbol="EURUSD", session_pair_id="ASIAN_LONDON", trading_date=DAY,
        campaign_id=result.campaign.campaign_id, strategy_authority=_authority(),
    )
    synthetic_snapshot = from_synthetic_candle(
        "EURUSD", "M15", Candle(datetime(2026, 9, 10, 11, 0, tzinfo=timezone.utc), 1.1, 1.1, 1.1, 1.1),
    )
    gated = apply_formation_gate(envelope, market_snapshot=synthetic_snapshot)
    assert gated.proposal_state == PROPOSAL_BLOCKED


def test_missing_snapshot_blocks_formation():
    result, accepted, _snapshot = _accepted_setup_and_snapshot()
    envelope = to_canonical_proposal(
        accepted, symbol="EURUSD", session_pair_id="ASIAN_LONDON", trading_date=DAY,
        campaign_id=result.campaign.campaign_id, strategy_authority=_authority(),
    )
    gated = apply_formation_gate(envelope, market_snapshot=None)
    assert gated.proposal_state == PROPOSAL_BLOCKED


# 5/8: duplicate + restart idempotency.
def test_ledger_idempotent_on_duplicate_and_restart():
    result, accepted, snapshot = _accepted_setup_and_snapshot()
    envelope = to_canonical_proposal(
        accepted, symbol="EURUSD", session_pair_id="ASIAN_LONDON", trading_date=DAY,
        campaign_id=result.campaign.campaign_id, strategy_authority=_authority(),
    )
    gated = apply_formation_gate(envelope, market_snapshot=snapshot)
    assert gated.proposal_state == PROPOSAL_READY

    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/ledger.json"
        ledger1 = ProposalLedger(path)
        first = ledger1.record_proposal(gated)
        second = ledger1.record_proposal(gated)  # duplicate cycle run
        assert first.proposal_envelope_id == second.proposal_envelope_id
        assert first.version == second.version == 1

        ledger2 = ProposalLedger(path)  # simulated restart -- fresh instance, same store path
        restarted = ledger2.get_proposal(gated.proposal_envelope_id)
        assert restarted is not None
        assert restarted.proposal_envelope_id == gated.proposal_envelope_id
        assert len(ledger2.list_active_proposals()) == 1


# 11: unmodeled friction stays UNKNOWN, never fabricated as zero-cost/ITEMIZED.
def test_unavailable_friction_never_fabricated():
    accepted_setup = {
        "setup_model": "S1", "direction": "LONG", "entry_time": datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc),
        "entry_price": 1.1000, "stop_price": 1.0990, "risk_pct": 0.4, "fill_precision": "M15_OHLC",
        "outcome": {"terminal_state": "RESOLVED_SESSION_EXIT", "gross_R": None, "net_R": None, "cost_status": "UNAVAILABLE"},
    }
    envelope = to_canonical_proposal(
        accepted_setup, symbol="EURUSD", session_pair_id="ASIAN_LONDON", trading_date=DAY,
        campaign_id="TEST_CAMPAIGN", strategy_authority=_authority(),
    )
    assert envelope.cost_assumptions.status == "NOT_INCLUDED"
    assert envelope.cost_assumptions.spread is None
    assert envelope.cost_assumptions.commission is None
    assert envelope.cost_assumptions.slippage is None


# 12: no execution import reachable from the new orchestration/adapter modules.
def test_no_execution_imports_in_ssc_pilot_or_adapter():
    import inspect
    import session_sweep_continuation_pilot.pipeline as pipeline_module
    import proposal_envelope.adapters.ssc_adapter as adapter_module

    for module in (pipeline_module, adapter_module):
        source = inspect.getsource(module)
        for forbidden in ("execution.executor", "execution.mt5_gateway", "mt5.management_gateway"):
            assert forbidden not in source, f"{module.__name__} must never import {forbidden}"
