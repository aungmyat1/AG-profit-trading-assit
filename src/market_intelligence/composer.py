"""Deterministic MI composition from admitted replay evidence."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from historical_replay.evaluation_context import ReplayEvaluationContext

from .snapshot import (MIComponent, MIExecutionLineage, MIIdentity, MIProvenance,
                       MIQuality, MarketIntelligenceSnapshot, SCHEMA_VERSION,
                       build_snapshot_id)


def _component(value, name: str, *, feature_version: str = "UNAVAILABLE", classification: str = "UNAVAILABLE"):
    if value is None:
        return MIComponent("UNAVAILABLE", "UNAVAILABLE", feature_version, None, (f"{name}_UNAVAILABLE",))
    return MIComponent("AVAILABLE", classification, feature_version, value)


def compose_market_intelligence(
    context: ReplayEvaluationContext,
    *,
    sessions: Any = None,
    higher_timeframe_context: Any = None,
    h1_bias: Any = None,
    structure: Any = None,
    liquidity: Any = None,
    regime: Any = None,
    atr: Any = None,
    ema: Any = None,
    execution_timeframe: Optional[str] = None,
    decision_cycle: Optional[str] = None,
) -> MarketIntelligenceSnapshot:
    """Compose evidence without fetching data or calculating replacement features."""
    if not isinstance(context, ReplayEvaluationContext):
        raise TypeError("MI requires an admitted ReplayEvaluationContext")
    components = {
        "sessions": _component(sessions, "sessions", feature_version="TD8C_SESSION_REFERENCE_V1", classification="ADAPTED_AUTHORITATIVE"),
        "higher_timeframe_context": _component({"topdown": higher_timeframe_context, "h1_bias": h1_bias} if (higher_timeframe_context is not None or h1_bias is not None) else None, "topdown", feature_version="TD8_TOPDOWN_CONTEXT_V1", classification="ADAPTED_AUTHORITATIVE"),
        "structure": _component(structure, "structure", feature_version="MARKET_STRUCTURE_EXISTING", classification="ADAPTED_AUTHORITATIVE"),
        "liquidity": _component(liquidity, "liquidity", feature_version="LIQUIDITY_EXISTING", classification="ADAPTED_AUTHORITATIVE"),
        "regime": _component(regime, "regime", feature_version="CROSS_STRATEGY_REGIME_UNAVAILABLE"),
        "volatility": _component({"atr": atr, "ema": None} if atr is not None else None, "volatility", feature_version="ATR_EXISTING_EMA_UNAVAILABLE", classification="ADAPTED_AUTHORITATIVE" if atr is not None else "UNAVAILABLE"),
    }
    missing = tuple(name for name, item in components.items() if item.status == "UNAVAILABLE")
    quality = MIQuality("INCOMPLETE" if missing else "VALID", tuple(f"{n.upper()}_UNAVAILABLE" for n in missing), missing, "PARTIAL" if missing else "COMPLETE")
    identities = tuple((tf, identity.as_composed_identity_token()) for tf, identity in sorted(context.series_identities.items()))
    provenance = MIProvenance(context.event_id, context.visibility_rule_version, identities,
                              tuple((tf, "REPLAY_BOUND_SERIES") for tf, _ in identities))
    identity = MIIdentity(context.symbol, context.as_of, context.event_id, "HISTORICAL_AS_OF", decision_cycle)
    lineage = MIExecutionLineage(execution_timeframe or context.timeframes[-1], context.timeframes, None, (), "M1" in context.timeframes)
    provisional = MarketIntelligenceSnapshot(SCHEMA_VERSION, "PENDING", identity, provenance, quality,
                                              components["sessions"], components["higher_timeframe_context"],
                                              components["structure"], components["liquidity"], components["regime"],
                                              components["volatility"], lineage)
    snapshot_id = build_snapshot_id(provisional.to_dict())
    return MarketIntelligenceSnapshot(SCHEMA_VERSION, snapshot_id, identity, provenance, quality,
                                      provisional.sessions, provisional.higher_timeframe_context,
                                      provisional.structure, provisional.liquidity, provisional.regime,
                                      provisional.volatility, lineage)
