"""TD-7: canonical six-timeframe TopDownContext composition (W1 -> D1 -> H4 -> H1 ->
M15 -> M5). INFRASTRUCTURE ONLY -- answers "what shared market context was legitimately
available as of time T", never "should a strategy trade". Reuses TD-3/TD-3A/TD-4's
existing build_<tier>_context() orchestration functions verbatim; implements no
structure/FVG/order-block/liquidity detection of its own (same discipline as every
other module in this package -- see topdown_context_adapters.py /
topdown_new_builders.py module docstrings).

SCOPE BOUNDARY (repeated deliberately): this module adds NO directional confluence, no
bullish/bearish/alignment/confidence score, no allowed_long/allowed_short, no setup
ranking, no strategy gating, no proposal/risk/execution behavior. It only assembles the
six already-frozen tier contexts (topdown_contracts.py) into one TopDownContext and
proves the assembly is internally coherent -- correct lineage, correct symbol, correct
timeframe slot, and every child's bar_close_time no later than one single composition
boundary.

SUPPORTED MODES
  LIVE_CURRENT     -- IMPLEMENTED. Composes the six tiers' current live builders
                      (each independently calls "now" via analyze_structure() /
                      liquidity_result() / etc -- see AS-OF LIMITATION below), all
                      validated against ONE composition boundary captured once at the
                      start of build_topdown_context().
  HISTORICAL_AS_OF -- NOT IMPLEMENTED. No layer beneath this composer
                      (analyze_structure, liquidity_result, the D1/H1 orchestrators,
                      mt5.market_data.get_latest_candles) accepts an as-of/historical-
                      time argument today -- there is nothing honest to compose a
                      historical reconstruction FROM. Calling
                      build_topdown_context(symbol, as_of_time=<datetime>) raises
                      HistoricalAsOfNotSupportedError immediately rather than silently
                      fetching today's latest closed bars and mislabeling them as time
                      T's context. Deferred to TD-8 per this mission's explicit scope
                      boundary.

AS-OF LIMITATION (reported, not hidden): `composition_as_of_time` is captured exactly
once (a single `datetime.now(timezone.utc)` call, via the `_clock` seam below) before
any tier is built, and every built tier is validated against it (see _require_tier) --
but the six `build_<tier>_context()` calls themselves are NOT given this boundary; each
independently calls its own "latest closed bar" authority afresh. In the ordinary case
this is harmless (a full six-call composition takes milliseconds and no new bar closes
mid-composition), but if a bar for one of the six timeframes closes in the brief window
between capturing composition_as_of_time and that tier's own build_<tier>_context()
call, that tier's bar_close_time could exceed composition_as_of_time. TD-7 does not
solve this race (no per-tier as-of injection exists yet to solve it with) -- it DETECTS
it and fails closed (TopDownTemporalViolationError) rather than silently composing a
context that violates its own stated invariant. This is the one way LIVE_CURRENT
composition can deterministically fail even with all six tiers individually healthy;
it is expected to be rare and is exactly what TD-8's replay/as-of work must resolve
properly (a per-tier historical data source, not a race-prone live boundary).

PARTIAL-CONTEXT POLICY: FAIL CLOSED is the only behavior this module implements.
  - A tier whose OWN build_<tier>_context() returns None (its authority could not
    establish a closed bar / hit DATA_ERROR internally) is treated as MISSING, and
    composition raises IncompleteTopDownCompositionError immediately -- TD-7 never
    constructs a TopDownContext with a None child by silently treating "None" as an
    acceptable placeholder for that tier. (TopDownContext's own dataclass DOES allow
    Optional children -- that flexibility exists for TD-1's original "no builder exists
    yet" era, not as license for this composer to skip a tier it could not build.)
  - A tier that WAS built but carries a degraded (existing, not invented)
    data_quality_status other than VALID (today, in practice, only PARTIAL is ever
    returned this way -- see _data_quality_for_structure in topdown_context_adapters.py;
    DATA_ERROR is always converted to None by the tier builders themselves, never
    returned on a live object) is NOT treated as missing: composition proceeds, and the
    degraded status is propagated into the composed TopDownContext.data_quality_status
    (see _aggregate_data_quality) rather than being hidden behind a false VALID. This is
    the "preserve existing data-quality state" behavior the mission requires, distinct
    from the "tier could not be built at all" fail-closed case above.

TD-6 CACHE BOUNDARY: this module calls only the six existing build_<tier>_context()
functions -- it never imports shared_cache, never adds composer-specific caching, and
never wires derived_fact_cache.py (TD6_DERIVED_CACHE_INTEGRATION_DEFERRED remains
carried forward, unresolved by this pass). It benefits indirectly, and only to the
extent the underlying analyze_structure()/liquidity_result()/etc authorities already
do, from TD-6's raw closed-candle cache (Layer A, wired inside
mt5.market_data.get_latest_candles) -- e.g. two tiers that happen to request
byte-identical (symbol, timeframe, count) shapes within the same closed bar would
already dedupe at that layer, with zero composer-specific code. No verification was
done in this pass that any two of the six tiers actually share an identical raw-fetch
shape (TD-5's own audit found the D1/H1 duplication was WITHIN one tier's own call
chain, not across tiers) -- reported as an open question, not a claimed benefit.

SEMANTIC FIREWALL: no SSC/Sweep-Retest/AS5R/Large-SMC/proposal/risk/execution module is
imported here (see tests/test_topdown_composer_no_strategy_import_guard.py and the
pre-existing, whole-package tests/test_mtf_context_execution_guard.py, which already
AST-scans every file under src/mtf_context including this one).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple, Type

from .topdown_context_adapters import build_daily_context, build_h1_context, build_m5_context
from .topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_MISSING,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    DailyContext,
    H1Context,
    H4Context,
    M5Context,
    M15Context,
    TopDownContext,
    WeeklyContext,
)
from .topdown_new_builders import build_h4_context, build_m15_context, build_weekly_context

COMPOSER_FEATURE_VERSION = "TD7_TOPDOWN_COMPOSER_V1"
COMPOSER_SOURCE = "mtf_context.topdown_composer.build_topdown_context"

COMPOSITION_MODE_LIVE_CURRENT = "LIVE_CURRENT"
COMPOSITION_MODE_HISTORICAL_AS_OF = "HISTORICAL_AS_OF"  # not supported this pass -- see module docstring


class TopDownCompositionError(ValueError):
    """Base class for every TD-7 fail-closed composition error."""


class IncompleteTopDownCompositionError(TopDownCompositionError):
    """Raised when a required tier's own build_<tier>_context() returned None (that
    tier's own authority could not establish a closed bar). TD-7's preferred, and only
    implemented, partial-context policy: FAIL CLOSED -- see module docstring."""


class TopDownSymbolMismatchError(TopDownCompositionError):
    """Raised when a built tier context's symbol does not match the requested symbol
    (e.g. a mixed-symbol composition)."""


class TopDownTimeframeSlotError(TopDownCompositionError):
    """Raised when an object placed in a tier slot does not carry that slot's expected
    type/timeframe -- defends against a wrong-slot assignment that the frozen
    dataclasses' own lineage check does not itself catch (that check compares id
    strings, not which physical Python object occupies which slot)."""


class TopDownTemporalViolationError(TopDownCompositionError):
    """Raised when a built tier's bar_close_time exceeds the single composition
    boundary captured for this call -- see module docstring's AS-OF LIMITATION."""


class HistoricalAsOfNotSupportedError(NotImplementedError):
    """Raised immediately for any as_of_time request -- see module docstring's
    SUPPORTED MODES. Deferred to TD-8; TD-7 never fakes historical support."""


_QUALITY_SEVERITY = {
    DATA_QUALITY_VALID: 0,
    DATA_QUALITY_PARTIAL: 1,
    DATA_QUALITY_MISSING: 2,
    DATA_QUALITY_DATA_ERROR: 3,
}


def _aggregate_data_quality(tiers: Tuple[object, ...]) -> str:
    """Worst-case rollup of the six tiers' OWN, pre-existing data_quality_status
    values -- not a new score, not a strategy signal, just the most-degraded status
    among the six, so a caller reading TopDownContext.data_quality_status alone is
    never told VALID when one tier is actually degraded."""
    worst = DATA_QUALITY_VALID
    for tier in tiers:
        status = tier.data_quality_status
        if _QUALITY_SEVERITY[status] > _QUALITY_SEVERITY[worst]:
            worst = status
    return worst


def compute_topdown_context_id(
    *, symbol: str, evaluation_time: datetime, child_context_ids: Tuple[str, ...],
    feature_version: str,
) -> str:
    """Deterministic identity for a composed TopDownContext -- same blake2b/pipe-join
    idiom as topdown_contracts.compute_context_id (no new hashing convention
    invented). Same (symbol, evaluation_time, six child context_ids, feature_version)
    always yields the same id; a different child id changes the composed id."""
    payload = "|".join([
        symbol, evaluation_time.astimezone(timezone.utc).isoformat(), feature_version,
        *child_context_ids,
    ])
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=12).hexdigest()
    return f"TDTOP-{digest}"


def _require_tier(
    tier, *, expected_type: Type, expected_timeframe: str, symbol: str,
    composition_as_of_time: datetime, label: str,
) -> None:
    if not isinstance(tier, expected_type):
        raise TopDownTimeframeSlotError(
            f"{label}: expected a {expected_type.__name__} instance, got {type(tier).__name__}"
        )
    if tier.timeframe != expected_timeframe:
        raise TopDownTimeframeSlotError(
            f"{label}: expected timeframe {expected_timeframe!r}, got {tier.timeframe!r}"
        )
    if tier.symbol != symbol:
        raise TopDownSymbolMismatchError(
            f"{label}: expected symbol {symbol!r}, got {tier.symbol!r}"
        )
    if tier.bar_close_time > composition_as_of_time:
        raise TopDownTemporalViolationError(
            f"{label}: bar_close_time {tier.bar_close_time.isoformat()} is after "
            f"composition_as_of_time {composition_as_of_time.isoformat()}"
        )


def build_topdown_context(
    symbol: str, *, as_of_time: Optional[datetime] = None,
    _clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> TopDownContext:
    """Compose the canonical six-timeframe TopDownContext for `symbol`.

    LIVE_CURRENT only (`as_of_time` must be None -- see module docstring). Captures one
    `composition_as_of_time` boundary, builds all six tiers top-down (each freshly-
    built parent's REAL context_id is threaded into the next tier's
    parent_*_context_id kwarg -- never a caller-supplied/unverified id), validates each
    against the single boundary plus symbol/timeframe-slot correctness, and fails
    closed (a TopDownCompositionError subclass) on the first violation rather than
    returning a partially-correct object.

    `_clock` is a private testability seam (not part of the public contract -- always
    omit it in real use) so tests can pin `composition_as_of_time` without patching
    the standard library; production callers always get real `datetime.now(timezone.utc)`.
    """
    if as_of_time is not None:
        raise HistoricalAsOfNotSupportedError(
            "HISTORICAL_AS_OF is not supported by TD-7 -- no layer beneath this composer "
            "(analyze_structure/liquidity_result/get_latest_candles) accepts an as-of "
            "time yet. Call build_topdown_context(symbol) with no as_of_time for "
            "LIVE_CURRENT composition; historical/as-of reconstruction is deferred to TD-8."
        )

    composition_as_of_time = _clock()

    weekly = build_weekly_context(symbol)
    if weekly is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: weekly (W1) context unavailable")
    _require_tier(weekly, expected_type=WeeklyContext, expected_timeframe=TIMEFRAME_W1,
                  symbol=symbol, composition_as_of_time=composition_as_of_time, label="weekly")

    daily = build_daily_context(symbol, parent_weekly_context_id=weekly.context_id)
    if daily is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: daily (D1) context unavailable")
    _require_tier(daily, expected_type=DailyContext, expected_timeframe=TIMEFRAME_D1,
                  symbol=symbol, composition_as_of_time=composition_as_of_time, label="daily")

    h4 = build_h4_context(symbol, parent_daily_context_id=daily.context_id)
    if h4 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: H4 context unavailable")
    _require_tier(h4, expected_type=H4Context, expected_timeframe=TIMEFRAME_H4,
                  symbol=symbol, composition_as_of_time=composition_as_of_time, label="h4")

    h1 = build_h1_context(symbol, parent_h4_context_id=h4.context_id)
    if h1 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: H1 context unavailable")
    _require_tier(h1, expected_type=H1Context, expected_timeframe=TIMEFRAME_H1,
                  symbol=symbol, composition_as_of_time=composition_as_of_time, label="h1")

    m15 = build_m15_context(symbol, parent_h1_context_id=h1.context_id)
    if m15 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: M15 context unavailable")
    _require_tier(m15, expected_type=M15Context, expected_timeframe=TIMEFRAME_M15,
                  symbol=symbol, composition_as_of_time=composition_as_of_time, label="m15")

    m5 = build_m5_context(symbol, parent_m15_context_id=m15.context_id)
    if m5 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: M5 context unavailable")
    _require_tier(m5, expected_type=M5Context, expected_timeframe=TIMEFRAME_M5,
                  symbol=symbol, composition_as_of_time=composition_as_of_time, label="m5")

    tiers: Tuple[WeeklyContext, DailyContext, H4Context, H1Context, M15Context, M5Context] = (
        weekly, daily, h4, h1, m15, m5,
    )
    data_quality_status = _aggregate_data_quality(tiers)
    context_id = compute_topdown_context_id(
        symbol=symbol, evaluation_time=composition_as_of_time,
        child_context_ids=tuple(tier.context_id for tier in tiers),
        feature_version=COMPOSER_FEATURE_VERSION,
    )

    return TopDownContext(
        context_id=context_id, symbol=symbol, evaluation_time=composition_as_of_time,
        data_quality_status=data_quality_status,
        weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5,
    )
