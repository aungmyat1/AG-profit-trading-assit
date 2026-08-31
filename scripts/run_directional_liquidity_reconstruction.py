"""Reconstructs the time-varying directional HTF liquidity context (BUY/SELL) that
M3 actually consumes -- confirmed by call-graph audit to be computed once per poll,
per direction, independent of which E family later composes with it
(conditional_entry_snapshot.py:222-256). Much cheaper than the E-eligibility walk:
only liquidity_result(symbol,"H1") per step, no full E1/E2/E3/M5-structure analysis.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
warnings.filterwarnings("ignore", category=FutureWarning)

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned  # noqa: E402
from historical_replay.data_source_patch import historical_data_context  # noqa: E402
from historical_replay.orchestrator import D1_WARMUP_CANDLES, H1_WARMUP_CANDLES, M5_WARMUP_CANDLES, _has_enough_history  # noqa: E402
from historical_replay.stage2 import Stage1LiquidityReference  # noqa: E402
from liquidity.analyzer import liquidity_result  # noqa: E402
from mt5.market_data import MarketDataError  # noqa: E402

SYMBOL = "EURUSD"
START = datetime(2025, 8, 1, tzinfo=timezone.utc)
END = datetime(2025, 10, 1, tzinfo=timezone.utc)
CHECKPOINT_PATH = "artifacts/backtests/directional_liquidity_checkpoint.json"
OUT_PATH = "artifacts/backtests/directional_liquidity_timeline.json"


def _ref_tuple(level):
    if level is None:
        return None
    return (level.side.value, level.price, level.source,
            level.sweep_time.isoformat() if level.sweep_time else None,
            level.reclaim_time.isoformat() if level.reclaim_time else None)


def main() -> None:
    candles, rep = load_mt5_export_csv(r"D:\EURUSD_M5_202504211715_202607310000.csv", SYMBOL, "M5")
    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series(SYMBOL, tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series(SYMBOL, tf, resample_broker_aligned(candles, rep.broker_times, "M5", tf))

    buy_polls: list = []   # (as_of, ref_tuple_or_None)
    sell_polls: list = []
    steps = valid_steps = 0
    warmup_cleared = False
    t0 = time.time()

    for candle in candles:
        as_of = candle.time + timedelta(minutes=5)
        if as_of < START or as_of >= END:
            continue
        steps += 1

        if not warmup_cleared:
            if (_has_enough_history(store, SYMBOL, "D1", D1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, SYMBOL, "H1", H1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, SYMBOL, "M5", M5_WARMUP_CANDLES, as_of)):
                warmup_cleared = True
            else:
                continue

        valid_steps += 1
        with historical_data_context(store, as_of):
            try:
                liq = liquidity_result(SYMBOL, "H1")
            except MarketDataError:
                liq = None

        buy_ref = liq.nearest_buy_side if liq is not None and liq.status == "LIQUIDITY_OK" else None
        sell_ref = liq.nearest_sell_side if liq is not None and liq.status == "LIQUIDITY_OK" else None
        buy_polls.append((as_of, _ref_tuple(buy_ref)))
        sell_polls.append((as_of, _ref_tuple(sell_ref)))

        if valid_steps % 2000 == 0:
            with open(CHECKPOINT_PATH, "w") as f:
                json.dump({"valid_steps": valid_steps, "steps": steps, "as_of": as_of.isoformat(),
                          "elapsed_seconds": round(time.time() - t0, 1)}, f, indent=2)

    def _compress(polls):
        intervals = []  # (start, end, ref_tuple)
        for as_of, ref in polls:
            end = as_of + timedelta(minutes=5)
            if intervals and intervals[-1][2] == ref and intervals[-1][1] == as_of:
                intervals[-1] = (intervals[-1][0], end, ref)
            else:
                intervals.append((as_of, end, ref))
        return intervals

    buy_intervals = _compress(buy_polls)
    sell_intervals = _compress(sell_polls)

    def _serialize(intervals):
        out = []
        for start, end, ref in intervals:
            out.append({
                "start_time": start.isoformat(), "end_time": end.isoformat(),
                "liquidity_reference": None if ref is None else {
                    "side": ref[0], "price": ref[1], "source": ref[2], "sweep_time": ref[3], "reclaim_time": ref[4],
                },
            })
        return out

    result = {
        "symbol": SYMBOL, "range": [START.isoformat(), END.isoformat()],
        "steps": steps, "valid_steps": valid_steps, "elapsed_seconds": round(time.time() - t0, 2),
        "BUY": _serialize(buy_intervals), "SELL": _serialize(sell_intervals),
        "buy_interval_count": len(buy_intervals), "sell_interval_count": len(sell_intervals),
        "buy_gap_count": sum(1 for iv in buy_intervals if iv[2] is None),
        "sell_gap_count": sum(1 for iv in sell_intervals if iv[2] is None),
    }
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in result.items() if k not in ("BUY", "SELL")}, indent=2))


if __name__ == "__main__":
    main()
