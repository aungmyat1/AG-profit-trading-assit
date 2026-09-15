"""AG SSC HYP_002 P2 -- closes the thinner-than-requested regression coverage identified
in the Stage-2 Attempt-2 report: duplicate/invalid/unordered/non-finite candles must
never reach `historical_replay.warmup_readiness.closed_h1_bar_count`, because
`load_utc_export_csv` rejects them at the ingestion boundary before any Candle object is
constructed. Tests the real ingestion -> readiness boundary (not a reimplementation of
the loader's own validation logic).
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from historical_replay.mt5_export_loader import IngestionError
from historical_replay.utc_export_csv_loader import load_utc_export_csv
from historical_replay.warmup_readiness import closed_h1_bar_count, sufficient_h1_warmup

HEADER = "timestamp_utc,open,high,low,close,tick_volume\n"


def _write_csv(rows: str) -> str:
    path = tempfile.mktemp(suffix=".csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER + rows)
    return path


def _load(path: str):
    try:
        return load_utc_export_csv(path, "EURUSD", "H1")
    finally:
        os.remove(path)


VALID_ROWS = "\n".join(
    f"2026-01-0{d} {h:02d}:00:00,1.1000,1.1010,1.0990,1.1005,10"
    for d in (1, 2) for h in range(0, 5)
) + "\n"


def test_duplicate_timestamp_rejected_at_ingestion_never_reaches_readiness_counter():
    rows = VALID_ROWS + "2026-01-01 00:00:00,1.1000,1.1010,1.0990,1.1005,10\n"
    path = _write_csv(rows)
    with pytest.raises(IngestionError) as exc:
        _load(path)
    assert exc.value.reason_code == "DUPLICATE_OR_UNORDERED_TIMESTAMP"


def test_unordered_timestamp_rejected_at_ingestion_fail_closed():
    rows = (
        "2026-01-01 02:00:00,1.1000,1.1010,1.0990,1.1005,10\n"
        "2026-01-01 01:00:00,1.1000,1.1010,1.0990,1.1005,10\n"
    )
    path = _write_csv(rows)
    with pytest.raises(IngestionError) as exc:
        _load(path)
    assert exc.value.reason_code == "DUPLICATE_OR_UNORDERED_TIMESTAMP"


def test_invalid_ohlc_rejected_at_ingestion_never_reaches_readiness_counter():
    # high < low -- physically impossible candle.
    rows = VALID_ROWS + "2026-01-02 05:00:00,1.1000,1.0500,1.1500,1.1005,10\n"
    path = _write_csv(rows)
    with pytest.raises(IngestionError) as exc:
        _load(path)
    assert exc.value.reason_code == "INVALID_OHLC"


def test_non_finite_ohlc_rejected_at_ingestion_fail_closed():
    # All-infinite OHLC satisfies h>=max(o,c) and l<=min(o,c) and h>=l trivially, so it
    # must be caught by an explicit finiteness check, not the OHLC-ordering check alone.
    rows = VALID_ROWS + "2026-01-02 05:00:00,inf,inf,inf,inf,10\n"
    path = _write_csv(rows)
    with pytest.raises(IngestionError) as exc:
        _load(path)
    assert exc.value.reason_code == "NON_FINITE_OHLC"


def test_nan_ohlc_rejected_at_ingestion_fail_closed():
    rows = VALID_ROWS + "2026-01-02 05:00:00,nan,nan,nan,nan,10\n"
    path = _write_csv(rows)
    with pytest.raises(IngestionError) as exc:
        _load(path)
    assert exc.value.reason_code == "NON_FINITE_OHLC"


def test_rejected_file_produces_zero_candles_for_readiness_purposes():
    # An ingestion-rejected file must never silently degrade to "fewer bars" -- it must
    # raise, so no caller can accidentally treat a corrupted file as valid-but-thin data
    # and evaluate readiness against a partial/garbage candle list.
    rows = VALID_ROWS + "2026-01-01 00:00:00,1.1000,1.1010,1.0990,1.1005,10\n"
    path = _write_csv(rows)
    with pytest.raises(IngestionError):
        _load(path)
    # (no candles list is ever produced to pass into closed_h1_bar_count)


def test_only_clean_ingested_candles_reach_the_readiness_counter():
    path = _write_csv(VALID_ROWS)
    candles, report = _load(path)
    as_of = candles[-1].time + timedelta(hours=1)
    assert closed_h1_bar_count(candles, as_of) == len(candles) == 10
    assert sufficient_h1_warmup(candles, as_of, required_bars=10)
    assert not sufficient_h1_warmup(candles, as_of, required_bars=11)

