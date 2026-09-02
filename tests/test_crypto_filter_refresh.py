"""Tests for execution/crypto_filter_refresh.py: the refresh -> normalize -> revalidate ->
submit sequence, and that the sequence's ordering is actually enforced (not just
documented)."""
from __future__ import annotations

import pytest

from execution.crypto_filter_refresh import (
    QuantityBelowMinQty,
    StaleFilterCycleError,
    normalize_quantity,
    refresh_filters,
    revalidate,
    submit_step,
)
from execution.crypto_metadata import OfflineFixtureMetadataSource
from execution_runtime.binance_usdtm_feed import CANONICAL_SYMBOL, default_symbol_meta


def _source():
    return OfflineFixtureMetadataSource(default_symbol_meta())


def test_refresh_produces_a_fresh_cycle_id_each_call():
    r1 = refresh_filters(_source(), CANONICAL_SYMBOL)
    r2 = refresh_filters(_source(), CANONICAL_SYMBOL)
    assert r1.cycle_id != r2.cycle_id


def test_normalize_floors_to_step_size():
    refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    # step_size = 0.001 -- 0.0125 should floor to 0.012
    normalized = normalize_quantity(0.0125, refresh, cycle_id=refresh.cycle_id)
    assert normalized == pytest.approx(0.012)


def test_normalize_rejects_below_min_qty():
    refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    with pytest.raises(QuantityBelowMinQty):
        normalize_quantity(0.0001, refresh, cycle_id=refresh.cycle_id)


def test_normalize_with_wrong_cycle_id_raises_stale_error():
    """Proves the SEQUENCE is enforced: a caller cannot normalize against a filter set
    from a different (or fabricated) refresh cycle."""
    refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    with pytest.raises(StaleFilterCycleError):
        normalize_quantity(0.01, refresh, cycle_id="not-the-real-cycle-id")


def test_stale_cycle_from_an_earlier_refresh_is_rejected():
    old_refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    new_refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    # Using the OLD refresh's data but the NEW cycle_id (or vice versa) must fail --
    # normalization must be against the SAME cycle end-to-end.
    with pytest.raises(StaleFilterCycleError):
        normalize_quantity(0.01, old_refresh, cycle_id=new_refresh.cycle_id)


def test_revalidate_requires_matching_cycle_id_too():
    refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    normalized = normalize_quantity(0.01, refresh, cycle_id=refresh.cycle_id)
    assert revalidate(normalized, refresh, cycle_id=refresh.cycle_id) is True
    with pytest.raises(StaleFilterCycleError):
        revalidate(normalized, refresh, cycle_id="wrong-cycle")


def test_full_sequence_ends_in_not_implemented_never_a_real_send():
    refresh = refresh_filters(_source(), CANONICAL_SYMBOL)
    normalized = normalize_quantity(0.01, refresh, cycle_id=refresh.cycle_id)
    ok = revalidate(normalized, refresh, cycle_id=refresh.cycle_id)
    result = submit_step(ok)
    assert result.status == "NOT_IMPLEMENTED"
    assert result.reason_code == "CRYPTO_EXECUTION_NOT_IMPLEMENTED"


def test_submit_step_rejects_when_revalidation_failed():
    result = submit_step(False)
    assert result.status == "REJECTED"
    assert result.reason_code == "REVALIDATION_FAILED"
