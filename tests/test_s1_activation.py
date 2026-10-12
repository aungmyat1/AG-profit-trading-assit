"""OD1012 S1 authority, receipt and hermetic route checks; no broker-capable adapter."""
from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from _demo_execution_boundary_fixtures import ACCOUNT, NOW, LiveAccountRead, boundary
from _s1_notice_fixture import append_notice

from demo_execution.admission import evaluate_pre_send_gates
from demo_execution.authority import validate_live_account
from demo_execution.notification import (
    check_notification_failure_policy,
    notification_gate,
)
from demo_execution.scope import load_scope_policy
from ticket_store.store import TicketStore
from v1_tickets import ready_authority as ra

HASH = "4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf"
SID = "ST_ASIAN_SWEEP_5R_V1"


@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"])
@pytest.mark.parametrize("session", ["ASIAN_LONDON", "LONDON_NEWYORK"])
def test_committed_ready_matrix(symbol, session):
    allowed, reason = ra.ready_authority(SID, strategy_version="1.1.2", contract_sha256=HASH,
                                         symbol=symbol, session=session)
    assert allowed is (symbol == "GBPUSD" and session == "ASIAN_LONDON")
    if allowed:
        assert reason == "READY_AUTHORITY_ON_OWNER_RECORD"


def test_ready_never_enables_execution():
    scope = load_scope_policy()
    assert scope.enabled is False and scope.per_order_confirm_required is True
    assert scope.account_login_suffix == "999" and scope.broker_server == "VTMarkets-Demo"
    registry = yaml.safe_load(scope.registry_path.read_text())
    strategy = registry["strategies"][SID]
    assert strategy.get("demo_authorized") is not True and strategy.get("live_authorized") is not True
    assert ra.ready_authority(SID, strategy_version="1.1.2", contract_sha256="0" * 64,
                              symbol="GBPUSD", session="ASIAN_LONDON") == (False, ra.OWNER_DECISION_CONTRACT_MISMATCH)


@pytest.mark.parametrize("delivered,reason", [(True, None), (False, "PRE_ORDER_NOTIFICATION_NOT_DELIVERED"),
                                            (None, "PRE_ORDER_NOTIFICATION_NOT_DELIVERED"),
                                            (1, "PRE_ORDER_NOTIFICATION_NOT_DELIVERED")])
def test_delivery_matrix(tmp_path, delivered, reason):
    f = boundary(tmp_path)
    store = TicketStore(str(tmp_path / "isolated_notice_store"))
    receipt = append_notice(store, f["ticket"], NOW, delivered=delivered)
    assert check_notification_failure_policy("BLOCK_NEW_ORDERS", receipt, ticket=f["ticket"], now_utc=NOW) == reason


@pytest.mark.parametrize("policy,reason", [("PENDING_OWNER", "NOTIFICATION_FAILURE_POLICY_PENDING_OWNER"),
                                        (None, "NOTIFICATION_FAILURE_POLICY_UNRESOLVED"),
                                        ("UNKNOWN", "NOTIFICATION_FAILURE_POLICY_UNRESOLVED"),
                                        ({}, "NOTIFICATION_FAILURE_POLICY_UNRESOLVED"),
                                        ("BLOCK_NEW_ORDERS", "PRE_ORDER_NOTIFICATION_MISSING")])
def test_missing_receipt_and_policy_fail_closed(policy, reason):
    assert check_notification_failure_policy(policy) == reason


@pytest.mark.parametrize("updates", [{"message_id": True}, {"message_id": 0}, {"api_ok": False},
                                     {"channel": "PREVIEW"}, {"message_id": "1"}])
def test_invalid_api_evidence(tmp_path, updates):
    f = boundary(tmp_path)
    receipt = append_notice(f["store"], f["ticket"], NOW + timedelta(seconds=1), **updates)
    assert check_notification_failure_policy("BLOCK_NEW_ORDERS", receipt, ticket=f["ticket"],
                                             now_utc=NOW + timedelta(seconds=1)) == "PRE_ORDER_NOTIFICATION_INVALID"


def test_receipt_binding_tamper_and_future_timestamp(tmp_path):
    f = boundary(tmp_path)
    receipt = append_notice(f["store"], f["ticket"], NOW)
    assert check_notification_failure_policy("BLOCK_NEW_ORDERS", receipt, ticket={**f["ticket"], "entry": 2},
                                             now_utc=NOW) == "PRE_ORDER_NOTIFICATION_TICKET_MISMATCH"
    receipt["payload"]["api_ok"] = False
    assert check_notification_failure_policy("BLOCK_NEW_ORDERS", receipt, ticket=f["ticket"],
                                             now_utc=NOW) == "PRE_ORDER_NOTIFICATION_INVALID"
    append_notice(f["store"], f["ticket"], NOW + timedelta(seconds=2), delivered=False)
    assert notification_gate("BLOCK_NEW_ORDERS", f["store"], f["ticket"], NOW + timedelta(seconds=2)) \
        == "PRE_ORDER_NOTIFICATION_NOT_DELIVERED"
    assert notification_gate("BLOCK_NEW_ORDERS", f["store"], f["ticket"], NOW) \
        == "PRE_ORDER_NOTIFICATION_TIMESTAMP_INVALID"


class DecisionOnlyAdapter:
    """Records decisions only. No broker API or order submission methods exist."""
    def __init__(self):
        self.decisions = []

    def record(self, reasons):
        self.decisions.append({"route": "NO_ORDER_SUBMISSION", "reasons": reasons})


@pytest.mark.parametrize("case,expected", [
    ("valid", None), ("scope", "SYMBOL_SCOPE_MISMATCH"),
    ("hash", "OWNER_DECISION_CONTRACT_HASH_MISMATCH"),
    ("account", "ACCOUNT_LOGIN_SUFFIX_MISMATCH"), ("server", "ACCOUNT_SERVER_MISMATCH"),
    ("stale", "MARKET_DATA_STALE"), ("stop", "RISK_TICKET_GEOMETRY_INVALID"),
    ("risk", "STRATEGY_DAILY_LOSS_LIMIT"), ("notice", "PRE_ORDER_NOTIFICATION_NOT_DELIVERED"),
    ("authorization", "AUTHORIZATION_MISSING"), ("duplicate", "HALT_UNCERTAIN_SEND"),
    ("broker", "ACCOUNT_IDENTITY_UNAVAILABLE"),
])
def test_decision_only_simulation(tmp_path, case, expected):
    f = boundary(tmp_path)
    ticket, scope, market, risk = f["ticket"], f["scope"], f["market"], f["risk_snapshot"]
    account = {"login_suffix": ACCOUNT.login_suffix, "server": ACCOUNT.server, "trade_mode": "DEMO",
               "observed_at_utc": NOW.isoformat()}
    if case == "scope":
        ticket["symbol"] = "EURUSD"
    elif case == "hash":
        p = Path(scope.owner_decision_register_path)
        p.write_text(p.read_text().replace(HASH, "'" + "0" * 64 + "'"))
    elif case == "account":
        account["login_suffix"] = "985"
    elif case == "server":
        account["server"] = "OTHER"
    elif case == "stale":
        market = replace(market, data_close_utc=NOW - timedelta(days=1))
    elif case == "stop":
        ticket["stop_loss"] = None
    elif case == "risk":
        risk = replace(risk, strategy_daily_loss_pct=1.0)
    elif case == "notice":
        append_notice(f["store"], ticket, NOW + timedelta(seconds=1), delivered=False)
    elif case == "authorization":
        f["auth_path"].unlink()
    elif case == "duplicate":
        from demo_execution.idempotency import ExecutionLedger
        ExecutionLedger(f["store"]).reserve_before_send(ticket["ticket_id"], strategy_id=scope.strategy_id,
                                                        symbol=scope.symbol, logic_identity=scope.logic_identity,
                                                        now_utc=NOW)
    elif case == "broker":
        account = None
    result = evaluate_pre_send_gates(ticket, market, risk, now_utc=NOW + timedelta(seconds=1),
                                     authorization_path=str(f["auth_path"]), scope=scope, ticket_store=f["store"])
    account_reasons = validate_live_account(account, f["authority"], scope, now_utc=NOW + timedelta(seconds=1))
    reasons = list(result.block_reasons) + list(account_reasons)
    adapter = DecisionOnlyAdapter()
    assert not hasattr(adapter, "order_send") and not hasattr(adapter, "order_check")
    adapter.record(reasons)
    assert adapter.decisions[0]["route"] == "NO_ORDER_SUBMISSION"
    if expected is None:
        assert result.admitted and not reasons
    else:
        assert expected in reasons
    evidence_dir = os.environ.get("AGP_S1_SIM_EVIDENCE_DIR")
    if evidence_dir:
        target = Path(evidence_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{case}.json").write_text(json.dumps({
            "case": case, "source": "SYNTHETIC_TEST_ONLY", "expected_reason": expected,
            "actual_admission_reason": result.reason_code, "block_reasons": reasons,
            "route": "NO_ORDER_SUBMISSION", "order_api_calls": 0, "broker_mutations": 0,
            "gate_details": result.details.get("gate_details", {}), "verdict": "PASS",
        }, indent=2, default=str) + "\n")


def test_unknown_and_wrong_account_are_rejected(tmp_path):
    for index, payload in enumerate([{}, {"login_suffix": "UNKNOWN", "server": "VTMarkets-Demo", "trade_mode": "DEMO"},
                                   {"login_suffix": "999", "server": "VTMarkets-Demo", "trade_mode": "REAL"}]):
        f = boundary(tmp_path / str(index), account_read=LiveAccountRead(payload))
        assert validate_live_account(payload, f["authority"], f["scope"], now_utc=NOW)


def test_ambiguous_and_replay_receipts_are_rejected(tmp_path):
    f = boundary(tmp_path)
    receipt = append_notice(f["store"], f["ticket"], NOW, delivered=False)
    assert notification_gate("BLOCK_NEW_ORDERS", f["store"], f["ticket"], NOW) == "PRE_ORDER_NOTIFICATION_INVALID"
    from ticket_store.store import build_outcome
    replay = build_outcome(**{**receipt, "source": "REPLAY"})
    assert check_notification_failure_policy("BLOCK_NEW_ORDERS", replay, ticket=f["ticket"], now_utc=NOW) \
        == "PRE_ORDER_NOTIFICATION_INVALID"
