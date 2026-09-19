"""One historical event delivered to both unmodified strategy consumers."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import MetaTrader5 as mt5

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext
from historical_replay.utc_export_csv_loader import load_utc_export_csv
from historical_replay.symbol_metadata_manifest import HistoricalSymbolMetadataManifest
from historical_replay.symbol_metadata_manifest import load_symbol_metadata_manifest, validate_manifest_for_dataset
from replay_evaluation import evaluate_asian_replay, evaluate_ssc_replay
from session_sweep_continuation.config import load_config
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle


UTC = timezone.utc
DAY = date(2026, 1, 26)
T = datetime(2026, 1, 26, 11, tzinfo=UTC)


def _bars(start, minutes, count, future_offset=0):
    result = []
    for i in range(count):
        t = start + timedelta(minutes=i * minutes)
        p = 1.1 + i * 0.000001 + (future_offset if t >= T else 0)
        result.append(Candle(t, p, p + 0.0002, p - 0.0002, p, 1))
    return result


def _context(future_offset=0):
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "H1", _bars(datetime(2025, 12, 1, tzinfo=UTC), 60, 1350, future_offset))
    store.load_series("EURUSD", "M15", _bars(datetime(2026, 1, 16, tzinfo=UTC), 15, 1100, future_offset))
    return ReplayEvaluationContext.create(store, "EURUSD", T, ("H1", "M15"))


def _run(context, day=DAY, manifest=None):
    strategy = load_strategy("strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
    asian = evaluate_asian_replay(
        context, strategy=strategy, pair_id="ASIAN_LONDON", trading_date=day,
        reference_session="asian",
        execution_window_start=datetime(day.year, day.month, day.day, 7, tzinfo=UTC),
        execution_window_end=datetime(day.year, day.month, day.day, 11, tzinfo=UTC),
    )
    manifest = manifest or HistoricalSymbolMetadataManifest(
        "TEST", "EURUSD", 0.00001, "HISTORICAL_ANALYSIS_ONLY",
        "OWNER_APPROVED_DATASET_MANIFEST", "2026-09-02", "sha256:" + "0" * 64, "unused",
    )
    ssc = evaluate_ssc_replay(
        context, manifest=manifest, config=load_config(),
        session_pair_id="ASIAN_LONDON", trading_date=day, pip_size=0.0001,
    )
    return asian, ssc


def test_both_actual_consumers_share_event_and_ignore_future_mutation():
    context1, context2 = _context(), _context(0.5)
    with patch("assistant.market_data.get_candles", side_effect=AssertionError("LIVE candle query")) as live, \
         patch.object(mt5, "copy_rates_from_pos", side_effect=AssertionError("LIVE candles")) as live_pos, \
         patch.object(mt5, "copy_rates_range", side_effect=AssertionError("LIVE range")) as live_range:
        a1, s1 = _run(context1)
        a2, s2 = _run(context2)
    assert live.call_count == live_pos.call_count == live_range.call_count == 0
    assert a1.status == a2.status == "COMPLETE"
    assert s1.status == s2.status == "COMPLETE"
    assert a1.event_id == s1.event_id
    assert a2.event_id == s2.event_id
    assert a1.event_id != a2.event_id
    assert a1.signal == a2.signal
    assert s1.cycle.replay_result == s2.cycle.replay_result
    print({"controlled_event": a1.event_id, "future_mutated_event": a2.event_id,
           "H1_count": len(context1.candles("H1")), "M15_count": len(context1.candles("M15")),
           "reference_count": len([c for c in context1.candles("M15") if c.time.date() == DAY and c.time.hour < 6]),
           "asian_status": a1.status, "ssc_status": s1.status})


def test_consumed_dev002_one_non_counting_shared_event():
    root = "data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/"
    h1_path = root + "EURUSD_H1.csv"
    manifest = load_symbol_metadata_manifest(
        "config/historical_datasets/EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml"
    )
    validate_manifest_for_dataset(manifest, h1_path, "EURUSD")
    store = HistoricalCandleStore()
    for timeframe in ("H1", "M15"):
        candles, _ = load_utc_export_csv(root + f"EURUSD_{timeframe}.csv", "EURUSD", timeframe)
        store.load_series("EURUSD", timeframe, candles)
    day = date(2026, 6, 23)
    t = datetime(2026, 6, 23, 11, tzinfo=UTC)
    context = ReplayEvaluationContext.create(store, "EURUSD", t, ("H1", "M15"))
    with patch("assistant.market_data.get_candles", side_effect=AssertionError("LIVE candle query")) as live, \
         patch.object(mt5, "copy_rates_from_pos", side_effect=AssertionError("LIVE candles")) as live_pos, \
         patch.object(mt5, "copy_rates_range", side_effect=AssertionError("LIVE range")) as live_range:
        asian, ssc = _run(context, day, manifest)
    assert asian.event_id == ssc.event_id == context.event_id
    assert asian.status == ssc.status == "COMPLETE"
    assert live.call_count == live_pos.call_count == live_range.call_count == 0
    print({"event_id": context.event_id, "T": t.isoformat(),
           "H1_count": len(context.candles("H1")), "M15_count": len(context.candles("M15")),
           "reference_count": len([c for c in context.candles("M15") if c.time.date() == day and c.time.hour < 6]),
           "asian_status": asian.status, "ssc_status": ssc.status, "live_calls": live.call_count})


def test_m1_outcome_lineage_uses_bound_series_without_changing_setup_identity():
    store = _context().provider.store
    store.load_series("EURUSD", "M1", _bars(datetime(2026, 1, 25, tzinfo=UTC), 1, 2200))
    setup = ReplayEvaluationContext.create(store, "EURUSD", T, ("H1", "M15"))
    outcome = ReplayEvaluationContext.create(store, "EURUSD", T, ("H1", "M15", "M1"))
    assert setup.event_id != outcome.event_id
    assert "M1" not in setup.series_identities
    assert "M1" in outcome.series_identities
    manifest = HistoricalSymbolMetadataManifest(
        "TEST", "EURUSD", 0.00001, "HISTORICAL_ANALYSIS_ONLY",
        "OWNER_APPROVED_DATASET_MANIFEST", "2026-09-02", "sha256:" + "0" * 64, "unused",
    )
    result = evaluate_ssc_replay(
        outcome, manifest=manifest, config=load_config(), session_pair_id="ASIAN_LONDON",
        trading_date=DAY, pip_size=0.0001, include_m1_outcome=True,
    )
    assert result.status == "COMPLETE"
    assert result.event_id == outcome.event_id
