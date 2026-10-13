"""AGP-TQ-D1: FAIL_CLOSED_IF_TP1_BEYOND_TP2 at the canonical S1 READY boundary and the execution handoff.

Before: actionability could return WATCH_READY for inverted targets (USDJPY 12760: TP1 5.607R beyond TP2
5.0R), zero risk or missing targets, and demo admission never checked target geometry.
After: both boundaries fail closed through v1_tickets.target_geometry. Synthetic fixtures only.
"""
from __future__ import annotations

import datetime as dt

import pytest
from test_actionability_and_canonical_ticket import (
    SIGNED_POLICY,
    _build_asian_london_sweep,
)

from v1_tickets import actionability as A
from v1_tickets import fx as v1_fx
from v1_tickets import target_geometry as G
from v1_tickets.canonical_ticket import build_canonical_ticket

UTC = dt.timezone.utc


@pytest.mark.parametrize("entry,sl,tp1,tp2,direction,expected", [
    (158.182, 158.121, 158.400, 158.487, "LONG", None),
    (158.182, 158.121, 158.487, 158.487, "LONG", None),                       # TP1 == TP2 allowed
    (158.182, 158.121, 158.524, 158.487, "LONG", G.TARGET_ORDER_INVALID),     # real 12760 inversion
    (1.3000, 1.3010, 1.2980, 1.2950, "SHORT", None),
    (1.3000, 1.3010, 1.2940, 1.2950, "SHORT", G.TARGET_ORDER_INVALID),
    (1.3000, 1.3000, 1.3020, 1.3050, "LONG", G.NON_POSITIVE_RISK),
    (1.3000, 1.3010, 1.3020, 1.3050, "LONG", G.NON_POSITIVE_RISK),            # stop on the wrong side
    (1.3000, 1.2990, 1.2995, 1.3050, "LONG", G.TP1_SIDE_INVALID),
    (1.3000, 1.2990, None, 1.3050, "LONG", G.INCOMPLETE),
    (1.3000, 1.2990, "x", 1.3050, "LONG", G.INCOMPLETE),
    (1.3000, 1.2990, float("nan"), 1.3050, "LONG", G.INCOMPLETE),
    (1.3000, 1.2990, 1.3020, 1.3050, None, G.DIRECTION_INVALID),
])
def test_validator(entry, sl, tp1, tp2, direction, expected):
    assert G.geometry_violation(entry, sl, tp1, tp2, direction) == expected


def test_ticket_levels_read_targets_legs():
    t = {"entry": 1.3, "stop_loss": 1.29, "direction": "LONG",
         "targets": [{"leg": 1, "price": 1.32}, {"leg": 2, "price": 1.31}]}
    assert G.ticket_geometry_violation(t) == G.TARGET_ORDER_INVALID
    assert G.ticket_geometry_violation({**t, "targets": []}) == G.INCOMPLETE


def _fresh_ready_ticket(now):
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    return v1_fx.build_fx_ticket("EURUSD", "ASIAN_LONDON", now.date(), ref, n, post, data_source="TEST",
                                 evaluated_at=now, data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001)


def test_valid_geometry_still_reaches_watch_ready(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    canon = build_canonical_ticket(_fresh_ready_ticket(now), now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["decision"] == A.WATCH_READY


@pytest.mark.parametrize("mutate,reason", [
    (lambda t: t["targets"].reverse() or [leg.update(leg=i + 1) for i, leg in enumerate(t["targets"])],
     G.TARGET_ORDER_INVALID),
    (lambda t: t.update(targets=[]), G.INCOMPLETE),
    (lambda t: t.update(stop_loss=t["entry"]), G.NON_POSITIVE_RISK),
])
def test_invalid_geometry_never_becomes_watch_ready(stub_symbol_verified, mutate, reason):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ticket = _fresh_ready_ticket(now)
    assert ticket["decision"] == "READY"
    mutate(ticket)
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["decision"] == A.BLOCKED and canon["reason_code"] == reason
    assert canon["execution_authorization"] is False


def _gates(inputs):
    from demo_execution.admission import evaluate_pre_send_gates
    return evaluate_pre_send_gates(inputs["ticket"], inputs["market"], inputs["risk_snapshot"],
                                   now_utc=inputs["now"], authorization_path=str(inputs["auth_path"]),
                                   scope=inputs["scope"], ticket_store=inputs["ticket_store"])


def test_demo_admission_refuses_inverted_or_missing_targets(tmp_path):
    from test_demo_execution_gates import _pre_send_inputs

    inputs = _pre_send_inputs(tmp_path)
    assert _gates(inputs).admitted is True                  # fixture with valid targets
    for targets, reason in (([{"leg": 1, "price": 1.3061}, {"leg": 2, "price": 1.3051}], G.TARGET_ORDER_INVALID),
                            ([], G.INCOMPLETE)):
        bad = {**inputs, "ticket": {**inputs["ticket"], "targets": targets}}
        result = _gates(bad)
        assert result.admitted is False and reason in result.block_reasons
