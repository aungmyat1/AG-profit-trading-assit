"""The ONLY module in supply_demand/ allowed to import smartmoneyconcepts or touch its
raw DataFrame/Series output -- same isolation rule as market_structure/smc_adapter.py,
whose candles_to_dataframe() this module reuses rather than re-deriving.

Verified against smartmoneyconcepts 0.0.27 (2026-08-26):
- ob(ohlc, swing_highs_lows, close_mitigation) -> DataFrame[OB, Top, Bottom, OBVolume,
  MitigatedIndex, Percentage]. OB=1 bullish / -1 bearish. MitigatedIndex==0 means NOT
  mitigated (verified from source: the array is zero-initialized and only overwritten on
  an actual mitigation event, whose index is always >= 2 -- so 0 is an unambiguous
  sentinel here, not a real position). An order block that gets fully invalidated (price
  closes back through it after crossing) is deleted from the library's internal arrays
  entirely -- it simply does not appear as a row in the output. That means this adapter
  can only ever report FRESH or MITIGATED for an OB/FVG that's still present in the
  frame; true INVALIDATED zones are invisible to us and are NOT reported (not guessed).
- Percentage = min(highVolume,lowVolume)/max(...)*100 -- a volume-symmetry ratio the
  library itself calls "strength". Exposed as `raw_strength_metric`, never as a
  probability or confidence score.
- fvg(ohlc, join_consecutive) -> DataFrame[FVG, Top, Bottom, MitigatedIndex]. Same
  MitigatedIndex==0 sentinel semantics as ob(), verified from source the same way.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
from smartmoneyconcepts import smc

from market_structure.smc_adapter import StructureLibraryError, StructureOutputInvalid, candles_to_dataframe
from strategy_engine.session import Candle

from .models import ZoneDirection, ZoneFamily, ZoneRole, ZoneResult, ZoneStatus

_REQUIRED_OB_COLUMNS = {"OB", "Top", "Bottom", "OBVolume", "MitigatedIndex", "Percentage"}
_REQUIRED_FVG_COLUMNS = {"FVG", "Top", "Bottom", "MitigatedIndex"}

__all__ = ["candles_to_dataframe", "order_blocks", "fair_value_gaps"]


def order_blocks(
    symbol: str,
    timeframe: str,
    candles: List[Candle],
    swing_length: int,
    close_mitigation: bool = False,
) -> List[ZoneResult]:
    df = candles_to_dataframe(candles)
    try:
        swings = smc.swing_highs_lows(df, swing_length=swing_length)
        raw = smc.ob(df, swings, close_mitigation=close_mitigation)
    except Exception as exc:
        raise StructureLibraryError(f"ob failed: {exc}") from exc
    if not _REQUIRED_OB_COLUMNS.issubset(raw.columns):
        raise StructureOutputInvalid(f"ob columns {list(raw.columns)} missing {_REQUIRED_OB_COLUMNS}")

    zones = []
    for pos, row in raw[raw["OB"].notna()].iterrows():
        bullish = float(row["OB"]) > 0
        zones.append(ZoneResult(
            symbol=symbol, timeframe=timeframe,
            family=ZoneFamily.ORDER_BLOCK,
            role=ZoneRole.DEMAND if bullish else ZoneRole.SUPPLY,
            direction=ZoneDirection.BULLISH if bullish else ZoneDirection.BEARISH,
            low=float(row["Bottom"]), high=float(row["Top"]),
            origin_time=_time_at(df, pos),
            status=_mitigation_status(row["MitigatedIndex"]),
            source="smc.ob",
            raw_strength_metric=float(row["Percentage"]),
        ))
    return zones


def fair_value_gaps(
    symbol: str,
    timeframe: str,
    candles: List[Candle],
    join_consecutive: bool = False,
) -> List[ZoneResult]:
    df = candles_to_dataframe(candles)
    try:
        raw = smc.fvg(df, join_consecutive=join_consecutive)
    except Exception as exc:
        raise StructureLibraryError(f"fvg failed: {exc}") from exc
    if not _REQUIRED_FVG_COLUMNS.issubset(raw.columns):
        raise StructureOutputInvalid(f"fvg columns {list(raw.columns)} missing {_REQUIRED_FVG_COLUMNS}")

    zones = []
    for pos, row in raw[raw["FVG"].notna()].iterrows():
        bullish = float(row["FVG"]) > 0
        zones.append(ZoneResult(
            symbol=symbol, timeframe=timeframe,
            family=ZoneFamily.FVG,
            # A bullish FVG is an air pocket price left behind while rising -- the kind
            # of zone that would draw price back down into it, i.e. functionally a
            # demand-side reference on a pullback; bearish is the supply-side mirror.
            role=ZoneRole.DEMAND if bullish else ZoneRole.SUPPLY,
            direction=ZoneDirection.BULLISH if bullish else ZoneDirection.BEARISH,
            low=float(row["Bottom"]), high=float(row["Top"]),
            origin_time=_time_at(df, pos),
            status=_mitigation_status(row["MitigatedIndex"]),
            source="smc.fvg",
        ))
    return zones


def _mitigation_status(mitigated_index) -> ZoneStatus:
    return ZoneStatus.FRESH if float(mitigated_index) == 0.0 else ZoneStatus.MITIGATED


def _time_at(df: pd.DataFrame, position) -> Optional[datetime]:
    try:
        return df.index[position].to_pydatetime()
    except (KeyError, IndexError, TypeError):
        return None
