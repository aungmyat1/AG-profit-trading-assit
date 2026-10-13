"""Offline S1 C14 admission regressions; MT5 is import-stubbed and never called."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from demo_execution.admission import (
    MarketEvidence,
    check_account_mode,
    check_cost_gate,
    check_freshness,
    check_notification_failure_policy,
    evaluate_pre_send_gates,
    prepare_canonical_handoff,
)
from demo_execution.authorization import load_standing_authorization
from demo_execution.confirmation import append_owner_confirmation
from demo_execution.idempotency import ExecutionLedger
from demo_execution.risk import OpenPosition, RiskSnapshot, evaluate_risk_caps
from demo_execution.scope import load_scope_policy
from mt5.symbol_resolver import SymbolMeta
from ticket_store.store import TicketStore

REPO = Path(__file__).resolve().parents[1]
SCOPE_CONFIG = REPO / "config" / "demo_execution_s1.yaml"
BROKER_MAP = REPO / "config" / "broker_symbol_map" / "vt_markets_demo.yaml"
REGISTRY = REPO / "strategies" / "registry.yaml"


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _fixture_scope(
    tmp_path: Path,
    *,
    enabled: bool = True,
    ready_on: bool = True,
    per_order_confirm_required: Any = True,
    include_confirm_flag: bool = True,
):
    config = _yaml(SCOPE_CONFIG)
    config["enabled"] = enabled
    if include_confirm_flag:
        config["per_order_confirm_required"] = per_order_confirm_required
    else:
        config.pop("per_order_confirm_required", None)
    scope_path = tmp_path / "demo_execution_s1.yaml"
    _write_yaml(scope_path, config)

    registry = _yaml(REGISTRY)
    strategy = registry["strategies"]["ST_ASIAN_SWEEP_5R_V1"]
    candidate = strategy["candidate_versions"]["1.1.2"]
    # Test-only identity-pinned S1 row, matching the registry schema enforced by #142.
    from v1_tickets.authority import logic_identity
    identity = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2")
    candidate["logic_verified_scopes"] = [{
        "scope_id": "S1", "symbol": "GBPUSD", "session": "ASIAN_LONDON", "branch": "RANGE_SWEEP",
        "engine_setup": "SWEEP", "status": "LOGIC_VERIFIED", "config_source": candidate["config_source"],
        "contract_hash": identity["contract_hash"], "engine_hash": identity["engine_identity"],
        "identity_hash": identity["digest"], "evidence": "TEST_ONLY_PR142_FIXTURE",
    }]
    registry_path = tmp_path / "registry.yaml"
    _write_yaml(registry_path, registry)

    contract_path = REPO / candidate["config_source"]
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    ready_path = tmp_path / "ready_authority.yaml"
    ready_value = "ON" if ready_on else "OFF"
    _write_yaml(ready_path, {"strategies": {"ST_ASIAN_SWEEP_5R_V1": {"ready": ready_value}}})
    owner_path = tmp_path / "OWNER_DECISION_REGISTER.md"
    if ready_on:
        owner_yaml = {
            "ready_authority_records": [{
                "decision_id": "TEST_ONLY_NOT_OWNER_AUTHORITY",
                "strategy_id": "ST_ASIAN_SWEEP_5R_V1",
                "version": "1.1.2",
                "contract_sha256": contract_hash,
                "status": "APPROVED",
                "symbol_scope": ["GBPUSD"],
                "session_scope": ["ASIAN_LONDON"],
                "date": "2026-10-11",
            }],
        }
        owner_path.write_text(
            "<!-- READY_AUTHORITY_RECORDS_START -->\n```yaml\n"
            + yaml.safe_dump(owner_yaml, sort_keys=False)
            + "```\n<!-- READY_AUTHORITY_RECORDS_END -->\n",
            encoding="utf-8",
        )
    else:
        owner_path.write_text("No test READY record.\n", encoding="utf-8")

    scope = load_scope_policy(
        scope_path,
        repo_root=REPO,
        registry_path=registry_path,
        broker_symbol_map_path=BROKER_MAP,
        ready_authority_config_path=ready_path,
        owner_decision_register_path=owner_path,
    )
    return scope, registry_path, ready_path, owner_path


def _ticket(scope, now: datetime, **updates):
    ticket = {
        "ticket_id": "AG-S1-TEST-20261011-GBPUSD-ASIAN_LONDON-001",
        "strategy_id": scope.strategy_id,
        "strategy_version": scope.strategy_version,
        "logic_identity": scope.logic_identity,
        "symbol": scope.symbol,
        "cycle": scope.session,
        "regime": "RANGE",
        "setup": scope.setup_branch,
        "branch": "SWEEP:TEST_ONLY",
        "direction": "LONG",
        "decision": "READY",
        "reason_code": "SIGNAL",
        "entry": 1.3001,
        "stop_loss": 1.2991,
        "risk_distance": 0.001,
        "targets": [{"leg": 1, "price": 1.3021}, {"leg": 2, "price": 1.3051}],   # AGP-TQ-D1 valid geometry
        "spread_check": "PASS",
        "evaluated_at": (now - timedelta(minutes=2)).isoformat(),
        "signal_close_utc": (now - timedelta(minutes=2)).isoformat(),
        "valid_until": (now + timedelta(minutes=10)).isoformat(),
    }
    ticket.update(updates)
    return ticket


def _auth_file(tmp_path: Path, scope, ticket, now: datetime, **updates) -> Path:
    record = {
        "schema": "AGP_STANDING_DEMO_AUTHORIZATION_V1",
        "strategy": scope.strategy_id,
        "version": scope.strategy_version,
        "symbol": scope.symbol,
        "session": scope.session,
        "branch": scope.setup_branch,
        "direction": ticket["direction"],
        "logic_identity": scope.logic_identity,
        "granted_at": (now - timedelta(days=1)).isoformat(),
        "revoked_at": None,
        "decision_id": "TEST_ONLY_NOT_OWNER_AUTHORITY",
        "emergency_stop": False,
    }
    record.update(updates)
    path = tmp_path / "host_local_auth.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _market(scope, now: datetime, **updates) -> MarketEvidence:
    data = {
        "broker_symbol": scope.broker_symbol,
        "bid": 1.3000,
        "ask": 1.3001,
        "observed_at_utc": now - timedelta(seconds=20),
        "data_close_utc": now - timedelta(minutes=1),
    }
    data.update(updates)
    return MarketEvidence(**data)


def _risk(scope, now: datetime, **updates) -> RiskSnapshot:
    meta = SymbolMeta(
        symbol=scope.broker_symbol,
        tick_size=0.00001,
        tick_value=1.0,
        contract_size=100000.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        digits=5,
        point=0.00001,
        metadata_source="EXCHANGE_VERIFIED",
    )
    data = {
        "observed_at_utc": now - timedelta(seconds=30),
        "server_day": now.date(),
        "demo_equity": 10000.0,
        "strategy_daily_loss_pct": 0.0,
        "account_daily_loss_pct": 0.0,
        "strategy_trades_today": 0,
        "open_positions": [],
        "positions_complete": True,
        "daily_metrics_complete": True,
        "symbol_meta": meta,
        "daily_reset_basis": scope.daily_reset_basis,
    }
    data.update(updates)
    return RiskSnapshot(**data)


def _pre_send_inputs(
    tmp_path: Path,
    *,
    now=None,
    enabled=True,
    ready_on=True,
    per_order_confirm_required: Any = True,
    include_confirm_flag: bool = True,
    write_confirm: bool = True,
):
    now = now or datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    scope, registry_path, ready_path, owner_path = _fixture_scope(
        tmp_path,
        enabled=enabled,
        ready_on=ready_on,
        per_order_confirm_required=per_order_confirm_required,
        include_confirm_flag=include_confirm_flag,
    )
    ticket = _ticket(scope, now)
    auth_path = _auth_file(tmp_path, scope, ticket, now)
    ticket_store = TicketStore(str(tmp_path / "ticket_store"))
    from _s1_notice_fixture import append_notice
    append_notice(ticket_store, ticket, now)
    if write_confirm and scope.per_order_confirm_required:
        append_owner_confirmation(
            ticket_store,
            ticket,
            confirmed_at_utc=now - timedelta(minutes=1),
        )
    return {
        "scope": scope,
        "ticket": ticket,
        "auth_path": auth_path,
        "market": _market(scope, now),
        "risk_snapshot": _risk(scope, now),
        "now": now,
        "registry_path": registry_path,
        "ready_path": ready_path,
        "owner_path": owner_path,
        "ticket_store": ticket_store,
    }


def test_repo_scope_is_off_and_resolves_identity_magic_and_symbol_dynamically():
    scope = load_scope_policy()
    registry = _yaml(REGISTRY)["strategies"][scope.strategy_id]["candidate_versions"][scope.strategy_version]
    contract = _yaml(REPO / registry["config_source"])
    assert scope.enabled is False
    assert scope.logic_identity == registry["logic_verified_identity"]
    assert scope.broker_symbol == "GBPUSD-VIP"
    assert scope.magic_number == contract["magic_number"]
    assert (scope.daily_reset_basis, scope.daily_reset_owner_confirm) == ("VT_SERVER_DAY", True)
    assert scope.per_order_confirm_required is True
    assert scope.notification_failure_policy == "BLOCK_NEW_ORDERS"


def test_pre_send_happy_path_passes_only_broker_free_gates(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.admitted is True
    assert result.reason_code == "ADMITTED_PRE_SEND"
    assert result.ticket_id == inputs["ticket"]["ticket_id"]
    assert result.volume is not None and result.volume > 0
    assert result.details["risk_pct"] <= 0.5
    assert result.details["owner_confirmation_id"]
    assert result.block_reasons == ()
    assert [row["outcome_kind"] for row in inputs["ticket_store"].outcomes(inputs["ticket"]["ticket_id"])
            if row["outcome_kind"] != "S1_PRE_ORDER_TELEGRAM_NOTICE"] == [
        "DEMO_OWNER_ORDER_CONFIRM",
        "DEMO_OWNER_ORDER_CONFIRM_USED",
    ]
    # A pre-send admission is not a broker order or a DEMO authorization grant.


def test_missing_owner_confirmation_blocks_with_required_reason(tmp_path):
    inputs = _pre_send_inputs(tmp_path, write_confirm=False)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.admitted is False
    assert result.reason_code == "OWNER_CONFIRM_REQUIRED"
    assert "OWNER_CONFIRM_REQUIRED" in result.block_reasons


def test_confirmation_for_another_ticket_id_does_not_authorize_ticket(tmp_path):
    inputs = _pre_send_inputs(tmp_path, write_confirm=False)
    other_ticket = dict(inputs["ticket"], ticket_id="AG-S1-OTHER-TICKET")
    append_owner_confirmation(
        inputs["ticket_store"],
        other_ticket,
        confirmed_at_utc=inputs["now"] - timedelta(minutes=1),
    )
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "OWNER_CONFIRM_REQUIRED"
    assert "OWNER_CONFIRM_TICKET_MISMATCH" in result.block_reasons


def test_owner_confirmation_binds_the_ticket_branch_and_validity_window(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    inputs["ticket"]["branch"] = "SWEEP:CHANGED_AFTER_CONFIRM"
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "OWNER_CONFIRM_REQUIRED"
    assert "OWNER_CONFIRM_BINDING_MISMATCH" in result.block_reasons


def test_owner_confirmation_binds_the_ticket_validity_window(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    inputs["ticket"]["valid_until"] = (inputs["now"] + timedelta(minutes=11)).isoformat()
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "OWNER_CONFIRM_REQUIRED"
    assert "OWNER_CONFIRM_BINDING_MISMATCH" in result.block_reasons


def test_expired_ticket_cannot_use_its_prior_owner_confirmation(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    later = inputs["now"] + timedelta(minutes=11)
    result = evaluate_pre_send_gates(
        inputs["ticket"], _market(inputs["scope"], later), _risk(inputs["scope"], later),
        now_utc=later, authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "OWNER_CONFIRM_REQUIRED"
    assert "TICKET_EXPIRED" in result.block_reasons


def test_owner_confirmation_is_single_use(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    first = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    reused = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert first.admitted is True
    assert reused.reason_code == "OWNER_CONFIRM_REQUIRED"
    assert "OWNER_CONFIRM_REUSED" in reused.block_reasons


@pytest.mark.parametrize(("flag_value", "include_flag"), [(True, False), ("false", True)])
def test_missing_or_invalid_confirmation_flag_defaults_to_required(tmp_path, flag_value, include_flag):
    inputs = _pre_send_inputs(
        tmp_path,
        per_order_confirm_required=flag_value,
        include_confirm_flag=include_flag,
        write_confirm=False,
    )
    assert inputs["scope"].per_order_confirm_required is True
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "OWNER_CONFIRM_REQUIRED"


def test_false_confirmation_flag_skips_only_that_gate(tmp_path):
    inputs = _pre_send_inputs(tmp_path, per_order_confirm_required=False, write_confirm=False)
    result = evaluate_pre_send_gates(
        inputs["ticket"], None, None,
        now_utc=inputs["now"], authorization_path=str(tmp_path / "missing-auth.json"),
        scope=inputs["scope"], ticket_store=inputs["ticket_store"],
    )
    assert inputs["scope"].per_order_confirm_required is False
    assert result.reason_code == "AUTHORIZATION_MISSING"
    assert "OWNER_CONFIRM_REQUIRED" not in result.block_reasons
    assert "RISK_SNAPSHOT_MISSING" in result.block_reasons
    assert "COST_EVIDENCE_MISSING" in result.block_reasons
    assert "FRESHNESS_EVIDENCE_MISSING" in result.block_reasons
    assert result.details["gate_details"]["owner_confirmation"]["status"] == "SKIPPED_BY_CONFIG"


def test_false_confirmation_flag_can_pass_other_valid_gates_without_confirmation(tmp_path):
    inputs = _pre_send_inputs(tmp_path, per_order_confirm_required=False, write_confirm=False)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.admitted is True
    assert result.details["gate_details"]["owner_confirmation"]["status"] == "SKIPPED_BY_CONFIG"


def test_false_confirmation_flag_does_not_skip_ticket_expiry_freshness_gate(tmp_path):
    inputs = _pre_send_inputs(tmp_path, per_order_confirm_required=False, write_confirm=False)
    later = inputs["now"] + timedelta(minutes=11)
    result = evaluate_pre_send_gates(
        inputs["ticket"], _market(inputs["scope"], later), _risk(inputs["scope"], later),
        now_utc=later, authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "TICKET_EXPIRED"
    assert result.details["gate_details"]["owner_confirmation"]["status"] == "SKIPPED_BY_CONFIG"


def test_default_disabled_scope_blocks_before_any_other_gate(tmp_path):
    inputs = _pre_send_inputs(tmp_path, enabled=False)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert (result.admitted, result.reason_code) == (False, "EXECUTION_DISABLED")


@pytest.mark.parametrize(("changes", "reason"), [
    ({"ticket_id": ""}, "TICKET_ID_MISSING"),
    ({"strategy_id": "OTHER"}, "STRATEGY_SCOPE_MISMATCH"),
    ({"strategy_version": "1.1.1"}, "STRATEGY_VERSION_SCOPE_MISMATCH"),
    ({"symbol": "EURUSD"}, "SYMBOL_SCOPE_MISMATCH"),
    ({"cycle": "LONDON_NEWYORK"}, "SESSION_SCOPE_MISMATCH"),
    ({"setup": "RANGE"}, "LOGIC_SCOPE_NOT_VERIFIED"),
    ({"direction": "NEUTRAL"}, "DIRECTION_SCOPE_MISMATCH"),
    ({"logic_identity": "0" * 64}, "LOGIC_IDENTITY_MISMATCH"),
    ({"broker_symbol": "GBPUSD"}, "BROKER_SYMBOL_SCOPE_MISMATCH"),
])
def test_scope_mismatch_has_a_canonical_block_reason(tmp_path, changes, reason):
    inputs = _pre_send_inputs(tmp_path)
    inputs["ticket"].update(changes)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert (result.admitted, result.reason_code) == (False, reason)


def test_scope_is_primary_and_records_other_available_risk_and_cost_blocks(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    inputs["ticket"]["symbol"] = "EURUSD"
    inputs["risk_snapshot"] = replace(inputs["risk_snapshot"], strategy_trades_today=5)
    inputs["market"] = replace(inputs["market"], broker_symbol="WRONG-SYMBOL")
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "SYMBOL_SCOPE_MISMATCH"
    assert result.details["primary_block_reason"] == "SYMBOL_SCOPE_MISMATCH"
    assert "STRATEGY_DAILY_TRADE_LIMIT" in result.details["block_reasons"]
    assert "BROKER_SYMBOL_SCOPE_MISMATCH" in result.details["block_reasons"]


def test_all_applicable_gate_reasons_are_reported_with_scope_primary(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    inputs["ticket"].update(symbol="EURUSD", direction="NEUTRAL")
    ExecutionLedger(inputs["ticket_store"]).reserve_before_send(
        inputs["ticket"]["ticket_id"],
        strategy_id=inputs["scope"].strategy_id,
        symbol=inputs["scope"].symbol,
        logic_identity=inputs["scope"].logic_identity,
        now_utc=inputs["now"],
    )
    result = evaluate_pre_send_gates(
        inputs["ticket"], None, None,
        now_utc=inputs["now"], authorization_path=str(tmp_path / "missing-auth.json"),
        scope=inputs["scope"], ticket_store=inputs["ticket_store"],
    )
    assert result.reason_code == "SYMBOL_SCOPE_MISMATCH"
    expected_order = [
        "SYMBOL_SCOPE_MISMATCH",
        "AUTHORIZATION_MISSING",
        "OWNER_CONFIRM_REQUIRED",
        "RISK_SNAPSHOT_MISSING",
        "COST_EVIDENCE_MISSING",
        "FRESHNESS_EVIDENCE_MISSING",
        "HALT_UNCERTAIN_SEND",
    ]
    positions = [result.block_reasons.index(reason) for reason in expected_order]
    assert positions == sorted(positions)


def test_owner_ready_binding_must_be_on_and_record_bound(tmp_path):
    inputs = _pre_send_inputs(tmp_path, ready_on=False)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
        now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert (result.admitted, result.reason_code) == (False, "READY_AUTHORITY_OFF_D6")


def test_missing_host_authorization_blocks(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    result = evaluate_pre_send_gates(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"], now_utc=inputs["now"],
        authorization_path=str(tmp_path / "not-installed.json"), scope=inputs["scope"],
        ticket_store=inputs["ticket_store"],
    )
    assert (result.admitted, result.reason_code) == (False, "AUTHORIZATION_MISSING")


@pytest.mark.parametrize(("changes", "reason"), [
    ({"revoked_at": "2026-10-11T11:00:00+00:00"}, "AUTHORIZATION_REVOKED"),
    ({"emergency_stop": True}, "EMERGENCY_STOP_ENGAGED"),
    ({"direction": "SHORT"}, "AUTHORIZATION_SCOPE_MISMATCH"),
    ({"logic_identity": "f" * 64}, "AUTHORIZATION_SCOPE_MISMATCH"),
    ({"emergency_stop": None}, "AUTHORIZATION_INVALID"),
])
def test_revoked_stopped_or_mismatched_authorization_blocks(tmp_path, changes, reason):
    inputs = _pre_send_inputs(tmp_path)
    auth = _auth_file(tmp_path, inputs["scope"], inputs["ticket"], inputs["now"], **changes)
    result = load_standing_authorization(
        inputs["scope"], inputs["ticket"], path=auth, now_utc=inputs["now"],
    )
    assert (result.authorized, result.reason_code) == (False, reason)


def test_daily_risk_happy_path_sizes_at_or_below_half_percent(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    result = evaluate_risk_caps(inputs["ticket"], inputs["scope"], inputs["risk_snapshot"],
                                now_utc=inputs["now"])
    assert result.allowed is True
    assert result.reason_code == "C14_RISK_CAPS_PASS"
    assert result.planned_volume == pytest.approx(0.5)
    assert result.planned_risk_pct <= 0.5
    assert result.daily_reset_owner_confirm is True


@pytest.mark.parametrize("foreign_magic", [0, 999999])
def test_foreign_position_on_instrument_blocks_despite_other_magic_number(tmp_path, foreign_magic):
    inputs = _pre_send_inputs(tmp_path)
    snapshot = replace(inputs["risk_snapshot"], open_positions=[OpenPosition("GBPUSD-VIP", foreign_magic)])
    result = evaluate_risk_caps(inputs["ticket"], inputs["scope"], snapshot, now_utc=inputs["now"])
    assert result.reason_code == "INSTRUMENT_POSITION_LIMIT"
    assert result.foreign_positions_on_symbol == 1


def test_reserved_s1_magic_identifies_own_position_and_still_blocks(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    snapshot = replace(inputs["risk_snapshot"], open_positions=[
        OpenPosition(inputs["scope"].broker_symbol, inputs["scope"].magic_number),
    ])
    result = evaluate_risk_caps(inputs["ticket"], inputs["scope"], snapshot, now_utc=inputs["now"])
    assert result.reason_code == "INSTRUMENT_POSITION_LIMIT"
    assert result.own_positions_on_symbol == 1
    assert result.foreign_positions_on_symbol == 0


@pytest.mark.parametrize(("changes", "reason"), [
    ({"strategy_trades_today": 5}, "STRATEGY_DAILY_TRADE_LIMIT"),
    ({"strategy_daily_loss_pct": 0.51}, "STRATEGY_DAILY_LOSS_LIMIT"),
    ({"account_daily_loss_pct": 1.51}, "ACCOUNT_DAILY_LOSS_LIMIT"),
    ({"daily_reset_basis": "UTC"}, "RISK_SERVER_DAY_UNAVAILABLE"),
    ({"positions_complete": False}, "RISK_SNAPSHOT_INCOMPLETE"),
    ({"daily_metrics_complete": False}, "RISK_SNAPSHOT_INCOMPLETE"),
    ({"symbol_meta": None}, "RISK_SYMBOL_METADATA_UNVERIFIED"),
])
def test_each_non_per_trade_c14_risk_cap_or_required_snapshot_fails_closed(tmp_path, changes, reason):
    inputs = _pre_send_inputs(tmp_path)
    snapshot = replace(inputs["risk_snapshot"], **changes)
    result = evaluate_risk_caps(inputs["ticket"], inputs["scope"], snapshot, now_utc=inputs["now"])
    assert result.allowed is False
    assert result.reason_code == reason


def test_risk_snapshot_missing_stale_and_daily_trade_count_block(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    missing = evaluate_risk_caps(inputs["ticket"], inputs["scope"], None, now_utc=inputs["now"])
    stale_snapshot = replace(inputs["risk_snapshot"], observed_at_utc=inputs["now"] - timedelta(minutes=16))
    stale = evaluate_risk_caps(inputs["ticket"], inputs["scope"], stale_snapshot, now_utc=inputs["now"])
    trade_limit = replace(inputs["risk_snapshot"], strategy_trades_today=5)
    trades = evaluate_risk_caps(inputs["ticket"], inputs["scope"], trade_limit, now_utc=inputs["now"])
    assert missing.reason_code == "RISK_SNAPSHOT_MISSING"
    assert stale.reason_code == "RISK_SNAPSHOT_STALE_OR_INVALID"
    assert trades.reason_code == "STRATEGY_DAILY_TRADE_LIMIT"


def test_cost_gate_uses_registered_absolute_and_stop_fraction_limits(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    reason, _ = check_cost_gate(inputs["ticket"], inputs["market"], inputs["scope"])
    assert reason is None
    wide = replace(inputs["market"], ask=1.3003)
    assert check_cost_gate(inputs["ticket"], wide, inputs["scope"])[0] == "COST_SPREAD_LIMIT"
    tight_stop = dict(inputs["ticket"], stop_loss=1.2995)
    assert check_cost_gate(tight_stop, inputs["market"], inputs["scope"])[0] == "COST_STOP_FRACTION_LIMIT"
    moved = replace(inputs["market"], bid=1.3002, ask=1.3003)
    assert check_cost_gate(inputs["ticket"], moved, inputs["scope"])[0] == "EXECUTION_SLIPPAGE_LIMIT"


def test_freshness_requires_signal_quote_and_bar_within_contract_window(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    assert check_freshness(inputs["ticket"], inputs["market"], inputs["scope"],
                           now_utc=inputs["now"])[0] is None
    old = inputs["now"] - timedelta(minutes=16)
    stale = replace(inputs["market"], observed_at_utc=old, data_close_utc=old)
    assert check_freshness(inputs["ticket"], stale, inputs["scope"],
                           now_utc=inputs["now"])[0] == "MARKET_DATA_STALE"
    no_signal_close = dict(inputs["ticket"], signal_close_utc=None)
    assert check_freshness(no_signal_close, inputs["market"], inputs["scope"],
                           now_utc=inputs["now"])[0] == "FRESHNESS_TIMESTAMP_MISSING_OR_INVALID"


def test_execution_claim_survives_restart_and_unknown_result_halts(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    root = tmp_path / "ticket_store"
    first = ExecutionLedger(TicketStore(str(root)))
    claimed = first.reserve_before_send(
        inputs["ticket"]["ticket_id"], strategy_id=inputs["scope"].strategy_id,
        symbol=inputs["scope"].symbol, logic_identity=inputs["scope"].logic_identity,
        now_utc=inputs["now"],
    )
    assert claimed.available and claimed.reason_code == "SEND_CLAIM_PERSISTED"

    # A new TicketStore/ledger object models a process restart mid-send. No resend is allowed.
    restarted = ExecutionLedger(TicketStore(str(root)))
    check = restarted.inspect(inputs["ticket"]["ticket_id"])
    assert (check.available, check.reason_code) == (False, "HALT_UNCERTAIN_SEND")
    unknown = restarted.record_unknown(inputs["ticket"]["ticket_id"], reason_code="TRANSPORT_TIMEOUT",
                                       now_utc=inputs["now"] + timedelta(seconds=1))
    assert unknown.reason_code == "HALT_UNKNOWN_RESULT"
    assert restarted.inspect(inputs["ticket"]["ticket_id"]).reason_code == "HALT_UNKNOWN_RESULT"


def test_reconciled_attempt_is_append_only_and_same_ticket_cannot_retry(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    store = TicketStore(str(tmp_path / "ticket_store"))
    ledger = ExecutionLedger(store)
    ledger.reserve_before_send(inputs["ticket"]["ticket_id"], strategy_id=inputs["scope"].strategy_id,
                               symbol=inputs["scope"].symbol, logic_identity=inputs["scope"].logic_identity,
                               now_utc=inputs["now"])
    terminal = ledger.record_reconciled(
        inputs["ticket"]["ticket_id"],
        reconciliation={"reconciled": True, "terminal_result": "FILLED", "broker_order_id": "TEST-ORDER"},
        now_utc=inputs["now"] + timedelta(seconds=2),
    )
    assert terminal.reason_code == "DUPLICATE_TICKET_ID"
    outcomes = store.outcomes(inputs["ticket"]["ticket_id"])
    assert [row["outcome_kind"] for row in outcomes
            if row["outcome_kind"].startswith("DEMO_EXECUTION_")] == [
        "DEMO_EXECUTION_SENDING", "DEMO_EXECUTION_RECONCILED",
    ]
    assert any(row["outcome_kind"] == "DEMO_OWNER_ORDER_CONFIRM" for row in outcomes)
    assert ExecutionLedger(TicketStore(store.root)).inspect(inputs["ticket"]["ticket_id"]).reason_code \
        == "DUPLICATE_TICKET_ID"


def test_unknown_reconciliation_evidence_is_refused(tmp_path):
    inputs = _pre_send_inputs(tmp_path)
    ledger = ExecutionLedger(TicketStore(str(tmp_path / "ticket_store")))
    result = ledger.record_reconciled(
        inputs["ticket"]["ticket_id"],
        reconciliation={"reconciled": True, "terminal_result": "UNKNOWN"}, now_utc=inputs["now"],
    )
    assert result.reason_code == "RECONCILIATION_EVIDENCE_INVALID"


def test_live_or_missing_account_mode_blocks(tmp_path):
    assert check_account_mode("LIVE") == "ACCOUNT_NOT_DEMO"
    assert check_account_mode(None) == "ACCOUNT_MODE_UNAVAILABLE"
    assert check_account_mode("DEMO") is None


def test_pending_notification_policy_blocks_new_orders(tmp_path):
    assert check_notification_failure_policy("PENDING_OWNER") == "NOTIFICATION_FAILURE_POLICY_PENDING_OWNER"
    assert check_notification_failure_policy(None) == "NOTIFICATION_FAILURE_POLICY_UNRESOLVED"


def test_final_handoff_fails_live_account_then_pending_notification_without_broker(tmp_path, monkeypatch):
    import MetaTrader5 as mt5

    inputs = _pre_send_inputs(tmp_path, per_order_confirm_required=False)
    calls = []

    def forbidden(name):
        def _call(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"unexpected MT5 operation: {name}")
        return _call

    for operation in ("order_check", "order_send", "positions_get", "account_info"):
        monkeypatch.setattr(mt5, operation, forbidden(operation), raising=False)
    store = inputs["ticket_store"]
    live = prepare_canonical_handoff(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"], account_mode="LIVE",
        ticket_store=store, now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]),
        scope=inputs["scope"],
    )
    assert live.reason_code == "ACCOUNT_NOT_DEMO"
    demo = prepare_canonical_handoff(
        inputs["ticket"], inputs["market"], inputs["risk_snapshot"], account_mode="DEMO",
        ticket_store=store, now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]),
        scope=inputs["scope"],
    )
    assert demo.reason_code == "CANONICAL_EXECUTION_ADAPTER_NOT_IMPLEMENTED"
    assert calls == []
    assert [r for r in store.outcomes(inputs["ticket"]["ticket_id"])
            if r["outcome_kind"] != "S1_PRE_ORDER_TELEGRAM_NOTICE"] == []
