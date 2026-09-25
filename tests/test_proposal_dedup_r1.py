"""PANEL_PROPOSAL_DEDUP_R1: root-cause remediation of the known dedup regression
(tests/test_proposal_envelope_adapters.py::
test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover).

Root cause: proposal_envelope.adapters.fx_adapter.to_canonical_proposal()'s READY
branch built proposal_envelope_id (ProposalLedger's own dedup key) from
decision.decision_id, which post_asian_pilot.decision._decision_id() deliberately
hashes in evaluation_time -- a fresh value every scan/observation cycle, even for the
SAME still-open economic setup. The repository already has a stable, deterministic
economic-setup identity for this exact case -- trade_proposal.setup_id, itself
strategy_engine.engine's own `signal_id=f"{strategy_id}:{pair_id}:{symbol}:
{session_date}"`, unchanged through TradeIntent.signal_id -> TradeProposal.setup_id --
but the adapter was not using it as the proposal identity. The fix uses
trade_proposal.setup_id (not decision.decision_id) as the READY-path
proposal_envelope_id; decision.decision_id is preserved unchanged as
source_record_id (per-observation provenance, a separate field).

Every test here exercises the real proposal_envelope.ledger.ProposalLedger and
proposal_envelope.adapters.fx_adapter -- no test imports or can reach execution.executor,
execution.mt5_gateway, or any order_send-capable module.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone

from execution.adapter import TradeProposal
from post_asian_pilot.decision import PostAsianDecision, STATUS_READY

from proposal_envelope.adapters import fx_adapter
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import PROPOSAL_READY


def _decision(decision_id, strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="EURUSD",
              trading_date=date(2026, 9, 2), evaluation_seq=0):
    return PostAsianDecision(
        decision_id=decision_id, strategy_id=strategy_id, strategy_version="1.0.0",
        symbol=symbol, trading_date=trading_date, reference_session="ASIAN",
        status=STATUS_READY, reason_codes=("R1",),
        evaluation_time=datetime(2026, 9, 2, 9, 0, evaluation_seq, tzinfo=timezone.utc),
        ready_at=datetime(2026, 9, 2, 8, 30, evaluation_seq, tzinfo=timezone.utc),
        valid_until=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
    )


def _trade_proposal(setup_id, symbol="EURUSD", direction="LONG"):
    return TradeProposal(
        setup_id=setup_id, strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol=symbol,
        profile_id="FOREX", direction=direction, entry=1.16500, stop_loss=1.16400,
        tp1=1.16700, tp2=1.16900, volume=0.31, risk_amount=50.0, risk_percent=0.5,
    )


def _setup_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", pair_id="ASIAN_LONDON",
              symbol="EURUSD", trading_date=date(2026, 9, 2)):
    return f"{strategy_id}:{pair_id}:{symbol}:{trading_date.isoformat()}"


# ------------------------------------------------------------------- identity
def test_proposal_envelope_id_derived_from_stable_setup_id_not_decision_id():
    setup_id = _setup_id()
    decision = _decision(decision_id="DECISION-EURUSD-obs-1")
    trade_proposal = _trade_proposal(setup_id)
    envelope = fx_adapter.to_canonical_proposal(decision, trade_proposal)

    assert envelope.proposal_envelope_id == f"FX:{setup_id}:{decision.strategy_version}"
    assert envelope.proposal_envelope_id != f"FX:{decision.decision_id}"
    # decision_id -- per-observation provenance -- is preserved, not discarded.
    assert envelope.source_record_id == decision.decision_id


def test_repeated_observation_of_same_setup_yields_same_envelope_id():
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)
    ids = set()
    for seq in range(3):
        decision = _decision(decision_id=f"DECISION-EURUSD-obs-{seq}", evaluation_seq=seq)
        envelope = fx_adapter.to_canonical_proposal(decision, trade_proposal)
        ids.add(envelope.proposal_envelope_id)
    assert ids == {f"FX:{setup_id}:{decision.strategy_version}"}


# ------------------------------------------------------------------- P6/P7: admission
def test_admit_same_setup_twice_yields_one_canonical_proposal(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)

    for seq in range(2):
        decision = _decision(decision_id=f"DECISION-EURUSD-obs-{seq}", evaluation_seq=seq)
        ledger.record_proposal(fx_adapter.to_canonical_proposal(decision, trade_proposal))

    active = ledger.list_active_proposals()
    assert len(active) == 1
    assert active[0].proposal_state == PROPOSAL_READY
    assert active[0].proposal_envelope_id == f"FX:{setup_id}:{decision.strategy_version}"


def test_different_strategy_versions_of_same_setup_get_independent_envelope_ids(tmp_path):
    """Review finding: trade_proposal.setup_id alone (strategy_id:pair_id:symbol:date)
    does not vary with strategy_version, so two versions of the same strategy on the
    same pair/symbol/date must not collide on one proposal_envelope_id -- each must
    remain independently addressable and get its own owner decision."""
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)

    decision_v1 = _decision(decision_id="DECISION-EURUSD-v1", evaluation_seq=0)
    decision_v2 = PostAsianDecision(
        decision_id="DECISION-EURUSD-v2", strategy_id=decision_v1.strategy_id,
        strategy_version="1.1.0", symbol=decision_v1.symbol,
        trading_date=decision_v1.trading_date, reference_session="ASIAN",
        status=STATUS_READY, reason_codes=("R1",),
        evaluation_time=datetime(2026, 9, 2, 9, 0, 1, tzinfo=timezone.utc),
        ready_at=datetime(2026, 9, 2, 8, 30, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
    )

    envelope_v1 = fx_adapter.to_canonical_proposal(decision_v1, trade_proposal)
    envelope_v2 = fx_adapter.to_canonical_proposal(decision_v2, trade_proposal)
    assert envelope_v1.proposal_envelope_id != envelope_v2.proposal_envelope_id

    ledger.record_proposal(envelope_v1)
    ledger.record_proposal(envelope_v2)
    active = ledger.list_active_proposals()
    assert len(active) == 2
    assert {p.strategy_version for p in active} == {"1.0.0", "1.1.0"}


def test_admit_same_setup_three_times_yields_one_canonical_proposal(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)

    for seq in range(3):
        decision = _decision(decision_id=f"DECISION-EURUSD-obs-{seq}", evaluation_seq=seq)
        ledger.record_proposal(fx_adapter.to_canonical_proposal(decision, trade_proposal))

    active = [
        p for p in ledger.list_active_proposals()
        if p.proposal_state == PROPOSAL_READY and p.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
        and p.symbol == "EURUSD"
    ]
    assert len(active) == 1


def test_repeated_admission_returns_the_original_unchanged_not_a_mutation(tmp_path):
    """admit(P); admit(P); admit(P) is idempotent -- never mutates the original."""
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)
    decision = _decision(decision_id="DECISION-EURUSD-obs-0")
    envelope = fx_adapter.to_canonical_proposal(decision, trade_proposal)

    first = ledger.record_proposal(envelope)
    second = ledger.record_proposal(envelope)
    third = ledger.record_proposal(envelope)

    # Compared on dedup-relevant identity/economics fields, not full dataclass
    # equality: the ledger's own JSON round-trip does not restore every nested
    # dataclass's tuple-typed field (e.g. CostAssumptions.missing_fields comes
    # back as a list) -- a pre-existing serialization quirk unrelated to proposal
    # identity/dedup, out of this package's scope.
    for record in (first, second, third):
        assert record.proposal_envelope_id == envelope.proposal_envelope_id
        assert record.version == 1
        assert record.correction_of is None
        assert (record.direction, record.entry, record.stop, record.targets) == (
            envelope.direction, envelope.entry, envelope.stop, envelope.targets,
        )


# ------------------------------------------------------------------- P8: negative controls
def test_same_symbol_different_trading_date_remains_distinct(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    day1, day2 = date(2026, 9, 2), date(2026, 9, 3)

    for day in (day1, day2):
        setup_id = _setup_id(trading_date=day)
        decision = _decision(decision_id=f"DECISION-EURUSD-{day.isoformat()}", trading_date=day)
        ledger.record_proposal(fx_adapter.to_canonical_proposal(decision, _trade_proposal(setup_id)))

    assert len(ledger.list_active_proposals()) == 2


def test_same_date_different_strategy_remains_distinct(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    for strategy_id in ("ST_ASIAN_SWEEP_5R_V1", "ST_OTHER_STRATEGY_V1"):
        setup_id = _setup_id(strategy_id=strategy_id)
        decision = _decision(decision_id=f"DECISION-EURUSD-{strategy_id}", strategy_id=strategy_id)
        trade_proposal = TradeProposal(
            setup_id=setup_id, strategy_id=strategy_id, symbol="EURUSD", profile_id="FOREX",
            direction="LONG", entry=1.16500, stop_loss=1.16400, tp1=1.16700, tp2=1.16900,
            volume=0.31, risk_amount=50.0, risk_percent=0.5,
        )
        ledger.record_proposal(fx_adapter.to_canonical_proposal(decision, trade_proposal))

    assert len(ledger.list_active_proposals()) == 2


def test_same_date_different_setup_identity_remains_distinct(tmp_path):
    """Different pair_id (session pairing) under otherwise identical strategy/symbol/date
    is a genuinely distinct setup per strategy_engine's own signal_id convention."""
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    for pair_id in ("ASIAN_LONDON", "LONDON_NEWYORK"):
        setup_id = _setup_id(pair_id=pair_id)
        decision = _decision(decision_id=f"DECISION-EURUSD-{pair_id}")
        ledger.record_proposal(fx_adapter.to_canonical_proposal(decision, _trade_proposal(setup_id)))

    assert len(ledger.list_active_proposals()) == 2


def test_genuinely_separate_opportunity_different_symbol_remains_distinct(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    for symbol in ("EURUSD", "GBPUSD"):
        setup_id = _setup_id(symbol=symbol)
        decision = _decision(decision_id=f"DECISION-{symbol}-0", symbol=symbol)
        ledger.record_proposal(fx_adapter.to_canonical_proposal(decision, _trade_proposal(setup_id, symbol=symbol)))

    assert len(ledger.list_active_proposals()) == 2


# ------------------------------------------------------------------- P9: restart persistence
def test_dedup_survives_restart(tmp_path):
    path = str(tmp_path / "ledger.json")
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)

    ledger_one = ProposalLedger(path=path)
    decision_one = _decision(decision_id="DECISION-EURUSD-obs-0")
    ledger_one.record_proposal(fx_adapter.to_canonical_proposal(decision_one, trade_proposal))
    del ledger_one  # simulate process termination

    ledger_two = ProposalLedger(path=path)
    decision_two = _decision(decision_id="DECISION-EURUSD-obs-1", evaluation_seq=1)
    ledger_two.record_proposal(fx_adapter.to_canonical_proposal(decision_two, trade_proposal))

    assert len(ledger_two.list_active_proposals()) == 1


# ------------------------------------------------------------------- P10: concurrency
def test_concurrent_admission_of_same_setup_yields_one_canonical_proposal(tmp_path):
    """Two producer threads observing the SAME economic setup concurrently, sharing one
    ProposalLedger instance (JsonKeyValueStore's own per-path lock is this repository's
    existing concurrency guarantee -- see proposal_envelope/ledger.py docstring), must
    still converge on exactly one canonical proposal. This does not claim cross-process
    or distributed uniqueness -- only the same-process guarantee JsonKeyValueStore
    already provides."""
    path = str(tmp_path / "ledger.json")
    ledger = ProposalLedger(path=path)
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)
    envelopes = [
        fx_adapter.to_canonical_proposal(_decision(decision_id=f"DECISION-EURUSD-obs-{i}", evaluation_seq=i), trade_proposal)
        for i in range(8)
    ]

    barrier = threading.Barrier(len(envelopes))

    def _admit(envelope):
        barrier.wait(timeout=5)
        ledger.record_proposal(envelope)

    threads = [threading.Thread(target=_admit, args=(e,)) for e in envelopes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(ledger.list_active_proposals()) == 1


# ------------------------------------------------------------------- P12: owner-decision compatibility
def test_repeated_admission_after_owner_review_does_not_replace_the_reviewed_proposal(tmp_path):
    """A duplicate observation arriving AFTER the proposal has already been
    picked up/reviewed elsewhere (keyed by the same proposal_envelope_id) must not
    reset it, create a second version, or alter its economics -- record_proposal's
    own idempotent-return contract (identical geometry -> return the existing record
    unchanged) already guarantees this; this test proves it end-to-end through the
    adapter, not just the ledger in isolation."""
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    setup_id = _setup_id()
    trade_proposal = _trade_proposal(setup_id)
    decision = _decision(decision_id="DECISION-EURUSD-obs-0")
    envelope = fx_adapter.to_canonical_proposal(decision, trade_proposal)

    reviewed = ledger.record_proposal(envelope)
    assert reviewed.version == 1

    # A later re-observation of the SAME still-open setup (new decision_id, identical
    # trade_proposal/geometry) must not disturb the already-reviewed record.
    later_decision = _decision(decision_id="DECISION-EURUSD-obs-1", evaluation_seq=1)
    later_envelope = fx_adapter.to_canonical_proposal(later_decision, trade_proposal)
    result = ledger.record_proposal(later_envelope)

    # See test_repeated_admission_returns_the_original_unchanged_not_a_mutation for
    # why this compares dedup-relevant fields rather than full dataclass equality.
    assert result.proposal_envelope_id == reviewed.proposal_envelope_id
    assert result.version == 1
    assert result.correction_of is None
    assert (result.direction, result.entry, result.stop, result.targets) == (
        reviewed.direction, reviewed.entry, reviewed.stop, reviewed.targets,
    )
    assert len(ledger.list_active_proposals()) == 1
