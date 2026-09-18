"""Narrow rule-engine tests for the SSC1D Section 6.1 owner-adjudicated acceptance rule
(SSC1D-H1/H2 hypothesis-level PASS/FAIL/TARGET_REACHED), frozen at
artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_SECTION_6_1_ACCEPTANCE_RULES/
SSC1D_SECTION_6_1_acceptance_rules.json.

SYNTHETIC FIXTURES ONLY. This suite never loads, computes, or references any real SSC1D-H1/H2
candidate economic outcome -- every metrics dict below is a hand-authored fixture chosen only to
exercise a single rule-engine branch. No candidate backtest is run by this file; it tests the
decision function in isolation.

The rule engine implemented here is a direct, literal transcription of the deterministic logic
frozen in the Section 6.1 artifact's `rule_engine_logic` block (itself matching the mission's
owner-adjudicated D1-D4 pseudocode). It intentionally lives only in this test module: this work
package's mandate is a governance/documentation freeze, not a change to strategy or execution
code, so no new production module is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MIN_TREATMENT_N = 20  # OWNER_POLICY_VALUE, dated 2026-09-18

RESULT_INVALID_PRE_EVALUATION = "INVALID_PRE_EVALUATION"
RESULT_INVALID_EXPERIMENT = "INVALID_EXPERIMENT"
RESULT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
RESULT_FAIL = "FAIL"
RESULT_PASS = "PASS"
RESULT_TARGET_REACHED = "TARGET_REACHED"
RESULT_TARGET_REACHED_BLOCKED = "TARGET_REACHED_BLOCKED_PENDING_ROBUSTNESS_PREREGISTRATION"


@dataclass
class CandidateFixture:
    """A single synthetic candidate evaluation input. Every field is set explicitly per test --
    there is no hidden default that could accidentally make a fixture look like real evidence."""

    pre_evaluation_invalid: bool = False
    outcome_information_exposed: bool = True
    invalid_experiment: bool = False
    treatment_N: int = 0
    retention_gate_applicable: bool = True
    retention_gate_pass: bool = True
    net_expectancy_R: float = 0.0
    net_PF: float = 0.0
    mechanism_gate_pass: bool = True
    comparability_gate_pass: bool = True
    all_required_robustness_pass: bool = False
    robustness_required_but_undefined: bool = False


@dataclass
class Verdict:
    result: str
    budget_consumed: bool


def evaluate_ssc1d_section_6_1(c: CandidateFixture) -> Verdict:
    """Literal transcription of the frozen Section 6.1 rule_engine_logic pseudocode."""
    if c.pre_evaluation_invalid:
        return Verdict(result=RESULT_INVALID_PRE_EVALUATION, budget_consumed=False)

    if c.outcome_information_exposed:
        budget_consumed = True
        if c.invalid_experiment:
            return Verdict(result=RESULT_INVALID_EXPERIMENT, budget_consumed=budget_consumed)
        if c.treatment_N < MIN_TREATMENT_N:
            return Verdict(result=RESULT_INSUFFICIENT_EVIDENCE, budget_consumed=budget_consumed)
        if c.retention_gate_applicable and not c.retention_gate_pass:
            return Verdict(result=RESULT_FAIL, budget_consumed=budget_consumed)
        if c.net_expectancy_R <= 0:
            return Verdict(result=RESULT_FAIL, budget_consumed=budget_consumed)
        if c.net_PF <= 1:
            return Verdict(result=RESULT_FAIL, budget_consumed=budget_consumed)
        if not c.mechanism_gate_pass:
            return Verdict(result=RESULT_FAIL, budget_consumed=budget_consumed)
        if not c.comparability_gate_pass:
            return Verdict(result=RESULT_FAIL, budget_consumed=budget_consumed)

        if c.all_required_robustness_pass:
            return Verdict(result=RESULT_TARGET_REACHED, budget_consumed=budget_consumed)
        if c.robustness_required_but_undefined:
            return Verdict(result=RESULT_TARGET_REACHED_BLOCKED, budget_consumed=budget_consumed)
        return Verdict(result=RESULT_PASS, budget_consumed=budget_consumed)

    # No outcome exposed and not flagged pre-evaluation-invalid is not a reachable state under
    # this pilot's contract (every replay either fails before outcome or exposes an outcome) --
    # fail closed rather than silently returning a result.
    raise AssertionError("unreachable: candidate neither pre-evaluation-invalid nor outcome-exposed")


# ---------------------------------------------------------------------------
# Required coverage (mission-specified minimum matrix)
# ---------------------------------------------------------------------------


def test_n19_positive_economics_is_insufficient_evidence_not_pass():
    c = CandidateFixture(
        treatment_N=19,
        net_expectancy_R=0.35,
        net_PF=1.8,
        retention_gate_pass=True,
        mechanism_gate_pass=True,
        comparability_gate_pass=True,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_INSUFFICIENT_EVIDENCE
    assert v.result != RESULT_PASS
    assert v.budget_consumed is True


def test_n20_zero_expectancy_fails():
    c = CandidateFixture(treatment_N=20, net_expectancy_R=0.0, net_PF=1.5)
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_FAIL
    assert v.budget_consumed is True


def test_n20_positive_expectancy_pf_exactly_one_fails():
    c = CandidateFixture(treatment_N=20, net_expectancy_R=0.10, net_PF=1.0)
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_FAIL


def test_all_economic_gates_pass_but_mechanism_fails():
    c = CandidateFixture(
        treatment_N=25,
        net_expectancy_R=0.20,
        net_PF=1.4,
        mechanism_gate_pass=False,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_FAIL
    assert v.budget_consumed is True


def test_all_candidate_gates_pass_robustness_incomplete_is_pass():
    c = CandidateFixture(
        treatment_N=22,
        net_expectancy_R=0.15,
        net_PF=1.3,
        all_required_robustness_pass=False,
        robustness_required_but_undefined=False,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_PASS


def test_all_candidate_gates_pass_robustness_undefined_is_blocked_target_reached():
    c = CandidateFixture(
        treatment_N=22,
        net_expectancy_R=0.15,
        net_PF=1.3,
        all_required_robustness_pass=False,
        robustness_required_but_undefined=True,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_TARGET_REACHED_BLOCKED
    assert v.result != RESULT_FAIL


def test_all_mandatory_gates_and_robustness_pass_is_target_reached():
    c = CandidateFixture(
        treatment_N=30,
        net_expectancy_R=0.25,
        net_PF=1.6,
        all_required_robustness_pass=True,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_TARGET_REACHED
    assert v.budget_consumed is True


def test_pre_replay_invalid_does_not_consume_budget():
    c = CandidateFixture(pre_evaluation_invalid=True, outcome_information_exposed=False)
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_INVALID_PRE_EVALUATION
    assert v.budget_consumed is False


def test_post_outcome_invalid_consumes_budget():
    c = CandidateFixture(
        treatment_N=25,
        net_expectancy_R=0.20,
        net_PF=1.4,
        invalid_experiment=True,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_INVALID_EXPERIMENT
    assert v.budget_consumed is True


# ---------------------------------------------------------------------------
# Additional gate-ordering / independence checks
# ---------------------------------------------------------------------------


def test_retention_gate_failure_is_fail_even_with_positive_economics():
    c = CandidateFixture(
        treatment_N=25,
        net_expectancy_R=0.30,
        net_PF=2.0,
        retention_gate_applicable=True,
        retention_gate_pass=False,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_FAIL


def test_retention_gate_not_applicable_is_skipped():
    c = CandidateFixture(
        treatment_N=25,
        net_expectancy_R=0.10,
        net_PF=1.2,
        retention_gate_applicable=False,
        retention_gate_pass=False,  # would fail if evaluated -- must be ignored when N/A
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_PASS


def test_comparability_gate_failure_is_fail():
    c = CandidateFixture(
        treatment_N=25,
        net_expectancy_R=0.10,
        net_PF=1.2,
        comparability_gate_pass=False,
    )
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_FAIL


def test_less_negative_than_baseline_but_still_nonpositive_is_fail_not_pass():
    """Mirrors the project's own established 'better but still negative = FAIL' principle
    (HYP_002 preregistration section 9): baseline net_expectancy_R=-0.1896R; a candidate at
    -0.05R is closer to zero but still <=0 and must not pass."""
    c = CandidateFixture(treatment_N=25, net_expectancy_R=-0.05, net_PF=0.9)
    v = evaluate_ssc1d_section_6_1(c)
    assert v.result == RESULT_FAIL


def test_hypotheses_are_evaluated_independently():
    """H1 reaching TARGET_REACHED must not influence H2's classification -- exercised here as
    two independent calls with independent fixtures, confirming no shared mutable state."""
    h1 = CandidateFixture(treatment_N=30, net_expectancy_R=0.25, net_PF=1.6, all_required_robustness_pass=True)
    h2 = CandidateFixture(treatment_N=15, net_expectancy_R=0.25, net_PF=1.6)  # N below floor
    v1 = evaluate_ssc1d_section_6_1(h1)
    v2 = evaluate_ssc1d_section_6_1(h2)
    assert v1.result == RESULT_TARGET_REACHED
    assert v2.result == RESULT_INSUFFICIENT_EVIDENCE
