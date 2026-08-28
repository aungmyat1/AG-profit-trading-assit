"""Public entry points for Order Blocks / Fair Value Gaps: fetch candles, handle
MT5/library failures, delegate mapping to smc_adapter.py. Mirrors
market_structure/analyzer.py's shape and warm-up policy (reuses the SAME
config/market_structure.yaml swing_length rather than introducing a second config for
what is, for OB, the same swing_highs_lows input) and its fail-closed
status/reason_codes pattern -- an empty `zones` tuple with status "OK" means "queried
successfully, nothing found"; any other status means the query itself failed.
"""
from __future__ import annotations

from typing import List, Optional

from market_structure.config import load_market_structure_config
from market_structure.smc_adapter import StructureLibraryError, StructureOutputInvalid
from mt5.market_data import MarketDataError, get_latest_candles

from .models import ZoneFamily, ZoneQueryResult
from .ob_config import AGOrderBlockConfig
from .ob_contract import ValidatedOrderBlock, validate_order_blocks
from .smc_adapter import fair_value_gaps as _fair_value_gaps
from .smc_adapter import order_blocks as _order_blocks

__all__ = ["order_blocks_for", "fair_value_gaps_for", "validated_order_blocks_for"]


def order_blocks_for(symbol: str, timeframe: str, count: Optional[int] = None, close_mitigation: bool = False) -> ZoneQueryResult:
    config = load_market_structure_config()
    count = count or config.default_analysis_count
    warmup_bars = max(config.swing_length * 20, 100)

    try:
        candles = get_latest_candles(symbol, timeframe, count + warmup_bars)
    except MarketDataError as exc:
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK,
                                status=exc.reason_code, reason_codes=(exc.reason_code,))
    try:
        zones = _order_blocks(symbol, timeframe, candles, config.swing_length, close_mitigation)
    except StructureLibraryError as exc:
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK,
                                status="STRUCTURE_LIBRARY_ERROR", reason_codes=(str(exc),))
    except StructureOutputInvalid as exc:
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK,
                                status="STRUCTURE_OUTPUT_INVALID", reason_codes=(str(exc),))

    return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK,
                            status="OK", zones=tuple(zones))


def fair_value_gaps_for(symbol: str, timeframe: str, count: Optional[int] = None, join_consecutive: bool = False) -> ZoneQueryResult:
    config = load_market_structure_config()
    count = count or config.default_analysis_count

    try:
        candles = get_latest_candles(symbol, timeframe, count)
    except MarketDataError as exc:
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.FVG,
                                status=exc.reason_code, reason_codes=(exc.reason_code,))
    try:
        zones = _fair_value_gaps(symbol, timeframe, candles, join_consecutive)
    except StructureLibraryError as exc:
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.FVG,
                                status="STRUCTURE_LIBRARY_ERROR", reason_codes=(str(exc),))
    except StructureOutputInvalid as exc:
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.FVG,
                                status="STRUCTURE_OUTPUT_INVALID", reason_codes=(str(exc),))

    return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.FVG,
                            status="OK", zones=tuple(zones))


def validated_order_blocks_for(symbol: str, timeframe: str, count: Optional[int] = None,
                                close_mitigation: bool = False,
                                ob_config: Optional[AGOrderBlockConfig] = None) -> List[ValidatedOrderBlock]:
    """smc.ob() candidates run through the AG Order Block Validator (AG_ORDER_BLOCK_V1,
    ob_contract.py). Does NOT change order_blocks_for()'s/fair_value_gaps_for()'s own
    behavior -- those keep returning raw smc candidates unchanged; this fetches its own
    candle set (once) so OB and FVG candidates share identical positional alignment,
    which the validator's MAX_CANDLES_TO_FVG window and structure lookup both depend on."""
    structure_config = load_market_structure_config()
    count = count or structure_config.default_analysis_count
    warmup_bars = max(structure_config.swing_length * 20, 100)

    try:
        candles = get_latest_candles(symbol, timeframe, count + warmup_bars)
    except MarketDataError:
        return []

    try:
        ob_candidates = _order_blocks(symbol, timeframe, candles, structure_config.swing_length, close_mitigation)
        fvg_candidates = _fair_value_gaps(symbol, timeframe, candles)
    except (StructureLibraryError, StructureOutputInvalid):
        return []

    return validate_order_blocks(ob_candidates, fvg_candidates, candles, ob_config)
