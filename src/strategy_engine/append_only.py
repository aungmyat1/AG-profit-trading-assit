"""Append-only session routing for ST_ASIAN_SWEEP_5R_V1 candidate versions that declare it (v1.1.3).

Implements the two corrections declared by strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml and nothing else:

* D-ASW-1 (`min_risk_distance: STRICTLY_POSITIVE`): a candidate with risk_distance <= 0 is never
  emitted -- it is NO_SETUP at decision time instead of a VALID emission caught downstream.
* D-ASW-2 (`signal_stream: APPEND_ONLY`, `cross_branch_precedence: BY_EMISSION_TIME`, owner
  decision 2026-10-13): the post-session window is walked bar by bar; each bar is checked with the
  frozen per-candle detectors (Entry 2 before Entry 3 *within* that bar, as in v1.1.2). The first
  emission is the session's decision and is never rewritten by a later bar; later qualifications are
  appended to the stream (audit only, max_entries_per_session stays 1). signal_id is per qualifying bar.

The frozen modules (engine.py, session/*) are imported, never edited: they are shared with v1.1.1 and
the v1.1.2 candidate and are bound by the registry S1 identity. This module is part of the v1.1.3
identity only (v1_tickets.authority.CANDIDATE_ENGINE_FILES). Does not import MT5, sends no orders.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import List, Optional, Sequence, Tuple

from .engine import evaluate as _frozen_evaluate
from .models import StrategyConfig, TradeSignal
from .session import Candle, DecisionStatus, Regime
from .session.classifier import classify
from .session.reference_box import ReferenceBox, build_reference_box
from .session.setups import (
    SetupDecision,
    SetupType,
    entry_1_trend,
    entry_2_sweep,
    entry_3_range,
)

APPEND_ONLY_VERSIONS = frozenset({("ST_ASIAN_SWEEP_5R_V1", "1.1.3")})
NON_POSITIVE_RISK = "NON_POSITIVE_RISK_DISTANCE"


def uses_append_only(strategy: StrategyConfig) -> bool:
    return (strategy.strategy_id, str(strategy.version)) in APPEND_ONLY_VERSIONS


def _non_positive(decision: SetupDecision) -> bool:
    return (decision.decision_status is DecisionStatus.VALID
            and (decision.risk_distance is None or decision.risk_distance <= 0))


def _rejected(decision: SetupDecision) -> SetupDecision:
    return replace(decision, setup_type=SetupType.NONE, decision_status=DecisionStatus.NO_SETUP,
                   reason_code=NON_POSITIVE_RISK, direction=None, entry_reference=None, stop_reference=None,
                   target_reference=None, risk_distance=None,
                   evidence={**decision.evidence, "rejected_reason_code": decision.reason_code,
                             "rejected_risk_distance": decision.risk_distance})


def emission_stream(strategy_id: str, symbol: str, box: ReferenceBox, regime: Regime, session_date: date,
                    post_session_candles: Sequence[Candle]) -> Tuple[List[SetupDecision], List[SetupDecision]]:
    """(emissions, rejected): emissions in bar order (VALID or AMBIGUOUS, positive risk only);
    rejected = per-bar VALID candidates dropped by D-ASW-1. Causal: bar i depends only on bars <= i."""
    seen = {}
    previous = None
    for candle in post_session_candles:
        if previous is not None and candle.time < previous:
            raise ValueError("post-session candles must be chronological")
        prior = seen.get(candle.time)
        if prior is not None:
            if prior != candle:
                raise ValueError(f"conflicting candles share timestamp {candle.time.isoformat()}")
            raise ValueError(f"duplicate candle timestamp {candle.time.isoformat()}")
        seen[candle.time] = candle
        previous = candle.time
    if regime is Regime.TREND:
        decision = entry_1_trend(strategy_id, symbol, box, session_date)
        if _non_positive(decision):
            return [], [_rejected(decision)]
        return ([decision] if decision.decision_status is DecisionStatus.VALID else []), []
    emissions: List[SetupDecision] = []
    rejected: List[SetupDecision] = []
    for candle in post_session_candles:
        # D-ASW-1 applies at each detection site: a non-positive-risk Entry 2 decision is NO_SETUP,
        # so the bar falls through to Entry 3 exactly as v1.1.2 routes an Entry 2 NO_SETUP.
        emitted = None
        for detect in (entry_2_sweep, entry_3_range):
            candidate = detect(strategy_id, symbol, box, session_date, [candle])
            if candidate.decision_status is DecisionStatus.NO_SETUP:
                continue
            if _non_positive(candidate):
                rejected.append(_rejected(candidate))
                continue
            emitted = candidate
            break
        if emitted is not None:
            emissions.append(emitted)
    return emissions, rejected


def route_append_only(strategy_id: str, symbol: str, session_name: str, session_date: date,
                      session_candles: Sequence[Candle], expected_bar_count: int,
                      post_session_candles: Sequence[Candle] = (), regime_override: Optional[Regime] = None,
                      ) -> Tuple[ReferenceBox, Regime, SetupDecision]:
    """Same inputs/outputs as session.router.route_completed_session; the decision is the first emission."""
    box = build_reference_box(session_name, session_candles, expected_bar_count)
    if not box.session_complete:
        raise ValueError(f"route_append_only requires a completed box: got {box.bar_count}/"
                         f"{expected_bar_count} bars for {session_name} on {session_date}")
    regime = regime_override if regime_override is not None else classify(box)
    emissions, rejected = emission_stream(strategy_id, symbol, box, regime, session_date, post_session_candles)
    if emissions:
        return box, regime, emissions[0]
    if rejected:
        return box, regime, rejected[0]
    if regime is Regime.TREND:
        return box, regime, entry_1_trend(strategy_id, symbol, box, session_date)
    return box, regime, entry_3_range(strategy_id, symbol, box, session_date, ())   # NO_SETUP_BY_WINDOW_END


def evaluate_append_only(strategy: StrategyConfig, pair_id: str, symbol: str, session_date: date,
                         session_candles: Sequence[Candle], expected_bar_count: int,
                         post_session_candles: Sequence[Candle] = (),
                         regime_override: Optional[Regime] = None) -> TradeSignal:
    """strategy_engine.evaluate() contract with append-only routing and a per-bar signal_id."""
    if symbol not in strategy.instruments:
        raise ValueError(f"{symbol!r} is not in {strategy.strategy_id}'s instruments: {strategy.instruments}")
    pair = next((p for p in strategy.session_pairs if p.pair_id == pair_id), None)
    if pair is None:
        raise ValueError(f"unknown pair_id {pair_id!r} for {strategy.strategy_id}")
    box, regime, decision = route_append_only(strategy.strategy_id, symbol, pair.reference_session.name,
                                              session_date, session_candles, expected_bar_count,
                                              post_session_candles, regime_override=regime_override)
    base_id = f"{strategy.strategy_id}:{pair.pair_id}:{symbol}:{session_date.isoformat()}"
    return TradeSignal(
        signal_id=f"{base_id}:{decision.signal_timestamp.isoformat()}" if decision.signal_timestamp else base_id,
        strategy_id=strategy.strategy_id, strategy_version=strategy.version, symbol=symbol,
        pair_id=pair.pair_id, reference_session=pair.reference_session.name, session_date=session_date,
        box_high=box.session_high, box_low=box.session_low, box_mid=box.session_mid,
        regime=regime.value, setup=decision.setup_type.value,
        status="SIGNAL" if decision.decision_status is DecisionStatus.VALID else "NO_TRADE",
        reason_code=decision.reason_code,
        direction=decision.direction.value if decision.direction else None,
        entry=decision.entry_reference, stop_loss=decision.stop_reference,
        risk_distance=decision.risk_distance, signal_timestamp=decision.signal_timestamp,
    )


def evaluate_for(strategy: StrategyConfig, *, frozen_evaluate=None):
    """The evaluate() callable a ticket builder must use for this exact strategy version."""
    return evaluate_append_only if uses_append_only(strategy) else (frozen_evaluate or _frozen_evaluate)
