"""C14 item 1: one READY ticket -> one guarded DEMO order attempt (fake terminal only)."""
from __future__ import annotations

import itertools
import sys
from types import SimpleNamespace
from datetime import timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_execution_boundary_fixtures import (  # noqa: E402
    ACCOUNT,
    BROKER_MAP,
    CONFIRM_ID,
    HOST_MAGIC_REGISTRY,
    NOW,
    REPO,
    boundary,
)
from test_demo_execution_canonical_adapter import FakeMT5, _shape  # noqa: E402

from demo_execution.dispatch import (  # noqa: E402
    AUTHORIZATION_REFUSED,
    BROKER_ACK_RECORDED,
    HALTED,
    HALT_FAILED,
    ORDER_CHECK_REFUSED,
    SCOPE_REFUSED,
    dispatch_demo_order,
)
from demo_execution.mt5_canonical_adapter import MT5CanonicalAdapter  # noqa: E402


def _paths(tmp):
    return {"repo_root": REPO, "registry_path": str(tmp / "registry.yaml"), "broker_symbol_map_path": BROKER_MAP,
            "ready_authority_config_path": str(tmp / "ready_authority.yaml"),
            "owner_decision_register_path": str(tmp / "OWNER_DECISION_REGISTER.md"),
            "host_magic_registry_path": HOST_MAGIC_REGISTRY}


def _run(fixture, mt5, *, confirm_id=CONFIRM_ID):
    tmp = fixture["tmp_path"]
    seconds = itertools.count()
    clock = lambda: NOW + timedelta(seconds=next(seconds))  # noqa: E731
    adapter = MT5CanonicalAdapter(mt5=mt5, ticket_store=fixture["store"], order_shape_path=_shape(tmp),
                                  clock=clock, scope_config_path=str(tmp / "demo_execution_s1.yaml"),
                                  **_paths(tmp))
    return dispatch_demo_order(
        guard=fixture["guard"], broker=adapter, ticket=fixture["ticket"], market=fixture["market"],
        risk_snapshot=fixture["risk_snapshot"], account=ACCOUNT, authorization_path=str(fixture["auth_path"]),
        owner_confirmation_id=confirm_id, clock=clock,
        scope_config_path=str(tmp / "demo_execution_s1.yaml"), **_paths(tmp))


def _broker_calls(mt5, op):
    return [req for name, req in mt5.calls if name == op]


def test_ready_ticket_sends_exactly_one_checked_order(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    out = _run(fixture, mt5)
    assert out.stage == BROKER_ACK_RECORDED and out.order_send_called, out
    checks, sends = _broker_calls(mt5, "order_check"), _broker_calls(mt5, "order_send")
    assert len(checks) == 1 and sends == checks                # byte-identical to the checked request
    assert out.details["broker_order_id"] == "111"
    assert fixture["guard"].trail(fixture["ticket"]["ticket_id"]).current == "BROKER_ACK"


def test_same_ticket_is_never_sent_twice(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    assert _run(fixture, mt5).stage == BROKER_ACK_RECORDED
    again = _run(fixture, mt5)
    assert again.stage == ORDER_CHECK_REFUSED and not again.order_send_called
    assert len(_broker_calls(mt5, "order_send")) == 1 and len(_broker_calls(mt5, "order_check")) == 1


def test_disabled_scope_never_reaches_the_guard_or_broker(tmp_path):
    fixture, mt5 = boundary(tmp_path, enabled=False), FakeMT5()
    out = _run(fixture, mt5)
    assert (out.stage, out.reason_code) == (SCOPE_REFUSED, "EXECUTION_DISABLED") and mt5.calls == []
    assert fixture["guard"].trail(fixture["ticket"]["ticket_id"]).current is None


def test_revoked_standing_authorization_refuses_before_any_step(tmp_path):
    fixture, mt5 = boundary(tmp_path, auth_updates={"revoked_at": (NOW - timedelta(hours=1)).isoformat()}), FakeMT5()
    out = _run(fixture, mt5)
    assert out.stage == AUTHORIZATION_REFUSED and mt5.calls == []


def test_missing_owner_confirmation_never_reaches_the_broker(tmp_path):
    fixture, mt5 = boundary(tmp_path, confirm=False), FakeMT5()
    out = _run(fixture, mt5, confirm_id=None)
    assert out.stage == ORDER_CHECK_REFUSED and mt5.calls == []
    assert any(r.startswith("OWNER_CONFIRM") for r in out.reason_codes)


def test_send_that_raises_halts_and_is_not_retried(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5(send_raises=True)
    out = _run(fixture, mt5)
    assert out.stage == HALTED and out.order_send_called
    assert len(_broker_calls(mt5, "order_send")) == 1
    assert fixture["guard"].trail(fixture["ticket"]["ticket_id"]).current == "HALT"
    assert _run(fixture, mt5).stage == ORDER_CHECK_REFUSED and len(_broker_calls(mt5, "order_send")) == 1


def test_failed_halt_persistence_is_not_reported_as_halted(tmp_path, monkeypatch):
    fixture, mt5 = boundary(tmp_path), FakeMT5(send_raises=True)
    guard = fixture["guard"]
    monkeypatch.setattr(guard, "halt", lambda **kwargs: SimpleNamespace(
        admitted=False, reason_code="HALT_WRITE_FAILED", ticket_id=fixture["ticket"]["ticket_id"],
        reason_codes=("HALT_WRITE_FAILED",), details={}, state="SENT"))

    out = _run(fixture, mt5)

    assert out.stage == HALT_FAILED and out.order_send_called
    assert out.reason_code == "HALT_WRITE_FAILED"
    assert guard.trail(fixture["ticket"]["ticket_id"]).current == "SENT"


def test_ack_fallback_halt_persistence_failure_is_reported(tmp_path, monkeypatch):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    guard = fixture["guard"]
    monkeypatch.setattr(guard, "record_broker_ack", lambda **kwargs: SimpleNamespace(
        admitted=False, reason_code="ACK_WRITE_FAILED", ticket_id=fixture["ticket"]["ticket_id"],
        reason_codes=("ACK_WRITE_FAILED",), details={}, state="SENT"))
    monkeypatch.setattr(guard, "halt", lambda **kwargs: SimpleNamespace(
        admitted=False, reason_code="HALT_WRITE_FAILED", ticket_id=fixture["ticket"]["ticket_id"],
        reason_codes=("HALT_WRITE_FAILED",), details={}, state="SENT"))

    out = _run(fixture, mt5)

    assert out.stage == HALT_FAILED and out.order_send_called
    assert out.reason_code == "HALT_WRITE_FAILED"
    assert guard.trail(fixture["ticket"]["ticket_id"]).current == "SENT"


def test_account_switched_to_real_before_send_halts_without_sending(tmp_path):
    fixture = boundary(tmp_path)

    class SwitchesToReal(FakeMT5):
        def order_check(self, request):
            out = super().order_check(request)
            self.trade_mode = 2                                # REAL after the check
            return out

    mt5 = SwitchesToReal()
    out = _run(fixture, mt5)
    assert out.stage == HALTED and not out.order_send_called and _broker_calls(mt5, "order_send") == []


def test_committed_scope_stays_disabled():
    assert yaml.safe_load((REPO / "config/demo_execution_s1.yaml").read_text(encoding="utf-8"))["enabled"] is False
