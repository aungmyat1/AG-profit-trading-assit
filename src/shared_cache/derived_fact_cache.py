"""TD-6, Layer B: bounded, semantics-aware cache primitive for expensive derived
shared-market-fact computations (e.g. market_structure.analyze_structure()'s
StructureResult). NOT wired into any production authority this pass -- built and
proven here as a correct, collision-safe mechanism only. See
docs/status/TD6_EVENT_DRIVEN_SEMANTIC_CACHE_STATUS.md and
tests/test_td6_deterministic_dedup_targets.py's module docstring for why wiring this
into analyze_structure() was attempted and reverted (replay-substitution and
replay/fixture timestamp-collision risk), and what a future pass needs to resolve
first (a caller-supplied, dataset-scoped identity component in the key).

CACHE IDENTITY -- every field below is REQUIRED, per TD-5's own recommendation:
    (symbol, timeframe, closed_bar_identity, authority_definition_id, feature_version,
     parameters)
`parameters` is an already-sorted tuple of (name, value) pairs (hashable, order-
independent by construction) covering every input that can materially change the
authority's output for the same candle set (e.g. swing_length, close_break,
fetch_count for market_structure.analyze_structure).

`authority_definition_id` is the field that makes this cache SEMANTICALLY safe, not
merely data-safe: it is the exact same mandatory, whitelisted identity string already
enforced by StructureFact/ZoneFact/ImbalanceFact/LiquidityFact's own __post_init__
validation (mtf_context/topdown_contracts.py, frozen since TD-1/TD-3A) -- reused
here verbatim, not reinvented. Two computations that would produce facts under
different definition ids (e.g. a hypothetical two-tier SMC_MARKET_STRUCTURE_TIERED_V1
vs. today's single-tier SMC_MARKET_STRUCTURE_V1) can never share a cache entry,
because they can never share this key field.

`closed_bar_identity` must be the REAL timestamp of the last candle actually used
(never a predicted/guessed boundary) -- a future integration should obtain this from
Layer A's own fetch result (see mt5/market_data.py::get_latest_candles), so Layer B's
freshness would be entirely inherited from Layer A's already-proven, data-identity-
driven invalidation rather than reimplementing a second staleness rule.

FAILURE BEHAVIOR: nothing should be cached on a failure/degraded result unless a
future caller explicitly decides that specific outcome is a valid, stable negative
result worth caching (this module takes no position on that -- a caller should only
call `put()` after a successful computation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Hashable, Optional, Sequence, Tuple

from .bounded_cache import BoundedCache

_CacheKey = Tuple[str, str, str, str, str, Tuple[Tuple[str, Any], ...]]


def build_key(
    *, symbol: str, timeframe: str, closed_bar_identity: datetime,
    authority_definition_id: str, feature_version: str,
    parameters: Sequence[Tuple[str, Hashable]] = (),
) -> _CacheKey:
    """Deterministic, order-independent key. `parameters` is sorted by name so a
    caller supplying the same (name, value) pairs in any order still produces the
    same key."""
    return (
        symbol, timeframe,
        closed_bar_identity.astimezone(timezone.utc).isoformat(),
        authority_definition_id, feature_version,
        tuple(sorted(parameters, key=lambda item: item[0])),
    )


_CACHE: BoundedCache[_CacheKey, Any] = BoundedCache()


def get(key: _CacheKey) -> Optional[Any]:
    return _CACHE.get(key)


def put(key: _CacheKey, value: Any) -> None:
    _CACHE.put(key, value)


def clear_cache() -> None:
    """Test-isolation / explicit reset only."""
    _CACHE.clear()


def cache_diagnostics() -> dict:
    return _CACHE.diagnostics()
