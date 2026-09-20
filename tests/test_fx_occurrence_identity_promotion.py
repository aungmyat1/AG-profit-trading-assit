"""P1-P4 promotion-readiness proof for `AG_PROPOSAL_OCCURRENCE_IDENTITY_V1` on the
operational `ST_ASIAN_SWEEP_5R_V1` FX proposal path
(AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_V1).

This file deliberately proves the identity chain END TO END through the REAL producers --
`strategy_engine.engine.evaluate()` -> `post_asian_pilot.decision` ->
`post_asian_pilot.proposal.build_entry_proposal()` ->
`post_asian_pilot.pipeline._form_canonical_proposal()` -> `proposal_envelope` -> ledger --
rather than by hand-building canonical proposals. A hand-built envelope could not prove
that `confirmation_evidence.setup_id` is structural, because the claim under test is
exactly about what the real producers emit.

Import order note: `market_intelligence` is imported first, deliberately -- see
tests/test_strategy_engine_canonical_observations.py's docstring for the pre-existing,
unrelated circular import this works around. Not fixed here (out of scope).
"""
from __future__ import annotations

import market_intelligence  # noqa: F401  -- import-order workaround only, see docstring

import dataclasses
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mt5.symbol_resolver import SymbolMeta  # noqa: E402
from strategy_engine.engine import evaluate as evaluate_strategy  # noqa: E402
from strategy_engine.loader import load_strategy  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

from post_asian_pilot.decision import (  # noqa: E402
    STATUS_READY,
    map_trade_signal_to_decision,
)
from post_asian_pilot.pipeline import _form_canonical_proposal  # noqa: E402
from post_asian_pilot.proposal import build_entry_proposal  # noqa: E402

from proposal_envelope.ledger import ProposalLedger  # noqa: E402
from proposal_envelope.models import PROPOSAL_READY  # noqa: E402
from proposal_envelope.occurrence_identity_v1 import (  # noqa: E402
    CANDIDATE_VERSION,
    CUTOVER_POLICY,
    LEDGER_GENERATION_LEGACY,
    LEDGER_GENERATION_V1,
    WIRED_INTO_RUNTIME,
    current_proposals_from_ledger_file,
    expired_proposals_from_ledger_file,
    generation_of,
    is_expired,
    occurrence_id,
    presentation_ready_count,
    presentation_ready_count_from_ledger_file,
    read_cutover_marker,
    reporting_metrics,
    reporting_metrics_from_ledger_file,
    resolve_occurrence_identity,
    structural_reference_from_evidence,
    with_presentation_state,
    write_cutover_marker,
)
from strategy_contract.market_snapshot import from_real_candle  # noqa: E402

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
LEDGER_PATH = REPO_ROOT / "state" / "proposal_ledger" / "proposal_ledger.json"
NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

DAY = dt.date(2026, 1, 5)
NEXT_DAY = dt.date(2026, 1, 6)

_SYMBOL_META = {
    "EURUSD": SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                         volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5),
    "GBPUSD": SymbolMeta(symbol="GBPUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                         volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5),
}


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


# --------------------------------------------------------------------------- real fixtures


def _candle(day: dt.date, hour: int, minute: int, o, h, l, c) -> Candle:
    return Candle(dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC), o, h, l, c)


def _range_session_candles(day: dt.date = DAY, base: float = 1.1000):
    """The repo's own real-config RANGE session fixture (2 bars, expected_bar_count=2),
    parameterized by `base` so a genuinely DIFFERENT structural setup can be produced."""
    return [
        _candle(day, 0, 0, base, base + 0.0050, base - 0.0050, base + 0.0010),
        _candle(day, 0, 15, base + 0.0010, base + 0.0040, base - 0.0040, base + 0.0005),
    ]


def _sweep_candle(day: dt.date = DAY, hour: int = 7, base: float = 1.1000) -> Candle:
    """Upper-liquidity sweep: wicks above the session high (base + 0.0050) and closes
    back below it -- the repo's own sweep fixture shape."""
    return _candle(day, hour, 0, base + 0.0005, base + 0.0060, base, base + 0.0048)


def _real_signal(*, pair_id: str = "ASIAN_LONDON", symbol: str = "EURUSD", day: dt.date = DAY,
                 base: float = 1.1000, sweep_hour: int = 7):
    """A genuine `TradeSignal` from the real, unmodified strategy engine."""
    signal = evaluate_strategy(
        strategy=load_strategy(STRATEGY_PATH), pair_id=pair_id, symbol=symbol, session_date=day,
        session_candles=_range_session_candles(day, base), expected_bar_count=2,
        post_session_candles=[_sweep_candle(day, sweep_hour, base)],
    )
    assert signal.status == "SIGNAL" and signal.setup == "SWEEP", (
        f"fixture must produce a real SIGNAL/SWEEP, got status={signal.status!r} setup={signal.setup!r}")
    return signal


def _real_envelope(*, pair_id: str = "ASIAN_LONDON", symbol: str = "EURUSD", day: dt.date = DAY,
                   base: float = 1.1000, sweep_hour: int = 7,
                   evaluation_time: dt.datetime = None, snapshot_id: str = "SNAP-1",
                   ledger_path: str | None = None):
    """Drives the REAL production chain and returns the canonical envelope that the real
    pipeline actually forms and persists -- no hand-built proposal anywhere.

    The ledger is written to an isolated temp directory (never the repository's
    `state/proposal_ledger/`), so these tests cannot perturb operational state."""
    signal = _real_signal(pair_id=pair_id, symbol=symbol, day=day, base=base, sweep_hour=sweep_hour)
    evaluation_time = evaluation_time or dt.datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)
    window_end = dt.datetime(day.year, day.month, day.day, 11, 0, tzinfo=UTC)

    decision = map_trade_signal_to_decision(signal, snapshot_id, evaluation_time, window_end)
    assert decision.status == STATUS_READY

    proposal_result = build_entry_proposal(
        decision, load_strategy(STRATEGY_PATH), equity=10_000.0,
        symbol_meta=_SYMBOL_META[symbol], risk_per_trade_pct=0.5,
        session_snapshot_id=snapshot_id,
    )
    assert proposal_result.status == "READY"
    actionable = dataclasses.replace(proposal_result.proposal, actionable=True)

    path = ledger_path or str(Path(tempfile.mkdtemp(prefix="ag_fx_occ_")) / "ledger.json")
    ledger = ProposalLedger(path=path)
    snapshot = from_real_candle(
        symbol, "M15", _candle(day, 8, 45, base + 0.0005, base + 0.0010, base, base + 0.0008))
    _form_canonical_proposal(decision, actionable, snapshot, ledger)

    active = ledger.list_active_proposals()
    assert len(active) == 1
    return active[0], signal, decision


# =========================================================== P1 — setup_id authority


def test_setup_id_producer_formula_contains_no_timestamp(strategy):
    """The authoritative producer's own formula: `signal_id` is built from strategy_id,
    pair_id, symbol and `session_date` -- a `date`, so it has no time component at all.
    This is the structural claim, proven at the producer rather than assumed."""
    signal = _real_signal()

    assert signal.signal_id == (
        f"{strategy.strategy_id}:{signal.pair_id}:{signal.symbol}:{signal.session_date.isoformat()}")
    assert signal.signal_id == "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-01-05"
    assert isinstance(signal.session_date, dt.date) and not isinstance(signal.session_date, dt.datetime)
    # no time-of-evaluation anywhere in the key
    for fragment in ("09:00", "T09", "2026-01-05T", "evaluation", "timestamp"):
        assert fragment not in signal.signal_id


def test_setup_id_flows_unchanged_producer_to_envelope():
    """Full trace: engine `signal_id` -> `TradeProposal.setup_id` ->
    `PostAsianEntryProposal.setup_id` -> `confirmation_evidence.setup_id`. Each hop is the
    SAME string, so the envelope's authoritative identity really is the producer's."""
    envelope, signal, decision = _real_envelope()

    assert envelope.confirmation_evidence["setup_id"] == signal.signal_id
    assert envelope.confirmation_evidence["setup_id"] == (
        "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-01-05")
    # ...and the envelope's OWN persistence key is observation-derived (the defect)
    assert envelope.proposal_envelope_id == f"FX:{decision.decision_id}"
    assert envelope.proposal_envelope_id != envelope.confirmation_evidence["setup_id"]


def test_setup_id_is_structural_not_an_evaluation_timestamp():
    """Adversarial: two different evaluation instants for the SAME signal must yield the
    same setup_id but different decision ids. If setup_id were timestamp-derived, the
    first assertion would fail."""
    signal = _real_signal()
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)

    early = map_trade_signal_to_decision(signal, "SNAP-A", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    late = map_trade_signal_to_decision(signal, "SNAP-B", dt.datetime(2026, 1, 5, 9, 45, tzinfo=UTC), window_end)

    assert early.decision_id != late.decision_id  # evaluation layer: varies
    assert early.signal.signal_id == late.signal.signal_id  # logical setup: stable


def test_structural_reference_is_the_swept_price_level_not_a_timestamp():
    envelope, signal, _ = _real_envelope()
    reference = structural_reference_from_evidence(envelope.liquidity_evidence, envelope.setup_evidence)

    assert reference == f"LIQUIDITY_SWEEP|{signal.entry}|None|M15"
    assert str(signal.entry) in reference
    # the reference is derived from the strategy's own swept entry level
    assert envelope.liquidity_evidence["trigger_level"] == signal.entry


def test_observation_layer_fields_are_present_and_do_vary():
    """Confirms the OBSERVATION layer genuinely exists and varies, so the parity tests
    below cannot pass merely because nothing varies."""
    first, _, _ = _real_envelope(evaluation_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), snapshot_id="SNAP-A")
    second, _, _ = _real_envelope(evaluation_time=dt.datetime(2026, 1, 5, 9, 45, tzinfo=UTC), snapshot_id="SNAP-B")

    assert first.proposal_envelope_id != second.proposal_envelope_id
    assert first.timestamps.detected_at != second.timestamps.detected_at
    assert first.data_provenance.data_version != second.data_provenance.data_version


# =========================================================== P1 — occurrence parity


def test_repeated_m15_observations_of_unchanged_setup_share_one_occurrence():
    """The core requirement: 8 polls of one unchanged setup -> ONE occurrence identity,
    while every observation keeps its own evaluation identity."""
    envelopes = []
    for i in range(8):
        minute = 30 + i * 15
        hour = 12 + minute // 60
        envelope, _, _ = _real_envelope(
            evaluation_time=dt.datetime(2026, 1, 5, hour, minute % 60, 20, tzinfo=UTC),
            snapshot_id=f"SNAP-{i:02d}")
        envelopes.append(envelope)

    identities = [resolve_occurrence_identity(e) for e in envelopes]

    assert len({i.occurrence_id for i in identities}) == 1
    assert len({i.proposal_envelope_id for i in identities}) == 1
    assert len({i.logical_setup_id for i in identities}) == 1
    # the observation layer genuinely varied across those 8 polls
    assert len({i.evaluation_id for i in identities}) == 8
    assert len({e.proposal_envelope_id for e in envelopes}) == 8


def test_changed_market_data_timestamp_only_does_not_change_occurrence():
    """Only the market-data timestamp/snapshot changes -> same occurrence."""
    a, _, _ = _real_envelope(evaluation_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), snapshot_id="SNAP-1")
    b, _, _ = _real_envelope(evaluation_time=dt.datetime(2026, 1, 5, 10, 30, tzinfo=UTC), snapshot_id="SNAP-2")

    assert a.data_provenance.data_version != b.data_provenance.data_version
    assert resolve_occurrence_identity(a).occurrence_id == resolve_occurrence_identity(b).occurrence_id


def test_restart_produces_the_same_occurrence_identity():
    """Recomputing from scratch (fresh engine load, fresh process state) yields identical
    ids -- the identity is a pure function, not process memory."""
    first, _, _ = _real_envelope()
    second, _, _ = _real_envelope()

    assert resolve_occurrence_identity(first) == resolve_occurrence_identity(second)
    assert resolve_occurrence_identity(first).occurrence_id == occurrence_id(
        strategy_id=first.strategy_id, strategy_version=first.strategy_version,
        logical_setup_id=first.confirmation_evidence["setup_id"],
        structural_reference=structural_reference_from_evidence(
            first.liquidity_evidence, first.setup_evidence),
    )


def test_eurusd_and_gbpusd_are_distinct_occurrences():
    eur, _, _ = _real_envelope(symbol="EURUSD")
    gbp, _, _ = _real_envelope(symbol="GBPUSD")

    assert eur.confirmation_evidence["setup_id"] != gbp.confirmation_evidence["setup_id"]
    assert resolve_occurrence_identity(eur).occurrence_id != resolve_occurrence_identity(gbp).occurrence_id


def test_asian_london_and_london_newyork_are_distinct_occurrences():
    asian, _, _ = _real_envelope(pair_id="ASIAN_LONDON", sweep_hour=7)
    ny, _, _ = _real_envelope(pair_id="LONDON_NEWYORK", sweep_hour=12)

    assert asian.confirmation_evidence["setup_id"] == "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-01-05"
    assert ny.confirmation_evidence["setup_id"] == "ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-01-05"
    assert resolve_occurrence_identity(asian).occurrence_id != resolve_occurrence_identity(ny).occurrence_id


def test_new_structural_setup_produces_a_new_occurrence():
    """A genuinely new setup (different swept structural level) must NOT collapse into
    the first occurrence, even on the same symbol/cycle/date."""
    original, _, _ = _real_envelope(base=1.1000)
    new_setup, _, _ = _real_envelope(base=1.2000)

    assert original.liquidity_evidence["trigger_level"] != new_setup.liquidity_evidence["trigger_level"]
    assert resolve_occurrence_identity(original).occurrence_id != resolve_occurrence_identity(new_setup).occurrence_id


def test_next_trading_date_produces_a_new_occurrence():
    today, _, _ = _real_envelope(day=DAY)
    tomorrow, _, _ = _real_envelope(day=NEXT_DAY)

    assert today.confirmation_evidence["setup_id"] != tomorrow.confirmation_evidence["setup_id"]
    assert resolve_occurrence_identity(today).occurrence_id != resolve_occurrence_identity(tomorrow).occurrence_id


def test_session_and_date_separation_survive_identical_geometry():
    """Separation must come from the canonical setup identity, not from a coincidental
    geometry difference."""
    asian, _, _ = _real_envelope(pair_id="ASIAN_LONDON", sweep_hour=7)
    ny, _, _ = _real_envelope(pair_id="LONDON_NEWYORK", sweep_hour=12)

    assert asian.entry == ny.entry and asian.stop == ny.stop
    assert structural_reference_from_evidence(
        asian.liquidity_evidence, asian.setup_evidence) == structural_reference_from_evidence(
        ny.liquidity_evidence, ny.setup_evidence)
    assert resolve_occurrence_identity(asian).occurrence_id != resolve_occurrence_identity(ny).occurrence_id


def test_occurrence_key_excludes_every_observation_layer_field():
    """Structural assertion, not just behavioral: the occurrence key must contain no
    observation-layer value."""
    envelope, _, _ = _real_envelope()
    identity = resolve_occurrence_identity(envelope)

    for observation_field in (
        envelope.proposal_envelope_id, envelope.source_record_id,
        envelope.data_provenance.data_version, envelope.timestamps.detected_at,
        envelope.timestamps.last_evaluated_at, str(envelope.timestamps.state_entered_at),
    ):
        if observation_field:
            assert observation_field not in identity.occurrence_id


def test_occurrence_ledger_deduplicates_real_repeated_polls(tmp_path):
    """Through the real chain: 6 polls -> 1 persisted occurrence with all 6 observations
    preserved."""
    from proposal_envelope.occurrence_identity_v1 import ProposalOccurrenceLedger

    path = str(tmp_path / "occ.json")
    ledger = ProposalOccurrenceLedger(path=path)
    for i in range(6):
        envelope, _, _ = _real_envelope(
            evaluation_time=dt.datetime(2026, 1, 5, 9, i * 5, tzinfo=UTC), snapshot_id=f"SNAP-{i}")
        ledger.record_observation(envelope, now=NOW)

    records = ledger.all_occurrences()
    assert len(records) == 1
    assert records[0]["observation_count"] == 6
    assert len(records[0]["observations"]) == 6
    assert len({o["evaluation_id"] for o in records[0]["observations"]}) == 6


# =========================================================== P2 — cutover design


def test_cutover_policy_is_forward_only_and_never_reattributes():
    assert CUTOVER_POLICY["legacy_treatment"] == "IMMUTABLE_RAW_OBSERVATION"
    assert CUTOVER_POLICY["v1_treatment"] == "OCCURRENCE_AWARE"
    assert CUTOVER_POLICY["retroactive_rewrite"] is False
    assert CUTOVER_POLICY["reattribution"] is False
    assert CUTOVER_POLICY["migration"] == "NONE"
    assert CUTOVER_POLICY["legacy_path"] != CUTOVER_POLICY["v1_path"]


def test_generation_marker_distinguishes_legacy_from_v1():
    """A reader can always tell which generation produced a record from the record."""
    legacy_like = {"proposal_envelope_id": "FX:DECISION-EURUSD-abc", "confirmation_evidence": {}}
    v1_like = {"schema_version": "AG_PROPOSAL_OCCURRENCE_LEDGER_V1"}

    assert generation_of(legacy_like) == LEDGER_GENERATION_LEGACY
    assert generation_of(v1_like) == LEDGER_GENERATION_V1


def test_v1_records_carry_their_generation_schema_marker(tmp_path):
    from proposal_envelope.occurrence_identity_v1 import ProposalOccurrenceLedger

    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    envelope, _, _ = _real_envelope()
    record = ledger.record_observation(envelope, now=NOW)

    assert generation_of(record) == LEDGER_GENERATION_V1
    assert record["schema_version"] == "AG_PROPOSAL_OCCURRENCE_LEDGER_V1"


def test_cutover_marker_round_trips_and_is_explicit(tmp_path):
    marker_path = str(tmp_path / "cutover.json")
    assert read_cutover_marker(marker_path) is None  # absent by default, never fabricated

    written = write_cutover_marker(cutover_at=NOW, path=marker_path, note="promotion test")

    assert written["cutover_at"] == NOW.isoformat()
    assert written["policy"]["migration"] == "NONE"
    reread = read_cutover_marker(marker_path)
    assert reread == written


def test_cutover_marker_write_does_not_touch_the_legacy_ledger(tmp_path):
    """The cutover marker is a separate file; recording it must leave the frozen ledger
    byte-identical."""
    before = LEDGER_PATH.read_bytes()
    write_cutover_marker(cutover_at=NOW, path=str(tmp_path / "cutover.json"))
    assert LEDGER_PATH.read_bytes() == before


def test_legacy_ledger_is_never_migrated_or_rewritten_by_any_candidate_api(tmp_path):
    """Every read-only and V1-writing API is exercised, then the frozen ledger is checked
    byte-identical. The V1 ledger is a SEPARATE path -- nothing writes into LEGACY."""
    from proposal_envelope.occurrence_identity_v1 import ProposalOccurrenceLedger

    before = LEDGER_PATH.read_bytes()

    reporting_metrics_from_ledger_file(now=NOW)
    current_proposals_from_ledger_file(now=NOW)
    expired_proposals_from_ledger_file(now=NOW)
    presentation_ready_count_from_ledger_file(now=NOW)
    write_cutover_marker(cutover_at=NOW, path=str(tmp_path / "cutover.json"))
    ledger = ProposalOccurrenceLedger(path=str(tmp_path / "occ.json"))
    envelope, _, _ = _real_envelope()
    ledger.record_observation(envelope, now=NOW)

    assert LEDGER_PATH.read_bytes() == before
    assert str(LEDGER_PATH) != str(tmp_path / "occ.json")


def test_legacy_records_are_all_read_as_raw_observations():
    """LEGACY records are read as immutable raw observations -- the frozen ledger is
    never re-keyed, and its own keying still reflects the observation-derived defect."""
    raw = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    records = [e["current"] for e in raw.values()]

    assert len(records) == 69
    assert all(generation_of(r) == LEDGER_GENERATION_LEGACY for r in records)

    fx = [r for r in records if r["proposal_envelope_id"].startswith("FX:DECISION-")]
    ssc = [r for r in records if r["proposal_envelope_id"].startswith("SSC:")]
    assert len(fx) == 63  # observation-derived FX keys -- the defect, preserved as evidence
    assert len(ssc) == 6
    assert len(fx) + len(ssc) == 69
    # the FX keys are observation-derived, never the structural setup id
    assert all(r["proposal_envelope_id"] != (r.get("confirmation_evidence") or {}).get("setup_id")
               for r in fx)


# =========================================================== P3 — expiry presentation


def test_expired_real_proposal_is_not_presented_as_ready():
    """A real, formed proposal whose strategy-owned expiry has passed must not be
    presented as currently actionable PROPOSAL_READY."""
    envelope, _, _ = _real_envelope()
    assert envelope.proposal_state == PROPOSAL_READY
    assert envelope.plan_expires_at is not None

    presented = with_presentation_state(envelope, NOW)

    assert presented.proposal_state == "PROPOSAL_EXPIRED"
    assert "EXPIRED_AT_PRESENTATION" in presented.reasons
    # economics untouched by the expiry check
    assert (presented.entry, presented.stop, presented.targets) == (
        envelope.entry, envelope.stop, envelope.targets)


def test_expiry_presentation_is_independent_of_persistence():
    """Presentation state is a read-time view -- the persisted envelope is unchanged."""
    envelope, _, _ = _real_envelope()
    before = json.dumps(dataclasses.asdict(envelope), sort_keys=True, default=str)

    with_presentation_state(envelope, NOW)

    assert json.dumps(dataclasses.asdict(envelope), sort_keys=True, default=str) == before


def test_no_expiry_is_invented_when_the_strategy_provides_none():
    """`ST_ASIAN_SWEEP_5R_V1` always supplies `valid_until`, so a genuine absence is
    simulated by clearing it -- the candidate must NOT invent an expiry."""
    envelope, _, _ = _real_envelope()
    no_expiry = dataclasses.replace(
        envelope, plan_expires_at=None,
        timestamps=dataclasses.replace(envelope.timestamps, expires_at=None))

    assert is_expired(no_expiry, NOW) is False
    assert with_presentation_state(no_expiry, NOW).proposal_state == PROPOSAL_READY


def test_operational_count_must_use_presentation_ready_not_raw_active_count():
    """The confirmed operational defect: the frozen count is 69 (all 'active') while the
    expiry-corrected count is 0. A status surface must report the latter."""
    from proposal_envelope.ledger import ProposalLedger

    raw_active = len(ProposalLedger(path=str(LEDGER_PATH)).list_active_proposals())
    corrected = presentation_ready_count_from_ledger_file(now=NOW)

    assert raw_active == 69  # frozen behavior, unchanged
    assert corrected == 0  # expiry-corrected truth
    assert raw_active != corrected


def test_current_and_expired_views_partition_the_real_ledger():
    current = current_proposals_from_ledger_file(now=NOW)
    expired = expired_proposals_from_ledger_file(now=NOW)

    assert len(current) == 0
    assert len(expired) == 63
    assert len(current) + len(expired) == 63  # 6 SSC records fail closed, counted separately


# =========================================================== P4 — metrics


def test_all_six_metrics_are_exposed_separately():
    metrics = reporting_metrics_from_ledger_file(now=NOW)
    rendered = metrics.render()

    for name in ("OBSERVATION_COUNT", "DISTINCT_AUTHORITATIVE_SETUP_COUNT",
                 "DISTINCT_OCCURRENCE_COUNT", "IDENTITY_UNAVAILABLE_COUNT",
                 "CURRENT_ACTIVE_PROPOSAL_COUNT", "EXPIRED_PROPOSAL_COUNT"):
        assert name in rendered
        assert name in metrics.as_dict()


def test_six_metrics_on_the_real_ledger_are_internally_consistent():
    metrics = reporting_metrics_from_ledger_file(now=NOW)

    assert metrics.observation_count == 69
    assert metrics.distinct_authoritative_setup_count == 9
    assert metrics.distinct_occurrence_count == 10
    assert metrics.identity_unavailable_count == 6
    assert metrics.expired_proposal_count == 63
    assert metrics.current_active_proposal_count == 0

    # every record is accounted for exactly once, across mutually exclusive buckets
    assert (metrics.current_active_proposal_count + metrics.expired_proposal_count
            + metrics.identity_unavailable_count) == metrics.observation_count


def test_observation_count_is_never_the_opportunity_count():
    metrics = reporting_metrics_from_ledger_file(now=NOW)
    assert metrics.opportunity_count == metrics.current_active_proposal_count
    assert metrics.opportunity_count != metrics.observation_count
    assert "NOT a trade-opportunity count" in metrics.render()


def test_metrics_are_not_aliases_of_each_other():
    """The six figures must be genuinely distinct computations, not one number relabelled."""
    metrics = reporting_metrics_from_ledger_file(now=NOW)
    assert len({metrics.observation_count, metrics.distinct_authoritative_setup_count,
                metrics.distinct_occurrence_count, metrics.expired_proposal_count}) == 4
    assert metrics.distinct_occurrence_count > metrics.distinct_authoritative_setup_count


def test_metrics_do_not_count_identity_unavailable_as_setups_or_occurrences():
    metrics = reporting_metrics_from_ledger_file(now=NOW)
    # 9 + 6 unavailable would be 15 if unavailable records were mis-counted as setups
    assert metrics.distinct_authoritative_setup_count == 9
    assert metrics.distinct_authoritative_setup_count != 15


# =========================================================== boundaries


def test_candidate_still_unwired_and_versioned():
    assert CANDIDATE_VERSION == "AG_PROPOSAL_OCCURRENCE_IDENTITY_V1"
    assert WIRED_INTO_RUNTIME is False


def test_frozen_fx_path_untouched_by_this_mission():
    """The frozen producer/adapter/ledger behavior this mission examined is unchanged:
    the FX envelope id is still observation-derived and the ledger still keys on it."""
    envelope, _, decision = _real_envelope()
    assert envelope.proposal_envelope_id == f"FX:{decision.decision_id}"
    assert envelope.execution_authority == "NONE"
    assert envelope.demo_authorized is False and envelope.live_authorized is False


def test_expiry_check_cannot_grant_authority():
    envelope, _, _ = _real_envelope()
    presented = with_presentation_state(envelope, NOW)
    assert presented.execution_authority == "NONE"
    assert presented.demo_authorized is False
    assert presented.live_authorized is False
