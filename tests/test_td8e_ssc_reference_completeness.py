from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext
from historical_replay.candle_store import HistoricalDataError
from historical_replay.symbol_metadata_manifest import HistoricalSymbolMetadataManifest
from replay_evaluation.ssc import evaluate_ssc_replay
from session_sweep_continuation.config import load_config
from strategy_engine.session import Candle

UTC = timezone.utc
DAY = date(2026, 1, 25)
T = datetime(2026, 1, 25, 12, tzinfo=UTC)


def _manifest():
    return HistoricalSymbolMetadataManifest(
        "TEST", "EURUSD", 0.00001, "HISTORICAL_ANALYSIS_ONLY",
        "OWNER_APPROVED_DATASET_MANIFEST", "2026-09-02", "sha256:" + "0" * 64, "unused",
    )


def _candle(t, n=0):
    p = 1.1 + n * 0.00001
    return Candle(t, p, p + 0.0003, p - 0.0003, p, 1.0)


def _context(reference_times):
    store = HistoricalCandleStore()
    h1_start = datetime(2026, 1, 1, tzinfo=UTC)
    store.load_series("EURUSD", "H1", [_candle(h1_start + timedelta(hours=i), i) for i in range(1300)])
    m15 = [_candle(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i), i)
           for i in range(96)]
    m15.extend(_candle(t, 100 + i) for i, t in enumerate(reference_times))
    store.load_series("EURUSD", "M15", m15)
    return ReplayEvaluationContext.create(store, "EURUSD", T, ("H1", "M15"))


def _reference_times():
    start = datetime(2026, 1, 25, tzinfo=UTC)
    return tuple(start + timedelta(minutes=15 * i) for i in range(24))


def _run(context):
    return evaluate_ssc_replay(context, manifest=_manifest(), config=load_config(),
                               session_pair_id="ASIAN_LONDON", trading_date=DAY, pip_size=.0001)


@pytest.mark.parametrize("times", [
    (),
    _reference_times()[:1],
    _reference_times()[:-1],
    _reference_times()[:12] + _reference_times()[13:],
])
def test_incomplete_reference_defers_before_canonical_consumer(times):
    context = _context(times)
    with patch("replay_evaluation.ssc.run_canonical_shadow_cycle", Mock()) as consumer:
        result = _run(context)
    assert result.status == "SESSION_INCOMPLETE"
    assert result.reason_codes == ("SSC_REFERENCE_SESSION_INCOMPLETE",)
    consumer.assert_not_called()


def test_complete_reference_reaches_actual_canonical_consumer():
    context = _context(_reference_times())
    sentinel = object()
    with patch("replay_evaluation.ssc.run_canonical_shadow_cycle", return_value=sentinel) as consumer:
        result = _run(context)
    assert result.status == "COMPLETE"
    assert result.cycle is sentinel
    consumer.assert_called_once()


def test_duplicate_timestamp_is_rejected_by_bound_store():
    store = HistoricalCandleStore()
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(HistoricalDataError, match="DUPLICATE_OR_UNORDERED_TIMESTAMP"):
        store.load_series("EURUSD", "M15", [_candle(t), _candle(t)])


def test_pre_completion_defers_and_unrelated_future_session_is_not_required():
    context = _context(_reference_times())
    before = ReplayEvaluationContext.create(
        context.provider.store, "EURUSD", datetime(2026, 1, 25, 10, tzinfo=UTC), ("H1", "M15")
    )
    with patch("replay_evaluation.ssc.run_canonical_shadow_cycle", Mock()) as consumer:
        result = _run(before)
    assert result.status == "DEFERRED"
    consumer.assert_not_called()
    with patch("replay_evaluation.ssc.run_canonical_shadow_cycle", return_value=object()) as consumer:
        result = _run(context)
    assert result.status == "COMPLETE"
    consumer.assert_called_once()
