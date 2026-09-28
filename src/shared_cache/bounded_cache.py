"""TD-6: generic, bounded, thread-safe, in-process cache primitive. Domain-agnostic --
knows nothing about candles, symbols, or market structure. Both the raw closed-candle
cache (raw_candle_cache.py) and the derived shared-market-fact cache
(derived_fact_cache.py) are built on top of this one primitive so eviction policy,
diagnostics, and concurrency behavior are defined exactly once.

Eviction policy: bounded LRU (least-recently-used), via `collections.OrderedDict` --
`get()` moves a hit to the most-recently-used end; `put()` evicts the least-recently-
used entry once `max_entries` is exceeded. Chosen because it is the simplest
deterministic bounded policy that naturally favors whatever (symbol, timeframe, ...)
combination is actually being queried repeatedly (this project's realistic pattern:
`build_daily_context("EURUSD")` called repeatedly during a session), without any
distributed/external infrastructure (single-owner local runtime, per TD-6 scope).

Concurrency: a single `threading.Lock` guards every read/write. This project's
runtime is a local, single-process daytrading/research tool with no evidence of
concurrent cache access from multiple OS processes or a multi-threaded server request
path (no such usage found in this repository) -- a single in-process lock is the
minimum synchronization that makes this safe if a future caller ever does use
threads (e.g. a background poller alongside a main loop), without adding any
external-service dependency.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Hashable, Optional, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

DEFAULT_MAX_ENTRIES = 256


@dataclass
class CacheDiagnostics:
    """Lightweight, read-only-by-convention counters. Suitable for a future TD-9
    read-only exposure -- nothing here is authoritative market/trading state."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    puts: int = 0
    size: int = 0

    def as_dict(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "evictions": self.evictions,
                "puts": self.puts, "size": self.size}


class BoundedCache(Generic[K, V]):
    """Bounded LRU cache. `is_valid(value) -> bool` is called on every read to let a
    caller apply its own deterministic staleness rule (e.g. "has the bar-boundary
    this entry was fetched for passed?") without this class knowing what a "bar" is.
    An entry that fails `is_valid` is treated as a miss and evicted immediately --
    this cache never serves a value its own validity check has already rejected."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._store: "OrderedDict[K, V]" = OrderedDict()
        self._lock = threading.Lock()
        self._diagnostics = CacheDiagnostics()

    def get(self, key: K, is_valid: Optional[Callable[[V], bool]] = None) -> Optional[V]:
        with self._lock:
            if key not in self._store:
                self._diagnostics.misses += 1
                return None
            value = self._store[key]
            if is_valid is not None and not is_valid(value):
                del self._store[key]
                self._diagnostics.misses += 1
                self._diagnostics.size = len(self._store)
                return None
            self._store.move_to_end(key)
            self._diagnostics.hits += 1
            return value

    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            self._diagnostics.puts += 1
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)
                self._diagnostics.evictions += 1
            self._diagnostics.size = len(self._store)

    def clear(self) -> None:
        """Test-isolation / explicit reset only -- never called as part of normal
        request handling (no broad-clear invalidation policy; see module docstring)."""
        with self._lock:
            self._store.clear()
            self._diagnostics = CacheDiagnostics()

    def diagnostics(self) -> dict:
        with self._lock:
            self._diagnostics.size = len(self._store)
            return self._diagnostics.as_dict()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
