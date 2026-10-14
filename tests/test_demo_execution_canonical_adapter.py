"""B': the single canonical MT5 order_check/order_send adapter behind the guard (fake terminal only)."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_execution_boundary_fixtures import (  # noqa: E402
    BROKER_MAP,
    HOST_MAGIC_REGISTRY,
    NOW,
    REPO,
    authority_for,
    boundary,
)

from demo_execution.mt5_canonical_adapter import (  # noqa: E402
    ORDER_SHAPE_NOT_APPROVED,
    MT5CanonicalAdapter,
    load_order_shape,
)

ADAPTER = REPO / "src/demo_execution/mt5_canonical_adapter.py"


def test_committed_order_shape_is_not_approved():
    assert load_order_shape()["approved"] is False


class FakeMT5:
    TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TIME_GTC = 1, 0, 1, 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2

    def __init__(self, *, trade_mode=0, login=1234999, send_raises=False):
        self.calls, self.trade_mode, self.login, self.send_raises = [], trade_mode, login, send_raises

    def account_info(self):
        return SimpleNamespace(_asdict=lambda: {"login": self.login, "server": "VTMarkets-Demo",
                                                "trade_mode": self.trade_mode})

    def symbol_info_tick(self, symbol):
        return {"bid": 1.3000, "ask": 1.3001}

    def order_check(self, request):
        self.calls.append(("order_check", dict(request)))
        return {"retcode": 0, "volume": request["volume"], "price": request["price"]}

    def order_send(self, request):
        self.calls.append(("order_send", dict(request)))
        if self.send_raises:
            raise RuntimeError("terminal lost")
        return {"retcode": 10009, "order": 111, "deal": 222}

    def history_deals_get(self, **kw):
        self.calls.append(("history_deals_get", kw))
        return self.deals if hasattr(self, "deals") else ()


def _shape(tmp_path, status="OWNER_APPROVED"):
    path = tmp_path / "shape.yaml"
    path.write_text(yaml.safe_dump({"schema": "AGP_DEMO_ORDER_SHAPE_V1", "status": status,
                                    "owner_decision_id": "TEST_ONLY_NOT_OWNER", "shape_id": "PILOT_FULL_TP1",
                                    "deviation_tag": "SHAPEDEV", "analytics_exclusion": True,
                                    "account_margin_mode": "UNKNOWN_UNTIL_HOST_VERIFIED", "order": {
                                        "action": "DEAL", "take_profit_leg": 1, "filling": "IOC"}}))
    return path


def _adapter(fixture, mt5, *, shape, clock):
    tmp = fixture["tmp_path"]
    return MT5CanonicalAdapter(
        mt5=mt5, ticket_store=fixture["store"], order_shape_path=shape, clock=clock,
        scope_config_path=str(tmp / "demo_execution_s1.yaml"), repo_root=REPO,
        registry_path=str(tmp / "registry.yaml"), broker_symbol_map_path=BROKER_MAP,
        ready_authority_config_path=str(tmp / "ready_authority.yaml"),
        owner_decision_register_path=str(tmp / "OWNER_DECISION_REGISTER.md"),
        host_magic_registry_path=HOST_MAGIC_REGISTRY)


def _auth(decision):
    return {"ticket_id": decision.ticket_id, "state": decision.state, "authorization_id": decision.authorization_id}


def _flow(fixture, adapter, mt5=None):
    guard, ticket = fixture["guard"], fixture["ticket"]
    a1 = authority_for(fixture, now=NOW)
    check = guard.authorize_order_check(authority=a1, ticket=ticket, market=fixture["market"],
                                        risk_snapshot=fixture["risk_snapshot"], now_utc=NOW)
    assert check.admitted, check.reason_codes
    checked = adapter.order_check(authority=a1, authorization=_auth(check), ticket=ticket, account_mode="DEMO")
    return check, checked


def test_full_guarded_flow_sends_exactly_the_checked_request(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    t = {"now": NOW}
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: t["now"])
    guard, ticket = fixture["guard"], fixture["ticket"]
    _, checked = _flow(fixture, adapter, mt5)
    assert checked["retcode"] == 0 and checked["request"]["sl"] == 1.2991 and checked["request"]["tp"] == 1.3021
    t["now"] = NOW + timedelta(seconds=1)
    rec = guard.record_order_checked(authority=authority_for(fixture, now=t["now"]), ticket=ticket,
                                     checked_order=checked, now_utc=t["now"])
    assert rec.admitted, rec.reason_codes
    t["now"] = NOW + timedelta(seconds=2)
    a3 = authority_for(fixture, now=t["now"])
    send = guard.authorize_order_send(authority=a3, ticket=ticket, checked_order=checked, now_utc=t["now"])
    assert send.admitted, send.reason_codes
    result = adapter.order_send(authority=a3, authorization=_auth(send), ticket=ticket, checked_order=checked,
                                account_mode="DEMO")
    assert {k: result[k] for k in ("retcode", "order", "deal")} == {"retcode": 10009, "order": 111, "deal": 222}
    assert (result["shape_id"], result["shape_deviation_tag"], result["analytics_exclusion"],
            result["account_margin_mode"]) == ("PILOT_FULL_TP1", "SHAPEDEV", True, "UNKNOWN_UNTIL_HOST_VERIFIED")
    assert checked["request"]["comment"].endswith(" SHAPEDEV") and len(checked["request"]["comment"]) <= 31
    sent = [req for op, req in mt5.calls if op == "order_send"]
    assert sent == [checked["request"]]                 # byte-identical to the sealed request
    # The same send authorization is single-use: the lifecycle has moved on after the ack.
    t["now"] = NOW + timedelta(seconds=3)
    ack = guard.record_broker_ack(authority=authority_for(fixture, now=t["now"]), send_result=result,
                                  now_utc=t["now"])
    assert ack.admitted
    again = adapter.order_send(authority=a3, authorization=_auth(send), ticket=ticket, checked_order=checked,
                               account_mode="DEMO")
    assert again["refused"] and len([c for c in mt5.calls if c[0] == "order_send"]) == 1


def test_unapproved_shape_never_calls_the_broker(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path, status="PROPOSED_PENDING_OWNER"), clock=lambda: NOW)
    _, checked = _flow(fixture, adapter, mt5)
    assert checked == {"refused": True, "reason_code": ORDER_SHAPE_NOT_APPROVED} and mt5.calls == []


@pytest.mark.parametrize("mt5,account_mode,reason", [
    (FakeMT5(trade_mode=2), "DEMO", "ACCOUNT_NOT_DEMO"),
    (FakeMT5(login=1234111), "DEMO", "ACCOUNT_LOGIN_SUFFIX_MISMATCH"),
    (FakeMT5(), "REAL", "ACCOUNT_MODE_NOT_DEMO"),
])
def test_non_demo_or_foreign_account_never_calls_the_broker(tmp_path, mt5, account_mode, reason):
    fixture = boundary(tmp_path)
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: NOW)
    check = fixture["guard"].authorize_order_check(
        authority=(a1 := authority_for(fixture, now=NOW)), ticket=fixture["ticket"], market=fixture["market"],
        risk_snapshot=fixture["risk_snapshot"], now_utc=NOW)
    out = adapter.order_check(authority=a1, authorization=_auth(check), ticket=fixture["ticket"],
                              account_mode=account_mode)
    assert out["refused"] and out["reason_code"] == reason
    assert not [c for c in mt5.calls if c[0] in ("order_check", "order_send")]


def test_disabled_scope_or_forged_authorization_never_calls_the_broker(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: NOW)
    a1 = authority_for(fixture, now=NOW)
    forged = {"ticket_id": fixture["ticket"]["ticket_id"], "state": "AUTHORIZED", "authorization_id": "x" * 32}
    assert adapter.order_check(authority=a1, authorization=forged, ticket=fixture["ticket"],
                               account_mode="DEMO")["refused"]
    raw = yaml.safe_load((tmp_path / "demo_execution_s1.yaml").read_text())
    check = fixture["guard"].authorize_order_check(authority=a1, ticket=fixture["ticket"], market=fixture["market"],
                                                   risk_snapshot=fixture["risk_snapshot"], now_utc=NOW)
    raw["enabled"] = False
    (tmp_path / "demo_execution_s1.yaml").write_text(yaml.safe_dump(raw))
    out = adapter.order_check(authority=a1, authorization=_auth(check), ticket=fixture["ticket"], account_mode="DEMO")
    assert out["reason_code"] == "EXECUTION_DISABLED" and mt5.calls == []


def test_expired_step_authorization_never_calls_the_broker(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: NOW + timedelta(hours=6))
    _, out = _flow(fixture, adapter, mt5)
    assert out["reason_code"] == "STEP_AUTHORIZATION_EXPIRED" and mt5.calls == []


def test_send_that_raises_is_an_unknown_outcome_not_a_retry(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5(send_raises=True)
    t = {"now": NOW}
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: t["now"])
    guard, ticket = fixture["guard"], fixture["ticket"]
    _, checked = _flow(fixture, adapter, mt5)
    t["now"] = NOW + timedelta(seconds=1)
    guard.record_order_checked(authority=authority_for(fixture, now=t["now"]), ticket=ticket,
                               checked_order=checked, now_utc=t["now"])
    t["now"] = NOW + timedelta(seconds=2)
    a3 = authority_for(fixture, now=t["now"])
    send = guard.authorize_order_send(authority=a3, ticket=ticket, checked_order=checked, now_utc=t["now"])
    out = adapter.order_send(authority=a3, authorization=_auth(send), ticket=ticket, checked_order=checked,
                             account_mode="DEMO")
    assert out["unknown_outcome"] is True and len([c for c in mt5.calls if c[0] == "order_send"]) == 1


def test_reconcile_is_read_only_and_unknown_without_a_matching_deal(tmp_path):
    fixture, mt5 = boundary(tmp_path), FakeMT5()
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: NOW)
    a = fixture["authority"]
    assert adapter.reconcile(authority=a, ticket_id=a.ticket_id, send_result={})["terminal_result"] == "UNKNOWN"
    from demo_execution.mt5_canonical_adapter import _comment
    mt5.deals = [{"ticket": 222, "order": 111, "position_id": 333, "magic": a.magic_number,
                  "comment": _comment(a.ticket_id, "SHAPEDEV"), "volume": 0.5, "price": 1.3001}]
    out = adapter.reconcile(authority=a, ticket_id=a.ticket_id, send_result={"order": 111})
    assert out["reconciled"] and out["broker_deal_id"] == 222
    assert {c[0] for c in mt5.calls} == {"history_deals_get"}


def _to_send(fixture, adapter, t):
    """Drive guard + adapter to an issued send authorization; returns (authority, decision, checked)."""
    guard, ticket = fixture["guard"], fixture["ticket"]
    _, checked = _flow(fixture, adapter, None)
    assert checked.get("retcode") == 0, checked
    t["now"] = NOW + timedelta(seconds=1)
    rec = guard.record_order_checked(authority=authority_for(fixture, now=t["now"]), ticket=ticket,
                                     checked_order=checked, now_utc=t["now"])
    assert rec.admitted, rec.reason_codes
    t["now"] = NOW + timedelta(seconds=2)
    a3 = authority_for(fixture, now=t["now"])
    send = guard.authorize_order_send(authority=a3, ticket=ticket, checked_order=checked, now_utc=t["now"])
    return a3, send, checked


def test_send_rereads_the_account_and_refuses_a_non_demo_account(tmp_path):
    fixture, mt5, t = boundary(tmp_path), FakeMT5(), {"now": NOW}
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: t["now"])
    a3, send, checked = _to_send(fixture, adapter, t)
    assert send.admitted
    mt5.trade_mode = 2                                   # account switched to REAL after the check
    out = adapter.order_send(authority=a3, authorization=_auth(send), ticket=fixture["ticket"],
                             checked_order=checked, account_mode="DEMO")
    assert out == {"refused": True, "reason_code": "ACCOUNT_NOT_DEMO"}
    assert not [c for c in mt5.calls if c[0] == "order_send"]


def test_send_requires_the_durable_sending_claim(tmp_path, monkeypatch):
    fixture, mt5, t = boundary(tmp_path), FakeMT5(), {"now": NOW}
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: t["now"])
    a3, send, checked = _to_send(fixture, adapter, t)
    from demo_execution import idempotency
    monkeypatch.setattr(idempotency.ExecutionLedger, "inspect",
                        lambda self, ticket_id: idempotency.LedgerCheck(True, "IDEMPOTENCY_KEY_AVAILABLE"))
    out = adapter.order_send(authority=a3, authorization=_auth(send), ticket=fixture["ticket"],
                             checked_order=checked, account_mode="DEMO")
    assert out == {"refused": True, "reason_code": "SEND_CLAIM_MISSING"}
    assert not [c for c in mt5.calls if c[0] == "order_send"]


def test_per_order_confirm_required_true_needs_a_consumed_confirmation(tmp_path, monkeypatch):
    fixture, mt5, t = boundary(tmp_path), FakeMT5(), {"now": NOW}
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: t["now"])
    a3, send, checked = _to_send(fixture, adapter, t)
    from demo_execution import mt5_canonical_adapter as m
    monkeypatch.setattr(m, "validate_confirmation_evidence", lambda *a, **k: ("OWNER_CONFIRM_NOT_CONSUMED",))
    out = adapter.order_send(authority=a3, authorization=_auth(send), ticket=fixture["ticket"],
                             checked_order=checked, account_mode="DEMO")
    assert out == {"refused": True, "reason_code": "OWNER_CONFIRM_NOT_CONSUMED"}
    assert not [c for c in mt5.calls if c[0] == "order_send"]


def test_per_order_confirm_required_true_without_confirmation_never_reaches_the_broker(tmp_path):
    fixture, mt5 = boundary(tmp_path, confirm=False), FakeMT5()
    check = fixture["guard"].authorize_order_check(
        authority=authority_for(fixture, now=NOW), ticket=fixture["ticket"], market=fixture["market"],
        risk_snapshot=fixture["risk_snapshot"], now_utc=NOW)
    assert not check.admitted and any(r.startswith("OWNER_CONFIRM") for r in check.reason_codes)
    assert mt5.calls == []


def test_per_order_confirm_required_false_uses_the_standing_authorization_only(tmp_path):
    fixture = boundary(tmp_path, confirm=False)
    raw = yaml.safe_load((tmp_path / "demo_execution_s1.yaml").read_text())
    raw["per_order_confirm_required"] = False
    (tmp_path / "demo_execution_s1.yaml").write_text(yaml.safe_dump(raw))
    mt5, t = FakeMT5(), {"now": NOW}
    adapter = _adapter(fixture, mt5, shape=_shape(tmp_path), clock=lambda: t["now"])
    a3, send, checked = _to_send(fixture, adapter, t)
    assert send.admitted, send.reason_codes
    out = adapter.order_send(authority=a3, authorization=_auth(send), ticket=fixture["ticket"],
                             checked_order=checked, account_mode="DEMO")
    assert out["retcode"] == 10009 and len([c for c in mt5.calls if c[0] == "order_send"]) == 1
