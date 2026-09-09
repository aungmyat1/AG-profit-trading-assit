"""AG_STRATEGY_DIRECTION_CONTRACT_V1 BiasResolver -- M1 milestone.

Adapts daytrading.decision.market_bias.MarketBias (the most complete, evidence-backed
BULLISH/BEARISH/NEUTRAL/INDETERMINATE source already in this repository -- itself a pure
derivation over market_structure.tiers.TieredStructureResult, per that module's own
docstring) into the new canonical, immutable, fingerprinted MarketBiasResult.

This is deliberately an ADAPTER, not a new structure/liquidity/bias algorithm (P2
reuse-first, P9 "no other universal component may independently emit BULLISH/BEARISH").
M1 scope only covers htf_structure (from the adapted MarketBias); mtf_alignment,
liquidity_context, and session_context are honestly reported NOT_EVALUATED_M1 rather
than fabricated -- wiring market_swing_structure/liquidity/session_context evidence into
these fields is explicit M2+ future work (see the architecture doc), not silently
invented here.

INDETERMINATE (missing/invalid tiers evidence) maps to NEUTRAL -- P32's fail-closed rule:
missing context must never default to BULLISH/BEARISH.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from daytrading.decision.models import MarketBias, MarketBiasDirection
from market_structure.models import STATE_BEARISH, STATE_BULLISH, TieredStructureResult

from .models import MarketBiasResult, compute_input_fingerprint, make_decision_cycle_id

NOT_EVALUATED_M1 = "NOT_EVALUATED_M1"

_BIAS_MAP = {
    MarketBiasDirection.BULLISH.value: "BULLISH",
    MarketBiasDirection.BEARISH.value: "BEARISH",
    MarketBiasDirection.NEUTRAL.value: "NEUTRAL",
    MarketBiasDirection.INDETERMINATE.value: "NEUTRAL",  # fail-closed, P32
}


def resolve_from_daytrading_market_bias(
    daytrading_bias: MarketBias,
    symbol: str,
    decision_time: datetime,
    session_pair: str,
) -> MarketBiasResult:
    """Pure function: no I/O, no fetch -- the caller supplies the already-computed
    MarketBias evidence (P8: resolver consumes normalized evidence, does not reach into
    every subsystem itself)."""
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")

    bias = _BIAS_MAP.get(daytrading_bias.direction, "NEUTRAL")  # unknown label -> fail closed to NEUTRAL, never guessed bullish/bearish
    confidence = "EVIDENCE_BACKED" if daytrading_bias.direction != MarketBiasDirection.INDETERMINATE.value else "UNAVAILABLE"

    htf_structure = (
        f"{daytrading_bias.external_structure_direction or 'UNDEFINED'}"
        f"|latest_break={daytrading_bias.latest_break or 'NONE'}"
        f"|protected={daytrading_bias.protected_level_type or 'NONE'}:{daytrading_bias.protected_level}"
    )

    fingerprint = compute_input_fingerprint(
        daytrading_bias.direction, daytrading_bias.timeframe,
        daytrading_bias.external_structure_direction, daytrading_bias.protected_level_type,
        daytrading_bias.protected_level, daytrading_bias.latest_break, daytrading_bias.reasons,
        symbol, decision_time.isoformat(),
    )

    decision_cycle_id = make_decision_cycle_id(symbol, decision_time.date(), session_pair)

    return MarketBiasResult(
        bias=bias,
        confidence=confidence,
        decision_cycle_id=decision_cycle_id,
        symbol=symbol,
        decision_time=decision_time,
        htf_structure=htf_structure,
        mtf_alignment=NOT_EVALUATED_M1,
        liquidity_context=NOT_EVALUATED_M1,
        session_context=NOT_EVALUATED_M1,
        reason_codes=daytrading_bias.reasons,
        model_version="AG_MARKET_BIAS_RESOLVER_V1",
        input_fingerprint=fingerprint,
    )


def resolve_from_structure_tiers(
    tiers: TieredStructureResult,
    symbol: str,
    decision_time: datetime,
    session_pair: str,
    timeframe: str = "H1",
) -> MarketBiasResult:
    """M2/M3: THE canonical direction-from-structure mapping (invariant 1/9) -- reads
    only tiers.external.direction, exactly the same evidence
    daytrading.decision.market_bias.derive_market_bias_from_tiers already reads, so this
    does not introduce a second interpretation of the same evidence. After this
    milestone, derive_market_bias_from_tiers calls THIS function for the direction
    label instead of deciding it independently -- see that module's own updated
    docstring."""
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")

    if tiers.status != "VALID" or tiers.external is None:
        return resolve_unavailable(symbol, decision_time, session_pair, f"TIERED_STRUCTURE_STATUS={tiers.status}")

    direction = tiers.external.direction
    if direction == STATE_BULLISH:
        bias: str = "BULLISH"
    elif direction == STATE_BEARISH:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"  # STATE_UNDEFINED or any other value -- fail closed, never guessed

    # tiers.status == "VALID" already confirmed above -- a NEUTRAL bias here means the
    # structure itself is genuinely undefined (real evidence), not missing/failed data.
    confidence = "EVIDENCE_BACKED"
    htf_structure = f"{direction}|latest_bos={getattr(tiers.external.latest_bos, 'kind', None)}|latest_choch={getattr(tiers.external.latest_choch, 'kind', None)}"

    fingerprint = compute_input_fingerprint(
        "structure_tiers", tiers.status, direction,
        getattr(tiers.external.latest_swing_high, "price", None),
        getattr(tiers.external.latest_swing_low, "price", None),
        symbol, decision_time.isoformat(),
    )

    return MarketBiasResult(
        bias=bias,
        confidence=confidence,
        decision_cycle_id=make_decision_cycle_id(symbol, decision_time.date(), session_pair),
        symbol=symbol,
        decision_time=decision_time,
        htf_structure=htf_structure,
        mtf_alignment=NOT_EVALUATED_M1,
        liquidity_context=NOT_EVALUATED_M1,
        session_context=NOT_EVALUATED_M1,
        reason_codes=(f"EXTERNAL_STRUCTURE_{direction}",),
        model_version="AG_MARKET_BIAS_RESOLVER_V1",
        input_fingerprint=fingerprint,
    )


def resolve_unavailable(
    symbol: str, decision_time: datetime, session_pair: str, reason_code: str,
) -> MarketBiasResult:
    """P32 fail-closed entrypoint: missing/insufficient upstream evidence (no H1 data,
    incomplete reference session, unresolved structure, etc.) -- always NEUTRAL, never a
    guessed direction."""
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")
    fingerprint = compute_input_fingerprint("UNAVAILABLE", reason_code, symbol, decision_time.isoformat())
    return MarketBiasResult(
        bias="NEUTRAL",
        confidence="UNAVAILABLE",
        decision_cycle_id=make_decision_cycle_id(symbol, decision_time.date(), session_pair),
        symbol=symbol,
        decision_time=decision_time,
        htf_structure=NOT_EVALUATED_M1,
        mtf_alignment=NOT_EVALUATED_M1,
        liquidity_context=NOT_EVALUATED_M1,
        session_context=NOT_EVALUATED_M1,
        reason_codes=(reason_code,),
        model_version="AG_MARKET_BIAS_RESOLVER_V1",
        input_fingerprint=fingerprint,
    )
