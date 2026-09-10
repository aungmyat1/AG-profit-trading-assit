"""DAYTRADING_BASIC_SKILLS_ROUTER_V1 shapes. Reuses strategy_engine.session's own
SetupType/Direction/DecisionStatus/Regime verbatim -- never redefined here -- and embeds
its SetupDecision unmodified for full evidence/entry-reference access rather than
flattening/duplicating its fields (same "compose, don't flatten" discipline as
assistant.analysis_models.FiveSkillAnalysisResult composing each capability's own
result unchanged).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Tuple

from market_intelligence.models import MarketBiasResult
from strategy_engine.session import Direction, Regime, SetupDecision, SetupType


class MarketBiasDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INDETERMINATE = "INDETERMINATE"


class DirectionAlignment(str, Enum):
    ALIGNED = "ALIGNED"
    CONFLICT = "CONFLICT"
    BIAS_NEUTRAL = "BIAS_NEUTRAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class MarketBias:
    """Evidence, not just a label (spec section 4) -- every field traces back to
    market_structure.tiers.TieredStructureResult.external, never a new structure
    algorithm."""

    direction: str = MarketBiasDirection.INDETERMINATE.value
    timeframe: Optional[str] = None
    external_structure_direction: Optional[str] = None
    protected_level_type: Optional[str] = None  # "PROTECTED_HIGH" / "PROTECTED_LOW"
    protected_level: Optional[float] = None
    latest_break: Optional[str] = None  # e.g. "BOS_UP" / "CHOCH_DOWN", copied verbatim
    reasons: Tuple[str, ...] = field(default_factory=tuple)

    # AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1 M4: the exact canonical
    # MarketBiasResult this legacy MarketBias's direction was delegated to (P3/P6 --
    # "preserve canonical provenance, not just direction"). Held directly (Approach A
    # from the M4 spec) rather than copied field-by-field, since MarketBiasResult is
    # itself already frozen/immutable -- holding the object IS the lossless-traceability
    # guarantee, not a duplicate of it. None only for a MarketBias constructed by a
    # caller that never went through derive_market_bias_from_tiers (e.g. a hand-built
    # test fixture) -- never fabricated after the fact.
    canonical_provenance: Optional[MarketBiasResult] = None


@dataclass(frozen=True)
class DaytradingSetupDecision:
    symbol: str
    strategy_id: str
    evaluation_time: Optional[datetime]

    market_bias: MarketBias

    regime: Optional[Regime] = None
    session_trend_direction: Optional[Direction] = None
    efficiency_ratio: Optional[float] = None

    sweep_detected: bool = False
    sweep_side: Optional[str] = None  # "BUY_SIDE" / "SELL_SIDE"

    setup_type: SetupType = SetupType.NONE
    direction: Optional[Direction] = None
    direction_alignment: DirectionAlignment = DirectionAlignment.NOT_APPLICABLE

    decision_status: str = "NO_SETUP"  # VALID / NO_SETUP / CONFLICT / AMBIGUOUS / WAITING_REFERENCE
    execution_eligible: bool = False

    supply_demand_context: Optional[Any] = None
    entry_confirmation_state: Optional[str] = None

    reason_codes: Tuple[str, ...] = field(default_factory=tuple)

    session_decision: Optional[SetupDecision] = None  # verbatim strategy_engine.session result
    contract_version: str = "DAYTRADING_BASIC_SKILLS_ROUTER_V1"
