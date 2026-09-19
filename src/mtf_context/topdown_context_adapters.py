"""TD-3/TD-3A: thin, deterministic, read-only adapters translating EXISTING D1/H1/M5
market-context facts into the frozen TD-1 (+TD-3A amendment) tier-context contracts
(DailyContext, H1Context, M5Context). ADAPTATION ONLY -- this module implements no
swing, BOS/CHOCH, FVG, order-block, or liquidity detection. Every fact placed into a
TD context originates from an already-authoritative call this repository already
makes elsewhere; see AUTHORITY_REUSE below and
docs/status/TD3_EXISTING_CONTEXT_ADAPTERS_STATUS.md /
docs/status/TD3A_TOPDOWN_FACT_CONTRACT_GAP_AUDIT_STATUS.md for the full coverage
report.

AUTHORITY_REUSE (no new detector anywhere in this file):
  D1 structure   -> daily_routine.d1_context.build_d1_context()          (existing D1 orchestrator)
  H1 structure   -> daily_routine.h1_setup.build_h1_setup_context()       (existing H1 orchestrator)
  M5 structure   -> market_structure.analyze_structure() directly          (no composed M5
                    orchestrator exists in this repo -- TD-0 audit finding; this IS the same
                    canonical structure authority D1/H1 already call, just with no D1/H1-style
                    wrapper around it at M5)
  Liquidity      -> liquidity.liquidity_result()
  Order blocks   -> supply_demand.validated_order_blocks_for()
  FVG            -> supply_demand.fair_value_gaps_for()
  Reference lvls -> supply_demand.previous_day_high_low() / previous_week_high_low() / session_zone()

TD-3A RULE FOR WHICH CALLS ARE MADE (kept deliberately simple and stated once here):
  - If a fact is ALREADY a field on the existing D1/H1 orchestrator's own output object
    (D1Context.gap_liquidity, D1Context.evidence["liquidity"], H1SetupContext.
    evidence["liquidity"]), the pure mapper reads it directly -- ZERO extra I/O.
  - If no existing orchestrator exposes a fact at all for that tier (true for every M5
    fact, since no M5 orchestrator exists -- same reasoning TD-3 already used for M5
    structure), OR the orchestrator computes it internally but discards the full object
    (the H1-duplicate-structure-call gap TD-3 already documented, and equally true for
    H1's order blocks/FVG/session box), the ORCHESTRATION CONVENIENCE function
    (build_daily_context/build_h1_context/build_m5_context) calls the SAME existing
    authority function directly to recover it. This is invoking an existing authority a
    second (or first, for M5) time, never a new implementation of it.

Every BOS/CHOCH StructureFact in every tier traces to
market_structure.analyze_structure()'s own StructureResult.latest_bos/.latest_choch
(SMC_MARKET_STRUCTURE_V1 -- the one and only structure_definition_id this contract
allows). Neither session_sweep_continuation's hand-rolled BOS nor
strategy_engine.sweep_retest's MSS is imported or referenced anywhere in this module
(see tests/test_topdown_context_adapters_no_redetection.py).

STRATEGY-OWNED INTERPRETATION DELIBERATELY EXCLUDED: H1SetupContext's own
selected_poi/current_location/alert_zone/midnight_open/asian_session_high/low fields
are H1-strategy-specific interpretation layered on top of raw market structure (POI
selection driven by D1's directional permission) -- per the TD-3/TD-3A mission's
structure-semantic boundary, none of that is copied into H1Context. In particular,
H1SetupContext.poi_candidates is a ROLE-FILTERED subset of order blocks (filtered by
D1's directional_permission) -- TD-3A's ZoneFact mapping for H1 deliberately calls
validated_order_blocks_for() itself to get the FULL, unfiltered set instead of reusing
poi_candidates, so the shared fact carries no D1-permission-driven filter.

CONTRACT GAP CLOSED THIS PASS (TD-3A, TD3A_TOPDOWN_FACT_CONTRACT_GAP_AUDIT): TD-3
recorded that TD-1's frozen tier-context contracts had no field for liquidity levels,
order blocks, FVGs, or reference levels even though existing authorities already
produce all of them. TD-3A's audit (see status doc) classified each as
SHARED_MARKET_FACT and topdown_contracts.py now carries four new fact types
(LiquidityFact, ZoneFact, ImbalanceFact, ReferenceLevelFact) plus four new optional
tuple fields per tier context -- this module maps existing facts into them.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from daily_routine.d1_context import build_d1_context
from daily_routine.h1_setup import build_h1_setup_context
from daily_routine.models import D1Context, H1SetupContext
from liquidity import liquidity_result
from liquidity.models import LiquidityLevel
from market_structure import analyze_structure
from market_structure.models import StructureResult
from supply_demand import (
    ValidatedOrderBlock,
    ZoneResult,
    fair_value_gaps_for,
    previous_day_high_low,
    previous_week_high_low,
    session_zone,
    validated_order_blocks_for,
)

from .topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_M5,
    ZONE_DEFINITION_NATIVE_REFERENCE_V1,
    ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
    DailyContext,
    H1Context,
    ImbalanceFact,
    LiquidityFact,
    M5Context,
    ReferenceLevelFact,
    StructureFact,
    ZoneFact,
    compute_context_id,
)

ADAPTER_FEATURE_VERSION = "TD3_CONTEXT_ADAPTER_V1"

STRUCTURE_FACT_SOURCE = "market_structure.analyze_structure"
D1_CONTEXT_SOURCE = "daily_routine.d1_context.build_d1_context"
H1_CONTEXT_SOURCE = "daily_routine.h1_setup.build_h1_setup_context"
M5_CONTEXT_SOURCE = "market_structure.analyze_structure"  # no composed M5 orchestrator exists; see module docstring

FVG_SOURCE = "supply_demand.fair_value_gaps_for"
OB_SOURCE = "supply_demand.validated_order_blocks_for"
LIQUIDITY_SOURCE = "liquidity.liquidity_result"
REFERENCE_LEVEL_SOURCE_PREVIOUS_DAY = "supply_demand.native_zones.previous_day_high_low"
REFERENCE_LEVEL_SOURCE_PREVIOUS_WEEK = "supply_demand.native_zones.previous_week_high_low"
REFERENCE_LEVEL_SOURCE_SESSION_ASIAN = "supply_demand.native_zones.session_zone"

# supply_demand/ob_contract.py's own frozen contract name (AG_ORDER_BLOCK_V1, "frozen
# by owner 2026-08-26") -- reused verbatim as ZoneFact's feature_version for order
# blocks specifically, since it is a genuinely versioned, named contract distinct from
# the coarser zone_definition_id classification. FVG/reference zones have no such
# named per-instance contract at the source, so those fall back to their own
# zone_definition_id value as feature_version (see helpers below).
ORDER_BLOCK_FEATURE_VERSION = "AG_ORDER_BLOCK_V1"


def _structure_facts(structure: StructureResult, timeframe: str, source: str) -> Tuple[StructureFact, ...]:
    """Pure mapping over an already-computed StructureResult -- reads
    latest_bos/latest_choch verbatim, runs no detection. Returns () if smc_version is
    unavailable (StructureFact.feature_version is mandatory and non-empty; this
    function never fabricates one) or if neither event is present (a legitimate
    "no confirmed break yet" market fact, not a data problem)."""
    if structure.smc_version is None:
        return ()
    facts = []
    for point in (structure.latest_bos, structure.latest_choch):
        if point is None:
            continue
        kind = point.kind.value
        event_type = "BOS" if "BOS" in kind else "CHOCH"
        direction = "BULLISH" if "BULLISH" in kind else "BEARISH"
        facts.append(StructureFact(
            structure_definition_id=STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
            timeframe=timeframe, event_type=event_type, direction=direction,
            level=point.price, confirmation_bar_time=point.time_utc,
            source=source, feature_version=structure.smc_version,
        ))
    return tuple(facts)


def _data_quality_for_structure(structure: StructureResult) -> str:
    """VALID: structure fetched and a real detector version is attached.
    PARTIAL: structure fetched but smc_version unavailable (facts cannot be built).
    DATA_ERROR: the underlying analyze_structure() call itself failed/degraded."""
    if structure.status != "VALID":
        return DATA_QUALITY_DATA_ERROR
    if structure.smc_version is None:
        return DATA_QUALITY_PARTIAL
    return DATA_QUALITY_VALID


# --------------------------------------------------------------------------- TD-3A fact mappers
# All pure functions: no I/O, read already-computed source objects verbatim. Each
# skips (never fabricates) an instance missing a mandatory contract field.

def _imbalance_facts_from_zones(zones: Sequence[ZoneResult], timeframe: str) -> Tuple[ImbalanceFact, ...]:
    facts = []
    for zone in zones:
        if zone.low is None or zone.high is None or zone.origin_time is None:
            continue
        facts.append(ImbalanceFact(
            zone_definition_id=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1, timeframe=timeframe,
            direction=zone.direction.value, low=zone.low, high=zone.high,
            origin_time=zone.origin_time, status=zone.status.value, source=zone.source,
            feature_version=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
        ))
    return tuple(facts)


def _zone_facts_from_validated_obs(obs: Sequence[ValidatedOrderBlock], timeframe: str) -> Tuple[ZoneFact, ...]:
    facts = []
    for ob in obs:
        if ob.low is None or ob.high is None or ob.origin_time is None:
            continue
        facts.append(ZoneFact(
            zone_definition_id=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1, timeframe=timeframe,
            role=ob.candidate.role.value, direction=ob.direction.value,
            low=ob.low, high=ob.high, origin_time=ob.origin_time,
            validation_status=ob.status.value, source=ob.candidate.source,
            feature_version=ORDER_BLOCK_FEATURE_VERSION,
            structure_confirmation_time=ob.structure_event.time_utc if ob.structure_event is not None else None,
        ))
    return tuple(facts)


def _reference_level_fact_from_zone(zone: Optional[ZoneResult], timeframe: str, source: str) -> Optional[ReferenceLevelFact]:
    if zone is None or zone.low is None or zone.high is None or zone.origin_time is None:
        return None
    return ReferenceLevelFact(
        zone_definition_id=ZONE_DEFINITION_NATIVE_REFERENCE_V1, family=zone.family.value,
        timeframe=timeframe, low=zone.low, high=zone.high, origin_time=zone.origin_time,
        status=zone.status.value, source=source, feature_version=ZONE_DEFINITION_NATIVE_REFERENCE_V1,
    )


def _liquidity_facts_from_levels(levels: Sequence[LiquidityLevel], timeframe: str) -> Tuple[LiquidityFact, ...]:
    facts = []
    for level in levels:
        if level.origin_time is None:
            continue
        facts.append(LiquidityFact(
            liquidity_definition_id=LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1, timeframe=timeframe,
            side=level.side.value, price=level.price, origin_time=level.origin_time,
            status=level.status.value, source=level.source,
            feature_version=LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1,
            sweep_time=level.sweep_time, reclaim_time=level.reclaim_time,
        ))
    return tuple(facts)


# --------------------------------------------------------------------------- D1

def daily_context_from_d1(
    d1: D1Context, *, parent_weekly_context_id: Optional[str] = None,
    previous_day_zone: Optional[ZoneResult] = None,
    previous_week_zone: Optional[ZoneResult] = None,
) -> Optional[DailyContext]:
    """Pure mapping from an already-built daily_routine.models.D1Context (the existing
    build_d1_context() orchestrator's own return value) into DailyContext.

    `previous_day_zone`/`previous_week_zone` are optional pre-fetched ZoneResults
    (supply_demand.previous_day_high_low()/previous_week_high_low()) -- D1Context
    itself carries no reference-level field, so these are dependency-injected rather
    than read off `d1` (keeps this function pure/testable; see build_daily_context()
    for the orchestration convenience that actually calls those functions).

    Returns None when the D1 authority itself could not establish a closed-bar
    timestamp (its own `status == "UNAVAILABLE"`, i.e. `evidence["structure"]` was
    never populated because analyze_structure() failed) -- DailyContext.bar_close_time
    is mandatory, so there is nothing honest to construct. This is a data-quality
    outcome, not an adapter defect; see ADAPTER_COVERAGE in the status doc."""
    structure = d1.evidence.get("structure") if d1.evidence else None
    if structure is None:
        return None
    quality = _data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = _structure_facts(structure, TIMEFRAME_D1, STRUCTURE_FACT_SOURCE)
    imbalance_facts = _imbalance_facts_from_zones(d1.gap_liquidity, TIMEFRAME_D1)
    liq_result = d1.evidence.get("liquidity") if d1.evidence else None
    liquidity_facts = _liquidity_facts_from_levels(liq_result.levels if liq_result is not None else (), TIMEFRAME_D1)
    reference_level_facts = tuple(
        fact for fact in (
            _reference_level_fact_from_zone(previous_day_zone, TIMEFRAME_D1, REFERENCE_LEVEL_SOURCE_PREVIOUS_DAY),
            _reference_level_fact_from_zone(previous_week_zone, TIMEFRAME_D1, REFERENCE_LEVEL_SOURCE_PREVIOUS_WEEK),
        ) if fact is not None
    )
    context_id = compute_context_id(
        symbol=d1.symbol, timeframe=TIMEFRAME_D1, source=D1_CONTEXT_SOURCE,
        bar_close_time=structure.data_end_utc, feature_version=ADAPTER_FEATURE_VERSION,
        parent_context_id=parent_weekly_context_id,
    )
    return DailyContext(
        context_id=context_id, symbol=d1.symbol, timeframe=TIMEFRAME_D1,
        source=D1_CONTEXT_SOURCE, bar_close_time=structure.data_end_utc,
        feature_version=ADAPTER_FEATURE_VERSION, data_quality_status=quality,
        snapshot_fingerprint=None, parent_weekly_context_id=parent_weekly_context_id,
        structure_facts=facts, imbalance_facts=imbalance_facts,
        liquidity_facts=liquidity_facts, reference_level_facts=reference_level_facts,
    )


def build_daily_context(symbol: str, *, parent_weekly_context_id: Optional[str] = None) -> Optional[DailyContext]:
    """Orchestration convenience: calls the existing build_d1_context() plus
    previous_day_high_low()/previous_week_high_low() (no D1 orchestrator exposes
    those, so they're called directly here -- same existing authorities
    liquidity.liquidity_result() already calls internally, not a new detector). No
    detection of any kind happens in this function."""
    d1 = build_d1_context(symbol)
    previous_day_zone = previous_day_high_low(symbol)
    previous_week_zone = previous_week_high_low(symbol)
    return daily_context_from_d1(
        d1, parent_weekly_context_id=parent_weekly_context_id,
        previous_day_zone=previous_day_zone, previous_week_zone=previous_week_zone,
    )


# --------------------------------------------------------------------------- H1

def h1_context_from_sources(
    h1_setup: H1SetupContext, structure: StructureResult, *,
    parent_h4_context_id: Optional[str] = None,
    order_blocks: Sequence[ValidatedOrderBlock] = (),
    fvg_zones: Sequence[ZoneResult] = (),
    asian_session_zone: Optional[ZoneResult] = None,
) -> Optional[H1Context]:
    """Pure mapping. `h1_setup` is the existing build_h1_setup_context() result,
    consulted to confirm this really is that authority's output for this symbol, and
    to read its already-populated `evidence["liquidity"]` -- its own strategy-specific
    fields (selected_poi, current_location, alert_zone, midnight_open, asian session
    box, poi_candidates) are deliberately NOT copied into H1Context (see module
    docstring). `structure`/`order_blocks`/`fvg_zones`/`asian_session_zone` are fresh
    calls to the SAME existing authorities build_h1_setup_context() already calls (or
    would need to call) internally -- see module docstring's TD-3A rule."""
    if h1_setup.symbol != structure.symbol:
        raise ValueError("h1_setup and structure must describe the same symbol")
    quality = _data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = _structure_facts(structure, TIMEFRAME_H1, STRUCTURE_FACT_SOURCE)
    liq_result = h1_setup.evidence.get("liquidity") if h1_setup.evidence else None
    liquidity_facts = _liquidity_facts_from_levels(liq_result.levels if liq_result is not None else (), TIMEFRAME_H1)
    zone_facts = _zone_facts_from_validated_obs(order_blocks, TIMEFRAME_H1)
    imbalance_facts = _imbalance_facts_from_zones(fvg_zones, TIMEFRAME_H1)
    reference_fact = _reference_level_fact_from_zone(asian_session_zone, TIMEFRAME_H1, REFERENCE_LEVEL_SOURCE_SESSION_ASIAN)
    reference_level_facts = (reference_fact,) if reference_fact is not None else ()
    context_id = compute_context_id(
        symbol=h1_setup.symbol, timeframe=TIMEFRAME_H1, source=H1_CONTEXT_SOURCE,
        bar_close_time=structure.data_end_utc, feature_version=ADAPTER_FEATURE_VERSION,
        parent_context_id=parent_h4_context_id,
    )
    return H1Context(
        context_id=context_id, symbol=h1_setup.symbol, timeframe=TIMEFRAME_H1,
        source=H1_CONTEXT_SOURCE, bar_close_time=structure.data_end_utc,
        feature_version=ADAPTER_FEATURE_VERSION, data_quality_status=quality,
        snapshot_fingerprint=None, parent_h4_context_id=parent_h4_context_id,
        structure_facts=facts, liquidity_facts=liquidity_facts, zone_facts=zone_facts,
        imbalance_facts=imbalance_facts, reference_level_facts=reference_level_facts,
    )


def build_h1_context(
    symbol: str, *, d1_context: Optional[D1Context] = None, parent_h4_context_id: Optional[str] = None,
) -> Optional[H1Context]:
    """Orchestration convenience: calls the existing build_h1_setup_context() (which
    itself requires a D1Context -- built via build_d1_context() if the caller doesn't
    already have one) plus analyze_structure()/validated_order_blocks_for()/
    fair_value_gaps_for()/session_zone() at H1 to recover fields the H1 orchestrator
    either discards or role-filters (see module docstring). No detection is added."""
    d1_context = d1_context or build_d1_context(symbol)
    h1_setup = build_h1_setup_context(symbol, d1_context)
    structure = analyze_structure(symbol, TIMEFRAME_H1)
    order_blocks = validated_order_blocks_for(symbol, TIMEFRAME_H1)
    fvg_query = fair_value_gaps_for(symbol, TIMEFRAME_H1)
    fvg_zones = fvg_query.zones if fvg_query.status == "OK" else ()
    asian_zone = session_zone(symbol, "asian")
    return h1_context_from_sources(
        h1_setup, structure, parent_h4_context_id=parent_h4_context_id,
        order_blocks=order_blocks, fvg_zones=fvg_zones, asian_session_zone=asian_zone,
    )


# --------------------------------------------------------------------------- M5

def m5_context_from_structure(
    structure: StructureResult, *, parent_m15_context_id: Optional[str] = None,
    order_blocks: Sequence[ValidatedOrderBlock] = (),
    fvg_zones: Sequence[ZoneResult] = (),
    liquidity_levels: Sequence[LiquidityLevel] = (),
) -> Optional[M5Context]:
    """Pure mapping. No composed M5 orchestrator exists in this repository (TD-0
    finding) -- market_structure.analyze_structure(symbol, "M5") /
    validated_order_blocks_for(symbol, "M5") / fair_value_gaps_for(symbol, "M5") /
    liquidity_result(symbol, "M5") ARE the existing M5 authorities being adapted here,
    the same functions D1Context/H1SetupContext already call at their own
    timeframes."""
    quality = _data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = _structure_facts(structure, TIMEFRAME_M5, STRUCTURE_FACT_SOURCE)
    zone_facts = _zone_facts_from_validated_obs(order_blocks, TIMEFRAME_M5)
    imbalance_facts = _imbalance_facts_from_zones(fvg_zones, TIMEFRAME_M5)
    liquidity_facts = _liquidity_facts_from_levels(liquidity_levels, TIMEFRAME_M5)
    context_id = compute_context_id(
        symbol=structure.symbol, timeframe=TIMEFRAME_M5, source=M5_CONTEXT_SOURCE,
        bar_close_time=structure.data_end_utc, feature_version=ADAPTER_FEATURE_VERSION,
        parent_context_id=parent_m15_context_id,
    )
    return M5Context(
        context_id=context_id, symbol=structure.symbol, timeframe=TIMEFRAME_M5,
        source=M5_CONTEXT_SOURCE, bar_close_time=structure.data_end_utc,
        feature_version=ADAPTER_FEATURE_VERSION, data_quality_status=quality,
        snapshot_fingerprint=None, parent_m15_context_id=parent_m15_context_id,
        structure_facts=facts, zone_facts=zone_facts, imbalance_facts=imbalance_facts,
        liquidity_facts=liquidity_facts,
    )


def build_m5_context(symbol: str, *, parent_m15_context_id: Optional[str] = None) -> Optional[M5Context]:
    """Orchestration convenience over the same existing authorities used everywhere
    else in this module. No detection of any kind happens here."""
    structure = analyze_structure(symbol, TIMEFRAME_M5)
    order_blocks = validated_order_blocks_for(symbol, TIMEFRAME_M5)
    fvg_query = fair_value_gaps_for(symbol, TIMEFRAME_M5)
    fvg_zones = fvg_query.zones if fvg_query.status == "OK" else ()
    liq_result = liquidity_result(symbol, TIMEFRAME_M5)
    liquidity_levels = liq_result.levels if liq_result.status == "LIQUIDITY_OK" else ()
    return m5_context_from_structure(
        structure, parent_m15_context_id=parent_m15_context_id,
        order_blocks=order_blocks, fvg_zones=fvg_zones, liquidity_levels=liquidity_levels,
    )


# --------------------------------------------------------------------------- Public aliases (TD-4)
# TD-4's new W1/H4/M15 builders (topdown_new_builders.py) reuse the exact same pure
# fact-mapping helpers defined above rather than duplicating this logic -- these
# aliases change nothing about the private names' behavior or the tests that
# reference them directly; they exist purely so a second module can import the same
# functions under public names.
structure_facts_from_result = _structure_facts
data_quality_for_structure = _data_quality_for_structure
imbalance_facts_from_zones = _imbalance_facts_from_zones
zone_facts_from_validated_obs = _zone_facts_from_validated_obs
reference_level_fact_from_zone = _reference_level_fact_from_zone
liquidity_facts_from_levels = _liquidity_facts_from_levels
