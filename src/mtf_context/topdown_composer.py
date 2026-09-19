"""TD-7/TD-8: canonical six-timeframe TopDownContext composition (W1 -> D1 -> H4 -> H1
-> M15 -> M5). INFRASTRUCTURE ONLY -- answers "what shared market context was
legitimately available as of time T", never "should a strategy trade". Reuses
TD-3/TD-3A/TD-4's existing build_<tier>_context() orchestration functions verbatim;
implements no structure/FVG/order-block/liquidity detection of its own (same discipline
as every other module in this package -- see topdown_context_adapters.py /
topdown_new_builders.py module docstrings).

SCOPE BOUNDARY (repeated deliberately): this module adds NO directional confluence, no
bullish/bearish/alignment/confidence score, no allowed_long/allowed_short, no setup
ranking, no strategy gating, no proposal/risk/execution behavior. It only assembles the
six already-frozen tier contexts (topdown_contracts.py) into one TopDownContext and
proves the assembly is internally coherent -- correct lineage, correct symbol, correct
timeframe slot, and every child's bar_close_time no later than one single composition
boundary.

SUPPORTED MODES
  LIVE_CURRENT     -- IMPLEMENTED (TD-7, unchanged by TD-8). Composes the six tiers'
                      current live builders (each independently calls "now" via
                      analyze_structure()/liquidity_result()/etc -- see AS-OF
                      LIMITATION below), all validated against ONE composition boundary
                      captured once at the start of build_topdown_context().
  HISTORICAL_AS_OF -- IMPLEMENTED (TD-8). Caller supplies `as_of_time` (tz-aware UTC)
                      AND `replay_store` (a historical_replay.HistoricalCandleStore
                      already loaded with every timeframe's historical series for
                      `symbol`). The ENTIRE six-tier build runs inside
                      `historical_replay.historical_data_context(replay_store,
                      as_of_time, ...)` -- the same, already-tested substitution
                      mechanism `historical_replay/data_source_patch.py` established
                      well before TD-8 (see tests/test_historical_replay_no_lookahead.py),
                      reused verbatim, not reimplemented. `evaluation_time` on the
                      resulting TopDownContext is set to `as_of_time` EXACTLY -- never
                      wall-clock `datetime.now()` -- and `replay_store` is REQUIRED
                      whenever `as_of_time` is supplied (never silently falls through to
                      LIVE MT5; see REPLAY FALLBACK PROHIBITION below).

AS-OF LIMITATION (LIVE_CURRENT only, reported, not hidden): `composition_as_of_time` is
captured exactly once (a single `datetime.now(timezone.utc)` call, via the `_clock`
seam below) before any tier is built, and every built tier is validated against it (see
_require_tier) -- but the six `build_<tier>_context()` calls themselves are NOT given
this boundary; each independently calls its own "latest closed bar" authority afresh.
In the ordinary case this is harmless (a full six-call composition takes milliseconds
and no new bar closes mid-composition), but if a bar for one of the six timeframes
closes in the brief window between capturing composition_as_of_time and that tier's own
build_<tier>_context() call, that tier's bar_close_time could exceed
composition_as_of_time. This module does not solve this race for LIVE_CURRENT (no
per-tier as-of injection exists for it) -- it DETECTS it and fails closed
(TopDownTemporalViolationError) rather than silently composing a context that violates
its own stated invariant. HISTORICAL_AS_OF mode has NO such race: every one of the six
builders reads from the SAME already-loaded, immutable `replay_store` at the SAME fixed
`as_of_time` for the whole call, by construction of `historical_data_context`.

NO-LOOKAHEAD ENFORCEMENT (HISTORICAL_AS_OF -- read carefully, this is the actual
authority, not `_require_tier`): the true, primary no-future-data guarantee for replay
comes entirely from `historical_replay.candle_store.HistoricalCandleStore.closed_candles`
-- it will never return a bar whose `open_time + timeframe_duration > as_of`, so the
LAST candle any detector ever sees during HISTORICAL_AS_OF is always a genuinely closed
bar as of `as_of_time`. `_require_tier`'s own `tier.bar_close_time <= composition_as_of_
time` check is only ever comparing a bar's OPEN time (see topdown_context_adapters.py:
every tier's `bar_close_time` field is populated from `structure.data_end_utc`, which is
itself the last candle's OPEN time, not its true close -- a naming carried over
unchanged from TD-1) against `as_of_time` -- a WEAKER condition than true closure. It is
never violated in HISTORICAL_AS_OF mode because the store already guarantees true
closure upstream; it remains a secondary, always-trivially-satisfied safety net in this
mode, not the primary guarantee. It is the PRIMARY guarantee for LIVE_CURRENT (where
`get_latest_candles`'s own live position-1 exclusion is what makes it trivially true).

REPLAY FALLBACK PROHIBITION (P0 correctness requirement): `as_of_time` without
`replay_store` raises `ReplayStoreRequiredError` immediately -- HISTORICAL_AS_OF must
NEVER silently fall through to LIVE MT5. Additionally, once inside
`historical_data_context`, EVERY live MT5 SDK call
(`copy_rates_from_pos`/`copy_rates_range`) is itself patched to raise
`HistoricalDataError("HISTORICAL_REPLAY_MT5_ACCESS_FORBIDDEN", ...)` -- a second,
independent layer of defense against a data-access path this composer's own reuse of
`build_<tier>_context()` might have missed (see historical_replay/data_source_patch.py's
own module docstring for the exact regression class this already guards against).

DATASET IDENTITY (P5/P6): before entering `historical_data_context`, this module calls
`replay_store.dataset_identity(symbol, timeframe)` for all six required timeframes.
A `None` result (nothing was ever loaded for that (symbol, timeframe)) fails closed
immediately (`ReplayDatasetIdentityMissingError`) -- BEFORE any fetch is attempted --
rather than surfacing a deep INSUFFICIENT_CANDLES/DATA_MISSING error from inside a
builder. The six per-tier `ReplayDatasetIdentity.fingerprint`s (content-derived SHA-256,
see historical_replay/dataset_identity.py) are folded into one deterministic
`dataset_identity` token stored on the composed `TopDownContext` (topdown_contracts.py's
own `dataset_identity` field, added in TD-8) and into `compute_topdown_context_id`'s own
hash payload -- two datasets sharing symbol/timeframe/timestamps but differing in OHLC
content always produce a different composed identity (TD-8 P15/P16). Detector
provenance (`source`/`feature_version` on each tier) is NEVER overwritten with this
dataset provenance -- they remain two different dimensions, exactly as TD-8 requires.

SESSION-REFERENCE-LEVEL LIMITATION (HISTORICAL_AS_OF, reported, not hidden):
`supply_demand.native_zones.session_zone()` (feeding H1's "asian" session reference
level and M15's three session reference levels) internally calls
`assistant.market_data.session_snapshot()`, which is entirely wall-clock-driven (calls
`datetime.now(timezone.utc)` itself for both its default session date and its own
session-completeness check) and has no as-of parameter at all. `historical_data_context`
already anticipated this exact gap and fails it closed
(`_PATCHED_RANGE_CANDLE_TARGETS` maps `assistant.market_data.get_candles` to
`HISTORICAL_SESSION_DATA_UNAVAILABLE`) -- so no live market data ever leaks through this
path, but session-derived ReferenceLevelFacts are simply ABSENT from H1Context/
M15Context during HISTORICAL_AS_OF, regardless of the requested `as_of_time`, exactly
like any other "insufficient data" case this repository already handles honestly
(`_reference_level_fact_from_zone` returns None rather than fabricating a fact). This
does not fail the tier build (H1Context/M15Context still construct successfully; only
this one fact family is missing) and is TD-8's one known, explicitly out-of-scope-to-fix
limitation of the six-tier replay path (fixing session_snapshot() to accept an as-of
parameter is a change to assistant/market_data.py, outside TD-8's "reuse existing
abstractions, don't refactor strategy-adjacent modules" mandate).

PARTIAL-CONTEXT POLICY (both modes): FAIL CLOSED is the only behavior this module
implements.
  - A tier whose OWN build_<tier>_context() returns None (its authority could not
    establish a closed bar / hit DATA_ERROR internally, or -- in HISTORICAL_AS_OF --
    the replay store had insufficient historical depth by `as_of_time`) is treated as
    MISSING, and composition raises IncompleteTopDownCompositionError immediately --
    this composer never constructs a TopDownContext with a None child by silently
    treating "None" as an acceptable placeholder for that tier. (TopDownContext's own
    dataclass DOES allow Optional children -- that flexibility exists for TD-1's
    original "no builder exists yet" era, not as license for this composer to skip a
    tier it could not build.)
  - A tier that WAS built but carries a degraded (existing, not invented)
    data_quality_status other than VALID (today, in practice, only PARTIAL is ever
    returned this way -- see _data_quality_for_structure in topdown_context_adapters.py;
    DATA_ERROR is always converted to None by the tier builders themselves, never
    returned on a live object) is NOT treated as missing: composition proceeds, and the
    degraded status is propagated into the composed TopDownContext.data_quality_status
    (see _aggregate_data_quality) rather than being hidden behind a false VALID.

TD-6/TD-8B CACHE BOUNDARY: this module calls only the six existing
build_<tier>_context() functions -- it never imports shared_cache or adds
composer-specific caching. TD-8B caches only the shared structure authority;
other derived authorities remain deferred. It benefits indirectly, and only to the
extent the underlying analyze_structure()/liquidity_result()/etc authorities already
do, from TD-6's raw closed-candle cache (Layer A, wired inside
mt5.market_data.get_latest_candles for LIVE_CURRENT only -- HISTORICAL_AS_OF never
reaches that cache at all, since get_latest_candles itself is fully monkeypatched away
by historical_data_context; TD-6's live raw-identity `(symbol, timeframe, count)` is
therefore never at risk of serving a replay result, or vice versa, by construction, not
by any new source-aware key -- see docs/status/TD8_REPLAY_TEMPORAL_PARITY_STATUS.md for
the fuller RAW_CACHE_ISOLATION discussion). A future TD-6-Layer-B derived-fact cache key
could safely include `ReplayDatasetIdentity.fingerprint` as its dataset/source
discriminator once wired -- not done this pass.

SEMANTIC FIREWALL: no SSC/Sweep-Retest/AS5R/Large-SMC/proposal/risk/execution module is
imported here (see tests/test_topdown_composer_no_strategy_import_guard.py and the
pre-existing, whole-package tests/test_mtf_context_execution_guard.py, which already
AST-scans every file under src/mtf_context including this one). `historical_replay` is
a new, deliberate additive dependency for TD-8 (replay substitution infrastructure,
not a strategy/proposal/risk/execution module).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple, Type

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.data_source_patch import historical_data_context
from historical_replay.dataset_identity import ReplayDatasetIdentity
from historical_replay.symbol_metadata_manifest import HistoricalSymbolMetadataManifest

from .topdown_context_adapters import build_daily_context, build_h1_context, build_m5_context
from .topdown_contracts import (
    COMPOSITION_MODE_HISTORICAL_AS_OF,
    COMPOSITION_MODE_LIVE_CURRENT,
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

# Re-exported for backward compatibility -- TD-7 originally defined these locally;
# TD-8 moved the canonical definition to topdown_contracts.py (so the frozen
# TopDownContext contract itself can validate composition_mode) and this module now
# imports rather than redefines them. Same strings, same objects, no behavior change
# for any existing importer of mtf_context.topdown_composer.COMPOSITION_MODE_*.
__all_modes__ = (COMPOSITION_MODE_LIVE_CURRENT, COMPOSITION_MODE_HISTORICAL_AS_OF)

_REQUIRED_TIMEFRAMES: Tuple[str, ...] = (
    TIMEFRAME_W1, TIMEFRAME_D1, TIMEFRAME_H4, TIMEFRAME_H1, TIMEFRAME_M15, TIMEFRAME_M5,
)


class TopDownCompositionError(ValueError):
    """Base class for every TD-7/TD-8 fail-closed composition error."""


class IncompleteTopDownCompositionError(TopDownCompositionError):
    """Raised when a required tier's own build_<tier>_context() returned None (that
    tier's own authority could not establish a closed bar). This composer's preferred,
    and only implemented, partial-context policy: FAIL CLOSED -- see module docstring."""


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
    boundary captured for this call -- see module docstring's AS-OF LIMITATION /
    NO-LOOKAHEAD ENFORCEMENT sections."""


class HistoricalAsOfNotSupportedError(NotImplementedError):
    """No longer raised by this module (HISTORICAL_AS_OF is implemented as of TD-8) --
    kept as a public name for backward compatibility with any TD-7-era caller that
    catches it defensively. Never raised."""


class NaiveAsOfTimeError(TopDownCompositionError):
    """Raised when `as_of_time` is timezone-naive -- same NAIVE_DATETIME_REJECTED
    fail-closed idiom as mt5/market_data.py::get_candles and
    historical_replay/candle_store.py's own guard; TD-8 never silently assumes UTC."""


class ReplayStoreRequiredError(TopDownCompositionError):
    """Raised when `as_of_time` is supplied without `replay_store`, or vice versa.
    HISTORICAL_AS_OF must never silently fall through to LIVE MT5 -- see module
    docstring's REPLAY FALLBACK PROHIBITION."""


class ReplayDatasetIdentityMissingError(TopDownCompositionError):
    """Raised when `replay_store` has no loaded series (hence no dataset identity, see
    HistoricalCandleStore.dataset_identity) for a required (symbol, timeframe) tier --
    fails closed before attempting any fetch, live or replay."""


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
    feature_version: str, composition_mode: str = COMPOSITION_MODE_LIVE_CURRENT,
    dataset_identity: Optional[str] = None,
) -> str:
    """Deterministic identity for a composed TopDownContext -- same blake2b/pipe-join
    idiom as topdown_contracts.compute_context_id (no new hashing convention
    invented). Same (symbol, evaluation_time, composition_mode, dataset_identity, six
    child context_ids, feature_version) always yields the same id; a different child
    id, a different dataset_identity, or a different composition_mode all change the
    composed id (TD-8 P16: dataset/source provenance IS part of composed identity)."""
    payload = "|".join([
        symbol, evaluation_time.astimezone(timezone.utc).isoformat(), feature_version,
        composition_mode, dataset_identity or "",
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


def _compose(
    symbol: str, *, evaluation_time: datetime, composition_mode: str, dataset_identity_token: Optional[str],
) -> TopDownContext:
    """Shared six-tier build/validate/assemble sequence for both LIVE_CURRENT and
    HISTORICAL_AS_OF -- the only difference between the two modes is WHICH functions
    `build_weekly_context`/etc. actually call underneath (live MT5 vs. a
    historical_data_context-patched replay store) and what `evaluation_time`/
    `composition_mode`/`dataset_identity_token` are; this function itself has no
    knowledge of live vs. replay."""
    weekly = build_weekly_context(symbol)
    if weekly is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: weekly (W1) context unavailable")
    _require_tier(weekly, expected_type=WeeklyContext, expected_timeframe=TIMEFRAME_W1,
                  symbol=symbol, composition_as_of_time=evaluation_time, label="weekly")

    daily = build_daily_context(symbol, parent_weekly_context_id=weekly.context_id)
    if daily is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: daily (D1) context unavailable")
    _require_tier(daily, expected_type=DailyContext, expected_timeframe=TIMEFRAME_D1,
                  symbol=symbol, composition_as_of_time=evaluation_time, label="daily")

    h4 = build_h4_context(symbol, parent_daily_context_id=daily.context_id)
    if h4 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: H4 context unavailable")
    _require_tier(h4, expected_type=H4Context, expected_timeframe=TIMEFRAME_H4,
                  symbol=symbol, composition_as_of_time=evaluation_time, label="h4")

    h1 = build_h1_context(symbol, parent_h4_context_id=h4.context_id)
    if h1 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: H1 context unavailable")
    _require_tier(h1, expected_type=H1Context, expected_timeframe=TIMEFRAME_H1,
                  symbol=symbol, composition_as_of_time=evaluation_time, label="h1")

    m15 = build_m15_context(symbol, parent_h1_context_id=h1.context_id)
    if m15 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: M15 context unavailable")
    _require_tier(m15, expected_type=M15Context, expected_timeframe=TIMEFRAME_M15,
                  symbol=symbol, composition_as_of_time=evaluation_time, label="m15")

    m5 = build_m5_context(symbol, parent_m15_context_id=m15.context_id)
    if m5 is None:
        raise IncompleteTopDownCompositionError(f"{symbol}: M5 context unavailable")
    _require_tier(m5, expected_type=M5Context, expected_timeframe=TIMEFRAME_M5,
                  symbol=symbol, composition_as_of_time=evaluation_time, label="m5")

    tiers: Tuple[WeeklyContext, DailyContext, H4Context, H1Context, M15Context, M5Context] = (
        weekly, daily, h4, h1, m15, m5,
    )
    data_quality_status = _aggregate_data_quality(tiers)
    context_id = compute_topdown_context_id(
        symbol=symbol, evaluation_time=evaluation_time,
        child_context_ids=tuple(tier.context_id for tier in tiers),
        feature_version=COMPOSER_FEATURE_VERSION,
        composition_mode=composition_mode, dataset_identity=dataset_identity_token,
    )

    return TopDownContext(
        context_id=context_id, symbol=symbol, evaluation_time=evaluation_time,
        data_quality_status=data_quality_status,
        weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5,
        composition_mode=composition_mode, dataset_identity=dataset_identity_token,
    )


def build_topdown_context(
    symbol: str, *, as_of_time: Optional[datetime] = None,
    replay_store: Optional[HistoricalCandleStore] = None,
    replay_symbol_metadata_manifest: Optional[HistoricalSymbolMetadataManifest] = None,
    _clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> TopDownContext:
    """Compose the canonical six-timeframe TopDownContext for `symbol`.

    LIVE_CURRENT (`as_of_time=None`, the default): captures one
    `composition_as_of_time` boundary via `_clock` (a private testability seam --
    always omit it in real use; production callers always get real
    `datetime.now(timezone.utc)`), builds all six tiers top-down against live MT5.

    HISTORICAL_AS_OF (`as_of_time` supplied): `replay_store` is REQUIRED (never
    optional in this mode -- see ReplayStoreRequiredError). `as_of_time` must be
    timezone-aware UTC (NaiveAsOfTimeError otherwise). Every required timeframe's
    dataset identity is verified present in `replay_store` BEFORE any fetch is
    attempted (ReplayDatasetIdentityMissingError otherwise). The entire six-tier build
    then runs inside `historical_replay.historical_data_context`, so every
    `build_<tier>_context()` call transparently consumes `replay_store` instead of live
    MT5, with zero code change to any of the six builders themselves.

    Both modes build all six tiers top-down (each freshly-built parent's REAL
    context_id is threaded into the next tier's parent_*_context_id kwarg -- never a
    caller-supplied/unverified id), validate each against symbol/timeframe-slot/
    temporal correctness, and fail closed (a TopDownCompositionError subclass) on the
    first violation rather than returning a partially-correct object.
    """
    if as_of_time is None:
        if replay_store is not None:
            raise ReplayStoreRequiredError(
                "replay_store was supplied without as_of_time -- pass as_of_time to enter "
                "HISTORICAL_AS_OF mode, or omit replay_store for LIVE_CURRENT"
            )
        return _compose(
            symbol, evaluation_time=_clock(), composition_mode=COMPOSITION_MODE_LIVE_CURRENT,
            dataset_identity_token=None,
        )

    if as_of_time.tzinfo is None:
        raise NaiveAsOfTimeError("as_of_time must be timezone-aware UTC, got a naive datetime")
    if replay_store is None:
        raise ReplayStoreRequiredError(
            "as_of_time was supplied without replay_store -- HISTORICAL_AS_OF must never "
            "silently fall through to LIVE MT5; pass the replay_store carrying the "
            "historical dataset for every required timeframe"
        )

    dataset_identities: Dict[str, ReplayDatasetIdentity] = {}
    for timeframe in _REQUIRED_TIMEFRAMES:
        identity = replay_store.dataset_identity(symbol, timeframe)
        if identity is None:
            raise ReplayDatasetIdentityMissingError(
                f"{symbol} {timeframe}: no historical dataset loaded into replay_store -- "
                "HISTORICAL_AS_OF composition fails closed rather than falling back to live MT5"
            )
        dataset_identities[timeframe] = identity

    dataset_identity_token = "||".join(
        dataset_identities[tf].as_composed_identity_token() for tf in _REQUIRED_TIMEFRAMES
    )

    with historical_data_context(replay_store, as_of_time, symbol_metadata_manifest=replay_symbol_metadata_manifest):
        return _compose(
            symbol, evaluation_time=as_of_time, composition_mode=COMPOSITION_MODE_HISTORICAL_AS_OF,
            dataset_identity_token=dataset_identity_token,
        )
