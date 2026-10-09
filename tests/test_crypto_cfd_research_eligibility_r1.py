"""Strategy-blind Crypto-CFD research eligibility tests.

Fixtures are local immutable R2 RawDataset objects. No broker, MT5, strategy replay,
profitability calculation, C001 call, partition creation, or HOLDOUT read occurs here.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from edge_discovery.dataset_ledger import DatasetAccessLedger
from edge_discovery.ingestion import OhlcBar, RawDataset, sha256_of_file
from edge_discovery.models import load_manifest
from edge_discovery.research_eligibility import (
    AUTHORITATIVE_RAW_SHA256, ELIGIBILITY_POLICY_ID, EligibilityError, EligibilityReason,
    ResearchWindowEligibility, derive_complete_timeframe, freeze_eligibility_manifest,
)

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
C001 = load_manifest(ROOT / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml")


def _bars(day: int, *, count: int = 288, missing: set[int] | None = None,
          duplicate_index: int | None = None, invalid_index: int | None = None,
          synthetic_index: int | None = None, base: float = 100.0) -> list[OhlcBar]:
    missing = missing or set()
    start = datetime(2026, 1, day, tzinfo=UTC)
    result = []
    for index in range(count):
        if index in missing:
            continue
        timestamp = start + timedelta(minutes=5 * index)
        if duplicate_index is not None and index == duplicate_index:
            timestamp = start + timedelta(minutes=5 * (index - 1))
        low, high = base - 1.0, base + 1.0
        if invalid_index == index:
            high = base - 2.0
        result.append(OhlcBar(
            time=timestamp, open=base, high=high, low=low, close=base + 0.25,
            volume=1.0, synthetic=(synthetic_index == index),
        ))
    return result


def _dataset(symbol: str, bars: list[OhlcBar], *, sha: str = "fixture-sha",
             asset_class: str = "CRYPTO_CFD") -> RawDataset:
    return RawDataset(
        dataset_id=f"RAW_{symbol}_ELIGIBILITY_FIXTURE", source_path=Path(f"/{symbol}.parquet"),
        sha256=sha, symbol=symbol, asset_class=asset_class, timeframe="M5", broker="TEST",
        environment="TEST", timestamp_normalization={
            "normalized_timezone": "UTC", "normalization_complete": True,
            "timestamp_convention": "OPEN_TIME",
        }, schema_columns=("timestamp", "open", "high", "low", "close"),
        declared_row_count=len(bars), declared_coverage={}, bars=tuple(bars),
    )


def _engine(symbol: str, bars: list[OhlcBar], **kwargs) -> ResearchWindowEligibility:
    return ResearchWindowEligibility(
        _dataset(symbol, bars, **kwargs), expected_sha256={symbol: kwargs.get("sha", "fixture-sha")},
    )


def test_complete_288_bar_reference_day_is_eligible():
    record = _engine("BTCUSD", _bars(2)).reference_day("2026-01-02")
    assert record.eligible
    assert record.reasons == (EligibilityReason.ELIGIBLE,)
    assert record.bar_count == 288 and record.gap_dependency is False


def test_eligibility_cannot_reclassify_raw_unknown_gap_quality():
    engine = _engine("BTCUSD", _bars(2))
    assert engine.build_manifest().raw_data_quality == "BLOCKED_UNKNOWN_GAPS"
    with pytest.raises(EligibilityError, match="raw quality may not be reclassified"):
        engine.build_manifest("PASS")


def test_287_bar_reference_day_is_quarantined():
    record = _engine("BTCUSD", _bars(2, missing={120})).reference_day("2026-01-02")
    assert not record.eligible
    assert EligibilityReason.INCOMPLETE_REFERENCE_DAY in record.reasons
    assert EligibilityReason.UNKNOWN_GAP_REFERENCE_DAY in record.reasons
    assert record.gap_dependency is True


def test_duplicate_timestamp_is_quarantined():
    record = _engine("BTCUSD", _bars(2, duplicate_index=120)).reference_day("2026-01-02")
    assert not record.eligible
    assert EligibilityReason.DUPLICATE_TIMESTAMP in record.reasons


def test_invalid_ohlc_is_quarantined():
    record = _engine("BTCUSD", _bars(2, invalid_index=120)).reference_day("2026-01-02")
    assert not record.eligible
    assert EligibilityReason.INVALID_OHLC in record.reasons


def test_unknown_gap_in_reference_day_is_quarantined_not_reclassified():
    record = _engine("BTCUSD", _bars(2, missing={121})).reference_day("2026-01-02")
    assert not record.eligible
    assert EligibilityReason.UNKNOWN_GAP_REFERENCE_DAY in record.reasons
    assert EligibilityReason.NON_CONTIGUOUS_M5 in record.reasons


def test_complete_reference_but_gap_in_observation_window_is_rejected():
    bars = _bars(1) + _bars(2, missing={30})
    engine = _engine("BTCUSD", bars)
    assert engine.reference_day("2026-01-01").eligible
    window = engine.observation_window(
        datetime(2026, 1, 2, 2, 0, tzinfo=UTC), datetime(2026, 1, 2, 3, 0, tzinfo=UTC),
    )
    assert not window.eligible
    assert EligibilityReason.UNKNOWN_GAP_OBSERVATION_WINDOW in window.reasons
    assert window.gap_dependency is True


def test_unrelated_future_gap_does_not_invalidate_earlier_clean_window():
    bars = _bars(1) + _bars(2) + _bars(3, missing={40})
    engine = _engine("BTCUSD", bars)
    early = engine.observation_window(
        datetime(2026, 1, 2, 0, 0, tzinfo=UTC), datetime(2026, 1, 2, 23, 55, tzinfo=UTC),
    )
    assert early.eligible
    assert engine.reference_day("2026-01-03").eligible is False


def test_exact_m15_derivation_requires_three_consecutive_m5_bars():
    bars = [
        OhlcBar(datetime(2026, 1, 1, 0, minute, tzinfo=UTC), o, h, l, c, 1.0)
        for minute, o, h, l, c in ((0, 10, 12, 9, 11), (5, 11, 15, 10, 14), (10, 14, 16, 13, 13))
    ]
    derived = derive_complete_timeframe(bars, "M15")
    assert len(derived) == 1
    assert (derived[0].time, derived[0].open, derived[0].high, derived[0].low, derived[0].close) == (
        datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 10, 16, 9, 13,
    )


def test_missing_m15_constituent_prevents_authoritative_aggregate():
    bars = _bars(1, count=3, missing={1})
    assert derive_complete_timeframe(bars, "M15") == ()


def test_exact_h1_derivation_requires_twelve_consecutive_m5_bars():
    bars = _bars(1, count=12)
    derived = derive_complete_timeframe(bars, "H1")
    assert len(derived) == 1 and derived[0].time == datetime(2026, 1, 1, tzinfo=UTC)


def test_missing_h1_constituent_prevents_authoritative_aggregate():
    bars = _bars(1, count=12, missing={5})
    assert derive_complete_timeframe(bars, "H1") == ()


def test_d1_requires_exactly_288_valid_m5_bars():
    assert len(derive_complete_timeframe(_bars(1), "D1")) == 1
    assert derive_complete_timeframe(_bars(1, missing={287}), "D1") == ()


def test_raw_hashes_remain_authoritative_and_raw_file_is_not_modified(tmp_path):
    assert AUTHORITATIVE_RAW_SHA256 == {
        "BTCUSD": "ea0216b3431c8043537fd0a4cba9d57a7cf721f8d21656c2d90bb8a22468d3be",
        "ETHUSD": "1a2bd9429e14d0815210ae7913e130213d7c3b00c1608ec3025c333f06f5f713",
    }
    raw = tmp_path / "BTCUSD_M5_RAW.parquet"
    raw.write_bytes(b"immutable-fixture")
    before = sha256_of_file(raw)
    _engine("BTCUSD", _bars(1)).build_manifest()
    assert sha256_of_file(raw) == before


def test_eligibility_ignores_profitability_values_and_is_hash_reproducible(tmp_path):
    # Identical timestamps/validity but radically different valid OHLC values must
    # produce the same eligibility facts. Both datasets intentionally carry the same
    # fixture source identity because this is a dependency-isolation unit test.
    low_price = _bars(1, base=10.0)
    high_price = _bars(1, base=100000.0)
    first = _engine("BTCUSD", low_price).build_manifest()
    second = _engine("BTCUSD", high_price).build_manifest()
    assert first.manifest_sha256 == second.manifest_sha256
    frozen = freeze_eligibility_manifest(first, tmp_path / "eligibility.json")
    assert freeze_eligibility_manifest(first, tmp_path / "eligibility.json").manifest_sha256 == frozen.manifest_sha256
    assert ELIGIBILITY_POLICY_ID == "CRYPTO_CFD_RESEARCH_WINDOW_ELIGIBILITY_V1"


def test_holdout_remains_inaccessible_to_strategy_and_eligibility_never_requests_it(tmp_path):
    ledger = DatasetAccessLedger(tmp_path / "ledger.jsonl")
    denied = ledger.request_fast_screen_access(C001, "HOLDOUT", "HOLDOUT", "FAST_SCREEN_HOLDOUT")
    assert not denied.granted
    assert ledger.holdout_accessed_by_c001_fast_screen() is False
    # Building eligibility works without a ledger object and cannot request a partition.
    assert _engine("BTCUSD", _bars(1)).build_manifest().raw_data_quality == "BLOCKED_UNKNOWN_GAPS"


def test_btc_eth_isolation_and_cfd_perpetual_substitution_rejection():
    btc = _engine("BTCUSD", _bars(1)).build_manifest()
    eth = _engine("ETHUSD", _bars(1)).build_manifest()
    assert btc.symbol == "BTCUSD" and eth.symbol == "ETHUSD"
    assert btc.source_dataset_id != eth.source_dataset_id
    with pytest.raises(EligibilityError, match="INSUFFICIENT_DATA"):
        ResearchWindowEligibility(
            _dataset("BTCUSD", _bars(1), asset_class="CRYPTO_USDT_PERP"),
            expected_sha256={"BTCUSD": "fixture-sha"},
        )


def test_pr32_local_export_adapter_feeds_r2_rawdataset_without_reclassifying_gap(tmp_path):
    import pandas as pd

    raw_path = tmp_path / "BTCUSD_M5_RAW.parquet"
    records = [{
        "source_timestamp": bar.time.isoformat(), "timestamp_utc": bar.time,
        "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
        "tick_volume": bar.volume,
    } for bar in _bars(1, missing={20})]
    pd.DataFrame(records).to_parquet(raw_path, index=False)
    digest = sha256_of_file(raw_path)
    provenance = tmp_path / "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json"
    provenance.write_text(__import__("json").dumps({
        "schema": "AG_CRYPTO_CFD_RAW_PROVENANCE_V1",
        "datasets": [{
            "dataset_id": "PR32_BTC", "file": raw_path.name, "sha256": digest,
            "canonical_symbol": "BTCUSD", "asset_class": "CRYPTO_CFD", "timeframe": "M5",
            "broker": "TEST", "environment": "TEST", "row_count": len(records),
            "first_timestamp_utc": records[0]["timestamp_utc"].isoformat(),
            "last_timestamp_utc": records[-1]["timestamp_utc"].isoformat(),
        }],
    }), encoding="utf-8")
    from edge_discovery.pr32_dataset_adapter import load_pr32_raw_dataset
    raw = load_pr32_raw_dataset(raw_path, provenance, "BTCUSD", expected_hashes={"BTCUSD": digest})
    eligibility = ResearchWindowEligibility(raw, expected_sha256={"BTCUSD": digest})
    assert EligibilityReason.UNKNOWN_GAP_REFERENCE_DAY in eligibility.reference_day("2026-01-01").reasons
    assert sha256_of_file(raw_path) == digest


def test_authoritative_hash_mismatch_fails_closed():
    with pytest.raises(EligibilityError, match="RAW_HASH_MISMATCH"):
        ResearchWindowEligibility(_dataset("BTCUSD", _bars(1)), expected_sha256={"BTCUSD": "another-hash"})
