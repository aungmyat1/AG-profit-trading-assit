"""LargeSMCResearchEngine -- the thin, ST_LARGE_SMC_V1-labeled orchestration layer
(RESEARCH_ONLY_FUNNEL_V1 phase). Owns nothing detection-shaped: every E/M/composition
call below is a direct call into the already-frozen, already-golden-validated
`historical_replay.stage2` boundary (zero E/M redetection, per that module's own
docstring). This module adds exactly four things stage2 does not: (1) strategy identity
stamping, (2) C11 target selection (target_model.py), (3) candidate-occurrence identity
wiring (proposals/occurrence_identity.py, previously implemented but never called by
anything), (4) explicit, fail-closed decision states -- including refusing to fabricate
an actionable state when C10 (broker stop) or pending-entry expiry are unsigned.

MUST be called inside `historical_replay.data_source_patch.historical_data_context` (or
an equivalent live substitution) -- exactly the same requirement
`stage2.evaluate_entry_stage` itself documents. This module performs zero MT5 access of
its own; it only calls already-patched module attributes
(`historical_replay.stage2.get_latest_candles` / `.get_tick`,
`market_structure.tiers.analyze_structure_tiers`), so no change to
`historical_replay/data_source_patch.py`'s patch-target allowlist was needed.

C18 (simultaneous-combination selection): resolved by reuse of C14's already-frozen
`candidate_identity.selection`/`coexistence` fields (`strategy_level_single_winner_
required: NO`, `multiple_distinct_candidates_allowed: YES`,
`portfolio_selection_boundary: DOWNSTREAM_FUTURE_AUTHORITY`) -- every composed E*M
combination is returned as its own independent decision with its own
`candidate_occurrence_id`, never narrowed by list order or any other accidental
priority (the task explicitly prohibits that). `evaluate()` therefore returns a tuple,
not a single decision.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence, Tuple

import historical_replay.stage2 as stage2
from entry_confirmation.entry_models_v1 import EntryModelState
from historical_replay.stage1 import QualifiedEEvent, Stage1Dataset
from market_structure.tiers import analyze_structure_tiers
from mt5.market_data import MarketDataError
from proposals.gate import _matching_m_result
from proposals.identity import reference_key_for, setup_id as _setup_id
from proposals.occurrence_identity import candidate_occurrence_id as _candidate_occurrence_id
from proposals.occurrence_identity import eligibility_interval_id as _eligibility_interval_id

from .decision import (
    ENGINE_VERSION,
    REASON_INSUFFICIENT_DATA,
    REASON_REJECT_NO_TARGET,
    REASON_SYMBOL_NOT_IN_FROZEN_UNIVERSE,
    REASON_UNSIGNED_C10_BROKER_STOP,
    REASON_UNSIGNED_PENDING_ENTRY_EXPIRY,
    STRATEGY_ID,
    LargeSMCDecisionState,
    LargeSMCResearchDecision,
)
from .target_model import select_target

STRATEGY_VERSION = "1.0.5"

# C01, RESOLVED (2026-09-01): EURUSD only for the first discovery run. GBPUSD explicitly
# deferred until the funnel works and data quality passes on EURUSD -- see
# strategies/ST_LARGE_SMC_V1.yaml `instruments:`. No dynamic/inferred symbol inclusion.
FROZEN_INSTRUMENT_UNIVERSE = ("EURUSD",)

_WAITING_STATES = (
    EntryModelState.WAITING_HTF_TOUCH.value, EntryModelState.WAITING_H1_REACTION.value,
    EntryModelState.WAITING_M5_CONFIRMATION.value, EntryModelState.WAITING_M5_ENTRY.value,
)

_M5_TIMEFRAME = "M5"
_M5_CANDLE_COUNT = 200  # matches historical_replay.orchestrator.M5_WARMUP_CANDLES / daytrading_runtime's own M5_LOOKBACK_CANDLES


def _decision(**kwargs) -> LargeSMCResearchDecision:
    kwargs.setdefault("strategy_id", STRATEGY_ID)
    kwargs.setdefault("strategy_version", STRATEGY_VERSION)
    kwargs.setdefault("engine_version", ENGINE_VERSION)
    return LargeSMCResearchDecision(**kwargs)


def _active_interval(event: QualifiedEEvent, t: datetime):
    for start, end in event.eligibility_intervals:
        if start <= t < end:
            return start, end
    return None


def _most_recently_ended_interval(event: QualifiedEEvent, t: datetime):
    ended = [(s, e) for s, e in event.eligibility_intervals if e <= t]
    return max(ended, key=lambda se: se[1]) if ended else None


class LargeSMCResearchEngine:
    """`evaluate(symbol, evaluation_time, stage1_dataset)` -> tuple of
    `LargeSMCResearchDecision`, one per E*M combination independently observed at
    `evaluation_time` (see module docstring, C18)."""

    def evaluate(
        self, symbol: str, evaluation_time: datetime, stage1_dataset: Stage1Dataset,
    ) -> Tuple[LargeSMCResearchDecision, ...]:
        if symbol not in FROZEN_INSTRUMENT_UNIVERSE:
            return (_decision(
                symbol=symbol, evaluation_timestamp=evaluation_time,
                state=LargeSMCDecisionState.DATA_ERROR.value,
                reason_codes=(REASON_SYMBOL_NOT_IN_FROZEN_UNIVERSE,), data_quality_state="DATA_ERROR",
            ),)

        decisions = []
        for event in stage1_dataset.events:
            if event.symbol != symbol:
                continue
            decisions.extend(self._evaluate_event(symbol, evaluation_time, event, stage1_dataset.liquidity_timeline))
        return tuple(decisions)

    def _evaluate_event(
        self, symbol: str, evaluation_time: datetime, event: QualifiedEEvent, liquidity_timeline,
    ) -> Sequence[LargeSMCResearchDecision]:
        active = _active_interval(event, evaluation_time)
        if active is None:
            # C12: not currently eligible. Emit EXPIRED exactly once, at/after the end
            # of the most recently ENDED interval -- never for a not-yet-started future
            # interval (non_monotonic: that occurrence's story continues at that later
            # interval, on a subsequent evaluate() call, not here).
            ended = _most_recently_ended_interval(event, evaluation_time)
            if ended is None:
                return ()  # not yet eligible for the first time -- nothing to report
            interval_start, interval_end = ended
            return (_decision(
                symbol=symbol, evaluation_timestamp=evaluation_time,
                entry_condition=event.entry_condition, direction=event.direction,
                event_id=event.event_id,
                eligibility_interval_id=_eligibility_interval_id(event.event_id, interval_start, interval_end),
                e_context_eligibility_end=interval_end,
                state=LargeSMCDecisionState.EXPIRED.value,
            ),)

        interval_start, interval_end = active
        try:
            analysis = stage2.evaluate_entry_stage_canonical_v2(symbol, event, evaluation_time, liquidity_timeline)
        except MarketDataError as exc:
            return (_decision(
                symbol=symbol, evaluation_timestamp=evaluation_time,
                entry_condition=event.entry_condition, direction=event.direction, event_id=event.event_id,
                state=LargeSMCDecisionState.DATA_ERROR.value,
                reason_codes=(REASON_INSUFFICIENT_DATA, exc.reason_code), data_quality_state="DATA_ERROR",
            ),)

        out = []
        for combo in analysis.combinations:
            out.append(self._evaluate_combination(symbol, evaluation_time, event, combo, analysis, interval_start, interval_end))
        return out

    def _evaluate_combination(self, symbol, evaluation_time, event, combo, analysis, interval_start, interval_end):
        reference_key = reference_key_for(event.reference_type, event.reference_low, event.reference_high, event.reference_level)
        setup_family_id = _setup_id(symbol, combo.combination, combo.direction, reference_key)
        interval_id = _eligibility_interval_id(event.event_id, interval_start, interval_end)
        m_result = _matching_m_result(analysis, combo)
        m_source_id = getattr(m_result, "source_id", None) if m_result is not None else None
        occurrence_id = _candidate_occurrence_id(setup_family_id, interval_id, m_source_id)

        common = dict(
            symbol=symbol, evaluation_timestamp=evaluation_time,
            entry_condition=combo.entry_condition, maneuver=combo.maneuver, combination=combo.combination,
            direction=combo.direction, event_id=event.event_id, setup_family_id=setup_family_id,
            eligibility_interval_id=interval_id, m_candidate_source_id=m_source_id,
            candidate_occurrence_id=occurrence_id, entry_array=combo.entry_array, entry_price=combo.entry_price,
            structural_invalidation_price=combo.invalidation_price,
            structural_invalidation_source_type=combo.invalidation_source_type,
            structural_invalidation_reason=combo.invalidation_reason,
            structural_invalidation_trigger=combo.invalidation_trigger,
            e_context_eligibility_end=interval_end, missing_conditions=combo.missing_conditions,
        )

        if combo.state == EntryModelState.INVALIDATED.value:
            return _decision(**common, state=LargeSMCDecisionState.INVALIDATED.value)
        if combo.state == EntryModelState.EXPIRED.value:
            return _decision(**common, state=LargeSMCDecisionState.EXPIRED.value)
        if combo.state in _WAITING_STATES:
            return _decision(**common, state=LargeSMCDecisionState.WATCH.value)
        if combo.state != EntryModelState.READY.value:
            # NOT_APPLICABLE / NO_VALID_COMBINATION never reach here (composer already
            # excludes them from analysis.combinations) -- defensive fallback only.
            return _decision(**common, state=LargeSMCDecisionState.WATCH.value)

        # READY-equivalent: entry array + retracement available. Fail closed if entry
        # geometry is somehow absent despite READY (never fabricate a price).
        if combo.entry_price is None:
            return _decision(**common, state=LargeSMCDecisionState.BLOCKED.value,
                              reason_codes=("ENTRY_GEOMETRY_ABSENT",))

        try:
            target = self._select_target(symbol, combo.direction, combo.entry_price)
        except MarketDataError as exc:
            return _decision(**common, state=LargeSMCDecisionState.DATA_ERROR.value,
                              reason_codes=(REASON_INSUFFICIENT_DATA, exc.reason_code), data_quality_state="DATA_ERROR")
        if not target.found:
            return _decision(**common, state=LargeSMCDecisionState.NO_TRADE.value,
                              reason_codes=(REASON_REJECT_NO_TARGET,))

        # Target resolved; broker stop and pending-entry expiry remain unsigned (owner
        # decision: block outcome simulation rather than guess). BLOCKED, not
        # RESEARCH_QUALIFIED -- this candidate is exactly the kind Phase B's discovery
        # report counts as "READY-equivalent, blocked pending owner decision."
        return _decision(
            **common, state=LargeSMCDecisionState.BLOCKED.value,
            reason_codes=(REASON_UNSIGNED_C10_BROKER_STOP, REASON_UNSIGNED_PENDING_ENTRY_EXPIRY),
            target_price=target.target_price, target_tier=target.target_tier, target_type=target.target_type,
            target_source=target.target_source, target_source_id=target.target_source_id,
            target_side=target.target_side, target_status_at_selection=target.target_status_at_selection,
            target_selected_at=evaluation_time,
            target_anchor_price=combo.entry_price, target_evidence_timestamp=target.target_evidence_timestamp,
        )

    def _select_target(self, symbol: str, direction: Optional[str], anchor_price: float):
        m5_candles = stage2.get_latest_candles(symbol, _M5_TIMEFRAME, _M5_CANDLE_COUNT)
        live_bid = live_ask = None
        try:
            tick = stage2.get_tick(symbol)
            live_bid, live_ask = tick.bid, tick.ask
        except MarketDataError:
            pass
        tiers = analyze_structure_tiers(symbol, _M5_TIMEFRAME)
        external_tier = tiers.external if tiers.status == "VALID" else None
        return select_target(direction, anchor_price, symbol, _M5_TIMEFRAME, external_tier, m5_candles, live_bid, live_ask)
