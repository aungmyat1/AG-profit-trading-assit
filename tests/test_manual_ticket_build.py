"""Manual Trade Ticket V1 Phase 5: the MANUAL ticket on recorded sessions (offline, no MT5)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from mt5.symbol_resolver import SymbolMeta
from v1_tickets import manual_ticket as mt
from v1_tickets.authority import resolve_ticket_authority
from v1_tickets.logic_gate import PASS

from test_manual_ticket_logic_gate import replay  # noqa: E402  (shared recorded-session fixture)

UTC = dt.timezone.utc
META = SymbolMeta(symbol="EURUSD-VIP", tick_size=0.00001, tick_value=1.0, contract_size=100000, volume_min=0.01,
                  volume_max=100.0, volume_step=0.01, digits=5, point=0.00001)
UNSET = {"risk_pct": None, "risk_status": mt.RISK_CONFIG_MISSING, "cost_warn_R": None, "warn_status": "NOT_SET"}
OWNER = {"risk_pct": 0.5, "risk_status": "SET", "cost_warn_R": 0.25, "warn_status": "SET"}


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def manual(day="2026-06-17", at="07:20", owner=UNSET, **kw):
    d, w, now, session, post, _ = replay(day, at)
    return mt.build_manual_ticket("EURUSD", "ASIAN_LONDON", d, session, 24, post, now=now, data_close=now,
                                  spread=0.00002, owner=owner, **kw)     # 0.2 pip: inside the existing 15% gate


@pytest.fixture
def l2_pass(monkeypatch):
    """Test-only stub so the downstream READY/risk/expiry composition can be exercised; the
    real L2 fails on the frozen v1.1.1 divergences (see test_real_v1_1_1_ticket_is_blocked_by_l2)."""
    monkeypatch.setattr(mt, "l2_rule_conformance", lambda *a, **k: {"gate": "L2", "status": PASS, "checks": []})


def test_real_v1_1_1_ticket_is_blocked_by_l2_and_renders_not_set_fields():
    t = manual()
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == "LOGIC_GATE_FAIL:L2"
    assert t["owner_accept_allowed"] is False and t["logic_status"] == "NOT_VERIFIED"
    assert t["invariants"] == {"order_ready": False, "broker_authorized": False, "edge_verified": False,
                               "orders_sent_by_system": 0}
    assert t["lot_size"] == "OWNER RISK % NOT SET" and t["risk_status"] == "RISK_CONFIG_MISSING"
    assert t["cost_warn_R"] == "WARN LEVEL NOT SET"
    text = mt.render_text(t)
    lines = text.splitlines()
    assert lines[0] == "AG TRADE TICKET — MANUAL DECISION"
    assert lines[1].startswith(f"#{t['ticket_id']}  Strategy ST_ASIAN_SWEEP_5R_V1@1.1.1  Session ASIAN_LONDON")
    assert "Logic gate  L1 ✓ L2 ✗ L3 ✓ L4 ✓ L5 ⚠ L6 ✓" in text
    assert "Edge status NOT VERIFIED — logic only" in text and "Authority   MANUAL — no automatic order" in text
    assert "EURUSD LONG" in text and "WHY: context" in text and "ORDER FIELDS: type MARKET" in text
    assert "OWNER RISK % NOT SET" in text and "WARN LEVEL NOT SET" in text and "VALID UNTIL" in text


def test_same_day_replay_twice_gives_identical_tickets():
    a, b = manual(), manual()
    assert a == b and mt.content_hash(a) == mt.content_hash(b)


def test_no_setup_day_renders_without_order_fields():
    t = manual("2026-06-15", "11:00")
    assert t["state"] == "NO_SETUP" and t["logic_gate"] == {} and "no setup" in mt.render_text(t)


def test_unset_owner_risk_blocks_with_explicit_not_set(l2_pass):
    t = manual(balance=10000.0, meta=META)
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == "RISK_CONFIG_MISSING"
    assert t["lot_size"] == "OWNER RISK % NOT SET"


def test_owner_risk_set_gives_manual_ticket_ready(l2_pass):
    t = manual(owner=OWNER, balance=10000.0, meta=META)
    assert t["state"] == "TICKET_READY" and t["owner_accept_allowed"] is True and t["ticket_status"] == "READY"
    assert t["lot_size"] == pytest.approx(3.57) and t["risk"]["risk_amount"] <= 50.0
    assert t["valid_until"] == "2026-06-17T07:30:00+00:00" and t["rr_tp2"] == 5.0
    assert t["invariants"]["order_ready"] is False and t["edge_status"] == "NOT VERIFIED — logic only"


@pytest.mark.parametrize("balance,meta,status", [(None, META, "ACCOUNT_BALANCE_UNAVAILABLE"),
                                                 (10000.0, None, "SYMBOL_METADATA_MISSING")])
def test_lot_inputs_missing_block(l2_pass, balance, meta, status):
    t = manual(owner=OWNER, balance=balance, meta=meta)
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == status


def test_expired_ticket_cannot_be_accepted(l2_pass):
    t = manual(at="07:31", owner=OWNER, balance=10000.0, meta=META)
    assert t["ticket_status"] == "EXPIRED" and t["owner_accept_allowed"] is False and t["state"] != "TICKET_READY"


def test_strategy_without_manual_authority_is_opportunity_only(l2_pass):
    other = resolve_ticket_authority("ST_LARGE_SMC_V1", "1.0.7")
    t = manual(owner=OWNER, balance=10000.0, meta=META, authority=other)
    assert t["state"] == "OPPORTUNITY" and t["owner_accept_allowed"] is False


@pytest.mark.parametrize("body,expected", [
    (None, None), ("owner_ticket:\n  risk_pct: null\n", None), ("owner_ticket:\n  risk_pct: abc\n", None),
    ("owner_ticket:\n  risk_pct: 0\n", None), ("owner_ticket:\n  risk_pct: -1\n", None),
    ("owner_ticket:\n  risk_pct: true\n", None), ("owner_ticket: [1]\n", None), (":::bad", None),
    ("owner_ticket:\n  risk_pct: 0.5\n  cost_warn_R: 0.2\n", 0.5),
])
def test_owner_config_has_no_default(tmp_path, body, expected):
    if body is not None:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "owner_ticket.yaml").write_text(body)
    cfg = mt.load_owner_config(tmp_path)
    assert cfg["risk_pct"] == expected
    assert cfg["risk_status"] == ("SET" if expected else mt.RISK_CONFIG_MISSING)


def test_repo_owner_config_is_unset_and_never_falls_back_to_trading_yaml():
    cfg = mt.load_owner_config()
    if not (Path(mt.REPO_ROOT) / mt.OWNER_CONFIG_LOCAL).exists():
        assert cfg["risk_pct"] is None and cfg["cost_warn_R"] is None
    assert "trading.yaml" not in Path(mt.__file__).read_text().replace("config/trading.yaml risk", "")


def test_scheduled_run_archives_manual_ticket_and_records_its_state(tmp_path, monkeypatch):
    from test_host_go_live_kit import NOW as HOST_NOW, _vip_record, fake_fetch, smoke
    from v1_tickets.scan_record import read_jsonl, scan_path

    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    for canonical in ("EURUSD", "GBPUSD"):
        _vip_record(canonical, str(tmp_path / "evidence"))
    journal = str(tmp_path / "j")
    calls = []
    smoke.run_fx(fake_fetch(), HOST_NOW, journal, gated=False, notify=False,
                 quote=lambda b: (1.1000, 1.1001), balance=lambda: calls.append(1) or 10000.0)
    assert len(calls) == 1                                                   # balance read once per run
    rows = read_jsonl(scan_path(journal, HOST_NOW.date()))
    eur = [r for r in rows if r["symbol"] == "EURUSD" and r["strategy"].startswith("ST_ASIAN")]
    assert eur and all(r["state"] in ("NO_SETUP", "WATCH", "TICKET_BLOCKED", "TICKET_READY") for r in eur)
    tickets = read_jsonl(mt.ticket_path(journal, HOST_NOW.date()))
    assert tickets and all(t["invariants"]["order_ready"] is False for t in tickets)
    assert {t["state"] for t in tickets} <= {"NO_SETUP", "WATCH", "TICKET_BLOCKED", "TICKET_READY"}
