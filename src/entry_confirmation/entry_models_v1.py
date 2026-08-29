"""SMC_CONDITIONAL_ENTRY_V2 -- supersedes the initial SMC_ENTRY_MODELS_V1 hard-wired
pairing (E1->M1, E2->M2, E3->M3 only). The corrected model:

    ANY qualified E-condition + ANY qualified M-maneuver + DIRECTION ALIGNMENT
    = a valid SMC entry candidate

    3 entry contexts (E1/E2/E3) x 3 confirmation maneuvers (M1/M2/M3)
    = 9 possible combinations (E1M1..E3M3)

Canonical mapping (unchanged from V1 -- only the pairing rule changed, not what each
letter means):

    E1 = PRICE_FILL_AND_REACT_D1_GAP       M1 = CHARACTER_CHANGE_WITH_INDUCEMENT
    E2 = PRICE_REACT_H1_POI                M2 = SUPPLY_DEMAND_SHIFT
    E3 = PRICE_SWEEP_HTF_LIQUIDITY         M3 = SWEEP_DROP_PUMP

Four conceptual layers (spec section 1) -- never collapsed into one boolean:

    LAYER 1 REFERENCE     -- where should price become interesting? (E's own timeframe)
    LAYER 2 CHECK         -- did price react correctly at that HTF reference? (H1, always)
    LAYER 3 CONFIRMATION  -- how did M5 confirm the directional opportunity? (M1/M2/M3)
    LAYER 4 ENTRY         -- where does the execution array actually exist? (M1/M2/M3)

E1/E2/E3 (e1_daily_gap_reaction.py / e2_h1_poi_reaction.py / e3_liquidity_sweep.py) own
layers 1-2 only and produce a generic `EConditionResult` (this module) -- no M-specific
logic lives there. M1/M2/M3 (m1_character_change_inducement.py /
m2_supply_demand_shift.py / m3_sweep_drop_pump.py) consume ANY `EConditionResult` (not a
specific E1Result/E2Result/E3Result -- that hard-wiring is exactly what this pass
removes) plus their own M5/liquidity/zone evidence, and own layers 3-4. `composer.py`
cross-joins qualified E's with confirmed M's, filtered by direction alignment, into
`SMCEntryCombinationResult` -- see its own module docstring.

Each E1Result/E2Result/E3Result (still typed, evidence-rich, unchanged in shape from
V1) additionally converts to the generic envelope via `e1_to_econdition`/
`e2_to_econdition`/`e3_to_econdition` in its own module -- the detailed dataclass is not
replaced, only ALSO exposed generically so M1/M2/M3 no longer need to import it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple

SMC_CONDITIONAL_ENTRY_V2 = "SMC_CONDITIONAL_ENTRY_V2"
SMC_ENTRY_MODELS_V1 = "SMC_ENTRY_MODELS_V1"  # prior, superseded hard-wired-pair contract; kept for provenance only

ENTRY_CONDITIONS: Tuple[str, ...] = ("E1", "E2", "E3")
MANEUVERS: Tuple[str, ...] = ("M1", "M2", "M3")
COMBINATIONS: Tuple[str, ...] = tuple(f"{e}{m}" for e in ENTRY_CONDITIONS for m in MANEUVERS)

# Canonical timeframe responsibility (spec section 2/23). E3's reference_timeframe is
# intentionally NOT fixed here -- it may be H1/H4/D1 depending on which liquidity level
# qualified; check_timeframe is always H1 for all three.
CHECK_TIMEFRAME = "H1"
CONFIRMATION_TIMEFRAME = "M5"
EXECUTION_TIMEFRAME = "M5"
REFERENCE_TIMEFRAME_E1 = "D1"
REFERENCE_TIMEFRAME_E2 = "H1"

# H1_REACTION_V1 (frozen semantics, audit pass) -- the ONLY thing this package currently
# means by "did price react at the HTF reference" is:
#
#     QUALIFYING_DIRECTIONAL_DISPLACEMENT_REACTION
#     = a caller-supplied reaction candle, strictly after the reference was touched,
#       that passes AG_ENTRY_DISPLACEMENT_V1 (displacement.py) in the candidate direction
#
# Concretely: E1 (`gap.py::evaluate_gap_context`'s GAP_REACTED) and E2
# (`e2_h1_poi_reaction.py::_first_reacting_candle`) both gate their "reaction" status on
# exactly this one test, reused verbatim -- no separate reaction detector exists.
#
# WHAT COUNTS:      one displacement-qualifying candle after the touch, same direction.
# WHAT DOES NOT (NOT implemented, would be a different, unsigned primitive -- do not
#                claim these are supported unless a future pass explicitly adds them):
#     - wick-only rejection (no qualifying-candle displacement check exists for this)
#     - two-candle reclaim patterns
#     - deceleration (momentum slowdown without a qualifying displacement candle)
#     - failed acceptance without displacement (e.g. repeated small-range rejection)
#     - multi-candle reversal patterns (head-and-shoulders, three-drive, etc.)
# WHY THIS IS USED: AG_ENTRY_DISPLACEMENT_V1 is the only owner-signed generic candle
# qualification rule in this package (displacement.py); `rejection.py`'s wick-dominance
# measurement exists but its qualification threshold is UNSIGNED_RULE (see
# docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md) -- reusing it here would fabricate a
# threshold, so it is deliberately not used for H1_REACTION_V1.
H1_REACTION_V1 = "QUALIFYING_DIRECTIONAL_DISPLACEMENT_REACTION"


class EntryModelState(str, Enum):
    """Common lifecycle (spec section 20). Never reduced to True/False -- a caller
    always knows what is missing."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    SCANNING_CONTEXT = "SCANNING_CONTEXT"
    WAITING_HTF_TOUCH = "WAITING_HTF_TOUCH"
    WAITING_H1_REACTION = "WAITING_H1_REACTION"
    HTF_QUALIFIED = "HTF_QUALIFIED"
    WAITING_M5_CONFIRMATION = "WAITING_M5_CONFIRMATION"
    WAITING_M5_ENTRY = "WAITING_M5_ENTRY"
    READY = "READY"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_VALID_COMBINATION = "NO_VALID_COMBINATION"  # E and M both active but direction mismatched


@dataclass(frozen=True)
class EConditionResult:
    """Generic E-condition envelope (spec section 3) -- the normalized shape every
    E1/E2/E3 evaluator converts its detailed *Result into, so M1/M2/M3 and the composer
    can consume ANY qualified E-condition without importing a specific E1Result/
    E2Result/E3Result type. `entry_condition` names which E produced this (E1/E2/E3);
    model-specific evidence (the actual gap/POI/liquidity-level object) stays in the
    source *Result's own `evidence` dict, copied here verbatim, not re-typed."""

    version: str = SMC_CONDITIONAL_ENTRY_V2
    entry_condition: str = ""  # "E1" / "E2" / "E3"
    symbol: str = ""
    direction: Optional[str] = None  # "LONG" / "SHORT" / None

    reference_timeframe: Optional[str] = None
    check_timeframe: Optional[str] = None

    reference_type: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    reference_level: Optional[float] = None

    touch_status: str = EntryModelState.WAITING_HTF_TOUCH.value
    reaction_status: str = EntryModelState.WAITING_H1_REACTION.value
    invalidation_status: Optional[str] = None

    eligible_for_confirmation: bool = False

    evidence: Dict[str, Any] = field(default_factory=dict)
    missing_conditions: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SMCEntryCombinationResult:
    """Composer output (spec section 19) -- one per (E, M) pair that passed the
    composer's gating (E eligible, M engaged, directions aligned). See composer.py."""

    version: str = SMC_CONDITIONAL_ENTRY_V2
    combination: str = ""  # "E1M1".."E3M3"
    entry_condition: str = ""  # "E1" / "E2" / "E3"
    maneuver: str = ""  # "M1" / "M2" / "M3"

    symbol: str = ""
    direction: Optional[str] = None

    reference_timeframe: Optional[str] = None
    check_timeframe: Optional[str] = None
    confirmation_timeframe: str = CONFIRMATION_TIMEFRAME
    execution_timeframe: str = EXECUTION_TIMEFRAME

    e_condition_state: Optional[str] = None
    m_confirmation_state: str = EntryModelState.NOT_APPLICABLE.value

    entry_array: Optional[str] = None
    entry_price: Optional[float] = None
    invalidation: Optional[str] = None

    state: str = EntryModelState.NOT_APPLICABLE.value

    evidence: Dict[str, Any] = field(default_factory=dict)
    missing_conditions: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SMCConditionalEntryAnalysis:
    """Top-level live/historical analysis result (spec section 17) -- one snapshot's
    worth of E1/E2/E3 + M1/M2/M3 + composed combinations for one symbol at one
    evaluation time. Analysis only: `selected_combination` is always None in this
    package -- no priority/ranking/selection layer exists here (spec section 11/22),
    deliberately, so this field exists purely as a fail-safe placeholder for a future
    policy/router pass to populate, never fabricated by this contract.

    Never a trade decision, never an order_send call -- see package docstring."""

    version: str = SMC_CONDITIONAL_ENTRY_V2
    symbol: str = ""
    snapshot_time: Optional[datetime] = None

    reference_timeframes: Dict[str, Optional[str]] = field(default_factory=dict)  # {"E1": "D1", "E2": "H1", "E3": ...}
    check_timeframe: str = CHECK_TIMEFRAME
    confirmation_timeframe: str = CONFIRMATION_TIMEFRAME
    execution_timeframe: str = EXECUTION_TIMEFRAME

    e_conditions: Dict[str, EConditionResult] = field(default_factory=dict)  # keyed "E1"/"E2"/"E3"
    m_maneuvers: Dict[str, Any] = field(default_factory=dict)  # keyed "M1"/"M2"/"M3" -- M1Result/M2Result/M3Result

    combinations: Tuple[SMCEntryCombinationResult, ...] = field(default_factory=tuple)
    selected_combination: Optional[str] = None  # always None -- no selection/ranking layer exists

    data_quality: str = "OK"  # "OK" / "PARTIAL" / "UNAVAILABLE"
    missing_data: Tuple[str, ...] = field(default_factory=tuple)
    warnings: Tuple[str, ...] = field(default_factory=tuple)
