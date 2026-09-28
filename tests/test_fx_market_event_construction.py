"""AG_FX_OPPORTUNITY_PROPOSAL_SLICE_V1 — market event construction proofs.

Covers the seam the historical tests/test_opportunity_events.py covered
(that file was NOT restored: it imports strategy_contract, whose package
__init__ drags assistant + historical_replay -- excluded from this slice).
These tests use the same duck-typed contract the CLI's _ClosedBarView uses.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc

_spec = importlib.util.spec_from_file_location(
    "run_fx_opportunity_cycle", ROOT / "scripts" / "run_fx_opportunity_cycle.py"
)
cli = importlib.util.module_from_spec(_spec)
sys.modules["run_fx_opportunity_cycle"] = cli
_spec.loader.exec_module(cli)

from mt5 import market_data as mt5_market_data  # noqa: E402
from opportunity.events import from_market_snapshot  # noqa: E402
from strategy_engine.session.candles import Candle  # noqa: E402

BAR_TIME = datetime(2026, 9, 23, 10, 45, tzinfo=UTC)
CANDLE = Candle(time=BAR_TIME, open=1.1000, high=1.1010, low=1.0990, close=1.1005, volume=100.0)


def _view():
    return cli._ClosedBarView(candle=CANDLE, symbol="EURUSD")


def test_event_id_deterministic_for_same_closed_bar():
    a = from_market_snapshot(_view(), market="FX", venue="MT5")
    b = from_market_snapshot(_view(), market="FX", venue="MT5")
    assert a.event_id == b.event_id
    assert len(a.event_id) == 64  # sha256 hex, fully deterministic
    assert a.event_type == "BAR_CLOSE"
    assert a.market_data_mode == "REAL"
    assert a.market == "FX" and a.venue == "MT5"
    assert a.bar_close_time == BAR_TIME + timedelta(minutes=15)
    assert a.source == "MT5"


def test_future_forming_bar_rejected():
    class FormingView(_view().__class__):
        @property
        def is_closed(self):
            return False

    with pytest.raises(ValueError, match="closed"):
        from_market_snapshot(FormingView(candle=CANDLE, symbol="EURUSD"), market="FX")


def test_mode_and_fingerprint_cannot_drift():
    view = _view()
    assert view.market_data_mode == "REAL"
    assert view.fingerprint == _view().fingerprint  # stable across constructions
    assert len(view.fingerprint) == 64  # sha256 hex


class _FakeMT5:
    """Minimal read-only double for driving the REAL get_candles body."""

    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def terminal_info(self):
        self.calls.append("terminal_info")
        return SimpleNamespace(connected=True)

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        self.calls.append("symbol_info")
        return SimpleNamespace(visible=True)

    def symbol_select(self, symbol, enable):
        self.calls.append("symbol_select")
        return True

    def copy_rates_range(self, symbol, timeframe, start_epoch, end_epoch):
        self.calls.append("copy_rates_range")
        return [dict(b) for b in self.bars if start_epoch <= b["time"] < end_epoch]

    def order_send(self, *a, **k):
        raise AssertionError("order_send reached")

    def order_check(self, *a, **k):
        raise AssertionError("order_check reached")


def test_real_get_candles_body_against_fake_terminal(monkeypatch):
    """The restored mt5.market_data.get_candles runs its REAL body against the
    double: read-only call surface, UTC round-trip, deterministic output."""
    bars = [{
        "time": int(datetime(2026, 9, 23, 0, 0, tzinfo=UTC).timestamp()),
        "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005, "tick_volume": 42.0,
    }, {
        "time": int(datetime(2026, 9, 23, 0, 15, tzinfo=UTC).timestamp()),
        "open": 1.1005, "high": 1.1015, "low": 1.0995, "close": 1.1010, "tick_volume": 43.0,
    }]
    fake = _FakeMT5(bars)
    monkeypatch.setattr(mt5_market_data, "mt5", fake)
    monkeypatch.setattr(mt5_market_data, "_broker_offset_hours", lambda symbol: 0)

    candles = mt5_market_data.get_candles(
        "EURUSD", "M15",
        datetime(2026, 9, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 23, 0, 30, tzinfo=UTC),
    )
    assert [c.time for c in candles] == [
        datetime(2026, 9, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 23, 0, 15, tzinfo=UTC),
    ]
    assert candles[0].open == 1.1000 and candles[1].close == 1.1010
    assert fake.calls == ["terminal_info", "symbol_info", "copy_rates_range"]


def test_real_get_candles_data_missing_fails_closed(monkeypatch):
    fake = _FakeMT5([])
    monkeypatch.setattr(mt5_market_data, "mt5", fake)
    monkeypatch.setattr(mt5_market_data, "_broker_offset_hours", lambda symbol: 0)
    with pytest.raises(mt5_market_data.MarketDataError, match="DATA_MISSING"):
        mt5_market_data.get_candles(
            "EURUSD", "M15",
            datetime(2026, 9, 23, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 23, 0, 30, tzinfo=UTC),
        )
