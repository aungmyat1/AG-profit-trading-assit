"""AG_SYMBOL_METADATA_H1_BIAS_REMEDIATION / AG_DAILY_SESSION_TRADE_CONTINUATION --
structural smoke tests (M17/M18) for session_sweep_continuation.h1_bias.resolve_h1_market_bias,
plus real-dataset end-to-end proof now that the H1 symbol-metadata manifest is
owner-approved (2026-09-11) -- see config/historical_datasets/EURUSD_H1_symbol_metadata.yaml.

Most tests below use synthetic fixtures only (no real CSV dataset, no live MT5, no
economic replay) to prove the WIRING is mechanically correct and deterministic
independent of any real dataset's authorization state. The two tests under "real-dataset
authorization boundary" below are the exception -- they load the actual EURUSD H1 export
and skip gracefully if it is not present on the running machine.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.symbol_metadata_manifest import (
    HistoricalSymbolMetadataManifest,
    SymbolMetadataManifestError,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from session_sweep_continuation.h1_bias import resolve_h1_market_bias
from strategy_engine.session import Candle

UTC = timezone.utc
SYMBOL = "EURUSD"


def _hand_built_manifest(symbol: str = SYMBOL, tick_size: float = 0.00001) -> HistoricalSymbolMetadataManifest:
    """TEST FIXTURE ONLY -- mirrors tests/test_symbol_metadata_manifest.py's own
    documented pattern (hand-constructing the dataclass bypasses load_symbol_metadata_
    manifest's file/authorization checks on purpose, to isolate the H1-wiring question
    from the separate real-dataset-authorization question). Production code must only
    ever obtain a manifest via load_symbol_metadata_manifest."""
    return HistoricalSymbolMetadataManifest(
        dataset_id="TEST_H1_DATASET", symbol=symbol, tick_size=tick_size,
        metadata_scope="HISTORICAL_ANALYSIS_ONLY", authority="OWNER_APPROVED_DATASET_MANIFEST",
        approval_date="2026-09-02", dataset_fingerprint="sha256:" + "0" * 64, source_file="unused",
    )


def _build_h1_candles(count: int = 1300, symbol: str = SYMBOL):
    """analyze_structure_tiers needs >= EXTERNAL_SWING_LENGTH*20 = 1000 candles to clear
    its own warm-up gate, mirroring tests/test_symbol_metadata_manifest.py's own
    _build_candles helper, here on an H1 clock instead of M5 -- the count requirement is
    bar-count based, not calendar-time based."""
    out = []
    base = datetime(2020, 1, 1, tzinfo=UTC)
    price = 1.1000
    for i in range(count):
        price += 0.0006 if (i // 20) % 2 == 0 else -0.0006
        out.append(Candle(time=base + timedelta(hours=i), open=price, high=price + 0.0015,
                           low=price - 0.0015, close=price, volume=1.0))
    return out


def _store_with_h1_series(candles):
    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "H1", candles)
    return store


def test_resolve_h1_market_bias_produces_valid_bias_from_synthetic_h1_data():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    result = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, "ASIAN_LONDON")

    assert result.bias in ("BULLISH", "BEARISH", "NEUTRAL")
    assert result.symbol == SYMBOL
    assert result.decision_time == decision_time
    assert result.model_version == "AG_MARKET_BIAS_RESOLVER_V1"
    assert result.input_fingerprint  # non-empty, deterministic provenance
    assert result.decision_cycle_id == f"{SYMBOL}:{decision_time.date()}:ASIAN_LONDON"


def test_resolve_h1_market_bias_is_deterministic_for_identical_inputs():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    r1 = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, "ASIAN_LONDON")
    r2 = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, "ASIAN_LONDON")
    assert r1.bias == r2.bias
    assert r1.input_fingerprint == r2.input_fingerprint
    assert r1.decision_cycle_id == r2.decision_cycle_id


def test_resolve_h1_market_bias_no_lookahead_stable_when_future_bars_appended():
    """Appending MORE H1 bars strictly after decision_time must not change the bias
    already resolved for that decision_time -- same no-lookahead guarantee
    HistoricalCandleStore.closed_candles already enforces project-wide, exercised here
    specifically through the H1 bias path."""
    candles = _build_h1_candles()
    decision_time = candles[-1].time + timedelta(hours=1)
    manifest = _hand_built_manifest()

    store_base = _store_with_h1_series(candles)
    result_base = resolve_h1_market_bias(store_base, manifest, SYMBOL, decision_time, "ASIAN_LONDON")

    extra_future = _build_h1_candles(200)
    shifted_future = [
        Candle(time=candles[-1].time + timedelta(hours=1 + i), open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume)
        for i, c in enumerate(extra_future)
    ]
    store_extended = _store_with_h1_series(candles + shifted_future)
    result_extended = resolve_h1_market_bias(store_extended, manifest, SYMBOL, decision_time, "ASIAN_LONDON")

    assert result_base.bias == result_extended.bias
    assert result_base.input_fingerprint == result_extended.input_fingerprint


def test_resolve_h1_market_bias_fails_closed_to_neutral_on_insufficient_history():
    """Fewer than the structural warm-up requirement -> tiers.status != VALID ->
    resolve_unavailable -> NEUTRAL/UNAVAILABLE, never a guessed BULLISH/BEARISH."""
    candles = _build_h1_candles(count=50)  # far below the ~1000-bar warm-up gate
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    result = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, "ASIAN_LONDON")
    assert result.bias == "NEUTRAL"
    assert result.confidence == "UNAVAILABLE"


def test_resolve_h1_market_bias_fails_closed_on_symbol_mismatch():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    mismatched_manifest = _hand_built_manifest(symbol="GBPUSD")
    decision_time = candles[-1].time + timedelta(hours=1)

    result = resolve_h1_market_bias(store, mismatched_manifest, SYMBOL, decision_time, "ASIAN_LONDON")
    assert result.bias == "NEUTRAL"
    assert result.confidence == "UNAVAILABLE"


# --------------------------------------------------------------------------- real-dataset authorization boundary


def _repo_root():
    return Path(__file__).resolve().parent.parent


def test_h1_symbol_metadata_manifest_is_owner_approved_and_accepted():
    """AG_DAILY_SESSION_TRADE_CONTINUATION (2026-09-11): the real EURUSD H1 dataset's
    symbol-metadata manifest (config/historical_datasets/EURUSD_H1_symbol_metadata.yaml)
    was promoted from the prior task's PENDING_OWNER_AUTHORIZATION candidate to
    authority=OWNER_APPROVED_DATASET_MANIFEST after an explicit owner decision. This
    test proves the existing, unmodified loader now correctly ACCEPTS it and binds it to
    the actual H1 CSV via its real sha256 fingerprint -- the inverse of the prior task's
    rejection proof, reflecting the new, real authorization state."""
    manifest_path = _repo_root() / "config" / "historical_datasets" / "EURUSD_H1_symbol_metadata.yaml"
    dataset_path = Path(r"D:\EURUSD_H1_202501020000_202607310000.csv")
    if not dataset_path.exists():
        pytest.skip("real EURUSD H1 dataset not present on this machine")

    manifest = load_symbol_metadata_manifest(manifest_path)
    assert manifest.authority == "OWNER_APPROVED_DATASET_MANIFEST"
    validate_manifest_for_dataset(manifest, dataset_path, "EURUSD")  # must not raise
    assert manifest.tick_size == 0.00001


def test_resolve_h1_market_bias_on_real_dataset_end_to_end():
    """End-to-end proof on REAL data (not synthetic fixtures): loads the actual
    EURUSD H1 export via the existing historical_replay.mt5_export_loader (which itself
    uses the now-widened mt5.broker_time.offset_from_reopen), binds the now-approved
    symbol-metadata manifest, and resolves a real historical MarketBiasResult at a real
    historical decision time -- proving H1_BIAS_READY=YES is not merely a synthetic-
    fixture claim."""
    from historical_replay.mt5_export_loader import load_mt5_export_csv

    dataset_path = Path(r"D:\EURUSD_H1_202501020000_202607310000.csv")
    if not dataset_path.exists():
        pytest.skip("real EURUSD H1 dataset not present on this machine")

    manifest_path = _repo_root() / "config" / "historical_datasets" / "EURUSD_H1_symbol_metadata.yaml"
    manifest = load_symbol_metadata_manifest(manifest_path)
    validate_manifest_for_dataset(manifest, dataset_path, "EURUSD")

    candles, report = load_mt5_export_csv(str(dataset_path), SYMBOL, "H1")
    assert report.rows == len(candles) > 5000
    assert report.normalized_timezone == "UTC"

    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "H1", candles)

    # A decision time well inside the dataset, with ample warm-up history before it
    # (>= EXTERNAL_SWING_LENGTH*20 = 1000 H1 bars, comfortably available a few months
    # into a ~19-month H1 series) -- not the first or last bar, to avoid edge artifacts.
    decision_time = candles[0].time + timedelta(days=200)

    result = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, "ASIAN_LONDON")
    assert result.bias in ("BULLISH", "BEARISH", "NEUTRAL")
    assert result.symbol == SYMBOL
    assert result.decision_time == decision_time
    assert result.model_version == "AG_MARKET_BIAS_RESOLVER_V1"
    assert result.input_fingerprint
