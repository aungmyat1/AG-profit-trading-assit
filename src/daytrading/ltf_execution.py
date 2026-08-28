"""DayTrading skill 3: LTF Execution -- "does lower-timeframe price action provide a
valid execution trigger for the current DayTrading setup?"

NOT a second entry-confirmation detector: orchestrates entry_confirmation.
evaluate_entry_confirmation() (displacement/structure-shift/liquidity-reclaim/rejection,
already SMC-owned) and gates it behind this technique's own NarrativeBiasResult and
DayTradingLiquidityAffinityResult. A confirmed M5 signal with no resolved narrative/
affinity context never reaches evaluate_entry_confirmation() at all -- it stays DORMANT/
WAITING (spec section 6/21), never a trade.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional, Sequence

from entry_confirmation import (
    CandidateDirection,
    EntryConfirmationRequest,
    OverallState,
    SweepShiftArrayRequest,
    evaluate_entry_confirmation,
    evaluate_sweep_shift_array,
)
from strategy_engine.session import Candle

from .execution_models import (
    evaluate_clean_sweep,
    evaluate_gap_liquidity_respect,
    evaluate_inverted_gap,
    evaluate_liquidity_grab,
    evaluate_spread_sweep,
    evaluate_sweep_and_fail,
    evaluate_sweep_and_inducement,
)
from .models import (
    BIAS_BEARISH,
    BIAS_BULLISH,
    AFFINITY_PARTIAL,
    AFFINITY_RESOLVED,
    EXEC_MODEL_MULTIPLE,
    EXEC_MODEL_NONE,
    EXEC_STATUS_DORMANT,
    EXEC_STATUS_INDETERMINATE,
    EXEC_STATUS_INVALIDATED,
    EXEC_STATUS_MODEL_CONFIRMED,
    EXEC_STATUS_NOT_CONFIRMED,
    EXEC_STATUS_SWEEP_DETECTED,
    EXEC_STATUS_WAITING_CANDLE_CLOSE,
    EXEC_STATUS_WAITING_CONFIRMATION,
    EXEC_STATUS_WAITING_CONTEXT,
    EXEC_STATUS_WAITING_ENTRY_PRICE,
    EXEC_STATUS_WAITING_SWEEP,
    ENTRY_METHOD_NONE,
    LTF_CONFIRMED,
    LTF_DORMANT,
    LTF_INDETERMINATE,
    LTF_INVALIDATED,
    LTF_NOT_CONFIRMED,
    LTF_WAITING,
    DayTradingLiquidityAffinityResult,
    ExecutionModelAssessment,
    LTFExecutionResult,
    NarrativeBiasResult,
)

_EXPECTED_DIRECTION = {BIAS_BULLISH: CandidateDirection.LONG, BIAS_BEARISH: CandidateDirection.SHORT}
_OVERALL_TO_LTF = {
    OverallState.CONFIRMED: LTF_CONFIRMED,
    OverallState.NOT_CONFIRMED: LTF_NOT_CONFIRMED,
    OverallState.PARTIAL: LTF_WAITING,
    OverallState.INDETERMINATE: LTF_INDETERMINATE,
}

# Selection order when multiple assessments are non-trivial (spec section 66: no
# star-rating/priority is invented -- this only orders how "informative" a status is
# for picking execution_status, never which MODEL wins when several CONFIRM).
_STATUS_SEVERITY = {
    EXEC_STATUS_MODEL_CONFIRMED: 5,
    EXEC_STATUS_WAITING_ENTRY_PRICE: 4,
    EXEC_STATUS_WAITING_CONFIRMATION: 3,
    EXEC_STATUS_SWEEP_DETECTED: 2,
    EXEC_STATUS_WAITING_SWEEP: 2,
    EXEC_STATUS_NOT_CONFIRMED: 1,
    EXEC_STATUS_INDETERMINATE: 0,
}


def _forming_candle_would_sweep(direction: str, protected_level: Optional[float], forming_candle: Optional[Candle]) -> bool:
    if protected_level is None or forming_candle is None:
        return False
    return forming_candle.high > protected_level if direction == "SHORT" else forming_candle.low < protected_level


def _invalidated_by_later_close(direction: str, selected, candles: Sequence[Candle]) -> bool:
    """Spec section 67: a CONFIRMED candidate must not remain silently active once a
    later CLOSED candle closes back through its own structural_invalidation_reference.
    Only candles strictly after the confirming candle count -- the confirming candle's
    own close never self-invalidates its model (spec section 21 forbidding manufactured
    invalidation)."""
    if selected is None or selected.structural_invalidation_reference is None or selected.confirmation_candle_time is None:
        return False
    ref = selected.structural_invalidation_reference
    later = [c for c in candles if c.time > selected.confirmation_candle_time]
    return any((c.close > ref) for c in later) if direction == "SHORT" else any((c.close < ref) for c in later)


def classify_execution_models(
    direction: str,
    protected_high: Optional[float] = None,
    protected_low: Optional[float] = None,
    m5_closed_candles: Sequence[Candle] = (),
    m5_forming_candle: Optional[Candle] = None,
    gap_low: Optional[float] = None,
    gap_high: Optional[float] = None,
    gap_status: Optional[str] = None,
    inducement_confirmed: Optional[bool] = None,
):
    """Runs every execution-model classifier over the same causal, CLOSED candle window
    and picks execution_model/execution_status (spec sections 9-10, 29, 66). Returns
    (matching_models, execution_model, execution_status, selected). `m5_closed_candles`
    must already exclude the currently forming bar (spec sections 43-44) -- pass it
    separately as `m5_forming_candle`, used only for WAITING_CANDLE_CLOSE detection,
    never as evidence for any rule."""
    protected_level = protected_high if direction == "SHORT" else protected_low

    assessments = (
        evaluate_clean_sweep(direction, protected_level, m5_closed_candles),
        evaluate_spread_sweep(direction, protected_level),
        evaluate_sweep_and_fail(direction, protected_level, m5_closed_candles),
        evaluate_sweep_and_inducement(direction, protected_level, m5_closed_candles, inducement_confirmed),
        evaluate_liquidity_grab(direction, protected_level, m5_closed_candles, gap_low, gap_high),
        evaluate_gap_liquidity_respect(direction, gap_low, gap_high, m5_closed_candles),
        evaluate_inverted_gap(direction, gap_status),
    )

    confirmed = [a for a in assessments if a.status in (EXEC_STATUS_MODEL_CONFIRMED, EXEC_STATUS_WAITING_ENTRY_PRICE)]
    if len(confirmed) > 1:
        execution_model = EXEC_MODEL_MULTIPLE
        selected = None
    elif len(confirmed) == 1:
        execution_model = confirmed[0].model_type
        selected = confirmed[0]
    else:
        execution_model = EXEC_MODEL_NONE
        selected = None

    best = max(assessments, key=lambda a: _STATUS_SEVERITY.get(a.status, -1), default=None)
    execution_status = (selected.status if selected is not None else (best.status if best is not None else EXEC_STATUS_INDETERMINATE))

    if execution_status in (EXEC_STATUS_MODEL_CONFIRMED, EXEC_STATUS_WAITING_ENTRY_PRICE) and \
            _invalidated_by_later_close(direction, selected, m5_closed_candles):
        execution_status = EXEC_STATUS_INVALIDATED
        selected = replace(selected, status=EXEC_STATUS_INVALIDATED)

    if execution_status not in (EXEC_STATUS_MODEL_CONFIRMED, EXEC_STATUS_WAITING_ENTRY_PRICE) and \
            execution_status != EXEC_STATUS_INVALIDATED and \
            _forming_candle_would_sweep(direction, protected_level, m5_forming_candle):
        execution_status = EXEC_STATUS_WAITING_CANDLE_CLOSE

    return assessments, execution_model, execution_status, selected


def evaluate_ltf_execution(
    symbol: str,
    execution_timeframe: str,
    narrative_bias: NarrativeBiasResult,
    liquidity_affinity: DayTradingLiquidityAffinityResult,
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
    ec_request: Optional[EntryConfirmationRequest] = None,
    h1_structure_direction: Optional[str] = None,
    protected_high: Optional[float] = None,
    protected_low: Optional[float] = None,
    m5_closed_candles: Sequence[Candle] = (),
    m5_forming_candle: Optional[Candle] = None,
    gap_low: Optional[float] = None,
    gap_high: Optional[float] = None,
    gap_status: Optional[str] = None,
    inducement_confirmed: Optional[bool] = None,
    sweep_shift_request: Optional[SweepShiftArrayRequest] = None,
) -> LTFExecutionResult:
    base = dict(symbol=symbol, execution_timeframe=execution_timeframe,
                h1_structure_direction=h1_structure_direction,
                protected_high=protected_high, protected_low=protected_low)

    if narrative_bias.bias not in _EXPECTED_DIRECTION:
        return LTFExecutionResult(**base, status=LTF_DORMANT, execution_status=EXEC_STATUS_DORMANT,
                                   reason=f"narrative_bias={narrative_bias.bias} -- LTF execution stays "
                                          f"dormant without a directional day-trading narrative.")
    if liquidity_affinity.status not in (AFFINITY_RESOLVED, AFFINITY_PARTIAL):
        return LTFExecutionResult(**base, status=LTF_DORMANT, execution_status=EXEC_STATUS_DORMANT,
                                   reason=f"liquidity_affinity={liquidity_affinity.status} -- "
                                          f"no valid trading location to watch.")

    expected_direction = _EXPECTED_DIRECTION[narrative_bias.bias]
    if candidate_direction != expected_direction:
        return LTFExecutionResult(
            **base, context_valid=True, status=LTF_WAITING, execution_status=EXEC_STATUS_WAITING_CONTEXT,
            reason=f"context valid (narrative={narrative_bias.bias}, affinity={liquidity_affinity.status}); "
                   f"no {expected_direction.value} candidate on {execution_timeframe} yet.",
        )

    matching_models: tuple = ()
    execution_model = EXEC_MODEL_NONE
    execution_status = EXEC_STATUS_WAITING_CONTEXT
    selected: Optional[ExecutionModelAssessment] = None
    if m5_closed_candles and (protected_high is not None or protected_low is not None):
        matching_models, execution_model, execution_status, selected = classify_execution_models(
            candidate_direction.value, protected_high, protected_low, m5_closed_candles, m5_forming_candle,
            gap_low, gap_high, gap_status, inducement_confirmed,
        )

    model_fields = dict(
        matching_models=matching_models, execution_model=execution_model, execution_status=execution_status,
        selected_assessment=selected,
        entry_method=selected.entry_method if selected is not None else ENTRY_METHOD_NONE,
        entry_reference_price=selected.entry_reference_price if selected is not None else None,
        structural_invalidation_reference=selected.structural_invalidation_reference if selected is not None else None,
        confirmation_candle_time=selected.confirmation_candle_time if selected is not None else None,
        confirmation_candle_close=selected.confirmation_candle_close if selected is not None else None,
        unresolved_policies=tuple(a.unresolved_policy for a in matching_models if a.unresolved_policy),
    )

    # A structurally invalidated model candidate must surface as LTF_INVALIDATED
    # regardless of entry_confirmation's own (SMC-owned, unrelated) overall_state --
    # spec section 67/section F of DAYTRADING_LTF_EXECUTION_RUNTIME_V1.
    if execution_status == EXEC_STATUS_INVALIDATED:
        return LTFExecutionResult(
            **base, **model_fields, direction=candidate_direction.value, context_valid=True, status=LTF_INVALIDATED,
            reason=f"{execution_model} was CONFIRMED but a later closed candle closed back through "
                   f"structural_invalidation_reference={model_fields['structural_invalidation_reference']}.",
        )

    if ec_request is None:
        return LTFExecutionResult(
            **base, **model_fields, direction=candidate_direction.value, context_valid=True, status=LTF_WAITING,
            reason=f"context valid; no {execution_timeframe} candle/confirmation data supplied yet.",
        )

    ec_result = evaluate_entry_confirmation(ec_request)
    status = _OVERALL_TO_LTF[ec_result.overall_state]

    # Spec section 16: SMCSweepShiftArrayResult (entry_confirmation.engine_v2_1) is
    # optional corroborating evidence over the same H1 pivot/M5 structure-shift facts --
    # never a second independent confirmation engine. Fail closed on disagreement
    # (spec section 8): a v1-based CONFIRMED demotes to NOT_CONFIRMED if the
    # sweep-shift-array explicitly disagrees; it never upgrades a v1 NOT_CONFIRMED/
    # WAITING result to CONFIRMED on its own.
    sweep_shift_result = evaluate_sweep_shift_array(sweep_shift_request) if sweep_shift_request is not None else None
    reason = None if status == LTF_CONFIRMED else f"entry_confirmation overall_state={ec_result.overall_state.value}."
    if status == LTF_CONFIRMED and sweep_shift_result is not None and sweep_shift_result.aggregation_status == "NOT_CONFIRMED":
        status = LTF_NOT_CONFIRMED
        reason = (f"entry_confirmation overall_state={ec_result.overall_state.value} but "
                  f"sweep_shift_result disagreed (aggregation_status=NOT_CONFIRMED, "
                  f"status={sweep_shift_result.status}) -- fail closed.")

    return LTFExecutionResult(
        **base, **model_fields, direction=candidate_direction.value, context_valid=True,
        liquidity_event=ec_result.liquidity_reclaim.status.value,
        structure_shift=ec_result.structure_shift.status.value,
        displacement=ec_result.displacement.status.value,
        confirmation_result=ec_result, sweep_shift_result=sweep_shift_result, status=status,
        reason=reason,
    )
