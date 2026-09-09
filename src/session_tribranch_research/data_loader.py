"""AG_SESSION_TRADE_V120 P4/P7/P24 -- real EURUSD M5 historical data loader for the
Sweep/Range/Trend canonical-replay research candidate.

Source: the ONE dataset already owner-approved for HISTORICAL_ANALYSIS_ONLY research use
in this repository -- config/historical_datasets/EURUSD_M5_202504211715_202607310000.yaml
(dataset_id EURUSD_M5_202504211715_202607310000, tagged SYNTHETIC_RESEARCH,
`execution.adapter.require_exchange_verified_metadata()` already refuses this tag so it
can never reach an execution path). This module verifies the manifest's own
dataset_fingerprint (sha256) against the actual source file before use -- fails closed if
they diverge, rather than silently trusting an unverified file.

Timezone: MT5-exported CSV timestamps are the broker's own wall-clock reading (NOT true
UTC) -- the exact quirk src/mt5/broker_time.py exists to correct for live MT5 API data.
Reused here VERBATIM (_largest_gap, offset_from_reopen) against this file's own weekend
reopen gap to derive the real broker UTC offset empirically from the data itself, rather
than assuming one -- consistent with how src/mt5/market_data.py converts live candles.
"""
from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from mt5.broker_time import MIN_WEEKEND_GAP, BrokerTimeError, _largest_gap, offset_from_reopen
from strategy_engine.session.candles import Candle

DATASET_ID = "EURUSD_M5_202504211715_202607310000"
DATASET_MANIFEST_PATH = os.path.join(
    "config", "historical_datasets", f"{DATASET_ID}.yaml"
)
EXPECTED_FINGERPRINT = "sha256:0c269b9aae1a610cddc87b61f30c12bcd89bcd25c7276e5406a6e36c409957e8"
SOURCE_FILE = r"D:\EURUSD_M5_202504211715_202607310000.csv"
METADATA_SOURCE = "SYNTHETIC_RESEARCH"  # matches config/historical_datasets manifest's own scope tag


class DatasetIntegrityError(RuntimeError):
    pass


def verify_dataset_fingerprint(path: str = SOURCE_FILE, expected: str = EXPECTED_FINGERPRINT) -> str:
    """Fails closed (raises DatasetIntegrityError) if the file's sha256 does not match
    the owner-approved manifest's dataset_fingerprint -- never silently proceeds on an
    unverified or since-modified file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    digest = f"sha256:{h.hexdigest()}"
    if digest != expected:
        raise DatasetIntegrityError(
            f"{path}: fingerprint {digest} does not match owner-approved manifest fingerprint {expected}"
        )
    return digest


def _parse_naive_rows(path: str) -> List[Tuple[datetime, float, float, float, float, float]]:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader)
        assert header[:6] == ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>"], header
        spread_idx = header.index("<SPREAD>") if "<SPREAD>" in header else None
        for row in reader:
            if not row:
                continue
            dt_naive = datetime.strptime(f"{row[0]} {row[1]}", "%Y.%m.%d %H:%M:%S")
            o, hi, lo, c = float(row[2]), float(row[3]), float(row[4]), float(row[5])
            spread_points = float(row[spread_idx]) if spread_idx is not None else None
            rows.append((dt_naive, o, hi, lo, c, spread_points))
    return rows


def detect_offset_from_csv(naive_times: List[datetime]) -> int:
    """Same weekly-reopen-gap method as mt5.broker_time.detect_broker_utc_offset_hours,
    applied to this file's own timestamps instead of a live MT5 fetch -- no live
    connection is available or needed for this historical-only dataset."""
    gap, reopen_idx = _largest_gap(naive_times)
    if gap < MIN_WEEKEND_GAP:
        raise BrokerTimeError(
            f"NO_WEEKEND_GAP_FOUND: largest gap in dataset was {gap}, need >= {MIN_WEEKEND_GAP}"
        )
    return offset_from_reopen(naive_times[reopen_idx])


def load_eurusd_m5_utc(
    path: str = SOURCE_FILE, verify_fingerprint: bool = True
) -> Tuple[List[Candle], int, str, List[float]]:
    """Returns (candles in TRUE UTC chronological order, detected broker_utc_offset_hours,
    verified_fingerprint). Fails closed on a fingerprint mismatch or an undetectable
    broker offset -- never silently assumes UTC==broker time."""
    if verify_fingerprint:
        fingerprint = verify_dataset_fingerprint(path)
    else:
        fingerprint = "UNVERIFIED"

    rows = _parse_naive_rows(path)
    naive_times = [r[0] for r in rows]
    offset = detect_offset_from_csv(naive_times)

    candles = [
        Candle(
            time=(t - timedelta(hours=offset)).replace(tzinfo=timezone.utc),
            open=o, high=hi, low=lo, close=c, volume=None,
        )
        for (t, o, hi, lo, c, _spread) in rows
    ]
    spreads_points = [r[5] for r in rows if r[5] is not None]

    return candles, offset, fingerprint, spreads_points
