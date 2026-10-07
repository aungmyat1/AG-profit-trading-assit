"""Pure functions implementing D1/D2/D3/D4/D7 of LSMC_ACTIONABILITY_POLICY_V1.

Nothing here reads a clock, a broker, a file or a network socket. Every function takes
`now`/quotes/candidates as explicit arguments and returns a plain, frozen dataclass or tuple --
this keeps the whole module trivially unit-testable and keeps D1-D4/D7 auditable as pure
specifications, independent of how (or whether) a caller wires it into a live run.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

ACTIONABLE = "ACTIONABLE"
INFO_ONLY = "INFO_ONLY"
PENDING_BAR_CLOSE = "PENDING_BAR_CLOSE"
MISSED_NOT_ACTIONABLE = "MISSED_NOT_ACTIONABLE"

REASON_FRESH = "FRESH_WITHIN_2_TRIGGER_BARS"
REASON_STALE_FRESHNESS = "STALE_BEYOND_2_TRIGGER_BARS"
REASON_LOW_R = "REMAINING_R_BELOW_1_5"
REASON_BAR_NOT_CLOSED = "SIGNAL_BAR_NOT_CLOSED"

MIN_REMAINING_R = 1.5          # D2, signed value -- never change without a new owner decision
MAX_FRESHNESS_BARS = 2         # D1, signed value -- never change without a new owner decision

# D7 (signed doc, PR #48 docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md):
# "Add CORRELATION_CLUSTER_ID + CORRELATED_EXPOSURE (e.g. USD_SHORT, USD_SHORT_SENSITIVE for
# XAUUSD)" -- gold's USD correlation is treated as its own bucket, never merged with a plain FX
# USD pair's bucket, even though both ultimately trace back to the same usd_direction().
XAUUSD_SENSITIVE_SYMBOLS = ("XAUUSD",)


@dataclass(frozen=True)
class TriggerContext:
    """`trigger_timeframe_minutes` is the duration, in minutes, of ONE trigger-timeframe bar
    (e.g. 5 for Large-SMC's M5 sweep/CHoCH trigger). `trigger_close_utc` is when the bar that
    produced the signal closed. `signal_bar_closed=False` means the bar the signal is actually
    built from has not closed yet (D4) -- distinct from staleness (D1), which only applies once
    the signal bar itself exists."""

    trigger_timeframe: str
    trigger_timeframe_minutes: int
    trigger_close_utc: dt.datetime
    signal_bar_closed: bool = True


@dataclass(frozen=True)
class MarketQuote:
    bid: float
    ask: float


@dataclass(frozen=True)
class LsmcCandidate:
    symbol: str
    direction: str  # "LONG" / "SHORT"
    strategy_id: str
    strategy_version: str
    trigger: TriggerContext
    entry: float
    stop: float
    target: float
    reference_id: Optional[str] = None
    friction: Optional[float] = None  # e.g. spread / risk_distance; lower = cheaper to act on


@dataclass(frozen=True)
class ActionabilityDecision:
    symbol: str
    classification: str
    reason_codes: Tuple[str, ...]
    bars_since_trigger_close: Optional[float]
    remaining_r: Optional[float]                    # R_AT_SEND -- the D2 gate uses this one
    send_time_bid: Optional[float]
    send_time_ask: Optional[float]
    remaining_r_at_trigger: Optional[float] = None   # R_AT_TRIGGER (signed doc D2) -- audit only, never gates
    correlated: bool = False
    correlation_group: Optional[str] = None          # CORRELATED_EXPOSURE, e.g. "USD_SHORT" / "USD_SHORT_SENSITIVE"
    correlation_cluster_id: Optional[str] = None      # CORRELATION_CLUSTER_ID (signed doc D7)
    rank_in_group: Optional[int] = None


@dataclass(frozen=True)
class MissedDigest:
    kind: str = field(default="MISSED_NOT_ACTIONABLE_DIGEST", init=False)
    label: str = field(default="MISSED - NOT ACTIONABLE", init=False)
    downtime_start: Optional[dt.datetime] = None
    downtime_end: Optional[dt.datetime] = None
    symbols: Tuple[str, ...] = ()
    count: int = 0
    reason_code: str = field(default="NO_CATCH_UP_READYS_PER_D3", init=False)


def bars_since_close(trigger_close_utc: dt.datetime, now: dt.datetime, tf_minutes: int) -> float:
    """Elapsed trigger-timeframe bars since the triggering bar closed. Never negative (a
    `now` before the trigger close -- clock skew / bad input -- clamps to 0.0 rather than
    returning a confusing negative "freshness")."""
    elapsed_minutes = (now - trigger_close_utc).total_seconds() / 60.0
    return max(0.0, elapsed_minutes) / tf_minutes


def remaining_r(entry: float, stop: float, target: float, direction: str, reference_price: float) -> Optional[float]:
    """Remaining reward, in multiples of the original risk distance, from `reference_price`
    (the send-time quote side, see `classify()`) to `target`. None when risk is zero/invalid
    (fails closed -- a candidate with unmeasurable R can never be ACTIONABLE)."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    remaining = (target - reference_price) if direction == "LONG" else (reference_price - target)
    return remaining / risk


def classify(candidate: LsmcCandidate, *, now: dt.datetime, send_quote: MarketQuote) -> ActionabilityDecision:
    """D4 -> D1 -> D2, in that order. D4 short-circuits everything else (an unclosed bar's
    freshness/R cannot yet be meaningfully evaluated). `send_quote` is the actual bid/ask at
    the moment of evaluation -- D2 requires it to be persisted with the decision regardless of
    outcome, which `send_time_bid`/`send_time_ask` below do unconditionally."""
    if not candidate.trigger.signal_bar_closed:
        return ActionabilityDecision(
            symbol=candidate.symbol, classification=PENDING_BAR_CLOSE, reason_codes=(REASON_BAR_NOT_CLOSED,),
            bars_since_trigger_close=None, remaining_r=None,
            send_time_bid=send_quote.bid, send_time_ask=send_quote.ask,
        )

    bars = bars_since_close(candidate.trigger.trigger_close_utc, now, candidate.trigger.trigger_timeframe_minutes)
    fresh = bars <= MAX_FRESHNESS_BARS

    reference_price = send_quote.bid if candidate.direction == "LONG" else send_quote.ask
    r = remaining_r(candidate.entry, candidate.stop, candidate.target, candidate.direction, reference_price)
    r_ok = r is not None and r >= MIN_REMAINING_R
    # R_AT_TRIGGER (signed doc D2): remaining R measured from the entry price itself -- the
    # price already fixed at trigger time -- never from a live quote. Audit-only: it never
    # gates the classification below, only R_AT_SEND (`r`) does.
    r_at_trigger = remaining_r(candidate.entry, candidate.stop, candidate.target, candidate.direction,
                               reference_price=candidate.entry)

    reasons: List[str] = []
    if not fresh:
        reasons.append(REASON_STALE_FRESHNESS)
    if not r_ok:
        reasons.append(REASON_LOW_R)
    classification = ACTIONABLE if (fresh and r_ok) else INFO_ONLY
    if classification == ACTIONABLE:
        reasons.append(REASON_FRESH)

    return ActionabilityDecision(
        symbol=candidate.symbol, classification=classification, reason_codes=tuple(reasons),
        bars_since_trigger_close=bars, remaining_r=r, remaining_r_at_trigger=r_at_trigger,
        send_time_bid=send_quote.bid, send_time_ask=send_quote.ask,
    )


def detect_downtime(last_run_at: Optional[dt.datetime], now: dt.datetime, max_gap: dt.timedelta) -> bool:
    """True when the elapsed time since the last successful run exceeds `max_gap` -- the
    operator-configured normal poll cadence tolerance. `last_run_at=None` (first run ever /
    no prior checkpoint) is never treated as downtime -- there is nothing to have missed."""
    return last_run_at is not None and (now - last_run_at) > max_gap


def missed_digest(missed_candidates: Sequence[LsmcCandidate], *, downtime_start: Optional[dt.datetime],
                  downtime_end: dt.datetime) -> MissedDigest:
    """D3: one combined digest for everything a downtime gap caused to be withheld -- never a
    separate "catch-up READY" per candidate."""
    return MissedDigest(
        downtime_start=downtime_start, downtime_end=downtime_end,
        symbols=tuple(sorted({c.symbol for c in missed_candidates})), count=len(missed_candidates),
    )


def usd_direction(symbol: str, direction: str) -> Optional[str]:
    """Net USD exposure direction implied by holding `direction` on `symbol`. Returns
    "USD_LONG" / "USD_SHORT", or None when `symbol` has no recognizable USD leg (3+3-letter FX
    convention: EURUSD/GBPUSD/XAUUSD/BTCUSD/ETHUSD quote USD; USDJPY/USDCHF/... base USD)."""
    base, quote = symbol[:3], symbol[3:6]
    if quote == "USD":
        return "USD_SHORT" if direction == "LONG" else "USD_LONG"
    if base == "USD":
        return "USD_LONG" if direction == "LONG" else "USD_SHORT"
    return None


def correlated_exposure(symbol: str, direction: str) -> Optional[str]:
    """D7's CORRELATED_EXPOSURE tag: `usd_direction()`, except XAUUSD gets its own `_SENSITIVE`
    bucket (per the signed doc's explicit example) so a gold candidate is never silently pooled
    into the same correlation cluster as a plain USD-quoted FX pair."""
    base = usd_direction(symbol, direction)
    if base is None:
        return None
    return f"{base}_SENSITIVE" if symbol in XAUUSD_SENSITIVE_SYMBOLS else base


def tag_and_rank_correlated(
    decisions: Sequence[Tuple[LsmcCandidate, ActionabilityDecision]],
) -> List[Tuple[LsmcCandidate, ActionabilityDecision]]:
    """D7: among the ACTIONABLE decisions in this batch (INFO_ONLY/PENDING_BAR_CLOSE candidates
    are passed through untouched -- D7 only concerns itself with things that would actually be
    sent), group by `correlated_exposure()` (CORRELATED_EXPOSURE -- XAUUSD gets its own
    `_SENSITIVE` bucket, never merged with a plain USD pair's bucket). A group of size>=2 has
    every member tagged `correlated=True`, given a deterministic `correlation_cluster_id`
    (CORRELATION_CLUSTER_ID: `"<exposure>:<sorted symbols joined by '+'>"`), and ranked 1..N by
    friction ascending (None friction sorts last, as the most expensive/unknown-cost option),
    then by remaining_r descending as the tie-break. Never suppresses or changes
    `classification` -- D7 is a tag + an order, not a filter."""
    groups: Dict[str, List[int]] = {}
    for i, (cand, dec) in enumerate(decisions):
        if dec.classification != ACTIONABLE:
            continue
        key = correlated_exposure(cand.symbol, cand.direction)
        if key is None:
            continue
        groups.setdefault(key, []).append(i)

    out = list(decisions)
    for key, idxs in groups.items():
        if len(idxs) < 2:
            continue
        cluster_id = f"{key}:{'+'.join(sorted(out[i][0].symbol for i in idxs))}"
        ranked = sorted(idxs, key=lambda i: (
            out[i][0].friction if out[i][0].friction is not None else float("inf"),
            -(out[i][1].remaining_r if out[i][1].remaining_r is not None else float("-inf")),
        ))
        for rank, i in enumerate(ranked, start=1):
            cand, dec = out[i]
            out[i] = (cand, ActionabilityDecision(
                symbol=dec.symbol, classification=dec.classification, reason_codes=dec.reason_codes,
                bars_since_trigger_close=dec.bars_since_trigger_close, remaining_r=dec.remaining_r,
                remaining_r_at_trigger=dec.remaining_r_at_trigger,
                send_time_bid=dec.send_time_bid, send_time_ask=dec.send_time_ask,
                correlated=True, correlation_group=key, correlation_cluster_id=cluster_id, rank_in_group=rank,
            ))
    return out
