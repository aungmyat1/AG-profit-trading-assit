"""The ONLY module in market_structure/ allowed to import smartmoneyconcepts or touch
its raw DataFrame/Series output (supply_demand/smc_adapter.py is the equivalent module
for the Supply & Demand layer's own smc.ob/smc.fvg calls -- same isolation rule, applied
per capability layer). Everything crossing out of this module is a project-owned
market_structure.models type -- see that file's docstring.

Verified against smartmoneyconcepts 0.0.27 (2026-08-26):
- swing_highs_lows(ohlc, swing_length) -> DataFrame[HighLow, Level], fresh RangeIndex
  positionally aligned to `ohlc` regardless of `ohlc`'s own index.
- bos_choch(ohlc, swing_highs_lows, close_break) -> DataFrame[BOS, CHOCH, Level,
  BrokenIndex], same positional alignment. A row's own index is where the *swing point*
  that got broken sits; BrokenIndex is the position of the candle that *confirmed* the
  break -- we report events at BrokenIndex's time, since that's when it actually happened.
- previous_high_low(ohlc, time_frame) -> DataFrame[PreviousHigh, PreviousLow,
  BrokenHigh, BrokenLow]. Unlike the other two, this one calls `pd.to_datetime(ohlc.index)`
  internally -- passing a plain RangeIndex here would silently reinterpret 0,1,2,... as
  epoch nanoseconds, producing garbage. All three functions tolerate a genuine
  DatetimeIndex fine, so this module standardizes on ONE canonical DataFrame (DatetimeIndex
  = candle time_utc) for all of them rather than juggling two DataFrame shapes.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence

import pandas as pd
from smartmoneyconcepts import smc

from strategy_engine.session import Candle

from .models import StructurePoint, StructurePointKind

_REQUIRED_SWING_COLUMNS = {"HighLow", "Level"}
_REQUIRED_BOS_CHOCH_COLUMNS = {"BOS", "CHOCH", "Level", "BrokenIndex"}
_REQUIRED_PREV_HL_COLUMNS = {"PreviousHigh", "PreviousLow"}


class StructureLibraryError(RuntimeError):
    """Wraps any exception smartmoneyconcepts itself raises."""


class StructureOutputInvalid(RuntimeError):
    """The installed smartmoneyconcepts version returned a shape this adapter doesn't
    recognize -- a version-drift guard, not expected in normal operation."""


def candles_to_dataframe(candles: Sequence[Candle]) -> pd.DataFrame:
    """Canonical candles -> the one DataFrame shape every smc.* call in this module
    uses. DatetimeIndex = candle.time_utc (already true UTC -- see mt5/market_data.py)."""
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume if c.volume is not None else 0.0 for c in candles],
        },
        index=pd.DatetimeIndex([c.time for c in candles], name="time_utc"),
    )


def latest_swings_and_breaks(df: pd.DataFrame, swing_length: int, close_break: bool) -> dict:
    """Returns {'latest_swing_high', 'latest_swing_low', 'latest_bos', 'latest_choch'} ->
    Optional[StructurePoint]. Raises StructureLibraryError / StructureOutputInvalid."""
    try:
        swings = smc.swing_highs_lows(df, swing_length=swing_length)
    except Exception as exc:  # smc has no documented exception hierarchy of its own
        raise StructureLibraryError(f"swing_highs_lows failed: {exc}") from exc
    if not _REQUIRED_SWING_COLUMNS.issubset(swings.columns):
        raise StructureOutputInvalid(f"swing_highs_lows columns {list(swings.columns)} missing {_REQUIRED_SWING_COLUMNS}")

    try:
        breaks = smc.bos_choch(df, swings, close_break=close_break)
    except Exception as exc:
        raise StructureLibraryError(f"bos_choch failed: {exc}") from exc
    if not _REQUIRED_BOS_CHOCH_COLUMNS.issubset(breaks.columns):
        raise StructureOutputInvalid(f"bos_choch columns {list(breaks.columns)} missing {_REQUIRED_BOS_CHOCH_COLUMNS}")

    return {
        "latest_swing_high": _latest_swing(df, swings, want_high=True),
        "latest_swing_low": _latest_swing(df, swings, want_high=False),
        "latest_bos": _latest_break(df, breaks, column="BOS"),
        "latest_choch": _latest_break(df, breaks, column="CHOCH"),
    }


def all_breaks(df: pd.DataFrame, swing_length: int, close_break: bool) -> List[StructurePoint]:
    """ALL confirmed BOS/CHOCH events in the window, chronologically ordered by
    confirmation (BrokenIndex) time -- unlike latest_swings_and_breaks(), which only
    exposes the most recent of each. Needed by supply_demand/ob_contract.py to check
    whether a SPECIFIC order-block candidate (not just "the latest state") has a
    matching structure event, since a batch of historical OB candidates each need their
    own associated break, not just the newest one overall."""
    try:
        swings = smc.swing_highs_lows(df, swing_length=swing_length)
    except Exception as exc:
        raise StructureLibraryError(f"swing_highs_lows failed: {exc}") from exc
    if not _REQUIRED_SWING_COLUMNS.issubset(swings.columns):
        raise StructureOutputInvalid(f"swing_highs_lows columns {list(swings.columns)} missing {_REQUIRED_SWING_COLUMNS}")

    try:
        breaks = smc.bos_choch(df, swings, close_break=close_break)
    except Exception as exc:
        raise StructureLibraryError(f"bos_choch failed: {exc}") from exc
    if not _REQUIRED_BOS_CHOCH_COLUMNS.issubset(breaks.columns):
        raise StructureOutputInvalid(f"bos_choch columns {list(breaks.columns)} missing {_REQUIRED_BOS_CHOCH_COLUMNS}")

    points = [*_all_breaks_of(df, breaks, "BOS"), *_all_breaks_of(df, breaks, "CHOCH")]
    points.sort(key=lambda p: p.time_utc)
    return points


def full_swings(df: pd.DataFrame, swing_length: int) -> List[StructurePoint]:
    """ALL confirmed swing highs/lows (not just the latest of each), chronologically
    ordered -- needed by market_structure/tiers.py for HH/HL/LH/LL labeling. Deliberately
    duplicates latest_swings_and_breaks()'s swing_highs_lows call rather than sharing
    code with it, so this function's contract (swings only, no BOS/CHOCH) stays trivial
    to audit independently.

    Excludes the array's first and last row: smartmoneyconcepts 0.0.27's own
    swing_highs_lows() unconditionally force-assigns a swing label to position 0 and
    position len(df)-1 regardless of whether either was actually confirmed (a bookend
    artifact for indicator display, verified from source -- see this function's caller
    for the walk-forward test that caught it). Treating that as a real swing would be a
    hindsight leak: it's an artifact of "where the given array happens to end," not a
    structural fact, and disappears/moves the moment more candles are appended."""
    try:
        swings = smc.swing_highs_lows(df, swing_length=swing_length)
    except Exception as exc:
        raise StructureLibraryError(f"swing_highs_lows failed: {exc}") from exc
    if not _REQUIRED_SWING_COLUMNS.issubset(swings.columns):
        raise StructureOutputInvalid(f"swing_highs_lows columns {list(swings.columns)} missing {_REQUIRED_SWING_COLUMNS}")

    last_pos = len(df) - 1
    points = []
    for pos, row in swings.iterrows():
        if pos == 0 or pos == last_pos:
            continue
        level = row["Level"]
        if pd.isna(level):
            continue
        kind = StructurePointKind.SWING_HIGH if row["HighLow"] == 1.0 else StructurePointKind.SWING_LOW
        points.append(StructurePoint(time_utc=_time_at(df, pos), price=float(level), kind=kind))
    points.sort(key=lambda p: p.time_utc)
    return points


def previous_high_low(df: pd.DataFrame, time_frame: str) -> "tuple[Optional[float], Optional[float]]":
    try:
        result = smc.previous_high_low(df, time_frame=time_frame)
    except Exception as exc:
        raise StructureLibraryError(f"previous_high_low failed: {exc}") from exc
    if not _REQUIRED_PREV_HL_COLUMNS.issubset(result.columns):
        raise StructureOutputInvalid(f"previous_high_low columns {list(result.columns)} missing {_REQUIRED_PREV_HL_COLUMNS}")

    valid = result.dropna(subset=["PreviousHigh", "PreviousLow"])
    if valid.empty:
        return None, None
    last = valid.iloc[-1]
    return float(last["PreviousHigh"]), float(last["PreviousLow"])


def _latest_swing(df: pd.DataFrame, swings: pd.DataFrame, want_high: bool) -> Optional[StructurePoint]:
    target = 1.0 if want_high else -1.0
    rows = swings[swings["HighLow"] == target]
    if rows.empty:
        return None
    pos = rows.index[-1]  # RangeIndex position, aligned to df by construction
    kind = StructurePointKind.SWING_HIGH if want_high else StructurePointKind.SWING_LOW
    return StructurePoint(time_utc=_time_at(df, pos), price=float(rows.iloc[-1]["Level"]), kind=kind)


def _latest_break(df: pd.DataFrame, breaks: pd.DataFrame, column: str) -> Optional[StructurePoint]:
    points = _all_breaks_of(df, breaks, column)
    return points[-1] if points else None


def _all_breaks_of(df: pd.DataFrame, breaks: pd.DataFrame, column: str) -> List[StructurePoint]:
    rows = breaks[breaks[column].notna()]
    points = []
    for _, row in rows.iterrows():
        direction = float(row[column])
        broken_pos = int(row["BrokenIndex"])
        if column == "BOS":
            kind = StructurePointKind.BULLISH_BOS if direction > 0 else StructurePointKind.BEARISH_BOS
        else:
            kind = StructurePointKind.BULLISH_CHOCH if direction > 0 else StructurePointKind.BEARISH_CHOCH
        points.append(StructurePoint(time_utc=_time_at(df, broken_pos), price=float(row["Level"]), kind=kind))
    return points


def _time_at(df: pd.DataFrame, position: int) -> datetime:
    return df.index[position].to_pydatetime()
