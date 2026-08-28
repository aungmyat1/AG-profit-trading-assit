"""R-multiple tracking and broker-legal volume normalization for management actions.

current_r() always divides by the *frozen* initial_r_distance from the Claim -- never a
distance recomputed from a moved (e.g. breakeven) stop (spec section 9/12).

normalize_partial_close_volume() mirrors execution/risk.py's approach of deriving legal
volume from the broker's own tick/volume_step metadata rather than a hardcoded pip
formula, extended here for the two-piece (close now / remainder) shape a partial close
needs (spec section 10). Fails closed (reason_code, no volumes) if the remainder would
be an illegal size the broker would reject.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

from mt5.symbol_resolver import SymbolMeta

_FLOAT_TOL = 1e-9

REASON_CLOSE_VOLUME_BELOW_MIN = "CLOSE_VOLUME_BELOW_MIN"
REASON_ILLEGAL_REMAINDER_VOLUME = "ILLEGAL_REMAINDER_VOLUME"


def current_r(direction: str, entry_price: float, current_price: float, initial_r_distance: float) -> Optional[float]:
    if initial_r_distance <= 0 or not math.isfinite(initial_r_distance):
        return None
    if direction == "BUY":
        raw = current_price - entry_price
    elif direction == "SELL":
        raw = entry_price - current_price
    else:
        return None
    if not math.isfinite(raw):
        return None
    return raw / initial_r_distance


def target_price(direction: str, entry_price: float, initial_r_distance: float, r_multiple: float) -> Optional[float]:
    if direction == "BUY":
        return entry_price + (r_multiple * initial_r_distance)
    if direction == "SELL":
        return entry_price - (r_multiple * initial_r_distance)
    return None


def normalize_partial_close_volume(
    current_volume: float,
    close_fraction: float,
    symbol_meta: SymbolMeta,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Returns (close_volume, remaining_volume, reason_code). reason_code is None on
    success; on failure both volumes are None -- caller must fail closed (spec
    section 10), never silently round a different way."""
    raw_close = current_volume * close_fraction
    steps = math.floor(raw_close / symbol_meta.volume_step + _FLOAT_TOL)
    close_volume = round(steps * symbol_meta.volume_step, 8)

    if close_volume < symbol_meta.volume_min - _FLOAT_TOL:
        return None, None, REASON_CLOSE_VOLUME_BELOW_MIN

    remaining_volume = round(current_volume - close_volume, 8)
    if remaining_volume > _FLOAT_TOL and remaining_volume < symbol_meta.volume_min - _FLOAT_TOL:
        return None, None, REASON_ILLEGAL_REMAINDER_VOLUME
    if remaining_volume < 0:
        return None, None, REASON_ILLEGAL_REMAINDER_VOLUME

    return close_volume, max(remaining_volume, 0.0), None
