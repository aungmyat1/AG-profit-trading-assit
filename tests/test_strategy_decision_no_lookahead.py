"""Phase 4 (no-lookahead) coverage for the NEW code this task adds.

Discovery finding: AG already has a sufficiently general no-lookahead/replay-determinism
harness (tests/test_historical_replay_no_lookahead.py, backed by
historical_replay.HistoricalCandleStore/historical_data_context), which enforces the
prefix/sliced-replay invariant at the point where it actually matters -- candle/tick
access inside the native strategy engines (FX's strategy_engine.session router, BTC's
strategy_engine.sweep_retest.engine, Large-SMC's historical_replay.stage2 pipeline). This
task does not duplicate that harness.

What IS new in this task is src/strategy_contract/decision.py's adapter functions
(from_fx_decision/from_btc_setup_state/from_large_smc_decision). They introduce no new
lookahead risk because they are pure, referentially-transparent mappings: given an
ALREADY-PRODUCED native decision object, they only ever copy fields out of it -- they
never call get_candles/get_tick, never read wall-clock time, and never take an
"as-of" parameter that could let them peek past a native decision's own authoritative
decision_timestamp. These tests are the targeted regression check for exactly that
property, per the task's Phase 4 scope (extend, don't duplicate, the general harness).
"""
from __future__ import annotations

import datetime as dt

from large_smc_research.decision import LargeSMCResearchDecision, LargeSMCDecisionState
from post_asian_pilot.decision import PostAsianDecision
from strategy_engine.models import TradeSignal
from strategy_engine.sweep_retest.models import STATE_ENTRY_READY, SetupState
from strategy_contract.decision import from_btc_setup_state, from_fx_decision, from_large_smc_decision

UTC = dt.timezone.utc


def test_fx_adapter_decision_timestamp_never_exceeds_native_ready_at():
    """The adapter's decision_timestamp must equal the native decision's own ready_at
    (the CLOSED candle that caused READY) -- never a later, "we know more now" time."""
    ready_at = dt.datetime(2026, 9, 1, 6, 35, tzinfo=UTC)
    signal = TradeSignal(
        signal_id="SIG-1", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        symbol="EURUSD", pair_id="ASIAN_LONDON", reference_session="asian",
        session_date=dt.date(2026, 9, 1), box_high=1.11, box_low=1.10, box_mid=1.105,
        regime="SWEEP", setup="SWEEP", status="SIGNAL", reason_code="SWEEP_CONFIRMED",
        direction="LONG", entry=1.1010, stop_loss=1.0990, signal_timestamp=ready_at,
    )
    later_eval_time = dt.datetime(2026, 9, 1, 9, 0, tzinfo=UTC)  # much later "now"
    decision = PostAsianDecision(
        decision_id="DECISION-EURUSD-abc", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol="EURUSD", trading_date=dt.date(2026, 9, 1),
        reference_session="asian", status="READY", reason_codes=("SWEEP_CONFIRMED",),
        evaluation_time=later_eval_time, signal=signal, ready_at=ready_at,
    )

    result = from_fx_decision(decision)

    assert result.decision_timestamp == ready_at
    assert result.decision_timestamp != later_eval_time


def test_adapter_output_is_a_deterministic_pure_function_of_its_input():
    """Same native decision in -> identical StrategyDecision out, every time -- proves
    the adapter has no hidden state/clock dependency that could vary between a live call
    and a historical replay call at the same logical point."""
    state = SetupState(
        setup_id="SETUP-BTCUSDT-1", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        symbol="BTCUSDT", state=STATE_ENTRY_READY, reason_code="RETEST_CONFIRMED",
        evaluated_at=dt.datetime(2026, 9, 1, 3, 0, tzinfo=UTC), direction="LONG",
        entry=60000.0, stop_loss=59500.0, strategy_qualified=True,
    )

    first = from_btc_setup_state(state, strategy_version="2.0.0")
    second = from_btc_setup_state(state, strategy_version="2.0.0")

    assert first == second


def test_large_smc_adapter_never_widens_evaluation_timestamp():
    decision = LargeSMCResearchDecision(
        strategy_version="1.0.6", symbol="XAUUSD",
        evaluation_timestamp=dt.datetime(2026, 9, 1, 4, 0, tzinfo=UTC),
        direction="LONG", candidate_occurrence_id="OCC-1",
        state=LargeSMCDecisionState.BLOCKED.value,
        reason_codes=("UNSIGNED_CONTRACT:C10_BROKER_STOP",),
    )

    result = from_large_smc_decision(decision)

    assert result.decision_timestamp == decision.evaluation_timestamp
