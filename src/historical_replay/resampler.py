"""Deterministic single-feed resampling (historical-validation continuation spec
sections 6, 11): derive M15/H1/H4/D1 from one base feed (M5, or M1 when available)
rather than independently loading separate per-timeframe files. A derived bar is
included ONLY when every one of its constituent base bars is present -- an incomplete
window is dropped, never fabricated (spec section 8: no silent gap-filling), and its
open time is UTC-boundary-aligned to that timeframe (H1 on the hour, H4 on 0/4/8/12/16/
20 UTC, D1 on 00:00 UTC) -- the same boundaries live analyzers already assume from MT5's
own timeframe candles.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Sequence, Tuple

from strategy_engine.session import Candle

from .candle_store import TIMEFRAME_MINUTES, HistoricalDataError

H4_BOUNDARY_HOURS = (0, 4, 8, 12, 16, 20)


def _bucket_start(t: datetime, timeframe: str) -> datetime:
    if timeframe == "D1":
        return t.replace(hour=0, minute=0, second=0, microsecond=0)
    if timeframe == "H4":
        boundary_hour = max(h for h in H4_BOUNDARY_HOURS if h <= t.hour)
        return t.replace(hour=boundary_hour, minute=0, second=0, microsecond=0)
    if timeframe == "H1":
        return t.replace(minute=0, second=0, microsecond=0)
    if timeframe == "M15":
        return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)
    raise HistoricalDataError("UNSUPPORTED_TIMEFRAME", f"cannot bucket for {timeframe!r}")


def resample(base_candles: List[Candle], base_timeframe: str, target_timeframe: str) -> List[Candle]:
    """`base_candles` must already be ascending, gap-checked (mt5_export_loader's own
    job), and in the base timeframe's native spacing. Returns only COMPLETE target
    bars -- a target window missing any base bar is dropped, not approximated."""
    if base_timeframe not in TIMEFRAME_MINUTES or target_timeframe not in TIMEFRAME_MINUTES:
        raise HistoricalDataError("UNSUPPORTED_TIMEFRAME", f"{base_timeframe!r}/{target_timeframe!r}")
    base_minutes = TIMEFRAME_MINUTES[base_timeframe]
    target_minutes = TIMEFRAME_MINUTES[target_timeframe]
    if target_minutes < base_minutes or target_minutes % base_minutes != 0:
        raise HistoricalDataError(
            "UNSUPPORTED_RESAMPLE", f"{target_timeframe!r} is not an integer multiple of {base_timeframe!r}"
        )
    if base_timeframe == target_timeframe:
        return list(base_candles)

    expected_bars_per_bucket = target_minutes // base_minutes
    buckets: Dict[datetime, List[Candle]] = defaultdict(list)
    for c in base_candles:
        buckets[_bucket_start(c.time, target_timeframe)].append(c)

    out: List[Candle] = []
    for bucket_start in sorted(buckets):
        members = sorted(buckets[bucket_start], key=lambda c: c.time)
        # A complete bucket's members are exactly the expected consecutive base bars,
        # starting exactly at the bucket boundary.
        if len(members) != expected_bars_per_bucket or members[0].time != bucket_start:
            continue
        ok = all(members[i + 1].time - members[i].time == timedelta(minutes=base_minutes)
                 for i in range(len(members) - 1))
        if not ok:
            continue
        volumes = [m.volume for m in members if m.volume is not None]
        out.append(Candle(
            time=bucket_start,
            open=members[0].open,
            high=max(m.high for m in members),
            low=min(m.low for m in members),
            close=members[-1].close,
            volume=sum(volumes) if volumes else None,
        ))
    return out


def resample_broker_aligned(base_candles: Sequence[Candle], broker_times: Sequence[datetime],
                             base_timeframe: str, target_timeframe: str) -> List[Candle]:
    """D1/H4 ONLY. Buckets by the candle's BROKER wall-clock day (D1) or 4h window
    (H4) -- required because MT5's own D1/H4 candles are anchored to the broker's
    calendar day/4h window, not UTC midnight. Confirmed empirically this phase: a
    UTC-midnight-bucketed `resample(..., "D1")` mismatched EVERY SINGLE bar of a native
    MT5 D1 export for the same symbol/range, because the broker's UTC offset (+2/+3
    seasonal) does not divide evenly into 24h -- broker midnight lands at 21:00/22:00
    UTC the previous day, not 00:00 UTC. H1/M15 stay correct under plain UTC bucketing
    (whole-hour offsets preserve hour boundaries); only day/4h-anchored windows need
    this. `broker_times` must be the same length/order as `base_candles` (see
    IngestionReport.broker_times).

    Completeness here means CONTIGUOUS at native spacing within the bucket (no internal
    gap) -- NOT a fixed bar count. A broker day/4h window can legitimately be shorter
    near a weekly open/close or a holiday, exactly like MT5's own D1 candle for such a
    day is naturally shorter, not "incomplete"; the ingestion-level gap report already
    flags genuine missing data (spec section 8)."""
    if target_timeframe not in ("D1", "H4"):
        raise HistoricalDataError("UNSUPPORTED_TIMEFRAME", f"resample_broker_aligned only supports D1/H4, got {target_timeframe!r}")
    if base_timeframe not in TIMEFRAME_MINUTES:
        raise HistoricalDataError("UNSUPPORTED_TIMEFRAME", f"{base_timeframe!r}")
    if len(base_candles) != len(broker_times):
        raise HistoricalDataError("MISMATCHED_LENGTHS", "base_candles and broker_times must be parallel")
    base_minutes = TIMEFRAME_MINUTES[base_timeframe]

    buckets: Dict[datetime, List[Tuple[Candle, datetime]]] = defaultdict(list)
    for c, bt in zip(base_candles, broker_times):
        buckets[_bucket_start(bt, target_timeframe)].append((c, bt))

    out: List[Candle] = []
    for bucket_broker_start in sorted(buckets):
        members = sorted(buckets[bucket_broker_start], key=lambda pair: pair[1])
        broker_ts = [bt for _, bt in members]
        contiguous = all(broker_ts[i + 1] - broker_ts[i] == timedelta(minutes=base_minutes)
                          for i in range(len(broker_ts) - 1))
        if not contiguous:
            continue
        candles_only = [c for c, _ in members]
        volumes = [m.volume for m in candles_only if m.volume is not None]
        out.append(Candle(
            time=candles_only[0].time,  # UTC time of the first member -- matches how MT5's own conversion labels a broker-anchored bar
            open=candles_only[0].open,
            high=max(m.high for m in candles_only),
            low=min(m.low for m in candles_only),
            close=candles_only[-1].close,
            volume=sum(volumes) if volumes else None,
        ))
    return out
