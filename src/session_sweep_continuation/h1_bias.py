"""AG_SYMBOL_METADATA_H1_BIAS_REMEDIATION -- historical H1 MarketBiasResult resolution
for ST_SESSION_SWEEP_CONTINUATION_V1.

This module wires the ALREADY-EXISTING, strategy-neutral historical-replay pipeline
(discovered by audit, not reinvented):

  H1 candles (HistoricalCandleStore)
  + HistoricalSymbolMetadataManifest (historical_replay/symbol_metadata_manifest.py)
        -> historical_data_context(..., symbol_metadata_manifest=manifest)
        -> market_structure.tiers.analyze_structure_tiers(symbol, "H1")
        -> market_intelligence.bias_resolver.resolve_from_structure_tiers(tiers, ..., timeframe="H1")
        -> MarketBiasResult

No new metadata resolver, no new structure-tier analyzer, no new bias resolver was
written for this -- all three already exist and are already strategy-neutral
(historical_replay/data_source_patch.py's own docstring: "market_structure/tiers.py is
currently the only historical-replay consumer of get_symbol_meta" -- ST_LARGE_SMC_V1
already depends on this same mechanism, see strategies/ST_LARGE_SMC_V1.yaml's
target_model REPLAY_COMPATIBILITY caveat). This module is a THIN orchestration
function only: load a manifest, validate it against the actual dataset file, run the
pipeline, return one MarketBiasResult.

Authorization boundary (unchanged from the mechanism it wires): `manifest` must be an
already-loaded `HistoricalSymbolMetadataManifest` with `authority ==
"OWNER_APPROVED_DATASET_MANIFEST"` -- `load_symbol_metadata_manifest` enforces this
and raises `SymbolMetadataManifestError` for anything else (candidate/pending
manifests included). This module does not, and cannot, grant that authorization --
see config/historical_datasets/EURUSD_H1_symbol_metadata_candidate.yaml (status
PENDING_OWNER_AUTHORIZATION) for the real EURUSD H1 dataset's current state.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Union

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.data_source_patch import historical_data_context
from historical_replay.symbol_metadata_manifest import (
    HistoricalSymbolMetadataManifest,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from market_intelligence.bias_resolver import resolve_from_structure_tiers, resolve_unavailable
from market_intelligence.models import MarketBiasResult
from market_structure.tiers import analyze_structure_tiers

H1_TIMEFRAME = "H1"


def load_and_validate_h1_manifest(
    manifest_path: Union[str, Path], dataset_path: Union[str, Path], symbol: str,
) -> HistoricalSymbolMetadataManifest:
    """Loads an H1 symbol-metadata manifest and binds it to the actual dataset file
    being replayed. Raises SymbolMetadataManifestError (fail closed) for anything
    unauthorized, malformed, or mismatched -- never returns a partially-trusted
    manifest. Callers must not catch this exception to substitute a guessed tick_size."""
    manifest = load_symbol_metadata_manifest(manifest_path)
    validate_manifest_for_dataset(manifest, dataset_path, symbol)
    return manifest


def resolve_h1_market_bias(
    h1_store: HistoricalCandleStore,
    manifest: HistoricalSymbolMetadataManifest,
    symbol: str,
    decision_time: datetime,
    session_pair: str,
) -> MarketBiasResult:
    """One frozen MarketBiasResult for exactly (symbol, decision_time, session_pair),
    computed from H1 bars closed strictly at or before decision_time (no-lookahead
    enforced by HistoricalCandleStore.closed_candles' own closure check, unchanged and
    reused here, not reimplemented) and the manifest-authorized tick_size (never a
    hardcoded/guessed one -- historical_data_context raises SymbolMetaError, mapped to
    TieredStructureResult.status="SYMBOL_METADATA_MISSING", if the manifest is missing
    or scoped to a different symbol; resolve_unavailable then folds that into a fail-
    closed NEUTRAL/UNAVAILABLE MarketBiasResult, exactly like every other missing-
    evidence case in market_intelligence.bias_resolver -- never a guessed direction).

    This function performs no I/O of its own beyond what analyze_structure_tiers
    already does through the patched get_latest_candles/get_symbol_meta (both
    redirected to h1_store/manifest for the duration of the `with` block) -- no
    live MT5 connection is ever opened or required."""
    with historical_data_context(h1_store, decision_time, symbol_metadata_manifest=manifest):
        tiers = analyze_structure_tiers(symbol, H1_TIMEFRAME)

    if tiers.status != "VALID":
        return resolve_unavailable(symbol, decision_time, session_pair, f"H1_TIERED_STRUCTURE_STATUS={tiers.status}")

    return resolve_from_structure_tiers(tiers, symbol, decision_time, session_pair, timeframe=H1_TIMEFRAME)
