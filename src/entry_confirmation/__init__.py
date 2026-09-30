"""Entry & Confirmation capability (Phase 5, ENTRY_CONFIRMATION_V1): answers "what
confirmation evidence exists for a proposed direction?" -- never "should I buy or sell?"

Advisory only: this package reports deterministic confirmation facts (displacement and
rejection/reversal candle measurements, structure-shift alignment, liquidity-reclaim
alignment). It has no execution authority, never calls execution/order_check/
order_send, and never decides a trade -- see PROJECT_STATUS.md 'Authority order' and
entry_confirmation/contract.py.

Reuses market_structure.StructureResult and liquidity.LiquidityResult verbatim (never
re-detects swings/BOS/CHoCH/sweeps/reclaims) and never independently fetches market
data -- callers supply an already-fetched Candle and already-computed upstream results.
See engine.py's module docstring for the full data flow and the `overall_state`
aggregation contract.

Where no owner-signed generic threshold exists (displacement/rejection qualification),
this package reports the objective measurement and an explicit
`ConfirmationState.UNSIGNED_RULE` rather than inventing one -- see contract.py's
ENTRY_CONFIRMATION_CONTRACT_GAPS.
"""
from .contract import CONTRACT_VERSION, ENTRY_CONFIRMATION_CONTRACT_GAPS, EntryConfirmationContractGap
from .engine import evaluate_entry_confirmation
from .engine_v2 import EntryConfirmationV2Request, evaluate_entry_confirmation_v2
from .gap import evaluate_gap_context, evaluate_inverted_gap_context, gap_midpoint
from .models_v2 import (
    CONTRACT_VERSION_V2,
    ConfirmationModel,
    ConfirmationRoute,
    DirectionalContext,
    EntryConfirmationV2Result,
    EntryGeometry,
    EntryMethod,
    GapContext,
    InvertedGapContext,
    POIContext,
    RouteResult,
    SpreadContext,
    StructuralInvalidationType,
    TypedEvent,
)
from .poi import evaluate_poi_context
from .route import classify_route, evaluate_e1, evaluate_e2, evaluate_e3
from .spread import evaluate_spread_context
from .engine_v2_1 import (
    SweepShiftArrayRequest,
    determine_setup_family,
    evaluate_continuation_pullback,
    evaluate_reversal_sweep_shift,
    evaluate_sweep_shift_array,
)
from .entry_array import evaluate_entry_array, fvg_associated_with_leg, ob_associated_with_shift
from .models_v2_1 import (
    CONTRACT_VERSION_V2_1,
    ConfluenceRelation,
    DisplacementLeg,
    EntryArrayContext,
    EntryArrayType,
    EntryMethodV21,
    PivotContext,
    PivotRole,
    SetupFamily,
    SMCSweepShiftArrayResult,
    StructureShiftQuality,
    StructureShiftQualityStatus,
)
from .sweep_shift import classify_wick_or_close, evaluate_pivot_context, evaluate_structure_shift_quality
from .entry_models_v1 import (
    CHECK_TIMEFRAME,
    COMBINATIONS,
    CONFIRMATION_TIMEFRAME,
    ENTRY_CONDITIONS,
    EXECUTION_TIMEFRAME,
    H1_REACTION_V1,
    MANEUVERS,
    REFERENCE_TIMEFRAME_E1,
    REFERENCE_TIMEFRAME_E2,
    SMC_CONDITIONAL_ENTRY_V2,
    SMC_ENTRY_MODELS_V1,
    EConditionResult,
    EntryModelState,
    SMCConditionalEntryAnalysis,
    SMCEntryCombinationResult,
)
from .e1_daily_gap_reaction import E1Result, e1_to_econdition, evaluate_e1_daily_gap_reaction
from .m1_character_change_inducement import M1Result, evaluate_m1_character_change_with_inducement
from .e2_h1_poi_reaction import E2PoiReactionRequest, E2Result, e2_to_econdition, evaluate_e2_h1_poi_reaction
from .m2_supply_demand_shift import M2Result, evaluate_m2_supply_demand_shift
from .e3_liquidity_sweep import E3Result, e3_to_econdition, evaluate_e3_htf_liquidity_sweep
from .m3_sweep_drop_pump import M3_INVERTED_GAP_POLICY, M3Result, evaluate_m3_sweep_drop_pump
from .composer import compose, evaluate_entry_combinations
from .models import (
    ALL_CONFIRMATIONS,
    DISPLACEMENT,
    LIQUIDITY_RECLAIM,
    REJECTION,
    STRUCTURE_SHIFT,
    CandidateDirection,
    ConfirmationState,
    DisplacementEvidence,
    EntryConfirmationRequest,
    EntryConfirmationResult,
    EventSequenceEvidence,
    LiquidityAlignment,
    OverallState,
    RejectionEvidence,
    StructureAlignment,
)

__all__ = [
    "evaluate_entry_confirmation",
    "EntryConfirmationRequest", "EntryConfirmationResult",
    "CandidateDirection", "ConfirmationState", "OverallState",
    "DisplacementEvidence", "RejectionEvidence", "StructureAlignment", "LiquidityAlignment",
    "EventSequenceEvidence",
    "ALL_CONFIRMATIONS", "DISPLACEMENT", "STRUCTURE_SHIFT", "LIQUIDITY_RECLAIM", "REJECTION",
    "CONTRACT_VERSION", "ENTRY_CONFIRMATION_CONTRACT_GAPS", "EntryConfirmationContractGap",
    # AG_ENTRY_CONFIRMATION_V2 (additive -- see docs/specs/ENTRY_CONFIRMATION_V2_SPEC.md)
    "evaluate_entry_confirmation_v2", "EntryConfirmationV2Request", "EntryConfirmationV2Result",
    "CONTRACT_VERSION_V2",
    "ConfirmationRoute", "ConfirmationModel", "EntryMethod", "StructuralInvalidationType",
    "DirectionalContext", "GapContext", "InvertedGapContext", "POIContext", "SpreadContext",
    "RouteResult", "EntryGeometry", "TypedEvent",
    "evaluate_gap_context", "evaluate_inverted_gap_context", "gap_midpoint",
    "evaluate_poi_context", "evaluate_spread_context",
    "classify_route", "evaluate_e1", "evaluate_e2", "evaluate_e3",
    # AG_ENTRY_CONFIRMATION_V2_1 (additive -- see docs/specs/ENTRY_CONFIRMATION_V2_1_SPEC.md)
    "CONTRACT_VERSION_V2_1", "SMCSweepShiftArrayResult", "SweepShiftArrayRequest",
    "evaluate_sweep_shift_array", "evaluate_reversal_sweep_shift", "evaluate_continuation_pullback",
    "determine_setup_family",
    "PivotRole", "PivotContext", "StructureShiftQuality", "StructureShiftQualityStatus",
    "SetupFamily", "EntryArrayType", "EntryMethodV21", "ConfluenceRelation",
    "DisplacementLeg", "EntryArrayContext",
    "classify_wick_or_close", "evaluate_pivot_context", "evaluate_structure_shift_quality",
    "evaluate_entry_array", "fvg_associated_with_leg", "ob_associated_with_shift",
    # SMC_CONDITIONAL_ENTRY_V2 -- 3 E-conditions x 3 M-maneuvers, 9 combinations (see entry_models_v1.py)
    "SMC_CONDITIONAL_ENTRY_V2", "SMC_ENTRY_MODELS_V1",
    "ENTRY_CONDITIONS", "MANEUVERS", "COMBINATIONS",
    "CHECK_TIMEFRAME", "CONFIRMATION_TIMEFRAME", "EXECUTION_TIMEFRAME",
    "REFERENCE_TIMEFRAME_E1", "REFERENCE_TIMEFRAME_E2", "H1_REACTION_V1",
    "EntryModelState", "EConditionResult", "SMCEntryCombinationResult", "SMCConditionalEntryAnalysis",
    "E1Result", "evaluate_e1_daily_gap_reaction", "e1_to_econdition",
    "M1Result", "evaluate_m1_character_change_with_inducement",
    "E2Result", "E2PoiReactionRequest", "evaluate_e2_h1_poi_reaction", "e2_to_econdition",
    "M2Result", "evaluate_m2_supply_demand_shift",
    "E3Result", "evaluate_e3_htf_liquidity_sweep", "e3_to_econdition",
    "M3Result", "evaluate_m3_sweep_drop_pump", "M3_INVERTED_GAP_POLICY",
    "compose", "evaluate_entry_combinations",
]
