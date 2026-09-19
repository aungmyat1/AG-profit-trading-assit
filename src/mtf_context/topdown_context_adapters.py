"""TD-3: thin, deterministic, read-only adapters translating EXISTING D1/H1/M5
market-context facts into the frozen TD-1 tier-context contracts (DailyContext,
H1Context, M5Context). ADAPTATION ONLY -- this module implements no swing, BOS/CHOCH,
FVG, order-block, or liquidity detection. Every fact placed into a TD context
originates from an already-authoritative call this repository already makes
elsewhere; see AUTHORITY_REUSE below and
docs/status/TD3_EXISTING_CONTEXT_ADAPTERS_STATUS.md for the full coverage report.

AUTHORITY_REUSE (no new detector anywhere in this file):
  D1 -> daily_routine.d1_context.build_d1_context()          (existing D1 orchestrator)
  H1 -> daily_routine.h1_setup.build_h1_setup_context()       (existing H1 orchestrator)
  M5 -> market_structure.analyze_structure() directly          (no composed M5
        orchestrator exists in this repo -- TD-0 audit finding; this IS the same
        canonical structure authority D1/H1 already call, just with no D1/H1-style
        wrapper around it at M5)
  Every BOS/CHOCH StructureFact in every tier traces to
        market_structure.analyze_structure()'s own StructureResult.latest_bos /
        .latest_choch (market_structure/smc_adapter.py + analyzer.py's SMC semantics --
        the one and only structure_definition_id this contract allows,
        SMC_MARKET_STRUCTURE_V1). Neither session_sweep_continuation's hand-rolled BOS
        nor strategy_engine.sweep_retest's MSS is imported or referenced anywhere in
        this module (see tests/test_topdown_context_adapters_no_redetection.py).

DOCUMENTED GAP (existing H1 authority, not fixed here): daily_routine.h1_setup.
build_h1_setup_context() calls market_structure.analyze_structure(symbol, "H1")
internally but only preserves `.state` on its own H1SetupContext -- the full
StructureResult (data_end_utc for a closed-bar timestamp, latest_bos/latest_choch for
structure facts, smc_version for feature identity) is discarded after that call
returns. Since H1Context.bar_close_time is mandatory, this adapter makes its own
second call to the SAME market_structure.analyze_structure(symbol, "H1") function to
recover those fields -- this is invoking the existing authority a second time, not a
new implementation of it.

STRATEGY-OWNED INTERPRETATION DELIBERATELY EXCLUDED: H1SetupContext's own
selected_poi/current_location/alert_zone/midnight_open/asian_session_high/low fields
are H1-strategy-specific interpretation layered on top of raw market structure (POI
selection driven by D1's directional permission) -- per the TD-3 mission's structure-
semantic boundary, none of that is copied into H1Context. Only the generic structural
fact (BOS/CHOCH) is adapted.

CONTRACT GAP (TD-1, not fixed here): TD-1's frozen tier-context contracts
(topdown_contracts.py) define exactly one variable fact field, `structure_facts:
Tuple[StructureFact, ...]` -- there is no field to carry liquidity levels, order
blocks, or FVG zones, even though all three exist and are already computed by
existing authorities (liquidity.liquidity_result, supply_demand.
validated_order_blocks_for, supply_demand.fair_value_gaps_for -- the same functions
D1Context/H1SetupContext already call). This module does not extend TD-1's frozen
contracts to add such a field (that is a contract decision for a future work package,
not an adapter decision) -- see ADAPTER_COVERAGE in the status doc for the explicit
gap record.
"""
from __future__ import annotations

from typing import Optional, Tuple

from daily_routine.d1_context import build_d1_context
from daily_routine.h1_setup import build_h1_setup_context
from daily_routine.models import D1Context, H1SetupContext
from market_structure import analyze_structure
from market_structure.models import StructureResult

from .topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_M5,
    DailyContext,
    H1Context,
    M5Context,
    StructureFact,
    compute_context_id,
)

ADAPTER_FEATURE_VERSION = "TD3_CONTEXT_ADAPTER_V1"

STRUCTURE_FACT_SOURCE = "market_structure.analyze_structure"
D1_CONTEXT_SOURCE = "daily_routine.d1_context.build_d1_context"
H1_CONTEXT_SOURCE = "daily_routine.h1_setup.build_h1_setup_context"
M5_CONTEXT_SOURCE = "market_structure.analyze_structure"  # no composed M5 orchestrator exists; see module docstring


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


# --------------------------------------------------------------------------- D1

def daily_context_from_d1(
    d1: D1Context, *, parent_weekly_context_id: Optional[str] = None,
) -> Optional[DailyContext]:
    """Pure mapping from an already-built daily_routine.models.D1Context (the existing
    build_d1_context() orchestrator's own return value) into DailyContext.

    Returns None when the D1 authority itself could not establish a closed-bar
    timestamp (its own `status == "UNAVAILABLE"`, i.e. `evidence["structure"]` was
    never populated because analyze_structure() failed) -- DailyContext.bar_close_time
    is mandatory, so there is nothing honest to construct. This is a data-quality
    outcome, not an adapter defect; see ADAPTER_COVERAGE."""
    structure = d1.evidence.get("structure") if d1.evidence else None
    if structure is None:
        return None
    quality = _data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = _structure_facts(structure, TIMEFRAME_D1, STRUCTURE_FACT_SOURCE)
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
        structure_facts=facts,
    )


def build_daily_context(symbol: str, *, parent_weekly_context_id: Optional[str] = None) -> Optional[DailyContext]:
    """Orchestration convenience: calls the existing build_d1_context() (the same
    function daily_routine's own routine already calls) and adapts its result. No
    detection of any kind happens in this function -- see daily_context_from_d1()."""
    return daily_context_from_d1(build_d1_context(symbol), parent_weekly_context_id=parent_weekly_context_id)


# --------------------------------------------------------------------------- H1

def h1_context_from_sources(
    h1_setup: H1SetupContext, structure: StructureResult, *,
    parent_h4_context_id: Optional[str] = None,
) -> Optional[H1Context]:
    """Pure mapping. `h1_setup` is the existing build_h1_setup_context() result,
    consulted to confirm this really is that authority's output for this symbol --
    its own strategy-specific fields (selected_poi, current_location, alert_zone,
    midnight_open, asian session box) are deliberately NOT copied into H1Context (see
    module docstring). `structure` is a fresh analyze_structure(symbol, "H1") result --
    the SAME existing authority build_h1_setup_context() already calls internally,
    invoked here only because H1SetupContext does not retain the full StructureResult
    (documented gap, see module docstring)."""
    if h1_setup.symbol != structure.symbol:
        raise ValueError("h1_setup and structure must describe the same symbol")
    quality = _data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = _structure_facts(structure, TIMEFRAME_H1, STRUCTURE_FACT_SOURCE)
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
        structure_facts=facts,
    )


def build_h1_context(
    symbol: str, *, d1_context: Optional[D1Context] = None, parent_h4_context_id: Optional[str] = None,
) -> Optional[H1Context]:
    """Orchestration convenience: calls the existing build_h1_setup_context() (which
    itself requires a D1Context -- built via build_d1_context() if the caller doesn't
    already have one) plus one analyze_structure(symbol, "H1") call to recover fields
    the H1 orchestrator discards (see module docstring). No detection is added."""
    d1_context = d1_context or build_d1_context(symbol)
    h1_setup = build_h1_setup_context(symbol, d1_context)
    structure = analyze_structure(symbol, TIMEFRAME_H1)
    return h1_context_from_sources(h1_setup, structure, parent_h4_context_id=parent_h4_context_id)


# --------------------------------------------------------------------------- M5

def m5_context_from_structure(
    structure: StructureResult, *, parent_m15_context_id: Optional[str] = None,
) -> Optional[M5Context]:
    """Pure mapping. No composed M5 orchestrator exists in this repository (TD-0
    finding) -- market_structure.analyze_structure(symbol, "M5") IS the existing M5
    authority being adapted here, the same function D1Context/H1SetupContext already
    call at their own timeframes."""
    quality = _data_quality_for_structure(structure)
    if quality == DATA_QUALITY_DATA_ERROR:
        return None
    facts = _structure_facts(structure, TIMEFRAME_M5, STRUCTURE_FACT_SOURCE)
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
        structure_facts=facts,
    )


def build_m5_context(symbol: str, *, parent_m15_context_id: Optional[str] = None) -> Optional[M5Context]:
    """Orchestration convenience over the same analyze_structure() call used
    everywhere else in this module. No detection of any kind happens here."""
    return m5_context_from_structure(analyze_structure(symbol, TIMEFRAME_M5), parent_m15_context_id=parent_m15_context_id)
