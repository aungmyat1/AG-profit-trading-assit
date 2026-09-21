"""DRAFT — Mission 1 / P4: VA2 warm-up convergence proof for the one-year replay stack.

Question answered: for representative SSC decision points, does ADDITIONAL closed H1
history beyond the canonical minimum change the strategy-visible initialized context
(the frozen MarketBiasResult)? Classification:

  WARMUP_STABLE      -- context identical for every warmup prefix length >= minimum
  WARMUP_INSUFFICIENT-- minimum bars not reachable from the stack
  WARMUP_UNSTABLE    -- context keeps changing as history grows (fail closed)

No strategy parameter is touched; this is a data-readiness proof only. It reuses the
frozen authorities: historical_replay.warmup_readiness (actual closed-bar counting) and
session_sweep_continuation.h1_bias.resolve_h1_market_bias (the H1 bias authority).

Agent finalization points (marked TODO):
  - DECISION_TIMES: enumerate from the SSC replay decision schedule (session-pair
    reference ends across the window: first decision + quarterly checkpoints + both
    session pairs). Representative, outcome-independent selection only.
  - manifest path: the H1 symbol-metadata manifest bound to the STACK's H1 leg
    (post Mission-1 that is the one-year stack's own manifest -- DEV_002's is NOT it).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO / "src"))

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.symbol_metadata_manifest import load_symbol_metadata_manifest
from historical_replay.utc_export_csv_loader import load_utc_export_csv
from historical_replay.warmup_readiness import closed_h1_bar_count
from session_sweep_continuation.h1_bias import resolve_h1_market_bias

UTC = timezone.utc
SYMBOL = "EURUSD"
MIN_H1_WARMUP_BARS = 1000

# TODO(agent): bind to the one-year stack's H1 manifest once P8 freezes it.
H1_MANIFEST_PATH = REPO / "config/historical_datasets/<STACK_H1_symbol_metadata>.yaml"
H1_CSV = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_H1.csv"
WARMUP_H1_CSV = None  # TODO(agent): the declared WARMUP_CONTEXT_ONLY pre-window H1 leg

# TODO(agent): enumerate from the SSC decision schedule (outcome-independent):
DECISION_TIMES = [
    (datetime(2025, 9, 16, 6, 0, tzinfo=UTC), "ASIAN_LONDON"),
    (datetime(2025, 12, 15, 18, 0, tzinfo=UTC), "LONDON_NEWYORK"),
    (datetime(2026, 3, 16, 6, 0, tzinfo=UTC), "ASIAN_LONDON"),
    (datetime(2026, 6, 15, 18, 0, tzinfo=UTC), "LONDON_NEWYORK"),
    (datetime(2026, 9, 14, 6, 0, tzinfo=UTC), "ASIAN_LONDON"),
]

# Prefix lengths (closed H1 bars before the decision) at which convergence is probed.
PROBE_LENGTHS = (1000, 1250, 1500, 2000, 3000, 4500)


def _full_h1():
    candles, _ = load_utc_export_csv(str(H1_CSV), SYMBOL, "H1")
    if WARMUP_H1_CSV is not None:
        warm, _ = load_utc_export_csv(str(WARMUP_H1_CSV), SYMBOL, "H1")
        candles = sorted(warm + candles, key=lambda c: c.time)
    return candles


def _store_with_last_n(h1, as_of: datetime, n_bars: int) -> HistoricalCandleStore:
    """A store holding only the n_bars most recent CLOSED H1 bars before as_of --
    i.e., the exact warmup prefix a replay would have at that depth."""
    closed = [c for c in h1 if c.time <= as_of]  # store closure convention: open <= as_of - 1h
    prefix = closed[-n_bars:] if len(closed) >= n_bars else closed
    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "H1", prefix, dataset_id="WARMUP_PROBE", source="REPLAY")
    return store


@pytest.fixture(scope="module")
def manifest():
    return load_symbol_metadata_manifest(H1_MANIFEST_PATH)


def test_warmup_prefix_depths_available():
    h1 = _full_h1()
    first_decision = min(t for t, _ in DECISION_TIMES)
    assert closed_h1_bar_count(h1, first_decision) >= MIN_H1_WARMUP_BARS, (
        "WARMUP_INSUFFICIENT: the stack cannot supply the canonical minimum before the first decision"
    )


def test_warmup_convergence_classification_is_stable(manifest):
    """Core VA2 proof: at every decision point, the frozen MarketBiasResult is identical
    for ALL probed warmup depths >= minimum. Any divergence => WARMUP_UNSTABLE and the
    stack is inadmissible until the cause is found (never patched by changing parameters)."""
    h1 = _full_h1()
    unstable = []
    for decision_time, session_pair in DECISION_TIMES:
        results = {}
        for n in PROBE_LENGTHS:
            if closed_h1_bar_count(h1, decision_time) < n:
                continue  # this depth not reachable at this decision -- not instability
            store = _store_with_last_n(h1, decision_time, n)
            results[n] = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, session_pair)
        if not results:
            unstable.append((decision_time, "NO_PROBE_DEPTH_REACHABLE"))
            continue
        reference = next(iter(results.values()))
        for n, r in results.items():
            # MarketBiasResult is a frozen dataclass: structural equality is the contract.
            if r != reference:
                unstable.append((decision_time, f"depth {n} diverges from reference"))
    assert not unstable, f"WARMUP_UNSTABLE at: {unstable}"


def test_warmup_never_uses_future_bars():
    """Boundary sanity: a store truncated exactly at the decision time must equal one
    holding the full series (the store's own closed-bar rule enforces it) -- proves the
    convergence probe itself has no lookahead."""
    h1 = _full_h1()
    decision_time, session_pair = DECISION_TIMES[0]
    manifest = load_symbol_metadata_manifest(H1_MANIFEST_PATH)
    full = HistoricalCandleStore()
    full.load_series(SYMBOL, "H1", h1, dataset_id="FULL", source="REPLAY")
    truncated = _store_with_last_n(h1, decision_time, closed_h1_bar_count(h1, decision_time))
    a = resolve_h1_market_bias(full, manifest, SYMBOL, decision_time, session_pair)
    b = resolve_h1_market_bias(truncated, manifest, SYMBOL, decision_time, session_pair)
    assert a == b
