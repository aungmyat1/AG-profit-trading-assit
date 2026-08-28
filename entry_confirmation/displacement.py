"""Displacement primitive -- measurement always, qualification only if signed.

See contract.py for why qualification is UNSIGNED_RULE in V1.
"""
from __future__ import annotations

from typing import Optional

from strategy_engine.session import Candle

from .models import ConfirmationState, DisplacementEvidence


def measure_candle(candle: Candle) -> dict:
    """Pure arithmetic candle measurements. Zero-range candles do not divide by zero --
    body_ratio/close_location fall back the same way supply_demand/ob_contract.py's own
    body_ratio does (range 0 -> ratio 1.0), for the same reason: a zero-range candle has
    no wick to be anything but body-dominant."""
    range_size = candle.high - candle.low
    body_size = abs(candle.close - candle.open)
    body_ratio = (body_size / range_size) if range_size > 0 else 1.0
    close_location = ((candle.close - candle.low) / range_size) if range_size > 0 else 0.5

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
        "body_ratio": body_ratio,
        "close_location": close_location,
    }


def evaluate_displacement(candle: Optional[Candle]) -> DisplacementEvidence:
    if candle is None:
        return DisplacementEvidence(
            status=ConfirmationState.UNAVAILABLE,
            reason="No candidate_candle supplied in EntryConfirmationRequest.",
        )

    m = measure_candle(candle)
    return DisplacementEvidence(
        status=ConfirmationState.UNSIGNED_RULE,
        direction=m["direction"],
        candle_timestamp=candle.time,
        body_size=m["body_size"],
        range_size=m["range_size"],
        body_ratio=m["body_ratio"],
        close_location=m["close_location"],
        qualification="UNSIGNED_RULE",
        rule_version=None,
        reason="Measurement available; no owner-signed generic displacement threshold "
               "exists -- see entry_confirmation/contract.py's contract gaps.",
    )
