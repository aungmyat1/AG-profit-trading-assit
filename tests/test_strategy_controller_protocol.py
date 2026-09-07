"""Focused tests for src/strategy_contract/controller.py (Phase 2). Verifies the
StrategyController Protocol's surface is strictly limited to strategy_id/evaluate -- no
broker/order/account method exists on it -- and that a plain object structurally
satisfies it via duck typing, without inheriting from anything or importing Execution.
"""
from __future__ import annotations

import datetime as dt

from strategy_contract.controller import StrategyController
from strategy_contract.decision import StrategyDecision

_FORBIDDEN_NAMES = {
    "place_order", "cancel_order", "close_position", "submit_order", "send_order",
    "account", "broker", "execute", "modify_position",
}


def test_controller_protocol_has_no_execution_surface():
    declared = {name for name in dir(StrategyController) if not name.startswith("_")}
    assert declared & _FORBIDDEN_NAMES == set()
    assert declared == {"strategy_id", "evaluate"}


def test_plain_object_satisfies_protocol_structurally():
    class _FakeController:
        @property
        def strategy_id(self) -> str:
            return "ST_EXAMPLE_V1"

        def evaluate(self, market_context):
            return StrategyDecision(
                strategy_id="ST_EXAMPLE_V1", strategy_version="1.0.0", symbol="EURUSD",
                direction=None, decision_timestamp=dt.datetime.now(dt.timezone.utc),
                confidence=None, evidence_ref=None,
            )

    instance = _FakeController()
    assert isinstance(instance, StrategyController)
    assert instance.strategy_id == "ST_EXAMPLE_V1"
    assert instance.evaluate(None) is not None


def test_object_missing_evaluate_does_not_satisfy_protocol():
    class _NotAController:
        @property
        def strategy_id(self) -> str:
            return "X"

    assert not isinstance(_NotAController(), StrategyController)
