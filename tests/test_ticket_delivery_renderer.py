"""WP2 tests (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md)."""
from __future__ import annotations

import copy

import pytest

from ticket_delivery.renderer import (
    DECISION_BLOCKED,
    DECISION_DATA_ERROR,
    DECISION_NO_TRADE,
    DECISION_READY,
    DECISION_WATCH,
    INFORMATIONAL_LABEL,
    REASON_MISSING_FIELDS,
    REASON_NOT_READY,
    format_message_text,
    payload_hash,
    render_informational_ticket,
)


def _full_proposal():
    return {
        "application": {"release_id": "AG_TRADE_ASSISTANT_V1_0_3", "release_fingerprint": "abc123"},
        "strategy": {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1", "strategy_fingerprint": "def456"},
        "identity": {"ledger_slot": 0, "proposal_id": "PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-07", "setup_id": "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-07"},
        "market": {"symbol": "EURUSD", "direction": "SHORT", "setup_type": "SWEEP", "ready_at": "2026-09-07T07:45:00+00:00"},
        "session": {"asian_high": 1.0850, "asian_low": 1.0820, "asian_mid": 1.0835, "asian_range": 0.0030, "swept_level": 1.0850, "snapshot_id": "snap-1"},
        "entry": {"entry": 1.0822, "stop_loss": 1.0852, "tp1": 1.0792, "tp2": 1.0762},
        "allocation": {"tp1_pct": 75, "runner_pct": 25},
        "risk": {"risk_percent": 0.5, "risk_amount": 5.0, "raw_volume": 0.06, "normalized_volume": 0.05, "estimated_loss_at_sl": 5.0},
        "portfolio": {"daily_slots_used": "1/2", "aggregate_open_risk_pct": 0.5},
        "timing": {"created_at": "2026-09-07T07:45:00+00:00", "expires_at": "2026-09-07T11:00:00+00:00"},
        "evidence": {"reason_codes": ["UPPER_SWEEP_STRICT_PENETRATION"], "evidence_snapshot_id": "ev-1"},
        "decision": "READY",
        "execution": {"status": "PROPOSAL_ONLY", "execution_authorized": False},
    }


def _render(decision_status=DECISION_READY, proposal=None):
    return render_informational_ticket(
        logical_ticket_id="ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|2026-09-07",
        cycle="ASIAN_LONDON", trading_date="2026-09-07", decision_status=decision_status,
        proposal=proposal if proposal is not None else _full_proposal(),
    )


def test_complete_ready_rendering():
    result = _render()
    assert result.status == "RENDERED"
    assert result.payload["label"] == INFORMATIONAL_LABEL
    assert result.payload["symbol"] == "EURUSD"
    assert result.payload["entry"] == 1.0822
    assert result.payload["authorization"]["execution_authorized"] is False
    assert result.payload_hash is not None


@pytest.mark.parametrize("decision_status", [DECISION_WATCH, DECISION_NO_TRADE, DECISION_DATA_ERROR, DECISION_BLOCKED])
def test_watch_no_trade_data_error_blocked_never_render(decision_status):
    result = _render(decision_status=decision_status)
    assert result.status == "BLOCKED"
    assert result.reason_code == REASON_NOT_READY
    assert result.payload is None


@pytest.mark.parametrize("path", [
    ("identity", "setup_id"), ("strategy", "strategy_id"), ("strategy", "strategy_version"),
    ("application", "release_id"), ("market", "symbol"), ("market", "direction"),
    ("entry", "entry"), ("entry", "stop_loss"), ("entry", "tp1"),
    ("risk", "risk_percent"), ("risk", "normalized_volume"),
    ("timing", "created_at"), ("timing", "expires_at"), ("evidence", "reason_codes"),
])
def test_each_mandatory_field_missing_individually_blocks_rendering(path):
    proposal = copy.deepcopy(_full_proposal())
    section, field = path
    proposal[section][field] = None
    result = _render(proposal=proposal)
    assert result.status == "BLOCKED"
    assert result.reason_code == REASON_MISSING_FIELDS
    assert ".".join(path) in result.missing_fields


def test_stable_serialization_and_payload_hash():
    r1 = _render()
    r2 = _render()
    assert r1.payload_hash == r2.payload_hash
    assert r1.payload == r2.payload


def test_different_proposal_content_changes_the_hash():
    r1 = _render()
    proposal2 = copy.deepcopy(_full_proposal())
    proposal2["entry"]["entry"] = 1.0999
    r2 = _render(proposal=proposal2)
    assert r1.payload_hash != r2.payload_hash


def test_strategy_version_and_release_binding_present_in_payload():
    result = _render()
    assert result.payload["strategy_version"] == "1.1.1"
    assert result.payload["application_release"] == "AG_TRADE_ASSISTANT_V1_0_3"


def test_source_proposal_dict_is_never_mutated():
    proposal = _full_proposal()
    snapshot = copy.deepcopy(proposal)
    render_informational_ticket(
        logical_ticket_id="x", cycle="ASIAN_LONDON", trading_date="2026-09-07",
        decision_status=DECISION_READY, proposal=proposal,
    )
    assert proposal == snapshot


def test_format_message_text_has_no_inline_keyboard_or_callback_shape():
    result = _render()
    text = format_message_text(result.payload)
    assert INFORMATIONAL_LABEL in text
    assert "callback_data" not in text
    assert "Execution authority: DISABLED" in text


def test_no_execution_imports_in_renderer_module():
    import inspect

    import ticket_delivery.renderer as renderer_module

    source = inspect.getsource(renderer_module)
    for forbidden in ("import execution", "from execution", "mt5_gateway", "management_gateway"):
        assert forbidden not in source
