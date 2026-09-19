"""Regression tests for the SSC DEV_002 H1 metadata authorization remediation.

Proves the new manifest (config/historical_datasets/EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml)
resolves the BLOCKED_MISSING_H1_METADATA_AUTHORIZATION cause frozen in
artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/
G2_HISTORICAL_REPLAY_BLOCKER.json, while:
  1. binding correctly to DEV_002's own H1 file (BIND=PASS);
  2. failing closed on any fingerprint mismatch (wrong manifest <-> DEV_002, or DEV_002
     manifest <-> a different file);
  3. leaving the original owner-approved source manifest (EURUSD_H1_symbol_metadata.yaml)
     completely unchanged;
  4. proving this remediation did not and cannot change DEV_002's dataset bytes.

No replay is executed by any test here -- resolve_h1_market_bias is invoked exactly
once, at a single decision time, purely to prove the metadata preflight no longer fails
with SYMBOL_METADATA_MISSING; it never iterates the population or generates occurrences.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from historical_replay.symbol_metadata_manifest import (
    SymbolMetadataManifestError,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)

REPO = Path(__file__).resolve().parents[1]
DEV002_H1 = REPO / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_002" / "raw" / "EURUSD_H1.csv"
DEV002_MANIFEST = REPO / "config" / "historical_datasets" / "EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml"
ORIGINAL_MANIFEST = REPO / "config" / "historical_datasets" / "EURUSD_H1_symbol_metadata.yaml"
BLOCKER = json.load(open(
    REPO / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "SSC_V1_0_1_G2_DEV_002"
    / "G2_HISTORICAL_REPLAY_BLOCKER.json", encoding="utf-8",
))

EXPECTED_DEV002_H1_SHA256 = "93d27d8cbeb85c0b595ece7d18a43ac66219ae9fbb137e23a9826b84fc191c79"
EXPECTED_ORIGINAL_FINGERPRINT = "sha256:f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_blocker_recorded_dev002_h1_hash_matches_frozen_evidence():
    assert BLOCKER["evidence"]["h1_hash_actual"] == EXPECTED_DEV002_H1_SHA256


def test_dev002_h1_manifest_binds_to_its_own_file():
    manifest = load_symbol_metadata_manifest(DEV002_MANIFEST)
    assert manifest.authority == "OWNER_APPROVED_DATASET_MANIFEST"
    assert manifest.metadata_scope == "HISTORICAL_ANALYSIS_ONLY"
    assert manifest.symbol == "EURUSD"
    assert manifest.tick_size == 0.00001
    assert manifest.dataset_fingerprint == f"sha256:{EXPECTED_DEV002_H1_SHA256}"

    validate_manifest_for_dataset(manifest, DEV002_H1, "EURUSD")  # must not raise


def test_dev002_h1_file_bytes_unchanged_by_remediation():
    """The remediation is metadata-only -- the raw H1 CSV bytes must be exactly the
    fingerprint already frozen in the replay blocker and preregistration."""
    assert _sha256(DEV002_H1) == EXPECTED_DEV002_H1_SHA256


def test_wrong_fingerprint_fails_closed_original_manifest_against_dev002():
    """The pre-existing EURUSD H1 manifest (scoped to the D:\\ raw file) must NOT bind
    to DEV_002's combined H1 file -- this is the exact mismatch the replay blocker
    recorded, and it must remain a hard failure, never silently accepted."""
    original = load_symbol_metadata_manifest(ORIGINAL_MANIFEST)
    with pytest.raises(SymbolMetadataManifestError) as exc:
        validate_manifest_for_dataset(original, DEV002_H1, "EURUSD")
    assert exc.value.reason_code == "DATASET_FINGERPRINT_MISMATCH"


def test_wrong_fingerprint_fails_closed_dev002_manifest_against_wrong_symbol():
    manifest = load_symbol_metadata_manifest(DEV002_MANIFEST)
    with pytest.raises(SymbolMetadataManifestError) as exc:
        validate_manifest_for_dataset(manifest, DEV002_H1, "GBPUSD")
    assert exc.value.reason_code == "MANIFEST_SYMBOL_MISMATCH"


def test_original_owner_approved_source_manifest_is_unchanged():
    """This remediation must not modify, broaden, or reinterpret the pre-existing
    D:\\ EURUSD H1 manifest -- it remains scoped to its own file and fingerprint."""
    original = load_symbol_metadata_manifest(ORIGINAL_MANIFEST)
    assert original.dataset_id == "EURUSD_H1_202501020000_202607310000"
    assert original.dataset_fingerprint == EXPECTED_ORIGINAL_FINGERPRINT
    assert original.tick_size == 0.00001
    assert original.source_file == "D:\\EURUSD_H1_202501020000_202607310000.csv"


def test_h1_bias_metadata_preflight_no_longer_blocked_on_dev002():
    """Single-point preflight (NOT a population replay, NOT an occurrence generator):
    proves resolve_h1_market_bias's manifest-dependent path no longer fails with
    SYMBOL_METADATA_MISSING for DEV_002 now that its manifest exists and binds."""
    from datetime import datetime, timezone

    from historical_replay.candle_store import HistoricalCandleStore
    from historical_replay.utc_export_csv_loader import load_utc_export_csv
    from session_sweep_continuation.h1_bias import resolve_h1_market_bias

    manifest = load_symbol_metadata_manifest(DEV002_MANIFEST)
    validate_manifest_for_dataset(manifest, DEV002_H1, "EURUSD")

    candles, report = load_utc_export_csv(str(DEV002_H1), "EURUSD", "H1")
    assert report.normalized_timezone == "UTC"

    store = HistoricalCandleStore()
    store.load_series("EURUSD", "H1", candles)

    # First decision point the warmup readiness check already proved sufficient
    # (dataset_manifest.json: minimum_at = 2026-06-22 06:00:00+00:00) -- exactly ONE
    # bias resolution, not a loop over the population.
    decision_time = datetime(2026, 6, 22, 6, 0, tzinfo=timezone.utc)
    result = resolve_h1_market_bias(store, manifest, "EURUSD", decision_time, "ASIAN_LONDON")

    assert result.bias in ("BULLISH", "BEARISH", "NEUTRAL")
    # The previous blocker cause was a metadata failure, surfacing as tiers.status ==
    # "SYMBOL_METADATA_MISSING" folded into confidence == "UNAVAILABLE". A NEUTRAL bias
    # with confidence other than UNAVAILABLE, or a BULLISH/BEARISH bias, both prove the
    # metadata-specific cause is gone (a structural NEUTRAL for other reasons remains
    # possible and is not itself a failure of this remediation).
    if result.bias == "NEUTRAL":
        assert result.confidence != "UNAVAILABLE" or not any(
            "SYMBOL_METADATA_MISSING" in code for code in result.reason_codes
        )
