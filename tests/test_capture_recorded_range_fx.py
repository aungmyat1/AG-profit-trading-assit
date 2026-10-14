"""scripts/capture_recorded_range_fx.py: read-only surface (static), pin, time and gap logic."""
import ast
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "capture_recorded_range_fx.py"
REUSED = SCRIPTS / "capture_recorded_ccfd_tfs.py"
ALLOWED_MT5_ATTRS = {"initialize", "copy_rates_range", "symbol_info", "account_info", "shutdown",
                     "TIMEFRAME_M1", "TIMEFRAME_M5", "TIMEFRAME_M15", "TIMEFRAME_H1", "TIMEFRAME_D1"}
UTC = timezone.utc


def _load():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("capture_recorded_range_fx", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ts(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp())


def test_source_never_mentions_mutation_or_order_surfaces():
    src = SCRIPT.read_text(encoding="utf-8").lower()
    for word in ("order_send", "order_check", "order_calc", "orders", "positions",
                 "position", "trade_request", "order"):
        assert word not in src, word


@pytest.mark.parametrize("path", [SCRIPT, REUSED])
def test_only_allowed_mt5_attributes_are_used(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            assert "MetaTrader5" not in mods or isinstance(node, ast.Import), "no from-imports"
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"getattr", "eval", "exec"}:
            raise AssertionError("dynamic attribute access is not allowed")
        if isinstance(node, ast.Attribute):
            base = node.value
            if isinstance(base, ast.Name) and base.id == "mt5":
                used.add(node.attr)
            if isinstance(base, ast.Attribute) and base.attr == "mt5":  # self.mt5.<attr> / term.mt5.<attr>
                used.add(node.attr)
    assert used and used <= ALLOWED_MT5_ATTRS, used - ALLOWED_MT5_ATTRS


def test_pin_fails_closed():
    mod = _load()
    ok = SimpleNamespace(server="VTMarkets-Demo", login=1234999, trade_mode=0)
    mod.check_pin(ok)
    for bad in (None, SimpleNamespace(server="VTMarkets-Live", login=1234999, trade_mode=0),
                SimpleNamespace(server="VTMarkets-Demo", login=1234985, trade_mode=0),
                SimpleNamespace(server="VTMarkets-Demo", login=1234999, trade_mode=2)):
        with pytest.raises(SystemExit):
            mod.check_pin(bad)


def test_server_time_round_trip_edt_and_est():
    mod = _load()
    for utc in (_ts("2026-10-13T21:00:00"), _ts("2026-12-01T22:00:00")):
        srv = mod.to_server(utc)
        assert mod.to_utc(srv) == utc
        assert datetime.fromtimestamp(srv, UTC).strftime("%H:%M") == "00:00"  # 17:00 NY = server midnight


def test_gaps_listed_never_filled_and_weekend_labelled():
    mod = _load()
    lo, step = _ts("2026-10-09T20:00:00"), 3600            # Fri 16:00 NY
    hi = _ts("2026-10-11T23:00:00")                          # Sun 19:00 NY
    have = [lo, _ts("2026-10-11T21:00:00")]                  # Fri 16:00 and Sun 17:00 NY present
    runs = mod.gap_runs(have, step, lo, hi)
    assert runs[0]["kind"] == "MARKET_CLOSED" and runs[0]["missing"] == 48
    assert runs[1] == {"from_utc": "2026-10-11T22:00:00+00:00", "to_utc": "2026-10-11T22:00:00+00:00",
                       "missing": 1, "kind": "GAP"}


def test_missing_sunday_open_is_split_from_weekend_close():
    mod = _load()
    lo, step = _ts("2026-10-09T21:00:00"), 300               # Fri 17:00 NY
    hi = _ts("2026-10-11T21:10:00")
    runs = mod.gap_runs([_ts("2026-10-11T21:05:00")], step, lo, hi)  # Sun 17:00 NY bar missing
    assert [(r["kind"], r["missing"]) for r in runs] == [("MARKET_CLOSED", 576), ("GAP", 1)]
