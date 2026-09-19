"""TD-6, Layer B: tests for the derived-fact cache key builder and store. Proves the
semantic-collision-safety properties TD-5/TD-6 require, independent of any specific
authority (market_structure/liquidity/supply_demand) integration.
"""
from __future__ import annotations

import datetime as dt

import pytest

from shared_cache import derived_fact_cache as dfc

UTC = dt.timezone.utc
_BAR = dt.datetime(2026, 9, 18, 21, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_cache():
    dfc.clear_cache()
    yield
    dfc.clear_cache()


def _key(**overrides):
    base = dict(
        source_dataset_identity="LIVE_MT5", symbol="EURUSD", timeframe="H1", closed_bar_identity=_BAR.isoformat(),
        authority_definition_id="SMC_MARKET_STRUCTURE_V1", feature_version="0.0.27",
        parameters=(("swing_length", 5), ("close_break", True)),
    )
    base.update(overrides)
    return dfc.build_key(**base)


# --------------------------------------------------------------------------- 6. identical semantic request -> hit

def test_identical_semantic_request_hits():
    key = _key()
    dfc.put(key, "RESULT")
    assert dfc.get(_key()) == "RESULT"


# --------------------------------------------------------------------------- Collision A: same everything, different swing_length

def test_collision_a_different_swing_length_never_reuses():
    """Same symbol/timeframe/closed_bar, different semantic parameter (swing_length
    5 vs 50, e.g. single-tier analyzer.py vs tiers.py's EXTERNAL tier) -> different
    cache key, no reuse."""
    key_5 = _key(parameters=(("swing_length", 5), ("close_break", True)))
    key_50 = _key(parameters=(("swing_length", 50), ("close_break", True)))
    dfc.put(key_5, "SWING_LENGTH_5_RESULT")

    assert key_5 != key_50
    assert dfc.get(key_50) is None
    assert dfc.get(key_5) == "SWING_LENGTH_5_RESULT"


# --------------------------------------------------------------------------- Collision B: same everything, different authority_definition_id

def test_collision_b_different_authority_definition_id_never_reuses():
    """Same symbol/timeframe/closed_bar, different authority_definition_id (e.g. a
    hypothetical SSC-derived id vs SMC_MARKET_STRUCTURE_V1) -> different cache key,
    no reuse. This is the exact mechanism that prevents SSC/Sweep-Retest structure
    semantics from ever satisfying an SMC structure request via this cache."""
    key_smc = _key(authority_definition_id="SMC_MARKET_STRUCTURE_V1")
    key_other = _key(authority_definition_id="HYPOTHETICAL_OTHER_STRUCTURE_V1")
    dfc.put(key_smc, "SMC_RESULT")

    assert key_smc != key_other
    assert dfc.get(key_other) is None
    assert dfc.get(key_smc) == "SMC_RESULT"


# --------------------------------------------------------------------------- 7/8/9. other discriminators -> miss

def test_different_symbol_different_key():
    assert _key(symbol="EURUSD") != _key(symbol="GBPUSD")


def test_live_and_distinct_replay_datasets_never_share_key():
    live = _key(source_dataset_identity="LIVE_MT5")
    replay_a = _key(source_dataset_identity="REPLAY:dataset-A:sha256:a")
    replay_b = _key(source_dataset_identity="REPLAY:dataset-B:sha256:b")
    assert len({live, replay_a, replay_b}) == 3


def test_source_identity_is_required():
    with pytest.raises(ValueError):
        _key(source_dataset_identity="")


def test_different_timeframe_different_key():
    assert _key(timeframe="H1") != _key(timeframe="H4")


def test_different_closed_bar_identity_different_key():
    assert _key(closed_bar_identity=_BAR) != _key(closed_bar_identity=_BAR + dt.timedelta(hours=1))


def test_different_feature_version_different_key():
    assert _key(feature_version="0.0.27") != _key(feature_version="0.0.28")


def test_different_parameters_different_key():
    assert _key(parameters=(("swing_length", 5),)) != _key(parameters=(("swing_length", 6),))


def test_parameter_order_does_not_affect_key():
    """Order-independence: the same (name, value) pairs supplied in a different order
    must produce the SAME key (sorted internally), never a spurious miss."""
    key_a = _key(parameters=(("swing_length", 5), ("close_break", True)))
    key_b = _key(parameters=(("close_break", True), ("swing_length", 5)))
    assert key_a == key_b


# --------------------------------------------------------------------------- diagnostics

def test_diagnostics_accurate():
    key = _key()
    dfc.get(key)  # miss
    dfc.put(key, "R")
    dfc.get(key)  # hit
    diag = dfc.cache_diagnostics()
    assert diag["misses"] == 1
    assert diag["hits"] == 1
    assert diag["puts"] == 1
