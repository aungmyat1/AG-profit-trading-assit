from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from test_manual_ticket_build import META, OWNER, manual

from host_delivery import telegram_message
from telegram_delivery.adapter import render_summary, render_ticket
from v1_tickets.authority import registry_display_status
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
    assert "READY" not in legacy_message
    assert "decision=RESEARCH" in legacy_message
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


def test_research_registry_ticket_has_no_ready_token_and_admitted_fixture_is_unchanged(monkeypatch):
    ticket = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
        "strategy_id": "ST_LIQUIDITY_SWEEP_RETEST_V1", "strategy_version": "2.0.0",
        "symbol": "BTCUSDT", "cycle": "CRYPTO", "observation_date": "2026-10-10",
        "decision": "READY", "direction": "LONG",
    }
    research_text = telegram_message.format_ticket(ticket)
    assert "READY" not in research_text
    assert "decision=RESEARCH" in research_text
    assert "ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0" in research_text

    # Test-only registry fixture: explicit admission keeps the established READY message.
    admitted_registry = {ticket["strategy_id"]: {
        "registered": True, "research": False, "admitted": True, "version": "2.0.0",
    }}
    monkeypatch.setattr(
        telegram_message, "registry_display_status",
        lambda sid, version: registry_display_status(
            sid, version, registry=admitted_registry,
        ),
    )
    monkeypatch.setattr(telegram_message, "resolve_ticket_authority",
                        lambda *_a, **_kw: SimpleNamespace(logic_status_effective="LOGIC_VERIFIED"))
    admitted_text = telegram_message.format_ticket(ticket)
    assert admitted_text == research_text.replace("decision=RESEARCH", "decision=READY").replace(
        "logic_status: NOT_VERIFIED", "logic_status: LOGIC_VERIFIED",
    )
