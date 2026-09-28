"""Replay the EURUSD FX Opportunity slice over a hash-pinned MT5 M15 export (REPLAY mode).

    python scripts/replay_fx_opportunity.py --csv <file> --sha256 <hex> [--out <json>]

The CSV must have a `timestamp_utc,open,high,low,close,...` header with true-UTC bar
open times (see the package's dataset_manifest.json). Refuses to run on a hash
mismatch. Every trading day is evaluated for both cycles at two instants (mid-window
and window end) -- each run twice -- and the evaluations must be identical. Candles
are served only up to each evaluation instant by the runner's own look-ahead guard.
No MT5, no persistence, no proposal/ticket.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)

from fx_opportunity import CYCLES, evaluate_fx_opportunity  # noqa: E402
from mt5.market_data import MarketDataError  # noqa: E402
from opportunity.registry_binding import resolve_strategy_binding  # noqa: E402
from post_asian_pilot.pilot_config import load_pilot_config  # noqa: E402
from strategy_engine.loader import load_strategy  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

UTC = dt.timezone.utc


def _load(path):
    bars = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = dt.datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            bars.append(Candle(time=t, open=float(row["open"]), high=float(row["high"]),
                               low=float(row["low"]), close=float(row["close"]),
                               volume=float(row.get("tick_volume") or 0)))
    return bars


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--out")
    args = ap.parse_args()

    digest = hashlib.sha256(open(args.csv, "rb").read()).hexdigest()
    if digest != args.sha256.lower():
        print(json.dumps({"error": "DATASET_HASH_MISMATCH", "expected": args.sha256, "actual": digest}))
        return 2
    bars = _load(args.csv)

    def feed(symbol, timeframe, start, end):
        if symbol != args.symbol or timeframe != "M15":
            raise MarketDataError("DATA_MISSING", f"{symbol} {timeframe} not in replay file")
        out = [b for b in bars if start <= b.time < end]
        if not out:
            raise MarketDataError("DATA_MISSING", "no bars in range")
        return out

    days = sorted({b.time.date() for b in bars if b.time.weekday() < 5})
    source = f"replay:{os.path.relpath(args.csv, _REPO).replace(os.sep, '/')}@sha256:{digest}"
    rows, mismatches = [], []
    for cycle, cfg in sorted(CYCLES.items()):
        pilot = load_pilot_config(cfg)
        strategy = load_strategy(pilot.strategy_source_path)
        binding = resolve_strategy_binding(pilot.strategy_id)
        w_start = dt.time.fromisoformat(pilot.execution_window_start_utc)
        w_end = dt.time.fromisoformat(pilot.execution_window_end_utc)
        for day in days:
            end = dt.datetime.combine(day, w_end, tzinfo=UTC)
            mid = dt.datetime.combine(day, w_start, tzinfo=UTC) + (end - dt.datetime.combine(day, w_start, tzinfo=UTC)) / 2
            for label, now in (("MID", mid), ("END", end)):
                kw = dict(cycle=cycle, symbol=args.symbol, trading_date=day, now=now, pilot=pilot,
                          strategy=strategy, binding=binding, fetch_candles=feed,
                          market_data_mode="REPLAY", source=source)
                a, b = evaluate_fx_opportunity(**kw).summary(), evaluate_fx_opportunity(**kw).summary()
                if a != b:
                    mismatches.append((cycle, day.isoformat(), label))
                a["at"] = label
                rows.append(a)

    def tally(key, at="END"):
        return {cyc: dict(Counter(r[key] for r in rows if r["cycle"] == cyc and r["at"] == at)) for cyc in CYCLES}

    report = {
        "schema": "AG_FX_OPPORTUNITY_REPLAY_EVIDENCE_V1",
        "source": source,
        "symbol": args.symbol,
        "trading_days": len(days),
        "first_day": days[0].isoformat() if days else None,
        "last_day": days[-1].isoformat() if days else None,
        "evaluations": len(rows),
        "determinism_mismatches": mismatches,
        "end_of_window_decision_status": tally("decision_status"),
        "end_of_window_opportunity": tally("opportunity"),
        "mid_window_opportunity": tally("opportunity", at="MID"),
        "eligibility_status_all": dict(Counter(r["eligibility_status"] for r in rows)),
        "proposal_all": dict(Counter(r["proposal"] for r in rows)),
        "trade_ticket_all": dict(Counter(r["trade_ticket"] for r in rows)),
        "opportunities": [
            {k: r[k] for k in ("cycle", "trading_date", "at", "direction", "entry", "invalidation",
                               "candidate_id", "eligibility_status", "eligibility_reasons", "proposal")}
            for r in rows if r["opportunity"] == "OPPORTUNITY"
        ],
    }
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    print(text)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
