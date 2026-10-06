"""Manual Trade Ticket V1 Phase 1: registry ticket authority fails closed."""
from __future__ import annotations

import copy
import shutil

import pytest

from v1_tickets.authority import (
    LOGIC_VERIFIED, NOT_VERIFIED, REASON_ADAPTER_NOT_IMPLEMENTED, REASON_AUTHORITY_INVALID,
    REASON_NOT_MANUAL_ONLY, REASON_NOT_REGISTERED, REPO_ROOT, load_registry, logic_identity,
    resolve_ticket_authority,
)

ASIAN = "ST_ASIAN_SWEEP_5R_V1"


def test_asian_sweep_is_manual_only_ticket_eligible_without_order_or_edge_authority():
    reg = load_registry()
    a = resolve_ticket_authority(ASIAN, "1.1.1")
    assert a.ticket_eligible and a.logic_evaluable and a.reason is None
    assert a.ticket_authority == "MANUAL_ONLY" and a.demo_order_authority == "NONE"
    assert a.economic_status == "NOT_EVALUATED" and a.logic_status_effective == NOT_VERIFIED
    assert reg[ASIAN]["demo_authorized"] is False and reg[ASIAN]["live_authorized"] is False


def test_session_trade_v1_visible_but_fails_closed_without_adapter():
    a = resolve_ticket_authority("SESSION_TRADE_V1", "1")
    assert (a.registry_visible, a.scanner_visible, a.logic_evaluable, a.ticket_eligible) == (True, True, False, False)
    assert a.reason == REASON_ADAPTER_NOT_IMPLEMENTED
    assert load_registry()["SESSION_TRADE_V1"]["demo_authorized"] is False      # C2: unchanged


@pytest.mark.parametrize("strategy_id", ["ST_LARGE_SMC_V1", "ST_LIQUIDITY_SWEEP_RETEST_V1", "SMC_3R_V1"])
def test_strategies_without_manual_ticket_fields_are_not_ticket_eligible(strategy_id):
    a = resolve_ticket_authority(strategy_id, "x")
    assert not a.ticket_eligible and a.reason.startswith(REASON_AUTHORITY_INVALID)


@pytest.mark.parametrize("field,value", [
    ("ticket_authority", None), ("ticket_authority", "AUTO"), ("logic_status", "maybe"),
    ("economic_status", "EDGE_VERIFIED"), ("demo_order_authority", "DEMO"), ("demo_order_authority", None),
])
def test_unknown_or_missing_values_fail_closed(field, value):
    reg = copy.deepcopy(load_registry())
    reg[ASIAN][field] = value
    a = resolve_ticket_authority(ASIAN, "1.1.1", registry=reg)
    assert not a.ticket_eligible and a.reason == f"{REASON_AUTHORITY_INVALID}:{field}"


def test_unregistered_and_not_manual_only():
    assert resolve_ticket_authority("NOPE").reason == REASON_NOT_REGISTERED
    reg = copy.deepcopy(load_registry())
    reg[ASIAN]["ticket_authority"] = "NONE"
    a = resolve_ticket_authority(ASIAN, "1.1.1", registry=reg)
    assert not a.ticket_eligible and a.reason == REASON_NOT_MANUAL_ONLY


def test_logic_verified_claim_is_bound_to_identity(tmp_path):
    ident = logic_identity(ASIAN, "1.1.1")
    reg = copy.deepcopy(load_registry())
    reg[ASIAN]["logic_status"] = LOGIC_VERIFIED
    reg[ASIAN]["logic_verified_identity"] = ident["digest"]
    assert resolve_ticket_authority(ASIAN, "1.1.1", registry=reg).logic_status_effective == LOGIC_VERIFIED
    # A different version, or a changed engine/contract, does not inherit the claim.
    assert resolve_ticket_authority(ASIAN, "1.1.2", registry=reg).logic_status_effective == NOT_VERIFIED
    for rel in ("src/strategy_engine", "strategies"):
        shutil.copytree(REPO_ROOT / rel, tmp_path / rel)
    contract = tmp_path / "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
    contract.write_text(contract.read_text() + "\n# touched\n")
    changed = logic_identity(ASIAN, "1.1.1", root=tmp_path)
    assert changed["contract_hash"] != ident["contract_hash"] and changed["digest"] != ident["digest"]
    assert changed["engine_identity"] == ident["engine_identity"]
