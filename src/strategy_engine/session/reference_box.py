"""Frozen reference-session box metrics.

Consumes only a completed session's own candles (see session_clock.py for what "completed"
means for a given session name) -- never later data. Formulas match the VALIDATED
ER_ONLY_V2 classifier contract in config/session_flow_v2.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .candles import Candle


@dataclass(frozen=True)
class ReferenceBox:
    session_name: str
    session_open: float
    session_high: float
    session_low: float
    session_close: float
    session_range: float
    session_mid: float
    path_length: float
    displacement: float
    efficiency_ratio: float
    bar_count: int
    expected_bar_count: int
    session_complete: bool


def build_reference_box(session_name: str, candles: Sequence[Candle], expected_bar_count: int) -> ReferenceBox:
    """candles must already be filtered to exactly the session's own half-open window,
    in chronological order, and must contain only *closed* bars."""
    if not candles:
        raise ValueError("build_reference_box requires at least one candle")

    session_open = candles[0].open
    session_close = candles[-1].close
    session_high = max(c.high for c in candles)
    session_low = min(c.low for c in candles)
    session_range = session_high - session_low
    session_mid = (session_high + session_low) / 2.0

    # Path length: sum of |close[i] - close[i-1]|, seeded by |open[0] - close[0]|, matching the
    # ABS_FINAL_CLOSE_MINUS_FIRST_OPEN_DIVIDED_BY_CLOSE_PATH_FROM_FIRST_OPEN formula in
    # config/session_flow_v2.yaml's efficiency_ratio_formula.
    path_length = abs(candles[0].close - session_open)
    for prev, cur in zip(candles, candles[1:]):
        path_length += abs(cur.close - prev.close)

    displacement = abs(session_close - session_open)
    efficiency_ratio = 0.0 if path_length == 0 else displacement / path_length

    bar_count = len(candles)
    complete = bar_count >= expected_bar_count

    return ReferenceBox(
        session_name=session_name,
        session_open=session_open,
        session_high=session_high,
        session_low=session_low,
        session_close=session_close,
        session_range=session_range,
        session_mid=session_mid,
        path_length=path_length,
        displacement=displacement,
        efficiency_ratio=efficiency_ratio,
        bar_count=bar_count,
        expected_bar_count=expected_bar_count,
        session_complete=complete,
    )
