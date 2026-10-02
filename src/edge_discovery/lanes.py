"""Explicit research-lane isolation.

The factory shares ingestion/quality mechanics across lanes, never economic evidence.
A candidate and every dataset admitted to it must remain in the exact lane associated
with their asset class; there is no fallback or near-symbol conversion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple


@dataclass(frozen=True)
class ResearchLane:
    lane_id: str
    asset_class: str
    symbols: Tuple[str, ...]
    data_description: str


LANE_FX = ResearchLane(
    lane_id="LANE_FX", asset_class="FX", symbols=("EURUSD", "GBPUSD", "USDJPY"),
    data_description="Existing locally stored FX historical datasets",
)
LANE_CRYPTO_CFD = ResearchLane(
    lane_id="LANE_CRYPTO_CFD", asset_class="CRYPTO_CFD", symbols=("BTCUSD", "ETHUSD"),
    data_description="VT Markets BTCUSD/ETHUSD CFD exporter artifacts",
)
LANE_CRYPTO_PERP = ResearchLane(
    lane_id="LANE_CRYPTO_PERP", asset_class="CRYPTO_USDT_PERP", symbols=(),
    data_description="Future public-exchange BTC" + "USDT/ETH" + "USDT perpetual data",
)
LANES: Mapping[str, ResearchLane] = {
    LANE_FX.asset_class: LANE_FX,
    LANE_CRYPTO_CFD.asset_class: LANE_CRYPTO_CFD,
    LANE_CRYPTO_PERP.asset_class: LANE_CRYPTO_PERP,
}


class LaneIsolationError(ValueError):
    pass


def lane_for_asset_class(asset_class: str) -> ResearchLane:
    try:
        return LANES[asset_class]
    except KeyError as exc:
        raise LaneIsolationError(f"ASSET_CLASS_LANE_UNDEFINED:{asset_class}") from exc


def assert_lane_compatible(candidate_asset_class: str, dataset_asset_class: str, symbol: str) -> ResearchLane:
    candidate_lane = lane_for_asset_class(candidate_asset_class)
    dataset_lane = lane_for_asset_class(dataset_asset_class)
    if candidate_lane.lane_id != dataset_lane.lane_id:
        raise LaneIsolationError(
            f"CROSS_LANE_DATASET_SUBSTITUTION_FORBIDDEN:{dataset_lane.lane_id}->{candidate_lane.lane_id}"
        )
    if candidate_lane.symbols and symbol not in candidate_lane.symbols:
        raise LaneIsolationError(f"LANE_SYMBOL_NOT_ALLOWED:{symbol}@{candidate_lane.lane_id}")
    return candidate_lane


__all__ = [
    "LANE_CRYPTO_CFD", "LANE_CRYPTO_PERP", "LANE_FX", "LANES", "LaneIsolationError",
    "ResearchLane", "assert_lane_compatible", "lane_for_asset_class",
]
