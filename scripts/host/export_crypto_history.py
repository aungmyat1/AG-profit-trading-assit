"""AG_V1_HOST_HARDENING_R1 T4: export VT Markets MT5 BTCUSD/ETHUSD history (read-only).

    .venv\\Scripts\\python.exe scripts\\host\\export_crypto_history.py
    .venv\\Scripts\\python.exe scripts\\host\\export_crypto_history.py --symbol BTCUSD --timeframe H4

Uses MetaTrader5.copy_rates_range(symbol, timeframe, date_from, date_to) to pull the MAXIMUM
history the connected terminal's history cache holds for BTCUSD/ETHUSD on M15/H1/H4
(`date_from` is a date far enough in the past -- EXPORT_FROM_UTC below -- that `copy_rates_range`
simply returns everything the terminal has; it never raises when there is less than requested,
unlike `copy_rates_from_pos`'s count-based contract used elsewhere in this kit). Also dumps
`symbol_info()` (digits, tick size, contract size, spread, swap fields) for each symbol.

Trading-hours-including-weekends caveat (verified 2026-10-07): the official MetaTrader5 Python
package does not expose `symbol_info_session_quote`/`symbol_info_session_trade` at all (confirmed
against the MQL5 Python-API forum: those functions exist in MQL5 but are "attribute missing" in
the Python binding, and `symbol_info().session_open/session_close` are price fields, not times,
despite the name). This script therefore reports trading hours EMPIRICALLY: which (ISO weekday,
UTC hour-of-day) buckets actually contain at least one closed bar across the full exported M15
history (`observed_trading_hours_utc_by_weekday` in the manifest) -- this is evidence of when the
symbol actually traded, not a broker-declared schedule, and the manifest says so explicitly.

Output: one CSV per (symbol, timeframe) plus manifest.json (bar counts, gaps, first/last
timestamps, symbol_info dump, sha256 of every file) under --out (default
research_external/datasets/vt_markets_crypto_history_r1/). Read-only: no order, position or
account-mutation call exists in this file (tests/test_host_go_live_kit.py enforces this
statically across scripts/host/*.py).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import REPO_ROOT, call_with_timeout, import_mt5, mt5_initialize, require_demo_account, utcnow  # noqa: E402

from host_evidence.symbol_metadata import FIELDS, SWAP_FIELDS, server_time_to_utc  # noqa: E402

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAMES = ("M15", "H1", "H4")
TF_MINUTES = {"M15": 15, "H1": 60, "H4": 240}
# Far enough back that copy_rates_range returns the terminal's entire available history cache
# for a crypto CFD product (these venues rarely have more than a few years of M15 history).
EXPORT_FROM_UTC = dt.datetime(2015, 1, 1, tzinfo=dt.timezone.utc)
MANIFEST_SCHEMA = "AG_VT_CRYPTO_HISTORY_EXPORT_V1"
DEFAULT_OUT = os.path.join("research_external", "datasets", "vt_markets_crypto_history_r1")


def _mt5_server_wall(raw_time: int) -> dt.datetime:
    """Same convention as _host_common._mt5_server_wall -- duplicated locally (private, not
    re-exported) rather than imported, to keep this script's only dependency on that module
    limited to its public helpers."""
    return dt.datetime.fromtimestamp(raw_time, dt.timezone.utc).replace(tzinfo=None)


def _field(row: Any, name: str) -> Any:
    """Works for both a real numpy structured-array row (`row["time"]`) and a plain test
    double dict/namedtuple-like row."""
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return getattr(row, name, None)


def fetch_range_bars(mt5, symbol: str, timeframe: str, date_from: dt.datetime, date_to: dt.datetime) -> List[Dict[str, Any]]:
    """All CLOSED bars copy_rates_range returns for [date_from, date_to], oldest first, with
    `time` converted from broker-server wall clock to aware UTC (the same owner-stated rule
    host_fetch() uses: server midnight = New York 17:00)."""
    if timeframe not in TF_MINUTES:
        raise ValueError(f"UNSUPPORTED_TIMEFRAME {timeframe!r}")
    tf_const = getattr(mt5, f"TIMEFRAME_{timeframe}")
    rates = call_with_timeout(mt5.copy_rates_range, symbol, tf_const, date_from, date_to)
    if rates is None:
        raise RuntimeError(f"copy_rates_range({symbol!r}, {timeframe!r}) returned None: "
                           f"{call_with_timeout(mt5.last_error) if hasattr(mt5, 'last_error') else '?'}")
    bars = []
    for row in rates:
        utc_time = server_time_to_utc(_mt5_server_wall(int(_field(row, "time"))))
        bars.append({
            "time": utc_time, "open": float(_field(row, "open")), "high": float(_field(row, "high")),
            "low": float(_field(row, "low")), "close": float(_field(row, "close")),
            "tick_volume": float(_field(row, "tick_volume") or 0.0),
            "spread": _field(row, "spread"), "real_volume": _field(row, "real_volume"),
        })
    bars.sort(key=lambda b: b["time"])
    return bars


def detect_gaps(bars: Sequence[Dict[str, Any]], tf_minutes: int) -> List[Dict[str, Any]]:
    """Every consecutive pair whose elapsed time exceeds one trigger-timeframe bar. Purely
    factual (no broker-hours judgement is made about which gaps are "expected weekend closure"
    vs. an actual data hole) -- the manifest records every gap; interpreting them is a separate,
    later step once this is read by a human or another tool."""
    gaps = []
    for prev, nxt in zip(bars, bars[1:]):
        delta_min = (nxt["time"] - prev["time"]).total_seconds() / 60.0
        if delta_min > tf_minutes + 1e-6:
            gaps.append({"after_utc": prev["time"].isoformat(), "before_utc": nxt["time"].isoformat(),
                        "gap_minutes": delta_min})
    return gaps


def observed_hours_matrix(bars: Sequence[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Empirical (not broker-declared -- see module docstring) UTC hour-of-day coverage per ISO
    weekday (1=Monday..7=Sunday), derived from which hours actually contain a closed bar."""
    buckets: Dict[int, set] = {}
    for b in bars:
        buckets.setdefault(b["time"].isoweekday(), set()).add(b["time"].hour)
    return {str(k): sorted(v) for k, v in sorted(buckets.items())}


def write_bars_csv(path: str, bars: Sequence[Dict[str, Any]]) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
        for b in bars:
            writer.writerow([b["time"].isoformat(), b["open"], b["high"], b["low"], b["close"],
                             b["tick_volume"], b.get("spread"), b.get("real_volume")])
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def dump_symbol_info(mt5, symbol: str) -> Dict[str, Any]:
    info = call_with_timeout(mt5.symbol_info, symbol)
    if info is None and call_with_timeout(mt5.symbol_select, symbol, True):
        info = call_with_timeout(mt5.symbol_info, symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol!r}) returned None: "
                           f"{call_with_timeout(mt5.last_error) if hasattr(mt5, 'last_error') else '?'}")
    fields = {f: getattr(info, f, None) for f in FIELDS}
    for f in SWAP_FIELDS:
        val = getattr(info, f, None)
        if val is not None:
            fields[f] = val
    # session_open/session_close exist on symbol_info() but are PRICE fields (not times) --
    # included verbatim, explicitly labeled, never mistaken for a trading-hours schedule.
    for f in ("session_open", "session_close", "session_deals", "session_buy_orders", "session_sell_orders"):
        if hasattr(info, f):
            fields[f] = getattr(info, f)
    return fields


def export(mt5, *, symbols: Sequence[str] = SYMBOLS, timeframes: Sequence[str] = TIMEFRAMES,
          out_dir: str = DEFAULT_OUT, date_from: dt.datetime = EXPORT_FROM_UTC,
          date_to: Optional[dt.datetime] = None, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    now = now or utcnow()
    date_to = date_to or now
    manifest: Dict[str, Any] = {
        "schema": MANIFEST_SCHEMA, "generated_at_utc": now.isoformat(), "source": "MT5_VT_MARKETS_DEMO",
        "export_window_requested_utc": [date_from.isoformat(), date_to.isoformat()],
        "trading_hours_note": (
            "symbol_info_session_quote/session_trade are not exposed by the MetaTrader5 Python "
            "package (verified 2026-10-07); observed_trading_hours_utc_by_weekday below is "
            "EMPIRICAL (derived from which hours actually contain a closed M15 bar), not a "
            "broker-declared schedule."
        ),
        "symbols": {},
    }
    for symbol in symbols:
        manifest["symbols"][symbol] = {"symbol_info": dump_symbol_info(mt5, symbol), "timeframes": {}}
        m15_bars_for_hours: List[Dict[str, Any]] = []
        for tf in timeframes:
            bars = fetch_range_bars(mt5, symbol, tf, date_from, date_to)
            if tf == "M15":
                m15_bars_for_hours = bars
            file_name = f"{symbol}_{tf}.csv"
            sha256 = write_bars_csv(os.path.join(out_dir, file_name), bars)
            gaps = detect_gaps(bars, TF_MINUTES[tf])
            manifest["symbols"][symbol]["timeframes"][tf] = {
                "file": file_name, "sha256": sha256, "bar_count": len(bars),
                "first_closed_utc": bars[0]["time"].isoformat() if bars else None,
                "last_closed_utc": bars[-1]["time"].isoformat() if bars else None,
                "gap_count": len(gaps),
                "max_gap_minutes": max((g["gap_minutes"] for g in gaps), default=0.0),
                "total_gap_minutes": sum(g["gap_minutes"] for g in gaps),
                "gaps": gaps,
            }
        manifest["symbols"][symbol]["observed_trading_hours_utc_by_weekday"] = observed_hours_matrix(m15_bars_for_hours)

    manifest_path = os.path.join(out_dir, "manifest.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    manifest_sha256 = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    with open(manifest_path + ".sha256.txt", "w", encoding="utf-8") as f:
        f.write(f"{manifest_sha256}  manifest.json\n")
    manifest["_manifest_sha256"] = manifest_sha256
    return manifest


def main(argv=None, mt5=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbol", action="append", choices=SYMBOLS, dest="symbols", default=None)
    ap.add_argument("--timeframe", action="append", choices=TIMEFRAMES, dest="timeframes", default=None)
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, DEFAULT_OUT))
    ap.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH", ""))
    args = ap.parse_args(argv)

    mt5 = mt5 or import_mt5()
    if mt5 is None:
        print("MetaTrader5 package missing -- run scripts/host/diagnose_mt5.py first")
        return 1
    ok, err = mt5_initialize(mt5, args.terminal_path)
    if not ok:
        print(f"initialize() failed: {err} -- run scripts/host/diagnose_mt5.py")
        return 1
    try:
        demo_ok, demo_detail = require_demo_account(mt5)
        if not demo_ok:
            print(f"REFUSED: {demo_detail} (this export only ever runs against the VT Markets demo account)")
            return 1
        manifest = export(mt5, symbols=args.symbols or SYMBOLS, timeframes=args.timeframes or TIMEFRAMES,
                          out_dir=args.out)
        for symbol, rec in manifest["symbols"].items():
            for tf, tf_rec in rec["timeframes"].items():
                print(f"EXPORTED {symbol} {tf}: {tf_rec['bar_count']} bars "
                     f"[{tf_rec['first_closed_utc']} .. {tf_rec['last_closed_utc']}] "
                     f"gaps={tf_rec['gap_count']} sha256={tf_rec['sha256'][:16]}")
        print(f"MANIFEST: {os.path.join(args.out, 'manifest.json')} sha256={manifest['_manifest_sha256'][:16]}")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
