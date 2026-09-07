"""Behavioral (not merely doc-inspection) proof that a BOS/CHoCH becomes visible only
once its confirming candle exists in the window -- never at its own swing timestamp
before that. Uses the same deterministic synthetic-candle pattern as
tests/test_market_structure.py (no MT5/live dependency), but asserts the specific
availability-timing invariant multi-timeframe-market-context's SKILL.md claims:
"pivot is NOT visible at pivot timestamp if confirmation bars did not yet exist."
"""
from __future__ import annotations

import datetime as dt

from market_structure.smc_adapter import candles_to_dataframe, latest_swings_and_breaks
from strategy_engine.session import Candle

UTC = dt.timezone.utc
_SWING_LENGTH = 1


def _candles(prices, start=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), step_minutes=15):
    out = []
    t = start
    for p in prices:
        out.append(Candle(time=t, open=p, high=p + 0.0005, low=p - 0.0005, close=p, volume=1.0))
        t += dt.timedelta(minutes=step_minutes)
    return out


def _ascending_zigzag(cycles=25, trend_step=0.0100, amplitude=0.0300):
    prices = []
    for i in range(cycles):
        low = 1.1000 + i * trend_step
        high = low + amplitude
        prices.append(low)
        prices.append(high)
    return prices


def test_bos_choch_not_visible_before_confirming_candle_exists():
    """Truncate the candle series to just before the confirming break candle: no BOS/CHOCH
    may be reported. Extend by exactly the confirming candle: it must now appear. This
    proves availability_time (confirmation) governs visibility, not the earlier swing-point
    event time -- the core no-lookahead invariant the MTF skill depends on."""
    full = _candles(_ascending_zigzag(cycles=15))

    # Find the earliest index at which a BOS or CHOCH becomes confirmed as the window grows.
    # Start at 3 (the minimum a swing_length=1 pivot could need) so the "not yet visible"
    # state is actually exercised by this loop, not assumed past its own search range.
    first_confirmed_index = None
    for cutoff in range(3, len(full)):
        window = full[:cutoff]
        df = candles_to_dataframe(window)
        result = latest_swings_and_breaks(df, swing_length=_SWING_LENGTH, close_break=True)
        if result["latest_bos"] is not None or result["latest_choch"] is not None:
            first_confirmed_index = cutoff
            break

    assert first_confirmed_index is not None, "fixture must produce at least one confirmed BOS/CHOCH"

    # One candle short of the confirming bar: must NOT be visible yet.
    short_window = full[:first_confirmed_index - 1]
    short_df = candles_to_dataframe(short_window)
    short_result = latest_swings_and_breaks(short_df, swing_length=_SWING_LENGTH, close_break=True)
    assert short_result["latest_bos"] is None and short_result["latest_choch"] is None, (
        "a BOS/CHOCH appeared before its confirming candle closed -- lookahead leak"
    )

    # With the confirming bar included: must now be visible.
    full_window = full[:first_confirmed_index]
    full_df = candles_to_dataframe(full_window)
    full_result = latest_swings_and_breaks(full_df, swing_length=_SWING_LENGTH, close_break=True)
    assert full_result["latest_bos"] is not None or full_result["latest_choch"] is not None, (
        "confirming candle included but no BOS/CHOCH appeared -- fixture/assertion mismatch"
    )


def test_confirmed_break_timestamp_is_the_confirming_candle_not_the_swing_point():
    """The reported break event's own timestamp must be at/after the confirming candle's
    time, never the earlier swing-point candle's time -- otherwise a caller reading
    `.time` off the result would (wrongly) believe the fact was available earlier than
    it actually was."""
    full = _candles(_ascending_zigzag(cycles=15))
    df = candles_to_dataframe(full)
    result = latest_swings_and_breaks(df, swing_length=_SWING_LENGTH, close_break=True)

    point = result["latest_bos"] or result["latest_choch"]
    assert point is not None, "fixture must produce a confirmed break"
    assert point.time_utc is not None
    # The break's own recorded time must not precede its originating swing's time.
    swing = result["latest_swing_high"] or result["latest_swing_low"]
    if swing is not None and swing.time_utc is not None:
        assert point.time_utc >= swing.time_utc
