"""DAYTRADING_BASIC_SKILLS_V1 shapes -- Narrative Bias, Liquidity Affinity, LTF
Execution, Risk Management. A sibling TECHNIQUE to SMC_BASIC_SKILLS_V1
(market_structure/supply_demand/liquidity/entry_confirmation/trade_management), never a
layer inside or above it -- see PROJECT_STATUS.md 'Two-technique model'.

Every DayTrading skill here INTERPRETS evidence produced by SMC/shared capabilities
(market_structure, liquidity, entry_confirmation, trade_management); none of them
re-detects structure, liquidity, or confirmation. See each module's docstring for which
shared capability it consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from entry_confirmation.models import EntryConfirmationResult
    from entry_confirmation.models_v2_1 import SMCSweepShiftArrayResult
    from liquidity.models import LiquidityLevel
    from trade_management.models import TradeManagementResult

TECHNIQUE_SMC = "SMC"
TECHNIQUE_DAYTRADING = "DAYTRADING"
TECHNIQUES: Tuple[str, ...] = (TECHNIQUE_SMC, TECHNIQUE_DAYTRADING)

# --- Narrative Bias states (spec section 4) ---
BIAS_BULLISH = "BULLISH"
BIAS_BEARISH = "BEARISH"
BIAS_BALANCED = "BALANCED"
BIAS_TRANSITION = "TRANSITION"
BIAS_UNRESOLVED = "UNRESOLVED"
_DIRECTIONAL_BIAS = (BIAS_BULLISH, BIAS_BEARISH)

# --- DAYTRADING_NARRATIVE_BIAS_V1 profiles (frozen contract, "what kind of day is this") ---
PROFILE_BULLISH_DAY = "BULLISH_DAY"
PROFILE_BEARISH_DAY = "BEARISH_DAY"
PROFILE_BULLISH_REVERSAL_DAY = "BULLISH_REVERSAL_DAY"
PROFILE_BEARISH_REVERSAL_DAY = "BEARISH_REVERSAL_DAY"
PROFILE_CONSOLIDATION_DAY = "CONSOLIDATION_DAY"
PROFILE_UNRESOLVED = "UNRESOLVED"
NARRATIVE_PROFILES: Tuple[str, ...] = (
    PROFILE_BULLISH_DAY, PROFILE_BEARISH_DAY, PROFILE_BULLISH_REVERSAL_DAY,
    PROFILE_BEARISH_REVERSAL_DAY, PROFILE_CONSOLIDATION_DAY, PROFILE_UNRESOLVED,
)
PROFILE_TO_BIAS = {
    PROFILE_BULLISH_DAY: BIAS_BULLISH,
    PROFILE_BULLISH_REVERSAL_DAY: BIAS_BULLISH,
    PROFILE_BEARISH_DAY: BIAS_BEARISH,
    PROFILE_BEARISH_REVERSAL_DAY: BIAS_BEARISH,
    PROFILE_CONSOLIDATION_DAY: BIAS_BALANCED,
    PROFILE_UNRESOLVED: BIAS_UNRESOLVED,
}

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"
DIRECTION_NONE = "NONE"
DIRECTION_UNRESOLVED = "UNRESOLVED"

DELIVERY_UP = "UP"
DELIVERY_DOWN = "DOWN"
DELIVERY_BALANCED = "BALANCED"
DELIVERY_UNRESOLVED = "UNRESOLVED"

# --- Narrative Bias per-evidence and overall status vocabulary (spec sections 23/26) ---
EVIDENCE_SUPPORTS = "SUPPORTS"
EVIDENCE_CONFLICTS = "CONFLICTS"
EVIDENCE_NEUTRAL = "NEUTRAL"
EVIDENCE_INSUFFICIENT = "INSUFFICIENT"

NARRATIVE_STATUS_SUPPORTED = "SUPPORTED"
NARRATIVE_STATUS_CONFLICTED = "CONFLICTED"
NARRATIVE_STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NARRATIVE_STATUS_UNRESOLVED = "UNRESOLVED"

# Explicitly unresolved policy markers (spec section 22) -- surfaced in `reason`, never
# silently papered over with an invented numerical rule.
REVERSAL_CLASSIFICATION_POLICY_PARTIAL = (
    "REVERSAL_CLASSIFICATION_POLICY=PARTIAL -- reversal evidence limited to an H1 "
    "CHoCH matching the reversal direction inside the true day; no full deterministic "
    "reversal algorithm is frozen yet."
)

# --- Liquidity Affinity states (spec section 5, extended by DAYTRADING_LIQUIDITY_AFFINITY_V1 section 27) ---
AFFINITY_RESOLVED = "RESOLVED"
AFFINITY_PARTIAL = "PARTIAL"
AFFINITY_CONFLICTED = "CONFLICTED"
AFFINITY_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
AFFINITY_UNRESOLVED = "UNRESOLVED"

# --- DAYTRADING_LIQUIDITY_AFFINITY_V1 market_phase (spec section 10) ---
PHASE_IMPULSIVE = "IMPULSIVE"
PHASE_CORRECTIVE = "CORRECTIVE"
PHASE_BALANCED = "BALANCED"
PHASE_UNRESOLVED = "UNRESOLVED"

# --- External/Internal relationship phase (spec section 8) ---
REL_APPROACHING_EXTERNAL = "APPROACHING_EXTERNAL"
REL_EXTERNAL_SWEPT = "EXTERNAL_SWEPT"
REL_RETURNING_INTERNAL = "RETURNING_INTERNAL"
REL_INTERNAL_REBALANCE = "INTERNAL_REBALANCE"
REL_EXPANDING_EXTERNAL = "EXPANDING_EXTERNAL"
REL_BALANCED = "BALANCED"
REL_UNRESOLVED = "UNRESOLVED"

# --- Engineered Terminal Liquidity (spec section 16/4) -- conservative, no curve-fitting ---
TERMINAL_NONE = "NONE"
TERMINAL_BUY_SIDE = "BUY_SIDE_TERMINAL"
TERMINAL_SELL_SIDE = "SELL_SIDE_TERMINAL"
TERMINAL_UNRESOLVED = "UNRESOLVED"
TERMINAL_POLICY_UNRESOLVED = (
    "ENGINEERED_TERMINAL_LIQUIDITY POLICY_UNRESOLVED -- no deterministic curve/shape "
    "definition is frozen in this repository; the presenter-reference screenshots "
    "(spec section 43) are not reverse-engineered into a numeric rule (spec section 44)."
)

# --- Liquidity role hierarchy (spec section 22) ---
ROLE_EXTERNAL_TARGET = "EXTERNAL_TARGET"
ROLE_INTERNAL_REBALANCE = "INTERNAL_REBALANCE"
ROLE_SESSION_CONTEXT = "SESSION_CONTEXT"
ROLE_ENTRY_SIDE = "ENTRY_SIDE"
ROLE_TARGET_SIDE = "TARGET_SIDE"
ROLE_CONSUMED = "CONSUMED"
ROLE_UNRESOLVED = "UNRESOLVED"

SESSION_CONTEXT_RELEVANT = "RELEVANT"
SESSION_CONTEXT_DETECTED = "DETECTED"
SESSION_CONTEXT_NOT_AVAILABLE = "NOT_AVAILABLE"

# --- LTF Execution states (spec section 6) ---
LTF_DORMANT = "DORMANT"
LTF_WAITING = "WAITING"
LTF_CONFIRMED = "CONFIRMED"
LTF_NOT_CONFIRMED = "NOT_CONFIRMED"
LTF_INVALIDATED = "INVALIDATED"
LTF_INDETERMINATE = "INDETERMINATE"

# --- DAYTRADING_LTF_EXECUTION_V1 execution model family (spec section 9/10) --
# classifications, never seven independent strategies.
EXEC_MODEL_CLEAN_SWEEP = "CLEAN_SWEEP"
EXEC_MODEL_SPREAD_SWEEP = "SPREAD_SWEEP"
EXEC_MODEL_SWEEP_AND_FAIL = "SWEEP_AND_FAIL"
EXEC_MODEL_SWEEP_AND_INDUCEMENT = "SWEEP_AND_INDUCEMENT"
EXEC_MODEL_LIQUIDITY_GRAB = "LIQUIDITY_GRAB"
EXEC_MODEL_INVERTED_GAP = "INVERTED_GAP"
EXEC_MODEL_GAP_LIQUIDITY_RESPECT = "GAP_LIQUIDITY_RESPECT"
EXEC_MODEL_NONE = "NONE"
EXEC_MODEL_UNRESOLVED = "UNRESOLVED"
EXEC_MODEL_MULTIPLE = "MULTIPLE_MODELS"

# --- execution_status vocabulary (spec section 29) ---
EXEC_STATUS_DORMANT = "DORMANT"
EXEC_STATUS_WAITING_CONTEXT = "WAITING_CONTEXT"
EXEC_STATUS_WAITING_SWEEP = "WAITING_SWEEP"
EXEC_STATUS_SWEEP_DETECTED = "SWEEP_DETECTED"
EXEC_STATUS_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
EXEC_STATUS_WAITING_CANDLE_CLOSE = "WAITING_CANDLE_CLOSE"
EXEC_STATUS_MODEL_CONFIRMED = "MODEL_CONFIRMED"
EXEC_STATUS_WAITING_ENTRY_PRICE = "WAITING_ENTRY_PRICE"
EXEC_STATUS_ENTRY_AVAILABLE = "ENTRY_AVAILABLE"
EXEC_STATUS_INVALIDATED = "INVALIDATED"
EXEC_STATUS_NOT_CONFIRMED = "NOT_CONFIRMED"
EXEC_STATUS_INDETERMINATE = "INDETERMINATE"

# --- entry_method vocabulary (execution geometry only, never risk/broker -- spec section 38) ---
ENTRY_METHOD_FIFTY_PERCENT_BODY = "FIFTY_PERCENT_BODY"
ENTRY_METHOD_FIFTY_PERCENT_GAP = "FIFTY_PERCENT_GAP"
ENTRY_METHOD_NONE = "NONE"

# --- undefined-policy markers (spec sections 8/12/13/20/24/76) -- surfaced verbatim in
# ExecutionModelAssessment.unresolved_policy / LTFExecutionResult.reason, never silently
# resolved with an invented numeric rule. ---
PROTECTED_SWEEP_LEVEL_POLICY_PARTIAL = (
    "PROTECTED_SWEEP_LEVEL_POLICY=PARTIAL -- no protected_high/protected_low supplied "
    "(reuses market_structure.tiers EXTERNAL swing high/low; no arbitrary fractal length "
    "is invented to substitute for it)."
)
OPEN_LEVEL_TOLERANCE_POLICY_UNRESOLVED = (
    "OPEN_LEVEL_TOLERANCE_POLICY=UNRESOLVED -- 'must open at the same level' has no "
    "broker-aware numeric tolerance frozen in this repository; OPEN_LEVEL_ALIGNMENT is "
    "reported structurally (DETECTED/NOT_DETECTED/UNRESOLVED) from the existing FVG "
    "detector only, never a guessed pip tolerance."
)
SPREAD_SWEEP_POLICY_PARTIAL = (
    "SPREAD_SWEEP_POLICY=PARTIAL -- presenter material distinguishes Spread Sweep from "
    "Clean Sweep only by candle-spread appearance; no deterministic numeric rule is "
    "frozen, so this model never auto-confirms."
)
STOP_BREADTH_POLICY_UNRESOLVED = (
    "STOP_BREADTH_POLICY=UNRESOLVED -- 'SL + breadth behind the aggressive move' names no "
    "numeric buffer; structural_invalidation_reference marks the aggressive-move anchor "
    "only, the breadth itself is left to Risk Management/a future frozen rule."
)
INVERTED_GAP_POLICY_PARTIAL = (
    "INVERTED_GAP_POLICY=PARTIAL -- gap inversion is evidenced only via the existing FVG "
    "ZoneStatus (MITIGATED/INVALIDATED); no deterministic close-through-percentage or "
    "polarity-inversion rule is frozen, so this model never auto-confirms."
)
AGGRESSIVE_MOVE_POLICY_PARTIAL = (
    "AGGRESSIVE_MOVE_POLICY=PARTIAL -- no ATR/body-multiple aggressive-move threshold is "
    "frozen for DayTrading LTF Execution; displacement evidence is reused from "
    "entry_confirmation.displacement where supplied, otherwise this remains PARTIAL."
)

# --- Risk Management states (spec section 7) ---
RISK_PASS = "PASS"
RISK_FAIL = "FAIL"
RISK_UNRESOLVED = "UNRESOLVED"

# --- Pipeline / TRADE_STATE (spec section 20) ---
STATE_WAIT_NARRATIVE = "WAIT_NARRATIVE"
STATE_WAIT_AFFINITY = "WAIT_AFFINITY"
STATE_WAIT_LTF_EXECUTION = "WAIT_LTF_EXECUTION"
STATE_WAIT_RISK = "WAIT_RISK"
STATE_TRADE_READY_LONG = "TRADE_READY_LONG"
STATE_TRADE_READY_SHORT = "TRADE_READY_SHORT"
STATE_NO_TRADE = "NO_TRADE"
STATE_INVALIDATED = "INVALIDATED"

# Timeframe responsibility model (spec section 9) -- V1 depends on exactly these three.
TIMEFRAME_COMPASS = "D1"
TIMEFRAME_INTEREST = "H1"
TIMEFRAME_TRADE = "M5"


@dataclass(frozen=True)
class NarrativeBiasResult:
    symbol: str
    reference_timeframe: str
    bias: str = BIAS_UNRESOLVED  # derived from expected_profile; kept for pipeline/skills-2-4 compatibility
    primary_draw: Optional[str] = None  # "BUY_SIDE" / "SELL_SIDE"
    major_target: Optional[float] = None
    supporting_evidence: Tuple[str, ...] = field(default_factory=tuple)
    contradictory_evidence: Tuple[str, ...] = field(default_factory=tuple)
    invalidation: Optional[float] = None
    status: str = "INSUFFICIENT_DATA"  # "OK" / "INSUFFICIENT_DATA" (legacy vocabulary, preserved)
    reason: Optional[str] = None

    # --- DAYTRADING_NARRATIVE_BIAS_V1 additive fields (spec section 24) ---
    version: str = "DAYTRADING_NARRATIVE_BIAS_V1"
    evaluation_time: Optional[object] = None  # datetime, UTC
    reference_timezone: Optional[str] = None  # "America/New_York"
    trading_date: Optional[str] = None
    true_day_open: Optional[float] = None

    initial_delivery: str = DELIVERY_UNRESOLVED
    expected_delivery: str = DELIVERY_UNRESOLVED
    preferred_direction: str = DIRECTION_UNRESOLVED

    expected_profile: str = PROFILE_UNRESOLVED
    realized_profile: Optional[str] = None  # only ever set by evaluate_realized_narrative_bias()

    price_location: Optional[str] = None  # "PREMIUM" / "DISCOUNT" / "EQUILIBRIUM" / None
    inefficiency_above: Optional[float] = None
    inefficiency_below: Optional[float] = None

    structure_evidence: str = EVIDENCE_INSUFFICIENT
    liquidity_evidence: str = EVIDENCE_INSUFFICIENT
    premium_discount_evidence: str = EVIDENCE_INSUFFICIENT
    inefficiency_evidence: str = EVIDENCE_INSUFFICIENT

    narrative_status: str = NARRATIVE_STATUS_UNRESOLVED  # SUPPORTED / CONFLICTED / INSUFFICIENT_DATA / UNRESOLVED


@dataclass(frozen=True)
class SessionLiquidityContext:
    """Spec sections 17-21: session liquidity is contextual evidence, never itself an
    entry rule. Built entirely from already-detected SMC liquidity levels (ASIAN_HIGH/
    LOW etc., liquidity/analyzer.py) and an H1 structure read -- no new session engine."""

    session: Optional[str] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    swept_side: Optional[str] = None  # "BUY_SIDE" / "SELL_SIDE" / None
    h1_structure_direction: Optional[str] = None
    sweep_opposes_h1_structure: Optional[bool] = None
    external_gap_context: Optional[bool] = None   # None = NOT_EVALUATED (caller didn't supply gap evidence)
    external_ob_context: Optional[bool] = None    # None = NOT_EVALUATED (caller didn't supply OB evidence)
    session_ob_reaction: Optional[bool] = None    # None = NOT_EVALUATED
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    status: str = SESSION_CONTEXT_NOT_AVAILABLE


@dataclass(frozen=True)
class DayTradingLiquidityAffinityResult:
    """DAYTRADING_LIQUIDITY_AFFINITY_V1 -- distinct from liquidity.affinity's external/
    internal SMC relationship (spec section 14/2): that module DETECTS/relates SMC
    liquidity+imbalance objects; this one INTERPRETS the day-trading relevance of
    already-detected liquidity for the current NarrativeBiasResult. Never redetects a
    liquidity level, FVG, OB, or session box -- see liquidity_affinity.py's docstring for
    exactly which shared capability backs each field below.

    Legacy fields (symbol/narrative_bias/primary_draw/entry_side_liquidity/
    target_side_liquidity/relevant_levels/evidence/status/reason) are the original V0
    shape and remain load-bearing for ltf_execution.py/pipeline.py; every field below
    `version` is additive, populated only when the richer optional evidence is supplied."""

    symbol: str
    narrative_bias: str
    primary_draw: Optional[str] = None          # "BUY_SIDE" / "SELL_SIDE"
    entry_side_liquidity: Optional[str] = None   # "BUY_SIDE" / "SELL_SIDE"
    target_side_liquidity: Optional[str] = None  # "BUY_SIDE" / "SELL_SIDE"
    relevant_levels: Tuple["LiquidityLevel", ...] = field(default_factory=tuple)
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    status: str = AFFINITY_UNRESOLVED
    reason: Optional[str] = None

    # --- DAYTRADING_LIQUIDITY_AFFINITY_V1 additive fields (spec section 25) ---
    version: str = "DAYTRADING_LIQUIDITY_AFFINITY_V1"
    evaluation_time: Optional[object] = None  # datetime, UTC
    reference_timeframe: str = TIMEFRAME_INTEREST

    external_liquidity: Tuple[str, ...] = field(default_factory=tuple)   # e.g. "EXTERNAL_BUY_SIDE@1.1900:UNSWEPT"
    internal_liquidity: Tuple[str, ...] = field(default_factory=tuple)   # e.g. "INTERNAL_FVG@1.1690-1.1700:UNCONSUMED"
    session_liquidity: Optional[SessionLiquidityContext] = None

    consumed_liquidity: Tuple[str, ...] = field(default_factory=tuple)
    remaining_liquidity: Tuple[str, ...] = field(default_factory=tuple)

    primary_target_id: Optional[str] = None
    primary_target_price: Optional[float] = None
    primary_target_type: Optional[str] = None
    primary_target_timeframe: Optional[str] = None
    primary_target_reason: Optional[str] = None

    internal_rebalance_target: Optional[str] = None
    external_internal_relationship: Optional[str] = None  # REL_* vocabulary
    market_phase: str = PHASE_UNRESOLVED

    structure_context: Optional[str] = None
    premium_discount_context: Optional[str] = None

    terminal_liquidity_pattern: str = TERMINAL_UNRESOLVED
    terminal_liquidity_policy: str = TERMINAL_POLICY_UNRESOLVED

    affinity_direction: Optional[str] = None  # BUY_SIDE / SELL_SIDE / INTERNAL / BALANCED / UNRESOLVED
    contradictions: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecutionModelAssessment:
    """A single execution-model classification result (spec section 72). Internal
    building block consumed by LTFExecutionResult.execution_model/model_assessments --
    never itself account risk, broker volume, or a final order."""

    model_type: str = EXEC_MODEL_UNRESOLVED
    direction: Optional[str] = None  # "LONG" / "SHORT"
    protected_level: Optional[float] = None
    sweep_side: Optional[str] = None  # "BUY_SIDE" / "SELL_SIDE"
    sweep_count: int = 0
    wick_body_ratio: Optional[float] = None
    gap_low: Optional[float] = None
    gap_high: Optional[float] = None
    gap_status: Optional[str] = None
    entry_method: str = ENTRY_METHOD_NONE
    entry_reference_price: Optional[float] = None
    structural_invalidation_reference: Optional[float] = None
    confirmation_candle_closed: Optional[bool] = None
    confirmation_candle_time: Optional[object] = None  # datetime, UTC -- the candle that produced MODEL_CONFIRMED
    confirmation_candle_close: Optional[float] = None
    status: str = EXEC_STATUS_INDETERMINATE
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_policy: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class LTFExecutionResult:
    symbol: str
    execution_timeframe: str
    direction: Optional[str] = None  # "LONG" / "SHORT"
    context_valid: bool = False
    liquidity_event: Optional[str] = None
    structure_shift: Optional[str] = None
    displacement: Optional[str] = None
    confirmation_result: Optional["EntryConfirmationResult"] = None
    entry_reference: Optional[float] = None
    invalidation_reference: Optional[float] = None
    status: str = LTF_DORMANT
    reason: Optional[str] = None

    # --- DAYTRADING_LTF_EXECUTION_V1 additive fields (spec sections 7/30) -- never
    # populated with account risk, broker volume, or a sent order (spec sections 38/74). ---
    version: str = "DAYTRADING_LTF_EXECUTION_V1"
    h1_structure_direction: Optional[str] = None
    protected_high: Optional[float] = None
    protected_low: Optional[float] = None

    matching_models: Tuple[ExecutionModelAssessment, ...] = field(default_factory=tuple)
    execution_model: str = EXEC_MODEL_NONE
    selected_assessment: Optional[ExecutionModelAssessment] = None

    entry_method: str = ENTRY_METHOD_NONE
    entry_reference_price: Optional[float] = None
    structural_invalidation_reference: Optional[float] = None
    confirmation_candle_time: Optional[object] = None  # datetime, UTC
    confirmation_candle_close: Optional[float] = None

    execution_status: str = EXEC_STATUS_DORMANT
    unresolved_policies: Tuple[str, ...] = field(default_factory=tuple)
    execution_authority_changed: bool = False  # always False -- Skill #3 never sends an order (spec section 74)

    # --- AG_TRADING_ASSISTANT_WORKFLOW_V1 sweep-shift-array corroboration (spec section
    # 16): SMCSweepShiftArrayResult (entry_confirmation.engine_v2_1) evaluated over the
    # SAME H1 pivot/M5 structure-shift evidence, used only as a fail-closed corroborating
    # gate on the v1-based decision above -- never a second independent confirmation
    # engine. None when the caller supplied no sweep_shift_request. ---
    sweep_shift_result: Optional["SMCSweepShiftArrayResult"] = None


@dataclass(frozen=True)
class RiskManagementResult:
    symbol: str
    status: str = RISK_UNRESOLVED
    trade_management: Optional["TradeManagementResult"] = None
    risk_reward: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class DayTradingResult:
    symbol: str
    narrative_bias: NarrativeBiasResult
    liquidity_affinity: Optional[DayTradingLiquidityAffinityResult] = None
    ltf_execution: Optional[LTFExecutionResult] = None
    risk_management: Optional[RiskManagementResult] = None
    trade_state: str = STATE_NO_TRADE
    direction: Optional[str] = None
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    contract_version: str = "DAYTRADING_BASIC_SKILLS_V1"
