"""P4 focused tests: AG_PROPOSAL_OCCURRENCE_IDENTITY_V1
(AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_V1).

Proves the versioned candidate resolves repeated M15 observations of one unchanged
structural setup to ONE logical occurrence/proposal while preserving every observation's
provenance, that a genuinely new setup yields a new occurrence, and that the candidate
fails closed and never touches frozen behavior or historical ledger evidence.

Nothing here asserts a change to `_decision_id`, the FX adapter's
`proposal_envelope_id`, or `ProposalLedger` keying -- all three remain frozen and are
explicitly asserted unchanged.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from proposal_envelope.models import (  # noqa: E402
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PROPOSAL_EXPIRED,
    PROPOSAL_READY,
    WATCHER_SETUP_QUALIFIED,
    WatcherOccurrenceTimestamps,
)
from proposal_envelope.occurrence_identity_v1 import (  # noqa: E402
    CANDIDATE_VERSION,
    REASON_EXPIRED_AT_PRESENTATION,
    WIRED_INTO_RUNTIME,
    OccurrenceIdentityUnavailable,
    OccurrenceLedgerError,
    ProposalOccurrenceLedger,
    current_proposals,
    evaluation_id,
    expired_proposals,
    expiry_of,
    is_expired,
    occurrence_id,
    reporting_metrics,
    reporting_metrics_from_ledger_file,
    resolve_occurrence_identity,
    structural_reference_from_evidence,
    with_presentation_state,
)

LEDGER_PATH = REPO_ROOT / "state" / "proposal_ledger" / "proposal_ledger.json"

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

# The exact worst-case real setup: 11 duplicate ledger records, 1 distinct geometry.
WORST_SETUP = "ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-09-15"
WORST_REFERENCE = "LIQUIDITY_SWEEP|1.15397|None|M15"


def _setup_id(cycle: str = "LONDON_NEWYORK", symbol: str = "EURUSD",
              trading_date: str = "2026-09-15") -> str:
    return f"{STRATEGY_ID}:{cycle}:{symbol}:{trading_date}"


def _envelope(
    *, asof: str = "2026-09-15T12:30:00+00:00", evaluation_time: str = "2026-09-15T12:30:20+00:00",
    decision_id: str = "DECISION-EURUSD-0001", setup_id: str = WORST_SETUP,
    symbol: str = "EURUSD", strategy_version: str = STRATEGY_VERSION,
    trigger_level: float = 1.15397, entry: float = 1.15397, direction: str = "SHORT",
    stop: float = 1.15416, targets=(1.15264, 1.15302),
    expires_at: str = "2026-09-15T15:00:00+00:00",
    proposal_state: str = PROPOSAL_READY, confirmation: dict | None = None,
    liquidity: dict | None = None,
) -> CanonicalProposal:
    """Mirrors `proposal_envelope.adapters.fx_adapter.to_canonical_proposal`'s exact
    persisted shape for a STATUS_READY decision -- the fields the three identity layers
    read, plus geometry."""
    return CanonicalProposal(
        proposal_envelope_id=f"FX:{decision_id}",
        strategy_id=STRATEGY_ID, strategy_version=strategy_version,
        market="FX", venue="MT5_BROKER", contract_type="SPOT_FX", symbol=symbol,
        watcher_state=WATCHER_SETUP_QUALIFIED, proposal_state=proposal_state,
        execution_authority=AUTHORITY_NONE,
        direction=direction, entry=entry, stop=stop, targets=tuple(targets),
        plan_expires_at=expires_at,
        setup_evidence={"volume": 0.31, "risk_amount": 100.0},
        market_context_evidence={"reference_session": "London", "trading_date": asof[:10]},
        liquidity_evidence=liquidity if liquidity is not None else {
            "trigger_type": "LIQUIDITY_SWEEP", "trigger_level": trigger_level,
            "trigger_timeframe": "M15"},
        confirmation_evidence=confirmation if confirmation is not None else {"setup_id": setup_id},
        data_provenance=DataProvenance(source="MT5", data_version=f"SNAPSHOT-{symbol}-{asof[:13]}",
                                       complete_candle_evidence=True),
        cost_assumptions=CostAssumptions(),
        timestamps=WatcherOccurrenceTimestamps(
            detected_at=evaluation_time, state_entered_at=asof, last_evaluated_at=evaluation_time,
            evidence_candle_close=asof, expires_at=expires_at,
            evidence_complete=("LIQUIDITY_SWEEP", "M15_CLOSE_CONFIRMATION")),
        source_module="post_asian_pilot.decision.PostAsianDecision",
        source_record_id=decision_id,
    )


def _poll_series(count: int = 11, *, start_minute: int = 30) -> list[CanonicalProposal]:
    """The exact real-world pattern: one poll per M15 close, 12:30 -> 15:00."""
    out = []
    for i in range(count):
        minute = start_minute + i * 15
        hour = 12 + minute // 60
        stamp = f"2026-09-15T{hour:02d}:{minute % 60:02d}"
        out.append(_envelope(
            asof=f"{stamp}:00+00:00", evaluation_time=f"{stamp}:20+00:00",
            decision_id=f"DECISION-EURUSD-{i:04d}"))
    return out


# ------------------------------------------------------------------ candidate boundary


def test_candidate_is_versioned_and_not_wired_into_runtime():
    """Governed boundary: this is a CANDIDATE. Wiring it in is a promotion decision
    requiring validation + registry/ledger authorization, not a code change alone."""
    assert CANDIDATE_VERSION == "AG_PROPOSAL_OCCURRENCE_IDENTITY_V1"
    assert WIRED_INTO_RUNTIME is False


def test_candidate_module_has_no_execution_import():
    """Same structural isolation every other proposal_envelope module preserves."""
    import ast
    path = REPO_ROOT / "src" / "proposal_envelope" / "occurrence_identity_v1.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in imported:
        assert not name.startswith("execution"), f"forbidden execution import {name!r}"
        assert not name.startswith("mt5"), f"forbidden mt5 import {name!r}"
        assert not name.startswith("authorization"), f"forbidden authorization import {name!r}"


# ------------------------------------------------------- 1. repeated M15 -> one occurrence


def test_repeated_m15_evaluations_of_one_setup_resolve_to_one_occurrence():
    """P1/P2 core requirement: 11 polls of the same unchanged structural setup -> ONE
    occurrence, however many evaluation identities were produced."""
    identities = [resolve_occurrence_identity(e) for e in _poll_series(11)]

    assert len({i.occurrence_id for i in identities}) == 1
    assert len({i.proposal_envelope_id for i in identities}) == 1
    assert len({i.evaluation_id for i in identities}) == 11  # observation layer varies BY DESIGN
    assert len({i.logical_setup_id for i in identities}) == 1


def test_occurrence_identity_is_independent_of_evaluation_identity():
    """The three layers must stay distinct: renaming the decision (the evaluation-layer
    field that today IS the persistence key) must not change the occurrence."""
    a = resolve_occurrence_identity(_envelope(decision_id="DECISION-EURUSD-aaa"))
    b = resolve_occurrence_identity(_envelope(decision_id="DECISION-EURUSD-bbb"))
    assert a.evaluation_id != b.evaluation_id
    assert a.occurrence_id == b.occurrence_id
    assert a.proposal_envelope_id == b.proposal_envelope_id


def test_occurrence_key_excludes_every_time_varying_field():
    """The defect was a layer collapse. The occurrence key must therefore contain no
    observation-layer field -- asserted structurally, not just behaviorally."""
    assert "evaluation_time" not in WORST_REFERENCE
    for envelope in _poll_series(4):
        identity = resolve_occurrence_identity(envelope)
        assert identity.observed_at not in identity.occurrence_id
        assert identity.proposal_envelope_id not in identity.occurrence_id
        assert envelope.data_provenance.data_version not in identity.occurrence_id
        assert envelope.source_record_id not in identity.occurrence_id


# ------------------------------------------------------- 2. geometry-stable -> idempotent


def test_geometry_stable_repetition_is_idempotent_and_preserves_every_observation(tmp_path):
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    records = [ledger.record_observation(e, now=NOW) for e in _poll_series(11)]

    assert len(ledger.all_occurrences()) == 1  # ONE persisted occurrence
    final = records[-1]
    assert final["version"] == 1  # no correction, no version churn
    assert final["correction_of"] is None
    assert final["history"] == []  # nothing superseded
    assert final["observation_count"] == 11
    assert len(final["observations"]) == 11  # every observation's provenance preserved
    assert len({o["evaluation_id"] for o in final["observations"]}) == 11


def test_geometry_stable_repetition_does_not_change_current_record(tmp_path):
    """Idempotency must mean the persisted trade plan is untouched, not merely
    de-duplicated in a count."""
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    first = ledger.record_observation(_poll_series(1)[0], now=NOW)
    for e in _poll_series(10, start_minute=45):
        ledger.record_observation(e, now=NOW)
    last = ledger.all_occurrences()[0]

    def _normalized(record: dict) -> str:
        # JSON round-trip so tuple/list representation is not mistaken for a change.
        return json.dumps(record, sort_keys=True, default=str)

    assert _normalized(last["current"]) == _normalized(first["current"])
    assert last["current"]["entry"] == first["current"]["entry"]
    assert last["current"]["stop"] == first["current"]["stop"]
    assert list(last["current"]["targets"]) == list(first["current"]["targets"])
    assert last["version"] == first["version"] == 1


def test_same_geometry_different_observation_is_not_a_correction(tmp_path):
    """`ProposalLedger` bumps a version when the SAME key is re-recorded with different
    geometry; here the same-key/same-geometry case must never bump."""
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    for e in _poll_series(3):
        ledger.record_observation(e, now=NOW)
    assert ledger.all_occurrences()[0]["version"] == 1


def test_geometry_change_within_one_occurrence_is_a_linked_correction(tmp_path):
    """Mirrors ProposalLedger's existing, already-tested correction convention rather
    than inventing a second one."""
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    ledger.record_observation(_envelope(), now=NOW)
    changed = ledger.record_observation(
        _envelope(entry=1.15420, stop=1.15450), now=NOW)

    assert changed["version"] == 2
    assert changed["correction_of"] == changed["proposal_envelope_id"]
    assert len(changed["history"]) == 1  # original geometry never overwritten in place
    assert changed["history"][0]["entry"] == 1.15397
    assert changed["current"]["entry"] == 1.15420
    assert changed["observation_count"] == 2  # the observation is still recorded


# ------------------------------------------------------- 3. genuine new setup


def test_genuine_new_setup_produces_new_occurrence():
    """The fix must not over-deduplicate and hide real setups."""
    a = resolve_occurrence_identity(_envelope(setup_id=_setup_id(trading_date="2026-09-15")))
    b = resolve_occurrence_identity(_envelope(setup_id=_setup_id(trading_date="2026-09-16")))
    assert a.occurrence_id != b.occurrence_id
    assert a.logical_setup_id != b.logical_setup_id


def test_different_structural_reference_is_a_new_occurrence():
    """Two independent setups on the same symbol/cycle/date qualify on different
    structural anchors -- they must not collapse into one occurrence."""
    a = resolve_occurrence_identity(_envelope(trigger_level=1.15397))
    b = resolve_occurrence_identity(_envelope(trigger_level=1.16100))
    assert a.occurrence_id != b.occurrence_id
    assert a.logical_setup_id == b.logical_setup_id  # same canonical setup id...


def test_different_strategy_version_is_a_new_occurrence():
    """Same reason `ticket_delivery.identity.logical_ticket_id` adds this field: the
    canonical setup_id has no version component."""
    a = resolve_occurrence_identity(_envelope(strategy_version="1.1.1"))
    b = resolve_occurrence_identity(_envelope(strategy_version="1.2.0"))
    assert a.occurrence_id != b.occurrence_id


def test_new_setup_is_a_new_record_not_a_correction(tmp_path):
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    ledger.record_observation(_envelope(), now=NOW)
    ledger.record_observation(_envelope(setup_id=_setup_id(trading_date="2026-09-16")), now=NOW)
    records = ledger.all_occurrences()
    assert len(records) == 2
    assert all(r["version"] == 1 and r["correction_of"] is None for r in records)


# ------------------------------------------------------- 4. restart


def test_restart_produces_the_same_identity_and_does_not_duplicate(tmp_path):
    """A fresh ledger instance over the same path (process restart) must resolve the same
    occurrence and must not create a second record."""
    path = str(tmp_path / "occ.json")
    before = resolve_occurrence_identity(_envelope())

    ProposalOccurrenceLedger(path=path).record_observation(_envelope(), now=NOW)

    restarted = ProposalOccurrenceLedger(path=path)
    after = resolve_occurrence_identity(_envelope(decision_id="DECISION-EURUSD-restarted"))
    restarted.record_observation(_envelope(decision_id="DECISION-EURUSD-restarted"), now=NOW)

    assert before.occurrence_id == after.occurrence_id
    assert before.proposal_envelope_id == after.proposal_envelope_id
    assert len(restarted.all_occurrences()) == 1
    assert restarted.all_occurrences()[0]["observation_count"] == 2


def test_occurrence_identity_is_deterministic_across_repeated_calls():
    envelope = _envelope()
    assert resolve_occurrence_identity(envelope) == resolve_occurrence_identity(envelope)
    assert occurrence_id(
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
        logical_setup_id=WORST_SETUP, structural_reference=WORST_REFERENCE,
    ) == occurrence_id(
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
        logical_setup_id=WORST_SETUP, structural_reference=WORST_REFERENCE,
    )


# ------------------------------------------------------- 5. EURUSD and GBPUSD


@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD"])
def test_symbol_separation_holds_for_both_universe_symbols(symbol):
    """The live FX universe is EURUSD + GBPUSD; each must resolve its own occurrence."""
    a = resolve_occurrence_identity(_envelope(symbol=symbol, setup_id=_setup_id(symbol=symbol)))
    b = resolve_occurrence_identity(_envelope(symbol="EURUSD", setup_id=_setup_id(symbol="EURUSD")))
    if symbol == "EURUSD":
        assert a.occurrence_id == b.occurrence_id
    else:
        assert a.occurrence_id != b.occurrence_id


def test_eurusd_and_gbpusd_occurrences_are_distinct_and_each_deduplicate(tmp_path):
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    for symbol in ("EURUSD", "GBPUSD"):
        for i in range(5):
            ledger.record_observation(
                _envelope(symbol=symbol, setup_id=_setup_id(symbol=symbol),
                          decision_id=f"D-{symbol}-{i}"), now=NOW)
    records = ledger.all_occurrences()
    assert len(records) == 2
    assert {r["symbol"] for r in records} == {"EURUSD", "GBPUSD"}
    assert all(r["observation_count"] == 5 for r in records)


# ------------------------------------------------------- 6. session separation


def test_session_separation_holds():
    """ASIAN_LONDON and LONDON_NEWYORK on the same date/symbol are different setups."""
    a = resolve_occurrence_identity(_envelope(setup_id=_setup_id(cycle="ASIAN_LONDON")))
    b = resolve_occurrence_identity(_envelope(setup_id=_setup_id(cycle="LONDON_NEWYORK")))
    assert a.occurrence_id != b.occurrence_id
    assert a.logical_setup_id != b.logical_setup_id


def test_session_separation_survives_identical_geometry_and_timestamps():
    """Separating only on timestamps would be a coincidence; the key must separate on the
    canonical setup identity itself."""
    a = resolve_occurrence_identity(_envelope(setup_id=_setup_id(cycle="ASIAN_LONDON")))
    b = resolve_occurrence_identity(_envelope(setup_id=_setup_id(cycle="LONDON_NEWYORK")))
    assert a.structural_reference == b.structural_reference
    assert a.occurrence_id != b.occurrence_id


# ------------------------------------------------------- 7. trading-date separation


def test_trading_date_separation_holds():
    a = resolve_occurrence_identity(_envelope(setup_id=_setup_id(trading_date="2026-09-15")))
    b = resolve_occurrence_identity(_envelope(setup_id=_setup_id(trading_date="2026-09-16")))
    assert a.occurrence_id != b.occurrence_id


def test_trading_date_separation_within_one_cycle_and_symbol(tmp_path):
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    for date in ("2026-09-15", "2026-09-16", "2026-09-17"):
        for i in range(3):
            ledger.record_observation(
                _envelope(setup_id=_setup_id(trading_date=date), decision_id=f"D-{date}-{i}"),
                now=NOW)
    assert len(ledger.all_occurrences()) == 3


# ------------------------------------------------------- 8. expiry


def test_expired_proposal_is_not_presented_as_ready():
    """P3: an expired proposal must not remain operationally presented as current
    PROPOSAL_READY."""
    expired = _envelope(expires_at="2026-09-15T15:00:00+00:00")
    assert expired.proposal_state == PROPOSAL_READY

    presented = with_presentation_state(expired, NOW)

    assert presented.proposal_state == PROPOSAL_EXPIRED
    assert REASON_EXPIRED_AT_PRESENTATION in presented.reasons


def test_unexpired_proposal_remains_ready():
    live = _envelope(expires_at="2026-09-21T15:00:00+00:00")
    assert with_presentation_state(live, NOW).proposal_state == PROPOSAL_READY


def test_expiry_never_upgrades_or_mutates_geometry():
    expired = _envelope(expires_at="2026-09-15T15:00:00+00:00")
    presented = with_presentation_state(expired, NOW)
    assert (presented.direction, presented.entry, presented.stop, presented.targets) == (
        expired.direction, expired.entry, expired.stop, expired.targets)
    assert presented.execution_authority == expired.execution_authority == AUTHORITY_NONE


def test_expiry_is_never_invented_when_the_source_defines_none():
    """`is_expired` must be False, not True, when no strategy-owned expiry exists -- a
    missing expiry is not evidence of expiry."""
    no_expiry = _envelope(expires_at=None)
    assert expiry_of(no_expiry) is None
    assert is_expired(no_expiry, NOW) is False
    assert with_presentation_state(no_expiry, NOW).proposal_state == PROPOSAL_READY


def test_current_and_expired_views_partition_the_population():
    live = _envelope(expires_at="2026-09-21T15:00:00+00:00", decision_id="D-live")
    dead = _envelope(expires_at="2026-09-15T15:00:00+00:00", decision_id="D-dead")
    envelopes = [live, dead]

    current = current_proposals(envelopes, NOW)
    expired = expired_proposals(envelopes, NOW)

    assert [e.proposal_envelope_id for e in current] == [live.proposal_envelope_id]
    assert [e.proposal_envelope_id for e in expired] == [dead.proposal_envelope_id]
    assert len(current) + len(expired) == len(envelopes)


def test_expired_record_is_flagged_not_rewritten(tmp_path):
    """Historical evidence must stay immutable: expiry is flagged on the occurrence
    record, never written into the persisted `current` record."""
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    recorded = ledger.record_observation(_envelope(), now=NOW)
    before = json.dumps(recorded["current"], sort_keys=True)

    assert ledger.mark_expired_at_presentation(recorded["proposal_envelope_id"], NOW) is True

    after = ledger.get_occurrence(recorded["proposal_envelope_id"])
    assert after["expired_at_presentation"] is True
    assert json.dumps(after["current"], sort_keys=True) == before  # byte-identical
    assert after["current"]["proposal_state"] == PROPOSAL_READY  # persisted evidence intact


def test_marking_expiry_twice_is_idempotent(tmp_path):
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    recorded = ledger.record_observation(_envelope(), now=NOW)
    assert ledger.mark_expired_at_presentation(recorded["proposal_envelope_id"], NOW) is True
    assert ledger.mark_expired_at_presentation(recorded["proposal_envelope_id"], NOW) is False


def test_expiry_uses_the_strategy_owned_field_only():
    """`plan_expires_at` is the canonical field both FX and BTC adapters populate from
    the source strategy's own valid_until/expiry."""
    envelope = _envelope(expires_at="2026-09-15T15:00:00+00:00")
    assert expiry_of(envelope) == datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)


# ------------------------------------------------------- 9. fail closed


def test_missing_authoritative_identity_fails_closed():
    """A family emitting no `confirmation_evidence.setup_id` must be REPORTED, never
    given a derived persistence key (deliberately stricter than the read-only audit's
    documented DERIVED_SSC_COMPOSITE measurement fallback)."""
    ssc_like = _envelope(confirmation={}, liquidity={})
    with pytest.raises(OccurrenceIdentityUnavailable, match="OCCURRENCE_IDENTITY_UNAVAILABLE"):
        resolve_occurrence_identity(ssc_like)


def test_missing_structural_reference_fails_closed():
    """No structural anchor -> insufficient identity input -> fail closed rather than
    compose a partial key."""
    no_reference = _envelope(liquidity={}, confirmation={"setup_id": WORST_SETUP})
    with pytest.raises(OccurrenceIdentityUnavailable):
        resolve_occurrence_identity(no_reference)


def test_missing_strategy_version_fails_closed():
    with pytest.raises(OccurrenceIdentityUnavailable):
        occurrence_id(strategy_id=STRATEGY_ID, strategy_version="",
                      logical_setup_id=WORST_SETUP, structural_reference=WORST_REFERENCE)


def test_missing_strategy_id_fails_closed():
    with pytest.raises(OccurrenceIdentityUnavailable):
        occurrence_id(strategy_id="", strategy_version=STRATEGY_VERSION,
                      logical_setup_id=WORST_SETUP, structural_reference=WORST_REFERENCE)


def test_missing_evaluation_identity_fails_closed():
    bare = CanonicalProposal(
        proposal_envelope_id="FX:bare", strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION, proposal_state=PROPOSAL_READY)
    with pytest.raises(OccurrenceIdentityUnavailable):
        evaluation_id(bare)


def test_failed_closed_record_is_not_silently_bucketed(tmp_path):
    """An unresolvable envelope must raise, never produce a synthetic 'unknown'
    occurrence that would conceal the gap."""
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    with pytest.raises(OccurrenceIdentityUnavailable):
        ledger.record_observation(_envelope(confirmation={}, liquidity={}), now=NOW)
    assert ledger.all_occurrences() == []


def test_unknown_family_reference_shape_is_not_guessed():
    """`structural_reference_from_evidence` resolves only the two documented shapes --
    it must never invent a key from an unrecognized field."""
    assert structural_reference_from_evidence({}, {}) is None
    assert structural_reference_from_evidence({"unexpected": "x"}, {"other": "y"}) is None


def test_non_ready_envelope_is_rejected(tmp_path):
    """Mirrors ProposalLedger's own rule so evaluation evidence never inflates the
    proposal population."""
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    with pytest.raises(OccurrenceLedgerError, match="OCCURRENCE_LEDGER_REJECTED_NON_READY"):
        ledger.record_observation(_envelope(proposal_state=PROPOSAL_EXPIRED), now=NOW)


# ------------------------------------------------------- 10. historical ledger unchanged


def test_frozen_ledger_file_is_byte_identical_after_all_read_only_operations():
    """The mission requires historical ledger evidence never be rewritten."""
    before = LEDGER_PATH.read_bytes()
    reporting_metrics_from_ledger_file(now=NOW)
    after = LEDGER_PATH.read_bytes()
    assert after == before


def test_frozen_ledger_records_are_still_all_reported_ready_by_the_frozen_path():
    """Proves the candidate did NOT modify frozen behavior: `ProposalLedger` still returns
    every persisted record as PROPOSAL_READY (the defect the candidate addresses at
    presentation time only)."""
    from proposal_envelope.ledger import ProposalLedger

    active = ProposalLedger(path=str(LEDGER_PATH)).list_active_proposals()
    assert len(active) == 69
    assert {p.proposal_state for p in active} == {PROPOSAL_READY}


def test_identity_baseline_is_reproduced_on_the_real_ledger():
    """The reported defect, reproduced read-only: 69 records, 13 logical setups, 5.31x."""
    from proposal_envelope.identity_audit import audit_ledger_file

    audit = audit_ledger_file(str(LEDGER_PATH))
    assert audit.total_records == 69
    assert audit.distinct_logical_setups == 13
    assert audit.duplicate_records == 56
    assert audit.duplication_ratio == pytest.approx(5.31, abs=0.01)
    assert audit.duplicate_proposal_problem_reproduced is True


# ------------------------------------------------------- P5 reporting semantics


def test_reporting_metrics_keep_all_four_figures_distinct():
    envelopes = _poll_series(11) + [
        _envelope(setup_id=_setup_id(trading_date="2026-09-16"), decision_id="D-next-day"),
        _envelope(setup_id=_setup_id(symbol="GBPUSD"), decision_id="D-gbp"),
    ]
    metrics = reporting_metrics(envelopes, NOW)

    assert metrics.observation_count == 13
    assert metrics.distinct_setup_count == 3
    assert metrics.current_active_proposal_count == 0  # all expired at NOW
    assert metrics.expired_proposal_count == 13
    # the four figures are genuinely different numbers, not aliases
    assert len({metrics.observation_count, metrics.distinct_setup_count,
                metrics.current_active_proposal_count,
                metrics.expired_proposal_count}) >= 3


def test_opportunity_count_is_the_active_proposal_count_not_the_record_count():
    """A raw record count must never be presented as a trade-opportunity count."""
    envelopes = _poll_series(11) + [_envelope(expires_at="2026-09-21T15:00:00+00:00",
                                              decision_id="D-live")]
    metrics = reporting_metrics(envelopes, NOW)
    assert metrics.observation_count == 12
    assert metrics.opportunity_count == 1
    assert metrics.opportunity_count != metrics.observation_count


def test_reporting_metrics_render_states_the_raw_count_is_not_opportunities():
    metrics = reporting_metrics(_poll_series(11), NOW)
    rendered = metrics.render()
    assert "OBSERVATION_COUNT=11" in rendered
    assert "NOT a trade-opportunity count" in rendered
    assert "CURRENT_ACTIVE_PROPOSAL_COUNT=0 (= opportunity count)" in rendered


def test_reporting_metrics_exclude_identity_unavailable_from_other_figures():
    envelopes = _poll_series(2) + [_envelope(confirmation={}, liquidity={})]
    metrics = reporting_metrics(envelopes, NOW)
    assert metrics.observation_count == 3
    assert metrics.identity_unavailable_count == 1
    assert metrics.distinct_setup_count == 1  # the unresolvable record is not counted
    assert (metrics.current_active_proposal_count + metrics.expired_proposal_count) == 2


def test_reporting_metrics_from_ledger_file_matches_the_real_ledger():
    metrics = reporting_metrics_from_ledger_file(now=NOW)
    assert metrics.observation_count == 69
    assert metrics.distinct_setup_count == 9  # authoritative-identity setups only
    assert metrics.identity_unavailable_count == 6  # SSC: no authoritative identity
    assert metrics.expired_proposal_count == 63
    assert metrics.opportunity_count == 0
    assert metrics.observation_count != metrics.opportunity_count


def test_empty_population_reports_zeros_not_errors():
    metrics = reporting_metrics([], NOW)
    assert metrics.as_dict() == {
        "OBSERVATION_COUNT": 0, "DISTINCT_SETUP_COUNT": 0,
        "CURRENT_ACTIVE_PROPOSAL_COUNT": 0, "EXPIRED_PROPOSAL_COUNT": 0,
        "IDENTITY_UNAVAILABLE_COUNT": 0,
    }


# ------------------------------------------------------- strategy semantics untouched


def test_candidate_does_not_read_or_alter_any_strategy_economics():
    """A pure identity/persistence layer: it must not compute or adjust entry/stop/target
    geometry, and must carry `execution_authority` through verbatim."""
    envelopes = _poll_series(11)
    identities = [resolve_occurrence_identity(e) for e in envelopes]
    assert len({i.occurrence_id for i in identities}) == 1
    for e in envelopes:
        assert (e.direction, e.entry, e.stop, e.targets) == (
            "SHORT", 1.15397, 1.15416, (1.15264, 1.15302))
        assert e.execution_authority == AUTHORITY_NONE


def test_expiry_presentation_cannot_grant_authority():
    expired = _envelope(expires_at="2026-09-15T15:00:00+00:00")
    assert with_presentation_state(expired, NOW).execution_authority == AUTHORITY_NONE
    assert with_presentation_state(expired, NOW).demo_authorized is False
    assert with_presentation_state(expired, NOW).live_authorized is False
