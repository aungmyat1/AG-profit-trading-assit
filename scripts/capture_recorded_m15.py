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

Method RECORDED_M15_V1 is the default above. RECORDED_M15_V2 is any run that uses one of
the options below; its provenance names the method and every option in effect.

- --window HH:MM-HH:MM: M15 window per day (UTC, last bar open inclusive). M1 bars are
  read to the last minute of the last M15 bar.
- --all-days: the day set is contiguous calendar days, not weekdays.
- --offset-method reference-symbol:<SYM>: the offset is measured with step 1 on <SYM>
  (never on the captured symbol). Weekdays use <SYM>'s same-day offset. A Saturday or
  Sunday keeps an offset only if the adjacent Friday and Monday offsets are both measured
  and agree; otherwise the day is dropped.
- --list-gaps: a missing M15 or M1 bar does not drop the day; every missing bar is listed
  in the provenance and never filled. The M1 cross-check compares each present M15 bar
  with its present M1 bars; an M1 bar without its M15 bar fails the cross-check.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
HEADER = "timestamp_utc,open,high,low,close\n"
HEADER_SPREAD = "timestamp_utc,open,high,low,close,spread_points\n"
WINDOW_BARS_M15 = 64  # 00:00 .. 15:45 UTC
WINDOW_BARS_M1 = 960  # 00:00 .. 15:59 UTC
BREAK_TOLERANCE_S = 10 * 60  # break edge must sit within 10 min of a whole hour
SEARCH_BEFORE_S = 2 * 3600  # offsets searched: -2h .. +7h
SEARCH_AFTER_S = 7 * 3600
DEFAULT_WINDOW = "00:00-15:45"
METHOD_V2 = "RECORDED_M15_V2"


def parse_window(text: str) -> tuple[int, int]:
    """'HH:MM-HH:MM' -> (first, last) M15 bar open in minutes after 00:00 UTC."""
    m = re.fullmatch(r"(\d\d):(\d\d)-(\d\d):(\d\d)", text)
    if not m:
        raise argparse.ArgumentTypeError(f"window must be HH:MM-HH:MM: {text}")
    if any(int(h) > 23 for h in (m[1], m[3])) or any(int(mm) > 59 for mm in (m[2], m[4])):
        raise argparse.ArgumentTypeError(f"window times must be valid HH:MM clock times: {text}")
    a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
    if a % 15 or b % 15 or not 0 <= a <= b < 1440:
        raise argparse.ArgumentTypeError(f"window must be on M15 boundaries within one day: {text}")
    return a, b


def days_ending(end: date, count: int) -> list[date]:
    return [end - timedelta(days=i) for i in range(count - 1, -1, -1)]


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


def aggregate_present_m1(m1: list[tuple], m15_open: int) -> tuple | None:
    """--list-gaps: aggregate whatever M1 bars exist in the M15 bar; None if there are none."""
    bars = [b for b in m1 if m15_open <= b[0] < m15_open + 900]
    if not bars:
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

    def point(self, symbol: str) -> float:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise SystemExit(f"symbol not found: {symbol}")
        return float(info.point)

    def rates(self, symbol: str, tf: str, lo: int, hi: int, with_spread: bool = False) -> list[tuple]:
        frame = {"M1": self.mt5.TIMEFRAME_M1, "M15": self.mt5.TIMEFRAME_M15}[tf]
        r = self.mt5.copy_rates_range(symbol, frame, datetime.fromtimestamp(lo, UTC),
                                      datetime.fromtimestamp(hi, UTC))
        if r is None:
            return []
        return [(int(b["time"]), float(b["open"]), float(b["high"]), float(b["low"]),
                 float(b["close"])) + ((int(b["spread"]),) if with_spread else ())
                for b in r if lo <= int(b["time"]) <= hi]

    def close(self) -> None:
        self.mt5.shutdown()


def stable_rates(term: Terminal, symbol: str, tf: str, lo: int, hi: int,
                 with_spread: bool = False) -> list[tuple] | None:
    kw = {"with_spread": True} if with_spread else {}
    a = term.rates(symbol, tf, lo, hi, **kw)
    b = term.rates(symbol, tf, lo, hi, **kw)
    return a if a == b else None


def measure_offset(term: Terminal, symbol: str, d: date) -> dict:
    """Step 1 on `symbol` for day d: {'open': h|None, 'close': h|None, 'reason'?: str}."""
    offsets: dict = {}
    for side, anchor in (("open", ny_rollover_epoch(d - timedelta(days=1))),
                         ("close", ny_rollover_epoch(d))):
        lo, hi = anchor - SEARCH_BEFORE_S, anchor + SEARCH_AFTER_S
        m1 = stable_rates(term, symbol, "M1", lo, hi)
        if m1 is None:
            offsets["reason"] = f"unstable M1 read around {side} rollover"
            return offsets
        brk = largest_break([b[0] for b in m1], lo, hi)
        offsets[side] = offset_from_break(anchor, brk, side)
    if offsets["open"] is None or offsets["close"] is None:
        offsets["reason"] = "rollover break not located; offset unmeasured"
    elif offsets["open"] != offsets["close"]:
        offsets["reason"] = "open/close rollover offsets disagree"
    return offsets


def reference_offset(term: Terminal, ref: str, d: date) -> dict:
    """Offset for day d taken from reference symbol `ref` (see module docstring)."""
    if d.weekday() < 5:
        o = measure_offset(term, ref, d)
        o["source"] = f"{ref} {d.isoformat()}"
        if "reason" in o:
            o["reason"] = f"reference {ref}: {o['reason']}"
        return o
    fri = d - timedelta(days=d.weekday() - 4)
    mon = d + timedelta(days=7 - d.weekday())
    of, om = measure_offset(term, ref, fri), measure_offset(term, ref, mon)
    o = {"open": of.get("open") if "reason" not in of else None,
         "close": om.get("open") if "reason" not in om else None,
         "source": f"{ref} Fri {fri.isoformat()} / Mon {mon.isoformat()}"}
    if "reason" in of or "reason" in om:
        o["reason"] = f"reference {ref}: adjacent Fri/Mon offset unmeasured"
    elif o["open"] != o["close"]:
        o["reason"] = f"reference {ref}: adjacent Fri/Mon offsets disagree"
    return o


def utc_labels(stamps: list[int], off_s: int) -> list[str]:
    return [datetime.fromtimestamp(t - off_s, UTC).strftime("%H:%M") for t in stamps]


def check_day(term: Terminal, symbol: str, d: date, digits: int,
              window: tuple[int, int] = (0, 945), ref_symbol: str | None = None,
              list_gaps: bool = False, with_spread: bool = False) -> dict:
    res: dict = {"date": d.isoformat(), "kept": False}
    offsets = reference_offset(term, ref_symbol, d) if ref_symbol else measure_offset(term, symbol, d)
    if ref_symbol:
        res["offset_source"] = offsets["source"]
    if "open" not in offsets:
        res["reason"] = offsets["reason"]
        return res
    # An unstable close-edge read returns no 'close' key; record the drop instead of raising.
    res["offset_open_h"], res["offset_close_h"] = offsets["open"], offsets.get("close")
    if "reason" in offsets:
        res["reason"] = offsets["reason"]
        return res
    off_s = offsets["open"] * 3600
    res["offset_h"] = offsets["open"]

    n15 = (window[1] - window[0]) // 15 + 1
    n1 = n15 * 15
    start = int(datetime.combine(d, time(0, 0), UTC).timestamp()) + off_s + window[0] * 60
    m15 = stable_rates(term, symbol, "M15", start, start + (n15 - 1) * 900, with_spread)
    m1 = stable_rates(term, symbol, "M1", start, start + (n1 - 1) * 60)
    if m15 is None or m1 is None:
        res["reason"] = "unstable M15/M1 read in window"
        return res
    res["m15_bars"], res["m1_bars"] = len(m15), len(m1)
    exp15 = [start + 900 * i for i in range(n15)]
    exp1 = [start + 60 * i for i in range(n1)]
    if list_gaps:
        have15, have1 = {b[0] for b in m15}, {b[0] for b in m1}
        res["gaps_m15"] = utc_labels([t for t in exp15 if t not in have15], off_s)
        res["gaps_m1"] = utc_labels([t for t in exp1 if t not in have1], off_s)
        if not m15:
            res["reason"] = "no M15 bars in window"
            return res
    else:
        if [b[0] for b in m15] != exp15:
            res["reason"] = f"M15 gap: {len(m15)}/{n15} bars"
            return res
        if [b[0] for b in m1] != exp1:
            res["reason"] = f"M1 gap: {len(m1)}/{n1} bars"
            return res
    mismatches = []
    for bar in m15:
        agg = aggregate_m1(m1, bar[0]) if not list_gaps else aggregate_present_m1(m1, bar[0])
        got = tuple(round(x, digits) for x in bar[1:5])
        if agg is None or tuple(round(x, digits) for x in agg) != got:
            mismatches.append(datetime.fromtimestamp(bar[0] - off_s, UTC).strftime("%H:%M"))
    if list_gaps:
        orphan = sorted({t - (t - start) % 900 for t in have1} - have15)
        mismatches += [f"{x} (M1 without M15)" for x in utc_labels(orphan, off_s)]
    checked = len(m15)
    res["m1_crosscheck"] = (f"PASS {checked}/{checked}" if not mismatches
                            else f"FAIL {len(mismatches)}/{checked}")
    if mismatches:
        res["reason"] = "M15 != M1 aggregate at " + ",".join(mismatches[:5])
        return res
    res["kept"] = True
    res["partial_m1"] = [datetime.fromtimestamp(b[0] - off_s, UTC).strftime("%H:%M") for b in m15
                         if sum(b[0] <= x[0] < b[0] + 900 for x in m1) != 15]
    res["rows"] = [
        ",".join([datetime.fromtimestamp(b[0] - off_s, UTC).strftime("%Y-%m-%d %H:%M:%S")]
                 + [fmt_price(x, digits) for x in b[1:5]] + [str(x) for x in b[5:]])
        for b in m15
    ]
    return res


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def redact_host_path(raw: str | None) -> str:
    """AGENTS.md rule 4: record host paths as <HOST_SCRATCHPAD>/<file name> at capture time, never raw."""
    if not raw:
        return "default"
    return "<HOST_SCRATCHPAD>/" + re.split(r"[\\/]", raw.rstrip("\\/"))[-1]


def is_v2(args) -> bool:
    return (args.window != DEFAULT_WINDOW or args.all_days or args.list_gaps
            or args.offset_method != "rollover")


def write_note(path: str, args, out: str, digest: str, results: list[dict], captured: datetime,
               peak_mb: float | None) -> None:
    if is_v2(args):
        return write_note_v2(path, args, out, digest, results, captured, peak_mb)
    lines = [
        f"# {os.path.basename(out)} provenance",
        "",
        f"- sha256: `{digest}`",
        f"- capture date (UTC): {captured.strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"- terminal/server: {args.server_name} (terminal `{redact_host_path(args.terminal_path)}`)",
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


def write_note_v2(path: str, args, out: str, digest: str, results: list[dict], captured: datetime,
                  peak_mb: float | None) -> None:
    ref = args.offset_method.split(":", 1)[1] if args.offset_method != "rollover" else None
    kind = "calendar days" if args.all_days else "weekdays"
    lines = [
        f"# {os.path.basename(out)} provenance",
        "",
        f"- sha256: `{digest}`",
        f"- capture date (UTC): {captured.strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"- terminal/server: {args.server_name} (terminal `{redact_host_path(args.terminal_path)}`)",
        f"- method: {METHOD_V2} (window {args.window} UTC; day set {kind}; offset method "
        f"{args.offset_method}; gaps {'listed, never filled' if args.list_gaps else 'drop the day'})",
        f"- symbol: {args.symbol}; timeframe M15; window {args.window} UTC per day",
        f"- day set: {len(results)} contiguous {kind} ending {results[-1]['date']}, "
        "fixed before capture; dropped days are not replaced",
    ]
    if ref:
        lines.append(
            f"- offset method: measured on {ref}, never on {args.symbol} and never assumed. Per "
            f"{ref} day, M1 rollover break located at 17:00 America/New_York on both edges "
            "(open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, "
            "both edges must agree. Weekdays use the same-day offset; Saturday/Sunday keep an "
            "offset only if the adjacent Friday and Monday offsets are both measured and agree "
            "(table shows Fri/Mon), else the day is dropped")
    else:
        lines.append(
            "- offset method: per day, M1 rollover break located at 17:00 America/New_York on "
            "both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); "
            "offset = server label - UTC, whole hours, both edges must agree")
    lines += [
        "- M1 cross-check: every M15 bar must equal OHLC aggregated from its "
        + ("present M1 bars; an M1 bar without its M15 bar fails" if args.list_gaps else "15 M1 bars")
        + " (exact at symbol digits); every range read twice and must match",
        f"- capture script: scripts/capture_recorded_m15.py (peak working set {peak_mb} MB)",
        "",
        "| date | kept | offset (open/close, h) | offset source | M15 bars | M1 bars | "
        "M1 cross-check | reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['date']} | {'yes' if r['kept'] else 'DROPPED'} | "
            f"{r.get('offset_open_h')}/{r.get('offset_close_h')} | {r.get('offset_source', 'own')} | "
            f"{r.get('m15_bars', '-')} | {r.get('m1_bars', '-')} | "
            f"{r.get('m1_crosscheck', 'NOT_EVALUATED')} | {r.get('reason', '')} |"
        )
    if args.list_gaps:
        lines += ["", "## Gaps (UTC bar opens; missing bars are never filled)", "",
                  "| date | kept | missing M15 | missing M1 |", "|---|---|---|---|"]
        for r in results:
            g15, g1 = r.get("gaps_m15"), r.get("gaps_m1")
            lines.append(
                f"| {r['date']} | {'yes' if r['kept'] else 'DROPPED'} | "
                f"{'NOT_EVALUATED' if g15 is None else (len(g15) and ', '.join(g15)) or 'none'} | "
                f"{'NOT_EVALUATED' if g1 is None else (len(g1) and compress_minutes(g1)) or 'none'} |")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def append_spread_note(path: str, symbol: str, point: float, results: list[dict]) -> None:
    """--with-spread: spread units and the PARTIAL_M1_CHECK bar list, after the standard note."""
    partial = [f"{r['date']} {t}" for r in results if r["kept"] for t in r.get("partial_m1", [])]
    lines = [
        "", "## Spread (--with-spread)", "",
        "- column `spread_points`: the MqlRates `spread` field of each M15 bar, an integer in "
        f"points; price = spread_points x point. Point for {symbol} read with symbol_info at "
        f"capture: {point!r}. The value is the terminal's per-bar spread field; it is not a quote "
        "observed at a known instant.",
        "", "## PARTIAL_M1_CHECK bars", "",
        "M15 bars of kept days whose M1 cross-check covered fewer than 15 M1 bars:",
        "",
    ]
    lines += [f"- {x}" for x in partial] or ["- none (every kept M15 bar was checked against all 15 M1 bars)"]
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def compress_minutes(labels: list[str]) -> str:
    """'HH:MM' minute labels -> 'HH:MM-HH:MM (n)' runs, so long M1 gaps stay readable."""
    mins = [int(x[:2]) * 60 + int(x[3:]) for x in labels]
    runs, a = [], mins[0]
    for p, q in zip(mins, mins[1:] + [None]):
        if q != p + 1:
            runs.append(f"{a // 60:02d}:{a % 60:02d}" + ("" if p == a else
                        f"-{p // 60:02d}:{p % 60:02d} ({p - a + 1})"))
            a = q
    return ", ".join(runs)


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
    p.add_argument("--window", default=DEFAULT_WINDOW, help="HH:MM-HH:MM UTC, M15 bar opens")
    p.add_argument("--all-days", action="store_true", help="calendar days instead of weekdays")
    p.add_argument("--offset-method", default="rollover",
                   help="rollover | reference-symbol:<SYM>")
    p.add_argument("--with-spread", action="store_true",
                   help="add the MqlRates spread (points) as a spread_points column")
    p.add_argument("--list-gaps", action="store_true",
                   help="list missing bars in the provenance instead of dropping the day")
    args = p.parse_args(argv)
    window = parse_window(args.window)
    ref_symbol = None
    if args.offset_method != "rollover":
        m = re.fullmatch(r"reference-symbol:(\S+)", args.offset_method)
        if not m:
            p.error("--offset-method must be rollover or reference-symbol:<SYM>")
        ref_symbol = m[1]

    captured = datetime.now(UTC)
    end = args.end_date or last_completed_weekday(captured)
    days = days_ending(end, args.days) if args.all_days else weekdays_ending(end, args.days)

    term = Terminal(args.terminal_path)
    results: list[dict] = []
    try:
        digits = term.digits(args.symbol)
        point = term.point(args.symbol) if args.with_spread else None
        if ref_symbol:
            term.digits(ref_symbol)  # fail fast if the reference symbol is absent
        # warm-up read so the terminal syncs history before the per-day reads
        span_lo = ny_rollover_epoch(days[0] - timedelta(days=1)) - SEARCH_BEFORE_S
        span_hi = ny_rollover_epoch(days[-1]) + SEARCH_AFTER_S
        term.rates(args.symbol, "M1", span_lo, span_hi)
        term.rates(args.symbol, "M15", span_lo, span_hi)
        if ref_symbol:
            term.rates(ref_symbol, "M1", span_lo - 3 * 86400, span_hi + 3 * 86400)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(HEADER_SPREAD if args.with_spread else HEADER)
        for d in days:
            r = check_day(term, args.symbol, d, digits, window, ref_symbol, args.list_gaps,
                          args.with_spread)
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
    if args.with_spread:
        append_spread_note(args.note, args.symbol, point, results)
    print("SHA256", digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
