"""Read-only VT Markets MT5 D1 history + symbol_info export for BTCUSD/ETHUSD (owner item 5, 2026-10-07).

D1 only, chunked by calendar year (UTC open time), one CSV per symbol-year, plus a symbol_info
JSON dump and a manifest with SHA-256 per file. MT5 calls: initialize, account_info (demo check),
symbol_info, copy_rates_range, shutdown. No symbol_select, no order or position call. Holds the
host-wide MT5 access lock used by the scheduled AG tasks.

Usage: <live venv python> export_vt_mt5_d1_pack.py <host_code_root> <out_dir>
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import sys

HOST_ROOT, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(HOST_ROOT, "scripts", "host"))
sys.path.insert(0, os.path.join(HOST_ROOT, "src"))
import _host_common as hc  # noqa: E402
from host_evidence.symbol_metadata import server_time_to_utc  # noqa: E402

SYMBOLS = ("BTCUSD", "ETHUSD")
UTC = dt.timezone.utc
START_YEAR = 2010


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    mt5 = hc.import_mt5()
    if mt5 is None:
        print("MT5_PACKAGE_MISSING")
        return 1
    os.makedirs(OUT, exist_ok=True)
    exported_at = dt.datetime.now(UTC)
    files, symbols_out = [], {}
    with hc.mt5_access_lock():
        ok, err = hc.mt5_initialize(mt5, os.environ.get("MT5_TERMINAL_PATH", ""))
        if not ok:
            print(f"MT5_INITIALIZE_FAILED {err}")
            return 1
        try:
            demo_ok, demo_status = hc.require_demo_account(mt5)
            if not demo_ok:
                print(f"DEMO_ACCOUNT_REQUIRED {demo_status}")
                return 1
            acct = mt5.account_info()
            server = getattr(acct, "server", None)
            terminal = mt5.terminal_info()
            for sym in SYMBOLS:
                info = mt5.symbol_info(sym)
                if info is None:
                    symbols_out[sym] = {"status": "SYMBOL_INFO_NONE", "last_error": str(mt5.last_error())}
                    continue
                info_d = {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v))
                          for k, v in info._asdict().items()}
                info_path = os.path.join(OUT, f"{sym}_symbol_info.json")
                with open(info_path, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(info_d, f, indent=2, sort_keys=True)
                    f.write("\n")
                files.append(info_path)
                rows_all = []
                for year in range(START_YEAR, exported_at.year + 1):
                    a = dt.datetime(year, 1, 1, tzinfo=UTC)
                    b = min(dt.datetime(year + 1, 1, 1, tzinfo=UTC), exported_at)
                    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, a, b)
                    if rates is None or len(rates) == 0:
                        continue
                    for r in rates:
                        raw = int(r["time"])
                        utc_open = server_time_to_utc(hc._mt5_server_wall(raw))
                        rows_all.append((raw, utc_open, float(r["open"]), float(r["high"]), float(r["low"]),
                                         float(r["close"]), int(r["tick_volume"]), int(r["spread"]),
                                         int(r["real_volume"])))
                # de-duplicate (range edges) and chunk by UTC-open calendar year
                uniq = {row[0]: row for row in rows_all}
                rows = [uniq[k] for k in sorted(uniq)]
                closed = [r for r in rows if r[1] + dt.timedelta(days=1) <= exported_at]
                by_year = {}
                for r in rows:
                    by_year.setdefault(r[1].year, []).append(r)
                for year, yrows in sorted(by_year.items()):
                    path = os.path.join(OUT, f"{sym}_D1_{year}.csv")
                    with open(path, "w", encoding="utf-8", newline="") as f:
                        w = csv.writer(f, lineterminator="\n")
                        w.writerow(["server_time_raw", "open_time_utc", "open", "high", "low", "close",
                                    "tick_volume", "spread_points", "real_volume"])
                        for r in yrows:
                            w.writerow([r[0], r[1].isoformat(), repr(r[2]), repr(r[3]), repr(r[4]), repr(r[5]),
                                        r[6], r[7], r[8]])
                    files.append(path)
                dates = [r[1].date() for r in rows]
                gaps = []
                for prev, cur in zip(dates, dates[1:]):
                    if (cur - prev).days > 1:
                        gaps.append({"after": prev.isoformat(), "before": cur.isoformat(),
                                     "missing_days": (cur - prev).days - 1})
                weekday_counts = {d: 0 for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
                for r in rows:
                    weekday_counts[r[1].strftime("%a")] += 1
                symbols_out[sym] = {
                    "status": "OK", "bars": len(rows), "closed_bars": len(closed),
                    "first_open_utc": rows[0][1].isoformat() if rows else None,
                    "last_open_utc": rows[-1][1].isoformat() if rows else None,
                    "last_bar_forming": bool(rows) and len(closed) < len(rows),
                    "years": {str(y): len(v) for y, v in sorted(by_year.items())},
                    "gap_count": len(gaps), "missing_days_total": sum(g["missing_days"] for g in gaps),
                    "largest_gaps": sorted(gaps, key=lambda g: -g["missing_days"])[:10],
                    "bars_by_utc_open_weekday": weekday_counts,
                    "digits": info_d.get("digits"), "trade_tick_size": info_d.get("trade_tick_size"),
                    "trade_contract_size": info_d.get("trade_contract_size"), "spread_now": info_d.get("spread"),
                    "swap_long": info_d.get("swap_long"), "swap_short": info_d.get("swap_short"),
                    "trade_mode": info_d.get("trade_mode"),
                }
        finally:
            mt5.shutdown()
    manifest = {
        "pack_id": "VT_MT5_CRYPTO_D1_PACK_V1", "exported_at_utc": exported_at.isoformat(),
        "venue": "VT Markets MT5 demo", "server": server,
        "terminal_build": getattr(terminal, "build", None), "timeframe": "D1",
        "time_rule": "open_time_utc = host_evidence.symbol_metadata.server_time_to_utc(server wall time); "
                     "server midnight = New York 17:00 (owner-stated rule)",
        "chunking": "one CSV per symbol per calendar year of open_time_utc; last bar may still be forming",
        "trading_hours": "NOT_AVAILABLE_VIA_MT5_PYTHON_API (symbol_info has no session table); weekend "
                         "coverage is reported from bar weekdays",
        "read_only_calls": ["initialize", "account_info", "terminal_info", "symbol_info", "copy_rates_range",
                            "shutdown"],
        "symbols": symbols_out,
        "files": [{"path": os.path.basename(p), "sha256": sha256(p), "bytes": os.path.getsize(p)}
                  for p in sorted(files)],
    }
    manifest["pack_sha256"] = hashlib.sha256(
        "\n".join(f"{f['path']} {f['sha256']}" for f in manifest["files"]).encode()).hexdigest()
    with open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({s: {k: v for k, v in d.items() if k not in ("largest_gaps",)} for s, d in symbols_out.items()},
                     indent=1, default=str))
    print("PACK_SHA256", manifest["pack_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
