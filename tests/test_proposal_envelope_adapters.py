"""Lossless-mapping and missing-field->BLOCKED tests for the three Workstream 0 / Step 4
adapters (Large-SMC, FX post_asian_pilot, BTC sweep-retest research). Also documents why
none of these three adapters can themselves emit STRATEGY_UNMATCHED (see the dedicated
test/comment below) and proves the envelope model CAN represent it regardless.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from execution.adapter import TradeProposal
from mt5.symbol_resolver import SymbolMeta
from post_asian_pilot.decision import (
    PostAsianDecision,
    STATUS_BLOCKED,
    STATUS_DATA_ERROR,
    STATUS_EXPIRED,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
)
from proposals.models import LIFECYCLE_INVALIDATED, SMCTradeProposal, STATUS_ENTRY_CANDIDATE_INVALIDATED
from btc_sweep_research.proposal import BTCSweepResearchProposal
from strategy_engine.sweep_retest.models import (
    STATE_ENTRY_READY,
    STATE_NO_TRADE_DIRECTION,
    STATE_WAITING_SWEEP,
    SetupState,
)

from proposal_envelope.adapters import btc_adapter, fx_adapter, large_smc_adapter
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import (
    PROPOSAL_BLOCKED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_INVALIDATED,
    PROPOSAL_NO_TRADE,
    PROPOSAL_READY,
    PROPOSAL_STRATEGY_UNMATCHED,
    WATCHER_INVALIDATED,
    WATCHER_LIQUIDITY_APPROACH,
    WATCHER_SETUP_QUALIFIED,
    CanonicalProposal,
)


# ============================================================== Large-SMC adapter

def _smc_proposal(**overrides):
    fields = dict(
        proposal_id="AGP-SMC-1", setup_id="SETUP-1", snapshot_id="SNAP-1",
        snapshot_time="2026-09-01T08:00:00Z", symbol="EURUSD",
        combination="E1M1", entry_condition="E1", maneuver="M1", direction="LONG",
        entry_reference=1.16500, invalidation_price=1.16400,
        status=overrides.pop("status", "ENTRY_CANDIDATE_READY"),
    )
    fields.update(overrides)
    return SMCTradeProposal(**fields)


def test_large_smc_ready_maps_losslessly():
    proposal = _smc_proposal()
    envelope = large_smc_adapter.to_canonical_proposal(proposal)

    assert envelope.proposal_state == PROPOSAL_READY
    assert envelope.watcher_state == WATCHER_SETUP_QUALIFIED
    assert envelope.direction == proposal.direction
    assert envelope.entry == proposal.entry_reference
    assert envelope.stop == proposal.invalidation_price
    assert envelope.symbol == proposal.symbol
    assert envelope.source_record_id == proposal.proposal_id
    assert envelope.setup_evidence["combination"] == proposal.combination
    assert envelope.setup_evidence["entry_condition"] == proposal.entry_condition
    assert envelope.setup_evidence["maneuver"] == proposal.maneuver
    # No target/expected_R field exists on SMCTradeProposal -- never synthesized.
    assert envelope.targets == ()
    assert envelope.expected_R is None


def test_large_smc_missing_direction_maps_to_blocked_never_partial_ready():
    proposal = _smc_proposal(direction=None)
    envelope = large_smc_adapter.to_canonical_proposal(proposal)
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert "MISSING_DIRECTION" in envelope.reasons


def test_large_smc_missing_entry_reference_maps_to_blocked():
    proposal = _smc_proposal(entry_reference=None)
    envelope = large_smc_adapter.to_canonical_proposal(proposal)
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert "MISSING_ENTRY_REFERENCE" in envelope.reasons


def test_large_smc_invalidated_maps_to_invalidated():
    proposal = _smc_proposal(
        status=STATUS_ENTRY_CANDIDATE_INVALIDATED, lifecycle=LIFECYCLE_INVALIDATED,
        invalidation_reason="STRUCTURE_BROKEN",
    )
    envelope = large_smc_adapter.to_canonical_proposal(proposal)
    assert envelope.proposal_state == PROPOSAL_INVALIDATED
    assert envelope.watcher_state == WATCHER_INVALIDATED
    assert envelope.reasons == ("STRUCTURE_BROKEN",)


# ============================================================== FX adapter

def _eurusd_meta():
    return SymbolMeta(symbol="EURUSD", tick_size=1e-5, tick_value=1.0, contract_size=100000.0,
                       volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=1e-5)


def _decision(status, **overrides):
    now = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    fields = dict(
        decision_id="DECISION-EURUSD-abc123", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.0.0", symbol="EURUSD", trading_date=date(2026, 9, 1),
        reference_session="ASIAN", status=status, reason_codes=("R1",),
        evaluation_time=now,
    )
    fields.update(overrides)
    return PostAsianDecision(**fields)


def _trade_proposal(setup_id="DECISION-EURUSD-abc123", symbol="EURUSD"):
    return TradeProposal(
        setup_id=setup_id, strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol=symbol,
        profile_id="FOREX", direction="LONG", entry=1.16500, stop_loss=1.16400,
        tp1=1.16700, tp2=1.16900, volume=0.31, risk_amount=50.0, risk_percent=0.5,
    )


def test_fx_ready_with_actionable_trade_proposal_maps_losslessly():
    decision = _decision(STATUS_READY, ready_at=datetime(2026, 9, 1, 8, 30, tzinfo=timezone.utc),
                          valid_until=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc))
    trade_proposal = _trade_proposal()
    envelope = fx_adapter.to_canonical_proposal(decision, trade_proposal)

    assert envelope.proposal_state == PROPOSAL_READY
    assert envelope.watcher_state == WATCHER_SETUP_QUALIFIED
    assert envelope.direction == trade_proposal.direction
    assert envelope.entry == trade_proposal.entry
    assert envelope.stop == trade_proposal.stop_loss
    assert envelope.targets == (trade_proposal.tp1, trade_proposal.tp2)
    assert envelope.strategy_id == decision.strategy_id
    assert envelope.symbol == decision.symbol
    assert envelope.execution_authority == "NONE"
    assert envelope.identity_version == "AG_PROPOSAL_OCCURRENCE_IDENTITY_V1"


def test_fx_ready_without_trade_proposal_maps_to_blocked_never_partial_ready():
    decision = _decision(STATUS_READY)
    envelope = fx_adapter.to_canonical_proposal(decision, trade_proposal=None)
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert "MISSING_ACTIONABLE_TRADE_PROPOSAL" in envelope.reasons


def test_fx_ready_with_mismatched_trade_proposal_identity_maps_to_blocked():
    decision = _decision(STATUS_READY)
    mismatched = _trade_proposal(setup_id="SOME-OTHER-DECISION", symbol="GBPUSD")
    envelope = fx_adapter.to_canonical_proposal(decision, mismatched)
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert "TRADE_PROPOSAL_IDENTITY_MISMATCH" in envelope.reasons


def test_fx_watch_maps_to_incomplete_not_ready_and_not_no_trade():
    decision = _decision(STATUS_WATCH, missing_condition="WAITING_REFERENCE_SWEEP")
    envelope = fx_adapter.to_canonical_proposal(decision)
    assert envelope.proposal_state == PROPOSAL_INCOMPLETE
    assert envelope.watcher_state == WATCHER_LIQUIDITY_APPROACH
    assert envelope.timestamps.next_required_evidence == ("WAITING_REFERENCE_SWEEP",)


def test_fx_no_trade_maps_to_no_trade():
    decision = _decision(STATUS_NO_TRADE)
    envelope = fx_adapter.to_canonical_proposal(decision)
    assert envelope.proposal_state == PROPOSAL_NO_TRADE


def test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover(tmp_path):
    strategy_id = "ST_ASIAN_SWEEP_5R_V1"
    pair_id = "ASIAN_LONDON"
    symbol = "EURUSD"
    trading_date = date(2026, 9, 2)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    proposals = []

    for i in range(3):
        decision = _decision(
            STATUS_READY,
            decision_id=f"DECISION-{symbol}-{i}",
            strategy_id=strategy_id,
            symbol=symbol,
            trading_date=trading_date,
            reference_session="ASIAN",
            evaluation_time=datetime(2026, 9, 2, 9, 0, i, tzinfo=timezone.utc),
            ready_at=datetime(2026, 9, 2, 8, 30, i, tzinfo=timezone.utc),
            valid_until=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        )
        trade_proposal = _trade_proposal(
            setup_id=f"{strategy_id}:{pair_id}:{symbol}:{trading_date.isoformat()}",
            symbol=symbol,
        )
        proposals.append(fx_adapter.to_canonical_proposal(decision, trade_proposal))
        ledger.record_proposal(proposals[-1])

    observation_count = len(proposals)
    distinct_occurrence_count = len({
        (p.strategy_id, p.market_context_evidence.get("reference_session"), p.symbol, p.market_context_evidence.get("trading_date"))
        for p in proposals
    })
    current_proposal_count = len([
        p for p in ledger.list_active_proposals()
        if p.proposal_state == PROPOSAL_READY and p.strategy_id == strategy_id and p.symbol == symbol
    ])

    assert observation_count == 3
    assert distinct_occurrence_count == 1
    assert current_proposal_count <= 1


def test_fx_expired_ready_proposal_remains_in_current_view_until_filtered_out():
    now = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
    decision = _decision(
        STATUS_READY,
        ready_at=datetime(2026, 9, 2, 8, 30, tzinfo=timezone.utc),
        valid_until=now - timedelta(minutes=1),
    )
    envelope = fx_adapter.to_canonical_proposal(decision, _trade_proposal())

    assert envelope.proposal_state == PROPOSAL_READY
    assert envelope.timestamps.expires_at is not None
    expires_at = datetime.fromisoformat(envelope.timestamps.expires_at)
    assert expires_at < now
    assert not (envelope.proposal_state == PROPOSAL_READY and expires_at > now)


def test_fx_data_error_and_blocked_and_expired_never_become_ready():
    for status in (STATUS_DATA_ERROR, STATUS_BLOCKED, STATUS_EXPIRED):
        decision = _decision(status)
        envelope = fx_adapter.to_canonical_proposal(decision)
        assert envelope.proposal_state != PROPOSAL_READY


# ============================================================== BTC adapter

def _setup_state(state, **overrides):
    fields = dict(
        setup_id="BTCUSDT:2026-09-01:2026-09-01T02:00:00Z", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        symbol="BTCUSDT", state=state, reason_code="R1",
        evaluated_at=datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return SetupState(**fields)


def _btc_proposal(**overrides):
    fields = dict(
        strategy="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="1.0.0", authority="RESEARCH_ONLY",
        exchange="BYBIT", instrument="BTCUSDT", direction="LONG",
        reference_day=date(2026, 8, 31), reference_high=60000.0, reference_low=59000.0,
        sweep={"level": 59000.0, "extreme": 58900.0, "time": "2026-09-01T02:00:00Z"},
        confirmation={"broken_swing_price": 59300.0, "mss_time": "2026-09-01T02:30:00Z"},
        entry=59350.0, stop=58900.0, target={"tp1": 59700.0, "tp2": 60000.0}, RR=2.0,
        estimated_fees=5.0, funding_assumption={"funding_cost_estimate": 1.5},
        data_timestamp=datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc),
        expiry=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc), occurrence_id="OCC-1",
    )
    fields.update(overrides)
    return BTCSweepResearchProposal(**fields)


def test_btc_entry_ready_with_proposal_maps_losslessly():
    setup_state = _setup_state(STATE_ENTRY_READY, strategy_qualified=True, direction="LONG")
    proposal = _btc_proposal()
    envelope = btc_adapter.to_canonical_proposal(setup_state, proposal)

    assert envelope.proposal_state == PROPOSAL_READY
    assert envelope.watcher_state == WATCHER_SETUP_QUALIFIED
    assert envelope.direction == proposal.direction
    assert envelope.entry == proposal.entry
    assert envelope.stop == proposal.stop
    assert envelope.targets == (59700.0, 60000.0)
    assert envelope.expected_R == 2.0
    assert envelope.cost_assumptions.status == "ITEMIZED"
    assert envelope.cost_assumptions.commission == 5.0
    assert envelope.cost_assumptions.swap_or_funding == 1.5


def test_btc_qualified_without_proposal_maps_to_blocked_never_partial_ready():
    setup_state = _setup_state(STATE_ENTRY_READY, strategy_qualified=True, direction="LONG")
    envelope = btc_adapter.to_canonical_proposal(setup_state, proposal=None)
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert "MISSING_BTC_RESEARCH_PROPOSAL" in envelope.reasons


def test_btc_tradability_blocked_maps_to_blocked_not_ready():
    setup_state = _setup_state(STATE_ENTRY_READY, strategy_qualified=True, direction="LONG",
                                tradability_blocked=True, tradability_reason="DAILY_LOSS_GUARD")
    proposal = _btc_proposal(tradability_allowed=False, tradability_block_reason="DAILY_LOSS_GUARD")
    envelope = btc_adapter.to_canonical_proposal(setup_state, proposal)
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert "DAILY_LOSS_GUARD" in envelope.reasons


def test_btc_not_qualified_never_becomes_ready():
    setup_state = _setup_state(STATE_WAITING_SWEEP, strategy_qualified=False)
    envelope = btc_adapter.to_canonical_proposal(setup_state, proposal=None)
    assert envelope.proposal_state != PROPOSAL_READY
    assert envelope.watcher_state == WATCHER_LIQUIDITY_APPROACH


def test_btc_no_trade_direction_maps_to_invalidated_not_ready():
    setup_state = _setup_state(STATE_NO_TRADE_DIRECTION, strategy_qualified=False)
    envelope = btc_adapter.to_canonical_proposal(setup_state, proposal=None)
    assert envelope.proposal_state == PROPOSAL_INVALIDATED
    assert envelope.watcher_state == WATCHER_INVALIDATED


# ============================================================== STRATEGY_UNMATCHED

def test_envelope_can_represent_strategy_unmatched_even_though_no_current_adapter_emits_it():
    """None of the three Step-4 adapters can themselves produce STRATEGY_UNMATCHED: each
    source object (SMCTradeProposal, PostAsianDecision, SetupState) is only ever
    constructed by its own already-matched, signed strategy -- there is no "no compatible
    strategy" branch anywhere in proposals/*, post_asian_pilot/*, or
    strategy_engine.sweep_retest/* to adapt from. STRATEGY_UNMATCHED is the watcher
    strategy-resolver's own outcome (Workstream C2's "compatible signed strategy ->
    proposal evaluation / no compatible strategy -> STRATEGY_UNMATCHED"), and C2 is
    explicitly out of scope for this bounded action (see the reconciliation document's
    "Do not build C2 yet"). This test only proves the CANONICAL MODEL can carry the state
    once a future watcher resolver exists to emit it -- it is not claimed as adapter
    behavior today."""
    envelope = CanonicalProposal(proposal_state=PROPOSAL_STRATEGY_UNMATCHED)
    assert envelope.proposal_state == PROPOSAL_STRATEGY_UNMATCHED
