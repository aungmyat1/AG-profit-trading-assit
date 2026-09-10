import datetime as dt

import pytest

from ag_scheduler_v2 import lifecycle
from ag_scheduler_v2.resource_classes import P0_MARKET, P1_RESEARCH_CLASS, p1_research_permitted, resource_class_for_state, seconds_until_p1_must_stop
from ag_scheduler_v2.schedule import P1_RESEARCH, STANDBY, WINDOW_ASIAN_LONDON
from ag_scheduler_v2.validation_gate import GATE_FAIL, GATE_PASS, INSUFFICIENT_EVIDENCE, ValidationGateThresholds, evaluate_gate


def _utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


class TestP0P1:
    def test_p0_state_never_permits_p1(self):
        assert resource_class_for_state(WINDOW_ASIAN_LONDON) == P0_MARKET
        assert not p1_research_permitted(WINDOW_ASIAN_LONDON)

    def test_p1_research_state_is_p1(self):
        assert resource_class_for_state(P1_RESEARCH) == P1_RESEARCH_CLASS
        assert p1_research_permitted(P1_RESEARCH)

    def test_standby_defaults_to_low_resource_p0(self):
        assert resource_class_for_state(STANDBY, allow_p1_research=False) == P0_MARKET
        assert not p1_research_permitted(STANDBY, allow_p1_research=False)

    def test_standby_can_be_opted_into_p1_research(self):
        assert resource_class_for_state(STANDBY, allow_p1_research=True) == P1_RESEARCH_CLASS

    def test_standby_config_default_is_false(self):
        # Reads config/ag_scheduler_v2.yaml's own standby.allow_p1_research (no override passed).
        assert not p1_research_permitted(STANDBY)

    def test_p0_preempts_p1_seconds_until_stop_is_zero_in_p0_state(self):
        assert seconds_until_p1_must_stop(_utc(2026, 9, 10, 7, 0)) == 0.0

    def test_p1_must_stop_before_next_p0_boundary(self):
        # P1_RESEARCH from 15:10 UTC runs until tomorrow's PRE_FLIGHT (06:25 UTC).
        remaining = seconds_until_p1_must_stop(_utc(2026, 9, 10, 15, 10))
        assert remaining == pytest.approx((15 * 3600) + (15 * 60))  # 15h15m to 06:25 next day


class TestLifecycleGuard:
    def test_lifecycle_stage_is_offline_research(self):
        assert lifecycle.LIFECYCLE_STAGE == "OFFLINE_RESEARCH"
        assert lifecycle.DEMO_ELIGIBLE is False
        assert lifecycle.DEMO_AUTHORIZED is False
        assert lifecycle.EXECUTION_ENABLED is False

    def test_guard_no_execution_always_raises(self):
        with pytest.raises(lifecycle.ExecutionNotAuthorized):
            lifecycle.guard_no_execution()


class TestValidationGate:
    THRESHOLDS = ValidationGateThresholds(shadow_sample_threshold=100, net_expectancy_threshold_r=0.25, missed_observation_cycle_rate_threshold=0.05)

    def test_insufficient_evidence_below_sample_threshold(self):
        result = evaluate_gate(qualified_shadow_setups=50, net_expectancy_r=0.5, costs_complete=True, missed_observation_cycle_rate=0.01, thresholds=self.THRESHOLDS)
        assert result.verdict == INSUFFICIENT_EVIDENCE

    def test_gate_pass(self):
        result = evaluate_gate(qualified_shadow_setups=120, net_expectancy_r=0.30, costs_complete=True, missed_observation_cycle_rate=0.02, thresholds=self.THRESHOLDS)
        assert result.verdict == GATE_PASS

    def test_gate_fail_when_expectancy_below_threshold(self):
        result = evaluate_gate(qualified_shadow_setups=120, net_expectancy_r=0.10, costs_complete=True, missed_observation_cycle_rate=0.02, thresholds=self.THRESHOLDS)
        assert result.verdict == GATE_FAIL

    def test_incomplete_costs_never_pass_on_gross_r(self):
        result = evaluate_gate(qualified_shadow_setups=120, net_expectancy_r=0.5, costs_complete=False, missed_observation_cycle_rate=0.01, thresholds=self.THRESHOLDS)
        assert result.economic_gate_status == "NOT_EVALUABLE"
        assert result.verdict == INSUFFICIENT_EVIDENCE
