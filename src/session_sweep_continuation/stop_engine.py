"""Structural Stop Engine for ST_SESSION_SWEEP_CONTINUATION_V1 ONLY.

Explicitly does NOT touch, read, or reuse ST_ASIAN_SWEEP_5R_V1's
0.25 x session-range stop model (strategies/ST_ASIAN_SWEEP_5R_V1.yaml
risk_and_money_management.stop_loss_range_pct) -- that model is retired for this new
strategy only; the old strategy's own config/behavior is completely unchanged (verified
byte-identical in the final report).

Formula:
  structural_stop_distance = abs(entry - structural_anchor) + stop_buffer_multiplier * ATR_M15
  friction_floor            = friction.minimum_stop_multiple * expected_transaction_friction (price units)

Deliberate resolution of the spec's two stop-model clauses, both of which must hold
simultaneously ("final = max(structural_stop_distance, friction_floor)" AND "never widen
stops arbitrarily to force a trade" / "reject with STOP_BELOW_FRICTION_FLOOR"): widening
structural_stop_distance UP to friction_floor would itself be "arbitrarily widening a
stop to force a trade" -- so this engine never does that substitution. Instead:
  - if structural_stop_distance >= friction_floor: final = structural_stop_distance
    (which is trivially also max(...) -- the two clauses agree in this branch)
  - if structural_stop_distance <  friction_floor: REJECT_SETUP, reason
    STOP_BELOW_FRICTION_FLOOR (never substitute friction_floor as a synthetic final
    distance)
This is the single deterministic rule implemented below; it satisfies "final =
max(...)" exactly in the only branch where a final distance is actually produced, and
never fabricates a stop distance the market structure did not produce.

If no structural anchor is available for the setup type in play: REJECT_SETUP (fail
closed) -- see resolve_anchor().

Anchor rules (spec: "pick one deterministic rule and document it"):
  S1 (Sweep Reversal):       anchor = the sweep wick's own extreme (sweep low for LONG,
                              sweep high for SHORT) -- the literal price that was swept.
  S2 (Breakout Continuation): anchor = the most recently CONFIRMED swing point on the
                              side the BOS came FROM (i.e. for a BOS_UP, the most recent
                              confirmed swing LOW that formed before the breakout
                              candle; for BOS_DOWN, the most recent confirmed swing
                              HIGH) -- this is "the structural breakout invalidation
                              level": if price returns beyond that swing, the breakout
                              thesis is invalidated. Chosen over "most recent confirmed
                              pullback swing" because at the moment of BOS there has not
                              yet been a pullback -- the pre-breakout swing is the only
                              anchor guaranteed to exist.
  S3 (Pullback Continuation): anchor = the most recent CONFIRMED swing formed AFTER the
                              triggering BOS and BEFORE the pullback entry, on the stop
                              side of the trade direction (swing low for LONG, swing
                              high for SHORT) -- "the pullback swing that defended
                              continuation structure". If no such post-BOS swing is yet
                              confirmed, falls back to the FVG's own invalidation
                              boundary (the far edge of the eligible FVG opposite the
                              entry direction) when an eligible FVG is present; if
                              neither exists, REJECT_SETUP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .friction import FrictionEstimate
from .swing_structure import BOSEvent, FVGEvent, Swing, SwingType


@dataclass(frozen=True)
class AnchorResult:
    anchor_price: Optional[float]
    anchor_source: str  # e.g. "S1_SWEEP_EXTREME", "S2_PRE_BREAKOUT_SWING", "S3_POST_BOS_SWING", "S3_FVG_BOUNDARY", "NONE"


def resolve_anchor_s1(direction: str, sweep_extreme_price: float) -> AnchorResult:
    return AnchorResult(sweep_extreme_price, "S1_SWEEP_EXTREME")


def resolve_anchor_s2(direction: str, bos: BOSEvent) -> AnchorResult:
    # bos.broken_swing is the pre-breakout swing that was broken to produce this BOS --
    # exactly the "most recently confirmed swing point on the side the BOS came from".
    return AnchorResult(bos.broken_swing.price, "S2_PRE_BREAKOUT_SWING")


def resolve_anchor_s3(
    direction: str,
    post_bos_swings: Sequence[Swing],
    eligible_fvg: Optional[FVGEvent],
) -> AnchorResult:
    wanted_type = SwingType.LOW if direction == "LONG" else SwingType.HIGH
    candidates = [s for s in post_bos_swings if s.swing_type == wanted_type]
    if candidates:
        latest = max(candidates, key=lambda s: s.index)
        return AnchorResult(latest.price, "S3_POST_BOS_SWING")
    if eligible_fvg is not None:
        # invalidation boundary = far edge of the gap opposite the entry direction
        boundary = eligible_fvg.low if direction == "LONG" else eligible_fvg.high
        return AnchorResult(boundary, "S3_FVG_BOUNDARY")
    return AnchorResult(None, "NONE")


@dataclass(frozen=True)
class StopResult:
    accepted: bool
    reason: str
    entry_price: Optional[float]
    anchor_price: Optional[float]
    anchor_source: str
    structural_stop_distance: Optional[float]
    atr_buffer: Optional[float]
    friction_floor: Optional[float]
    final_stop_distance: Optional[float]
    stop_price: Optional[float]


def compute_stop(
    direction: str,
    entry_price: float,
    anchor: AnchorResult,
    atr_m15: Optional[float],
    stop_buffer_multiplier: float,
    friction: FrictionEstimate,
    minimum_stop_multiple: float,
) -> StopResult:
    if anchor.anchor_price is None:
        return StopResult(
            accepted=False, reason="NO_STRUCTURAL_ANCHOR_AVAILABLE",
            entry_price=entry_price, anchor_price=None, anchor_source=anchor.anchor_source,
            structural_stop_distance=None, atr_buffer=None, friction_floor=None,
            final_stop_distance=None, stop_price=None,
        )
    if atr_m15 is None:
        return StopResult(
            accepted=False, reason="ATR_UNAVAILABLE",
            entry_price=entry_price, anchor_price=anchor.anchor_price, anchor_source=anchor.anchor_source,
            structural_stop_distance=None, atr_buffer=None, friction_floor=None,
            final_stop_distance=None, stop_price=None,
        )
    if friction.cost_status == "UNAVAILABLE" or friction.total_price is None:
        # Fail closed: never assume friction is zero / never let economic eligibility
        # falsely pass when cost is unknown.
        return StopResult(
            accepted=False, reason="FRICTION_UNAVAILABLE",
            entry_price=entry_price, anchor_price=anchor.anchor_price, anchor_source=anchor.anchor_source,
            structural_stop_distance=None, atr_buffer=None, friction_floor=None,
            final_stop_distance=None, stop_price=None,
        )

    atr_buffer = stop_buffer_multiplier * atr_m15
    structural_stop_distance = abs(entry_price - anchor.anchor_price) + atr_buffer
    friction_floor = minimum_stop_multiple * friction.total_price

    if structural_stop_distance < friction_floor:
        return StopResult(
            accepted=False, reason="STOP_BELOW_FRICTION_FLOOR",
            entry_price=entry_price, anchor_price=anchor.anchor_price, anchor_source=anchor.anchor_source,
            structural_stop_distance=structural_stop_distance, atr_buffer=atr_buffer,
            friction_floor=friction_floor, final_stop_distance=None, stop_price=None,
        )

    final_stop_distance = structural_stop_distance  # == max(structural, floor) in this branch
    stop_price = entry_price - final_stop_distance if direction == "LONG" else entry_price + final_stop_distance

    return StopResult(
        accepted=True, reason="OK",
        entry_price=entry_price, anchor_price=anchor.anchor_price, anchor_source=anchor.anchor_source,
        structural_stop_distance=structural_stop_distance, atr_buffer=atr_buffer,
        friction_floor=friction_floor, final_stop_distance=final_stop_distance, stop_price=stop_price,
    )
