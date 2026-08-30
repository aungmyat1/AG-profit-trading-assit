"""Unit tests for orchestrator.SetupLedger/FunnelTracker using synthetic
SMCConditionalEntryAnalysis snapshots (no real dataset needed -- fast). Locks in a real
bug found this session: SetupLedgerRow.entry_type/low/high/reference only populated at
READY, undercounting relative to FunnelTracker's ENTRY_ARRAY_CREATED (which counts array
formation regardless of whether READY is ever reached).
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from historical_replay.orchestrator import FunnelTracker, SetupLedger

UTC = dt.timezone.utc


def _analysis(state, entry_array="FVG", entry_price=1.1050, reference_level=1.1000):
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                          eligible_for_confirmation=True, reference_type="H1_POI", reference_level=reference_level)
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction="SHORT", confirmation_timeframe="M5",
                                       entry_array=entry_array, entry_price=entry_price, state=state)
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        e_conditions={"E1": EConditionResult(entry_condition="E1", symbol="EURUSD"), "E2": e2,
                      "E3": EConditionResult(entry_condition="E3", symbol="EURUSD")},
        m_maneuvers={"M1": (), "M2": (), "M3": ()}, combinations=(combo,),
    )


def test_ledger_records_entry_array_even_when_never_ready():
    """The exact bug: WAITING_M5_ENTRY means an entry array formed -- the ledger must
    reflect that, not wait for READY which may never come."""
    ledger = SetupLedger()
    ledger.observe(_analysis("WAITING_M5_ENTRY"), dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    rows = list(ledger.rows.values())
    assert len(rows) == 1
    assert rows[0].entry_type == "FVG"
    assert rows[0].entry_reference == 1.1050
    assert rows[0].ready_time is None  # never reached READY


def test_ledger_and_funnel_agree_on_entry_array_count():
    """FunnelTracker.ENTRY_ARRAY_CREATED and the ledger's own entry_type population must
    count the same setups -- this is the reconciliation this bug broke."""
    ledger, funnel = SetupLedger(), FunnelTracker()
    analysis = _analysis("WAITING_M5_ENTRY")
    ledger.observe(analysis, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    funnel.observe(analysis)

    ledger_arrays = sum(1 for r in ledger.rows.values() if r.entry_type not in (None, "NONE"))
    funnel_arrays = funnel.per_combination()["E2M1"]["ENTRY_ARRAY_CREATED"]
    assert ledger_arrays == funnel_arrays == 1


def test_funnel_does_not_misclassify_early_waiting_states_as_confirmed():
    """Regression for a real bug found via the Aug-Sep 2025 discovery run: composer
    copies combo.state = m.state directly, and M1/M3's own early state vocabulary
    includes WAITING_HTF_TOUCH ("no inducement candidate identified yet") and
    WAITING_H1_REACTION ("identified but not taken") in addition to
    WAITING_M5_CONFIRMATION. A blacklist that only excluded WAITING_M5_CONFIRMATION
    silently counted these early states as M_CONFIRMED."""
    for early_state in ("WAITING_HTF_TOUCH", "WAITING_H1_REACTION", "WAITING_M5_CONFIRMATION"):
        funnel = FunnelTracker()
        funnel.observe(_analysis(early_state))
        assert funnel.per_combination()["E2M1"]["M_CONFIRMED"] == 0, early_state

    for confirmed_state in ("WAITING_M5_ENTRY", "READY", "INVALIDATED"):
        funnel = FunnelTracker()
        funnel.observe(_analysis(confirmed_state))
        assert funnel.per_combination()["E2M1"]["M_CONFIRMED"] == 1, confirmed_state


def test_ledger_still_records_entry_fields_at_ready():
    ledger = SetupLedger()
    ledger.observe(_analysis("READY"), dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    row = next(iter(ledger.rows.values()))
    assert row.ready_time is not None
    assert row.entry_type == "FVG"
