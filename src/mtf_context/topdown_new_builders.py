"""TD-4: deterministic advisory context builders for the three TopDownContext V1
timeframes that had no producer before this work package -- W1 (WeeklyContext), H4
(H4Context), M15 (M15Context). ADAPTATION ONLY -- same discipline as TD-3's
topdown_context_adapters.py: no swing, BOS/CHOCH, FVG, order-block, or liquidity
detection is implemented here. Reuses the SAME pure fact-mapping helpers TD-3 already
defined (imported as public aliases from topdown_context_adapters.py) rather than
duplicating that logic.

AUTHORITY_REUSE (audited live before writing this module -- see
docs/status/TD4_NEW_CONTEXT_BUILDERS_STATUS.md AUTHORITY_REUSE table):
  structure   -> market_structure.analyze_structure(symbol, "W1"/"H4"/"M15") -- confirmed
                 to already work at all three timeframes with no code change (TD-2 added
                 the one genuinely missing MT5 mapping, W1, in mt5/market_data.py).
  liquidity   -> liquidity.liquidity_result(symbol, timeframe) -- same, unmodified.
  order blocks -> supply_demand.validated_order_blocks_for(symbol, timeframe) -- same.
  FVG         -> supply_demand.fair_value_gaps_for(symbol, timeframe) -- same.
  session box -> supply_demand.session_zone(symbol, session_name) -- session-window-
                 derived, not candle-timeframe-derived; attached to M15Context only
                 (see module docstring's REFERENCE-LEVEL SCOPING note below), never to
                 W1/H4 (no existing authority produces a weekly- or 4-hour-scoped
                 reference level -- reported as an honest gap, not invented).

REFERENCE-LEVEL SCOPING (a deliberate choice, not a limitation of the source):
  previous_day_high_low()/previous_week_high_low() are already attached to
  DailyContext (TD-3A) and session_zone("asian") is already attached to H1Context
  (TD-3A) -- re-attaching the identical fact to every other tier would be meaningless
  duplication of the same underlying value, not a new fact. M15Context additionally
  gets its OWN session-box ReferenceLevelFact (all three canonical sessions, not just
  Asian) because supply_demand.native_zones.session_zone()'s own ZoneResult is
  natively M15-scoped (assistant.market_data.session_snapshot() -- which session_zone
  wraps -- always operates on M15 candles), making M15 the more natural home for it;
  this is an independent, additive mapping in this new builder, not a modification of
  H1Context's existing (frozen, untouched) session mapping.

WeeklyContext has no parent field in the frozen contract (topdown_contracts.py) --
it is the top of the W1->D1->H4->H1->M15->M5 hierarchy, so build_weekly_context()
takes no parent-id parameter at all. H4Context/M15Context expose an OPTIONAL parent-id
parameter (never populated automatically -- parent-child orchestration is TD-7's job,
per this mission's explicit scope boundary).

STRUCTURE SEMANTICS: every StructureFact produced here traces to
market_structure.analyze_structure()'s own StructureResult.latest_bos/.latest_choch,
carrying structure_definition_id = SMC_MARKET_STRUCTURE_V1 -- the one and only
definition this contract allows (enforced by StructureFact.__post_init__ itself, not
re-validated here). Neither session_sweep_continuation's hand-rolled BOS nor
strategy_engine.sweep_retest's MSS is imported or referenced anywhere in this module.
"""
from __future__ import annotations

from typing import Optional, Sequence

from liquidity import liquidity_result
from liquidity.models import LiquidityLevel
from market_structure import analyze_structure
from market_structure.models import StructureResult
from supply_demand import ValidatedOrderBlock, ZoneResult, fair_value_gaps_for, session_zone, validated_order_blocks_for

from .topdown_context_adapters import (
    ADAPTER_FEATURE_VERSION,
    STRUCTURE_FACT_SOURCE,
    data_quality_for_structure,
    imbalance_facts_from_zones,
    liquidity_facts_from_levels,
    reference_level_fact_from_zone,
    structure_facts_from_result,
    zone_facts_from_validated_obs,
)
from .topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    TIMEFRAME_H4,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    H4Context,
    M15Context,
    WeeklyContext,
    compute_context_id,
)

WEEKLY_CONTEXT_SOURCE = "market_structure.analyze_structure"
H4_CONTEXT_SOURCE = "market_structure.analyze_structure"
M15_CONTEXT_SOURCE = "market_structure.analyze_structure"


def _session_source(session_name: str) -> str:
    return f"supply_demand.native_zones.session_zone:{session_name}"


# --------------------------------------------------------------------------- W1

def weekly_context_from_structure(
    structure: StructureResult, *,
    order_blocks: Sequence[ValidatedOrderBlock] = (),
    fvg_zones: Sequence[ZoneResult] = (),
    liquidity_levels: Sequence[LiquidityLevel] = (),
) -> Optional[WeeklyContext]:
    """Pure mapping. No composed W1 orchestrator exists anywhere in this repository
    (none did for M5 either, per TD-3) -- market_structure.analyze_structure(symbol,
    "W1") / validated_order_blocks_for(symbol, "W1") / fair_value_gaps_for(symbol,
    "W1") / liquidity_result(symbol, "W1") ARE the existing W1 authorities, confirmed
    (TD-4 audit) to already operate on native W1 candles with zero code change beyond
    TD-2's addition of "W1" to mt5/market_data.py's timeframe mapping.

    No reference_level_facts are populated for WeeklyContext -- no existing authority
    in this repository produces a weekly-scoped reference level (previous-month
    high/low, for example, does not exist); this is an honest absence, not a
    fabricated one."""
    quality = data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = structure_facts_from_result(structure, TIMEFRAME_W1, STRUCTURE_FACT_SOURCE)
    zone_facts = zone_facts_from_validated_obs(order_blocks, TIMEFRAME_W1)
    imbalance_facts = imbalance_facts_from_zones(fvg_zones, TIMEFRAME_W1)
    liquidity_facts = liquidity_facts_from_levels(liquidity_levels, TIMEFRAME_W1)
    context_id = compute_context_id(
        symbol=structure.symbol, timeframe=TIMEFRAME_W1, source=WEEKLY_CONTEXT_SOURCE,
        bar_close_time=structure.data_end_utc, feature_version=ADAPTER_FEATURE_VERSION,
    )
    return WeeklyContext(
        context_id=context_id, symbol=structure.symbol, timeframe=TIMEFRAME_W1,
        source=WEEKLY_CONTEXT_SOURCE, bar_close_time=structure.data_end_utc,
        feature_version=ADAPTER_FEATURE_VERSION, data_quality_status=quality,
        snapshot_fingerprint=None, structure_facts=facts, zone_facts=zone_facts,
        imbalance_facts=imbalance_facts, liquidity_facts=liquidity_facts,
    )


def build_weekly_context(symbol: str) -> Optional[WeeklyContext]:
    """Orchestration convenience over the same existing authorities used throughout
    this package. No detection of any kind happens here. Takes no parent-id parameter
    -- WeeklyContext is the top of the hierarchy (TD-1 contract)."""
    structure = analyze_structure(symbol, TIMEFRAME_W1)
    order_blocks = validated_order_blocks_for(symbol, TIMEFRAME_W1)
    fvg_query = fair_value_gaps_for(symbol, TIMEFRAME_W1)
    fvg_zones = fvg_query.zones if fvg_query.status == "OK" else ()
    liq_result = liquidity_result(symbol, TIMEFRAME_W1)
    liquidity_levels = liq_result.levels if liq_result.status == "LIQUIDITY_OK" else ()
    return weekly_context_from_structure(
        structure, order_blocks=order_blocks, fvg_zones=fvg_zones, liquidity_levels=liquidity_levels,
    )


# --------------------------------------------------------------------------- H4

def h4_context_from_structure(
    structure: StructureResult, *, parent_daily_context_id: Optional[str] = None,
    order_blocks: Sequence[ValidatedOrderBlock] = (),
    fvg_zones: Sequence[ZoneResult] = (),
    liquidity_levels: Sequence[LiquidityLevel] = (),
) -> Optional[H4Context]:
    """Pure mapping. No composed H4 orchestrator exists anywhere in this repository --
    the raw existing authorities ARE the H4 authority, same reasoning already
    established for M5 (TD-3) and W1 (above). No reference_level_facts are populated
    (see module docstring's REFERENCE-LEVEL SCOPING note -- previous-day/week facts
    already live on DailyContext; nothing H4-specific exists at the source)."""
    quality = data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = structure_facts_from_result(structure, TIMEFRAME_H4, STRUCTURE_FACT_SOURCE)
    zone_facts = zone_facts_from_validated_obs(order_blocks, TIMEFRAME_H4)
    imbalance_facts = imbalance_facts_from_zones(fvg_zones, TIMEFRAME_H4)
    liquidity_facts = liquidity_facts_from_levels(liquidity_levels, TIMEFRAME_H4)
    context_id = compute_context_id(
        symbol=structure.symbol, timeframe=TIMEFRAME_H4, source=H4_CONTEXT_SOURCE,
        bar_close_time=structure.data_end_utc, feature_version=ADAPTER_FEATURE_VERSION,
        parent_context_id=parent_daily_context_id,
    )
    return H4Context(
        context_id=context_id, symbol=structure.symbol, timeframe=TIMEFRAME_H4,
        source=H4_CONTEXT_SOURCE, bar_close_time=structure.data_end_utc,
        feature_version=ADAPTER_FEATURE_VERSION, data_quality_status=quality,
        snapshot_fingerprint=None, parent_daily_context_id=parent_daily_context_id,
        structure_facts=facts, zone_facts=zone_facts, imbalance_facts=imbalance_facts,
        liquidity_facts=liquidity_facts,
    )


def build_h4_context(symbol: str, *, parent_daily_context_id: Optional[str] = None) -> Optional[H4Context]:
    """Orchestration convenience over the same existing authorities used throughout
    this package. No detection of any kind happens here."""
    structure = analyze_structure(symbol, TIMEFRAME_H4)
    order_blocks = validated_order_blocks_for(symbol, TIMEFRAME_H4)
    fvg_query = fair_value_gaps_for(symbol, TIMEFRAME_H4)
    fvg_zones = fvg_query.zones if fvg_query.status == "OK" else ()
    liq_result = liquidity_result(symbol, TIMEFRAME_H4)
    liquidity_levels = liq_result.levels if liq_result.status == "LIQUIDITY_OK" else ()
    return h4_context_from_structure(
        structure, parent_daily_context_id=parent_daily_context_id,
        order_blocks=order_blocks, fvg_zones=fvg_zones, liquidity_levels=liquidity_levels,
    )


# --------------------------------------------------------------------------- M15

def m15_context_from_structure(
    structure: StructureResult, *, parent_h1_context_id: Optional[str] = None,
    order_blocks: Sequence[ValidatedOrderBlock] = (),
    fvg_zones: Sequence[ZoneResult] = (),
    liquidity_levels: Sequence[LiquidityLevel] = (),
    session_zones: Sequence[tuple] = (),
) -> Optional[M15Context]:
    """Pure mapping. No composed M15 orchestrator exists anywhere in this repository.
    `session_zones` is a caller-supplied sequence of (canonical_session_name,
    ZoneResult) pairs from already-fetched supply_demand.session_zone() calls
    (Asian/London/NY) -- M15 is the native timeframe of the underlying
    session_snapshot() calculation (see module docstring), so this is the tier where
    the fact is most naturally attached; each is mapped independently (absence for an
    incomplete session is valid, not fabricated; the session name is threaded through
    explicitly rather than read off ZoneResult.family, since all three canonical
    sessions share family=SESSION and would otherwise be indistinguishable in
    provenance). Deliberately does NOT import or reuse any SSC-specific M15
    interpretation (S1/S2/S3, fractal BOS, regime decision, entry scoring, campaign
    state) or Asian-Sweep-5R setup qualification -- neither module is imported here."""
    quality = data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = structure_facts_from_result(structure, TIMEFRAME_M15, STRUCTURE_FACT_SOURCE)
    zone_facts = zone_facts_from_validated_obs(order_blocks, TIMEFRAME_M15)
    imbalance_facts = imbalance_facts_from_zones(fvg_zones, TIMEFRAME_M15)
    liquidity_facts = liquidity_facts_from_levels(liquidity_levels, TIMEFRAME_M15)
    reference_level_facts = tuple(
        fact for fact in (
            reference_level_fact_from_zone(zone, TIMEFRAME_M15, _session_source(name))
            for name, zone in session_zones
        ) if fact is not None
    )
    context_id = compute_context_id(
        symbol=structure.symbol, timeframe=TIMEFRAME_M15, source=M15_CONTEXT_SOURCE,
        bar_close_time=structure.data_end_utc, feature_version=ADAPTER_FEATURE_VERSION,
        parent_context_id=parent_h1_context_id,
    )
    return M15Context(
        context_id=context_id, symbol=structure.symbol, timeframe=TIMEFRAME_M15,
        source=M15_CONTEXT_SOURCE, bar_close_time=structure.data_end_utc,
        feature_version=ADAPTER_FEATURE_VERSION, data_quality_status=quality,
        snapshot_fingerprint=None, parent_h1_context_id=parent_h1_context_id,
        structure_facts=facts, zone_facts=zone_facts, imbalance_facts=imbalance_facts,
        liquidity_facts=liquidity_facts, reference_level_facts=reference_level_facts,
    )


def build_m15_context(symbol: str, *, parent_h1_context_id: Optional[str] = None) -> Optional[M15Context]:
    """Orchestration convenience over the same existing authorities used throughout
    this package. No detection of any kind happens here."""
    structure = analyze_structure(symbol, TIMEFRAME_M15)
    order_blocks = validated_order_blocks_for(symbol, TIMEFRAME_M15)
    fvg_query = fair_value_gaps_for(symbol, TIMEFRAME_M15)
    fvg_zones = fvg_query.zones if fvg_query.status == "OK" else ()
    liq_result = liquidity_result(symbol, TIMEFRAME_M15)
    liquidity_levels = liq_result.levels if liq_result.status == "LIQUIDITY_OK" else ()
    session_zones = tuple((name, session_zone(symbol, name)) for name in ("asian", "london_am", "new_york_am"))
    return m15_context_from_structure(
        structure, parent_h1_context_id=parent_h1_context_id,
        order_blocks=order_blocks, fvg_zones=fvg_zones, liquidity_levels=liquidity_levels,
        session_zones=session_zones,
    )
