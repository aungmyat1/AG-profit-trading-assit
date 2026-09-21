"""Focused tests for src/opportunity/registry_binding.py (StrategyBinding, P6).

Covers: registry identity != runtime dispatchability, missing adapter fails
closed for an unregistered id, alias does not imply semantic identity, and
execution authority is read from the registry's own authorization fields only
(never upgraded by a binding default).
"""
from __future__ import annotations

import pytest

from opportunity.registry_binding import (
    StrategyNotRegisteredError,
    resolve_strategy_binding,
)

REGISTRY_PATH = "strategies/registry.yaml"


class TestStrategyBinding:
    def test_session_trade_v1_is_dispatchable(self):
        binding = resolve_strategy_binding("SESSION_TRADE_V1", REGISTRY_PATH)
        assert binding.dispatchable is True

    def test_registered_non_dispatched_strategy_is_not_dispatchable(self):
        # ST_ASIAN_SWEEP_5R_V1 is registered/active but has no adapter wired into
        # strategy_manager.manager.evaluate() -- registration must not imply
        # dispatchability.
        binding = resolve_strategy_binding("ST_ASIAN_SWEEP_5R_V1", REGISTRY_PATH)
        assert binding.dispatchable is False

    def test_large_smc_v1_research_no_execution_authority(self):
        binding = resolve_strategy_binding("ST_LARGE_SMC_V1", REGISTRY_PATH)
        assert binding.dispatchable is False
        assert binding.execution_authority == "NONE"
        assert binding.lifecycle == "RESEARCH"

    def test_session_trade_v1_demo_authorized_reflected(self):
        binding = resolve_strategy_binding("SESSION_TRADE_V1", REGISTRY_PATH)
        assert binding.execution_authority == "DEMO_AUTHORIZED"

    def test_unregistered_strategy_fails_closed(self):
        with pytest.raises(StrategyNotRegisteredError):
            resolve_strategy_binding("ST_NOT_A_REAL_STRATEGY", REGISTRY_PATH)

    def test_alias_does_not_imply_semantic_identity(self):
        # ST_SESSION_SWEEP_CONTINUATION_V1 is a distinct registered identity from
        # SESSION_TRADE_V1 (registry.yaml's own identity note) -- resolving it must
        # not silently borrow SESSION_TRADE_V1's dispatchability or authority.
        binding = resolve_strategy_binding("ST_SESSION_SWEEP_CONTINUATION_V1", REGISTRY_PATH)
        assert binding.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"
        assert binding.dispatchable is False
        assert binding.execution_authority == "NONE"
