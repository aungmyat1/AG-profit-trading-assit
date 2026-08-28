"""Entry 1 (Trend), Entry 2 (Sweep), Entry 3 (Range) candidate-setup detectors.

Every function here only ever looks at candles up to and including the one that produces the
decision -- never later data (see tests/test_session_router.py's lookahead tests). None of this
authorizes broker execution: decision_status VALID means "a candidate setup was found under the
signed rule," not "send an order." See README/ACTIVE_STRATEGY_ARCHITECTURE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, Sequence

from session_clock import CONTRACT_VERSION as CANONICAL_SESSION_VERSION

from .candles import Candle
from .classifier import CLASSIFIER_ID, CLASSIFIER_VERSION, Regime
from .reference_box import ReferenceBox

SETUP_VERSION = "SESSION_ROUTER_SETUPS_V1"


class SetupType(str, Enum):
    TREND = "TREND"
    SWEEP = "SWEEP"
    RANGE = "RANGE"
    NONE = "NONE"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class DecisionStatus(str, Enum):
    VALID = "VALID"
    NO_SETUP = "NO_SETUP"
    AMBIGUOUS = "AMBIGUOUS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SetupDecision:
    strategy_id: str
    symbol: str
    reference_session: str
    session_date: date
    regime: Regime
    setup_type: SetupType
    decision_status: DecisionStatus
    reason_code: str
    direction: Optional[Direction] = None
    signal_timestamp: Optional[datetime] = None
    entry_reference: Optional[float] = None
    stop_reference: Optional[float] = None
    target_reference: Optional[float] = None
    risk_distance: Optional[float] = None
    evidence: dict = field(default_factory=dict)
    contract_status: str = "RESEARCH_CANDIDATE_NOT_EXECUTION_AUTHORITY"
    canonical_session_version: str = CANONICAL_SESSION_VERSION
    classifier_id: str = CLASSIFIER_ID
    classifier_version: str = CLASSIFIER_VERSION
    setup_version: str = SETUP_VERSION


def _no_setup(strategy_id, symbol, session, session_date, regime, reason_code) -> SetupDecision:
    return SetupDecision(
        strategy_id=strategy_id, symbol=symbol, reference_session=session, session_date=session_date,
        regime=regime, setup_type=SetupType.NONE, decision_status=DecisionStatus.NO_SETUP,
        reason_code=reason_code,
    )


# --------------------------------------------------------------------------- Entry 1 -- TREND

def entry_1_trend(strategy_id: str, symbol: str, box: ReferenceBox, session_date: date) -> SetupDecision:
    """Direction = BOX_DIRECTION_V1 (config/session_flow_v2.yaml entry_1_trend: SIGNED_IMPLEMENTED),
    i.e. completed-box first-open vs final-close, not a provisional rule."""
    if box.session_close > box.session_open:
        direction = Direction.LONG
    elif box.session_close < box.session_open:
        direction = Direction.SHORT
    else:
        return _no_setup(strategy_id, symbol, box.session_name, session_date, Regime.TREND,
                          "BOX_DIRECTION_V1_FLAT_NO_TRADE")

    return SetupDecision(
        strategy_id=strategy_id, symbol=symbol, reference_session=box.session_name,
        session_date=session_date, regime=Regime.TREND, setup_type=SetupType.TREND,
        decision_status=DecisionStatus.VALID, reason_code="BOX_DIRECTION_V1",
        direction=direction, signal_timestamp=None,
        entry_reference=box.session_mid, stop_reference=box.session_low if direction == Direction.LONG else box.session_high,
        target_reference=None,
        risk_distance=abs(box.session_mid - (box.session_low if direction == Direction.LONG else box.session_high)),
        evidence={"session_open": box.session_open, "session_close": box.session_close,
                  "session_mid": box.session_mid, "efficiency_ratio": box.efficiency_ratio},
    )


# --------------------------------------------------------------------------- Entry 2 -- SWEEP

def entry_2_sweep(strategy_id: str, symbol: str, box: ReferenceBox, session_date: date,
                   post_session_candles: Sequence[Candle]) -> SetupDecision:
    """Strict penetration (config/session_flow_v2.yaml sweep_classifier: penetration STRICT,
    reclaim_clearance_fraction 0.0), first qualified chronologically. A single candle that
    breaches both sides is SWEEP_DIRECTION_UNRESOLVED -> AMBIGUOUS/NO_TRADE, matching
    same_candle_dual_side in the same contract."""
    for candle in post_session_candles:
        upper_swept = candle.high > box.session_high and candle.close < box.session_high
        lower_swept = candle.low < box.session_low and candle.close > box.session_low

        if upper_swept and lower_swept:
            return SetupDecision(
                strategy_id=strategy_id, symbol=symbol, reference_session=box.session_name,
                session_date=session_date, regime=Regime.RANGE, setup_type=SetupType.SWEEP,
                decision_status=DecisionStatus.AMBIGUOUS, reason_code="AMBIGUOUS_DUAL_SWEEP",
                signal_timestamp=candle.time,
                evidence={"candle_high": candle.high, "candle_low": candle.low, "candle_close": candle.close},
            )

        if upper_swept:
            return SetupDecision(
                strategy_id=strategy_id, symbol=symbol, reference_session=box.session_name,
                session_date=session_date, regime=Regime.RANGE, setup_type=SetupType.SWEEP,
                decision_status=DecisionStatus.VALID, reason_code="UPPER_SWEEP_STRICT_PENETRATION",
                direction=Direction.SHORT, signal_timestamp=candle.time,
                entry_reference=max(candle.open, candle.close), stop_reference=candle.high,
                target_reference=None, risk_distance=candle.high - max(candle.open, candle.close),
                evidence={"session_high": box.session_high, "candle_high": candle.high, "candle_close": candle.close},
            )
        if lower_swept:
            return SetupDecision(
                strategy_id=strategy_id, symbol=symbol, reference_session=box.session_name,
                session_date=session_date, regime=Regime.RANGE, setup_type=SetupType.SWEEP,
                decision_status=DecisionStatus.VALID, reason_code="LOWER_SWEEP_STRICT_PENETRATION",
                direction=Direction.LONG, signal_timestamp=candle.time,
                entry_reference=min(candle.open, candle.close), stop_reference=candle.low,
                target_reference=None, risk_distance=min(candle.open, candle.close) - candle.low,
                evidence={"session_low": box.session_low, "candle_low": candle.low, "candle_close": candle.close},
            )

    return _no_setup(strategy_id, symbol, box.session_name, session_date, Regime.RANGE,
                      "NO_QUALIFIED_SWEEP_IN_WINDOW")


# --------------------------------------------------------------------------- Entry 3 -- RANGE

def entry_3_range(strategy_id: str, symbol: str, box: ReferenceBox, session_date: date,
                   post_session_candles: Sequence[Candle]) -> SetupDecision:
    """Boundary touch + directional close (config/strategy.yaml range_rejection contract);
    direction rule UPPER_BOUNDARY_REJECTION_SHORT_LOWER_BOUNDARY_REJECTION_LONG
    (config/session_flow_v2.yaml entry_3_range, SIGNED). Only reached when Entry 2 found no
    qualified sweep -- may legitimately terminate in NO_SETUP (range_setup.terminal_reason:
    NO_SETUP_BY_WINDOW_END)."""
    for candle in post_session_candles:
        upper_rejection = candle.high >= box.session_high and candle.close < box.session_high and candle.close < candle.open
        lower_rejection = candle.low <= box.session_low and candle.close > box.session_low and candle.close > candle.open

        if upper_rejection:
            return SetupDecision(
                strategy_id=strategy_id, symbol=symbol, reference_session=box.session_name,
                session_date=session_date, regime=Regime.RANGE, setup_type=SetupType.RANGE,
                decision_status=DecisionStatus.VALID, reason_code="UPPER_BOUNDARY_REJECTION",
                direction=Direction.SHORT, signal_timestamp=candle.time,
                entry_reference=box.session_high, stop_reference=candle.high,
                target_reference=box.session_mid, risk_distance=candle.high - box.session_high,
                evidence={"session_high": box.session_high, "candle_high": candle.high, "candle_close": candle.close},
            )
        if lower_rejection:
            return SetupDecision(
                strategy_id=strategy_id, symbol=symbol, reference_session=box.session_name,
                session_date=session_date, regime=Regime.RANGE, setup_type=SetupType.RANGE,
                decision_status=DecisionStatus.VALID, reason_code="LOWER_BOUNDARY_REJECTION",
                direction=Direction.LONG, signal_timestamp=candle.time,
                entry_reference=box.session_low, stop_reference=candle.low,
                target_reference=box.session_mid, risk_distance=box.session_low - candle.low,
                evidence={"session_low": box.session_low, "candle_low": candle.low, "candle_close": candle.close},
            )

    return _no_setup(strategy_id, symbol, box.session_name, session_date, Regime.RANGE,
                      "NO_SETUP_BY_WINDOW_END")
