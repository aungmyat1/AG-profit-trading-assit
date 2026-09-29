"""Prepared-only position sizing for the TradeTicket slice. Computes a volume; never
sends, checks or queues an order, and holds no broker handle.

`size_position` below is the repository's canonical sizing function restored VERBATIM
from 1a8e7c5:src/execution/risk.py (blob ecda12d2a131c6fdc40c738e79bac79d3a0bd7b4).
It is relocated here, not re-imported, because the platform lineage deliberately keeps
`src/execution` absent (tests/test_fx_opportunity_containment.py). Money-per-lot comes
from broker tick_size/tick_value, so FX, JPY crosses and metals size identically.

Everything around it only validates caller-supplied inputs (account snapshot, symbol
metadata, the cycle pilot's risk policy) and fails closed -- no MT5 I/O, no hidden Live authority, no
default risk substituted when the owner policy is missing.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Optional, Tuple

from mt5.symbol_resolver import METADATA_SOURCE_EXCHANGE_VERIFIED, SymbolMeta
from post_asian_pilot.fingerprint import fingerprint

_FLOAT_TOL = 1e-9

# ---- verbatim restoration: 1a8e7c5:src/execution/risk.py ----------------------------
def size_position(
    entry: float,
    stop_loss: float,
    equity: float,
    risk_per_trade_pct: float,
    symbol_meta: SymbolMeta,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Returns (volume, risk_amount, reason_code). reason_code is None on success; on
    failure volume and risk_amount are both None and reason_code is one of
    VOLUME_BELOW_MIN / VOLUME_ABOVE_MAX / RISK_EXCEEDS_BUDGET / INVALID_STOP_DISTANCE.

    Money-per-lot is derived from tick_size/tick_value (broker-supplied, symbol-agnostic)
    rather than a hardcoded pip-value formula -- see this module's docstring.
    """
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return None, None, "INVALID_STOP_DISTANCE"

    risk_budget = equity * (risk_per_trade_pct / 100.0)
    value_per_price_unit = symbol_meta.tick_value / symbol_meta.tick_size
    loss_per_lot = stop_distance * value_per_price_unit

    raw_volume = risk_budget / loss_per_lot
    steps = math.floor(raw_volume / symbol_meta.volume_step + _FLOAT_TOL)
    volume = round(steps * symbol_meta.volume_step, 8)  # round off float accumulation noise

    if volume < symbol_meta.volume_min - _FLOAT_TOL:
        return None, None, "VOLUME_BELOW_MIN"
    if volume > symbol_meta.volume_max + _FLOAT_TOL:
        return None, None, "VOLUME_ABOVE_MAX"

    risk_amount = volume * loss_per_lot
    tolerance = max(risk_budget * 1e-6, 1e-6)
    if risk_amount > risk_budget + tolerance:
        return None, None, "RISK_EXCEEDS_BUDGET"

    return volume, risk_amount, None
# ---- end verbatim restoration --------------------------------------------------------


@dataclass(frozen=True)
class RiskPolicy:
    """The cycle's authoritative risk policy. Built only from the cycle's own pilot
    config (`risk_policy_from_pilot`); there is deliberately no loader for the generic
    DEMO defaults (config/trading.demo.yaml risk_per_trade_pct 1.0 historically
    diverged from the pilots' 0.5) and no fallback between them."""
    risk_per_trade_pct: float
    max_aggregate_open_risk_pct: float
    pilot_id: str
    source: str

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


def risk_policy_from_pilot(pilot: Any) -> Optional[RiskPolicy]:
    """None (fail closed) unless both percentages are positive finite numbers."""
    pct = getattr(pilot, "risk_per_trade_pct", None)
    agg = getattr(pilot, "max_aggregate_open_risk_pct", None)
    if not (_finite_positive(pct) and _finite_positive(agg)):
        return None
    return RiskPolicy(risk_per_trade_pct=float(pct), max_aggregate_open_risk_pct=float(agg),
                      pilot_id=pilot.pilot_id, source=f"pilot:{pilot.pilot_id}")


@dataclass(frozen=True)
class AccountSnapshot:
    """Caller-supplied, read-only account facts (e.g. recorded account_info()).
    `open_risk_pct` is the already-committed aggregate open risk; None means unknown
    and blocks sizing (this module never reads positions itself)."""
    equity: float
    currency: str
    server: str
    environment: str
    open_risk_pct: Optional[float]


@dataclass(frozen=True)
class SizingResult:
    volume: Optional[float]
    risk_amount: Optional[float]
    reason_code: Optional[str]
    symbol_meta_fingerprint: Optional[str]

    @property
    def ok(self) -> bool:
        return self.reason_code is None


def _finite_positive(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def _fail(reason: str, meta_fp: Optional[str] = None) -> SizingResult:
    return SizingResult(None, None, reason, meta_fp)


def prepare_sizing(
    *,
    entry: float,
    stop_loss: float,
    account: AccountSnapshot,
    risk_policy: Optional[RiskPolicy],
    symbol_meta: Optional[SymbolMeta],
    expected_symbol: str,
    expected_digits: int,
    require_verified_metadata: bool,
) -> SizingResult:
    if risk_policy is None or not _finite_positive(risk_policy.risk_per_trade_pct):
        return _fail("RISK_POLICY_UNAVAILABLE")
    if not _finite_positive(account.equity):
        return _fail("ACCOUNT_EQUITY_INVALID")
    open_risk = account.open_risk_pct
    if isinstance(open_risk, bool) or not isinstance(open_risk, (int, float)) or not math.isfinite(open_risk) or open_risk < 0:
        return _fail("AGGREGATE_RISK_UNKNOWN")
    if open_risk + risk_policy.risk_per_trade_pct > risk_policy.max_aggregate_open_risk_pct + _FLOAT_TOL:
        return _fail("AGGREGATE_RISK_EXCEEDED")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (entry, stop_loss)):
        return _fail("NONFINITE_GEOMETRY")
    if not isinstance(symbol_meta, SymbolMeta):
        return _fail("SYMBOL_METADATA_UNAVAILABLE")
    meta_fp = fingerprint(asdict(symbol_meta))
    if symbol_meta.symbol != expected_symbol:
        return _fail("SYMBOL_METADATA_MISMATCH", meta_fp)
    if symbol_meta.digits != expected_digits:
        return _fail("INSTRUMENT_DIGITS_MISMATCH", meta_fp)
    if require_verified_metadata and symbol_meta.metadata_source != METADATA_SOURCE_EXCHANGE_VERIFIED:
        return _fail("SYMBOL_METADATA_NOT_BROKER_VERIFIED", meta_fp)
    for name in ("tick_size", "tick_value", "volume_min", "volume_max", "volume_step"):
        if not _finite_positive(getattr(symbol_meta, name)):
            return _fail("SYMBOL_METADATA_INVALID", meta_fp)
    if symbol_meta.volume_max < symbol_meta.volume_min:
        return _fail("SYMBOL_METADATA_INVALID", meta_fp)
    volume, risk_amount, reason = size_position(
        entry, stop_loss, account.equity, risk_policy.risk_per_trade_pct, symbol_meta)
    return SizingResult(volume, risk_amount, reason, meta_fp)
