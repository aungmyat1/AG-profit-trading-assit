from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import MetaTrader5 as mt5

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext
from historical_replay.utc_export_csv_loader import load_utc_export_csv
from market_intelligence import compose_market_intelligence
from strategy_engine.session import Candle

UTC = timezone.utc


def _controlled(offset=0.0):
    store = HistoricalCandleStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for timeframe, minutes, count in (("H1", 60, 80), ("M15", 15, 320), ("M1", 1, 400)):
        bars = []
        for i in range(count):
            t = start + timedelta(minutes=i * minutes)
            p = 1.1 + i * 0.00001 + (offset if t > datetime(2026, 1, 2, tzinfo=UTC) else 0)
            bars.append(Candle(t, p, p + .0002, p - .0002, p, 1))
        store.load_series("EURUSD", timeframe, bars)
    return ReplayEvaluationContext.create(
        store, "EURUSD", datetime(2026, 1, 2, 12, tzinfo=UTC), ("H1", "M15", "M1")
    )


def test_same_event_determinism_and_identity_preservation():
    c1, c2 = _controlled(), _controlled()
    a = compose_market_intelligence(c1, sessions={"authority": "session"}, structure={"authority": "structure"}, atr=0.001)
    b = compose_market_intelligence(c2, sessions={"authority": "session"}, structure={"authority": "structure"}, atr=0.001)
    assert a == b
    assert a.snapshot_id == b.snapshot_id
    assert a.identity.event_id == c1.event_id == a.provenance.event_id
    assert a.identity.symbol == "EURUSD"
    assert a.identity.as_of == c1.as_of
    assert tuple(tf for tf, _ in a.provenance.dataset_identities) == ("H1", "M1", "M15")
    assert a.execution_timeframe_lineage.participating_series == ("H1", "M15", "M1")
    assert a.execution_timeframe_lineage.m1_used is True


def test_future_only_mutation_does_not_change_semantics_at_t():
    first = compose_market_intelligence(_controlled())
    future_changed = compose_market_intelligence(_controlled(0.5))
    assert first.identity.as_of == future_changed.identity.as_of
    assert first.quality == future_changed.quality
    assert first.execution_timeframe_lineage == future_changed.execution_timeframe_lineage
    assert first.snapshot_id != future_changed.snapshot_id


def test_incomplete_evidence_and_unresolved_authorities_are_explicit():
    snapshot = compose_market_intelligence(_controlled(), sessions={"complete": False})
    assert snapshot.sessions.status == "AVAILABLE"
    assert snapshot.regime.status == "UNAVAILABLE"
    assert snapshot.volatility.status == "UNAVAILABLE"
    assert snapshot.volatility.feature_version == "ATR_EXISTING_EMA_UNAVAILABLE"
    assert snapshot.quality.overall_status == "INCOMPLETE"
    assert "regime" in snapshot.quality.missing_components
    assert "volatility" in snapshot.quality.missing_components


def test_historical_mi_composition_makes_no_live_calls():
    root = "data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/"
    store = HistoricalCandleStore()
    for timeframe in ("H1", "M15", "M1"):
        candles, _ = load_utc_export_csv(root + f"EURUSD_{timeframe}.csv", "EURUSD", timeframe)
        store.load_series("EURUSD", timeframe, candles)
    context = ReplayEvaluationContext.create(
        store, "EURUSD", datetime(2026, 6, 23, 11, tzinfo=UTC), ("H1", "M15", "M1")
    )
    with patch.object(mt5, "copy_rates_from_pos", side_effect=AssertionError("live fallback")), \
         patch.object(mt5, "copy_rates_range", side_effect=AssertionError("live fallback")):
        result = compose_market_intelligence(context, sessions={"event": "real-complete"}, atr=0.001)
    assert result.identity.event_id == context.event_id
    assert result.identity.as_of == context.as_of
    assert result.execution_timeframe_lineage.m1_used is True
    assert result.quality.overall_status == "INCOMPLETE"  # regime remains unresolved

