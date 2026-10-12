"""Guarded C14/S1 execution boundary: authority re-validation, ledger order, evidence, halts.

Offline and broker-free. The live DEMO account read is a counted test double, the host
authorization record is a tmp file, and every timestamp is injected -- so "read live
immediately before order_check" and "expired window" are both directly observable here.
"""
from __future__ import annotations

import ast
import json
from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _demo_execution_boundary_fixtures import (  # noqa: E402
    ACCOUNT,
    BROKER_MAP,
    CONFIRM_ID,
    DECISION_ID,
    HOST_MAGIC_REGISTRY,
    NOW,
    TICKET_ID,
    LiveAccountRead,
    append_confirmation,
    authority_for,
    boundary,
    mark_confirmation_consumed,
    new_authority_id,
)

from demo_execution.admission import check_account_mode
from demo_execution.authority import (
    AccountIdentity,
    EvidenceRef,
    ExecutionAuthority,
    consumed_confirmation_ids,
    evidence_id_map,
    normalize_trade_mode,
    per_order_confirm_required,
    validate_authority_shape,
    validate_confirmation_evidence,
)
from demo_execution.guarded_adapter import GuardedCanonicalAdapter
from demo_execution.idempotency import ExecutionLedger
from demo_execution.lifecycle import (
    AUTHORIZED,
    BROKER_ACK,
    CHECKED,
    CLOSED,
    HALT,
    LIFECYCLE_KIND,
    LIFECYCLE_STATES,
    POSITION_TRACKED,
    RECONCILED,
    SENT,
    ExecutionLifecycle,
)
from ticket_store.store import TicketStore

REPO = Path(__file__).resolve().parents[1]
CHECKED_ORDER = {"retcode": 0, "volume": 0.5, "price": 1.3001, "order": 111}
SEND_RESULT = {"retcode": 10009, "order": 111, "deal": 222}


def _seconds(value: int):
    return NOW + timedelta(seconds=value)


def _kinds(store, ticket_id: str = TICKET_ID) -> list[str]:
    return [row["outcome_kind"] for row in store.outcomes(ticket_id)
            if row["outcome_kind"] != "S1_PRE_ORDER_TELEGRAM_NOTICE"]


def _trail(guard, ticket_id: str = TICKET_ID) -> list[str]:
    return [row.state for row in guard.trail(ticket_id).states]


def _check(fixture, *, now=NOW, authority=None, ticket=None, market=None, risk=None):
    return fixture["guard"].authorize_order_check(
        authority=authority if authority is not None else fixture["authority"],
        ticket=ticket if ticket is not None else fixture["ticket"],
        market=market if market is not None else fixture["market"],
        risk_snapshot=risk if risk is not None else fixture["risk_snapshot"],
        now_utc=now,
    )


def _walk_to_send(fixture) -> dict:
    """Drive a pristine fixture to a persisted send claim (check -> checked -> send)."""
    guard, ticket = fixture["guard"], fixture["ticket"]
    checked = _check(fixture, authority=authority_for(fixture))
    assert checked.admitted, checked.reason_codes
    recorded = guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)),
                                          ticket=ticket, checked_order=CHECKED_ORDER,
                                          now_utc=_seconds(1))
    assert recorded.admitted, recorded.reason_codes
    sent = guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(2)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(2))
    assert sent.admitted, sent.reason_codes
    return {"check": checked, "checked": recorded, "sent": sent}


def _walk_to_ack(fixture):
    steps = _walk_to_send(fixture)
    ack = fixture["guard"].record_broker_ack(authority=authority_for(fixture, now=_seconds(3)),
                                             send_result=SEND_RESULT, now_utc=_seconds(3))
    assert ack.admitted, ack.reason_codes
    return {**steps, "ack": ack}


# --------------------------------------------------------------- authority is mandatory


@pytest.mark.parametrize("authority", [None, {}, {"ticket_id": TICKET_ID, "enabled": True}, "AUTHORIZED"])
def test_every_guarded_call_refuses_without_an_execution_authority_object(tmp_path, authority):
    fixture = boundary(tmp_path)
    guard, store = fixture["guard"], fixture["store"]
    calls = [
        guard.authorize_order_check(authority=authority, ticket=fixture["ticket"],
                                    market=fixture["market"], risk_snapshot=fixture["risk_snapshot"],
                                    now_utc=NOW),
        guard.record_order_checked(authority=authority, ticket=fixture["ticket"],
                                   checked_order=CHECKED_ORDER, now_utc=NOW),
        guard.authorize_order_send(authority=authority, ticket=fixture["ticket"],
                                   checked_order=CHECKED_ORDER, now_utc=NOW),
        guard.record_broker_ack(authority=authority, send_result=SEND_RESULT, now_utc=NOW),
        guard.record_position_tracked(authority=authority, broker_position_id="111", now_utc=NOW),
        guard.record_position_closed(authority=authority, broker_deal_id="333", now_utc=NOW),
        guard.reconcile(authority=authority, reconciliation={"reconciled": True,
                                                             "terminal_result": "FILLED"}, now_utc=NOW),
        guard.halt(authority=authority, ticket_id=TICKET_ID, reason_code="TEST", now_utc=NOW),
    ]
    assert [decision.admitted for decision in calls] == [False] * len(calls)
    assert {decision.reason_code for decision in calls} == {"EXECUTION_AUTHORITY_MISSING"}
    assert _trail(guard) == []                        # no lifecycle evidence was written
    assert "DEMO_EXECUTION_SENDING" not in _kinds(store)
    assert fixture["reader"].calls == 0               # not even the account was read


def test_authority_shape_validation_rejects_incomplete_and_forged_claims(tmp_path):
    authority = boundary(tmp_path)["authority"]
    assert validate_authority_shape(authority) == ()
    assert validate_authority_shape(replace(authority, ticket_id="")) == ("EXECUTION_AUTHORITY_INVALID",)
    assert validate_authority_shape(replace(authority, magic_number=True)) == ("EXECUTION_AUTHORITY_INVALID",)
    assert validate_authority_shape(replace(authority, account={"login_suffix": "985"})) \
        == ("EXECUTION_AUTHORITY_INVALID",)
    assert validate_authority_shape(
        replace(authority, ready_evidence=EvidenceRef("READY", "not-a-digest", NOW))
    ) == ("EXECUTION_AUTHORITY_INVALID",)
    assert validate_authority_shape(replace(authority, owner_confirmation_id="")) \
        == ()        # absence is judged against the scope gate, not the shape
    assert validate_authority_shape(replace(authority, issued_at_utc="2026-10-11T12:00:00")) \
        == ("AUTHORITY_TIMESTAMP_INVALID",)


# ------------------------------------------------------- the guard re-validates, not the caller


def test_the_guard_reloads_the_committed_scope_and_refuses_a_disabled_lane(tmp_path):
    fixture = boundary(tmp_path, enabled=False)
    decision = _check(fixture)
    assert (decision.admitted, decision.reason_code) == (False, "EXECUTION_DISABLED")
    assert decision.details["scope_enabled"] is False
    assert _trail(fixture["guard"]) == []


def _guard_with(fixture, **overrides):
    """The same boundary, but with one scope input the guard must re-load for itself."""
    root = fixture["tmp_path"]
    paths = {
        "scope_config_path": str(root / "demo_execution_s1.yaml"),
        "repo_root": REPO,
        "registry_path": str(root / "registry.yaml"),
        "broker_symbol_map_path": BROKER_MAP,
        "ready_authority_config_path": str(root / "ready_authority.yaml"),
        "owner_decision_register_path": str(root / "OWNER_DECISION_REGISTER.md"),
        "host_magic_registry_path": HOST_MAGIC_REGISTRY,
        "authorization_path": str(fixture["auth_path"]),
    }
    paths.update(overrides)
    return GuardedCanonicalAdapter(ticket_store=fixture["store"],
                                   live_account_reader=fixture["reader"], **paths)


def test_the_guard_refuses_when_its_own_scope_inputs_are_unusable(tmp_path):
    fixture = boundary(tmp_path)
    broken = _guard_with(fixture, host_magic_registry_path=str(tmp_path / "absent-magics.yaml"))
    decision = broken.authorize_order_check(
        authority=fixture["authority"], ticket=fixture["ticket"], market=fixture["market"],
        risk_snapshot=fixture["risk_snapshot"], now_utc=NOW,
    )
    assert (decision.admitted, decision.reason_code) == (False, "HOST_MAGIC_REGISTRY_UNAVAILABLE")

    unready = boundary(tmp_path / "unready", ready_on=False)
    decision = _check(unready)
    assert decision.admitted is False
    assert "READY_AUTHORITY_OFF_D6" in decision.reason_codes


@pytest.mark.parametrize(("field_name", "value"), [
    ("strategy_id", "ST_SOMETHING_ELSE"),
    ("strategy_version", "1.1.1"),
    ("symbol", "EURUSD"),
    ("session", "LONDON_NEWYORK"),
    ("setup_branch", "RANGE"),
    ("direction", "NEUTRAL"),
    ("logic_identity", "0" * 64),
    ("magic_number", 777002),
])
def test_an_authority_that_does_not_match_the_committed_scope_refuses(tmp_path, field_name, value):
    fixture = boundary(tmp_path)
    decision = _check(fixture, authority=authority_for(fixture, **{field_name: value}))
    assert decision.admitted is False
    assert "AUTHORITY_SCOPE_MISMATCH" in decision.reason_codes


@pytest.mark.parametrize("changes", [
    {"ticket_id": "AG-S1-TEST-OTHER"},
    {"direction": "SHORT"},
    {"strategy_version": "1.1.1"},
    {"symbol": "EURUSD"},
    {"setup": "RANGE"},
    {"logic_identity": "0" * 64},
])
def test_an_authority_bound_to_a_different_ticket_than_the_one_presented_refuses(tmp_path, changes):
    fixture = boundary(tmp_path)
    decision = _check(fixture, ticket=dict(fixture["ticket"], **changes))
    assert decision.admitted is False
    assert "AUTHORITY_TICKET_MISMATCH" in decision.reason_codes


def test_caller_gate_results_alone_never_authorize_a_call(tmp_path):
    """The authority claims fresh evidence; the facts handed over are not that evidence."""
    fixture = boundary(tmp_path)
    decision = _check(fixture, market=replace(fixture["market"], ask=1.3003))
    assert decision.admitted is False
    # The id is recomputed from the facts the guard was actually given, and the guard's own gate
    # run blocks on them too -- a caller's ADMITTED_PRE_SEND is never taken on trust.
    assert "FRESHNESS_EVIDENCE_ID_MISMATCH" in decision.reason_codes
    assert "COST_SPREAD_LIMIT" in decision.reason_codes

    decision = _check(fixture, risk=replace(fixture["risk_snapshot"], demo_equity=9999.0))
    assert decision.admitted is False
    assert "RISK_EVIDENCE_ID_MISMATCH" in decision.reason_codes

    decision = _check(fixture, ticket=dict(fixture["ticket"], decision="WATCH_READY"))
    assert decision.admitted is False
    assert "READY_EVIDENCE_ID_MISMATCH" in decision.reason_codes


def test_ready_risk_and_freshness_evidence_ids_must_be_present_current_and_bound(tmp_path):
    fixture = boundary(tmp_path)
    authority = fixture["authority"]

    forged = replace(authority, ready_evidence=EvidenceRef("READY", "0" * 64, NOW))
    assert "READY_EVIDENCE_ID_MISMATCH" in _check(fixture, authority=forged).reason_codes

    stale = replace(authority, risk_evidence=replace(authority.risk_evidence,
                                                     observed_at_utc=NOW - timedelta(minutes=20)))
    assert "RISK_EVIDENCE_STALE" in _check(fixture, authority=stale).reason_codes

    future = replace(authority, freshness_evidence=replace(authority.freshness_evidence,
                                                           observed_at_utc=NOW + timedelta(minutes=1)))
    assert "FRESHNESS_EVIDENCE_TIMESTAMP_IN_FUTURE" in _check(fixture, authority=future).reason_codes

    missing = replace(authority, freshness_evidence=None)
    decision = _check(fixture, authority=missing)
    assert decision.admitted is False
    assert "EXECUTION_AUTHORITY_INVALID" in decision.reason_codes


def test_a_missing_gate_input_is_a_refusal_not_a_default(tmp_path):
    fixture = boundary(tmp_path)
    decision = fixture["guard"].authorize_order_check(
        authority=fixture["authority"], ticket=fixture["ticket"], market=None, risk_snapshot=None,
        now_utc=NOW,
    )
    assert decision.admitted is False
    assert {"RISK_EVIDENCE_ID_MISMATCH", "FRESHNESS_EVIDENCE_ID_MISMATCH"} <= set(decision.reason_codes)
    assert decision.reason_code == "RISK_EVIDENCE_ID_MISMATCH"
    # The guard's own gate run reports every gate it could evaluate, not just the first.
    assert "RISK_SNAPSHOT_MISSING" in decision.details["gate_block_reasons"]
    assert "COST_EVIDENCE_MISSING" in decision.details["gate_block_reasons"]


def test_an_authority_is_single_use_expires_and_cannot_predate_its_own_use(tmp_path):
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    assert _check(fixture).admitted is True

    reused = guard.record_order_checked(authority=fixture["authority"], ticket=fixture["ticket"],
                                        checked_order=CHECKED_ORDER, now_utc=_seconds(1))
    assert (reused.admitted, reused.reason_code) == (False, "AUTHORITY_REUSED")

    stale = replace(fixture["authority"], authority_id=new_authority_id(),
                    issued_at_utc=NOW - timedelta(minutes=30))
    decision = guard.record_order_checked(authority=stale, ticket=fixture["ticket"],
                                          checked_order=CHECKED_ORDER, now_utc=NOW)
    assert "AUTHORITY_EXPIRED" in decision.reason_codes

    premature = replace(fixture["authority"], authority_id=new_authority_id(),
                        issued_at_utc=NOW + timedelta(minutes=1))
    decision = guard.record_order_checked(authority=premature, ticket=fixture["ticket"],
                                          checked_order=CHECKED_ORDER, now_utc=NOW)
    assert "AUTHORITY_NOT_YET_VALID" in decision.reason_codes


# ------------------------------------------------------- live DEMO account identity


def test_the_demo_account_is_read_live_inside_the_guard_before_the_check_is_authorized(tmp_path):
    fixture = boundary(tmp_path)
    assert fixture["reader"].calls == 0
    decision = _check(fixture)
    assert decision.admitted is True
    assert fixture["reader"].calls == 1
    recorded = ExecutionLifecycle(fixture["store"]).trail(TICKET_ID).state_row(AUTHORIZED)
    assert recorded is not None
    account = recorded.evidence["account"]
    assert account["login_suffix"] == ACCOUNT.login_suffix
    assert account["server"] == ACCOUNT.server
    assert account["trade_mode"] == "DEMO"
    # A read taken by the guard is a live read: it is stamped with this call's own timestamp.
    assert account["read_at_utc"] == NOW.isoformat()

    guard, ticket = fixture["guard"], fixture["ticket"]
    assert guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(1)).admitted is True
    assert fixture["reader"].calls == 2
    assert guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(2)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(2)).admitted is True
    assert fixture["reader"].calls == 3          # check, checked result, send


@pytest.mark.parametrize(("payload", "reason"), [
    ({"login_suffix": "985", "server": "VTMarkets-Demo", "trade_mode": "DEMO"},
     "ACCOUNT_LOGIN_SUFFIX_MISMATCH"),
    ({"login_suffix": "999", "server": "VTMarkets-Live", "trade_mode": "DEMO"},
     "ACCOUNT_SERVER_MISMATCH"),
    ({"login_suffix": "999", "server": "VTMarkets-Demo", "trade_mode": 2}, "ACCOUNT_NOT_DEMO"),
    ({"login_suffix": "999", "server": "VTMarkets-Demo", "trade_mode": "REAL"}, "ACCOUNT_NOT_DEMO"),
    ({"login_suffix": "999", "server": "VTMarkets-Demo", "trade_mode": None},
     "ACCOUNT_MODE_UNAVAILABLE"),
    ({"login_suffix": "999", "server": "VTMarkets-Demo"}, "ACCOUNT_MODE_UNAVAILABLE"),
    ({"server": "VTMarkets-Demo", "trade_mode": "DEMO"}, "ACCOUNT_IDENTITY_UNAVAILABLE"),
    ({"login_suffix": "98", "server": "VTMarkets-Demo", "trade_mode": "DEMO"},
     "ACCOUNT_IDENTITY_UNAVAILABLE"),
    ({"login_suffix": "985", "server": "", "trade_mode": "DEMO"}, "ACCOUNT_IDENTITY_UNAVAILABLE"),
    ({}, "ACCOUNT_IDENTITY_UNAVAILABLE"),
])
def test_any_other_account_identity_than_the_pinned_demo_account_refuses(tmp_path, payload, reason):
    fixture = boundary(tmp_path, account_read=LiveAccountRead(payload))
    decision = _check(fixture)
    assert decision.admitted is False
    assert reason in decision.reason_codes
    assert _trail(fixture["guard"]) == []


def test_an_account_read_that_raises_or_returns_a_cached_snapshot_refuses(tmp_path):
    raising = boundary(tmp_path, account_read=LiveAccountRead(raises=True))
    decision = _check(raising)
    assert (decision.admitted, decision.reason_code) == (False, "ACCOUNT_IDENTITY_UNAVAILABLE")

    cached = LiveAccountRead().with_observed_at((NOW - timedelta(seconds=60)).isoformat())
    stale = boundary(tmp_path / "stale", account_read=cached)
    assert "ACCOUNT_READ_STALE" in _check(stale).reason_codes

    ahead = LiveAccountRead().with_observed_at((NOW + timedelta(seconds=5)).isoformat())
    future = boundary(tmp_path / "future", account_read=ahead)
    assert "ACCOUNT_IDENTITY_TIMESTAMP_INVALID" in _check(future).reason_codes


def test_a_full_account_login_is_never_accepted_and_never_recorded(tmp_path):
    reader = LiveAccountRead({"login": 26088985, "server": "VTMarkets-Demo", "trade_mode": "DEMO"})
    fixture = boundary(tmp_path, account_read=reader)
    decision = _check(fixture)
    assert decision.admitted is False
    assert "ACCOUNT_IDENTITY_UNAVAILABLE" in decision.reason_codes
    assert reader.calls == 1                     # it was read; it was simply not accepted
    assert "26088985" not in json.dumps(fixture["store"].outcomes(TICKET_ID))


@pytest.mark.parametrize(("raw", "expected"), [
    (0, "DEMO"), ("0", "DEMO"), ("DEMO", "DEMO"), ("demo", "DEMO"),
    ("ACCOUNT_TRADE_MODE_DEMO", "DEMO"),
    (1, "CONTEST"), (2, "REAL"), ("REAL", "REAL"), ("LIVE", "LIVE"), (3, "MODE_3"), (-1, "MODE_-1"),
    (None, None), ("", None), ("  ", None), (True, None), (False, None), ({}, None),
])
def test_a_terminal_trade_mode_is_classified_never_guessed(raw, expected):
    assert normalize_trade_mode(raw) == expected
    # Whatever the terminal reports, only DEMO passes the mode gate.
    assert check_account_mode(normalize_trade_mode(raw)) == (None if expected == "DEMO"
                                                             else "ACCOUNT_MODE_UNAVAILABLE"
                                                             if expected is None else "ACCOUNT_NOT_DEMO")


def test_the_authority_and_account_types_never_carry_a_full_login_or_secret():
    authority_fields = {item.name for item in fields(ExecutionAuthority)}
    account_fields = {item.name for item in fields(AccountIdentity)}
    assert account_fields == {"login_suffix", "server", "trade_mode"}
    assert not authority_fields & {"login", "account_login", "password", "token", "secret"}


# ------------------------------------------- standing authorization + per-order confirmation


@pytest.mark.parametrize(("auth_updates", "reason"), [
    ({"emergency_stop": True}, "EMERGENCY_STOP_ENGAGED"),
    ({"revoked_at": "2026-10-11T11:00:00+00:00"}, "AUTHORIZATION_REVOKED"),
    ({"symbol": "EURUSD"}, "AUTHORIZATION_SCOPE_MISMATCH"),
    ({"logic_identity": "f" * 64}, "AUTHORIZATION_SCOPE_MISMATCH"),
])
def test_the_standing_authorization_record_is_re_read_inside_the_guard(tmp_path, auth_updates, reason):
    fixture = boundary(tmp_path, auth_updates=auth_updates)
    decision = _check(fixture)
    assert decision.admitted is False
    assert reason in decision.reason_codes


def test_the_authority_must_name_the_authorization_record_and_decision_the_guard_holds(tmp_path):
    fixture = boundary(tmp_path)
    other_path = tmp_path / "some_other_authorization.json"
    other_path.write_text(json.dumps({"schema": "AGP_STANDING_DEMO_AUTHORIZATION_V1"}), encoding="utf-8")
    decision = _check(fixture, authority=authority_for(fixture, authorization_path=str(other_path)))
    assert "AUTHORIZATION_PATH_MISMATCH" in decision.reason_codes

    relative = _check(fixture, authority=authority_for(fixture, authorization_path="host_local_auth.json"))
    assert "AUTHORIZATION_PATH_MISMATCH" in relative.reason_codes

    decision = _check(fixture, authority=authority_for(fixture,
                                                       authorization_decision_id="NOT_THE_RECORDED_DECISION"))
    assert "AUTHORIZATION_DECISION_ID_MISMATCH" in decision.reason_codes
    assert decision.details["authorization_decision_id"] == DECISION_ID


def test_a_stop_engaged_between_check_and_send_blocks_the_send_and_writes_no_claim(tmp_path):
    fixture = boundary(tmp_path / "stopped")
    guard, ticket = fixture["guard"], fixture["ticket"]
    assert _check(fixture).admitted is True
    assert guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(1)).admitted is True
    record = json.loads(fixture["auth_path"].read_text(encoding="utf-8"))
    record["emergency_stop"] = True
    fixture["auth_path"].write_text(json.dumps(record), encoding="utf-8")

    decision = guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(2)), ticket=ticket,
                                          checked_order=CHECKED_ORDER, now_utc=_seconds(2))
    assert decision.admitted is False
    assert "EMERGENCY_STOP_ENGAGED" in decision.reason_codes
    assert "DEMO_EXECUTION_SENDING" not in _kinds(fixture["store"])
    assert _trail(guard) == [AUTHORIZED, CHECKED]


def test_per_order_confirmation_is_required_while_the_gate_is_in_force(tmp_path):
    assert per_order_confirm_required(SimpleNamespace()) is True                  # absent stays required
    assert per_order_confirm_required(SimpleNamespace(per_order_confirm_required="no")) is True
    assert per_order_confirm_required(SimpleNamespace(per_order_confirm_required=False)) is False
    assert per_order_confirm_required(boundary(tmp_path)["scope"]) is True

    missing = boundary(tmp_path / "missing", confirm=False)
    decision = _check(missing, authority=replace(missing["authority"], owner_confirmation_id=None))
    assert decision.admitted is False
    assert "OWNER_CONFIRM_REQUIRED" in decision.reason_codes

    absent = boundary(tmp_path / "absent", confirm=False)
    decision = _check(absent, authority=authority_for(absent, owner_confirmation_id=CONFIRM_ID))
    assert decision.admitted is False
    assert "OWNER_CONFIRM_MISSING" in decision.reason_codes

    unbound = boundary(tmp_path / "unbound")
    decision = _check(unbound, authority=authority_for(unbound, owner_confirmation_id="SOME_OTHER_ID"))
    assert decision.admitted is False
    # The ledger holds a valid, bound confirmation -- but not the one this authority claims.
    assert "OWNER_CONFIRM_ID_MISMATCH" in decision.reason_codes
    # A refused call never spends the owner's single-use confirmation: the claim is validated
    # before the gates that would consume it.
    assert "DEMO_OWNER_ORDER_CONFIRM_USED" not in _kinds(unbound["store"])
    assert decision.details["gates"] == "NOT_EVALUATED_OWNER_CONFIRMATION_REFUSED"


def test_a_confirmation_bound_to_another_identity_is_not_this_ticket_s_confirmation(tmp_path):
    fixture = boundary(tmp_path, confirm=False)
    append_confirmation(fixture["store"], fixture["scope"], fixture["ticket"], confirm_id=CONFIRM_ID,
                        payload_updates={"symbol": "EURUSD"})
    decision = _check(fixture, authority=authority_for(fixture, owner_confirmation_id=CONFIRM_ID))
    assert decision.admitted is False
    assert "OWNER_CONFIRM_BINDING_MISMATCH" in decision.reason_codes

    other_ticket = boundary(tmp_path / "other", confirm=False)
    append_confirmation(other_ticket["store"], other_ticket["scope"], other_ticket["ticket"],
                        confirm_id=CONFIRM_ID, payload_updates={"ticket_id": "AG-S1-OTHER"})
    decision = _check(other_ticket,
                      authority=authority_for(other_ticket, owner_confirmation_id=CONFIRM_ID))
    assert decision.admitted is False
    assert "OWNER_CONFIRM_BINDING_MISMATCH" in decision.reason_codes


def test_two_confirmations_for_one_ticket_are_refused_not_picked_between(tmp_path):
    fixture = boundary(tmp_path)
    append_confirmation(fixture["store"], fixture["scope"], fixture["ticket"], confirm_id=CONFIRM_ID,
                        confirmed_at=NOW - timedelta(seconds=30))
    decision = _check(fixture)
    assert decision.admitted is False
    # The sanctioned validator will not pick between two rows for one ticket: it reports reuse,
    # and the guard adds that the claimed confirmation was never consumed. Nothing was consumed
    # by this refused call, and no evidence row was written.
    assert {"OWNER_CONFIRM_REUSED", "OWNER_CONFIRM_MISSING"} <= set(decision.reason_codes)
    assert _kinds(fixture["store"]) == ["DEMO_OWNER_ORDER_CONFIRM", "DEMO_OWNER_ORDER_CONFIRM"]
    assert _trail(fixture["guard"]) == []


def test_an_expired_ticket_window_refuses_the_confirmation_and_the_order(tmp_path):
    fixture = boundary(tmp_path)
    expired = dict(fixture["ticket"], valid_until=(NOW - timedelta(seconds=1)).isoformat())
    decision = _check(fixture, ticket=expired)
    assert decision.admitted is False
    assert "TICKET_EXPIRED" in decision.reason_codes
    assert _trail(fixture["guard"]) == []          # no authorization was issued for an expired ticket


def test_a_confirmation_is_consumed_once_by_the_check_and_never_authorizes_a_second_order(tmp_path):
    fixture = boundary(tmp_path)
    guard, ticket, store = fixture["guard"], fixture["ticket"], fixture["store"]
    assert _kinds(store) == ["DEMO_OWNER_ORDER_CONFIRM"]

    assert _check(fixture).admitted is True
    # The canonical admission gates the guard runs itself consumed the confirmation exactly once.
    assert _kinds(store) == ["DEMO_OWNER_ORDER_CONFIRM", "DEMO_OWNER_ORDER_CONFIRM_USED",
                             "DEMO_LIFECYCLE_EVIDENCE"]
    assert consumed_confirmation_ids(store, TICKET_ID) == frozenset({CONFIRM_ID})

    assert guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(1)).admitted is True
    sent = guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(2)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(2))
    assert sent.admitted is True                        # consumed once, by this ticket's own check
    assert _kinds(store).count("DEMO_OWNER_ORDER_CONFIRM_USED") == 1

    # A second order may not borrow the consumed confirmation, and the same ticket may not be
    # re-authorized on the strength of it: it now has a trail and an in-flight send claim.
    again = _check(fixture, now=_seconds(9), authority=authority_for(fixture, now=_seconds(9)))
    assert again.admitted is False
    assert {"LIFECYCLE_ORDER_INVALID", "HALT_UNCERTAIN_SEND"} <= set(again.reason_codes)
    assert _kinds(store).count("DEMO_EXECUTION_SENDING") == 1
    assert _kinds(store).count("DEMO_OWNER_ORDER_CONFIRM_USED") == 1


def test_a_send_requires_the_confirmation_to_have_been_consumed(tmp_path):
    """The send-phase rule, checked directly: bound but unconsumed is not enough."""
    fixture = boundary(tmp_path)
    authority, ticket, store = fixture["authority"], fixture["ticket"], fixture["store"]
    assert validate_confirmation_evidence(store, authority, ticket, now_utc=NOW,
                                          require_consumed=False) == ()
    assert validate_confirmation_evidence(store, authority, ticket, now_utc=NOW,
                                          require_consumed=True) == ("OWNER_CONFIRM_NOT_CONSUMED",)
    mark_confirmation_consumed(store, ticket, confirm_id=CONFIRM_ID)
    assert validate_confirmation_evidence(store, authority, ticket, now_utc=NOW,
                                          require_consumed=True) == ()
    assert validate_confirmation_evidence(store, authority, None, now_utc=NOW,
                                          require_consumed=True) == ("OWNER_CONFIRM_TICKET_INVALID",)


# ------------------------------------------------- duplicate ticket check before order_check


def test_a_duplicate_ticket_is_refused_before_order_check_not_only_before_send(tmp_path):
    fixture = boundary(tmp_path)
    scope = fixture["scope"]
    claim = ExecutionLedger(fixture["store"]).reserve_before_send(
        TICKET_ID, strategy_id=scope.strategy_id, symbol=scope.symbol,
        logic_identity=scope.logic_identity, now_utc=NOW - timedelta(minutes=1),
    )
    assert claim.reason_code == "SEND_CLAIM_PERSISTED"

    decision = _check(fixture)
    assert decision.admitted is False
    assert decision.reason_code == "HALT_UNCERTAIN_SEND"
    assert decision.details["ledger_check"] == "HALT_UNCERTAIN_SEND"
    assert _kinds(fixture["store"]) == ["DEMO_OWNER_ORDER_CONFIRM", "DEMO_EXECUTION_SENDING"]
    assert _trail(fixture["guard"]) == []            # no AUTHORIZED evidence was written
    assert fixture["reader"].calls == 0              # the ledger check runs before the account read


def test_a_reconciled_ticket_can_never_be_re_authorized(tmp_path):
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    _walk_to_ack(fixture)
    assert guard.record_position_tracked(authority=authority_for(fixture, now=_seconds(4)),
                                         broker_position_id="111", now_utc=_seconds(4)).admitted is True
    assert guard.record_position_closed(authority=authority_for(fixture, now=_seconds(5)),
                                        broker_deal_id="333", now_utc=_seconds(5)).admitted is True
    settled = guard.reconcile(
        authority=authority_for(fixture, now=_seconds(6)),
        reconciliation={"reconciled": True, "terminal_result": "FILLED", "broker_order_id": "111",
                        "broker_deal_id": "333"}, now_utc=_seconds(6),
    )
    assert settled.admitted is True
    assert settled.details["resubmission"] == "NEVER"

    again = _check(fixture, now=_seconds(7), authority=authority_for(fixture, now=_seconds(7)))
    assert again.admitted is False
    assert {"DUPLICATE_TICKET_ID", "LIFECYCLE_ALREADY_RECONCILED", "LIFECYCLE_ORDER_INVALID"} \
        <= set(again.reason_codes)
    assert again.authorization_id is None


def test_the_checked_order_presented_at_send_must_be_the_one_order_check_returned(tmp_path):
    fixture = boundary(tmp_path)
    guard, ticket = fixture["guard"], fixture["ticket"]
    assert _check(fixture).admitted is True
    assert guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(1)).admitted is True
    decision = guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(2)),
                                          ticket=ticket, checked_order=dict(CHECKED_ORDER, volume=5.0),
                                          now_utc=_seconds(2))
    assert decision.admitted is False
    assert "CHECKED_ORDER_MISMATCH" in decision.reason_codes
    assert "DEMO_EXECUTION_SENDING" not in _kinds(fixture["store"])


def test_a_missing_checked_order_at_send_is_refused(tmp_path):
    fixture = boundary(tmp_path)
    guard, ticket = fixture["guard"], fixture["ticket"]
    assert _check(fixture).admitted is True
    assert guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(1)).admitted is True
    decision = guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(2)),
                                          ticket=ticket, checked_order=None, now_utc=_seconds(2))
    assert decision.admitted is False
    assert "CHECKED_ORDER_MISMATCH" in decision.reason_codes


def test_an_expired_check_or_send_window_is_refused_rather_than_assumed_fine(tmp_path):
    fixture = boundary(tmp_path)
    guard, ticket = fixture["guard"], fixture["ticket"]
    late = NOW + timedelta(minutes=fixture["scope"].signal_expiry_minutes + 1)
    assert _check(fixture).admitted is True

    decision = guard.record_order_checked(authority=authority_for(fixture, now=late), ticket=ticket,
                                          checked_order=CHECKED_ORDER, now_utc=late)
    assert decision.admitted is False
    assert "ORDER_CHECK_AUTHORIZATION_EXPIRED" in decision.reason_codes

    assert guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)), ticket=ticket,
                                      checked_order=CHECKED_ORDER, now_utc=_seconds(1)).admitted is True
    decision = guard.authorize_order_send(authority=authority_for(fixture, now=late), ticket=ticket,
                                          checked_order=CHECKED_ORDER, now_utc=late)
    assert decision.admitted is False
    assert "ORDER_SEND_AUTHORIZATION_EXPIRED" in decision.reason_codes
    assert "DEMO_EXECUTION_SENDING" not in _kinds(fixture["store"])


def test_a_wrong_authorization_id_reference_is_refused(tmp_path):
    fixture = boundary(tmp_path)
    check = _check(fixture)
    decision = fixture["guard"].record_order_checked(
        authority=authority_for(fixture, now=_seconds(1)), ticket=fixture["ticket"],
        checked_order=CHECKED_ORDER, now_utc=_seconds(1), authorization_id="0" * 32,
    )
    assert decision.admitted is False
    assert "AUTHORIZATION_ID_MISMATCH" in decision.reason_codes
    assert check.authorization_id and check.authorization_id != "0" * 32


# ------------------------------------------------------------ lifecycle evidence trail


def test_every_transition_appends_one_evidence_record_with_ids_and_utc_timestamps(tmp_path):
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    _walk_to_ack(fixture)
    steps = [
        guard.record_position_tracked(authority=authority_for(fixture, now=_seconds(4)),
                                      broker_position_id="111", now_utc=_seconds(4)),
        guard.record_position_closed(authority=authority_for(fixture, now=_seconds(5)),
                                     broker_deal_id="333", broker_order_id="111", now_utc=_seconds(5)),
        guard.reconcile(authority=authority_for(fixture, now=_seconds(6)),
                        reconciliation={"reconciled": True, "terminal_result": "FILLED",
                                        "broker_order_id": "111", "broker_deal_id": "333",
                                        "broker_position_id": "111"}, now_utc=_seconds(6)),
    ]
    assert [step.admitted for step in steps] == [True] * 3
    assert _trail(guard) == list(LIFECYCLE_STATES)

    rows = [row for row in fixture["store"].outcomes(TICKET_ID) if row["outcome_kind"] == LIFECYCLE_KIND]
    assert len(rows) == len(LIFECYCLE_STATES)
    previous = None
    for row, state, prior in zip(rows, LIFECYCLE_STATES, (None,) + LIFECYCLE_STATES):
        payload = row["payload"]
        assert row["result"] == state and payload["state"] == state
        assert row["ticket_id"] == payload["ticket_id"] == TICKET_ID
        assert payload["prior_state"] == prior
        assert payload["authority_id"]
        # UTC, aware, and never going backwards.
        assert payload["transitioned_at_utc"] == row["recorded_at_utc"]
        assert row["recorded_at_utc"].endswith("+00:00")
        assert previous is None or row["recorded_at_utc"] >= previous
        previous = row["recorded_at_utc"]
        assert payload["evidence"]["ready_evidence_id"] == evidence_id_map(fixture["authority"])[
            "ready_evidence_id"]

    by_state = {row["payload"]["state"]: row["payload"] for row in rows}
    assert by_state[BROKER_ACK]["broker_order_id"] == "111"
    assert by_state[BROKER_ACK]["broker_deal_id"] == "222"
    assert by_state[POSITION_TRACKED]["broker_position_id"] == "111"
    assert by_state[CLOSED]["broker_deal_id"] == "333"
    assert by_state[RECONCILED]["terminal_result"] == "FILLED"
    assert by_state[RECONCILED]["broker_order_id"] == "111"
    # The broker-facing steps are bound to the single-use authorization the guard issued.
    assert by_state[CHECKED]["authorization_id"] == by_state[AUTHORIZED]["authorization_id"]
    assert by_state[SENT]["authorization_id"] != by_state[AUTHORIZED]["authorization_id"]
    assert by_state[BROKER_ACK]["authorization_id"] == by_state[SENT]["authorization_id"]
    # The pre-broker steps carry no broker identifier, and say so explicitly.
    assert by_state[AUTHORIZED]["broker_order_id"] is None
    assert by_state[SENT]["broker_deal_id"] is None


def test_lifecycle_evidence_never_disturbs_the_duplicate_claim_ledger(tmp_path):
    fixture = boundary(tmp_path)
    _walk_to_send(fixture)
    # The claim ledger must still see only its own rows: no EXECUTION_LEDGER_UNKNOWN_STATE.
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).reason_code == "HALT_UNCERTAIN_SEND"
    assert _kinds(fixture["store"]).count("DEMO_EXECUTION_SENDING") == 1


def test_the_lifecycle_ledger_only_accepts_the_next_state(tmp_path):
    lifecycle = ExecutionLifecycle(TicketStore(str(tmp_path / "store")))
    append = lifecycle.append

    assert append(TICKET_ID, CHECKED, now_utc=NOW, authority_id="a1",
                  authorization_id="z1").reason_code == "LIFECYCLE_ORDER_INVALID"
    assert append(TICKET_ID, AUTHORIZED, now_utc=NOW, authority_id="a1").reason_code \
        == "LIFECYCLE_AUTHORIZATION_ID_MISSING"
    assert append(TICKET_ID, "INVENTED", now_utc=NOW, authority_id="a1").reason_code \
        == "LIFECYCLE_STATE_UNKNOWN"
    assert append(TICKET_ID, HALT, now_utc=NOW, authority_id="a1").reason_code \
        == "LIFECYCLE_HALT_REASON_MISSING"
    assert append("", AUTHORIZED, now_utc=NOW, authority_id="a1").reason_code == "TICKET_ID_MISSING"
    assert append(TICKET_ID, AUTHORIZED, now_utc=None, authority_id="a1").reason_code \
        == "LIFECYCLE_TIMESTAMP_INVALID"

    first = append(TICKET_ID, AUTHORIZED, now_utc=NOW, authority_id="a1", authorization_id="z1")
    assert first.recorded and first.prior_state is None
    assert append(TICKET_ID, AUTHORIZED, now_utc=_seconds(1), authority_id="a2",
                  authorization_id="z2").reason_code == "LIFECYCLE_ORDER_INVALID"      # repeat
    assert append(TICKET_ID, SENT, now_utc=_seconds(1), authority_id="a2",
                  authorization_id="z2").reason_code == "LIFECYCLE_ORDER_INVALID"       # skip
    assert append(TICKET_ID, CHECKED, now_utc=NOW - timedelta(seconds=1), authority_id="a2",
                  authorization_id="z1").reason_code == "LIFECYCLE_TIMESTAMP_OUT_OF_ORDER"
    assert append(TICKET_ID, RECONCILED, now_utc=_seconds(1), authority_id="a2",
                  terminal_result="UNKNOWN").reason_code == "RECONCILIATION_EVIDENCE_INVALID"

    assert append(TICKET_ID, CHECKED, now_utc=_seconds(1), authority_id="a2",
                  authorization_id="z1").recorded is True
    assert append(TICKET_ID, SENT, now_utc=_seconds(2), authority_id="a3",
                  authorization_id="z2").recorded is True
    assert append(TICKET_ID, BROKER_ACK, now_utc=_seconds(3), authority_id="a4",
                  authorization_id="z2").reason_code == "LIFECYCLE_BROKER_EVIDENCE_MISSING"
    assert append(TICKET_ID, BROKER_ACK, now_utc=_seconds(3), authority_id="a4", authorization_id="z2",
                  broker_order_id="111", broker_deal_id="222").recorded is True
    assert append(TICKET_ID, POSITION_TRACKED, now_utc=_seconds(4), authority_id="a5").reason_code \
        == "LIFECYCLE_BROKER_EVIDENCE_MISSING"
    assert append(TICKET_ID, POSITION_TRACKED, now_utc=_seconds(4), authority_id="a5",
                  broker_position_id="111").recorded is True
    assert append(TICKET_ID, CLOSED, now_utc=_seconds(5), authority_id="a6",
                  broker_deal_id="333").recorded is True
    assert append(TICKET_ID, RECONCILED, now_utc=_seconds(6), authority_id="a7",
                  terminal_result="FILLED").reason_code == "LIFECYCLE_BROKER_EVIDENCE_MISSING"
    assert append(TICKET_ID, RECONCILED, now_utc=_seconds(6), authority_id="a7",
                  terminal_result="FILLED", broker_order_id="111").recorded is True
    assert append(TICKET_ID, HALT, now_utc=_seconds(7), authority_id="a8",
                  reason_code="TOO_LATE").reason_code == "LIFECYCLE_ALREADY_RECONCILED"
    assert [row.state for row in lifecycle.trail(TICKET_ID).states] == list(LIFECYCLE_STATES)


def test_a_halted_trail_only_accepts_reconciliation(tmp_path):
    lifecycle = ExecutionLifecycle(TicketStore(str(tmp_path / "store")))
    lifecycle.append(TICKET_ID, AUTHORIZED, now_utc=NOW, authority_id="a1", authorization_id="z1")
    halted = lifecycle.append(TICKET_ID, HALT, now_utc=_seconds(1), authority_id="a2",
                              reason_code="TRANSPORT_TIMEOUT")
    assert halted.recorded is True
    assert lifecycle.append(TICKET_ID, CHECKED, now_utc=_seconds(2), authority_id="a3",
                            authorization_id="z1").reason_code == "HALT_UNKNOWN_RESULT"
    assert lifecycle.append(TICKET_ID, HALT, now_utc=_seconds(2), authority_id="a3",
                            reason_code="AGAIN").reason_code == "HALT_UNKNOWN_RESULT"
    assert lifecycle.append(TICKET_ID, RECONCILED, now_utc=_seconds(3), authority_id="a4",
                            terminal_result="NOT_SUBMITTED").recorded is True


@pytest.mark.parametrize(("method", "kwargs", "reason"), [
    ("record_order_checked", {"checked_order": None}, "ORDER_CHECK_EVIDENCE_MISSING"),
    ("record_order_checked", {"checked_order": {}}, "ORDER_CHECK_EVIDENCE_MISSING"),
    ("record_position_tracked", {"broker_position_id": None}, "POSITION_EVIDENCE_MISSING"),
    ("record_position_tracked", {"broker_position_id": " "}, "POSITION_EVIDENCE_MISSING"),
    ("record_position_closed", {"broker_deal_id": None}, "CLOSE_EVIDENCE_MISSING"),
])
def test_a_transition_without_its_required_evidence_is_refused(tmp_path, method, kwargs, reason):
    fixture = boundary(tmp_path)
    guard, ticket = fixture["guard"], fixture["ticket"]
    if method == "record_order_checked":
        assert _check(fixture).admitted is True
        decision = getattr(guard, method)(authority=authority_for(fixture, now=_seconds(1)),
                                          ticket=ticket, now_utc=_seconds(1), **kwargs)
    else:
        _walk_to_ack(fixture)
        decision = getattr(guard, method)(authority=authority_for(fixture, now=_seconds(4)),
                                          now_utc=_seconds(4), **kwargs)
    assert decision.admitted is False
    assert reason in decision.reason_codes


@pytest.mark.parametrize("retcode", [10004, 10009, None, True])
def test_rejected_or_malformed_order_check_result_cannot_be_recorded_as_checked(tmp_path, retcode):
    fixture = boundary(tmp_path)
    assert _check(fixture).admitted is True
    result = dict(CHECKED_ORDER, retcode=retcode)
    decision = fixture["guard"].record_order_checked(
        authority=authority_for(fixture, now=_seconds(1)), ticket=fixture["ticket"],
        checked_order=result, now_utc=_seconds(1),
    )
    assert decision.admitted is False
    assert decision.reason_code == "ORDER_CHECK_RESULT_REJECTED"
    assert _trail(fixture["guard"]) == [AUTHORIZED]


def test_a_tampered_evidence_row_is_a_conflict_not_a_silent_pass(tmp_path):
    fixture = boundary(tmp_path)
    guard, store = fixture["guard"], fixture["store"]
    assert _check(fixture).admitted is True
    last = store.outcomes(TICKET_ID)[-1]
    path = Path(store.outcome_path(last))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row["outcome_kind"] == LIFECYCLE_KIND:
            row["payload"]["state"] = RECONCILED          # breaks the record seal
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    decision = guard.record_order_checked(authority=authority_for(fixture, now=_seconds(1)),
                                          ticket=fixture["ticket"], checked_order=CHECKED_ORDER,
                                          now_utc=_seconds(1))
    assert decision.admitted is False
    assert "LIFECYCLE_EVIDENCE_CONFLICT" in decision.reason_codes


# ------------------------------------------------------ unknown outcome: HALT + reconcile


def test_an_unknown_send_outcome_halts_and_is_never_resubmitted(tmp_path):
    fixture = boundary(tmp_path)
    guard, ticket = fixture["guard"], fixture["ticket"]
    _walk_to_send(fixture)
    assert "DEMO_EXECUTION_SENDING" in _kinds(fixture["store"])

    unknown = guard.record_broker_ack(authority=authority_for(fixture, now=_seconds(3)),
                                      send_result={"retcode": 10004}, now_utc=_seconds(3))
    assert (unknown.admitted, unknown.reason_code) == (False, "HALT_UNKNOWN_RESULT")
    assert unknown.details["halt_reason"] == "BROKER_ACK_IDENTIFIER_MISSING"
    assert unknown.details["action_required"] == "RECONCILE"
    assert unknown.details["resubmission"] == "NEVER"
    assert _trail(guard)[-1] == HALT
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).reason_code == "HALT_UNKNOWN_RESULT"

    for attempt in (
        _check(fixture, now=_seconds(4), authority=authority_for(fixture, now=_seconds(4))),
        guard.authorize_order_send(authority=authority_for(fixture, now=_seconds(5)), ticket=ticket,
                                   checked_order=CHECKED_ORDER, now_utc=_seconds(5)),
    ):
        assert attempt.admitted is False
        assert "HALT_UNKNOWN_RESULT" in attempt.reason_codes
    assert _kinds(fixture["store"]).count("DEMO_EXECUTION_SENDING") == 1

    settled = guard.reconcile(
        authority=authority_for(fixture, now=_seconds(6)),
        reconciliation={"reconciled": True, "terminal_result": "NOT_SUBMITTED_NO_BROKER_IDENTIFIER"},
        now_utc=_seconds(6),
    )
    assert settled.admitted is True
    assert settled.details["resubmission"] == "NEVER"
    assert _trail(guard)[-2:] == [HALT, RECONCILED]
    # The halt stays permanent: the claim ledger still refuses, and nothing may follow RECONCILED.
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).reason_code == "HALT_UNKNOWN_RESULT"
    after = guard.record_position_tracked(authority=authority_for(fixture, now=_seconds(7)),
                                          broker_position_id="111", now_utc=_seconds(7))
    assert (after.admitted, after.reason_code) == (False, "LIFECYCLE_ALREADY_RECONCILED")


@pytest.mark.parametrize(("send_result", "halt_reason"), [
    ({"retcode": 10009, "order": 0, "deal": 0}, "BROKER_ACK_IDENTIFIER_MISSING"),
    ({"retcode": 10009, "order": "0", "deal": "000"}, "BROKER_ACK_IDENTIFIER_MISSING"),
    ({"retcode": 10004, "order": 123, "deal": 456}, "BROKER_SEND_NOT_ACCEPTED"),
])
def test_failed_send_result_cannot_be_recorded_as_broker_ack(tmp_path, send_result, halt_reason):
    fixture = boundary(tmp_path)
    _walk_to_send(fixture)
    decision = fixture["guard"].record_broker_ack(
        authority=authority_for(fixture, now=_seconds(3)), send_result=send_result, now_utc=_seconds(3),
    )
    assert (decision.admitted, decision.reason_code) == (False, "HALT_UNKNOWN_RESULT")
    assert decision.details["halt_reason"] == halt_reason
    assert _trail(fixture["guard"])[-1] == HALT
    assert BROKER_ACK not in _trail(fixture["guard"])


def test_halt_cannot_write_a_different_ticket_than_its_authority(tmp_path):
    fixture = boundary(tmp_path)
    _walk_to_send(fixture)
    other_ticket = f"{TICKET_ID}-other"
    decision = fixture["guard"].halt(
        authority=authority_for(fixture, now=_seconds(3)), ticket_id=other_ticket,
        reason_code="TRANSPORT_TIMEOUT", now_utc=_seconds(3),
    )
    assert (decision.admitted, decision.reason_code) == (False, "HALT_TICKET_MISMATCH")
    assert _trail(fixture["guard"])[-1] == SENT
    assert _trail(fixture["guard"], other_ticket) == []


def test_a_send_window_that_closes_without_a_reported_outcome_halts(tmp_path):
    fixture = boundary(tmp_path)
    _walk_to_send(fixture)
    late = NOW + timedelta(minutes=fixture["scope"].signal_expiry_minutes + 1)
    decision = fixture["guard"].record_broker_ack(authority=authority_for(fixture, now=late),
                                                  send_result=SEND_RESULT, now_utc=late)
    assert (decision.admitted, decision.reason_code) == (False, "HALT_UNKNOWN_RESULT")
    assert decision.details["halt_reason"] == "SEND_ACK_WINDOW_EXPIRED"
    assert _trail(fixture["guard"])[-1] == HALT


def test_an_unknown_reconciliation_result_is_refused_and_the_halt_stays(tmp_path):
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    _walk_to_send(fixture)
    guard.halt(authority=authority_for(fixture, now=_seconds(3)), ticket_id=TICKET_ID,
               reason_code="TRANSPORT_TIMEOUT", now_utc=_seconds(3))
    for reconciliation in ({"reconciled": True, "terminal_result": "UNKNOWN"},
                           {"reconciled": True, "terminal_result": "  "},
                           {"reconciled": False, "terminal_result": "FILLED"},
                           {"terminal_result": "FILLED"}, None):
        decision = guard.reconcile(authority=authority_for(fixture, now=_seconds(4)),
                                   reconciliation=reconciliation, now_utc=_seconds(4))
        assert decision.admitted is False
        assert "RECONCILIATION_EVIDENCE_INVALID" in decision.reason_codes
    assert _trail(guard)[-1] == HALT


def test_halt_requires_a_reason_and_records_it_with_the_ticket_id(tmp_path):
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    _walk_to_send(fixture)
    reasonless = guard.halt(authority=authority_for(fixture, now=_seconds(3)), ticket_id=TICKET_ID,
                            reason_code="  ", now_utc=_seconds(3))
    assert reasonless.admitted is False
    assert "HALT_REASON_MISSING" in reasonless.reason_codes

    halted = guard.halt(authority=authority_for(fixture, now=_seconds(4)), ticket_id=TICKET_ID,
                        reason_code="TRANSPORT_TIMEOUT", now_utc=_seconds(4))
    assert halted.reason_code == "HALT_UNKNOWN_RESULT"
    row = ExecutionLifecycle(fixture["store"]).trail(TICKET_ID).state_row(HALT)
    assert row is not None and row.reason_code == "TRANSPORT_TIMEOUT"
    assert row.evidence["halted_from"] == SENT

    again = guard.halt(authority=authority_for(fixture, now=_seconds(5)), ticket_id=TICKET_ID,
                       reason_code="TRANSPORT_TIMEOUT", now_utc=_seconds(5))
    assert (again.admitted, again.reason_code) == (False, "HALT_UNKNOWN_RESULT")
    assert _trail(guard).count(HALT) == 1


def test_post_trade_evidence_is_still_recorded_after_the_authorization_is_revoked(tmp_path):
    """Revoking authority must never strand an open position's evidence trail."""
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    _walk_to_ack(fixture)
    record = json.loads(fixture["auth_path"].read_text(encoding="utf-8"))
    record["emergency_stop"] = True
    fixture["auth_path"].write_text(json.dumps(record), encoding="utf-8")

    tracked = guard.record_position_tracked(authority=authority_for(fixture, now=_seconds(4)),
                                            broker_position_id="111", now_utc=_seconds(4))
    closed = guard.record_position_closed(authority=authority_for(fixture, now=_seconds(5)),
                                          broker_deal_id="333", now_utc=_seconds(5))
    assert (tracked.admitted, closed.admitted) == (True, True)
    assert _trail(guard)[-2:] == [POSITION_TRACKED, CLOSED]


def test_post_trade_calls_must_cite_the_evidence_that_authorized_the_order(tmp_path):
    fixture = boundary(tmp_path)
    guard = fixture["guard"]
    _walk_to_ack(fixture)
    forged = authority_for(fixture, now=_seconds(4))
    forged = replace(forged, risk_evidence=replace(forged.risk_evidence, evidence_id="f" * 64))
    decision = guard.record_position_tracked(authority=forged, broker_position_id="111",
                                             now_utc=_seconds(4))
    assert decision.admitted is False
    assert "RISK_EVIDENCE_ID_MISMATCH" in decision.reason_codes


# ------------------------------------------------------------------ static broker boundary


def test_the_demo_execution_package_never_calls_a_broker_api():
    forbidden_calls = {
        "order_send", "order_check", "order_modify", "order_cancel", "positions_get", "orders_get",
        "position_close", "position_modify", "history_orders_get", "history_deals_get",
        "symbol_select", "account_info", "initialize", "login", "execute_command",
    }
    for path in sorted((REPO / "src" / "demo_execution").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", None))
                assert name not in forbidden_calls, f"{path.name}:{node.lineno} calls {name}"
            if isinstance(node, ast.Import):
                assert not any(alias.name.split(".")[0] == "MetaTrader5" for alias in node.names), path.name
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] != "MetaTrader5", path.name
