"""Loads config/liquidity.yaml. Fails loudly on a missing/malformed file -- same policy
as strategy_engine/loader.py and market_structure/config.py."""
from __future__ import annotations

from dataclasses import dataclass

import yaml

_DEFAULT_PATH = "config/liquidity.yaml"


@dataclass(frozen=True)
class LiquidityConfig:
    equal_level_tolerance_points: float
    local_extremum_window: int
    lookback_bars: int


def load_liquidity_config(path: str = _DEFAULT_PATH) -> LiquidityConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return LiquidityConfig(
        equal_level_tolerance_points=float(raw["equal_level_tolerance_points"]),
        local_extremum_window=int(raw["local_extremum_window"]),
        lookback_bars=int(raw["lookback_bars"]),
    )
