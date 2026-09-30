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

  Layer B (derived shared-market-fact results) -- TD-8B wires only
  market_structure.analyze_structure() using the TD-6 BoundedCache. Its key includes
  source/dataset identity and the fingerprint of actual visible candle input.
  Other authorities remain unwired pending separate semantic audits.

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
