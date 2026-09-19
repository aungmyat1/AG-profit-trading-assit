"""TD-6: bounded, deterministic, semantics-aware in-process caching primitives for
the shared market-data and shared-derived-fact layers. Single-owner local runtime --
no external service, no distributed cache. See
docs/status/TD6_EVENT_DRIVEN_SEMANTIC_CACHE_STATUS.md.

WHAT IS ACTUALLY WIRED INTO PRODUCTION THIS PASS:
  Layer A (raw closed candles) -- implemented DIRECTLY inside
  mt5/market_data.py::get_latest_candles() itself (using BoundedCache from this
  package), not as an external wrapper here. That placement is deliberate: it is the
  one integration point immune by construction to
  historical_replay/data_source_patch.py's existing monkeypatch-based replay
  substitution (which replaces get_latest_candles's own bound name per consumer
  module, function object and all -- see that function's own docstring).

  Layer B (derived shared-market-fact results, e.g. StructureResult) -- the cache
  MECHANISM (derived_fact_cache.py) is built and unit-tested here as a correct,
  collision-safe primitive, but is NOT wired into any production authority
  (market_structure.analyze_structure() or otherwise) this pass. Reason: a
  derived-fact cache keyed on (symbol, timeframe, closed_bar_identity, ...) is safe
  for LIVE data (where closed_bar_identity is a real, globally unique market
  timestamp) but would be unsafe for REPLAY or test-fixture data, where two
  different, unrelated candle sets (different historical datasets, different test
  fixtures) can share the exact same hand-built or simulated timestamp -- producing a
  silently wrong cached result for the second query. Resolving this correctly
  requires the caller to supply a replay/dataset-scoped identity, which is out of
  TD-6's explicit scope ("do not implement replay integration now"). See the status
  doc's LIVE EDGE CASE / Layer B section for the full reasoning.

This package has no knowledge of any strategy (SSC/Sweep-Retest/AS5R/Large-SMC) and
must never be imported by strategy-specific modules.
"""
from .bounded_cache import BoundedCache, CacheDiagnostics
from .derived_fact_cache import build_key as build_derived_fact_cache_key
from .derived_fact_cache import cache_diagnostics as derived_fact_cache_diagnostics
from .derived_fact_cache import clear_cache as clear_derived_fact_cache
from .derived_fact_cache import get as get_derived_fact
from .derived_fact_cache import put as put_derived_fact

__all__ = [
    "BoundedCache", "CacheDiagnostics",
    "build_derived_fact_cache_key", "get_derived_fact", "put_derived_fact",
    "derived_fact_cache_diagnostics", "clear_derived_fact_cache",
]
