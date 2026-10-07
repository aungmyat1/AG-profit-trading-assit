"""MT5_CANDLES_READONLY_R1 live acceptance: pull ~3 trading days of closed M15/H1 candles for
EURUSD, GBPUSD, USDJPY and XAUUSD through src/mt5/mt5_candles_readonly.py and report rows,
first/last UTC timestamps, gaps, duplicates, schema result and broker symbol.

    .venv\\Scripts\\python.exe scripts\\host\\mt5_candles_readonly_acceptance.py [--out DIR]

Read-only: the adapter receives a guard proxy of the MetaTrader5 module that permits only the
adapter's ALLOWED_MT5_CALLS and counts (and refuses) anything else, so ORDER_API_CALLS is
measured, not assumed.  Session setup here uses only initialize / account_info (demo check,
non-mutating; nothing from it is written) / shutdown.  No strategy evaluation, no evaluator.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import REPO_ROOT, import_mt5, mt5_access_lock, mt5_initialize, require_demo_account, utcnow  # noqa: E402

from mt5 import mt5_candles_readonly as adapter  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

COUNTS = {"M15": 3 * 96, "H1": 3 * 24}   # ~three trading days of closed bars
ORDER_API = ("order_send", "order_check", "positions_get", "orders_get", "history_orders_get",
             "history_deals_get", "symbol_select")


class GuardedMT5:
    def __init__(self, mt5):
        self._mt5 = mt5
        self.allowed_calls = 0
        self.refused = []

    def __getattr__(self, name):
        if name.startswith("TIMEFRAME_"):
            return getattr(self._mt5, name)
        if name not in adapter.ALLOWED_MT5_CALLS:
            self.refused.append(name)
            raise PermissionError(f"MT5 call refused by read-only guard: {name}")
        self.allowed_calls += 1
        return getattr(self._mt5, name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "artifacts", "validation", "mt5_candles_readonly_r1"))
    ap.add_argument("--sample-bars", type=int, default=3)
    args = ap.parse_args(argv)

    mt5 = import_mt5()
    if mt5 is None:
        print("BLOCKER = MT5_PACKAGE_UNAVAILABLE")
        return 2
    with mt5_access_lock():
        ok, detail = mt5_initialize(mt5)
        if not ok:
            print(f"BLOCKER = MT5_INITIALIZE_FAILED {detail}")
            return 2
        try:
            demo_ok, demo_detail = require_demo_account(mt5)
            if not demo_ok:
                print(f"BLOCKER = {demo_detail}")
                return 2
            guard = GuardedMT5(mt5)
            smap = adapter.default_symbol_map()
            fixture_fields = [f.name for f in dataclasses.fields(Candle)]
            results, sample = [], {}
            for sym in adapter.SUPPORTED_SYMBOLS:
                for tf, n in COUNTS.items():
                    row = {"symbol": sym, "timeframe": tf, "broker_symbol": smap.get(sym)}
                    try:
                        candles = adapter.fetch_closed_candles(guard, sym, tf, n, smap)
                        rep = adapter.series_report(candles, tf)
                        engine = adapter.to_engine_candles(candles)
                        schema_ok = (all(isinstance(e, Candle) for e in engine)
                                     and all(tuple(r) == adapter.CANONICAL_FIELDS for r in adapter.as_rows(candles)))
                        row.update(rep, status="OK", schema="PASS" if schema_ok else "FAIL")
                        rows = adapter.as_rows(candles)
                        sample[f"{sym}_{tf}"] = rows[:args.sample_bars] + rows[-args.sample_bars:]
                    except adapter.CandleAdapterError as exc:
                        row.update(status=exc.code, detail=exc.detail, schema="NOT_EVALUATED")
                    results.append(row)
        finally:
            mt5.shutdown()

    report = {
        "mission": "MT5_CANDLES_READONLY_R1",
        "captured_at_utc": utcnow().isoformat(),
        "adapter": "src/mt5/mt5_candles_readonly.py",
        "time_rule": "host_evidence.symbol_metadata.server_time_to_utc (server midnight = New York 17:00)",
        "fixture_schema": {"strategy_engine.session.Candle": fixture_fields,
                           "canonical": list(adapter.CANONICAL_FIELDS)},
        "allowed_mt5_calls_made": guard.allowed_calls,
        "refused_mt5_calls": guard.refused,
        "order_api_calls": sum(1 for r in guard.refused if r in ORDER_API),
        "results": results,
    }
    os.makedirs(args.out, exist_ok=True)
    stamp = report["captured_at_utc"][:10]
    with open(os.path.join(args.out, f"{stamp}_acceptance_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    with open(os.path.join(args.out, f"{stamp}_sanitized_sample.json"), "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2, sort_keys=True)

    for r in results:
        print(f"{r['symbol']:7} {r['timeframe']:4} {r['status']:24} broker={r['broker_symbol']} rows={r.get('rows')} "
              f"first={r.get('first')} last={r.get('last')} gaps={len(r.get('gaps', []))} "
              f"unexpected={r.get('unexpected_gaps')} dup={r.get('duplicates')} schema={r['schema']}")
    print(f"ORDER_API_CALLS = {report['order_api_calls']}  REFUSED = {guard.refused}")
    return 0 if all(r["status"] == "OK" and r["schema"] == "PASS" for r in results) and not guard.refused else 1


if __name__ == "__main__":
    raise SystemExit(main())
