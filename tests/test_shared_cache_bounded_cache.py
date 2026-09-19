"""TD-6: tests for the generic BoundedCache primitive, in isolation -- no domain
knowledge (candles, structure, symbols) involved.
"""
from __future__ import annotations

import threading

import pytest

from shared_cache.bounded_cache import BoundedCache


def test_put_then_get_hits():
    cache = BoundedCache(max_entries=10)
    cache.put("k", "v")
    assert cache.get("k") == "v"


def test_missing_key_is_miss():
    cache = BoundedCache(max_entries=10)
    assert cache.get("nope") is None


def test_is_valid_predicate_rejects_stale_entry_and_evicts_it():
    cache = BoundedCache(max_entries=10)
    cache.put("k", "v")
    assert cache.get("k", is_valid=lambda v: False) is None
    assert len(cache) == 0  # rejected entry is evicted, not left dangling


def test_is_valid_predicate_accepts_fresh_entry():
    cache = BoundedCache(max_entries=10)
    cache.put("k", "v")
    assert cache.get("k", is_valid=lambda v: True) == "v"


def test_bounded_eviction_lru_order():
    cache = BoundedCache(max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)  # evicts "a" (least recently used)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_get_promotes_entry_to_most_recently_used():
    cache = BoundedCache(max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")  # "a" now most-recently-used
    cache.put("c", 3)  # should evict "b", not "a"
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_max_entries_must_be_positive():
    with pytest.raises(ValueError):
        BoundedCache(max_entries=0)


def test_diagnostics_counts_hits_misses_evictions_puts():
    cache = BoundedCache(max_entries=1)
    cache.get("missing")  # miss
    cache.put("a", 1)  # put
    cache.get("a")  # hit
    cache.put("b", 2)  # put + eviction of "a"
    diag = cache.diagnostics()
    assert diag["misses"] == 1
    assert diag["hits"] == 1
    assert diag["puts"] == 2
    assert diag["evictions"] == 1
    assert diag["size"] == 1


def test_clear_resets_store_and_diagnostics():
    cache = BoundedCache(max_entries=10)
    cache.put("a", 1)
    cache.get("a")
    cache.clear()
    assert len(cache) == 0
    assert cache.diagnostics() == {"hits": 0, "misses": 0, "evictions": 0, "puts": 0, "size": 0}


def test_concurrent_put_get_does_not_corrupt_state():
    """Minimal concurrency smoke test -- not a proof of absence of races, but proves
    the lock prevents outright corruption (exceptions, lost entries) under
    contention, matching TD-6's 'minimum appropriate synchronization' scope."""
    cache = BoundedCache(max_entries=50)
    errors = []

    def worker(n):
        try:
            for i in range(200):
                cache.put(f"k{n}-{i}", i)
                cache.get(f"k{n}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(cache) <= 50


def test_cached_value_identity_not_accidentally_shared_mutation():
    """The cache stores whatever object it's given -- if that object is mutable and a
    caller mutates it after put(), get() will observe the mutation (this class makes
    no defensive copy itself; immutability/copy-on-read is the CALLER's contract, as
    documented and exercised by raw_candle_cache.py returning list(...) copies)."""
    cache = BoundedCache(max_entries=10)
    original = {"x": 1}
    cache.put("k", original)
    original["x"] = 2
    assert cache.get("k")["x"] == 2  # documents the actual (no-copy) contract
