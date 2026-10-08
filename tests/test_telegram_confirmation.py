"""Manual Telegram confirmations are append-only and never call a broker."""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from host_delivery import telegram_confirm as confirm
from v1_tickets.code_identity import code_sha
from v1_tickets.owner_decision import load_decisions
from v1_tickets.scan_record import append_jsonl

UTC = dt.timezone.utc
SECRET = "test-secret-only"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    journal = str(tmp_path / "journal")
    ticket = {"ticket_id": "ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|2026-10-08",
              "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1", "code_sha": code_sha(),
              "symbol": "EURUSD", "session": "ASIAN_LONDON", "state": "TICKET_READY", "direction": "LONG",
              "entry": 1.1, "sl": 1.09, "tp1": 1.12, "tp2": 1.15, "risk_distance": .01,
              "spread": .0001, "logic_status": "LOGIC_VERIFIED", "logic_gate": {"L6": {"status": "PASS"}},
              "data_freshness_s": 42.5,
              "valid_until": "2026-10-08T12:00:00+00:00", "session_date": "2026-10-08", "content_hash": "x"}
    path = Path(journal, "ticket_delivery", "manual", "tickets", "2026-10-08.jsonl")
    append_jsonl(str(path), ticket)
    return journal, ticket


def _cb(ticket, action):
    return confirm.callback_data(ticket, action, SECRET)


def test_confirm_message_uses_only_canonical_fields_and_buttons_only_for_ready(ready):
    _, ticket = ready
    rendered, keyboard = confirm.render_confirmation(ticket, SECRET)
    assert "NOT EDGE-VERIFIED" in rendered
    assert "Freshness 42.5s; L6 PASS" in rendered
    assert "Entry 1.1 | SL 1.09 | TP1 1.12 | TP2 1.15" in rendered
    assert "WHY:" not in rendered and "branch" not in rendered
    assert all(len(button["callback_data"]) <= 64 for button in keyboard["inline_keyboard"][0])
    with pytest.raises(ValueError, match="TICKET_READY"):
        confirm.render_confirmation({**ticket, "state": "WATCH"}, SECRET)


def test_unauthorized_chat_and_tampered_callback_do_not_record(ready):
    journal, ticket = ready
    callback = _cb(ticket, "accept")
    refused = confirm.handle_callback(callback=callback, chat_id="other", journal=journal,
                                      now=dt.datetime(2026, 10, 8, 10, tzinfo=UTC), secret=SECRET,
                                      chat_allowlist={"owner"})
    tampered = confirm.handle_callback(callback=callback[:-1] + ("A" if callback[-1] != "A" else "B"),
                                       chat_id="owner", journal=journal,
                                       now=dt.datetime(2026, 10, 8, 10, tzinfo=UTC), secret=SECRET,
                                       chat_allowlist={"owner"})
    assert "not authorized" in refused and "signature is invalid" in tampered
    assert load_decisions(journal) == {}


def test_accept_is_idempotent_and_stays_blocked_when_execution_flag_is_off(ready, monkeypatch):
    journal, ticket = ready
    # The forbidden MT5 order-send sentinel makes any attempted broker call observable.
    import mt5
    calls = []
    monkeypatch.setattr(mt5, "order_send", lambda *a, **kw: calls.append((a, kw)), raising=False)
    monkeypatch.setattr(mt5, "order_check", lambda *a, **kw: calls.append((a, kw)), raising=False)
    config_root = ready[0] + "-config"
    Path(config_root, "strategies").mkdir(parents=True)
    Path(config_root, "config").mkdir()
    Path(config_root, "strategies/registry.yaml").write_text(
        "strategies:\n  ST_ASIAN_SWEEP_5R_V1:\n    demo_authorized: true\n", encoding="utf-8")
    Path(config_root, "config/trading.yaml").write_text(
        "execution:\n  allow_order_send: false\n", encoding="utf-8")
    first = confirm.handle_callback(callback=_cb(ticket, "accept"), chat_id="owner", journal=journal,
                                    now=dt.datetime(2026, 10, 8, 10, tzinfo=UTC), secret=SECRET,
                                    chat_allowlist={"owner"}, root=config_root)
    second = confirm.handle_callback(callback=_cb(ticket, "accept"), chat_id="owner", journal=journal,
                                     now=dt.datetime(2026, 10, 8, 10, 1, tzinfo=UTC), secret=SECRET,
                                     chat_allowlist={"owner"}, root=config_root)
    decisions = load_decisions(journal)
    assert "EXECUTION_ORDER_SEND_DISABLED" in first and "EXECUTION_ORDER_SEND_DISABLED" in second
    assert len(decisions) == 1 and decisions[ticket["ticket_id"]]["decision"] == "ACCEPTED"
    assert calls == []


def test_expired_and_host_offline_callbacks_fail_closed(ready):
    journal, ticket = ready
    expired = confirm.handle_callback(callback=_cb(ticket, "reject"), chat_id="owner", journal=journal,
                                      now=dt.datetime(2026, 10, 8, 12, tzinfo=UTC), secret=SECRET,
                                      chat_allowlist={"owner"})
    offline = confirm.handle_callback(callback=_cb(ticket, "reject"), chat_id="owner", journal=journal,
                                      now=dt.datetime(2026, 10, 8, 11, tzinfo=UTC), secret=SECRET,
                                      host_online=False, chat_allowlist={"owner"})
    assert "ticket has expired" in expired and "host is offline" in offline
    assert load_decisions(journal) == {}


def test_reject_is_recorded_without_handoff(ready):
    journal, ticket = ready
    reply = confirm.handle_callback(callback=_cb(ticket, "reject"), chat_id="owner", journal=journal,
                                    now=dt.datetime(2026, 10, 8, 10, tzinfo=UTC), secret=SECRET,
                                    chat_allowlist={"owner"}, root=str(ROOT))
    assert reply == "Rejected and recorded; no execution handoff was made."
    assert load_decisions(journal)[ticket["ticket_id"]]["decision"] == "REJECTED"


def test_telegram_update_replies_with_blocked_reason(ready, monkeypatch):
    journal, ticket = ready
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock-token")
    monkeypatch.setattr(confirm, "allowed_chat_ids", lambda root: frozenset({"owner"}))

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    class Session:
        def __init__(self):
            self.posts = []

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return Response()

    session = Session()
    update = {"callback_query": {"id": "cb-1", "data": confirm.callback_data(ticket, "accept", "mock-token"),
                                  "message": {"chat": {"id": "owner"}}}}
    result = confirm.process_callback_update(update, journal=journal,
                                             now=dt.datetime(2026, 10, 8, 10, tzinfo=UTC),
                                             root=str(ROOT), session=session)
    assert "BLOCKED_NOT_AUTHORIZED" in result
    assert len(session.posts) == 1 and session.posts[0][0].endswith("/answerCallbackQuery")
    assert "BLOCKED_NOT_AUTHORIZED" in session.posts[0][1]["data"]["text"]


def test_confirmation_module_is_statically_broker_free_and_runtime_has_zero_order_calls():
    path = ROOT / "src/host_delivery/telegram_confirm.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"execution", "mt5", "mt5_gateway", "order_send", "order_check", "broker"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in {"order_send", "order_check", "execute"} for node in ast.walk(tree))

