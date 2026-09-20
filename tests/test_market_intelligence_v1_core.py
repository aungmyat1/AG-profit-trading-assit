from datetime import datetime, timezone
from dataclasses import FrozenInstanceError

import pytest

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext
from strategy_engine.session import Candle
from market_intelligence import MarketIntelligenceSnapshot, compose_market_intelligence

UTC = timezone.utc


def context():
    store = HistoricalCandleStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [Candle(start, 1, 2, 0, 1.5, 1)]
    store.load_series("EURUSD", "M15", bars)
    store.load_series("EURUSD", "H1", bars)
    return ReplayEvaluationContext.create(store, "EURUSD", start + __import__("datetime").timedelta(hours=2), ("H1", "M15"))


def test_snapshot_is_immutable_and_deterministic():
    first = compose_market_intelligence(context())
    second = compose_market_intelligence(context())
    assert first == second
    assert first.snapshot_id.startswith("MI-")
    with pytest.raises(FrozenInstanceError):
        first.snapshot_id = "changed"


def test_identity_and_provenance_are_preserved_and_missing_authorities_are_explicit():
    snap = compose_market_intelligence(context(), sessions={"session": "ok"}, atr=1.2)
    assert snap.identity.event_id == snap.provenance.event_id
    assert snap.identity.symbol == "EURUSD"
    assert snap.sessions.status == "AVAILABLE"
    assert snap.volatility.status == "AVAILABLE"
    assert snap.regime.status == "UNAVAILABLE"
    assert snap.quality.overall_status == "INCOMPLETE"
    assert "regime" in snap.quality.missing_components


def test_contract_has_no_trade_or_execution_semantics():
    forbidden = {"buy", "sell", "entry", "stop_loss", "take_profit", "lot_size", "risk", "order_type", "execution_authority"}
    assert not forbidden.intersection(MarketIntelligenceSnapshot.__dataclass_fields__)
    assert not forbidden.intersection(snap_field_names())


def snap_field_names():
    return set(MarketIntelligenceSnapshot.__dataclass_fields__) | {"buy", "sell"} & set()


def test_requires_admitted_replay_context():
    with pytest.raises(TypeError):
        compose_market_intelligence(object())
