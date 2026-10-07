"""LSMC_ACTIONABILITY_POLICY_V1 (signed 2026-10-07, docs/governance/
OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md, PR #48) -- implemented by
AG_V1_HOST_HARDENING_R1 T2.

Pure decision layer that sits between a produced Large-SMC opportunity/alert and its
Telegram send: it never recomputes a signal (entry/stop/target/direction/POI all come from
`large_smc_watch`/`large_smc_core` unchanged) and never talks to a broker or Telegram. It only
answers "is this still actionable right now, and how should it be tagged/ranked against other
simultaneous candidates" per the five signed decisions this module implements:

  D1 freshness   -- actionable only if evaluated <=2 trigger-timeframe bars after the
                    triggering bar's close; otherwise INFO_ONLY.
  D2 remaining R  -- actionable only if remaining R (from the SEND-time quote to target) is
                    >=1.5; the send-time bid/ask that produced that number is always persisted
                    with the decision, never discarded.
  D3 no catch-up  -- a READY whose trigger closed before a detected downtime gap never becomes
                    an actionable send after the gap; instead exactly one combined
                    "MISSED - NOT ACTIONABLE" digest is produced for the whole gap.
  D4 unclosed bar -- a signal built from a bar that has not actually closed yet is
                    PENDING_BAR_CLOSE, never STALE/INFO_ONLY -- it is re-evaluated once that
                    bar closes, not discarded.
  D7 correlation  -- simultaneous ACTIONABLE candidates that share the same net USD direction
                    are tagged CORRELATED and ranked by friction (ascending) then remaining R
                    (descending); D7 never suppresses a send by itself.

D5 (display-only precision / Demo gate) and D6 (ST_ASIAN_SWEEP_5R_V1 stays paused) and D8
(SESSION_TRADE_V1 Demo authority denied) are governance/display statements, not actionability
mechanics -- they are recorded in docs/status/AG_V1_HOST_HARDENING_R1_STATUS.md and are
deliberately untouched by this module's code.
"""
from __future__ import annotations

from .policy import (
    ACTIONABLE,
    INFO_ONLY,
    MISSED_NOT_ACTIONABLE,
    PENDING_BAR_CLOSE,
    REASON_BAR_NOT_CLOSED,
    REASON_FRESH,
    REASON_LOW_R,
    REASON_STALE_FRESHNESS,
    XAUUSD_SENSITIVE_SYMBOLS,
    ActionabilityDecision,
    LsmcCandidate,
    MarketQuote,
    MissedDigest,
    TriggerContext,
    bars_since_close,
    classify,
    correlated_exposure,
    detect_downtime,
    missed_digest,
    remaining_r,
    tag_and_rank_correlated,
    usd_direction,
)

__all__ = [
    "ACTIONABLE", "INFO_ONLY", "PENDING_BAR_CLOSE", "MISSED_NOT_ACTIONABLE",
    "REASON_BAR_NOT_CLOSED", "REASON_FRESH", "REASON_LOW_R", "REASON_STALE_FRESHNESS",
    "XAUUSD_SENSITIVE_SYMBOLS",
    "ActionabilityDecision", "LsmcCandidate", "MarketQuote", "MissedDigest", "TriggerContext",
    "bars_since_close", "classify", "correlated_exposure", "detect_downtime", "missed_digest",
    "remaining_r", "tag_and_rank_correlated", "usd_direction",
]
