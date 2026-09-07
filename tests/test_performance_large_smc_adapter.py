"""Tests for performance.adapters.large_smc_adapter against a fixture-populated
LargeSMCSetupLedger (no live MT5, no real historical dataset required)."""
from __future__ import annotations

import datetime as dt

from historical_replay.orchestrator import SetupLedgerRow
from large_smc_research.live_ledger import LargeSMCSetupLedger
from performance.adapters.large_smc_adapter import (
    load_large_smc_funnel_counts,
    load_large_smc_resolved_samples,
)
from performance.calculator import funnel_ratio
from performance.models import NOT_EVALUATED

_T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _row(setup_id, entry_condition, maneuver, final_state, terminal):
    return SetupLedgerRow(
        setup_id=setup_id, symbol="EURUSD", combination=f"{entry_condition}x{maneuver}",
        entry_condition=entry_condition, maneuver=maneuver, direction="LONG", reference_key="ref",
        first_seen_time=_T0, last_seen_time=_T0, final_state=final_state, terminal=terminal,
    )


def _populated_ledger(tmp_path):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    rows = (
        _row("s1", "E1", "M1", "SCANNING_CONTEXT", False),
        _row("s2", "E2", "M2", "WAITING_M5_ENTRY", False),
        _row("s3", "E3", "M3", "READY", False),
        _row("s4", "E1", "M2", "INVALIDATED", True),
        _row("s5", "E2", "M1", "EXPIRED", True),
    )
    ledger.upsert_many(rows)
    return ledger


def test_funnel_counts_reflect_current_row_states(tmp_path):
    ledger = _populated_ledger(tmp_path)
    counts = load_large_smc_funnel_counts(ledger)
    assert counts.total_rows == 5
    assert counts.e_qualified == 5  # every persisted row is at least E-qualified
    assert counts.m_engaged == 2  # WAITING_M5_ENTRY (s2), READY (s3) -- INVALIDATED/EXPIRED are not M-engaged states
    assert counts.entry_eligible == 2  # WAITING_M5_ENTRY, READY
    assert counts.trade_geometry_complete == 1  # READY only
    assert counts.resolved == 2  # the two terminal rows
    assert counts.invalidated == 1
    assert counts.expired == 1
    assert counts.by_entry_condition == {"E1": 2, "E2": 2, "E3": 1}
    assert counts.by_maneuver == {"M1": 2, "M2": 2, "M3": 1}


def test_funnel_ratios_from_counts(tmp_path):
    counts = load_large_smc_funnel_counts(_populated_ledger(tmp_path))
    assert funnel_ratio(counts.m_engaged, counts.e_qualified) == 2 / 5
    assert funnel_ratio(counts.trade_geometry_complete, counts.entry_eligible) == 0.5


def test_no_resolved_trade_samples_until_an_outcome_resolver_exists(tmp_path):
    ledger = _populated_ledger(tmp_path)
    samples = load_large_smc_resolved_samples(ledger)
    assert samples == []  # SetupLedgerRow carries no realized_R -- must not be fabricated


def test_empty_ledger_funnel_ratios_are_not_evaluated_not_zero(tmp_path):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "empty.json"))
    counts = load_large_smc_funnel_counts(ledger)
    assert funnel_ratio(counts.m_engaged, counts.e_qualified) == NOT_EVALUATED
