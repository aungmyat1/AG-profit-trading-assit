"""SMC_MARKET_MAP_V1 -- the normalized, single-snapshot picture of everything the
assistant already knows about a symbol at one evaluation timestamp (spec sections 17-19).

Not a new detector: every field is populated by calling an already-frozen analyzer
exactly once per timeframe (market_structure.analyze_structure_tiers,
supply_demand.analyzer.{order_blocks_for,fair_value_gaps_for,validated_order_blocks_for},
liquidity.analyzer.liquidity_result, supply_demand.native_zones.dealing_range_zones) and
stitching the results together with stable evidence IDs (see evidence.py) so downstream
consumers (surveillance, proposals, visual explanation) can reference the SAME object
without re-deriving it.

This module intentionally does NOT re-derive or duplicate SMC_CONDITIONAL_ENTRY_V2's own
E1/E2/E3/M1/M2/M3/composer logic (daytrading_runtime/conditional_entry_snapshot.py) --
that pipeline already fetches and evaluates what IT needs, independently, and stays
untouched. SMCMarketMap exists for the broader "what's on the chart" picture (structure/
zones/liquidity/premium-discount across multiple timeframes) that surveillance and visual
explanation need but the entry pipeline does not expose wholesale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

from liquidity.models import LiquidityLevel
from market_structure.models import TieredStructureResult
from supply_demand.models import ZoneResult
from supply_demand.native_zones import DealingRangeZones

SMC_MARKET_MAP_V1 = "SMC_MARKET_MAP_V1"

DEFAULT_TIMEFRAMES: Tuple[str, ...] = ("D1", "H4", "H1", "M15", "M5")


@dataclass(frozen=True)
class TimeframeMap:
    """Everything normalized for ONE timeframe. Any field may be absent (None / empty
    tuple) rather than fabricated -- absence is a valid, honestly-reported state (spec
    section 51/53), never silently defaulted to a guess."""

    timeframe: str
    structure: Optional[TieredStructureResult] = None
    order_blocks: Tuple[ZoneResult, ...] = field(default_factory=tuple)
    fair_value_gaps: Tuple[ZoneResult, ...] = field(default_factory=tuple)
    liquidity_levels: Tuple[LiquidityLevel, ...] = field(default_factory=tuple)

    # Evidence-ID lookup: id -> (kind, object). Populated by the builder so proposal/
    # visual-explanation layers can resolve a `source_id` back to its real object
    # without re-scanning the tuples above.
    evidence_index: Dict[str, object] = field(default_factory=dict)

    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SMCMarketMap:
    version: str = SMC_MARKET_MAP_V1
    symbol: str = ""
    snapshot_time: Optional[datetime] = None

    timeframes: Dict[str, TimeframeMap] = field(default_factory=dict)  # keyed by timeframe string

    premium_discount: Optional[DealingRangeZones] = None
    premium_discount_source: Optional[str] = None  # e.g. "previous_day" -- see native_zones.dealing_range_zones

    data_quality: str = "OK"  # "OK" / "PARTIAL" / "UNAVAILABLE"
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    def timeframe_map(self, timeframe: str) -> Optional[TimeframeMap]:
        return self.timeframes.get(timeframe)

    def resolve_evidence(self, evidence_id: str) -> Optional[object]:
        """Cross-timeframe evidence lookup -- proposal/visual layers carry a bare
        `source_id` without knowing which timeframe it came from."""
        for tf_map in self.timeframes.values():
            if evidence_id in tf_map.evidence_index:
                return tf_map.evidence_index[evidence_id]
        return None
