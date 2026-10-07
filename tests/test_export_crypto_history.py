"""AG_V1_HOST_HARDENING_R1 T4 -- export_crypto_history.py manifest/gap/hash logic.

No real MetaTrader5 terminal is available in this sandbox (confirmed: MetaTrader5.py at the
repo root is an explicit non-Windows fallback that refuses every broker call -- see its own
module docstring). Every test below injects a fake MT5 double with synthetic, clearly-labeled
bars; nothing here is presented as real VT Markets history. The real export (bar counts, gaps,
first/last timestamps against the live VT Markets demo terminal) is NOT_VERIFIED by this test
suite -- see docs/status/AG_V1_HOST_HARDENING_R1_STATUS.md.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "host"))
import export_crypto_history as exp  # noqa: E402

UTC = dt.timezone.utc


class _Row:
    """Mimics one row of MT5's copy_rates_range numpy structured-array result: supports both
    `row["time"]` (what the export script uses) and attribute access."""

    def __init__(self, time_epoch, o, h, l, c, vol, spread=2, real_volume=0):  # noqa: E741
        self._d = {"time": time_epoch, "open": o, "high": h, "low": l, "close": c,
                  "tick_volume": vol, "spread": spread, "real_volume": real_volume}

    def __getitem__(self, key):
        return self._d[key]


def _server_epoch(naive_server_wall_clock: dt.datetime) -> int:
    return calendar.timegm(naive_server_wall_clock.timetuple())


def _bars(start_server_wall: dt.datetime, count: int, minutes: int, base_price=50000.0, gap_after=None):
    """`gap_after` (0-based index) doubles the spacing after that bar, to synthesize one gap."""
    rows = []
    t = start_server_wall
    for i in range(count):
        rows.append(_Row(_server_epoch(t), base_price + i, base_price + i + 1, base_price + i - 1,
                         base_price + i + 0.5, 10.0 + i))
        step = minutes * (3 if gap_after is not None and i == gap_after else 1)
        t = t + dt.timedelta(minutes=step)
    return rows


class FakeMt5T4(types.SimpleNamespace):
    ACCOUNT_TRADE_MODE_DEMO = 0
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388

    def __init__(self, history):
        super().__init__(history=history, calls=[])

    def initialize(self, **kw):
        return True

    def last_error(self):
        return (1, "Success")

    def account_info(self):
        return types.SimpleNamespace(login=1, server="VTMarkets-Demo", trade_mode=0)

    def symbol_info(self, symbol):
        if symbol not in ("BTCUSD", "ETHUSD"):
            return None
        return types.SimpleNamespace(
            name=symbol, digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=0.01,
            trade_contract_size=1.0, volume_min=0.01, volume_step=0.01, volume_max=50.0,
            trade_stops_level=0, trade_freeze_level=0, spread=20, currency_profit="USD",
            swap_long=-5.0, swap_short=-2.0, swap_rollover3days=3, session_open=0.0, session_close=0.0,
        )

    def symbol_select(self, symbol, enable):
        return symbol in ("BTCUSD", "ETHUSD")

    def copy_rates_range(self, symbol, timeframe, date_from, date_to):
        self.calls.append(("copy_rates_range", symbol, timeframe, date_from, date_to))
        tf_name = {15: "M15", 16385: "H1", 16388: "H4"}[timeframe]
        return self.history.get((symbol, tf_name), [])

    def shutdown(self):
        self.calls.append(("shutdown",))


def _history_for(symbol):
    start = dt.datetime(2026, 1, 5, 0, 0)  # a January Monday server wall-clock, well clear of any DST edge
    return {
        (symbol, "M15"): _bars(start, 20, 15, gap_after=10),
        (symbol, "H1"): _bars(start, 10, 60),
        (symbol, "H4"): _bars(start, 5, 240),
    }


def test_fetch_range_bars_converts_time_and_sorts_oldest_first():
    mt5 = FakeMt5T4(_history_for("BTCUSD"))
    bars = exp.fetch_range_bars(mt5, "BTCUSD", "M15", exp.EXPORT_FROM_UTC, dt.datetime.now(UTC))
    assert len(bars) == 20
    assert bars == sorted(bars, key=lambda b: b["time"])
    assert all(b["time"].tzinfo is not None for b in bars)


def test_detect_gaps_finds_the_synthetic_gap_only():
    mt5 = FakeMt5T4(_history_for("BTCUSD"))
    bars = exp.fetch_range_bars(mt5, "BTCUSD", "M15", exp.EXPORT_FROM_UTC, dt.datetime.now(UTC))
    gaps = exp.detect_gaps(bars, exp.TF_MINUTES["M15"])
    assert len(gaps) == 1
    assert gaps[0]["gap_minutes"] == 45.0  # 3x the normal 15-minute spacing


def test_observed_hours_matrix_reports_iso_weekday_and_utc_hour_buckets():
    mt5 = FakeMt5T4(_history_for("BTCUSD"))
    bars = exp.fetch_range_bars(mt5, "BTCUSD", "M15", exp.EXPORT_FROM_UTC, dt.datetime.now(UTC))
    matrix = exp.observed_hours_matrix(bars)
    assert matrix  # non-empty
    assert all(isinstance(hours, list) and hours == sorted(hours) for hours in matrix.values())


def test_dump_symbol_info_includes_required_fields_and_price_labeled_session_fields():
    mt5 = FakeMt5T4(_history_for("BTCUSD"))
    info = exp.dump_symbol_info(mt5, "BTCUSD")
    for f in ("digits", "trade_tick_size", "trade_contract_size", "spread"):
        assert f in info
    for f in ("swap_long", "swap_short", "swap_rollover3days"):
        assert f in info
    assert "session_open" in info and "session_close" in info  # present but documented as PRICE, not time


def test_export_writes_csv_and_manifest_with_hashes(tmp_path):
    mt5 = FakeMt5T4({**_history_for("BTCUSD"), **_history_for("ETHUSD")})
    out = str(tmp_path / "pack")
    now = dt.datetime(2026, 1, 6, tzinfo=UTC)
    manifest = exp.export(mt5, symbols=("BTCUSD", "ETHUSD"), timeframes=("M15", "H1", "H4"), out_dir=out, now=now)

    assert manifest["schema"] == exp.MANIFEST_SCHEMA
    assert set(manifest["symbols"]) == {"BTCUSD", "ETHUSD"}
    for symbol in ("BTCUSD", "ETHUSD"):
        rec = manifest["symbols"][symbol]
        assert set(rec["timeframes"]) == {"M15", "H1", "H4"}
        m15 = rec["timeframes"]["M15"]
        assert m15["bar_count"] == 20 and m15["gap_count"] == 1
        assert m15["first_closed_utc"] and m15["last_closed_utc"]
        csv_path = Path(out) / m15["file"]
        assert csv_path.exists()
        import hashlib
        assert hashlib.sha256(csv_path.read_bytes()).hexdigest() == m15["sha256"]
        assert "observed_trading_hours_utc_by_weekday" in rec

    manifest_path = Path(out) / "manifest.json"
    assert manifest_path.exists()
    on_disk = json.loads(manifest_path.read_text())
    assert on_disk["schema"] == exp.MANIFEST_SCHEMA
    sha_file = Path(out) / "manifest.json.sha256.txt"
    assert sha_file.exists() and manifest["_manifest_sha256"][:16] in sha_file.read_text()


def test_main_refuses_non_demo_account(tmp_path, capsys):
    mt5 = FakeMt5T4(_history_for("BTCUSD"))
    mt5.account_info = lambda: types.SimpleNamespace(login=1, server="Live", trade_mode=2)
    rc = exp.main(["--out", str(tmp_path / "pack")], mt5=mt5)
    assert rc == 1
    assert "NON_DEMO_ACCOUNT_BLOCKED" in capsys.readouterr().out


def test_main_exports_and_prints_summary(tmp_path, capsys):
    mt5 = FakeMt5T4({**_history_for("BTCUSD"), **_history_for("ETHUSD")})
    rc = exp.main(["--out", str(tmp_path / "pack"), "--symbol", "BTCUSD", "--timeframe", "M15"], mt5=mt5)
    assert rc == 0
    out = capsys.readouterr().out
    assert "EXPORTED BTCUSD M15: 20 bars" in out
    assert "MANIFEST:" in out
    assert ("shutdown",) in mt5.calls


def test_no_order_or_position_calls_in_export_script():
    src = (Path(__file__).resolve().parent.parent / "scripts" / "host" / "export_crypto_history.py").read_text()
    for call in ("order_send(", "order_check(", "positions_get(", "position_close(", "orders_get("):
        assert call not in src
