"""S1 (Sweep Reversal) / S2 (Breakout Continuation) / S3 (Pullback Continuation) setup
generators. Each returns a SetupCandidate (or None) -- these functions never place
orders, never mutate campaign state, and never allocate risk; campaign.py owns that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

from strategy_engine.session.candles import Candle

from .regime import Regime, ema
from .swing_structure import BOSDirection, BOSEvent, FVGDirection, FVGEvent, Swing, SwingType, detect_fvg


class SetupModel(str, Enum):
    S1 = "S1_SWEEP_REVERSAL"
    S2 = "S2_BREAKOUT_CONTINUATION"
    S3 = "S3_PULLBACK_CONTINUATION"


@dataclass(frozen=True)
class SetupCandidate:
    setup_model: SetupModel
    direction: str  # "LONG" | "SHORT"
    trigger_candle_index: int
    trigger_candle_time: object
    entry_price: float
    regime: Regime
    evidence: Dict[str, object] = field(default_factory=dict)
    rejected: bool = False
    rejection_reason: Optional[str] = None


def evaluate_s1_sweep_reversal(
    candle: Candle, candle_index: int, reference_high: float, reference_low: float, regime: Regime,
) -> Optional[SetupCandidate]:
    """Wick breach + close back inside the reference range. Only RANGE/TRANSITION
    regimes qualify. Direction is LONG on a low-side sweep (reversal up), SHORT on a
    high-side sweep (reversal down)."""
    if regime not in (Regime.RANGE, Regime.TRANSITION):
        return None

    swept_low = candle.low < reference_low and candle.close >= reference_low
    swept_high = candle.high > reference_high and candle.close <= reference_high
    if swept_low and swept_high:
        # Ambiguous dual-side sweep on the same candle -- no trade (mirrors the
        # frozen-baseline strategy's own documented AMBIGUOUS_NO_TRADE guard, applied
        # independently here rather than imported, to keep this engine isolated).
        return None
    if swept_low:
        return SetupCandidate(
            setup_model=SetupModel.S1, direction="LONG",
            trigger_candle_index=candle_index, trigger_candle_time=candle.time,
            entry_price=candle.close, regime=regime,
            evidence={"sweep_extreme_price": candle.low, "reference_low": reference_low, "reference_high": reference_high},
        )
    if swept_high:
        return SetupCandidate(
            setup_model=SetupModel.S1, direction="SHORT",
            trigger_candle_index=candle_index, trigger_candle_time=candle.time,
            entry_price=candle.close, regime=regime,
            evidence={"sweep_extreme_price": candle.high, "reference_low": reference_low, "reference_high": reference_high},
        )
    return None


def evaluate_s2_breakout_continuation(bos: BOSEvent, candle: Candle, regime: Regime) -> Optional[SetupCandidate]:
    """Regime must be TREND_UP/TREND_DOWN, BOS confirmed on CLOSE (bos_events are only
    ever produced by swing_structure.detect_bos on a close-break, never a wick -- "no
    single wick triggers it" is therefore structurally enforced by construction, not
    re-checked here)."""
    if bos.direction == BOSDirection.UP and regime == Regime.TREND_UP:
        direction = "LONG"
    elif bos.direction == BOSDirection.DOWN and regime == Regime.TREND_DOWN:
        direction = "SHORT"
    else:
        return None
    return SetupCandidate(
        setup_model=SetupModel.S2, direction=direction,
        trigger_candle_index=bos.break_candle_index, trigger_candle_time=bos.break_candle_time,
        entry_price=bos.close_price, regime=regime,
        evidence={"bos_direction": bos.direction.value, "broken_swing_price": bos.broken_swing.price,
                  "displacement_confirmed": bos.displacement_confirmed},
    )


CONTINUATION_SCORE_SIGNALS = (
    "eligible_fvg_retrace",
    "ema20_retest",
    "breakout_level_retest",
    "pullback_liquidity_sweep",
    "displacement_reconfirmation",
)


def compute_continuation_score(signals: Dict[str, bool]) -> int:
    return sum(1 for name in CONTINUATION_SCORE_SIGNALS if signals.get(name, False))


def evaluate_s3_pullback_continuation(
    prior_bos: Optional[BOSEvent],
    candle: Candle,
    candle_index: int,
    direction: str,
    regime: Regime,
    signals: Dict[str, bool],
    minimum_score: int,
) -> Optional[SetupCandidate]:
    """Requires a prior BOS in this campaign (`prior_bos` is None => no setup, fail
    closed). Confirmation score from 5 boolean signals, >= minimum_score (config, spec
    default 2). EMA-only can never qualify alone: even if a caller supplied a
    misconfigured minimum_score of 1, this function explicitly refuses to qualify a
    candidate whose ONLY true signal is ema20_retest -- that guard is enforced here,
    independent of the configured threshold, per spec ("EMA-only must never qualify
    alone")."""
    if prior_bos is None:
        return None

    score = compute_continuation_score(signals)
    true_signals = [name for name in CONTINUATION_SCORE_SIGNALS if signals.get(name, False)]
    ema_only = true_signals == ["ema20_retest"]

    if ema_only or score < minimum_score:
        return None

    return SetupCandidate(
        setup_model=SetupModel.S3, direction=direction,
        trigger_candle_index=candle_index, trigger_candle_time=candle.time,
        entry_price=candle.close, regime=regime,
        evidence={"continuation_score": score, "signals": dict(signals), "prior_bos_direction": prior_bos.direction.value},
    )


def compute_continuation_signals(
    *,
    history: Sequence[Candle],
    candle: Candle,
    candle_index: int,
    direction: str,
    prior_bos: BOSEvent,
    confirmed_swings: Sequence[Swing],
    config: dict,
    pip_size: float,
) -> Dict[str, bool]:
    """Computes the 5 boolean continuation-score signals (CONTINUATION_SCORE_SIGNALS)
    for one candle, from real evidence only -- no hardcoded overrides, no new
    parameters beyond what strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml already
    defines (fvg.min_pips/max_pips, ema.fast_period, displacement.min_body_to_range_ratio).
    GAP_2 remediation: prior to this, nothing in the package computed these signals
    from price data at all -- evaluate_s3_pullback_continuation only ever received a
    caller-supplied dict, and no caller existed. `history` must be every candle up to
    and including `candle` (index 0..candle_index), already-closed only (enforced by
    the caller's own no-lookahead slicing, unchanged here)."""
    is_long = direction == "LONG"
    bos_index = prior_bos.break_candle_index

    # 1. breakout_level_retest: this candle's range touches back to the breakout level
    # (the swing price that was broken to produce prior_bos).
    level = prior_bos.broken_swing.price
    breakout_level_retest = candle.low <= level <= candle.high

    # 2. ema20_retest: candle's range touches the trailing EMA(fast_period) of closes
    # up to (not including) this candle -- "fast_period" is literally 20 in the signed
    # config (ema.fast_period), matching the signal's own name.
    fast_period = int(config["ema"]["fast_period"])
    trailing_closes = [c.close for c in history[:candle_index]]
    ema_fast = ema(trailing_closes, fast_period)
    ema20_retest = ema_fast is not None and candle.low <= ema_fast <= candle.high

    # 3. eligible_fvg_retrace: an eligible FVG (min_pips<=size<=max_pips), matching
    # continuation direction, formed strictly after the breakout and strictly before
    # this candle, whose zone this candle's range overlaps.
    fvg_cfg = config["fvg"]
    fvgs = detect_fvg(list(history[: candle_index + 1]), pip_size, float(fvg_cfg["min_pips"]), float(fvg_cfg["max_pips"]))
    wanted_fvg_dir = FVGDirection.BULLISH if is_long else FVGDirection.BEARISH
    eligible_fvg_retrace = any(
        f.eligible and f.direction == wanted_fvg_dir and bos_index < f.index < candle_index
        and candle.low <= f.high and candle.high >= f.low
        for f in fvgs
    )

    # 4. pullback_liquidity_sweep: this candle sweeps a confirmed swing formed AFTER
    # the breakout (on the stop side of the trade direction) and closes back beyond it
    # -- the same "wick breach + close back inside" shape S1 uses, applied to the
    # smaller post-BOS pullback swing rather than the session reference range.
    wanted_swing_type = SwingType.LOW if is_long else SwingType.HIGH
    post_bos_swings = [s for s in confirmed_swings if s.index > bos_index and s.swing_type == wanted_swing_type and s.confirmed_at <= candle.time]
    pullback_liquidity_sweep = False
    if post_bos_swings:
        nearest = max(post_bos_swings, key=lambda s: s.index)
        if is_long:
            pullback_liquidity_sweep = candle.low < nearest.price and candle.close >= nearest.price
        else:
            pullback_liquidity_sweep = candle.high > nearest.price and candle.close <= nearest.price

    # 5. displacement_reconfirmation: this candle's own body/range ratio meets the
    # signed displacement threshold, in the continuation direction.
    min_ratio = float(config["displacement"]["min_body_to_range_ratio"])
    body = candle.close - candle.open
    rng = max(candle.high - candle.low, 1e-12)
    if is_long:
        displacement_reconfirmation = body > 0 and (body / rng) >= min_ratio
    else:
        displacement_reconfirmation = body < 0 and (abs(body) / rng) >= min_ratio

    return {
        "eligible_fvg_retrace": eligible_fvg_retrace,
        "ema20_retest": ema20_retest,
        "breakout_level_retest": breakout_level_retest,
        "pullback_liquidity_sweep": pullback_liquidity_sweep,
        "displacement_reconfirmation": displacement_reconfirmation,
    }
