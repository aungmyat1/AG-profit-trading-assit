"""scripts/capture_recorded_m15.py: read-only surface (static) and offset/aggregation logic."""
import ast
import importlib.util
import re
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_recorded_m15.py"
ALLOWED_MT5_ATTRS = {"initialize", "copy_rates_range", "symbol_info", "shutdown",
                     "TIMEFRAME_M1", "TIMEFRAME_M15"}


def _load():
    spec = importlib.util.spec_from_file_location("capture_recorded_m15", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_never_mentions_mutation_or_order_surfaces():
    src = SCRIPT.read_text(encoding="utf-8").lower()
    for word in ("order_send", "order_check", "order_calc", "orders", "positions",
                 "position", "trade_request", "order"):
        assert word not in src, word


def test_only_allowed_mt5_attributes_are_used():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    mt5_aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            assert "MetaTrader5" not in mods or isinstance(node, ast.Import), "no from-imports"
            for a in getattr(node, "names", []):
                if a.name == "MetaTrader5":
                    mt5_aliases.add(a.asname or a.name)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"getattr", "eval", "exec"}:
            raise AssertionError("dynamic attribute access is not allowed")
    assert mt5_aliases == {"mt5"}
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            base = node.value
            if isinstance(base, ast.Name) and base.id == "mt5":
                used.add(node.attr)
            if isinstance(base, ast.Attribute) and base.attr == "mt5":  # self.mt5.<attr>
                used.add(node.attr)
    assert used and used <= ALLOWED_MT5_ATTRS, used - ALLOWED_MT5_ATTRS


def _ep(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp())


def test_offset_measured_from_daily_break_edt():
    m = _load()
    anchor = m.ny_rollover_epoch(date(2026, 10, 7))  # 21:00Z (EDT)
    assert anchor == _ep(2026, 10, 7, 21)
    lo, hi = anchor - m.SEARCH_BEFORE_S, anchor + m.SEARCH_AFTER_S
    # server +3: bars to 23:57 label, break, resume 00:01 label
    times = [t for t in range(lo, hi + 1, 60)
             if not (_ep(2026, 10, 7, 23, 58) <= t <= _ep(2026, 10, 8, 0, 0))]
    brk = m.largest_break(times, lo, hi)
    assert m.offset_from_break(anchor, brk, "open") == 3
    assert m.offset_from_break(anchor, brk, "close") == 3


def test_weekend_edges_and_unlocatable_break():
    m = _load()
    fri = m.ny_rollover_epoch(date(2026, 10, 9))
    lo, hi = fri - m.SEARCH_BEFORE_S, fri + m.SEARCH_AFTER_S
    times = [t for t in range(lo, hi + 1, 60) if t <= _ep(2026, 10, 9, 23, 56)]
    assert m.offset_from_break(fri, m.largest_break(times, lo, hi), "close") == 3
    sun = m.ny_rollover_epoch(date(2026, 10, 4))
    lo, hi = sun - m.SEARCH_BEFORE_S, sun + m.SEARCH_AFTER_S
    times = [t for t in range(lo, hi + 1, 60) if t >= _ep(2026, 10, 5, 0, 1)]
    assert m.offset_from_break(sun, m.largest_break(times, lo, hi), "open") == 3
    # a break in mid-hour cannot be read as an offset
    assert m.offset_from_break(fri, (_ep(2026, 10, 9, 23, 20), _ep(2026, 10, 9, 23, 35)), "open") is None


def test_aggregate_m1_requires_all_15_bars():
    m = _load()
    t0 = _ep(2026, 10, 6, 3)
    m1 = [(t0 + 60 * i, 1.0 + i, 2.0 + i, 0.5 - i, 1.5 + i) for i in range(15)]
    assert m.aggregate_m1(m1, t0) == (1.0, 16.0, -13.5, 15.5)
    assert m.aggregate_m1(m1[:-1], t0) is None


def test_day_set_is_fixed_contiguous_weekdays():
    m = _load()
    days = m.weekdays_ending(date(2026, 10, 9), 10)
    assert days[0] == date(2026, 9, 28) and days[-1] == date(2026, 10, 9) and len(days) == 10
    assert m.last_completed_weekday(datetime(2026, 10, 10, 12, tzinfo=timezone.utc)) == date(2026, 10, 9)
    assert not re.search(r"\d", m.HEADER)


def test_terminal_path_is_redacted_in_provenance():
    mod = _load()
    assert mod.redact_host_path(r"C:\\Users\\someone\\AppData\\Roaming\\MetaTrader 5\\terminal64.exe") == \
        "<HOST_SCRATCHPAD>/terminal64.exe"
    assert mod.redact_host_path("/home/someone/mt5/terminal64.exe") == "<HOST_SCRATCHPAD>/terminal64.exe"
    assert mod.redact_host_path(None) == "default"
    note = (SCRIPT.parents[1] / "tests/fixtures/manual_ticket/GBPUSD_M15_recorded.PROVENANCE.md").read_text()
    assert "Users" not in note and ":\\" not in note


# --- default-output freeze -------------------------------------------------------------
# A deterministic fake terminal (server = UTC+3, 17:00 New York daily/weekend breaks, one
# M15/M1 mismatch day, one M1 gap day). Golden bytes in tests/fixtures/capture_recorded_m15_golden/
# were produced by the 5b67199 script before any option was added; the default CLI must
# still reproduce them byte for byte.
GOLDEN = SCRIPT.parents[1] / "tests" / "fixtures" / "capture_recorded_m15_golden"
SERVER_OFFSET_S = 3 * 3600
MISMATCH_UTC = _ep(2026, 10, 1, 10, 0)  # M15 high bumped on this bar
MISSING_M1_UTC = _ep(2026, 10, 6, 5, 7)  # this M1 bar is absent


class FakeTerminal:
    def __init__(self, path=None, always_open=(), missing_utc=()):
        self.always_open = set(always_open)
        self.missing_utc = set(missing_utc)

    def digits(self, symbol):
        return 2 if symbol in self.always_open else 5

    def _open(self, symbol, u):
        if u == MISSING_M1_UTC or u in self.missing_utc:
            return False
        if symbol in self.always_open:
            return True
        ny = datetime.fromtimestamp(u, timezone.utc).astimezone(_NY)
        day = ny.date()
        roll = int(datetime.combine(day, _T17, _NY).timestamp())
        if roll - 120 <= u < roll + 60:
            return False
        wd, after = ny.weekday(), u >= roll
        return not ((wd == 4 and after) or wd == 5 or (wd == 6 and not after))

    @staticmethod
    def _bar(symbol, u, digits):
        base = 30000.0 if digits == 2 else 1.1
        step = 0.37 if digits == 2 else 0.00001
        k = (u // 60 * 7919 + sum(map(ord, symbol))) % 1000
        o = round(base + k * step, digits)
        return (o, round(o + 3 * step, digits), round(o - 2 * step, digits),
                round(o + (k % 5 - 2) * step, digits))

    def rates(self, symbol, tf, lo, hi):
        d = self.digits(symbol)
        out = []
        if tf == "M1":
            for s in range(lo + (-lo) % 60, hi + 1, 60):
                if self._open(symbol, s - SERVER_OFFSET_S):
                    out.append((s,) + self._bar(symbol, s - SERVER_OFFSET_S, d))
            return out
        for s in range(lo + (-lo) % 900, hi + 1, 900):
            m1 = [(t,) + self._bar(symbol, t - SERVER_OFFSET_S, d) for t in range(s, s + 900, 60)
                  if self._open(symbol, t - SERVER_OFFSET_S)]
            if not m1:
                continue
            h = max(b[2] for b in m1)
            if s - SERVER_OFFSET_S == MISMATCH_UTC:
                h = round(h + 0.001, d)
            out.append((s, m1[0][1], h, min(b[3] for b in m1), m1[-1][4]))
        return out

    def close(self):
        pass


from zoneinfo import ZoneInfo as _ZI  # noqa: E402
from datetime import time as _time  # noqa: E402

_NY, _T17 = _ZI("America/New_York"), _time(17, 0)
FIXED_NOW = datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc)


def run_capture(mod, tmp_path, argv, terminal_factory=FakeTerminal):
    """Run mod.main(argv) against the fake terminal with a fixed clock; return (rc, csv, note)."""
    class _FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED_NOW

    mod.Terminal = terminal_factory
    mod.datetime = _FixedDT
    mod.peak_working_set_mb = lambda: 12.3
    out, note = tmp_path / "out.csv", tmp_path / "out.PROVENANCE.md"
    rc = mod.main(argv + ["--out", str(out), "--note", str(note), "--server-name", "FAKE-Server",
                          "--terminal-path", r"C:\Users\someone\mt5\terminal64.exe"])
    read = lambda p: p.read_bytes() if p.exists() else None  # noqa: E731
    return rc, read(out), read(note)


def test_default_output_is_byte_identical_to_5b67199(tmp_path):
    for symbol in ("EURUSD", "GBPUSD"):
        rc, csv_b, note_b = run_capture(_load(), tmp_path, ["--symbol", symbol])
        assert rc == 0
        assert csv_b == (GOLDEN / f"{symbol}_default.csv").read_bytes(), symbol
        assert note_b == (GOLDEN / f"{symbol}_default.PROVENANCE.md").read_bytes(), symbol


def test_v2_crypto_reference_offset_all_days_and_listed_gaps(tmp_path):
    m = _load()
    gap = _ep(2026, 10, 3, 22, 30)  # Saturday, one missing M1 inside a still-present M15 bar
    hole = [_ep(2026, 10, 4, 1, 0) + 60 * i for i in range(15)]  # Sunday, a whole M15 bar missing
    factory = lambda path=None: FakeTerminal(path, always_open={"BTCUSD"},  # noqa: E731
                                              missing_utc=[gap] + hole)
    rc, csv_b, note_b = run_capture(m, tmp_path, [
        "--symbol", "BTCUSD", "--end-date", "2026-10-09", "--days", "14", "--all-days",
        "--window", "00:00-23:45", "--offset-method", "reference-symbol:EURUSD", "--list-gaps"],
        terminal_factory=factory)
    assert rc == 0
    note = note_b.decode()
    rows = csv_b.decode().splitlines()[1:]
    assert "RECORDED_M15_V2" in note and "calendar days" in note
    # 14 days 2026-09-26..10-09; MISSING_M1_UTC (10-06 05:07) is listed, not a drop
    assert "| 2026-09-26 | yes | 3/3 | EURUSD Fri 2026-09-25 / Mon 2026-09-28 |" in note
    assert "| 2026-10-06 | yes | 3/3 | EURUSD 2026-10-06 | 96 | 1439 | PASS 96/96 |" in note
    assert "| 2026-10-04 | yes | 01:00 | 01:00-01:14 (15) |" in note
    assert "| 2026-10-03 | yes | none | 22:30 |" in note
    # the fake's +0.001 high bump rounds away at 2 digits, so 10-01 is clean here
    assert "DROPPED" not in note
    assert len(rows) == 14 * 96 - 1 and rows[0].startswith("2026-09-26 00:00:00,")
    assert not any(r.startswith("2026-10-04 01:00:00") for r in rows)  # never filled


def test_reference_offset_weekend_requires_agreeing_fri_and_mon():
    m = _load()
    seen = {}
    m.measure_offset = lambda term, sym, d: dict(seen[d])
    sat = date(2026, 10, 3)
    seen = {date(2026, 10, 2): {"open": 3, "close": 3}, date(2026, 10, 5): {"open": 3, "close": 3}}
    assert m.reference_offset(None, "EURUSD", sat) == {
        "open": 3, "close": 3, "source": "EURUSD Fri 2026-10-02 / Mon 2026-10-05"}
    seen[date(2026, 10, 5)] = {"open": 2, "close": 2}
    assert "disagree" in m.reference_offset(None, "EURUSD", date(2026, 10, 4))["reason"]
    seen[date(2026, 10, 5)] = {"open": None, "close": 3, "reason": "rollover break not located"}
    assert "unmeasured" in m.reference_offset(None, "EURUSD", sat)["reason"]


def test_window_rejects_non_clock_times():
    m = _load()
    for bad in ("00:75-02:00", "01:60-03:00", "24:00-24:15", "00:00-23:60"):
        try:
            m.parse_window(bad)
        except m.argparse.ArgumentTypeError as exc:
            assert "clock" in str(exc), bad
            continue
        raise AssertionError(bad)


def test_unstable_close_edge_is_dropped_not_keyerror():
    m = _load()
    m.measure_offset = lambda term, sym, d: {"open": 3, "reason": "unstable M1 read around close rollover"}
    res = m.check_day(None, "GBPUSD", date(2026, 10, 9), 5)
    assert res["kept"] is False and res["offset_close_h"] is None
    assert res["reason"] == "unstable M1 read around close rollover"


def test_window_and_method_parsing():
    m = _load()
    assert m.parse_window("00:00-15:45") == (0, 945) and m.parse_window("00:00-23:45") == (0, 1425)
    for bad in ("00:00-23:50", "10:00-09:00", "0:00-1:00"):
        try:
            m.parse_window(bad)
        except Exception:
            continue
        raise AssertionError(bad)
    assert m.days_ending(date(2026, 10, 9), 14)[0] == date(2026, 9, 26)
    assert m.compress_minutes(["01:00", "01:01", "01:02", "05:07"]) == "01:00-01:02 (3), 05:07"


class SpreadFakeTerminal(FakeTerminal):
    def point(self, symbol):
        return 0.00001

    def rates(self, symbol, tf, lo, hi, with_spread=False):
        bars = super().rates(symbol, tf, lo, hi)
        return [b + ((b[0] // 900 % 7 + 3,) if with_spread else ()) for b in bars]


def test_with_spread_adds_only_a_column_and_note_sections(tmp_path):
    rc, plain_csv, plain_note = run_capture(_load(), tmp_path, ["--symbol", "GBPUSD"])
    rc2, csv_b, note_b = run_capture(_load(), tmp_path, ["--symbol", "GBPUSD", "--with-spread"],
                                     terminal_factory=SpreadFakeTerminal)
    assert rc == rc2 == 0
    plain, spread = plain_csv.decode().splitlines(), csv_b.decode().splitlines()
    assert spread[0] == "timestamp_utc,open,high,low,close,spread_points"
    assert [r.rsplit(",", 1)[0] for r in spread[1:]] == plain[1:]
    assert all(r.rsplit(",", 1)[1].isdigit() for r in spread[1:])
    note = note_b.decode()
    assert note.split("\n## Spread")[0].split("- capture date")[1].split("\n", 1)[1] == \
        plain_note.decode().split("- capture date")[1].split("\n", 1)[1].rstrip("\n") + "\n"
    assert "points; price = spread_points x point" in note and "- none (every kept M15 bar" in note
