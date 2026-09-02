"""Owner-approved historical symbol-metadata manifests (ST_LARGE_SMC_V1
REPLAY_METADATA_DECOUPLING_V1). Resolves the gap disclosed in
`docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`:
`market_structure.tiers.analyze_structure_tiers` needs `SymbolMeta.tick_size` for its
equal-level tolerance calculation (`tolerance_price = equal_level_tolerance_points *
tick_size`, `market_structure/tiers.py:147`) but historical replay has no live MT5
terminal to fetch it from.

This module does NOT infer a tick_size from test fixtures, price decimals, or current
MT5 values -- it only loads and validates an explicit, owner-approved, dataset-bound
manifest (`config/historical_datasets/*.yaml`). No manifest for a given dataset means
no historical tick_size for that dataset; callers must fail closed, never guess.

Authorization boundary (binding, from the manifest's own `metadata_scope` field):
HISTORICAL_ANALYSIS_ONLY. A `SymbolMeta` built from a manifest via `to_synthetic_symbol_meta()`
is always tagged `metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH` -- the same tag
`strategy_engine/sweep_retest/crypto_symbols.py::crypto_symbol_meta()` already uses for
exactly this reason -- so `execution.adapter.require_exchange_verified_metadata()`
(the project's existing, already-tested guard) refuses it if it ever reached an
execution path. Fields this manifest does not actually authorize (tick_value,
contract_size, volume_min/max/step, digits) are filled with inert zeros, never a
fabricated plausible-looking number -- `analyze_structure_tiers` is the manifest's only
intended consumer, and it reads `.tick_size` only (verified directly from its source).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml

from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta

from .candle_store import HistoricalDataError

REQUIRED_AUTHORITY = "OWNER_APPROVED_DATASET_MANIFEST"
REQUIRED_SCOPE = "HISTORICAL_ANALYSIS_ONLY"


class SymbolMetadataManifestError(HistoricalDataError):
    """Raised for any manifest load/validation/binding failure -- always fail closed,
    never silently fall back to a guessed or default tick_size."""


@dataclass(frozen=True)
class HistoricalSymbolMetadataManifest:
    dataset_id: str
    symbol: str
    tick_size: float
    metadata_scope: str
    authority: str
    approval_date: str
    dataset_fingerprint: str
    source_file: str

    def to_synthetic_symbol_meta(self) -> SymbolMeta:
        """Only `.tick_size` is real/authorized -- every other field is structurally
        required by the `SymbolMeta` dataclass but not authorized by this manifest
        (see module docstring) and MUST NEVER be read for anything beyond structure
        analysis's own tick_size lookup. `metadata_source=SYNTHETIC_RESEARCH` is the
        load-bearing safety tag -- see execution.adapter.require_exchange_verified_metadata()."""
        return SymbolMeta(
            symbol=self.symbol, tick_size=self.tick_size,
            tick_value=0.0, contract_size=0.0, volume_min=0.0, volume_max=0.0, volume_step=0.0,
            digits=0, point=0.0, metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH,
        )


def compute_dataset_fingerprint(path: Union[str, Path]) -> str:
    """SHA-256 over the exact raw file bytes -- deterministic, no repo-specific
    convention existed for this already (searched), so this is the smallest new
    primitive: standard `sha256:<hex>` framing, nothing project-specific invented."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _validate_tick_size(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SymbolMetadataManifestError("INVALID_TICK_SIZE", f"tick_size must be numeric, got {value!r}")
    tick = float(value)
    if not math.isfinite(tick) or tick <= 0:
        raise SymbolMetadataManifestError("INVALID_TICK_SIZE", f"tick_size must be a finite positive number, got {tick!r}")
    return tick


def load_symbol_metadata_manifest(path: Union[str, Path]) -> HistoricalSymbolMetadataManifest:
    """Loads and validates a manifest file's own internal consistency (required
    fields, authority, scope, tick_size). Does NOT check it against a live dataset --
    see `validate_manifest_for_dataset` for that binding step, which callers must
    always perform before trusting `.tick_size`."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except OSError as exc:
        raise SymbolMetadataManifestError("MANIFEST_NOT_FOUND", f"{path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SymbolMetadataManifestError("MANIFEST_MALFORMED", f"{path}: expected a YAML mapping")

    required_keys = ("dataset_id", "symbol", "tick_size", "metadata_scope", "authority",
                      "approval_date", "dataset_fingerprint", "source_file")
    missing = [k for k in required_keys if k not in raw]
    if missing:
        raise SymbolMetadataManifestError("MANIFEST_MISSING_FIELDS", f"{path}: missing {missing}")

    if raw["authority"] != REQUIRED_AUTHORITY:
        raise SymbolMetadataManifestError(
            "UNSUPPORTED_MANIFEST_AUTHORITY", f"{path}: authority={raw['authority']!r}, expected {REQUIRED_AUTHORITY!r}"
        )
    if raw["metadata_scope"] != REQUIRED_SCOPE:
        raise SymbolMetadataManifestError(
            "UNSUPPORTED_METADATA_SCOPE", f"{path}: metadata_scope={raw['metadata_scope']!r}, expected {REQUIRED_SCOPE!r}"
        )
    tick_size = _validate_tick_size(raw["tick_size"])
    if not raw["symbol"] or not isinstance(raw["symbol"], str):
        raise SymbolMetadataManifestError("INVALID_SYMBOL", f"{path}: symbol={raw['symbol']!r}")
    if not raw["dataset_fingerprint"] or not str(raw["dataset_fingerprint"]).startswith("sha256:"):
        raise SymbolMetadataManifestError("INVALID_FINGERPRINT_FORMAT", f"{path}: dataset_fingerprint={raw['dataset_fingerprint']!r}")

    return HistoricalSymbolMetadataManifest(
        dataset_id=raw["dataset_id"], symbol=raw["symbol"], tick_size=tick_size,
        metadata_scope=raw["metadata_scope"], authority=raw["authority"],
        approval_date=str(raw["approval_date"]), dataset_fingerprint=raw["dataset_fingerprint"],
        source_file=raw["source_file"],
    )


def validate_manifest_for_dataset(
    manifest: HistoricalSymbolMetadataManifest, dataset_path: Union[str, Path], expected_symbol: str,
) -> None:
    """Binds the manifest to the ACTUAL dataset file being replayed -- fails closed on
    any mismatch. Never associate metadata by symbol name alone (a different EURUSD
    export could have different provenance -- module docstring)."""
    if manifest.symbol != expected_symbol:
        raise SymbolMetadataManifestError(
            "MANIFEST_SYMBOL_MISMATCH", f"manifest symbol={manifest.symbol!r}, requested symbol={expected_symbol!r}"
        )
    actual_fingerprint = compute_dataset_fingerprint(dataset_path)
    if actual_fingerprint != manifest.dataset_fingerprint:
        raise SymbolMetadataManifestError(
            "DATASET_FINGERPRINT_MISMATCH",
            f"{dataset_path}: actual={actual_fingerprint}, manifest={manifest.dataset_fingerprint}",
        )
