from __future__ import annotations

import json
from pathlib import Path

from host_delivery import telegram_message
from telegram_delivery.adapter import render_summary, render_ticket
from test_manual_ticket_build import META, OWNER, manual
from v1_tickets.manual_ticket import render_text


ROOT = Path(__file__).resolve().parents[1]


def test_unverified_logic_never_renders_ready_and_edge_is_explicit():
    legacy = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
        "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1",
        "symbol": "EURUSD", "cycle": "ASIAN_LONDON", "session_date": "2026-10-08",
        "decision": "READY", "direction": "LONG", "entry": 1.1, "stop_loss": 1.099,
        "targets": [],
    }
    legacy_message = telegram_message.format_ticket(legacy)
    assert "decision=NOT_READY" in legacy_message
    assert "logic_status: NOT_VERIFIED" in legacy_message
    assert "EDGE_VERIFIED=FALSE" in legacy_message

    fixture_path = ROOT / "tests/fixtures/telegram_delivery/tickets.json"
    canonical = next(t for t in json.loads(fixture_path.read_text()) if t["decision"] == "WATCH_READY")
    canonical["logic_status"] = "NOT_VERIFIED"
    canonical_message = render_ticket(canonical)
    assert "EURUSD | NOT_READY | LONG" in canonical_message
    assert "logic_status: NOT_VERIFIED" in canonical_message
    assert "EDGE_VERIFIED=FALSE" in canonical_message
    summary = render_summary([canonical])
    assert "| NOT_READY |" in summary
    assert "logic_status: NOT_VERIFIED" in summary and "EDGE_VERIFIED=FALSE" in summary

    ticket = manual(owner=OWNER, balance=10000.0, meta=META)
    ticket["state"] = "TICKET_READY"
    ticket["primary_block_reason"] = None
    ticket["block_reasons"] = []
    assert ticket["logic_status"] == "NOT_VERIFIED"
    manual_message = render_text(ticket)
    assert "State       TICKET_BLOCKED (LOGIC_STATUS_NOT_VERIFIED)" in manual_message
    assert "State       TICKET_READY" not in manual_message
    assert "logic_status: NOT_VERIFIED" in manual_message
    assert "EDGE_VERIFIED=FALSE" in manual_message
