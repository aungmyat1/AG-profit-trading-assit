"""Displacement primitive -- measurement always; qualification per AG_ENTRY_DISPLACEMENT_V1
once a candidate direction and a >=20-candle prior history are supplied.

AG_ENTRY_DISPLACEMENT_V1 (owner-signed, see docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md):

    body_ratio >= 0.60
    AND body_size >= 1.30 * median_body_20
    AND candle direction matches candidate_direction

    median_body_20 = median(abs(close - open)) over the 20 completed candles
    immediately preceding the evaluated candle. The evaluated candle itself never
    contaminates its own reference sample -- see contract.py.

Deliberately NOT config/ag_order_block_v1.yaml's pivot_shadow_body_ratio_threshold --
that constant answers a different question (Order Block PIVOT/SHADOW classification).
This threshold is its own, capability-scoped constant.
"""
from __future__ import annotations

import statistics
from typing import Optional, Sequence

from strategy_engine.session import Candle

from .models import CandidateDirection, ConfirmationState, DisplacementEvidence

DISPLACEMENT_RULE_VERSION = "AG_ENTRY_DISPLACEMENT_V1"
BODY_RATIO_MIN = 0.60
RELATIVE_BODY_MIN = 1.30
MEDIAN_LOOKBACK = 20

_DIRECTION_FOR_CANDIDATE = {
    CandidateDirection.LONG: "BULLISH",
    CandidateDirection.SHORT: "BEARISH",
}


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


def evaluate_displacement(
    candle: Optional[Candle],
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
    history: Sequence[Candle] = (),
) -> DisplacementEvidence:
    if candle is None:
        return DisplacementEvidence(
            status=ConfirmationState.UNAVAILABLE,
            reason="No candidate_candle supplied in EntryConfirmationRequest.",
        )

    m = measure_candle(candle)
    base_fields = dict(
        direction=m["direction"], candle_timestamp=candle.time,
        body_size=m["body_size"], range_size=m["range_size"],
        body_ratio=m["body_ratio"], close_location=m["close_location"],
    )

    if candidate_direction == CandidateDirection.NONE:
        return DisplacementEvidence(
            status=ConfirmationState.INSUFFICIENT_DATA, **base_fields,
            qualification="INSUFFICIENT_DATA", rule_version=DISPLACEMENT_RULE_VERSION,
            reason="candidate_direction is required to qualify displacement direction.",
        )

    if m["range_size"] <= 0:
        return DisplacementEvidence(
            status=ConfirmationState.INSUFFICIENT_DATA, **base_fields,
            qualification="INSUFFICIENT_DATA", rule_version=DISPLACEMENT_RULE_VERSION,
            reason="Zero-range candle -- not valid displacement evidence.",
        )

    # history must be strictly prior to `candle` -- defends against a caller accidentally
    # including the candidate candle (or anything later) in its own reference sample.
    prior = [c for c in history if c.time < candle.time]
    if len(prior) < MEDIAN_LOOKBACK:
        return DisplacementEvidence(
            status=ConfirmationState.INSUFFICIENT_DATA, **base_fields,
            qualification="INSUFFICIENT_DATA", rule_version=DISPLACEMENT_RULE_VERSION,
            reason=f"Need >= {MEDIAN_LOOKBACK} prior candles for median_body_20, got {len(prior)}.",
        )
    reference = prior[-MEDIAN_LOOKBACK:]

    if any((c.high - c.low) < 0 for c in reference):
        return DisplacementEvidence(
            status=ConfirmationState.INSUFFICIENT_DATA, **base_fields,
            qualification="INSUFFICIENT_DATA", rule_version=DISPLACEMENT_RULE_VERSION,
            reason="Invalid candle in median_body_20 reference window (high < low).",
        )

    median_body = statistics.median(abs(c.close - c.open) for c in reference)
    if median_body <= 0:
        return DisplacementEvidence(
            status=ConfirmationState.INSUFFICIENT_DATA, **base_fields,
            median_body=median_body,
            qualification="INSUFFICIENT_DATA", rule_version=DISPLACEMENT_RULE_VERSION,
            reason="median_body_20 is zero -- relative-body condition cannot be evaluated.",
        )

    relative_body = m["body_size"] / median_body
    ratio_pass = m["body_ratio"] >= BODY_RATIO_MIN
    relative_pass = m["body_size"] >= RELATIVE_BODY_MIN * median_body
    direction_pass = m["direction"] == _DIRECTION_FOR_CANDIDATE[candidate_direction]
    qualified = ratio_pass and relative_pass and direction_pass

    if qualified:
        reason = None
    else:
        failed = [
            name for name, ok in (
                ("body_ratio", ratio_pass), ("relative_body", relative_pass), ("direction", direction_pass),
            ) if not ok
        ]
        reason = f"AG_ENTRY_DISPLACEMENT_V1 conditions not met: {', '.join(failed)}."

    return DisplacementEvidence(
        status=ConfirmationState.PASS if qualified else ConfirmationState.FAIL,
        **base_fields,
        median_body=median_body, relative_body=relative_body,
        qualification=DISPLACEMENT_RULE_VERSION, rule_version=DISPLACEMENT_RULE_VERSION,
        reason=reason,
    )
