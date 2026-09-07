"""C10 -- ST_LARGE_SMC_V1 broker stop-loss distance, V1 signed policy.

Owner-signed V1 policy (2026-09-07,
AG_LARGE_SMC_V1_C10_STRUCTURAL_INVALIDATION_IMPLEMENTATION_AND_PROMOTION_V3;
supersedes an earlier same-day static-1.5-pip-only proposal, which never shipped in any
commit and is not active evidence), narrowing
docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md's three previously-open
parameters into one deterministic rule:

  C10-A structural buffer   = DYNAMIC_ATR_WITH_HARD_FLOOR:
                              buffer = max(1.5 pips, 0.35 x ATR14(M5))
                              ATR uses only closed M5 candles available at the decision
                              timestamp (see compute_atr14_m5's own no-lookahead
                              contract) and is REQUIRED -- missing/insufficient ATR
                              history fails closed (ATR_NOT_READY), it never silently
                              degrades to the 1.5-pip floor alone.
  C10-B spread treatment    = side-aware, reusing entry_confirmation/spread.py's own
                              already-signed LONG/SHORT buffer-direction convention:
                              LONG = anchor - buffer (spread not added -- see module
                              docstring on price-side reconciliation); SHORT = anchor +
                              buffer + verified live spread (protects the Bid-derived
                              structural anchor from Ask-side stop-trigger effects, per
                              owner intent). Missing spread for a SHORT fails closed.
  C10-C broker minimum stop = REJECT (fail closed; WIDEN is never implemented).

Structural anchor, direction, and missing-anchor behavior are the pre-existing, already-
signed C10 rules (unchanged, not reopened): anchor =
SMCEntryCombinationResult.invalidation_price (EXACT_REUSE, never recomputed here),
LONG stop below / SHORT stop above that anchor, missing anchor fails closed.

No ATR implementation existed anywhere else in this repository at the time this module
was written (confirmed by a repository-wide search) -- compute_atr14_m5 is therefore new,
minimal, Wilder-smoothed ATR, not a duplicate of any existing utility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# EURUSD-only frozen research universe (C01, strategies/ST_LARGE_SMC_V1.yaml). At
# 5-digit broker quoting, 1 pip = 10 points = 0.0001 -- a standard FX quoting fact for
# this specific, already-frozen instrument, not a broker-execution assumption (compare
# Track B1's prohibition on FX-shaped fallbacks in generic *execution* code, which this
# module is not: it is EURUSD-only research geometry by C01's own existing contract).
MIN_BUFFER_PIPS = 1.5
PIP_SIZE_EURUSD = 0.0001

ATR_TIMEFRAME = "M5"
ATR_PERIOD = 14
ATR_MULTIPLIER = 0.35


class C10StopPolicyViolation(Exception):
    """Fail-closed C10 computation failure. Raised only when a required input is
    genuinely missing/invalid, or when the signed REJECT minimum-stop policy forbids
    proceeding -- never for a value that is merely unfavorable to the trade."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class C10StopResult:
    stop_price: float
    structural_anchor: float
    buffer_price: float
    atr_value: float
    atr_component: float
    floor_component: float
    spread_price: float
    direction: str


def _true_ranges(candles: Sequence) -> list:
    trs = []
    for i in range(1, len(candles)):
        high, low, prev_close = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return trs


def compute_atr14_m5(candles: Sequence, period: int = ATR_PERIOD) -> Optional[float]:
    """Wilder-smoothed ATR over `candles`. No-lookahead contract: `candles` must
    already be closed, chronologically ordered (oldest first), and contain no bar dated
    after the decision timestamp -- this function trusts the caller's fetch (mirroring
    every other stage2-fed computation in this engine, e.g. target_model's structure-
    tier lookup), it does not itself filter by time. Returns None (ATR_NOT_READY) if
    fewer than `period` + 1 candles are supplied -- callers must fail closed on None,
    never substitute a partial-window estimate."""
    if len(candles) < period + 1:
        return None
    trs = _true_ranges(candles)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def compute_c10_stop(
    direction: str,
    invalidation_price: Optional[float],
    bid: Optional[float],
    ask: Optional[float],
    m5_candles: Optional[Sequence] = None,
    min_stop_distance_price: Optional[float] = None,
    entry_price: Optional[float] = None,
    pip_size: float = PIP_SIZE_EURUSD,
) -> C10StopResult:
    """Pure and deterministic given identical inputs. Raises C10StopPolicyViolation
    (fail-closed) rather than ever returning a partial or fabricated result.

    direction: "LONG" or "SHORT" (SMCEntryCombinationResult.direction's own values).
    invalidation_price: the already-signed structural anchor. None fails closed
        (MISSING_STRUCTURAL_ANCHOR) -- never substituted with entry/current price.
    bid/ask: the current market tick. Required for SHORT (C10-B); LONG's own formula
        does not use spread. Both missing when required fails closed (MISSING_SPREAD).
    m5_candles: closed M5 candles (oldest first) for ATR14 -- REQUIRED. None/insufficient
        history fails closed (ATR_NOT_READY); never silently falls back to the 1.5-pip
        floor alone (C10-A's own explicit requirement).
    min_stop_distance_price: the broker's minimum SL distance, already converted to
        price terms by the caller (SymbolMeta.trade_stops_level * SymbolMeta.point).
        None means no broker/account context is available -- the check is then
        NOT_APPLICABLE (never silently PASS or WIDEN). If supplied and violated: raises
        MIN_STOP_VIOLATION (REJECT); WIDEN is never implemented.
    entry_price: required only to evaluate min_stop_distance_price (distance from the
        entry, not the anchor).
    """
    if direction not in ("LONG", "SHORT"):
        raise C10StopPolicyViolation("INVALID_DIRECTION", f"C10 requires LONG or SHORT, got {direction!r}")

    if invalidation_price is None:
        raise C10StopPolicyViolation(
            "MISSING_STRUCTURAL_ANCHOR",
            "C10 requires a structural invalidation_price anchor; none supplied.",
        )

    if m5_candles is None:
        raise C10StopPolicyViolation("MISSING_ATR_DATA", "C10-A requires closed M5 candles for ATR14; none supplied.")
    atr = compute_atr14_m5(m5_candles)
    if atr is None:
        raise C10StopPolicyViolation(
            "ATR_NOT_READY",
            f"Fewer than {ATR_PERIOD + 1} closed M5 candles available -- ATR14 cannot be computed; "
            "the 1.5-pip floor is never used alone as a silent fallback.",
        )
    if atr < 0:
        raise C10StopPolicyViolation("INVALID_ATR", f"Computed ATR is negative ({atr}); refusing to use it.")

    floor_component = MIN_BUFFER_PIPS * pip_size
    atr_component = ATR_MULTIPLIER * atr
    buffer_price = max(floor_component, atr_component)

    if direction == "LONG":
        # LONG: anchor minus buffer only. Spread is not added on the LONG side --
        # invalidation_price is treated as already Bid-side-consistent with a LONG's
        # own SELL-stop trigger convention (see module docstring / C10-B); adding
        # spread here would double-count what the SHORT side accounts for once.
        spread = 0.0
        stop_price = invalidation_price - buffer_price
    else:
        if bid is None or ask is None:
            raise C10StopPolicyViolation(
                "MISSING_SPREAD",
                "C10-B requires a live bid/ask spread for SHORT; none available.",
            )
        spread = ask - bid
        if spread < 0:
            raise C10StopPolicyViolation("INVALID_SPREAD", f"ask ({ask}) < bid ({bid}); cannot compute a spread.")
        stop_price = invalidation_price + buffer_price + spread

    if min_stop_distance_price is not None:
        if entry_price is None:
            raise C10StopPolicyViolation(
                "MISSING_ENTRY_FOR_MIN_STOP_CHECK",
                "min_stop_distance_price was supplied but entry_price was not.",
            )
        actual_distance = abs(entry_price - stop_price)
        if actual_distance < min_stop_distance_price:
            raise C10StopPolicyViolation(
                "MIN_STOP_VIOLATION",
                f"computed stop distance {actual_distance} is below the broker minimum "
                f"{min_stop_distance_price}; C10-C policy is REJECT, never WIDEN.",
            )

    return C10StopResult(
        stop_price=stop_price,
        structural_anchor=invalidation_price,
        buffer_price=buffer_price,
        atr_value=atr,
        atr_component=atr_component,
        floor_component=floor_component,
        spread_price=spread,
        direction=direction,
    )
