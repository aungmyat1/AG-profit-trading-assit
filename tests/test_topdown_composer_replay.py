"""TD-8: HISTORICAL_AS_OF composition tests for src/mtf_context/topdown_composer.py.

Two tiers of tests:

1. CHEAP ORCHESTRATION/GUARD tests -- the six tier builders are mocked (same idiom as
   test_topdown_composer.py's LIVE_CURRENT suite) and `historical_data_context` itself
   is replaced with a no-op context manager, so these tests are about the composer's
   OWN pre/post validation logic (naive-datetime rejection, replay-store-required,
   dataset-identity-missing, symbol/timeframe/temporal guards, evaluation_time ==
   as_of_time exactly), independent of whether the real replay-substitution mechanism
   works. A minimal HistoricalCandleStore (1 candle per timeframe) is used only to
   satisfy the pre-flight dataset_identity() check.

2. REAL END-TO-END REPLAY tests -- a full, deterministic, synthetic six-timeframe
   candle fixture (independently generated per timeframe -- NOT literally aggregated
   from one base feed; nothing in the composer's own contracts requires literal
   cross-timeframe OHLC consistency, only per-timeframe temporal ordering and
   sufficient depth) is loaded into a real HistoricalCandleStore, and
   `build_topdown_context(..., as_of_time=T, replay_store=store)` runs through the
   REAL `historical_data_context` substitution and REAL analyze_structure()/
   liquidity_result()/etc detectors -- no mocking below the composer. This proves the
   actual no-lookahead/zero-live-MT5/dataset-collision/parity properties end to end,
   not just that the composer's own bookkeeping is self-consistent.

`market_structure.analyzer.load_market_structure_config`'s real default
(default_analysis_count=200, warmup=max(swing_length*20,100)) needs ~300 closed
candles per timeframe to reach a VALID StructureResult; this file patches it to a
much smaller config (still >=100 warmup floor -- that floor is hard-coded in
analyzer.py itself, not config-driven) so fixtures stay deterministic and fast rather
than needing hundreds of hand-generated bars per timeframe.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from unittest.mock import patch

import pytest

import mt5.market_data as market_data
from historical_replay.candle_store import HistoricalCandleStore
from market_structure.models import MarketStructureConfig
from mtf_context.topdown_composer import (
    IncompleteTopDownCompositionError,
    NaiveAsOfTimeError,
    ReplayDatasetIdentityMissingError,
    ReplayStoreRequiredError,
    TopDownSymbolMismatchError,
    TopDownTemporalViolationError,
    TopDownTimeframeSlotError,
    build_topdown_context,
)
from mtf_context.topdown_contracts import (
    COMPOSITION_MODE_HISTORICAL_AS_OF,
    COMPOSITION_MODE_LIVE_CURRENT,
    DATA_QUALITY_VALID,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    DailyContext,
    H1Context,
    H4Context,
    M5Context,
    M15Context,
    WeeklyContext,
)
from strategy_engine.session import Candle

UTC = timezone.utc
_ALL_TF: Tuple[str, ...] = ("W1", "D1", "H4", "H1", "M15", "M5")
_TF_MINUTES = {"W1": 10080, "D1": 1440, "H4": 240, "H1": 60, "M15": 15, "M5": 5}
_T = datetime(2026, 9, 19, 10, 37, 0, tzinfo=UTC)  # deliberately mid-H1/mid-H4, per the mission's own example

_SMALL_CONFIG = MarketStructureConfig(swing_length=3, close_break=True, default_analysis_count=5)


# =============================================================================
# Section 1: cheap orchestration/guard tests (mocked builders, no-op replay patch)
# =============================================================================

def _weekly(symbol="EURUSD", context_id="TDCTX-W1-1", bar_close=None, status=DATA_QUALITY_VALID):
    return WeeklyContext(context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_W1, source="TEST",
                          bar_close_time=bar_close, feature_version="TEST_V1", data_quality_status=status)


def _daily(symbol="EURUSD", context_id="TDCTX-D1-1", parent_weekly_context_id=None, bar_close=None,
           status=DATA_QUALITY_VALID):
    return DailyContext(context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_D1, source="TEST",
                         bar_close_time=bar_close, feature_version="TEST_V1", data_quality_status=status,
                         parent_weekly_context_id=parent_weekly_context_id)


def _h4(symbol="EURUSD", context_id="TDCTX-H4-1", parent_daily_context_id=None, bar_close=None,
        status=DATA_QUALITY_VALID):
    return H4Context(context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_H4, source="TEST",
                      bar_close_time=bar_close, feature_version="TEST_V1", data_quality_status=status,
                      parent_daily_context_id=parent_daily_context_id)


def _h1(symbol="EURUSD", context_id="TDCTX-H1-1", parent_h4_context_id=None, bar_close=None,
        status=DATA_QUALITY_VALID):
    return H1Context(context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_H1, source="TEST",
                      bar_close_time=bar_close, feature_version="TEST_V1", data_quality_status=status,
                      parent_h4_context_id=parent_h4_context_id)


def _m15(symbol="EURUSD", context_id="TDCTX-M15-1", parent_h1_context_id=None, bar_close=None,
         status=DATA_QUALITY_VALID):
    return M15Context(context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_M15, source="TEST",
                       bar_close_time=bar_close, feature_version="TEST_V1", data_quality_status=status,
                       parent_h1_context_id=parent_h1_context_id)


def _m5(symbol="EURUSD", context_id="TDCTX-M5-1", parent_m15_context_id=None, bar_close=None,
        status=DATA_QUALITY_VALID):
    return M5Context(context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_M5, source="TEST",
                      bar_close_time=bar_close, feature_version="TEST_V1", data_quality_status=status,
                      parent_m15_context_id=parent_m15_context_id)


def _valid_chain(symbol="EURUSD", as_of=_T):
    base = as_of - timedelta(days=30)
    weekly = _weekly(symbol=symbol, bar_close=base)
    daily = _daily(symbol=symbol, parent_weekly_context_id=weekly.context_id, bar_close=base + timedelta(days=1))
    h4 = _h4(symbol=symbol, parent_daily_context_id=daily.context_id, bar_close=base + timedelta(days=1, hours=4))
    h1 = _h1(symbol=symbol, parent_h4_context_id=h4.context_id, bar_close=base + timedelta(days=1, hours=5))
    m15 = _m15(symbol=symbol, parent_h1_context_id=h1.context_id, bar_close=base + timedelta(days=1, hours=5, minutes=15))
    m5 = _m5(symbol=symbol, parent_m15_context_id=m15.context_id, bar_close=base + timedelta(days=1, hours=5, minutes=20))
    return weekly, daily, h4, h1, m15, m5


def _patch_builders(weekly=None, daily=None, h4=None, h1=None, m15=None, m5=None):
    return patch.multiple(
        "mtf_context.topdown_composer",
        build_weekly_context=lambda symbol: weekly,
        build_daily_context=lambda symbol, **kw: daily,
        build_h4_context=lambda symbol, **kw: h4,
        build_h1_context=lambda symbol, **kw: h1,
        build_m15_context=lambda symbol, **kw: m15,
        build_m5_context=lambda symbol, **kw: m5,
    )


@contextlib.contextmanager
def _noop_replay_context(*_args, **_kwargs):
    yield


def _minimal_store(symbol="EURUSD"):
    """Just enough for dataset_identity() to return non-None for every required
    timeframe -- these guard tests mock the six builders directly, so no real fetch
    ever reaches the store's actual candle content."""
    store = HistoricalCandleStore()
    t0 = datetime(2020, 1, 6, 0, 0, tzinfo=UTC)
    for tf in _ALL_TF:
        store.load_series(symbol, tf, [Candle(time=t0, open=1.1, high=1.1005, low=1.0995, close=1.1002, volume=10.0)])
    return store


def test_naive_as_of_time_rejected():
    with pytest.raises(NaiveAsOfTimeError):
        build_topdown_context("EURUSD", as_of_time=datetime(2026, 1, 1, 0, 0))  # no tzinfo


def test_as_of_time_without_replay_store_rejected():
    with pytest.raises(ReplayStoreRequiredError):
        build_topdown_context("EURUSD", as_of_time=_T)


def test_replay_store_without_as_of_time_rejected():
    with pytest.raises(ReplayStoreRequiredError):
        build_topdown_context("EURUSD", replay_store=_minimal_store())


@pytest.mark.parametrize("missing_tf", _ALL_TF)
def test_missing_dataset_identity_for_one_timeframe_fails_closed(missing_tf):
    store = HistoricalCandleStore()
    t0 = datetime(2020, 1, 6, 0, 0, tzinfo=UTC)
    for tf in _ALL_TF:
        if tf == missing_tf:
            continue
        store.load_series("EURUSD", tf, [Candle(time=t0, open=1.1, high=1.1005, low=1.0995, close=1.1002, volume=10.0)])
    with pytest.raises(ReplayDatasetIdentityMissingError):
        build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)


def test_evaluation_time_equals_supplied_as_of_time_exactly_not_wall_clock():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5), \
         patch("mtf_context.topdown_composer.historical_data_context", _noop_replay_context):
        ctx = build_topdown_context("EURUSD", as_of_time=_T, replay_store=_minimal_store())

    assert ctx.evaluation_time == _T
    assert ctx.composition_mode == COMPOSITION_MODE_HISTORICAL_AS_OF


def test_dataset_identity_recorded_on_composed_context():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5), \
         patch("mtf_context.topdown_composer.historical_data_context", _noop_replay_context):
        ctx = build_topdown_context("EURUSD", as_of_time=_T, replay_store=_minimal_store())

    assert ctx.dataset_identity is not None and len(ctx.dataset_identity) > 0


def test_live_current_still_uses_wall_clock_and_no_dataset_identity():
    """Regression: LIVE_CURRENT (TD-7) behavior must be completely unaffected by TD-8."""
    fixed_now = _T

    def _clock():
        return fixed_now

    weekly, daily, h4, h1, m15, m5 = _valid_chain(as_of=fixed_now)
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        ctx = build_topdown_context("EURUSD", _clock=_clock)

    assert ctx.composition_mode == COMPOSITION_MODE_LIVE_CURRENT
    assert ctx.dataset_identity is None
    assert ctx.evaluation_time == fixed_now


def test_symbol_guard_in_historical_mode():
    weekly = _weekly(symbol="EURUSD", bar_close=_T - timedelta(days=30))
    daily = _daily(symbol="EURUSD", parent_weekly_context_id=weekly.context_id, bar_close=_T - timedelta(days=29))
    h4 = _h4(symbol="GBPUSD", parent_daily_context_id=daily.context_id, bar_close=_T - timedelta(days=28))
    with _patch_builders(weekly=weekly, daily=daily, h4=h4), \
         patch("mtf_context.topdown_composer.historical_data_context", _noop_replay_context):
        with pytest.raises(TopDownSymbolMismatchError):
            build_topdown_context("EURUSD", as_of_time=_T, replay_store=_minimal_store())


def test_timeframe_slot_guard_in_historical_mode():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    wrong_type_h4 = _h1(context_id="WRONG-SLOT", parent_h4_context_id=daily.context_id, bar_close=h4.bar_close_time)
    with _patch_builders(weekly=weekly, daily=daily, h4=wrong_type_h4), \
         patch("mtf_context.topdown_composer.historical_data_context", _noop_replay_context):
        with pytest.raises(TopDownTimeframeSlotError):
            build_topdown_context("EURUSD", as_of_time=_T, replay_store=_minimal_store())


@pytest.mark.parametrize("missing_tier", ["weekly", "daily", "h4", "h1", "m15", "m5"])
def test_missing_tier_fails_closed_in_historical_mode(missing_tier):
    tiers = dict(zip(("weekly", "daily", "h4", "h1", "m15", "m5"), _valid_chain()))
    tiers[missing_tier] = None
    with _patch_builders(**tiers), \
         patch("mtf_context.topdown_composer.historical_data_context", _noop_replay_context):
        with pytest.raises(IncompleteTopDownCompositionError):
            build_topdown_context("EURUSD", as_of_time=_T, replay_store=_minimal_store())


def test_temporal_violation_in_historical_mode():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    future_m5 = _m5(context_id="FUTURE", parent_m15_context_id=m15.context_id, bar_close=_T + timedelta(minutes=1))
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=future_m5), \
         patch("mtf_context.topdown_composer.historical_data_context", _noop_replay_context):
        with pytest.raises(TopDownTemporalViolationError):
            build_topdown_context("EURUSD", as_of_time=_T, replay_store=_minimal_store())


def test_historical_data_context_entered_with_the_supplied_store_and_as_of_time():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    captured = {}

    @contextlib.contextmanager
    def _spy(store, as_of, **kwargs):
        captured["store"] = store
        captured["as_of"] = as_of
        yield

    store = _minimal_store()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5), \
         patch("mtf_context.topdown_composer.historical_data_context", _spy):
        build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)

    assert captured["store"] is store
    assert captured["as_of"] == _T


# =============================================================================
# Section 2: real end-to-end replay tests (real detectors, real historical_data_context)
# =============================================================================

import numpy as np  # noqa: E402  (kept local to this section -- only these tests need it)

from historical_replay.data_source_patch import historical_data_context  # noqa: E402


@pytest.fixture(autouse=True)
def _small_market_structure_config():
    """The real config/market_structure.yaml needs ~300 closed candles per timeframe
    for a VALID StructureResult (default_analysis_count=200 + warmup>=100). Patched
    here to a much smaller, still-real config so this file's fixtures stay a few
    hundred synthetic candles total instead of ~1800+. Test-only; production config
    file is never touched."""
    with patch("market_structure.analyzer.load_market_structure_config", return_value=_SMALL_CONFIG):
        yield


def _bucket_start(t: datetime, minutes: int) -> datetime:
    epoch_minutes = int(t.timestamp() // 60)
    aligned = (epoch_minutes // minutes) * minutes
    return datetime.fromtimestamp(aligned * 60, tz=UTC)


def _price_candle(idx: int, t: datetime, base: float = 1.1000, step: float = 0.0006) -> Candle:
    """Deterministic, non-degenerate synthetic OHLC -- not meant to be realistic or to
    guarantee a specific swing/BOS outcome from the smartmoneyconcepts library, only to
    be internally ordered and distinct enough to exercise the real detector path."""
    direction = 1 if idx % 2 == 0 else -1
    o = base + direction * step * (idx % 4)
    c = o + direction * step
    h = max(o, c) + step / 2
    l = min(o, c) - step / 2
    return Candle(time=t, open=round(o, 6), high=round(h, 6), low=round(l, 6), close=round(c, 6), volume=100.0)


def _series_for_timeframe(
    tf: str, as_of: datetime, *, closed_count: int = 115, future_count: int = 2,
    base: float = 1.1000, step: float = 0.0006,
) -> Tuple[List[Candle], datetime, datetime]:
    """Independently generates one timeframe's series (NOT literally aggregated from a
    common base feed across timeframes -- nothing in the composer's own contracts
    requires literal cross-timeframe OHLC consistency, only per-timeframe ordering and
    sufficient depth; see this file's module docstring). `closed_count` closed bars end
    exactly at the bar immediately before the one containing `as_of` (the "forming"
    bar, open <= as_of, not yet closed); `future_count` additional bars follow it,
    strictly after `as_of`, for the future-leak sentinel test."""
    minutes = _TF_MINUTES[tf]
    delta = timedelta(minutes=minutes)
    current_open = _bucket_start(as_of, minutes)
    opens = [current_open - delta * n for n in range(closed_count, 0, -1)]
    opens.append(current_open)
    for k in range(1, future_count + 1):
        opens.append(current_open + delta * k)
    candles = [_price_candle(i, t, base=base, step=step) for i, t in enumerate(opens)]
    last_closed_open = current_open - delta
    return candles, current_open, last_closed_open


def _load_full_store(
    symbol: str, as_of: datetime, *, closed_count: int = 115, future_count: int = 2,
    source: str = "TEST_SOURCE", dataset_label: str = "A", base: float = 1.1000, step: float = 0.0006,
):
    store = HistoricalCandleStore()
    current_opens: dict = {}
    last_closed_opens: dict = {}
    for tf in _ALL_TF:
        candles, current_open, last_closed_open = _series_for_timeframe(
            tf, as_of, closed_count=closed_count, future_count=future_count, base=base, step=step,
        )
        store.load_series(symbol, tf, candles, dataset_id=f"{symbol}:{tf}:{dataset_label}", source=source)
        current_opens[tf] = current_open
        last_closed_opens[tf] = last_closed_open
    return store, current_opens, last_closed_opens


def test_real_replay_composition_succeeds_and_respects_the_boundary():
    """P13: T is deliberately mid-bar for every timeframe (see _T's own definition).
    Proves the composer reports exactly the last CLOSED bar for every tier, never the
    forming one, through the REAL end-to-end call graph (real analyze_structure(),
    real historical_data_context substitution)."""
    store, current_opens, last_closed_opens = _load_full_store("EURUSD", _T)

    ctx = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)

    assert ctx.symbol == "EURUSD"
    assert ctx.evaluation_time == _T
    assert ctx.composition_mode == COMPOSITION_MODE_HISTORICAL_AS_OF
    assert ctx.dataset_identity is not None
    assert ctx.data_quality_status == DATA_QUALITY_VALID

    tiers = {"W1": ctx.weekly, "D1": ctx.daily, "H4": ctx.h4, "H1": ctx.h1, "M15": ctx.m15, "M5": ctx.m5}
    for tf, tier in tiers.items():
        assert tier.symbol == "EURUSD"
        assert tier.bar_close_time <= _T
        assert tier.bar_close_time == last_closed_opens[tf]
        assert tier.bar_close_time < current_opens[tf]  # the forming bar is excluded

    assert ctx.daily.parent_weekly_context_id == ctx.weekly.context_id
    assert ctx.h4.parent_daily_context_id == ctx.daily.context_id
    assert ctx.h1.parent_h4_context_id == ctx.h4.context_id
    assert ctx.m15.parent_h1_context_id == ctx.h1.context_id
    assert ctx.m5.parent_m15_context_id == ctx.m15.context_id


def test_actual_candle_inputs_never_exceed_the_as_of_boundary():
    """P3/#6: instruments the REAL no-lookahead enforcement point
    (HistoricalCandleStore.closed_candles) to inspect every candle actually handed to
    a detector during a real composition, not merely the final reported timestamps."""
    store, _, _ = _load_full_store("EURUSD", _T)
    calls = []
    original = HistoricalCandleStore.closed_candles

    def _spy(self, symbol, timeframe, as_of, count):
        result = original(self, symbol, timeframe, as_of, count)
        calls.append((timeframe, tuple(c.time for c in result), as_of))
        return result

    with patch.object(HistoricalCandleStore, "closed_candles", _spy):
        build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)

    assert calls, "expected at least one closed_candles call during composition"
    for timeframe, times, as_of in calls:
        duration = timedelta(minutes=_TF_MINUTES[timeframe])
        for t in times:
            assert t + duration <= as_of, (
                f"{timeframe}: candle open {t} + duration {duration} exceeds as_of {as_of} -- future leak"
            )


def test_replay_composition_never_touches_the_live_raw_cache():
    """P9/P10: TD-6's Layer A raw-candle cache lives INSIDE mt5.market_data.
    get_latest_candles's own body. If replay ever fell through to that real function,
    its cache counters would move. They must not -- the entire six-tier call graph is
    monkeypatched away by historical_data_context before any of it runs."""
    market_data.clear_raw_candle_cache()
    before = market_data.raw_candle_cache_diagnostics()

    store, _, _ = _load_full_store("EURUSD", _T)
    ctx = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)

    after = market_data.raw_candle_cache_diagnostics()
    assert after == before == {"hits": 0, "misses": 0, "evictions": 0, "puts": 0, "size": 0}
    assert ctx.data_quality_status == DATA_QUALITY_VALID


def _fake_mt5_rates(rows):
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")]
    return np.array(rows, dtype=dtype)


def test_pre_existing_live_cache_entry_cannot_answer_a_replay_request_of_the_same_shape():
    """P10 (LIVE_vs_REPLAY): populates the LIVE raw cache with a real (mocked-MT5-SDK)
    fetch for the exact same (symbol, timeframe, count) shape a replay request would
    use, then proves entering historical_data_context for that same shape returns the
    REPLAY data (not the live-cached entry) and never registers a cache hit."""
    market_data.clear_raw_candle_cache()
    live_epoch_time = int(datetime(1999, 1, 4, tzinfo=UTC).timestamp())  # wildly outside any replay window
    with patch("mt5.market_data._require_connected", return_value=None), \
         patch("mt5.market_data._require_symbol", return_value=None), \
         patch("mt5.market_data._broker_offset_hours", return_value=0), \
         patch("mt5.market_data.mt5.copy_rates_from_pos",
               return_value=_fake_mt5_rates([(live_epoch_time, 99.0, 99.1, 98.9, 99.05, 1)])):
        live_result = market_data.get_latest_candles("EURUSD", "M5", 1)
    assert live_result[0].open == 99.0
    assert market_data.raw_candle_cache_diagnostics()["size"] == 1

    t0 = datetime(2020, 1, 6, 0, 0, tzinfo=UTC)
    replay_store = HistoricalCandleStore()
    replay_store.load_series("EURUSD", "M5", [
        Candle(time=t0, open=1.0, high=1.0005, low=0.9995, close=1.0002, volume=1.0),
    ])
    hits_before = market_data.raw_candle_cache_diagnostics()["hits"]

    with historical_data_context(replay_store, t0 + timedelta(minutes=5)):
        replay_result = market_data.get_latest_candles("EURUSD", "M5", 1)

    assert replay_result[0].open == 1.0  # replay data, not the live-cached 99.0 entry
    assert market_data.raw_candle_cache_diagnostics()["hits"] == hits_before  # live cache never consulted


def test_replay_a_cannot_answer_replay_b_for_the_same_shape():
    """P10 (REPLAY_A_vs_REPLAY_B): two independent stores, entered as two independent
    historical_data_context scopes -- each must answer only from its own data, and
    their dataset fingerprints must differ even though symbol/timeframe/timestamp are
    identical (P15's narrower unit-level proof)."""
    t0 = datetime(2020, 1, 6, 0, 0, tzinfo=UTC)
    store_a = HistoricalCandleStore()
    store_a.load_series("EURUSD", "M5", [Candle(time=t0, open=1.0, high=1.0005, low=0.9995, close=1.0002, volume=1.0)],
                         dataset_id="A")
    store_b = HistoricalCandleStore()
    store_b.load_series("EURUSD", "M5", [Candle(time=t0, open=2.0, high=2.0005, low=1.9995, close=2.0002, volume=1.0)],
                         dataset_id="B")
    as_of = t0 + timedelta(minutes=5)

    with historical_data_context(store_a, as_of):
        result_a = market_data.get_latest_candles("EURUSD", "M5", 1)
    with historical_data_context(store_b, as_of):
        result_b = market_data.get_latest_candles("EURUSD", "M5", 1)

    assert result_a[0].open == 1.0
    assert result_b[0].open == 2.0
    assert store_a.dataset_identity("EURUSD", "M5").fingerprint != store_b.dataset_identity("EURUSD", "M5").fingerprint


def test_dataset_collision_same_timestamps_different_content_different_composed_identity():
    """P15: two full six-timeframe datasets sharing symbol/timeframe/timestamps but
    with different OHLC content (different base price) must never produce the same
    composed identity, and no raw/cache/provenance mechanism may let one answer the
    other's request (proven end to end through the real composer, not just the
    key-builder unit level)."""
    store_a, _, _ = _load_full_store("EURUSD", _T, dataset_label="CONTENT_A", base=1.1000, step=0.0006)
    store_b, _, _ = _load_full_store("EURUSD", _T, dataset_label="CONTENT_B", base=1.3000, step=0.0009)

    ctx_a = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store_a)
    ctx_b = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store_b)

    assert ctx_a.dataset_identity != ctx_b.dataset_identity
    assert ctx_a.context_id != ctx_b.context_id
    for tf in _ALL_TF:
        assert (store_a.dataset_identity("EURUSD", tf).fingerprint
                != store_b.dataset_identity("EURUSD", tf).fingerprint)


def test_future_leak_sentinel_does_not_alter_semantic_payload_at_t():
    """P14: an extreme-value candle strictly AFTER T (never eligible per
    HistoricalCandleStore's own closure rule, regardless of its content) must never
    change any tier's semantic payload -- proves future data is genuinely invisible to
    the real detector call graph, not merely excluded from the final reported
    timestamp."""
    store_normal, current_opens, _ = _load_full_store("EURUSD", _T, dataset_label="NORMAL")
    ctx_normal = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store_normal)

    store_mutated = HistoricalCandleStore()
    for tf in _ALL_TF:
        candles, _, _ = _series_for_timeframe(tf, _T)
        minutes = _TF_MINUTES[tf]
        future_open = current_opens[tf] + timedelta(minutes=minutes * 2)  # strictly after T
        mutated_candles = [
            Candle(time=c.time, open=1.0, high=999.0, low=0.0001, close=500.0, volume=c.volume)
            if c.time == future_open else c
            for c in candles
        ]
        store_mutated.load_series("EURUSD", tf, mutated_candles, dataset_id=f"EURUSD:{tf}:MUTATED", source="TEST_SOURCE")

    ctx_mutated = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store_mutated)

    # Dataset/composed identity LEGITIMATELY differ (the underlying dataset really is
    # different) -- per P12's own instruction, compare semantic payload separately.
    assert ctx_normal.dataset_identity != ctx_mutated.dataset_identity
    assert ctx_normal.context_id != ctx_mutated.context_id

    for tier_name in ("weekly", "daily", "h4", "h1", "m15", "m5"):
        tier_normal = getattr(ctx_normal, tier_name)
        tier_mutated = getattr(ctx_mutated, tier_name)
        assert tier_normal.bar_close_time == tier_mutated.bar_close_time
        assert tier_normal.data_quality_status == tier_mutated.data_quality_status
        assert tier_normal.structure_facts == tier_mutated.structure_facts
        assert tier_normal.zone_facts == tier_mutated.zone_facts
        assert tier_normal.imbalance_facts == tier_mutated.imbalance_facts
        assert tier_normal.liquidity_facts == tier_mutated.liquidity_facts
        assert tier_normal.reference_level_facts == tier_mutated.reference_level_facts


def test_parity_same_content_different_dataset_labels_semantic_payload_equal():
    """P12: replay must reuse the same shared detectors regardless of data source
    labeling -- two stores with IDENTICAL candle content (same base/step) but
    different dataset_id/source labels must produce EQUAL semantic payload per tier,
    even though their composed identity legitimately differs (labels are part of
    provenance identity -- see topdown_composer's DATASET IDENTITY docstring
    section)."""
    store_a, _, _ = _load_full_store("EURUSD", _T, dataset_label="VENDOR_A", source="VENDOR_A_EXPORT")
    store_b, _, _ = _load_full_store("EURUSD", _T, dataset_label="VENDOR_B", source="VENDOR_B_EXPORT")

    ctx_a = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store_a)
    ctx_b = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store_b)

    assert ctx_a.dataset_identity != ctx_b.dataset_identity  # labels differ -> identity differs
    for tier_name in ("weekly", "daily", "h4", "h1", "m15", "m5"):
        tier_a = getattr(ctx_a, tier_name)
        tier_b = getattr(ctx_b, tier_name)
        assert tier_a.bar_close_time == tier_b.bar_close_time
        assert tier_a.structure_facts == tier_b.structure_facts
        assert tier_a.zone_facts == tier_b.zone_facts
        assert tier_a.imbalance_facts == tier_b.imbalance_facts
        assert tier_a.liquidity_facts == tier_b.liquidity_facts
        assert tier_a.reference_level_facts == tier_b.reference_level_facts


def test_repeated_equivalent_replay_composition_is_deterministic():
    """P13/#13 analogue for HISTORICAL_AS_OF: composing twice from the SAME store at
    the SAME as_of_time must yield the same composed identity and semantic payload."""
    store, _, _ = _load_full_store("EURUSD", _T)
    ctx_1 = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)
    ctx_2 = build_topdown_context("EURUSD", as_of_time=_T, replay_store=store)

    assert ctx_1.context_id == ctx_2.context_id
    assert ctx_1.dataset_identity == ctx_2.dataset_identity
    assert ctx_1.to_dict() == ctx_2.to_dict()
