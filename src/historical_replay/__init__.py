"""SMC_3X3_HISTORICAL_VALIDATION_V1 -- replay/backtest research layer built around the
frozen SMC_CONDITIONAL_ENTRY_V2 / SMC_ASSISTANT_RUNTIME_V1 engines. See
docs/specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md.
"""
from .candle_store import HistoricalCandleStore, HistoricalDataError, TIMEFRAME_MINUTES, timeframe_duration
from .data_source_patch import historical_data_context
from .mt5_export_loader import GapReport, IngestionError, IngestionReport, load_mt5_export_csv
from .resampler import resample, resample_broker_aligned
from .symbol_metadata_manifest import (
    HistoricalSymbolMetadataManifest,
    SymbolMetadataManifestError,
    compute_dataset_fingerprint,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)

__all__ = [
    "HistoricalCandleStore", "HistoricalDataError", "TIMEFRAME_MINUTES", "timeframe_duration",
    "historical_data_context",
    "load_mt5_export_csv", "IngestionError", "IngestionReport", "GapReport",
    "resample", "resample_broker_aligned",
    "HistoricalSymbolMetadataManifest", "SymbolMetadataManifestError",
    "compute_dataset_fingerprint", "load_symbol_metadata_manifest", "validate_manifest_for_dataset",
]
