"""AG_EGSVF_V1 foundation tests.

Covers the invariants required by the AG_EGSVF_V1_EVIDENCE_BACKED_FOUNDATION task:
identity/evidence version-binding, evidence immutability, transition-specific gating,
authority separation, execution isolation, and the state-machine's fail-closed
behavior. Also exercises the three adapters against real repository evidence and the
ledger's discrepancy detector.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from validation_framework.adapters.btc_adapter import build_btc_record
from validation_framework.adapters.fx_adapter import build_fx_record
from validation_framework.adapters.large_smc_adapter import build_large_smc_record
from validation_framework.evaluator import (
    FOUNDATIONAL_INVARIANTS,
    evaluate_transition,
    get_cumulative_required_gates,
    required_gates_for,
)
from validation_framework.ledger import (
    build_ledger,
    detect_project_status_discrepancies,
    serialize_record,
    write_snapshot,
)
from validation_framework.models import (
    GateResult,
    GateStatus,
    LifecycleStage,
    StrategyIdentity,
    StrategyValidationRecord,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _gate(name, status, evaluated_at=None):
    return GateResult(
        gate_name=name,
        status=status,
        evidence_refs=("synthetic-fixture",),
        evaluated_at=evaluated_at or datetime.now(timezone.utc),
        evaluator_version="TEST",
    )


# ---------------------------------------------------------------------------
# Invariant 1 -- Identity: evidence belongs to exact (strategy_id, semantic_version).
# ---------------------------------------------------------------------------


def test_identity_key_distinguishes_versions():
    a = StrategyIdentity("ST_X", "1.0.0")
    b = StrategyIdentity("ST_X", "1.0.1")
    assert a.key() != b.key()
    assert a.key() == StrategyIdentity("ST_X", "1.0.0").key()


def test_same_strategy_same_version_evidence_associates():
    identity_a = StrategyIdentity("ST_X", "1.0.0")
    identity_b = StrategyIdentity("ST_X", "1.0.0")
    assert identity_a.key() == identity_b.key()


def test_different_semantic_version_evidence_cannot_silently_transfer():
    """Simulates a caller trying to attribute v1.0.0 evidence to v1.0.1: the identity
    keys must differ, so any evidence store keyed by identity.key() naturally rejects
    the silent transfer this task forbids."""
    v1 = StrategyIdentity("ST_X", "1.0.0")
    v2 = StrategyIdentity("ST_X", "1.0.1")
    evidence_store = {v1.key(): "evidence-for-v1"}
    assert evidence_store.get(v2.key()) is None


def test_fx_adapter_only_attributes_records_matching_its_own_semantic_version():
    """Real-evidence check: every outcome-resolution record the FX adapter actually
    cites must carry strategy_version == the adapter's own SEMANTIC_VERSION -- proves
    the version-filter in fx_adapter._read_outcome_records is not a no-op."""
    record = build_fx_record(repo_root=REPO_ROOT)
    historical = record.gates["HISTORICAL_REPLAY"]
    for ref in historical.evidence_refs:
        path = os.path.join(REPO_ROOT, ref)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["strategy_id"] == record.identity.strategy_id
        assert data["strategy_version"] == record.identity.semantic_version


# ---------------------------------------------------------------------------
# Invariant 2 -- Immutability: EGSVF cannot modify source evidence.
# ---------------------------------------------------------------------------


def test_adapters_do_not_mutate_source_evidence_files(tmp_path):
    """Copies the real outcome-resolution directory into a temp repo root, records a
    byte-for-byte snapshot, runs the FX adapter against it, and asserts nothing
    changed."""
    src_dir = os.path.join(REPO_ROOT, "artifacts", "outcome_resolution", "records")
    if not os.path.isdir(src_dir):
        pytest.skip("no outcome_resolution records present in this checkout")

    fixture_root = tmp_path / "repo"
    dest_dir = fixture_root / "artifacts" / "outcome_resolution" / "records"
    dest_dir.mkdir(parents=True)
    before = {}
    for name in os.listdir(src_dir):
        src_path = os.path.join(src_dir, name)
        if not os.path.isfile(src_path):
            continue
        with open(src_path, "rb") as fh:
            content = fh.read()
        (dest_dir / name).write_bytes(content)
        before[name] = content

    build_fx_record(repo_root=str(fixture_root))

    for name, content in before.items():
        after = (dest_dir / name).read_bytes()
        assert after == content, f"{name} was mutated by the adapter"


def test_write_snapshot_never_overwrites_existing_file(tmp_path):
    ledger = build_ledger([], repository_head="deadbeef", evaluated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    path1 = write_snapshot(ledger, out_dir=str(tmp_path))
    path2 = write_snapshot(ledger, out_dir=str(tmp_path))
    assert path1 != path2
    assert os.path.exists(path1)
    assert os.path.exists(path2)


# ---------------------------------------------------------------------------
# Invariant 3 -- Transition-specific gates: only gates required for the requested
# transition determine eligibility; a future/unrelated gate absent must not block an
# earlier transition.
# ---------------------------------------------------------------------------


def test_only_transition_specific_gates_are_required():
    gates = {
        "SPEC_FIDELITY": _gate("SPEC_FIDELITY", GateStatus.PASS),
        "DETERMINISM": _gate("DETERMINISM", GateStatus.PASS),
        "NO_LOOKAHEAD": _gate("NO_LOOKAHEAD", GateStatus.PASS),
        "HISTORICAL_REPLAY": _gate("HISTORICAL_REPLAY", GateStatus.PASS),
        # A later-stage gate is deliberately absent/irrelevant here.
    }
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, gates)
    assert result.eligible is True
    assert set(result.required_gates) == {"SPEC_FIDELITY", "DETERMINISM", "NO_LOOKAHEAD", "HISTORICAL_REPLAY"}


def test_future_gate_absence_does_not_block_earlier_transition():
    gates = {
        "SPEC_FIDELITY": _gate("SPEC_FIDELITY", GateStatus.PASS),
        "DETERMINISM": _gate("DETERMINISM", GateStatus.PASS),
        "NO_LOOKAHEAD": _gate("NO_LOOKAHEAD", GateStatus.PASS),
        "HISTORICAL_REPLAY": _gate("HISTORICAL_REPLAY", GateStatus.PASS),
    }
    # OOS_VALIDATION / FRICTION_STRESS_TEST (required much later) are absent entirely.
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, gates)
    assert result.eligible is True


def test_strategy_override_adds_but_never_removes_a_required_gate():
    overrides = {(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH): ("C10_STOP_POLICY",)}
    required = required_gates_for(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, overrides)
    assert "SPEC_FIDELITY" in required  # global default preserved
    assert "C10_STOP_POLICY" in required  # strategy-specific addition present


# ---------------------------------------------------------------------------
# Invariant 4 -- Authority separation: promotion eligibility cannot grant execution
# authority.
# ---------------------------------------------------------------------------


def _all_pass_gates(*names):
    return {name: _gate(name, GateStatus.PASS) for name in names}


def test_promotion_eligible_does_not_change_execution_authority_field():
    """Even a fully-eligible PromotionEvaluation is a separate object from
    StrategyValidationRecord.execution_authority -- evaluate_transition() has no way to
    write that field, and this test proves the record's authority field is left exactly
    as the caller set it regardless of eligibility. Under cumulative inheritance,
    reaching LIVE_AUTHORIZED requires every earlier stage's prerequisites too, not just
    OWNER_LIVE_SIGNATURE -- so the fixture supplies the full cumulative set."""
    gates = _all_pass_gates(
        "SPEC_FIDELITY", "DETERMINISM", "NO_LOOKAHEAD", "HISTORICAL_REPLAY",
        "NATURAL_CAMPAIGN_ACCRUAL",
        "SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST", "OOS_VALIDATION",
        "OWNER_PROMOTION_SIGNATURE", "RISK_INVARIANTS_AUDIT",
        "DEMO_SLIPPAGE_VERIFICATION", "IDEMPOTENCY_CHECK",
        "OWNER_LIVE_SIGNATURE",
    )
    result = evaluate_transition(LifecycleStage.LIVE_ELIGIBLE, LifecycleStage.LIVE_AUTHORIZED, gates)
    assert result.eligible is True

    record = StrategyValidationRecord(
        identity=StrategyIdentity("ST_X", "1.0.0"),
        lifecycle_stage=LifecycleStage.LIVE_ELIGIBLE,
        gates=gates,
        execution_capability="MT5_DEMO_AVAILABLE",
        execution_capability_evidence=(),
        execution_authority="SHADOW_PROPOSAL_ONLY",
        execution_authority_evidence=(),
        next_transition=LifecycleStage.LIVE_AUTHORIZED,
        promotion_eligible=result.eligible,
        promotion_blockers=(),
        last_updated=datetime.now(timezone.utc),
    )
    assert record.promotion_eligible is True
    assert record.execution_authority == "SHADOW_PROPOSAL_ONLY"  # unchanged by eligibility


def test_demo_eligible_without_explicit_authorization_is_not_demo_authorized():
    """Under cumulative inheritance, OPERATIONAL_SHADOW -> DEMO_ELIGIBLE requires the
    foundational four AND NATURAL_CAMPAIGN_ACCRUAL AND DEMO_ELIGIBLE's own three gates
    -- not just the latter, which is all the pre-hardening delta-only evaluator
    checked."""
    gates = _all_pass_gates(
        "SPEC_FIDELITY", "DETERMINISM", "NO_LOOKAHEAD", "HISTORICAL_REPLAY",
        "NATURAL_CAMPAIGN_ACCRUAL",
        "SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST", "OOS_VALIDATION",
    )
    result = evaluate_transition(LifecycleStage.OPERATIONAL_SHADOW, LifecycleStage.DEMO_ELIGIBLE, gates)
    assert result.eligible is True
    # Reaching DEMO_ELIGIBLE is not itself DEMO_AUTHORIZED -- that requires a further,
    # explicit transition with its own gates (OWNER_PROMOTION_SIGNATURE, etc.).
    next_result = evaluate_transition(LifecycleStage.DEMO_ELIGIBLE, LifecycleStage.DEMO_AUTHORIZED, {})
    assert next_result.eligible is False
    assert "OWNER_PROMOTION_SIGNATURE" in next_result.blocking_gates


def test_live_eligible_without_explicit_authorization_is_not_live_authorized():
    result = evaluate_transition(LifecycleStage.LIVE_ELIGIBLE, LifecycleStage.LIVE_AUTHORIZED, {})
    assert result.eligible is False
    assert "OWNER_LIVE_SIGNATURE" in result.blocking_gates


# ---------------------------------------------------------------------------
# Invariant 5 -- Execution isolation: broker capability cannot alter validation or
# authority.
# ---------------------------------------------------------------------------


def test_broker_capability_available_does_not_expand_research_only_authority():
    """BTC-shaped fixture: market-data capability is AVAILABLE, but authority stays
    RESEARCH_ONLY and no gate/evaluator path can change that from evidence alone."""
    record = build_btc_record(repo_root=REPO_ROOT)
    assert "MARKET_DATA_ONLY" in record.execution_capability
    assert record.execution_authority == "RESEARCH_ONLY"
    # Even if every discovered gate happened to PASS, execution_authority is a field the
    # adapter sets directly from registry evidence, never derived from gate status.
    assert all(isinstance(g, GateResult) for g in record.gates.values())


# ---------------------------------------------------------------------------
# State-machine tests (section 52).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [GateStatus.FAIL, GateStatus.PARTIAL, GateStatus.BLOCKED, GateStatus.UNSIGNED, GateStatus.NOT_VERIFIED],
)
def test_non_pass_required_gate_blocks_transition(status):
    gates = {
        "SPEC_FIDELITY": _gate("SPEC_FIDELITY", GateStatus.PASS),
        "DETERMINISM": _gate("DETERMINISM", GateStatus.PASS),
        "NO_LOOKAHEAD": _gate("NO_LOOKAHEAD", GateStatus.PASS),
        "HISTORICAL_REPLAY": _gate("HISTORICAL_REPLAY", status),
    }
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, gates)
    assert result.eligible is False
    assert "HISTORICAL_REPLAY" in result.blocking_gates


def test_missing_required_gate_blocks_transition():
    gates = {"SPEC_FIDELITY": _gate("SPEC_FIDELITY", GateStatus.PASS)}
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, gates)
    assert result.eligible is False
    assert "NO_LOOKAHEAD" in result.blocking_gates
    assert "MISSING_GATE:NO_LOOKAHEAD" in result.violations


def test_not_applicable_blocks_unless_explicitly_permitted():
    base_pass = _all_pass_gates(
        "SPEC_FIDELITY", "DETERMINISM", "NO_LOOKAHEAD", "HISTORICAL_REPLAY",
        "NATURAL_CAMPAIGN_ACCRUAL",
        "SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST",
    )
    na_gate = {"OOS_VALIDATION": _gate("OOS_VALIDATION", GateStatus.NOT_APPLICABLE)}

    blocked = evaluate_transition(
        LifecycleStage.OPERATIONAL_SHADOW, LifecycleStage.DEMO_ELIGIBLE, {**base_pass, **na_gate}
    )
    assert blocked.eligible is False
    assert "OOS_VALIDATION" in blocked.blocking_gates

    allowed = evaluate_transition(
        LifecycleStage.OPERATIONAL_SHADOW,
        LifecycleStage.DEMO_ELIGIBLE,
        {**base_pass, **na_gate},
        na_satisfies={(LifecycleStage.OPERATIONAL_SHADOW, LifecycleStage.DEMO_ELIGIBLE): ("OOS_VALIDATION",)},
    )
    assert allowed.eligible is True


def test_invalid_skipped_transition_rejected_by_default():
    gates = {name: _gate(name, GateStatus.PASS) for name in ("SPEC_FIDELITY", "DETERMINISM", "NO_LOOKAHEAD", "HISTORICAL_REPLAY", "OWNER_PROMOTION_SIGNATURE", "RISK_INVARIANTS_AUDIT")}
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.DEMO_AUTHORIZED, gates)
    assert result.eligible is False
    assert "NON_ADJACENT_TRANSITION_NOT_PERMITTED" in result.violations


def test_unknown_transition_pair_yields_no_requirements_but_is_still_adjacency_checked():
    # OFFLINE_RESEARCH -> OFFLINE_RESEARCH: not adjacent (same stage), must reject.
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.OFFLINE_RESEARCH, {})
    assert result.eligible is False
    assert "SOURCE_EQUALS_TARGET" in result.violations


# ---------------------------------------------------------------------------
# Adapter reconciliation tests against real repository evidence.
# ---------------------------------------------------------------------------


def test_fx_adapter_reconciles_against_registry_and_yaml():
    """Hardened expectation: FX is legacy-labeled OPERATIONAL_SHADOW, but cumulative
    inheritance re-checks FOUNDATIONAL_INVARIANTS and NATURAL_CAMPAIGN_ACCRUAL for its
    next transition too -- DETERMINISM/HISTORICAL_REPLAY (both PARTIAL) and
    NATURAL_CAMPAIGN_ACCRUAL (a gate FX has never computed) must all surface as
    blockers alongside the stage's own SHADOW_SERIES_COMPLETION/FRICTION_STRESS_TEST/
    OOS_VALIDATION -- none of the foundational ones may silently disappear."""
    record = build_fx_record(repo_root=REPO_ROOT)
    assert record.identity.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert record.identity.semantic_version == "1.1.1"
    assert record.lifecycle_stage == LifecycleStage.OPERATIONAL_SHADOW
    assert record.execution_authority == "SHADOW_PROPOSAL_ONLY"
    assert record.promotion_eligible is False
    assert set(record.promotion_blockers) == {
        "DETERMINISM",
        "HISTORICAL_REPLAY",
        "NATURAL_CAMPAIGN_ACCRUAL",
        "SHADOW_SERIES_COMPLETION",
        "FRICTION_STRESS_TEST",
        "OOS_VALIDATION",
    }
    assert "SPEC_FIDELITY" not in record.promotion_blockers  # PASS, correctly not blocking
    assert "NO_LOOKAHEAD" not in record.promotion_blockers  # PASS, correctly not blocking


def test_btc_adapter_reconciles_against_registry_and_yaml():
    """Hardened expectation: BTC's NO_LOOKAHEAD/HISTORICAL_REPLAY (NOT_VERIFIED) and
    DETERMINISM (PARTIAL) must block FORWARD_RESEARCH -> OPERATIONAL_SHADOW alongside
    NATURAL_CAMPAIGN_ACCRUAL -- campaign completion alone could never make this
    eligible while the foundational gates stay unproven."""
    record = build_btc_record(repo_root=REPO_ROOT)
    assert record.identity.strategy_id == "ST_LIQUIDITY_SWEEP_RETEST_V1"
    assert record.identity.semantic_version == "2.0.0"
    assert record.lifecycle_stage == LifecycleStage.FORWARD_RESEARCH
    assert record.execution_authority == "RESEARCH_ONLY"
    assert record.promotion_eligible is False
    assert set(record.promotion_blockers) == {
        "DETERMINISM",
        "NO_LOOKAHEAD",
        "HISTORICAL_REPLAY",
        "NATURAL_CAMPAIGN_ACCRUAL",
    }
    assert "SPEC_FIDELITY" not in record.promotion_blockers
    assert record.gates["NATURAL_CAMPAIGN_ACCRUAL"].details["observed_count"] == 0


def test_large_smc_adapter_reconciles_against_registry_and_yaml():
    """Hardened expectation: OFFLINE_RESEARCH -> FORWARD_RESEARCH requires only the
    foundational four plus this strategy's own C10_STOP_POLICY addition --
    FRICTION_STRESS_TEST/OOS_VALIDATION belong to a later transition (DEMO_ELIGIBLE)
    and must NOT appear here (this was the pre-hardening adapter's own over-blocking
    bug -- section 29's forbidden pattern)."""
    record = build_large_smc_record(repo_root=REPO_ROOT)
    assert record.identity.strategy_id == "ST_LARGE_SMC_V1"
    assert record.identity.semantic_version == "1.0.6"
    assert record.gates["C10_STOP_POLICY"].status == GateStatus.UNSIGNED
    assert record.execution_authority == "NONE"
    assert record.promotion_eligible is False
    assert set(record.promotion_blockers) == {"DETERMINISM", "C10_STOP_POLICY"}
    assert "FRICTION_STRESS_TEST" not in record.promotion_blockers  # belongs to a later transition
    assert "OOS_VALIDATION" not in record.promotion_blockers  # belongs to a later transition
    assert "SPEC_FIDELITY" not in record.promotion_blockers
    assert "NO_LOOKAHEAD" not in record.promotion_blockers
    assert "HISTORICAL_REPLAY" not in record.promotion_blockers


# ---------------------------------------------------------------------------
# Ledger + discrepancy detector.
# ---------------------------------------------------------------------------


def test_ledger_round_trips_serializable_json():
    records = [build_fx_record(repo_root=REPO_ROOT), build_btc_record(repo_root=REPO_ROOT), build_large_smc_record(repo_root=REPO_ROOT)]
    ledger = build_ledger(records, repository_head="testhead")
    # Must be JSON-serializable with no custom encoder.
    text = json.dumps(ledger)
    reloaded = json.loads(text)
    assert len(reloaded["strategies"]) == 3


def test_discrepancy_detector_reports_consistent_when_counters_match():
    records = [build_fx_record(repo_root=REPO_ROOT), build_btc_record(repo_root=REPO_ROOT)]
    ledger = build_ledger(records, repository_head="testhead")
    status_text = "BTC: 0/30 observations. valid_days = 0/20, invalid_days = 1"
    findings = detect_project_status_discrepancies(ledger, status_text)
    assert findings, "expected at least one comparison to run"
    for f in findings:
        assert f["classification"] == "CONSISTENT"


def test_discrepancy_detector_flags_stale_documentation():
    records = [build_btc_record(repo_root=REPO_ROOT)]
    ledger = build_ledger(records, repository_head="testhead")
    stale_status_text = "BTC campaign progress: 0/30 observations recorded."
    # Simulate primary evidence having moved ahead of documentation.
    ledger["strategies"][0]["gate_results"]["NATURAL_CAMPAIGN_ACCRUAL"]["details"]["observed_count"] = 3
    findings = detect_project_status_discrepancies(ledger, stale_status_text)
    btc_finding = next(f for f in findings if f["field"] == "BTC_FORWARD_OBSERVATION_COUNT")
    assert btc_finding["classification"] == "PROJECT_STATUS_STALE"


# ---------------------------------------------------------------------------
# AG_EGSVF_V1_PROMOTION_INVARIANT_HARDENING regressions.
#
# Root defect (confirmed by inspection before any edit): promotion_eligible/
# promotion_blockers were computed independently inside each adapter -- a hand-picked
# subset of "this stage's own" gate names -- and evaluator.evaluate_transition() was
# never called from adapter/ledger code at all (only from tests). That let foundational
# gates (SPEC_FIDELITY/DETERMINISM/NO_LOOKAHEAD/HISTORICAL_REPLAY) silently drop out of
# the blocker list for any strategy already legacy-labeled past OFFLINE_RESEARCH, and
# let Large-SMC's adapter over-block on FRICTION_STRESS_TEST/OOS_VALIDATION -- gates
# that belong to a transition it isn't even being evaluated against. These tests prove
# the fix: cumulative stage-prerequisite inheritance, with evaluate_transition() as the
# sole source of promotion_eligible/promotion_blockers everywhere in the framework.
# ---------------------------------------------------------------------------


def test_cumulative_required_gates_grow_monotonically_through_the_lifecycle():
    forward = set(get_cumulative_required_gates(LifecycleStage.FORWARD_RESEARCH))
    shadow = set(get_cumulative_required_gates(LifecycleStage.OPERATIONAL_SHADOW))
    demo_eligible = set(get_cumulative_required_gates(LifecycleStage.DEMO_ELIGIBLE))

    assert forward == set(FOUNDATIONAL_INVARIANTS)
    assert forward.issubset(shadow)
    assert shadow.issubset(demo_eligible)
    assert shadow - forward == {"NATURAL_CAMPAIGN_ACCRUAL"}
    assert demo_eligible - shadow == {"SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST", "OOS_VALIDATION"}


def test_large_smc_blocker_includes_determinism():
    """Mandatory regression (AGENT PROMPT section 20). Large-SMC's real evidence has
    DETERMINISM=PARTIAL, SPEC_FIDELITY/NO_LOOKAHEAD/HISTORICAL_REPLAY=PASS, and its own
    additive C10_STOP_POLICY=UNSIGNED for OFFLINE_RESEARCH -> FORWARD_RESEARCH.
    DETERMINISM must remain a blocker -- it cannot disappear just because Large-SMC's
    current stage label is OFFLINE_RESEARCH (the very first stage)."""
    record = build_large_smc_record(repo_root=REPO_ROOT)
    assert record.promotion_eligible is False
    assert "DETERMINISM" in record.promotion_blockers
    assert "C10_STOP_POLICY" in record.promotion_blockers


def test_btc_cumulative_block_at_operational_shadow():
    """Mandatory regression (AGENT PROMPT section 21). Even with NATURAL_CAMPAIGN_
    ACCRUAL forced to PASS (simulating campaign completion), NO_LOOKAHEAD and
    HISTORICAL_REPLAY (both real-evidence NOT_VERIFIED for BTC) and DETERMINISM
    (PARTIAL) must still block FORWARD_RESEARCH -> OPERATIONAL_SHADOW. Campaign
    completion alone can never erase a foundational deficiency."""
    gates = {
        "SPEC_FIDELITY": _gate("SPEC_FIDELITY", GateStatus.PASS),
        "DETERMINISM": _gate("DETERMINISM", GateStatus.PARTIAL),
        "NO_LOOKAHEAD": _gate("NO_LOOKAHEAD", GateStatus.NOT_VERIFIED),
        "HISTORICAL_REPLAY": _gate("HISTORICAL_REPLAY", GateStatus.NOT_VERIFIED),
        "NATURAL_CAMPAIGN_ACCRUAL": _gate("NATURAL_CAMPAIGN_ACCRUAL", GateStatus.PASS),
    }
    result = evaluate_transition(LifecycleStage.FORWARD_RESEARCH, LifecycleStage.OPERATIONAL_SHADOW, gates)
    assert result.eligible is False
    assert "NO_LOOKAHEAD" in result.blocking_gates
    assert "HISTORICAL_REPLAY" in result.blocking_gates
    assert "DETERMINISM" in result.blocking_gates
    assert "NATURAL_CAMPAIGN_ACCRUAL" not in result.blocking_gates  # forced PASS, correctly satisfied


def test_fx_cumulative_block_at_demo_eligible():
    """Mandatory regression (AGENT PROMPT section 22). Even with the stage's own three
    gates (SHADOW_SERIES_COMPLETION/FRICTION_STRESS_TEST/OOS_VALIDATION) and
    NATURAL_CAMPAIGN_ACCRUAL forced to PASS, DETERMINISM=PARTIAL must still block
    OPERATIONAL_SHADOW -> DEMO_ELIGIBLE."""
    gates = _all_pass_gates(
        "SPEC_FIDELITY", "NO_LOOKAHEAD",
        "NATURAL_CAMPAIGN_ACCRUAL", "SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST", "OOS_VALIDATION",
    )
    gates["DETERMINISM"] = _gate("DETERMINISM", GateStatus.PARTIAL)
    gates["HISTORICAL_REPLAY"] = _gate("HISTORICAL_REPLAY", GateStatus.PARTIAL)
    result = evaluate_transition(LifecycleStage.OPERATIONAL_SHADOW, LifecycleStage.DEMO_ELIGIBLE, gates)
    assert result.eligible is False
    assert "DETERMINISM" in result.blocking_gates
    assert "HISTORICAL_REPLAY" in result.blocking_gates
    assert "SHADOW_SERIES_COMPLETION" not in result.blocking_gates  # forced PASS, correctly satisfied


def test_ledger_blockers_exactly_match_evaluator():
    """Mandatory regression (AGENT PROMPT section 23): ledger.promotion_eligible /
    promotion_blockers must be exactly the evaluator's own eligible/blocking_gates for
    every adapter-built record -- no extra blocker, no missing blocker, no reordering
    into a different set. Large-SMC's own strategy-specific override
    (C10_STOP_POLICY) must be supplied here too, since it is a legitimate additive
    requirement the adapter itself registers with the evaluator -- reusing it in the
    independent re-evaluation (rather than omitting it) is what proves the adapter
    passed the evaluator's exact result through unchanged, not a different subset."""
    from validation_framework.adapters.large_smc_adapter import STRATEGY_TRANSITION_OVERRIDES

    builds_and_overrides = (
        (build_fx_record, None),
        (build_btc_record, None),
        (build_large_smc_record, STRATEGY_TRANSITION_OVERRIDES),
    )
    for build, overrides in builds_and_overrides:
        record = build(repo_root=REPO_ROOT)
        evaluation = evaluate_transition(
            record.lifecycle_stage, record.next_transition, record.gates, strategy_overrides=overrides
        )

        ledger = build_ledger([record], repository_head="testhead")
        ledger_entry = ledger["strategies"][0]

        assert ledger_entry["promotion_eligible"] == evaluation.eligible
        assert tuple(ledger_entry["promotion_blockers"]) == evaluation.blocking_gates
        # And the record itself (what the ledger serialized from) must already equal
        # the evaluator's output -- proving the adapter did not invent a second answer.
        assert record.promotion_eligible == evaluation.eligible
        assert record.promotion_blockers == evaluation.blocking_gates


def test_future_stage_gate_does_not_block_earlier_transition():
    """Cumulative must not mean 'every gate in the entire lifecycle.' OFFLINE_RESEARCH
    -> FORWARD_RESEARCH must never require FRICTION_STRESS_TEST, OOS_VALIDATION, or
    OWNER_LIVE_SIGNATURE -- those belong to much later stages."""
    required = get_cumulative_required_gates(LifecycleStage.FORWARD_RESEARCH)
    assert "FRICTION_STRESS_TEST" not in required
    assert "OOS_VALIDATION" not in required
    assert "OWNER_LIVE_SIGNATURE" not in required
    assert "NATURAL_CAMPAIGN_ACCRUAL" not in required

    gates = _all_pass_gates("SPEC_FIDELITY", "DETERMINISM", "NO_LOOKAHEAD", "HISTORICAL_REPLAY")
    result = evaluate_transition(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, gates)
    assert result.eligible is True


def test_strategy_override_can_add_but_not_remove_foundational_gate():
    """A strategy override that tries to omit a foundational gate has no mechanism to do
    so: required_gates_for only ever unions the override on top of the cumulative base,
    it never subtracts. Simulate a hypothetical "remove DETERMINISM" attempt by an
    override that just doesn't mention it -- DETERMINISM must still be present because
    it was never the override's to remove."""
    overrides = {(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH): ("C10_STOP_POLICY",)}
    required = required_gates_for(LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH, overrides)
    for foundational_gate in FOUNDATIONAL_INVARIANTS:
        assert foundational_gate in required
    assert "C10_STOP_POLICY" in required


def test_legacy_stage_assignment_does_not_imply_prior_gate_pass():
    """Mandatory regression (AGENT PROMPT section 8/27). A strategy record whose
    lifecycle_stage is already OPERATIONAL_SHADOW (assigned before AG-EGSVF existed)
    must not be treated as having proven FORWARD_RESEARCH's own entry gates. Evaluating
    its next transition with only the OPERATIONAL_SHADOW-labeled stage's "own" gates
    supplied (foundational gates deliberately withheld, as a legacy record would have
    none recorded) must still block on the foundational gates, not silently pass them."""
    gates = _all_pass_gates("NATURAL_CAMPAIGN_ACCRUAL", "SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST", "OOS_VALIDATION")
    record = StrategyValidationRecord(
        identity=StrategyIdentity("ST_LEGACY", "1.0.0"),
        lifecycle_stage=LifecycleStage.OPERATIONAL_SHADOW,  # legacy, pre-EGSVF label
        gates=gates,  # no SPEC_FIDELITY/DETERMINISM/NO_LOOKAHEAD/HISTORICAL_REPLAY recorded
        execution_capability="NONE",
        execution_capability_evidence=(),
        execution_authority="RESEARCH_ONLY",
        execution_authority_evidence=(),
        next_transition=LifecycleStage.DEMO_ELIGIBLE,
        promotion_eligible=False,
        promotion_blockers=(),
        last_updated=datetime.now(timezone.utc),
        details={"stage_assignment_provenance": "LEGACY_PRE_EGSVF"},
    )
    evaluation = evaluate_transition(record.lifecycle_stage, record.next_transition, record.gates)
    assert evaluation.eligible is False
    for foundational_gate in FOUNDATIONAL_INVARIANTS:
        assert foundational_gate in evaluation.blocking_gates
        assert f"MISSING_GATE:{foundational_gate}" in evaluation.violations
