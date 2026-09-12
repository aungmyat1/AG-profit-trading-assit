from __future__ import annotations

import pytest

from research_external.tools.partitions import (
    ROLE_FINAL_HOLDOUT,
    ROLE_TRAIN,
    HoldoutAccessDeniedError,
    freeze_partitions,
    require_not_holdout,
)


def _candle(date: str) -> dict:
    return {"time": f"{date}T00:00:00+00:00", "open": 1.1, "high": 1.11, "low": 1.09, "close": 1.1}


def test_train_partition_is_readable():
    candles = [_candle("2026-01-05"), _candle("2026-06-15")]
    partitions = freeze_partitions(candles, "sha256:parent", {
        ROLE_TRAIN: ("2026-01-01", "2026-07-01"),
        ROLE_FINAL_HOLDOUT: ("2026-07-01", "2026-08-01"),
    })
    rows = require_not_holdout(partitions[ROLE_TRAIN])
    assert len(rows) == 2


def test_final_holdout_partition_is_denied():
    candles = [_candle("2026-07-05")]
    partitions = freeze_partitions(candles, "sha256:parent", {
        ROLE_FINAL_HOLDOUT: ("2026-07-01", "2026-08-01"),
    })
    with pytest.raises(HoldoutAccessDeniedError):
        require_not_holdout(partitions[ROLE_FINAL_HOLDOUT])


def test_holdout_partition_is_marked_locked():
    candles = [_candle("2026-07-05")]
    partitions = freeze_partitions(candles, "sha256:parent", {
        ROLE_FINAL_HOLDOUT: ("2026-07-01", "2026-08-01"),
    })
    assert partitions[ROLE_FINAL_HOLDOUT].locked is True
