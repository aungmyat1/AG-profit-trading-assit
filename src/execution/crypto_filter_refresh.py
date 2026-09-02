"""Filter-refresh interface (spec item 5): "explicit order authorization -> refresh
exchange filters -> normalize -> revalidate -> submit" as a documented, testable sequence
of individually callable/mockable steps. The SEQUENCE is enforced structurally:
normalize_quantity() requires the exact FilterRefreshResult.cycle_id produced by THIS
cycle's refresh_filters() call, so normalization cannot run against a stale or
never-refreshed filter set -- passing a mismatched/guessed cycle_id raises
StaleFilterCycleError instead of silently normalizing against whatever filters happen to
be lying around.

No network call anywhere in this module: refresh_filters() only ever calls
ExchangeMetadataSource.get_symbol_meta() (see execution/crypto_metadata.py), which in this
phase is always either OfflineFixtureMetadataSource (no I/O) or LiveExchangeMetadataSource
(raises NotImplementedError, never reaches a network library). submit_step() never calls a
real or mocked-as-real broker endpoint -- it returns the same NOT_IMPLEMENTED shape
execution.adapter.CryptoExecutionAdapter.submit() already returns.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from execution.adapter import AdapterSubmitResult
from execution.crypto_metadata import ExchangeMetadataSource
from execution_runtime.binance_usdtm_feed import BinanceSymbolMeta

_QUANTITY_STEP_TOLERANCE = 1e-9


class StaleFilterCycleError(RuntimeError):
    """Raised when normalize_quantity() is given a cycle_id that does not match the
    FilterRefreshResult it was called with -- i.e. an attempt to normalize against a
    filter set from a different (older, or never-issued) refresh cycle."""


class QuantityBelowMinQty(ValueError):
    """Raised when a normalized quantity floors to below the exchange's min_qty filter."""


@dataclass(frozen=True)
class FilterRefreshResult:
    """One refresh cycle's output. cycle_id is a fresh, unpredictable token per call --
    the SEQUENCE-enforcement mechanism: a caller cannot fabricate a valid cycle_id ahead
    of time, so normalize_quantity() effectively requires "a refresh happened, and this
    normalization is against THAT refresh, not an earlier one"."""

    symbol: str
    symbol_meta: BinanceSymbolMeta
    refreshed_at: datetime
    cycle_id: str


def refresh_filters(
    source: ExchangeMetadataSource, symbol: str, *, now: Optional[datetime] = None,
) -> FilterRefreshResult:
    """Step 2 of the sequence (step 1, "explicit order authorization", is the caller's own
    concern -- see execution.crypto_models.build_crypto_trade_command's `authorized`
    flag). Pulls current filters from `source` -- an OfflineFixtureMetadataSource in every
    test in this phase, never a real network call."""
    meta = source.get_symbol_meta(symbol)
    return FilterRefreshResult(
        symbol=symbol, symbol_meta=meta,
        refreshed_at=now or datetime.now(timezone.utc), cycle_id=str(uuid.uuid4()),
    )


def normalize_quantity(quantity: float, refresh: FilterRefreshResult, *, cycle_id: str) -> float:
    """Step 3: floor `quantity` to the refreshed step_size, then reject (fail closed) if
    the normalized result is below min_qty. Requires the caller to pass back the SAME
    cycle_id refresh_filters() just produced -- see StaleFilterCycleError docstring."""
    if cycle_id != refresh.cycle_id:
        raise StaleFilterCycleError(
            f"normalize_quantity called with cycle_id={cycle_id!r}, but the supplied "
            f"FilterRefreshResult is from cycle_id={refresh.cycle_id!r} -- refresh_filters() "
            "must be called again for this cycle before normalizing."
        )
    meta = refresh.symbol_meta
    if quantity is None or quantity <= 0:
        raise ValueError(f"quantity must be > 0, got {quantity!r}")
    steps = math.floor(quantity / meta.step_size + _QUANTITY_STEP_TOLERANCE)
    normalized = round(steps * meta.step_size, 10)
    if normalized < meta.min_qty - _QUANTITY_STEP_TOLERANCE:
        raise QuantityBelowMinQty(
            f"normalized quantity {normalized} (from requested {quantity}) is below "
            f"min_qty {meta.min_qty} for {refresh.symbol!r}"
        )
    return normalized


def revalidate(normalized_quantity: float, refresh: FilterRefreshResult, *, cycle_id: str) -> bool:
    """Step 4: re-check the normalized quantity against the SAME refresh cycle's filters
    immediately before submit -- defense in depth, matching execution/executor.py's own
    "final revalidation immediately before order_check/order_send" pattern
    (_RISK_REVALIDATION_TOLERANCE_PCT there). Also enforces the cycle_id check, so
    revalidate() cannot silently be called against a stale refresh either."""
    if cycle_id != refresh.cycle_id:
        raise StaleFilterCycleError(
            f"revalidate called with cycle_id={cycle_id!r}, but the supplied "
            f"FilterRefreshResult is from cycle_id={refresh.cycle_id!r}."
        )
    meta = refresh.symbol_meta
    return normalized_quantity >= meta.min_qty - _QUANTITY_STEP_TOLERANCE


def submit_step(revalidated: bool) -> AdapterSubmitResult:
    """Step 5, terminal in this phase. Reuses execution.adapter.AdapterSubmitResult's
    shape (not a new parallel result type). No network call reachable -- always returns
    NOT_IMPLEMENTED when the sequence's own checks passed, matching
    execution.adapter.CryptoExecutionAdapter.submit()'s posture exactly; returns a
    REJECTED result if the caller reached this step without a passing revalidation."""
    if not revalidated:
        return AdapterSubmitResult(status="REJECTED", reason_code="REVALIDATION_FAILED")
    return AdapterSubmitResult(status="NOT_IMPLEMENTED", reason_code="CRYPTO_EXECUTION_NOT_IMPLEMENTED")
