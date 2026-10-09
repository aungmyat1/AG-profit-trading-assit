"""Capture a recorded M15 OHLC fixture from a local MT5 terminal (read-only).

Allowed MetaTrader5 calls: initialize, copy_rates_range, symbol_info, shutdown.
Nothing else is called on the terminal; tests/test_capture_recorded_m15.py enforces
this statically.

Per day D (UTC), processed one at a time and appended to the output when clean:

1. Offset: the server-to-UTC offset is measured from that day's own M1 bars. The
   daily rollover break (and the weekend break) sits at 17:00 America/New_York. The
   break that opens day D (17:00 NY on D-1) and the break that closes it (17:00 NY on
   D) are each located in server-labelled M1 time; offset = server label - UTC
   instant, in whole hours. Both must be found and must agree, else the day is dropped.
2. Range: every M15 bar 00:00-15:45 UTC (64 bars) and every M1 bar 00:00-15:59 UTC
   (960 bars) must be present. Any gap drops the day.
3. Cross-check: each M15 bar must equal the OHLC aggregated from its 15 M1 bars,
   compared at the symbol's digits. Any mismatch drops the day.
4. Stability: each range is read twice; differing reads drop the day.

Dropped days are never patched or replaced. Fewer than --min-clean-days clean days
removes the output and exits non-zero (NOT_EVIDENCED) without writing provenance.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
HEADER = "timestamp_utc,open,high,low,close\n"
WINDOW_BARS_M15 = 64  # 00:00 .. 15:45 UTC
WINDOW_BARS_M1 = 960  # 00:00 .. 15:59 UTC
BREAK_TOLERANCE_S = 10 * 60  # break edge must sit within 10 min of a whole hour
SEARCH_BEFORE_S = 2 * 3600  # offsets searched: -2h .. +7h
SEARCH_AFTER_S = 7 * 3600


def weekdays_ending(end: date, count: int) -> list[date]:
    days: list[date] = []
    d = end
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def last_completed_weekday(now_utc: datetime) -> date:
    d = now_utc.date()
    while True:
        close_utc = datetime.combine(d, time(17, 0), NY).astimezone(UTC)
        if d.weekday() < 5 and close_utc <= now_utc:
            return d
        d -= timedelta(days=1)


def ny_rollover_epoch(d: date) -> int:
    """UTC epoch of 17:00 America/New_York on calendar day d."""
    return int(datetime.combine(d, time(17, 0), NY).timestamp())


def largest_break(times: list[int], lo: int, hi: int) -> tuple[int, int] | None:
    """Largest silence in [lo, hi] given M1 bar open times; window edges act as sentinels."""
    pts = [lo - 60] + [t for t in times if lo <= t <= hi] + [hi + 60]
    best = None
    for a, b in zip(pts[:-1], pts[1:]):
        if b - a > 60 and (best is None or b - a > best[1] - best[0]):
            best = (a, b)
    return best


def offset_from_break(anchor_utc: int, brk: tuple[int, int] | None, side: str) -> int | None:
    """Whole-hour offset from a located break.

    side='open': the session resumes after the break; its first bar opens at the
    anchor's server label (floor to the hour). side='close': the session stops before
    the break; the bar after its last bar is the anchor's server label (ceil to hour).
    """
    if brk is None:
        return None
    if side == "open":
        edge = brk[1]
        label = edge - edge % 3600
        if edge - label > BREAK_TOLERANCE_S:
            return None
    else:
        edge = brk[0] + 60
        label = edge + (-edge) % 3600
        if label - edge > BREAK_TOLERANCE_S:
            return None
    diff = label - anchor_utc
    if diff % 3600:
        return None
    return diff // 3600


def aggregate_m1(m1: list[tuple], m15_open: int) -> tuple | None:
    bars = [b for b in m1 if m15_open <= b[0] < m15_open + 900]
    if len(bars) != 15:
        return None
    return (bars[0][1], max(b[2] for b in bars), min(b[3] for b in bars), bars[-1][4])


def fmt_price(x: float, digits: int) -> str:
    return repr(round(float(x), digits))


def peak_working_set_mb() -> float | None:
    if os.name != "nt":
        return None

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(k32.GetCurrentProcess()),
                                                     ctypes.byref(pmc), pmc.cb):
        return None
    return round(pmc.PeakWorkingSetSize / 1048576, 1)


class Terminal:
    """Thin read-only wrapper; the only place the MT5 package is touched."""

    def __init__(self, path: str | None):
        import MetaTrader5 as mt5

        self.mt5 = mt5
        ok = mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            raise SystemExit("MT5 initialize failed")

    def digits(self, symbol: str) -> int:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise SystemExit(f"symbol not found: {symbol}")
        return int(info.digits)

    def rates(self, symbol: str, tf: str, lo: int, hi: int) -> list[tuple]:
        frame = {"M1": self.mt5.TIMEFRAME_M1, "M15": self.mt5.TIMEFRAME_M15}[tf]
        r = self.mt5.copy_rates_range(symbol, frame, datetime.fromtimestamp(lo, UTC),
                                      datetime.fromtimestamp(hi, UTC))
        if r is None:
            return []
        return [(int(b["time"]), float(b["open"]), float(b["high"]), float(b["low"]),
                 float(b["close"])) for b in r if lo <= int(b["time"]) <= hi]

    def close(self) -> None:
        self.mt5.shutdown()


def stable_rates(term: Terminal, symbol: str, tf: str, lo: int, hi: int) -> list[tuple] | None:
    a = term.rates(symbol, tf, lo, hi)
    b = term.rates(symbol, tf, lo, hi)
    return a if a == b else None


def check_day(term: Terminal, symbol: str, d: date, digits: int) -> dict:
    res: dict = {"date": d.isoformat(), "kept": False}
    offsets = {}
    for side, anchor in (("open", ny_rollover_epoch(d - timedelta(days=1))),
                         ("close", ny_rollover_epoch(d))):
        lo, hi = anchor - SEARCH_BEFORE_S, anchor + SEARCH_AFTER_S
        m1 = stable_rates(term, symbol, "M1", lo, hi)
        if m1 is None:
            res["reason"] = f"unstable M1 read around {side} rollover"
            return res
        brk = largest_break([b[0] for b in m1], lo, hi)
        offsets[side] = offset_from_break(anchor, brk, side)
    res["offset_open_h"], res["offset_close_h"] = offsets["open"], offsets["close"]
    if offsets["open"] is None or offsets["close"] is None:
        res["reason"] = "rollover break not located; offset unmeasured"
        return res
    if offsets["open"] != offsets["close"]:
        res["reason"] = "open/close rollover offsets disagree"
        return res
    off_s = offsets["open"] * 3600
    res["offset_h"] = offsets["open"]

    day0 = int(datetime.combine(d, time(0, 0), UTC).timestamp())
    m15 = stable_rates(term, symbol, "M15", day0 + off_s, day0 + off_s + 15 * 3600 + 45 * 60)
    m1 = stable_rates(term, symbol, "M1", day0 + off_s, day0 + off_s + 16 * 3600 - 60)
    if m15 is None or m1 is None:
        res["reason"] = "unstable M15/M1 read in window"
        return res
    res["m15_bars"], res["m1_bars"] = len(m15), len(m1)
    exp15 = [day0 + off_s + 900 * i for i in range(WINDOW_BARS_M15)]
    exp1 = [day0 + off_s + 60 * i for i in range(WINDOW_BARS_M1)]
    if [b[0] for b in m15] != exp15:
        res["reason"] = f"M15 gap: {len(m15)}/{WINDOW_BARS_M15} bars"
        return res
    if [b[0] for b in m1] != exp1:
        res["reason"] = f"M1 gap: {len(m1)}/{WINDOW_BARS_M1} bars"
        return res
    mismatches = []
    for bar in m15:
        agg = aggregate_m1(m1, bar[0])
        got = tuple(round(x, digits) for x in bar[1:])
        if agg is None or tuple(round(x, digits) for x in agg) != got:
            mismatches.append(datetime.fromtimestamp(bar[0] - off_s, UTC).strftime("%H:%M"))
    res["m1_crosscheck"] = "PASS 64/64" if not mismatches else f"FAIL {len(mismatches)}/64"
    if mismatches:
        res["reason"] = "M15 != M1 aggregate at " + ",".join(mismatches[:5])
        return res
    res["kept"] = True
    res["rows"] = [
        ",".join([datetime.fromtimestamp(b[0] - off_s, UTC).strftime("%Y-%m-%d %H:%M:%S")]
                 + [fmt_price(x, digits) for x in b[1:]])
        for b in m15
    ]
    return res


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def write_note(path: str, args, out: str, digest: str, results: list[dict], captured: datetime,
               peak_mb: float | None) -> None:
    lines = [
        f"# {os.path.basename(out)} provenance",
        "",
        f"- sha256: `{digest}`",
        f"- capture date (UTC): {captured.strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"- terminal/server: {args.server_name} (terminal `{args.terminal_path or 'default'}`)",
        f"- symbol: {args.symbol}; timeframe M15; window 00:00-15:45 UTC per day",
        f"- day set: {len(results)} contiguous weekdays ending {results[-1]['date']}, "
        "fixed before capture; dropped days are not replaced",
        "- offset method: per day, M1 rollover break located at 17:00 America/New_York on "
        "both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); "
        "offset = server label - UTC, whole hours, both edges must agree",
        "- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars "
        "(exact at symbol digits); every range read twice and must match",
        f"- capture script: scripts/capture_recorded_m15.py (peak working set {peak_mb} MB)",
        "",
        "| date | kept | offset (open/close, h) | M15 bars | M1 bars | M1 cross-check | reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['date']} | {'yes' if r['kept'] else 'DROPPED'} | "
            f"{r.get('offset_open_h')}/{r.get('offset_close_h')} | {r.get('m15_bars', '-')} | "
            f"{r.get('m1_bars', '-')} | {r.get('m1_crosscheck', 'NOT_EVALUATED')} | "
            f"{r.get('reason', '')} |"
        )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--symbol", default="GBPUSD")
    p.add_argument("--end-date", type=date.fromisoformat, default=None,
                   help="last day (UTC); default: most recent weekday past 17:00 NY")
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--min-clean-days", type=int, default=5)
    p.add_argument("--out", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH"))
    p.add_argument("--server-name", required=True,
                   help="server shown in the terminal journal (not readable via allowed calls)")
    args = p.parse_args(argv)

    captured = datetime.now(UTC)
    end = args.end_date or last_completed_weekday(captured)
    days = weekdays_ending(end, args.days)

    term = Terminal(args.terminal_path)
    results: list[dict] = []
    try:
        digits = term.digits(args.symbol)
        # warm-up read so the terminal syncs history before the per-day reads
        span_lo = ny_rollover_epoch(days[0] - timedelta(days=1)) - SEARCH_BEFORE_S
        span_hi = ny_rollover_epoch(days[-1]) + SEARCH_AFTER_S
        term.rates(args.symbol, "M1", span_lo, span_hi)
        term.rates(args.symbol, "M15", span_lo, span_hi)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(HEADER)
        for d in days:
            r = check_day(term, args.symbol, d, digits)
            if r["kept"]:
                with open(args.out, "a", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(r.pop("rows")) + "\n")
            print(f"{r['date']} kept={r['kept']} offset={r.get('offset_h')} "
                  f"xcheck={r.get('m1_crosscheck', 'NOT_EVALUATED')} {r.get('reason', '')}")
            results.append(r)
    finally:
        term.close()

    kept = sum(r["kept"] for r in results)
    peak_mb = peak_working_set_mb()
    print(f"KEPT={kept} DROPPED={len(results) - kept} PEAK_WORKING_SET_MB={peak_mb}")
    if kept < args.min_clean_days:
        os.remove(args.out)
        print("NOT_EVIDENCED: fewer than", args.min_clean_days, "clean days; output removed")
        return 2
    digest = sha256_file(args.out)
    write_note(args.note, args, args.out, digest, results, captured, peak_mb)
    print("SHA256", digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
