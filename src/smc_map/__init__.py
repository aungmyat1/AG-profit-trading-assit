"""SMC_MARKET_MAP_V1 -- normalized, single-snapshot SMC market map (spec sections 17-19).
See builder.py and models.py module docstrings for what this is and, just as
importantly, what it deliberately does NOT do (redetect, or replace
SMC_CONDITIONAL_ENTRY_V2's own E1/E2/E3/M1/M2/M3/composer pipeline).
"""
from .builder import build_smc_market_map
from .evidence import evidence_id
from .models import DEFAULT_TIMEFRAMES, SMC_MARKET_MAP_V1, SMCMarketMap, TimeframeMap

__all__ = [
    "build_smc_market_map", "evidence_id",
    "SMCMarketMap", "TimeframeMap", "SMC_MARKET_MAP_V1", "DEFAULT_TIMEFRAMES",
]
