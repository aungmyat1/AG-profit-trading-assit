"""btc_sweep_research.costs -- new fee/slippage/funding cost model (spec section 23; no
prior fee/funding model existed anywhere in the repo, confirmed by grep before adding)."""
from __future__ import annotations

import datetime as dt

import pytest

from btc_sweep_research.costs import (
    DEFAULT_FEE_RATE,
    DEFAULT_SLIPPAGE_TICKS,
    estimate_costs,
    funding_timestamps_between,
)

UTC = dt.timezone.utc


def test_funding_timestamps_between_finds_all_boundaries_in_range():
    start = dt.datetime(2026, 1, 5, 23, 0, tzinfo=UTC)
    end = dt.datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
    boundaries = funding_timestamps_between(start, end)
    assert boundaries == [
        dt.datetime(2026, 1, 6, 0, 0, tzinfo=UTC),
        dt.datetime(2026, 1, 6, 8, 0, tzinfo=UTC),
    ]


def test_funding_timestamps_between_empty_when_no_crossing():
    start = dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC)
    end = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC)
    assert funding_timestamps_between(start, end) == []


def test_funding_timestamps_between_requires_utc_aware():
    with pytest.raises(ValueError):
        funding_timestamps_between(dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 2, tzinfo=UTC))


def test_estimate_costs_applies_funding_only_when_crossed():
    entry_time_no_cross = dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC)  # +8h -> 09:00, crosses 08:00
    result_cross = estimate_costs(
        entry_time=entry_time_no_cross, entry_price=41500.0, exit_price=41000.0,
        volume=0.01, tick_size=0.1,
    )
    assert result_cross.funding_crossings >= 1
    assert result_cross.funding_cost_estimate > 0

    entry_time_no_boundary = dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC)
    result_no_cross = estimate_costs(
        entry_time=entry_time_no_boundary, entry_price=41500.0, exit_price=41000.0,
        volume=0.01, tick_size=0.1, assumed_hold_hours=2.0,  # 01:00 -> 03:00, no boundary
    )
    assert result_no_cross.funding_crossings == 0
    assert result_no_cross.funding_cost_estimate == 0.0


def test_estimate_costs_fees_and_slippage_scale_with_volume():
    small = estimate_costs(
        entry_time=dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC), entry_price=41500.0, exit_price=41000.0,
        volume=0.01, tick_size=0.1, assumed_hold_hours=2.0,
    )
    large = estimate_costs(
        entry_time=dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC), entry_price=41500.0, exit_price=41000.0,
        volume=0.02, tick_size=0.1, assumed_hold_hours=2.0,
    )
    assert large.fees_estimate == pytest.approx(small.fees_estimate * 2)
    assert large.slippage_estimate == pytest.approx(small.slippage_estimate * 2)
    assert large.total_estimated_cost == pytest.approx(large.fees_estimate + large.slippage_estimate + large.funding_cost_estimate)


def test_estimate_costs_rejects_non_positive_volume():
    with pytest.raises(ValueError):
        estimate_costs(
            entry_time=dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC), entry_price=41500.0, exit_price=41000.0,
            volume=0.0, tick_size=0.1,
        )


def test_estimate_costs_uses_documented_defaults():
    result = estimate_costs(
        entry_time=dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC), entry_price=41500.0, exit_price=41000.0,
        volume=0.01, tick_size=0.1, assumed_hold_hours=2.0,
    )
    assert result.fee_rate_assumed == DEFAULT_FEE_RATE
    assert result.slippage_ticks_assumed == DEFAULT_SLIPPAGE_TICKS
    assert "not live-fetched" in result.source_note
