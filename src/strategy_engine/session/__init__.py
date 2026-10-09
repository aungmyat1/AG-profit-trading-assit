"""Session-box strategy component: build a frozen reference-session box from completed
candles, classify TREND/RANGE, and route to the matching candidate-setup detector.

Status: RESEARCH. Candidate-setup generation only -- not wired to any MT5 gateway or
order-sending path. Formerly the top-level `session_router` package; moved here because
it is one strategy component (the session-box family), not the whole project. See
../../strategies/STRATEGY_LEDGER.md and ../../PROJECT_STATUS.md.
"""
from .candles import Candle
from .reference_box import ReferenceBox, build_reference_box
from .classifier import Regime, classify, CLASSIFIER_ID, CLASSIFIER_VERSION, EFFICIENCY_RATIO_THRESHOLD
from .setups import (
    SetupDecision, SetupType, Direction, DecisionStatus,
    entry_1_trend, entry_2_sweep, entry_3_range,
)
from .router import route_completed_session

__all__ = [
    "Candle", "ReferenceBox", "build_reference_box",
    "Regime", "classify", "CLASSIFIER_ID", "CLASSIFIER_VERSION", "EFFICIENCY_RATIO_THRESHOLD",
    "SetupDecision", "SetupType", "Direction", "DecisionStatus",
    "entry_1_trend", "entry_2_sweep", "entry_3_range",
    "route_completed_session",
]
