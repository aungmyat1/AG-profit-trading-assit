"""Mission 1 / P4 -- SSC one-year replay warmup convergence (VA2).

Proves, for representative decision points across the one-year window, that (a) the
required minimum of closed H1 bars (1000, matching market_structure.tiers's own
`EXTERNAL_SWING_LENGTH * 20` warmup requirement) is actually available once the
WARMUP_CONTEXT_ONLY leg is merged in front of the decision-window leg, and (b) once that
minimum is available, adding MORE preceding H1 history never changes the strategy-visible
initialized context for a fixed decision instant.

(b) is not a statistical inference -- it is a direct consequence of
`HistoricalCandleStore.closed_candles`'s own slicing rule (`start_index = max(0,
end_index - count)`; see candle_store.py): the window handed to any consumer (structure
tiers, bias resolution, ...) for a given `as_of` is always exactly the most recent
`count` closed bars, so once `count` bars are available, prepending further history
cannot change which bars are in that slice. This test proves the general store property
AND exercises it on the actual one-year merged series, rather than trusting the
architecture argument alone.

No SSC replay, no bias resolution, no symbol-metadata/tick_size authorization is
exercised here -- this module answers a data-readiness question only, using the existing
`historical_replay.warmup_readiness` authority named by the mission.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.mt5_export_loader import load_mt5_export_csv
from historical_replay.utc_export_csv_loader import load_utc_export_csv
from historical_replay.warmup_merge import merge_warmup_and_decision_window
from historical_replay.warmup_readiness import closed_h1_bar_count

REPO = Path(__file__).resolve().parents[1]
DERIVED_H1 = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_H1.csv"
WARMUP_H1 = Path(r"D:\EURUSD_H1_202501020000_202607310000.csv")

REQUIRED_H1_BARS = 1000  # market_structure.tiers.analyze_structure_tiers: EXTERNAL_SWING_LENGTH(50) * 20

WINDOW_START = datetime(2025, 9, 15, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)


def _merged_series():
    # Gaps (e.g. the Christmas/New Year closure) are expected market-closure artifacts
    # of the warmup leg, not a quality defect -- this leg's alignment (+0h, exact=1.0,
    # DST_CONSISTENT) is independently established by
    # scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py; this test only needs
    # its candles, not a fresh quality re-adjudication.
    warmup_candles, _warmup_report = load_mt5_export_csv(str(WARMUP_H1), "EURUSD", "H1")
    decision_candles, decision_report = load_utc_export_csv(str(DERIVED_H1), "EURUSD", "H1")
    assert decision_report.normalized_timezone == "UTC"
    return merge_warmup_and_decision_window(warmup_candles, decision_candles)


@pytest.fixture(scope="module")
def merged_h1():
    return _merged_series()


@pytest.fixture(scope="module")
def representative_decision_points():
    return {
        "FIRST": WINDOW_START,
        "MID": WINDOW_START + timedelta(days=180),
        "LAST": WINDOW_END,
    }


def test_general_store_property_extra_history_never_changes_a_sufficient_slice():
    """Locks the general HistoricalCandleStore.closed_candles contract this whole
    convergence proof depends on, independent of the one-year dataset: once >= count
    bars are closed by as_of, prepending MORE bars before the existing history must not
    change the returned slice."""
    from strategy_engine.session import Candle

    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    tail = [
        Candle(time=base + timedelta(hours=i), open=1.0, high=1.0, low=1.0, close=1.0, volume=1)
        for i in range(50)
    ]
    as_of = tail[-1].time + timedelta(hours=1)

    short_store = HistoricalCandleStore()
    short_store.load_series("EURUSD", "H1", tail)
    short_slice = short_store.closed_candles("EURUSD", "H1", as_of, 20)

    extra_history = [
        Candle(time=base - timedelta(hours=i), open=1.0, high=1.0, low=1.0, close=1.0, volume=1)
        for i in range(1, 5001)
    ]
    long_store = HistoricalCandleStore()
    long_store.load_series("EURUSD", "H1", extra_history + tail)
    long_slice = long_store.closed_candles("EURUSD", "H1", as_of, 20)

    assert short_slice == long_slice


def test_warmup_bar_sufficiency_at_representative_decision_points(merged_h1, representative_decision_points):
    counts = {
        label: closed_h1_bar_count(merged_h1, as_of)
        for label, as_of in representative_decision_points.items()
    }
    for label, count in counts.items():
        assert count >= REQUIRED_H1_BARS, f"{label}: only {count} closed H1 bars (need {REQUIRED_H1_BARS})"


def test_warmup_convergence_minimal_vs_full_history(merged_h1, representative_decision_points):
    """For each representative decision point, the exactly-1000-bar slice computed from
    the full merged series must equal the slice computed from a store holding ONLY that
    minimal tail -- proving the initialized context is identical regardless of how much
    additional warmup history preceded it."""
    for label, as_of in representative_decision_points.items():
        full_store = HistoricalCandleStore()
        full_store.load_series("EURUSD", "H1", merged_h1)
        full_slice = full_store.closed_candles("EURUSD", "H1", as_of, REQUIRED_H1_BARS)

        minimal_store = HistoricalCandleStore()
        minimal_store.load_series("EURUSD", "H1", full_slice)
        minimal_slice = minimal_store.closed_candles("EURUSD", "H1", as_of, REQUIRED_H1_BARS)

        assert full_slice == minimal_slice, f"{label}: warmup-convergence mismatch"


def test_warmup_classification_is_stable_for_the_one_year_window(merged_h1, representative_decision_points):
    """Final VA2 classification: WARMUP_STABLE requires sufficiency AND convergence at
    every representative point; otherwise WARMUP_INSUFFICIENT (bar shortfall) or
    WARMUP_UNSTABLE (convergence failure) -- this test asserts the stack qualifies as
    WARMUP_STABLE."""
    classification = "WARMUP_STABLE"
    for label, as_of in representative_decision_points.items():
        count = closed_h1_bar_count(merged_h1, as_of)
        if count < REQUIRED_H1_BARS:
            classification = "WARMUP_INSUFFICIENT"
            break
        full_store = HistoricalCandleStore()
        full_store.load_series("EURUSD", "H1", merged_h1)
        full_slice = full_store.closed_candles("EURUSD", "H1", as_of, REQUIRED_H1_BARS)
        minimal_store = HistoricalCandleStore()
        minimal_store.load_series("EURUSD", "H1", full_slice)
        minimal_slice = minimal_store.closed_candles("EURUSD", "H1", as_of, REQUIRED_H1_BARS)
        if full_slice != minimal_slice:
            classification = "WARMUP_UNSTABLE"
            break

    assert classification == "WARMUP_STABLE"
