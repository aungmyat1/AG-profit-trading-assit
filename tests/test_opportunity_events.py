"""Focused tests for src/opportunity/events.py (MarketEvent construction, P6)."""
from __future__ import annotations

import datetime as dt

import pytest

from opportunity.events import from_market_snapshot
from strategy_contract.market_snapshot import MarketSnapshot

UTC = dt.timezone.utc


def _snapshot(**overrides) -> MarketSnapshot:
    base = dict(
        symbol="EURUSD",
        timeframe="M15",
        source="VANTAGE_DEMO_MT5",
        market_data_mode="REAL",
        bar_open_time=dt.datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        bar_close_time=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
        market_data_asof=dt.datetime(2026, 9, 21, 8, 15, 1, tzinfo=UTC),
        retrieved_at=dt.datetime(2026, 9, 21, 8, 15, 2, tzinfo=UTC),
        is_closed=True,
        fingerprint="fp-1",
    )
    base.update(overrides)
    return MarketSnapshot(**base)


class TestFromMarketSnapshot:
    def test_builds_event_with_propagated_fields(self):
        snap = _snapshot()
        event = from_market_snapshot(snap, market="FX", venue="VANTAGE_DEMO_MT5")
        assert event.symbol == snap.symbol
        assert event.timeframe == snap.timeframe
        assert event.bar_close_time == snap.bar_close_time
        assert event.market_data_mode == snap.market_data_mode
        assert event.snapshot_fingerprint == snap.fingerprint

    def test_deterministic_identity_same_bar_same_source(self):
        snap = _snapshot()
        e1 = from_market_snapshot(snap, market="FX")
        e2 = from_market_snapshot(snap, market="FX")
        assert e1.event_id == e2.event_id

    def test_identity_changes_with_different_bar(self):
        e1 = from_market_snapshot(_snapshot(), market="FX")
        e2 = from_market_snapshot(
            _snapshot(
                bar_open_time=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
                bar_close_time=dt.datetime(2026, 9, 21, 8, 30, tzinfo=UTC),
                market_data_asof=dt.datetime(2026, 9, 21, 8, 30, 1, tzinfo=UTC),
            ),
            market="FX",
        )
        assert e1.event_id != e2.event_id

    def test_unclosed_snapshot_rejected(self):
        with pytest.raises(ValueError):
            from_market_snapshot(_snapshot(is_closed=False), market="FX")

    def test_replay_and_live_shape_parity(self):
        real = from_market_snapshot(_snapshot(market_data_mode="REAL"), market="FX")
        replay = from_market_snapshot(_snapshot(market_data_mode="REPLAY"), market="FX")
        assert set(vars(real).keys()) == set(vars(replay).keys())
        assert real.market_data_mode == "REAL"
        assert replay.market_data_mode == "REPLAY"

    def test_synthetic_mode_preserved(self):
        event = from_market_snapshot(_snapshot(market_data_mode="SYNTHETIC"), market="FX")
        assert event.market_data_mode == "SYNTHETIC"
