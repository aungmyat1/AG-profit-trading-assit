"""Directional authority gate for ST_SESSION_SWEEP_CONTINUATION_V1.

AG_ST_SESSION_SWEEP_CONTINUATION_REPLAY_BLOCKER_REMEDIATION: MarketBiasResult
(src/market_intelligence/models.py) is the ONE canonical directional authority
project-wide (AG_STRATEGY_DIRECTION_CONTRACT_V1, invariant 3/9 -- "no other universal
component may independently emit BULLISH/BEARISH"). This engine's own regime.py
classifier (RANGE/TREND_UP/TREND_DOWN/TRANSITION) still exists and is still consumed by
replay.py/setups.py exactly as before this change -- it decides WHICH setup branch
(S1/S2/S3) is eligible, never which DIRECTION is allowed. Direction is decided here,
and only here, from the caller-supplied MarketBiasResult.

This module does not fetch, compute, or cache a MarketBiasResult itself (no I/O, no
MT5 call, no market_structure/market_intelligence import beyond the frozen dataclass
type) -- consistent with replay.py's own existing pure-function/no-I-O/
restart-deterministic design (see replay.py module docstring). The caller (an
orchestration layer, e.g. a future replay-runner script) is responsible for resolving
one MarketBiasResult per (symbol, decision_time, session_pair) BEFORE calling
run_replay, exactly as market_intelligence.bias_resolver's own functions already do
(pure functions consuming already-computed evidence, not reaching into subsystems
themselves).
"""
from __future__ import annotations

from typing import FrozenSet, Optional

from market_intelligence.models import MarketBiasResult

LONG: FrozenSet[str] = frozenset({"LONG"})
SHORT: FrozenSet[str] = frozenset({"SHORT"})
NO_TRADE: FrozenSet[str] = frozenset()

BIAS_MISSING = "BIAS_MISSING"
BIAS_SYMBOL_MISMATCH = "BIAS_SYMBOL_MISMATCH"
BIAS_DIRECTION_MISMATCH = "BIAS_DIRECTION_MISMATCH"


def allowed_directions(bias_result: Optional[MarketBiasResult], symbol: str) -> FrozenSet[str]:
    """Returns the set of SetupCandidate.direction values this decision cycle may
    produce. Fail-closed on every non-affirmative case (invariant P32, reused
    verbatim from market_intelligence.bias_resolver's own fail-closed convention):

      bias_result is None                -> NO_TRADE (no bias was ever resolved)
      bias_result.symbol != symbol       -> NO_TRADE (never apply another symbol's bias)
      bias_result.bias == "BULLISH"      -> LONG only
      bias_result.bias == "BEARISH"      -> SHORT only
      bias_result.bias == "NEUTRAL"      -> NO_TRADE (covers both a genuine NEUTRAL
                                             read and confidence="UNAVAILABLE", which
                                             bias_resolver already forces to bias=
                                             "NEUTRAL" -- MarketBiasResult itself never
                                             carries a fourth state, see models.py
                                             InvalidBiasStateError).

    Strategy-local regime (regime.py) is never consulted here and can never override
    this result -- it restricts WHICH setup model is eligible in replay.py's existing
    branch dispatch, not which direction is allowed.
    """
    if bias_result is None:
        return NO_TRADE
    if bias_result.symbol != symbol:
        return NO_TRADE
    if bias_result.bias == "BULLISH":
        return LONG
    if bias_result.bias == "BEARISH":
        return SHORT
    return NO_TRADE  # NEUTRAL (or, structurally, nothing else -- see docstring)


def rejection_reason(bias_result: Optional[MarketBiasResult], symbol: str) -> str:
    """Diagnostic reason code paired with an empty allowed_directions() result --
    never used to change acceptance, only to make a BLOCKED/NO_TRADE cycle
    attributable in replay evidence (steps/rejected_setups)."""
    if bias_result is None:
        return BIAS_MISSING
    if bias_result.symbol != symbol:
        return BIAS_SYMBOL_MISMATCH
    return BIAS_DIRECTION_MISMATCH  # bias resolved but is NEUTRAL/UNAVAILABLE
