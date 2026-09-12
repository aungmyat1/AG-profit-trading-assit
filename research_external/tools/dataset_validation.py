"""Pure dataset validation helpers -- no I/O. Used before any candle series is
trusted as research evidence (mission sections 12-13)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Sequence


@dataclass(frozen=True)
class DatasetValidationReport:
    row_count: int
    monotonic: bool
    duplicate_timestamp_count: int
    future_row_count: int
    invalid_ohlc_count: int
    first_invalid_ohlc_index: "int | None"

    @property
    def passed(self) -> bool:
        return (
            self.row_count > 0 and self.monotonic
            and self.duplicate_timestamp_count == 0
            and self.future_row_count == 0
            and self.invalid_ohlc_count == 0
        )


def _valid_ohlc(c: dict) -> bool:
    o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
    return h >= l and h >= o and h >= cl and l <= o and l <= cl


def validate_dataset(candles: Sequence[dict]) -> DatasetValidationReport:
    times = [str(c["time"]) for c in candles]
    monotonic = all(times[i] <= times[i + 1] for i in range(len(times) - 1))
    duplicate_count = len(times) - len(set(times))

    now_utc = datetime.now(timezone.utc).isoformat()
    future_count = sum(1 for t in times if t > now_utc)

    invalid_indices = [i for i, c in enumerate(candles) if not _valid_ohlc(c)]

    return DatasetValidationReport(
        row_count=len(candles),
        monotonic=monotonic,
        duplicate_timestamp_count=duplicate_count,
        future_row_count=future_count,
        invalid_ohlc_count=len(invalid_indices),
        first_invalid_ohlc_index=invalid_indices[0] if invalid_indices else None,
    )
