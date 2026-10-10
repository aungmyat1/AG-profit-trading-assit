"""AGP-DATA-R2b: M1/M5/H1/D1 (+ M15 spread) for the PR #128 crypto day set (read-only).

Allowed MetaTrader5 calls: initialize, copy_rates_range, symbol_info, shutdown.
tests/test_capture_recorded_ccfd_tfs.py enforces this statically.

The day set, per-day offsets and M1 gap list are read from the PR #128 provenance note
(`<SYM>_M15_recorded.PROVENANCE.md`); nothing is re-selected or re-measured. Per day:

- M1 00:00-23:59, M5 00:00-23:55, H1 00:00-23:00, M15 00:00-23:45 UTC, each read twice
  (differing reads drop the day). Missing bars are listed, never filled.
- M1 gaps must equal the PR #128 gap list and M15 OHLC must equal the PR #128 rows, or
  the day is dropped (the M15 file is referenced, not re-written).
- M5/H1/M15 bars are compared with the aggregate of their present M1 bars: PASS when all
  M1 bars are present, PARTIAL_M1_CHECK when some are missing (still compared), FAIL on
  any difference or on M1 bars without their bar.
- D1 is the broker day (server midnight = 17:00 America/New_York), written at its own UTC
  open, never re-bucketed. Only bars closed at capture time are kept. A D1 bar wholly
  inside the captured M1 range is compared with its M1 aggregate.
- spread: the MqlRates spread field (points) and spread x host-captured point (price).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_recorded_m15 import (aggregate_present_m1, compress_minutes, fmt_price,  # noqa: E402
                                  peak_working_set_mb, redact_host_path)

UTC = timezone.utc
STEP = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "D1": 86400}
OHLC_HEADER = "timestamp_utc,open,high,low,close\n"


class Terminal:
    """Thin read-only wrapper; the only place the MT5 package is touched."""

    def __init__(self, path: str | None):
        import MetaTrader5 as mt5

        self.mt5 = mt5
        ok = mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            raise SystemExit("MT5 initialize failed")

    def info(self, symbol: str) -> tuple[int, float]:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise SystemExit(f"symbol not found: {symbol}")
        return int(info.digits), float(info.point)

    def rates(self, symbol: str, tf: str, lo: int, hi: int) -> list[tuple]:
        frame = {"M1": self.mt5.TIMEFRAME_M1, "M5": self.mt5.TIMEFRAME_M5,
                 "M15": self.mt5.TIMEFRAME_M15, "H1": self.mt5.TIMEFRAME_H1,
                 "D1": self.mt5.TIMEFRAME_D1}[tf]
        r = self.mt5.copy_rates_range(symbol, frame, datetime.fromtimestamp(lo, UTC),
                                      datetime.fromtimestamp(hi, UTC))
        if r is None:
            return []
        return [(int(b["time"]), float(b["open"]), float(b["high"]), float(b["low"]),
                 float(b["close"]), int(b["spread"])) for b in r if lo <= int(b["time"]) <= hi]

    def close(self) -> None:
        self.mt5.shutdown()


def stable(term, symbol, tf, lo, hi):
    a = term.rates(symbol, tf, lo, hi)
    return a if a == term.rates(symbol, tf, lo, hi) else None


def parse_pr128_note(text: str) -> tuple[list[dict], dict[str, str]]:
    """Kept days with offsets, and the M1 gap cell per date, from a PR #128 V2 note."""
    days, gaps = [], {}
    for m in re.finditer(r"^\| (\d{4}-\d\d-\d\d) \| (yes|DROPPED) \| (\S+)/(\S+) \| [^|]+ \| \d+ \| \d+ \|",
                         text, re.M):
        if m[2] == "yes" and m[3] == m[4] and m[3] != "None":
            days.append({"date": m[1], "offset_h": int(m[3])})
    for m in re.finditer(r"^\| (\d{4}-\d\d-\d\d) \| yes \| ([^|]+) \| ([^|]+) \|$", text, re.M):
        gaps[m[1]] = m[3].strip()
    return days, gaps


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat()


def m1_check(bars, m1, step, digits, off_s):
    """Return {bar_time: status} and the list of failures for bars of size `step`."""
    have = {b[0] for b in bars}
    status, fails = {}, []
    for b in bars:
        inside = [x for x in m1 if b[0] <= x[0] < b[0] + step]
        agg = aggregate_present_m1(m1, b[0]) if step == 900 else (
            (inside[0][1], max(x[2] for x in inside), min(x[3] for x in inside), inside[-1][4])
            if inside else None)
        ok = agg is not None and tuple(round(v, digits) for v in agg) == tuple(
            round(v, digits) for v in b[1:5])
        status[b[0]] = ("FAIL" if not ok else "PASS" if len(inside) == step // 60
                        else "PARTIAL_M1_CHECK")
        if not ok:
            fails.append(iso(b[0] - off_s))
    for t in sorted({x[0] - (x[0] % step) for x in m1} - have):
        fails.append(iso(t - off_s) + " (M1 without bar)")
    return status, fails


def capture_symbol(term, symbol, note_text, m15_csv_text, captured, point):
    digits, live_point = term.info(symbol)
    days, gap_cells = parse_pr128_note(note_text)
    m15_rows = {r.split(",", 1)[0]: r for r in m15_csv_text.splitlines()[1:]}
    out = {tf: [] for tf in ("M1", "M5", "H1", "M15", "D1")}
    meta = {tf: [] for tf in out}
    report = {"symbol": symbol, "digits": digits, "point_host": point, "point_live": live_point,
              "days": [], "d1": []}
    for d in days:
        off_s = d["offset_h"] * 3600
        day0 = int(datetime.fromisoformat(d["date"]).replace(tzinfo=UTC).timestamp()) + off_s
        r = {"date": d["date"], "offset_h": d["offset_h"], "kept": False}
        reads = {tf: stable(term, symbol, tf, day0, day0 + 86400 - STEP[tf])
                 for tf in ("M1", "M5", "M15", "H1")}
        if any(v is None for v in reads.values()):
            r["reason"] = "unstable read: " + ",".join(k for k, v in reads.items() if v is None)
            report["days"].append(r)
            continue
        m1 = reads["M1"]
        have1 = {b[0] for b in m1}
        gap1 = [datetime.fromtimestamp(t - off_s, UTC).strftime("%H:%M")
                for t in range(day0, day0 + 86400, 60) if t not in have1]
        gap_cell = (len(gap1) and compress_minutes(gap1)) or "none"
        r["m1_gaps"] = gap_cell
        if gap_cell != gap_cells.get(d["date"]):
            r["reason"] = f"M1 gap list differs from PR #128 ({gap_cells.get(d['date'])})"
            report["days"].append(r)
            continue
        got15 = {datetime.fromtimestamp(b[0] - off_s, UTC).strftime("%Y-%m-%d %H:%M:%S"):
                 ",".join([datetime.fromtimestamp(b[0] - off_s, UTC).strftime("%Y-%m-%d %H:%M:%S")]
                          + [fmt_price(x, digits) for x in b[1:5]]) for b in reads["M15"]}
        if any(m15_rows.get(k) != v for k, v in got15.items()) or \
                sum(k.startswith(d["date"]) for k in m15_rows) != len(got15):
            r["reason"] = "M15 OHLC differs from PR #128 rows"
            report["days"].append(r)
            continue
        fails, counts = [], {}
        for tf in ("M5", "M15", "H1"):
            bars = reads[tf]
            st, f = m1_check(bars, m1, STEP[tf], digits, off_s)
            fails += [f"{tf} {x}" for x in f]
            exp = range(day0, day0 + 86400, STEP[tf])
            missing = [iso(t - off_s) for t in exp if t not in {b[0] for b in bars}]
            counts[tf] = {"bars": len(bars), "missing": missing,
                          "PASS": sum(v == "PASS" for v in st.values()),
                          "PARTIAL_M1_CHECK": sum(v == "PARTIAL_M1_CHECK" for v in st.values()),
                          "FAIL": sum(v == "FAIL" for v in st.values())}
            r.setdefault("_status", {})[tf] = st
        r["counts"] = counts
        if fails:
            r["reason"] = "M1 aggregate mismatch: " + "; ".join(fails[:5])
            report["days"].append(r)
            continue
        r["kept"] = True
        for tf in ("M1", "M5", "M15", "H1"):
            st = r["_status"].get(tf, {})
            for b in reads[tf]:
                if tf != "M15":
                    out[tf].append(",".join([iso(b[0] - off_s)] + [fmt_price(x, digits) for x in b[1:5]]))
                meta[tf].append(",".join([iso(b[0] - off_s), str(b[5]),
                                          fmt_price(b[5] * point, digits), st.get(b[0], "")]))
        del r["_status"]
        report["days"].append(r)

    kept = [d for d, r in zip(days, report["days"]) if r["kept"]]
    if kept:
        off_s = kept[0]["offset_h"] * 3600
        first = datetime.fromisoformat(days[0]["date"]).replace(tzinfo=UTC)
        last = datetime.fromisoformat(days[-1]["date"]).replace(tzinfo=UTC) + timedelta(days=1)
        lo = int(first.timestamp()) - 86400 + off_s
        hi = int(last.timestamp()) + 86400 + off_s
        d1 = stable(term, symbol, "D1", lo, hi)
        if d1 is None:
            report["d1_error"] = "unstable D1 read"
            d1 = []
        if len({k["offset_h"] for k in kept}) != 1:
            report["d1_error"] = "offsets differ across the day set; D1 not written"
            d1 = []
        m1_all = {}
        for row in out["M1"]:
            t, *v = row.split(",")
            m1_all[int(datetime.fromisoformat(t).timestamp())] = tuple(float(x) for x in v)
        span_lo, span_hi = int(first.timestamp()), int(last.timestamp())
        for b in d1:
            open_utc = b[0] - off_s
            close_utc = open_utc + 86400
            ny = datetime.fromtimestamp(open_utc, UTC).astimezone(ZoneInfo("America/New_York"))
            entry = {"server_date": datetime.fromtimestamp(b[0], UTC).strftime("%Y-%m-%d"),
                     "open_utc": iso(open_utc), "close_utc": iso(close_utc),
                     "open_is_17_ny": ny.strftime("%H:%M") == "17:00"}
            if close_utc > int(captured.timestamp()):
                entry["status"] = "EXCLUDED_NOT_CLOSED_AT_CAPTURE"
                report["d1"].append(entry)
                continue
            if open_utc < span_lo or close_utc > span_hi:
                check = "NOT_EVALUATED_OUTSIDE_M1_RANGE"
            else:
                sub = [(t,) + m1_all[t] for t in sorted(m1_all) if open_utc <= t < close_utc]
                agg = (sub[0][1], max(x[2] for x in sub), min(x[3] for x in sub), sub[-1][4]) if sub else None
                ok = agg is not None and tuple(round(v, digits) for v in agg) == tuple(
                    round(v, digits) for v in b[1:5])
                check = "FAIL" if not ok else "PASS" if len(sub) == 1440 else "PARTIAL_M1_CHECK"
            entry["status"] = check
            report["d1"].append(entry)
            out["D1"].append(",".join([iso(open_utc)] + [fmt_price(x, digits) for x in b[1:5]]))
            meta["D1"].append(",".join([iso(open_utc), str(b[5]), fmt_price(b[5] * point, digits),
                                        check, entry["server_date"]]))
    return out, meta, report


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--symbols", nargs="+", default=["BTCUSD", "ETHUSD"])
    p.add_argument("--m15-dir", required=True, help="dir with <SYM>_M15_recorded.csv/.PROVENANCE.md")
    p.add_argument("--metadata-dir", required=True, help="host_captured symbol metadata dir")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH"))
    p.add_argument("--server-name", required=True,
                   help="server shown in the terminal journal (not readable via allowed calls)")
    args = p.parse_args(argv)
    captured = datetime.now(UTC)
    os.makedirs(args.out_dir, exist_ok=True)
    term = Terminal(args.terminal_path)
    reports = []
    try:
        for sym in args.symbols:
            with open(os.path.join(args.m15_dir, f"{sym}_M15_recorded.PROVENANCE.md"), encoding="utf-8") as f:
                note = f.read()
            with open(os.path.join(args.m15_dir, f"{sym}_M15_recorded.csv"), encoding="utf-8") as f:
                m15 = f.read()
            with open(os.path.join(args.metadata_dir, f"{sym}.json"), encoding="utf-8") as f:
                point = float(json.load(f)["fields"]["point"])
            out, meta, rep = capture_symbol(term, sym, note, m15, captured, point)
            files = {}
            for tf in ("M1", "M5", "H1", "D1"):
                path = os.path.join(args.out_dir, f"{sym}_{tf.lower()}.csv")
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(OHLC_HEADER + "".join(r + "\n" for r in out[tf]))
                files[os.path.basename(path)] = sha256(path)
            for tf in ("M1", "M5", "M15", "H1", "D1"):
                path = os.path.join(args.out_dir, f"{sym}_{tf.lower()}_meta.csv")
                head = "timestamp_utc,spread_points,spread_price,m1_check" + (
                    ",server_date" if tf == "D1" else "")
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(head + "\n" + "".join(r + "\n" for r in meta[tf]))
                files[os.path.basename(path)] = sha256(path)
            rep["files"] = files
            rep["m15_reference_sha256"] = hashlib.sha256(m15.encode("utf-8")).hexdigest()
            reports.append(rep)
            kept = sum(r["kept"] for r in rep["days"])
            print(sym, f"kept={kept}/{len(rep['days'])}", "point", point, rep["point_live"])
            for r in rep["days"]:
                c = r.get("counts", {})
                print(" ", r["date"], r["kept"], r.get("reason", ""),
                      {k: (v["bars"], v["PARTIAL_M1_CHECK"], v["FAIL"], len(v["missing"])) for k, v in c.items()})
            for e in rep["d1"]:
                print("  D1", e)
    finally:
        term.close()
    summary = {"captured_at_utc": captured.isoformat(), "server": args.server_name,
               "terminal": redact_host_path(args.terminal_path), "peak_working_set_mb": peak_working_set_mb(),
               "symbols": reports}
    with open(os.path.join(args.out_dir, "capture_report.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    ok = all(r["kept"] for rep in reports for r in rep["days"])
    print("ALL_DAYS_KEPT" if ok else "DAYS_DROPPED", "PEAK_WORKING_SET_MB", summary["peak_working_set_mb"])
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
