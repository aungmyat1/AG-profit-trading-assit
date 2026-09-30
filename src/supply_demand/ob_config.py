"""Loads config/ag_order_block_v1.yaml. Fails loudly on a missing/malformed file --
same policy as strategy_engine/loader.py, market_structure/config.py, liquidity/config.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import yaml

_DEFAULT_PATH = "config/ag_order_block_v1.yaml"


@dataclass(frozen=True)
class AGOrderBlockConfig:
    pivot_shadow_body_ratio_threshold: float


def load_ag_order_block_config(path: str = _DEFAULT_PATH) -> AGOrderBlockConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AGOrderBlockConfig(
        pivot_shadow_body_ratio_threshold=float(raw["pivot_shadow_body_ratio_threshold"]),
    )
