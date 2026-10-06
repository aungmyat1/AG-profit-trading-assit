"""Manual Trade Ticket V1 Phase 5: the MANUAL ticket on recorded sessions (offline, no MT5)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from mt5.symbol_resolver import SymbolMeta
from v1_tickets import manual_ticket as mt
from v1_tickets.authority import resolve_ticket_authority
from v1_tickets.guards import LEGACY_STALE_SIGNAL
from v1_tickets.logic_gate import PASS

from test_manual_ticket_logic_gate import replay  # noqa: E402  (shared recorded-session fixture)

UTC = dt.timezone.utc
META = SymbolMeta(symbol="EURUSD-VIP", tick_size=0.00001, tick_value=1.0, contract_size=100000, volume_min=0.01,
                  volume_max=100.0, volume_step=0.01, digits=5, point=0.00001)
UNSET = {"risk_pct": None, "risk_status": mt.RISK_CONFIG_MISSING, "cost_warn_R": None, "warn_status": "NOT_SET"}
OWNER = {"risk_pct": 0.5, "risk_status": "SET", "cost_warn_R": 0.25, "warn_status": "SET"}
# READY-path composition uses 2026-06-23 (SHORT): L3 passes there. 2026-06-17 (LONG) fails L3.target_order
# (TP1 box high 1.16160 is beyond TP2 1.16145 at 5R) -- the A1 regression on recorded data.
READY_DAY = "2026-06-23"


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
    assert t["state"] == "TICKET_BLOCKED" and t["primary_block_reason"] == "LOGIC_GATE_FAIL:L2"
    assert t["block_reasons"] == ["LOGIC_GATE_FAIL:L2", "LOGIC_GATE_FAIL:L3", "RISK_CONFIG_MISSING"]
    assert t["warnings"] == ["L5_WARN"]
    assert t["stop_reason"] == t["primary_block_reason"]
    assert t["owner_accept_allowed"] is False and t["logic_status"] == "NOT_VERIFIED"
    assert t["invariants"] == {"order_ready": False, "broker_authorized": False, "edge_verified": False,
                               "orders_sent_by_system": 0}
    assert t["lot_size"] == "OWNER RISK % NOT SET" and t["risk_status"] == "RISK_CONFIG_MISSING"
    assert t["cost_warn_R"] == "WARN LEVEL NOT SET"
    text = mt.render_text(t)
    lines = text.splitlines()
    assert lines[0] == "AG TRADE TICKET — MANUAL DECISION"
    assert lines[1].startswith(f"#{t['ticket_id']}  Strategy ST_ASIAN_SWEEP_5R_V1@1.1.1  Session ASIAN_LONDON")
    assert "Logic gate  L1 ✓ L2 ✗ L3 ✗ L4 ✓ L5 ⚠ L6 ✓" in text
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
    t = manual(READY_DAY, "07:20", balance=10000.0, meta=META)
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == "RISK_CONFIG_MISSING"
    assert t["lot_size"] == "OWNER RISK % NOT SET"


def test_owner_risk_set_gives_manual_ticket_ready(l2_pass):
    t = manual(READY_DAY, "07:20", owner=OWNER, balance=10000.0, meta=META)
    assert t["state"] == "TICKET_READY" and t["owner_accept_allowed"] is True and t["ticket_status"] == "READY"
    assert t["primary_block_reason"] is None and t["block_reasons"] == [] and t["warnings"] == ["L5_WARN"]
    assert t["lot_size"] == pytest.approx(0.98) and t["risk"]["risk_amount"] <= 50.0
    assert t["valid_until"] == "2026-06-23T07:30:00+00:00" and t["rr_tp2"] == 5.0
    assert t["invariants"]["order_ready"] is False and t["edge_status"] == "NOT VERIFIED — logic only"


@pytest.mark.parametrize("balance,meta,status", [(None, META, "ACCOUNT_BALANCE_UNAVAILABLE"),
                                                 (10000.0, None, "SYMBOL_METADATA_MISSING")])
def test_lot_inputs_missing_block(l2_pass, balance, meta, status):
    t = manual(READY_DAY, "07:20", owner=OWNER, balance=balance, meta=meta)
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == status


def test_expired_ticket_cannot_be_accepted(l2_pass):
    t = manual(READY_DAY, "07:31", owner=OWNER, balance=10000.0, meta=META)
    assert t["ticket_status"] == "EXPIRED" and t["owner_accept_allowed"] is False and t["state"] != "TICKET_READY"


def test_strategy_without_manual_authority_is_opportunity_only(l2_pass):
    other = resolve_ticket_authority("ST_LARGE_SMC_V1", "1.0.7")
    t = manual(READY_DAY, "07:20", owner=OWNER, balance=10000.0, meta=META, authority=other)
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
    assert eur and all(r["state"] in ("NO_SETUP", "WATCH", "TICKET_BLOCKED", "TICKET_READY") for r in eur
                       if r["session"] == "ASIAN_LONDON")
    # 09:30 UTC: the LONDON_NEWYORK reference window (06:00-11:00) is still open -> lifecycle, not DATA_ERROR
    assert all(r["state"] == "REFERENCE_NOT_READY" and r["stage_reached"] == "SESSION"
               for r in eur if r["session"] == "LONDON_NEWYORK")
    tickets = read_jsonl(mt.ticket_path(journal, HOST_NOW.date()))
    assert tickets and all(t["invariants"]["order_ready"] is False for t in tickets)
    assert {t["state"] for t in tickets} <= {"NO_SETUP", "WATCH", "TICKET_BLOCKED", "TICKET_READY", "REFERENCE_NOT_READY"}


def test_pass_b_shape_l2_primary_with_signal_stale_secondary():
    """A2: a stale-signal sweep that also fails L2 reports L2 as primary, SIGNAL_STALE secondary
    (previously the single stop_reason was STALE_SIGNAL and hid the logic failure)."""
    t = manual(READY_DAY, "07:40", owner=OWNER, balance=10000.0, meta=META)
    assert t["state"] == "TICKET_BLOCKED" and t["primary_block_reason"] == "LOGIC_GATE_FAIL:L2"
    assert t["block_reasons"] == ["LOGIC_GATE_FAIL:L2", "SIGNAL_STALE", "TICKET_EXPIRED"]
    assert t["warnings"] == ["L5_WARN"]
    assert t["stage_reached"] == "LOGIC_GATE" and "also: SIGNAL_STALE" in mt.render_text(t)


def test_block_reason_precedence_tiers():
    from v1_tickets.logic_gate import is_blocking, order_block_reasons
    raw = ["L5_WARN", "TICKET_EXPIRED", "STALE_SIGNAL", "SPREAD_TOO_WIDE", "RISK_CONFIG_MISSING",
           "SYMBOL_METADATA_MISSING", "DATA_ERROR:MT5_DOWN", "LOGIC_GATE_FAIL:L3", "LOGIC_GATE_FAIL:L1", "L5_WARN"]
    assert order_block_reasons(raw) == [
        "LOGIC_GATE_FAIL:L3", "LOGIC_GATE_FAIL:L1", "SYMBOL_METADATA_MISSING", "DATA_ERROR:MT5_DOWN",
        "RISK_CONFIG_MISSING", "SPREAD_TOO_WIDE", "TICKET_EXPIRED", "SIGNAL_STALE"]   # L5_WARN dropped
    assert not is_blocking("L5_WARN") and is_blocking("SIGNAL_STALE")


def test_ticket_ready_has_no_block_reasons_and_l5_warning_only_in_warnings(l2_pass):
    """Owner decision 3 (2026-10-06): warnings[] is separate; TICKET_READY => block_reasons == []."""
    t = manual(READY_DAY, "07:20", owner=OWNER, balance=10000.0, meta=META)       # cost_warn_R 0.25, no commission
    assert t["state"] == "TICKET_READY" and t["logic_gate"]["L5"]["status"] == "WARN"
    assert t["block_reasons"] == [] and t["primary_block_reason"] is None and t["stop_reason"] is None
    assert t["warnings"] == ["L5_WARN"] and "warn: L5_WARN" in mt.render_text(t)


def test_ticket_ready_always_carries_usable_freshness_fields(l2_pass):
    """Host acceptance Phase 7: L6 is advisory, so READY must not depend on it -- every
    TICKET_READY carries a parseable valid_until in the future plus non-empty stale_if/invalid_if."""
    t = manual(READY_DAY, "07:20", owner=OWNER, balance=10000.0, meta=META)
    assert t["state"] == "TICKET_READY"
    valid_until = dt.datetime.fromisoformat(t["valid_until"])
    assert dt.datetime.fromisoformat(t["evaluated_at"]) < valid_until
    assert t["stale_if"] and t["stale_if"]["rule"] and t["stale_if"]["or_after"] == t["valid_until"]
    assert t["invalid_if"] and t["invalid_if"]["sl_touched_before_fill"] == t["sl"]
    assert t["invalid_if"]["time_invalidation_utc"]
    assert t["logic_gate"]["L6"]["status"] == PASS


def test_ticket_past_valid_until_is_never_ready(l2_pass):
    """valid_until = signal close + STALE_AFTER, the same threshold as the existing V1 stale guard.
    Precedence: at build time the signal aged out before any actionable ticket existed -> SIGNAL_STALE;
    TICKET_EXPIRED is reserved for an already-actionable ticket (backstop test below)."""
    t = manual(READY_DAY, "07:31", owner=OWNER, balance=10000.0, meta=META)  # valid_until 07:30 on 2026-06-23
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == "SIGNAL_STALE"
    assert t["reason_code"] == LEGACY_STALE_SIGNAL                         # legacy ticket reason unchanged
    assert t["ticket_status"] == "EXPIRED" and t["owner_accept_allowed"] is False


def test_manual_expiry_backstop_blocks_when_legacy_guard_does_not(l2_pass, monkeypatch):
    """If the legacy decision were still READY past valid_until, the manual layer itself blocks."""
    real = mt.fx.build_fx_ticket

    def still_ready(*a, **k):
        t = real(*a, **k)
        return {**t, "decision": "READY", "reason_code": t.get("engine_reason_code", t["reason_code"])}             if t["decision"] == "STALE" else t
    monkeypatch.setattr(mt.fx, "build_fx_ticket", still_ready)
    t = manual(READY_DAY, "07:31", owner=OWNER, balance=10000.0, meta=META)
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == "TICKET_EXPIRED"
    assert t["ticket_status"] == "EXPIRED" and t["owner_accept_allowed"] is False
