"""Focused tests for WP8 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the persistent
proposal ledger's idempotency, restart-recovery, and correction-versioning invariants.
"""
from __future__ import annotations

import pytest

from proposal_envelope.models import CanonicalProposal, PROPOSAL_BLOCKED, PROPOSAL_NO_TRADE, PROPOSAL_READY
from proposal_envelope.ledger import ProposalLedger, ProposalLedgerError


def _ready(proposal_envelope_id="FX:DECISION-1", entry=1.0850, stop=1.0830, targets=(1.0900,), **overrides):
    base = dict(
        proposal_envelope_id=proposal_envelope_id, strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol="EURUSD", proposal_state=PROPOSAL_READY,
        direction="LONG", entry=entry, stop=stop, targets=targets,
    )
    base.update(overrides)
    return CanonicalProposal(**base)


def test_rejects_non_ready_envelope():
    ledger = ProposalLedger(path="")
    with pytest.raises(ProposalLedgerError):
        ledger.record_proposal(_ready(proposal_state=PROPOSAL_NO_TRADE))
    with pytest.raises(ProposalLedgerError):
        ledger.record_proposal(_ready(proposal_state=PROPOSAL_BLOCKED))


def test_first_record_is_stored_and_retrievable(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger = ProposalLedger(path=path)
    envelope = _ready()

    result = ledger.record_proposal(envelope)

    assert result.proposal_envelope_id == "FX:DECISION-1"
    fetched = ledger.get_proposal("FX:DECISION-1")
    assert fetched is not None
    assert fetched.entry == 1.0850
    assert fetched.stop == 1.0830
    assert fetched.targets == (1.0900,)


def test_rerun_same_event_is_idempotent_no_duplicate(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger = ProposalLedger(path=path)
    envelope = _ready()

    first = ledger.record_proposal(envelope)
    second = ledger.record_proposal(envelope)  # same identity, same geometry -- e.g. scheduler rerun

    assert first.version == second.version == 1
    assert len(ledger.list_active_proposals()) == 1


def test_scheduler_overlap_produces_one_logical_proposal(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger_a = ProposalLedger(path=path)
    ledger_b = ProposalLedger(path=path)  # simulates a second overlapping evaluation call
    envelope = _ready()

    ledger_a.record_proposal(envelope)
    ledger_b.record_proposal(envelope)

    assert len(ledger_a.list_active_proposals()) == 1


def test_restart_recovers_the_same_proposal(tmp_path):
    path = str(tmp_path / "ledger.json")
    envelope = _ready()
    ProposalLedger(path=path).record_proposal(envelope)

    # A fresh instance over the same path simulates a backend restart.
    recovered = ProposalLedger(path=path).get_proposal("FX:DECISION-1")

    assert recovered is not None
    assert recovered.entry == envelope.entry
    assert recovered.stop == envelope.stop
    assert recovered.targets == envelope.targets
    assert recovered.strategy_id == envelope.strategy_id


def test_different_geometry_same_identity_is_a_linked_correction_not_overwrite(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger = ProposalLedger(path=path)
    original = ledger.record_proposal(_ready(entry=1.0850, stop=1.0830, targets=(1.0900,)))
    corrected = ledger.record_proposal(_ready(entry=1.0855, stop=1.0830, targets=(1.0900,)))  # entry revised

    assert corrected.version == 2
    assert corrected.correction_of == original.proposal_envelope_id
    assert corrected.entry == 1.0855

    history = ledger.get_history("FX:DECISION-1")
    assert len(history) == 2
    assert history[0].entry == 1.0850  # original geometry preserved, never rewritten
    assert history[1].entry == 1.0855

    # get_proposal always returns the CURRENT (latest) version.
    assert ledger.get_proposal("FX:DECISION-1").entry == 1.0855


def test_distinct_occurrences_never_collide(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger = ProposalLedger(path=path)
    ledger.record_proposal(_ready(proposal_envelope_id="FX:DECISION-1"))
    ledger.record_proposal(_ready(proposal_envelope_id="FX:DECISION-2", entry=1.2000, stop=1.1980, targets=(1.2050,)))

    assert len(ledger.list_active_proposals()) == 2
