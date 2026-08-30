"""Stop loss, targets, and target-geometry guard.

Asset-independent by design: build_target_plan() takes a precomputed stop_buffer_price
(a plain price distance), never a Forex pip or a crypto tick itself -- so the SAME
geometry/reward-guard logic serves both the Forex and Crypto profiles without forking.
The two buffer CONVENTIONS (pip vs tick) live in their own small, profile-specific
helpers below/alongside so this stays true.

pip_size()/forex_sl_buffer_price(): Forex-only. mt5.symbol_resolver.SymbolMeta exposes
broker facts (digits/point/tick_size/tick_value) but nothing in this repo converts that
into an FX "pip" -- execution/risk.py deliberately sizes positions from tick_size/
tick_value directly and never needs a pip concept (see its own docstring). Standard FX
convention: a 5- or 3-digit (fractional-pip) broker's pip is 10x its point; a 4- or
2-digit broker's pip equals its point. Crypto MUST NOT go through this path (spec: "do
not apply Forex pip math to crypto") -- see crypto_symbols.py for its own buffer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from mt5.symbol_resolver import SymbolMeta

DEFAULT_SL_BUFFER_PIPS = 2.5
MIN_TP2_R_MULTIPLE = 1.5

GEOMETRY_VALID = "VALID"
GEOMETRY_INVALID = "NO_TRADE_TARGET_GEOMETRY"

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"


def pip_size(symbol_meta: SymbolMeta) -> float:
    return symbol_meta.point * 10 if symbol_meta.digits in (3, 5) else symbol_meta.point


def forex_sl_buffer_price(symbol_meta: SymbolMeta, sl_buffer_pips: float = DEFAULT_SL_BUFFER_PIPS) -> float:
    return sl_buffer_pips * pip_size(symbol_meta)


@dataclass(frozen=True)
class TargetPlan:
    status: str  # GEOMETRY_VALID or GEOMETRY_INVALID
    direction: str
    entry: float
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    risk_distance: Optional[float] = None
    tp2_r_multiple: Optional[float] = None
    reason_code: Optional[str] = None


def build_target_plan(
    direction: str,
    entry: float,
    sweep_extreme: float,
    ref_mid: float,
    ref_high: float,
    ref_low: float,
    stop_buffer_price: float,
) -> TargetPlan:
    """direction: "SHORT" after a HIGH sweep (TP1=reference mid, TP2=reference low) or
    "LONG" after a LOW sweep (TP1=reference mid, TP2=reference high). SL = sweep extreme
    +/- stop_buffer_price (a plain, already-resolved price distance -- see this module's
    docstring for how each profile computes that distance).

    Rejects invalid geometry (spec): for SHORT, TP1/TP2 must be below entry; for LONG,
    above. Minimum TP2 reward/risk is MIN_TP2_R_MULTIPLE (1.5R). If TP1 (the reference
    midpoint) lands on the wrong side of entry, the WHOLE setup is rejected here -- V1
    deliberately does not fall back to a TP1-less single-TP2 exit for either profile, to
    keep exactly one target-plan code path shared by both (documented choice, see status
    report: "reject" was chosen for consistency with this same existing Forex behavior,
    not invented separately for crypto). No substitute target is ever invented.
    """
    if direction == DIRECTION_SHORT:
        stop_loss = sweep_extreme + stop_buffer_price
        tp1, tp2 = ref_mid, ref_low
        risk_distance = stop_loss - entry
        geometry_ok = risk_distance > 0 and tp1 < entry and tp2 < entry
        reward = (entry - tp2) if risk_distance > 0 else None
    elif direction == DIRECTION_LONG:
        stop_loss = sweep_extreme - stop_buffer_price
        tp1, tp2 = ref_mid, ref_high
        risk_distance = entry - stop_loss
        geometry_ok = risk_distance > 0 and tp1 > entry and tp2 > entry
        reward = (tp2 - entry) if risk_distance > 0 else None
    else:
        raise ValueError(f"unknown direction {direction!r}")

    if not geometry_ok:
        return TargetPlan(
            GEOMETRY_INVALID, direction, entry, stop_loss, tp1, tp2,
            risk_distance=risk_distance if risk_distance and risk_distance > 0 else None,
            reason_code=GEOMETRY_INVALID,
        )

    r_multiple = reward / risk_distance
    if r_multiple < MIN_TP2_R_MULTIPLE:
        return TargetPlan(
            GEOMETRY_INVALID, direction, entry, stop_loss, tp1, tp2,
            risk_distance=risk_distance, tp2_r_multiple=r_multiple, reason_code=GEOMETRY_INVALID,
        )

    return TargetPlan(
        GEOMETRY_VALID, direction, entry, stop_loss, tp1, tp2,
        risk_distance=risk_distance, tp2_r_multiple=r_multiple, reason_code=None,
    )
