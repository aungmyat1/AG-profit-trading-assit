"""Rejection/reversal candle primitive -- measurement always, qualification only if signed.

See contract.py for why qualification is UNSIGNED_RULE in V1.
"""
from __future__ import annotations

from typing import Optional

from strategy_engine.session import Candle

from .models import ConfirmationState, RejectionEvidence


def measure_candle(candle: Candle) -> dict:
    range_size = candle.high - candle.low
    body_size = abs(candle.close - candle.open)
    body_top = max(candle.open, candle.close)
    body_bottom = min(candle.open, candle.close)
    upper_wick = candle.high - body_top
    lower_wick = body_bottom - candle.low

    if range_size > 0:
        body_ratio = body_size / range_size
        upper_wick_ratio = upper_wick / range_size
        lower_wick_ratio = lower_wick / range_size
        close_location = (candle.close - candle.low) / range_size
    else:
        body_ratio = 1.0
        upper_wick_ratio = 0.0
        lower_wick_ratio = 0.0
        close_location = 0.5

    if candle.close > candle.open:
        direction = "BULLISH"
    elif candle.close < candle.open:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {
        "direction": direction,
        "body_size": body_size,
        "range_size": range_size,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "close_location": close_location,
    }


def evaluate_rejection(candle: Optional[Candle]) -> RejectionEvidence:
    if candle is None:
        return RejectionEvidence(
            status=ConfirmationState.UNAVAILABLE,
            reason="No candidate_candle supplied in EntryConfirmationRequest.",
        )

    m = measure_candle(candle)
    return RejectionEvidence(
        status=ConfirmationState.UNSIGNED_RULE,
        direction=m["direction"],
        candle_timestamp=candle.time,
        body_size=m["body_size"],
        range_size=m["range_size"],
        upper_wick=m["upper_wick"],
        lower_wick=m["lower_wick"],
        body_ratio=m["body_ratio"],
        upper_wick_ratio=m["upper_wick_ratio"],
        lower_wick_ratio=m["lower_wick_ratio"],
        close_location=m["close_location"],
        qualification="UNSIGNED_RULE",
        rule_version=None,
        reason="Measurement available; no owner-signed generic rejection/reversal "
               "candle threshold exists -- see entry_confirmation/contract.py's contract gaps.",
    )
