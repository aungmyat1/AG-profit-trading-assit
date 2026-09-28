"""TD-6 Layer B cache, wired only to market_structure.analyze_structure in TD-8B.
TD-6 initially deferred wiring because a timestamp-only key could collide across
replay datasets. TD-8B adds source/dataset and actual input-content identity.

CACHE IDENTITY -- every field below is REQUIRED:
    (source_dataset_identity, symbol, timeframe, closed_bar_identity,
     authority_definition_id, feature_version,
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

`closed_bar_identity` for structure includes the actual last candle time and a
fingerprint of the complete fetched candle population. Replay also includes its
caller-supplied as-of time; `source_dataset_identity` distinguishes LIVE from each
content-derived replay dataset identity.

FAILURE BEHAVIOR: nothing should be cached on a failure/degraded result unless a
future caller explicitly decides that specific outcome is a valid, stable negative
result worth caching (this module takes no position on that -- a caller should only
call `put()` after a successful computation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Hashable, Optional, Sequence, Tuple

from .bounded_cache import BoundedCache

_CacheKey = Tuple[str, str, str, str, str, str, Tuple[Tuple[str, Any], ...]]


def build_key(
    *, source_dataset_identity: str, symbol: str, timeframe: str, closed_bar_identity: str | datetime,
    authority_definition_id: str, feature_version: str,
    parameters: Sequence[Tuple[str, Hashable]] = (),
) -> _CacheKey:
    """Deterministic, order-independent key. `parameters` is sorted by name so a
    caller supplying the same (name, value) pairs in any order still produces the
    same key."""
    if not source_dataset_identity:
        raise ValueError("source_dataset_identity is required")
    closed_identity = (closed_bar_identity.astimezone(timezone.utc).isoformat()
                       if isinstance(closed_bar_identity, datetime) else closed_bar_identity)
    if not closed_identity:
        raise ValueError("closed_bar_identity is required")
    return (
        source_dataset_identity, symbol, timeframe, closed_identity,
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
