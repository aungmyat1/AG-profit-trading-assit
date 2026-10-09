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
