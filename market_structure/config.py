"""Loads config/market_structure.yaml. Fails loudly on a missing/malformed file rather
than silently defaulting -- same policy as strategy_engine/loader.py."""
from __future__ import annotations

import yaml

from .models import MarketStructureConfig

_DEFAULT_PATH = "config/market_structure.yaml"


def load_market_structure_config(path: str = _DEFAULT_PATH) -> MarketStructureConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return MarketStructureConfig(
        swing_length=int(raw["swing_length"]),
        close_break=bool(raw["close_break"]),
        default_analysis_count=int(raw["default_analysis_count"]),
    )
