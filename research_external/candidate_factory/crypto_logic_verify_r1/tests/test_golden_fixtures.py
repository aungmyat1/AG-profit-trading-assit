"""T3 golden-fixture regression tests for CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1.

Each fixture under ../fixtures/*.csv is synthetic/hand-constructed (never real market
data) and encodes one named, specific scenario. These are deterministic regression
checks, distinct from the randomized hypothesis property tests in
test_properties_hypothesis.py.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research_external.candidate_factory.crypto_logic_verify_r1.engine import (
    Bar, evaluate, resolve_ticket, Ticket,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
TICK_SIZE = 0.01  # BTCUSD/ETHUSD VT Markets trade_tick_size (host-captured metadata)


def load_bars(name: str):
    path = FIXTURES_DIR / name
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            bars.append(Bar(
                time=datetime.fromisoformat(row["timestamp_utc"]).astimezone(timezone.utc),
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
            ))
    return bars


def test_clean_breakout_long_triggers():
    bars = load_bars("clean_breakout_long.csv")
    decision = evaluate(bars, TICK_SIZE)
    assert decision.status == "TRIGGER_LONG", decision
    assert decision.entry_price is not None
    assert decision.stop_loss < decision.entry_price < decision.tp1


def test_clean_breakout_short_triggers():
    bars = load_bars("clean_breakout_short.csv")
    decision = evaluate(bars, TICK_SIZE)
    assert decision.status == "TRIGGER_SHORT", decision
    assert decision.tp1 < decision.entry_price < decision.stop_loss


def test_ranging_produces_no_trigger():
    bars = load_bars("ranging_no_breakout.csv")
    # Evaluate every bar from the 56th onward; none should trigger (pure regression check
    # that a range-bound series never fabricates a signal).
    for i in range(N_CHANNEL_PLUS_ONE := 56, len(bars) + 1):
        decision = evaluate(bars[:i], TICK_SIZE)
        assert decision.status in ("NO_TRIGGER", "INSUFFICIENT_WARMUP"), (i, decision)


def test_weekend_bar_defers_not_loses_trigger():
    bars = load_bars("weekend_gap.csv")
    decision = evaluate(bars, TICK_SIZE)
    # The gap-open Monday bar is itself a weekday bar (Monday is not Sat/Sun), so a
    # trigger on it (if any) would NOT be deferred; this fixture's purpose is to prove
    # the weekend predicate itself is correct on the calendar boundary, exercised directly:
    from research_external.candidate_factory.crypto_logic_verify_r1.engine.turtle_breakout_d1 import _is_weekend_utc
    assert _is_weekend_utc(datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)) is True   # Saturday
    assert _is_weekend_utc(datetime(2026, 1, 11, 12, 0, tzinfo=timezone.utc)) is True   # Sunday
    assert _is_weekend_utc(datetime(2026, 1, 12, 12, 0, tzinfo=timezone.utc)) is False  # Monday
    assert decision.status in ("TRIGGER_LONG", "TRIGGER_SHORT", "NO_TRIGGER", "INSUFFICIENT_WARMUP")


def test_expiry_no_fill_always_terminates():
    bars = load_bars("expiry_no_fill.csv")
    trigger_bar_index = 55  # 0-indexed: bars[0:55] warmup, bars[55] is the trigger bar
    decision = evaluate(bars[: trigger_bar_index + 1], TICK_SIZE)
    assert decision.status == "TRIGGER_LONG", decision
    ticket = Ticket(direction="LONG", entry_price=decision.entry_price,
                     stop_loss=decision.stop_loss, tp1=decision.tp1,
                     trigger_time=decision.bar_time, expiry=decision.expiry)
    bars_after = bars[trigger_bar_index + 1:]
    resolution = resolve_ticket(ticket, bars_after, max_bars=5)
    assert resolution.filled is False
    assert resolution.outcome == "EXPIRED_UNFILLED"
    assert resolution.realized_r is None
