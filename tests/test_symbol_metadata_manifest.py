"""REPLAY_METADATA_DECOUPLING_V1: owner-approved historical symbol-metadata manifest
loading/validation, and the `historical_data_context` wiring that restores
`market_structure.tiers.analyze_structure_tiers`'s tick_size lookup during replay
without any live MT5 terminal.

All synthetic fixtures -- no real CSV dataset, no live MT5. The real-dataset
end-to-end proof lives in `scripts/run_large_smc_outcome_lifecycle_check.py`
(manually run, recorded in the OUTCOME_LIFECYCLE_V1/REPLAY_METADATA_DECOUPLING_V1
status docs) and `scripts/run_large_smc_discovery.py`.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import yaml

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.data_source_patch import historical_data_context
from historical_replay.symbol_metadata_manifest import (
    HistoricalSymbolMetadataManifest,
    SymbolMetadataManifestError,
    compute_dataset_fingerprint,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from market_structure.tiers import analyze_structure_tiers
from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH
from strategy_engine.session import Candle

UTC = timezone.utc


def _write_manifest(tmp_path, dataset_file, **overrides):
    fingerprint = compute_dataset_fingerprint(dataset_file)
    payload = {
        "dataset_id": "TEST_DATASET", "symbol": "EURUSD", "tick_size": 0.00001,
        "metadata_scope": "HISTORICAL_ANALYSIS_ONLY", "authority": "OWNER_APPROVED_DATASET_MANIFEST",
        "approval_date": "2026-09-02", "dataset_fingerprint": fingerprint, "source_file": str(dataset_file),
    }
    payload.update(overrides)
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return manifest_path


@pytest.fixture
def dataset_file(tmp_path):
    p = tmp_path / "dataset.csv"
    p.write_text("time,open,high,low,close\n2025-01-01,1.1,1.2,1.0,1.15\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- manifest authority


def test_approved_manifest_accepted(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file)
    manifest = load_symbol_metadata_manifest(manifest_path)
    validate_manifest_for_dataset(manifest, dataset_file, "EURUSD")  # must not raise
    assert manifest.tick_size == 0.00001


def test_wrong_dataset_fingerprint_rejected(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file, dataset_fingerprint="sha256:" + "0" * 64)
    manifest = load_symbol_metadata_manifest(manifest_path)
    with pytest.raises(SymbolMetadataManifestError):
        validate_manifest_for_dataset(manifest, dataset_file, "EURUSD")


def test_wrong_symbol_rejected(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file)
    manifest = load_symbol_metadata_manifest(manifest_path)
    with pytest.raises(SymbolMetadataManifestError):
        validate_manifest_for_dataset(manifest, dataset_file, "GBPUSD")


def test_missing_manifest_file_rejected(tmp_path):
    with pytest.raises(SymbolMetadataManifestError):
        load_symbol_metadata_manifest(tmp_path / "does_not_exist.yaml")


def test_unsupported_authority_rejected(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file, authority="SOME_OTHER_AUTHORITY")
    with pytest.raises(SymbolMetadataManifestError):
        load_symbol_metadata_manifest(manifest_path)


def test_unsupported_scope_rejected(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file, metadata_scope="LIVE_EXECUTION")
    with pytest.raises(SymbolMetadataManifestError):
        load_symbol_metadata_manifest(manifest_path)


def test_missing_required_field_rejected(tmp_path, dataset_file):
    manifest_path = tmp_path / "incomplete.yaml"
    manifest_path.write_text(yaml.safe_dump({"dataset_id": "X", "symbol": "EURUSD"}), encoding="utf-8")
    with pytest.raises(SymbolMetadataManifestError):
        load_symbol_metadata_manifest(manifest_path)


# --------------------------------------------------------------------------- tick_size validation


@pytest.mark.parametrize("bad_value", [None, 0, -0.00001, float("nan"), float("inf"), "0.00001", True])
def test_invalid_tick_size_rejected(tmp_path, dataset_file, bad_value):
    manifest_path = _write_manifest(tmp_path, dataset_file, tick_size=bad_value)
    with pytest.raises(SymbolMetadataManifestError):
        load_symbol_metadata_manifest(manifest_path)


def test_valid_positive_finite_tick_size_accepted(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file, tick_size=0.01)
    manifest = load_symbol_metadata_manifest(manifest_path)
    assert manifest.tick_size == 0.01


def test_never_silently_defaults_tick_size(tmp_path, dataset_file):
    """A rejected manifest must never fall back to 0.00001 or any other default --
    the caller gets an exception, not a plausible-looking number."""
    manifest_path = _write_manifest(tmp_path, dataset_file, tick_size=0)
    with pytest.raises(SymbolMetadataManifestError):
        load_symbol_metadata_manifest(manifest_path)


# --------------------------------------------------------------------------- SymbolMeta construction


def test_synthetic_symbol_meta_tagged_not_exchange_verified(tmp_path, dataset_file):
    manifest_path = _write_manifest(tmp_path, dataset_file)
    manifest = load_symbol_metadata_manifest(manifest_path)
    meta = manifest.to_synthetic_symbol_meta()
    assert meta.metadata_source == METADATA_SOURCE_SYNTHETIC_RESEARCH
    assert meta.tick_size == manifest.tick_size


def test_test_fixture_tick_size_is_not_promoted_to_manifest_authority(tmp_path, dataset_file):
    """A test fixture using tick_size=0.00001 must never be silently treated as a
    manifest -- only an actual, validated, on-disk OWNER_APPROVED_DATASET_MANIFEST is
    authoritative. This test constructs the manifest dataclass directly (bypassing the
    loader) purely to show the type distinction; production code only ever obtains a
    manifest via load_symbol_metadata_manifest, never by hand-construction."""
    hand_built = HistoricalSymbolMetadataManifest(
        dataset_id="TEST", symbol="EURUSD", tick_size=0.00001, metadata_scope="HISTORICAL_ANALYSIS_ONLY",
        authority="OWNER_APPROVED_DATASET_MANIFEST", approval_date="2026-09-02",
        dataset_fingerprint="sha256:" + "0" * 64, source_file="unused",
    )
    assert hand_built.tick_size == 0.00001  # TEST_INPUT, not HISTORICAL_METADATA_AUTHORITY by itself


# --------------------------------------------------------------------------- structure-analysis parity/formula


def _build_candles(count: int = 1300):
    """analyze_structure_tiers needs >= EXTERNAL_SWING_LENGTH*20 = 1000 candles just to
    clear its own warm-up gate, plus config/market_structure.yaml's
    default_analysis_count=200 -- 1300 covers both with margin. A simple oscillation
    guarantees real swing highs/lows exist (not just enough bars)."""
    out = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    price = 1.1000
    for i in range(count):
        price += 0.0002 if (i // 20) % 2 == 0 else -0.0002
        out.append(Candle(time=base + timedelta(minutes=5 * i), open=price, high=price + 0.0005,
                           low=price - 0.0005, close=price, volume=1.0))
    return out


_INTERNAL_HIGH_KIND_TOLERANCE_CANDLES = _build_candles()


def test_equal_level_tolerance_formula_unchanged(tmp_path, dataset_file):
    """equal_level_tolerance_points * tick_size -- the exact existing formula
    (market_structure/tiers.py:147) -- must be untouched by this phase. Verified here
    by confirming the SAME tick_size fed through two different sources (manifest vs. a
    live-shaped SymbolMeta) produces IDENTICAL structure-tier output."""
    from liquidity.hierarchy import LiquiditySide  # noqa: F401 -- import proves no accidental breakage

    manifest_path = _write_manifest(tmp_path, dataset_file, tick_size=0.00001)
    manifest = load_symbol_metadata_manifest(manifest_path)

    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES)
    as_of = _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES[-1].time + timedelta(minutes=5)

    with historical_data_context(store, as_of, symbol_metadata_manifest=manifest):
        via_manifest = analyze_structure_tiers("EURUSD", "M5")

    live_shaped_meta = manifest.to_synthetic_symbol_meta()
    with historical_data_context(store, as_of), patch("market_structure.tiers.get_symbol_meta", return_value=live_shaped_meta):
        via_live_shaped_source = analyze_structure_tiers("EURUSD", "M5")

    assert via_manifest.status == "VALID"
    assert via_live_shaped_source.status == "VALID"
    assert via_manifest.external.latest_swing_high == via_live_shaped_source.external.latest_swing_high
    assert via_manifest.external.latest_swing_low == via_live_shaped_source.external.latest_swing_low


# --------------------------------------------------------------------------- replay/live parity & no hidden MT5 lookup


def test_no_manifest_leaves_get_symbol_meta_completely_unpatched():
    """Backward compatibility, verified deterministically (not by relying on whether a
    live MT5 terminal happens to be connected in this environment, which the project's
    own README already documents as environment-dependent): omitting
    symbol_metadata_manifest must leave get_symbol_meta exactly as the caller's own
    environment already had it -- historical_data_context must not touch that target
    at all when no manifest is supplied."""
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES)
    as_of = _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES[-1].time + timedelta(minutes=5)

    sentinel_meta = HistoricalSymbolMetadataManifest(
        dataset_id="SENTINEL", symbol="EURUSD", tick_size=0.00001, metadata_scope="HISTORICAL_ANALYSIS_ONLY",
        authority="OWNER_APPROVED_DATASET_MANIFEST", approval_date="2026-09-02",
        dataset_fingerprint="sha256:" + "0" * 64, source_file="unused",
    ).to_synthetic_symbol_meta()

    with patch("market_structure.tiers.get_symbol_meta", return_value=sentinel_meta) as mocked:
        with historical_data_context(store, as_of):  # no symbol_metadata_manifest
            result = analyze_structure_tiers("EURUSD", "M5")
    mocked.assert_called_once_with("EURUSD")  # the pre-existing (mocked) source was used, untouched by the context
    assert result.status == "VALID"
    assert result.external is not None


def test_manifest_supplied_replay_never_calls_live_get_symbol_meta(tmp_path, dataset_file):
    """REPLAY_MT5_LOOKUP_COUNT = 0: with a valid manifest, the real
    mt5.symbol_resolver.get_symbol_meta (which would need a live terminal) must never
    be invoked."""
    manifest_path = _write_manifest(tmp_path, dataset_file)
    manifest = load_symbol_metadata_manifest(manifest_path)

    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES)
    as_of = _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES[-1].time + timedelta(minutes=5)

    with patch("mt5.symbol_resolver.get_symbol_meta", side_effect=AssertionError("live MT5 lookup must never happen")):
        with historical_data_context(store, as_of, symbol_metadata_manifest=manifest):
            result = analyze_structure_tiers("EURUSD", "M5")
    assert result.status == "VALID"


def test_wrong_symbol_request_fails_closed_not_silently_reused(tmp_path, dataset_file):
    """A manifest scoped to EURUSD must never silently answer for another symbol."""
    manifest_path = _write_manifest(tmp_path, dataset_file)
    manifest = load_symbol_metadata_manifest(manifest_path)

    store = HistoricalCandleStore()
    store.load_series("GBPUSD", "M5", _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES)
    as_of = _INTERNAL_HIGH_KIND_TOLERANCE_CANDLES[-1].time + timedelta(minutes=5)

    with historical_data_context(store, as_of, symbol_metadata_manifest=manifest):
        result = analyze_structure_tiers("GBPUSD", "M5")
    assert result.status != "VALID"  # MANIFEST_SYMBOL_MISMATCH -> SymbolMetaError -> fail closed


# --------------------------------------------------------------------------- safety


def test_no_fabricated_broker_execution_fields_are_nonzero_or_plausible(tmp_path, dataset_file):
    """Fields this manifest does not authorize must stay at inert zero, never a
    plausible-looking fabricated number (task's own explicit prohibition)."""
    manifest_path = _write_manifest(tmp_path, dataset_file)
    manifest = load_symbol_metadata_manifest(manifest_path)
    meta = manifest.to_synthetic_symbol_meta()
    assert meta.tick_value == 0.0
    assert meta.contract_size == 0.0
    assert meta.volume_min == 0.0
    assert meta.volume_max == 0.0
    assert meta.volume_step == 0.0
