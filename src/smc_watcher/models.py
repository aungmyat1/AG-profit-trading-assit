"""Generic SMC condition/alert shapes (spec sections 15/17/19/25). One shared
SMCConditionResult shape for E1/E2/E3 -- condition-specific facts live in `evidence`
(a plain dict of already-computed values, never re-derived here) rather than three
separate dataclasses, since the alert-level concerns (state, trigger, dedup identity,
reason codes) are identical across all three conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

CONDITION_E1 = "E1"
CONDITION_E2 = "E2"
CONDITION_E3 = "E3"

CONDITION_TYPE_DAILY_GAP_REACTION = "DAILY_GAP_FILL_REACTION"
CONDITION_TYPE_H1_POI_REACTION = "H1_POI_REACTION"
CONDITION_TYPE_LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"

STATE_WATCHING = "WATCHING"
STATE_INDETERMINATE = "INDETERMINATE"
STATE_INVALIDATED = "INVALIDATED"
# E1-specific
STATE_TOUCHED = "TOUCHED"
STATE_FILLED = "FILLED"
STATE_REACTED = "REACTED"
# E2-specific
STATE_POI_TOUCHED = "POI_TOUCHED"
# E3-specific
STATE_SWEPT = "SWEPT"
STATE_RECLAIMED = "RECLAIMED"

ALERT_STATE_WATCHING_HTF_CONDITION = "WATCHING_HTF_CONDITION"
ALERT_STATE_CONDITION_DETECTED = "CONDITION_DETECTED"
ALERT_STATE_ALERTED = "ALERTED"
ALERT_STATE_WAITING_M5_CONFIRMATION = "WAITING_M5_CONFIRMATION"
ALERT_STATE_CONFIRMED = "CONFIRMED"
ALERT_STATE_NOT_CONFIRMED = "NOT_CONFIRMED"
ALERT_STATE_EXPIRED = "EXPIRED"
ALERT_STATE_INVALIDATED = "INVALIDATED"

ALERT_STATE_VALUES = (
    ALERT_STATE_WATCHING_HTF_CONDITION,
    ALERT_STATE_CONDITION_DETECTED,
    ALERT_STATE_ALERTED,
    ALERT_STATE_WAITING_M5_CONFIRMATION,
    ALERT_STATE_CONFIRMED,
    ALERT_STATE_NOT_CONFIRMED,
    ALERT_STATE_EXPIRED,
    ALERT_STATE_INVALIDATED,
)


@dataclass(frozen=True)
class SMCConditionResult:
    condition_id: str  # E1 / E2 / E3
    condition_type: str
    state: str
    triggered: bool = False
    directional_implication: Optional[str] = None  # "LONG" / "SHORT" / None
    source_key: Optional[str] = None  # dedup identity fragment -- e.g. gap origin time, POI id, sweep level+time
    evidence: Dict[str, Any] = field(default_factory=dict)
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SMCConditionAlert:
    alert_id: str
    strategy_id: str
    symbol: str

    triggered_conditions: Tuple[str, ...]
    primary_condition: str
    direction: Optional[str]

    e1_result: Optional[SMCConditionResult]
    e2_result: Optional[SMCConditionResult]
    e3_result: Optional[SMCConditionResult]

    current_price: Optional[float]
    triggered_at: Optional[datetime]

    next_stage: str = "M5_CONFIRMATION"
    alert_state: str = ALERT_STATE_ALERTED
    confirmation_state: str = "PENDING"
    execution_eligible: bool = False

    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
