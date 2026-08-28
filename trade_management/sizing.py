"""Pre-trade position sizing -- deterministic, broker-realistic, tick_size/tick_value
based (never a hardcoded pip-value formula), so the same function sizes FX, metals,
indices, or anything else MT5 exposes that metadata for.

This is the SAME formula as execution/risk.py::size_position() (risk_budget ÷
loss_per_lot, floor-only rounding to volume_step -- never rounds up past the risk
budget, per the mission's explicit "no unsafe round-up" requirement) and
execution/validator.py::validate_account_and_config()'s reason-code vocabulary.
Reimplemented here rather than imported so trade_management/ (a core capability that
runs BEFORE any execution decision) does not depend on execution/ (which sits AFTER
Trade Management in the architecture and is project-wide paused) -- the same
independence trade_management/risk.py's own docstring already establishes for
normalize_partial_close_volume() vs. execution/risk.py. One algorithm, two owners by
architectural layer, not two independently-invented ones -- see
TRADE_MANAGEMENT_V1_SPEC.md's audit table.

Adds one thing execution/risk.py does not have: an optional caller-supplied
`max_risk_percent` ceiling (from ManagementPolicy) that is REJECTED against, never
silently clamped -- see the mission's "risk authority" requirement.
"""
from __future__ import annotations

import math
from typing import Optional

from .models import (
    PositionSizing,
    SIZING_ACCOUNT_DATA_MISSING,
    SIZING_INVALID_RISK_CONFIG,
    SIZING_READY,
    SIZING_RISK_LIMIT_EXCEEDED,
    SIZING_SIZE_UNAVAILABLE,
    SIZING_SYMBOL_METADATA_MISSING,
    SIZING_VOLUME_ABOVE_MAX,
    SIZING_VOLUME_BELOW_MIN,
    SymbolMeta,
)

_FLOAT_TOL = 1e-9


def evaluate_sizing(
    entry: float,
    stop_loss: float,
    equity: Optional[float],
    risk_percent: Optional[float],
    risk_amount: Optional[float],
    symbol_meta: Optional[SymbolMeta],
    max_risk_percent: Optional[float] = None,
) -> PositionSizing:
    if equity is None or not math.isfinite(equity) or equity <= 0:
        return PositionSizing(status=SIZING_ACCOUNT_DATA_MISSING,
                               reason="equity is missing, non-finite, or <= 0.")

    if risk_amount is None and risk_percent is None:
        return PositionSizing(status=SIZING_INVALID_RISK_CONFIG,
                               reason="either risk_percent or risk_amount must be supplied.")
    if risk_percent is not None and not (math.isfinite(risk_percent) and 0 < risk_percent <= 100):
        return PositionSizing(status=SIZING_INVALID_RISK_CONFIG,
                               reason="risk_percent must be a finite value in (0, 100].")
    if risk_amount is not None and not (math.isfinite(risk_amount) and risk_amount > 0):
        return PositionSizing(status=SIZING_INVALID_RISK_CONFIG,
                               reason="risk_amount must be a finite value > 0.")

    if max_risk_percent is not None and risk_percent is not None and risk_percent > max_risk_percent:
        return PositionSizing(status=SIZING_RISK_LIMIT_EXCEEDED,
                               requested_risk_percent=risk_percent,
                               reason=f"requested risk_percent {risk_percent} exceeds "
                                      f"management_policy.max_risk_percent {max_risk_percent}.")

    if (
        symbol_meta is None
        or symbol_meta.tick_size <= 0
        or symbol_meta.tick_value <= 0
        or symbol_meta.volume_step <= 0
        or symbol_meta.volume_min <= 0
        or symbol_meta.volume_max < symbol_meta.volume_min
    ):
        return PositionSizing(status=SIZING_SYMBOL_METADATA_MISSING,
                               reason="symbol_meta is missing or has invalid tick/volume fields.")

    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return PositionSizing(status=SIZING_SIZE_UNAVAILABLE,
                               reason="zero stop distance -- geometry should be validated first.")

    # risk_amount takes priority when both are supplied -- an explicit amount is a
    # stronger caller statement than a percentage derived from equity.
    requested_risk_amount = risk_amount if risk_amount is not None else equity * (risk_percent / 100.0)
    requested_risk_percent = risk_percent if risk_percent is not None else (requested_risk_amount / equity) * 100.0

    value_per_price_unit = symbol_meta.tick_value / symbol_meta.tick_size
    loss_per_lot = stop_distance * value_per_price_unit

    raw_volume = requested_risk_amount / loss_per_lot
    steps = math.floor(raw_volume / symbol_meta.volume_step + _FLOAT_TOL)
    normalized_volume = round(steps * symbol_meta.volume_step, 8)  # floor only -- never rounds up

    if normalized_volume < symbol_meta.volume_min - _FLOAT_TOL:
        return PositionSizing(status=SIZING_VOLUME_BELOW_MIN,
                               requested_risk_percent=requested_risk_percent,
                               requested_risk_amount=requested_risk_amount,
                               risk_budget=requested_risk_amount, loss_per_lot=loss_per_lot,
                               raw_volume=raw_volume,
                               reason=f"raw_volume {raw_volume:.6f} rounds below broker "
                                      f"volume_min {symbol_meta.volume_min} -- forcing the minimum "
                                      f"would exceed the requested risk budget, so this size is "
                                      f"unavailable rather than silently over-risking.")

    if normalized_volume > symbol_meta.volume_max + _FLOAT_TOL:
        # Mirrors execution/risk.py::size_position(): reject, never cap at volume_max --
        # no signed policy anywhere authorizes silently capping to a smaller, cheaper size.
        return PositionSizing(status=SIZING_VOLUME_ABOVE_MAX,
                               requested_risk_percent=requested_risk_percent,
                               requested_risk_amount=requested_risk_amount,
                               risk_budget=requested_risk_amount, loss_per_lot=loss_per_lot,
                               raw_volume=raw_volume,
                               reason=f"raw_volume {raw_volume:.6f} exceeds broker volume_max "
                                      f"{symbol_meta.volume_max}; no signed policy authorizes capping.")

    actual_risk_amount = normalized_volume * loss_per_lot
    actual_risk_percent = (actual_risk_amount / equity) * 100.0

    return PositionSizing(
        status=SIZING_READY,
        requested_risk_percent=requested_risk_percent,
        requested_risk_amount=requested_risk_amount,
        risk_budget=requested_risk_amount,
        loss_per_lot=loss_per_lot,
        raw_volume=raw_volume,
        normalized_volume=normalized_volume,
        actual_risk_amount=actual_risk_amount,
        actual_risk_percent=actual_risk_percent,
    )
