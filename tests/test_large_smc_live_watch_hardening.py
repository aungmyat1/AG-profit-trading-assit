"""P4 focused tests: Large-SMC live-watch hardening
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1).

Proves both confirmed defects and their fixes:

  DEFECT 1 -- the old watcher passed TRUE-UTC candle times to
  `resample_broker_aligned`, which requires BROKER WALL-CLOCK readings. The first tests
  below demonstrate the defect is real (UTC input degrades broker-anchored bucketing)
  and that `resolve_broker_times` restores correct broker alignment, including
  cross-validation against NATIVE broker D1/H4 candles where the exports are present.

  DEFECT 2 -- the old watcher re-ran the full 150-day window every invocation. The
  window tests prove evaluation is now incremental, that consecutive runs neither
  overlap nor skip a bar, and that warm-up is still preserved.

Plus the fail-closed rules (insufficient warm-up, stale data, ordering) and the
execution boundary. No test here asserts any economic edge or authorizes demo/live.
"""
from __future__ import annotations

import ast
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(REPO_ROOT / "src"))

from historical_replay import resample, resample_broker_aligned  # noqa: E402
from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from large_smc_research.live_watch import (  # noqa: E402
    DEFAULT_MAX_STALENESS_HOURS,
    LiveWatchError,
    WatchState,
    WatchStateStore,
    build_store,
    check_freshness,
    check_ordering,
    determine_evaluation_window,
    evaluate_increment,
    find_warmup_floor,
    next_watermark,
    resolve_broker_times,
)
from strategy_engine.session import Candle  # noqa: E402

UTC = timezone.utc
WATCH_SCRIPT = REPO_ROOT / "scripts" / "run_large_smc_live_watch.py"
LIVE_WATCH_MODULE = REPO_ROOT / "src" / "large_smc_research" / "live_watch.py"

# Real broker exports (M5/Daily paths match tests/test_resampler_broker_aligned.py).
REAL_M5 = r"D:\EURUSD_M5_202504211715_202607310000.csv"
REAL_DAILY = r"D:\EURUSD_Daily_202501020000_202607310000.csv"
REAL_H4 = r"D:\EURUSD_H4_202401020000_202609182000.csv"


def _m5_series(start_utc: datetime, count: int, price: float = 1.10):
    """Contiguous UTC M5 candles, ascending, no gaps -- a clean base feed."""
    out = []
    for i in range(count):
        t = start_utc + timedelta(minutes=5 * i)
        out.append(Candle(time=t, open=price, high=price + 0.001,
                          low=price - 0.001, close=price, volume=1.0))
    return out


# ===========================================================================
# DEFECT 1 -- time alignment
# ===========================================================================

def test_resolve_broker_times_reconstructs_wall_clock():
    """The inverse of `mt5.market_data.get_candles`'s normalization
    (true_utc = broker_wall_clock - offset)."""
    candles = _m5_series(datetime(2026, 9, 14, 21, 0, tzinfo=UTC), 3)
    broker = resolve_broker_times(candles, 3)
    assert broker[0] == datetime(2026, 9, 15, 0, 0)  # naive wall clock
    assert broker[0].tzinfo is None, "broker wall-clock readings must be naive"
    assert broker[0] - candles[0].time.replace(tzinfo=None) == timedelta(hours=3)


def test_resolve_broker_times_handles_both_seasonal_offsets():
    """The broker shifts UTC+2 winter / +3 summer -- both must reconstruct correctly."""
    candles = _m5_series(datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 2)
    assert resolve_broker_times(candles, 2)[0] == datetime(2026, 1, 5, 2, 0)
    assert resolve_broker_times(candles, 3)[0] == datetime(2026, 1, 5, 3, 0)


def test_resolve_broker_times_rejects_non_integer_offset():
    with pytest.raises(LiveWatchError, match="INVALID_BROKER_OFFSET"):
        resolve_broker_times(_m5_series(datetime(2026, 9, 14, tzinfo=UTC), 2), 3.5)


def test_defect_1_utc_input_degrades_broker_alignment():
    """THE DEFECT, demonstrated. Feeding true-UTC times (what the old watcher did) makes
    broker-anchored D1 bucketing collapse to UTC-midnight bucketing -- so most broker
    days are anchored on the wrong instant (and the first bucket is a partial day)."""
    # 3 broker days starting at broker midnight = 21:00 UTC the previous day (offset +3).
    start_utc = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    candles = _m5_series(start_utc, 288 * 3)

    buggy = resample_broker_aligned(candles, [c.time for c in candles], "M5", "D1")
    fixed = resample_broker_aligned(candles, resolve_broker_times(candles, 3), "M5", "D1")

    buggy_times = [b.time for b in buggy]
    fixed_times = [b.time for b in fixed]

    # The fixed path yields exactly 3 complete broker days, all anchored at 21:00 UTC.
    assert fixed_times == [
        datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 21, 0, tzinfo=UTC),
        datetime(2026, 9, 16, 21, 0, tzinfo=UTC),
    ]

    # The buggy path buckets on UTC midnight instead: different count, wrong boundaries.
    assert buggy_times != fixed_times, (
        "UTC input should bucket differently from broker-aligned input -- if these are "
        "equal, this fixture no longer exercises the defect")
    assert buggy_times[1].hour == 0, "UTC input anchors on UTC midnight"
    assert fixed_times[1].hour == 21, "broker-aligned input anchors on broker midnight"


def test_defect_1_broker_d1_boundaries_are_21_or_22_utc():
    """With a +3 broker offset, derived D1 bars must start at 21:00 UTC (broker
    midnight), never at 00:00 UTC."""
    candles = _m5_series(datetime(2026, 9, 14, 21, 0, tzinfo=UTC), 288 * 3)
    fixed = resample_broker_aligned(candles, resolve_broker_times(candles, 3), "M5", "D1")
    assert len(fixed) == 3
    for bar in fixed:
        assert bar.time.hour == 21, f"{bar.time} is not a broker-midnight boundary"


def test_build_store_uses_broker_alignment_for_d1_and_h4_only():
    """D1/H4 broker-aligned; M15/H1 stay UTC-bucketed (correct for whole-hour offsets)."""
    candles = _m5_series(datetime(2026, 9, 14, 21, 0, tzinfo=UTC), 288 * 4)
    store = build_store("EURUSD", candles, 3)
    as_of = candles[-1].time + timedelta(minutes=5)

    d1 = store.closed_candles("EURUSD", "D1", as_of, 3)
    assert d1, "expected derived D1 bars"
    assert all(b.time.hour == 21 for b in d1), "D1 must be broker-anchored"

    h4 = store.closed_candles("EURUSD", "H4", as_of, 3)
    assert h4, "expected derived H4 bars"
    # Broker-anchored 4h windows land on UTC 21/01/05/09/13/17 with a +3 offset -- NOT
    # on the UTC 00/04/08/12/16/20 boundaries a plain UTC resample would produce. This
    # is the H4 half of the time-alignment defect.
    assert {b.time.hour for b in h4} <= {1, 5, 9, 13, 17, 21}, (
        "H4 boundaries must be broker-anchored, not UTC-anchored")

    m15 = store.closed_candles("EURUSD", "M15", as_of, 3)
    assert all(b.time.minute % 15 == 0 for b in m15)


def test_h1_derivation_is_unaffected_by_the_offset():
    """H1 must be identical whether or not the broker offset is applied -- proving the
    fix is scoped to D1/H4 and cannot regress M15/H1. (`resample_broker_aligned`
    rejects H1 by contract, so the store's H1 must come from the plain UTC path.)"""
    from historical_replay.candle_store import HistoricalDataError

    candles = _m5_series(datetime(2026, 9, 14, 0, 0, tzinfo=UTC), 288 * 2)
    as_of = candles[-1].time + timedelta(minutes=5)
    utc_h1 = resample(list(candles), "M5", "H1")

    store = build_store("EURUSD", candles, 3)
    store_h1 = store.closed_candles("EURUSD", "H1", as_of, 3)
    assert [b.time for b in store_h1] == [b.time for b in utc_h1][-len(store_h1):]

    with pytest.raises(HistoricalDataError):
        resample_broker_aligned(list(candles), resolve_broker_times(candles, 3), "M5", "H1")


# --- parity against NATIVE broker candles -----------------------------------

@pytest.mark.skipif(not (os.path.exists(REAL_M5) and os.path.exists(REAL_DAILY)),
                    reason="real M5/Daily exports not present")
def test_parity_derived_d1_matches_native_broker_d1_candles():
    """PARITY AGAINST NATIVE BROKER D1. The broker-aligned D1 built the way the FIXED
    watcher builds it must match MT5's own natively-exported D1 candles (excluding the
    dataset's own partial first/last day, a coverage boundary effect).

    The native D1 export is DATE-only in broker time; a derived bar at 21:00/22:00 UTC
    is that broker day, so the mapping is `derived.time + offset -> date` and is robust
    across the seasonal offset change (both +2 and +3 land on the same date)."""
    import csv

    m5_candles, report = load_mt5_export_csv(REAL_M5, "EURUSD", "M5")
    derived = resample_broker_aligned(m5_candles, report.broker_times, "M5", "D1")

    native_by_date = {}
    with open(REAL_DAILY, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for row in reader:
            if len(row) < 5 or not row[0].strip():
                continue
            day = datetime.strptime(row[0].strip(), "%Y.%m.%d").date()
            native_by_date[day] = tuple(float(v) for v in row[1:5])

    compared = mismatches = 0
    for bar in derived[1:-1]:  # drop the dataset's own partial-day edges
        broker_date = (bar.time + timedelta(hours=3)).date()
        native = native_by_date.get(broker_date)
        if native is None:
            continue
        compared += 1
        if (bar.open, bar.high, bar.low, bar.close) != native:
            mismatches += 1

    assert compared > 300, f"expected a substantial overlap, compared only {compared}"
    assert mismatches == 0, (
        f"derived D1 mismatched {mismatches}/{compared} native broker D1 bars -- "
        "broker alignment is wrong")


@pytest.mark.skipif(not (os.path.exists(REAL_M5) and os.path.exists(REAL_H4)),
                    reason="real M5/H4 exports not present")
def test_parity_derived_h4_matches_native_broker_h4_candles():
    """PARITY AGAINST NATIVE BROKER H4 -- the other half of the time-alignment defect.

    Restricted to a summer window (constant +3 offset) so the broker wall-clock
    reconstruction is exact for every compared bar."""
    import csv

    m5_candles, report = load_mt5_export_csv(REAL_M5, "EURUSD", "M5")
    derived = resample_broker_aligned(m5_candles, report.broker_times, "M5", "H4")

    native = {}
    with open(REAL_H4, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for row in reader:
            if len(row) < 6 or not row[0].strip():
                continue
            stamp = datetime.strptime(f"{row[0].strip()} {row[1].strip()}", "%Y.%m.%d %H:%M:%S")
            native[stamp] = tuple(float(v) for v in row[2:6])

    summer_start = datetime(2026, 5, 1)
    summer_end = datetime(2026, 7, 30)  # 2026-07-31 is the export's own final partial day
    compared = mismatches = 0
    for bar in derived:
        broker_naive = (bar.time + timedelta(hours=3)).replace(tzinfo=None)
        if not (summer_start <= broker_naive <= summer_end):
            continue
        expected = native.get(broker_naive)
        if expected is None:
            continue
        compared += 1
        if (bar.open, bar.high, bar.low, bar.close) != expected:
            mismatches += 1

    assert compared > 100, f"expected a substantial overlap, compared only {compared}"
    assert mismatches == 0, (
        f"derived H4 mismatched {mismatches}/{compared} native broker H4 bars")


@pytest.mark.skipif(not (os.path.exists(REAL_M5) and os.path.exists(REAL_DAILY)),
                    reason="real M5/Daily exports not present")
def test_utc_bucketed_d1_does_not_match_native_broker_d1():
    """Confirms the defect was real on real data: plain UTC bucketing does NOT align
    with native broker D1, which is exactly why broker alignment is required.

    A UTC-midnight bucket is labelled by the UTC date, but a broker day runs from
    21:00/22:00 UTC -- so the UTC-derived label is the PREVIOUS broker date. The
    decisive, robust check is therefore that UTC bucketing produces a different number
    of bars and a different set of boundaries than the broker-aligned derivation."""
    import csv

    m5_candles, report = load_mt5_export_csv(REAL_M5, "EURUSD", "M5")
    utc_d1 = resample(m5_candles, "M5", "D1")
    broker_d1 = resample_broker_aligned(m5_candles, report.broker_times, "M5", "D1")

    # Every UTC bucket starts at UTC midnight; no broker bucket does.
    assert all(b.time.hour == 0 for b in utc_d1)
    assert not any(b.time.hour == 0 for b in broker_d1), (
        "broker-aligned D1 must not start at UTC midnight")
    assert len(utc_d1) != len(broker_d1), (
        "UTC and broker-aligned bucketing must yield different bar counts")

    # And the native D1 export's own dates never coincide with a UTC bucket's own
    # broker-day label for the same bar.
    native_dates = set()
    with open(REAL_DAILY, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for row in reader:
            if len(row) < 5 or not row[0].strip():
                continue
            native_dates.add(datetime.strptime(row[0].strip(), "%Y.%m.%d").date())

    aligned_labels = sum(
        1 for b in broker_d1[1:-1] if (b.time + timedelta(hours=3)).date() in native_dates)
    assert aligned_labels > 300, (
        "broker-aligned buckets must map onto native broker dates")


# ===========================================================================
# DEFECT 2 -- incrementality
# ===========================================================================

def _warm_enough_series(start_utc: datetime, days: int):
    """M5 series long enough to clear the 60-D1 warm-up (needs > 60 broker days)."""
    return _m5_series(start_utc, 288 * days)


def test_warmup_floor_is_found_and_preserves_warmup():
    """The incremental window must never start before warm-up is cleared -- that is how
    'preserves adequate warm-up' is guaranteed."""
    candles = _warm_enough_series(datetime(2026, 3, 1, 0, 0, tzinfo=UTC), 150)
    store = build_store("EURUSD", candles, 3)
    floor = find_warmup_floor(store, "EURUSD", candles)
    assert floor is not None, "150 days should clear warm-up"
    assert floor > candles[0].time, "warm-up floor must be later than the first bar"


def test_warmup_floor_is_absent_when_history_is_too_short():
    candles = _m5_series(datetime(2026, 9, 1, 0, 0, tzinfo=UTC), 288 * 5)  # 5 days
    store = build_store("EURUSD", candles, 3)
    assert find_warmup_floor(store, "EURUSD", candles) is None


def test_first_run_evaluates_from_warmup_floor_not_window_start():
    """A first run (no watermark) starts at the warm-up floor, so it never wastes the
    window on bars the engine would reject as warm-up anyway."""
    candles = _warm_enough_series(datetime(2026, 3, 1, 0, 0, tzinfo=UTC), 150)
    store = build_store("EURUSD", candles, 3)
    window = determine_evaluation_window(store, "EURUSD", candles, None)
    assert window.start_utc == window.warmup_floor_utc
    assert window.watermark_utc is None
    assert window.steps > 0


def test_second_run_is_incremental_and_far_smaller():
    """THE DEFECT-2 FIX. With a watermark, the evaluated step count must collapse from
    ~the whole window to only the bars closed since the previous run."""
    candles = _warm_enough_series(datetime(2026, 3, 1, 0, 0, tzinfo=UTC), 150)
    store = build_store("EURUSD", candles, 3)

    first = determine_evaluation_window(store, "EURUSD", candles, None)
    last_as_of, next_start = next_watermark(first, candles)

    second = determine_evaluation_window(store, "EURUSD", candles, next_start)

    assert first.steps > 10_000, "first run should cover a large window"
    assert second.steps < first.steps, "second run must evaluate strictly less"
    # The watermark sits near the end, so only the final bar (or none) remains.
    assert second.steps <= 1


def test_consecutive_windows_neither_overlap_nor_skip():
    """The half-open boundary must be exact: the first close of run N+1 is strictly
    after the last close of run N."""
    candles = _warm_enough_series(datetime(2026, 3, 1, 0, 0, tzinfo=UTC), 150)
    store = build_store("EURUSD", candles, 3)

    first = determine_evaluation_window(store, "EURUSD", candles, None)
    last_as_of, next_start = next_watermark(first, candles)
    second = determine_evaluation_window(store, "EURUSD", candles, next_start)

    assert second.start_utc == next_start
    assert second.start_utc > last_as_of
    assert (second.start_utc - last_as_of) == timedelta(minutes=5), (
        "consecutive windows must be exactly one M5 bar apart")


def test_watermark_advances_monotonically_over_many_runs():
    """Simulates a week of incremental runs over a growing feed."""
    start = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    base = _warm_enough_series(start, 150)
    store = build_store("EURUSD", base, 3)

    state = WatchState("ST_LARGE_SMC_V1", "1.0.7", "EURUSD", None, None, 0, None, None)
    watermarks = []
    candles = list(base)
    for _ in range(5):
        candles = candles + _m5_series(
            candles[-1].time + timedelta(minutes=5), 288)  # one more day
        store = build_store("EURUSD", candles, 3)
        window = determine_evaluation_window(store, "EURUSD", candles, state.next_start_utc)
        if window.is_empty:
            continue
        last_as_of, next_start = next_watermark(window, candles)
        watermarks.append(next_start)
        state = WatchState("ST_LARGE_SMC_V1", "1.0.7", "EURUSD", last_as_of,
                           next_start, state.runs + 1, None, 3)

    assert len(watermarks) >= 4
    assert watermarks == sorted(watermarks)
    assert len(set(watermarks)) == len(watermarks), "watermark must strictly advance"


def test_no_new_bars_yields_an_empty_window_not_an_error():
    """Re-running with an unchanged feed must be a clean no-op, not a failure."""
    candles = _warm_enough_series(datetime(2026, 3, 1, 0, 0, tzinfo=UTC), 150)
    store = build_store("EURUSD", candles, 3)
    first = determine_evaluation_window(store, "EURUSD", candles, None)
    _, next_start = next_watermark(first, candles)
    second = determine_evaluation_window(store, "EURUSD", candles, next_start)
    assert second.is_empty is True


# ===========================================================================
# Fail-closed rules
# ===========================================================================

def test_insufficient_warmup_fails_closed():
    """Previously this produced valid_steps=0 and an empty ledger -- indistinguishable
    from 'no setups found'. It must now refuse loudly."""
    candles = _m5_series(datetime(2026, 9, 1, 0, 0, tzinfo=UTC), 288 * 3)
    store = build_store("EURUSD", candles, 3)
    with pytest.raises(LiveWatchError, match="INSUFFICIENT_WARMUP_DATA"):
        determine_evaluation_window(store, "EURUSD", candles, None)


def test_no_candles_fails_closed():
    with pytest.raises(LiveWatchError, match="NO_M5_CANDLES_RETURNED"):
        build_store("EURUSD", [], 3)


def test_stale_data_fails_closed():
    candles = _m5_series(datetime(2026, 3, 1, tzinfo=UTC), 288 * 150)
    now = candles[-1].time + timedelta(hours=DEFAULT_MAX_STALENESS_HOURS + 1)
    with pytest.raises(LiveWatchError, match="STALE_DATA"):
        check_freshness(candles, now)


def test_fresh_data_passes():
    candles = _m5_series(datetime(2026, 3, 1, tzinfo=UTC), 288 * 2)
    check_freshness(candles, candles[-1].time + timedelta(minutes=10))


def test_weekend_staleness_is_tolerated():
    """A ~47h weekend closure must not trip the staleness gate."""
    candles = _m5_series(datetime(2026, 3, 1, tzinfo=UTC), 288 * 2)
    check_freshness(candles, candles[-1].time + timedelta(hours=47))


def test_out_of_order_candles_fail_closed():
    candles = _m5_series(datetime(2026, 3, 1, tzinfo=UTC), 10)
    scrambled = [candles[1], candles[0]] + candles[2:]
    with pytest.raises(LiveWatchError, match="OUT_OF_ORDER_OR_DUPLICATE_CANDLES"):
        check_ordering(scrambled)


def test_duplicate_candles_fail_closed():
    candles = _m5_series(datetime(2026, 3, 1, tzinfo=UTC), 10)
    with pytest.raises(LiveWatchError, match="OUT_OF_ORDER_OR_DUPLICATE_CANDLES"):
        check_ordering([candles[0], candles[0]])


# ===========================================================================
# Watcher state
# ===========================================================================

def test_watch_state_round_trips(tmp_path):
    store = WatchStateStore(str(tmp_path / "watch.json"))
    saved = WatchState(
        "ST_LARGE_SMC_V1", "1.0.7", "EURUSD",
        datetime(2026, 9, 18, 21, 0, tzinfo=UTC),
        datetime(2026, 9, 18, 21, 5, tzinfo=UTC), 3,
        datetime(2026, 9, 18, 21, 1, tzinfo=UTC), 3,
    )
    store.save(saved)
    loaded = store.load("ST_LARGE_SMC_V1", "1.0.7", "EURUSD")
    assert loaded == saved


def test_watch_state_is_empty_for_an_unseen_symbol(tmp_path):
    store = WatchStateStore(str(tmp_path / "watch.json"))
    state = store.load("ST_LARGE_SMC_V1", "1.0.7", "EURUSD")
    assert state.has_watermark is False
    assert state.runs == 0


def test_watch_state_is_version_scoped(tmp_path):
    """A strategy version bump must not inherit the prior version's watermark."""
    store = WatchStateStore(str(tmp_path / "watch.json"))
    store.save(WatchState("ST_LARGE_SMC_V1", "1.0.7", "EURUSD", None,
                          datetime(2026, 9, 18, 21, 5, tzinfo=UTC), 1, None, 3))
    assert store.load("ST_LARGE_SMC_V1", "1.0.8", "EURUSD").has_watermark is False


def test_watch_state_survives_restart(tmp_path):
    path = str(tmp_path / "watch.json")
    WatchStateStore(path).save(WatchState(
        "ST_LARGE_SMC_V1", "1.0.7", "EURUSD", None,
        datetime(2026, 9, 18, 21, 5, tzinfo=UTC), 1, None, 3))
    assert WatchStateStore(path).load(
        "ST_LARGE_SMC_V1", "1.0.7", "EURUSD").next_start_utc is not None


# ===========================================================================
# Execution boundary (RESEARCH_ONLY)
# ===========================================================================

FORBIDDEN = {"execution.executor", "execution.coordinator", "execution.adapter",
             "mt5.management_gateway", "execution.mt5_gateway"}


def _assert_no_forbidden_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in FORBIDDEN, f"{path.name} imports {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in FORBIDDEN, f"{path.name} imports from {module}"
            assert not module.startswith("execution."), f"{path.name} imports from {module}"


def test_live_watch_module_has_no_execution_reach():
    _assert_no_forbidden_imports(LIVE_WATCH_MODULE)


def test_watcher_script_has_no_execution_reach():
    _assert_no_forbidden_imports(WATCH_SCRIPT)


def test_watcher_never_calls_order_functions():
    for path in (WATCH_SCRIPT, LIVE_WATCH_MODULE):
        source = path.read_text(encoding="utf-8")
        for name in ("order_send", "order_check", "positions_close", "positions_modify"):
            assert name not in source, f"{path.name} references {name}"


def test_watcher_is_not_registered_with_task_scheduler():
    """The mission's own gate: the watcher must not be scheduled until its correctness
    tests pass. This asserts no task referencing it exists in the repo's installer
    scripts."""
    for candidate in (REPO_ROOT / "scripts").glob("*.ps1"):
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        assert "run_large_smc_live_watch" not in text, (
            f"{candidate.name} schedules the Large SMC watcher -- not permitted while "
            "the campaign is incomplete / before correctness sign-off")
