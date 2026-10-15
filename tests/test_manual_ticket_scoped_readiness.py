"""Manual-ticket READY must stay within ready_authority's exact scoped decision."""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pytest
import yaml

from v1_tickets import manual_ticket as mt
from v1_tickets import ready_authority as ra
from v1_tickets.authority import logic_identity
from v1_tickets.logic_gate import PASS
from v1_tickets.scan_record import TICKET_BLOCKED, TICKET_READY

ROOT = Path(__file__).resolve().parents[1]
ASW = "ST_ASIAN_SWEEP_5R_V1"
ASW_112 = ROOT / "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
CCFD = "ST_CRYPTO_CFD_SWEEP_RETEST_V1"
CCFD_CONTRACT = ROOT / "strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml"
NOW = dt.datetime(2026, 10, 15, 7, 20, tzinfo=dt.timezone.utc)


def _write_authority(tmp_path: Path, monkeypatch, strategy: str, version: str, symbol: str, session: str,
                     contract: Path, *, on: bool, owner_record: bool = True):
    config = tmp_path / "ready_authority.yaml"
    config.write_text(yaml.safe_dump({"strategies": ({strategy: {"ready": "ON"}} if on else {})}),
                      encoding="utf-8")
    monkeypatch.setattr(ra, "CONFIG_PATH", str(config))
    register = tmp_path / "owner_register.md"
    body = ""
    if owner_record:
        row = {"decision_id": "OD1012-S1-READY" if strategy == ASW else "TEST-CCFD-READY",
               "status": "APPROVED", "strategy_id": strategy, "version": version,
               "contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
               "symbol_scope": [symbol], "session_scope": [session], "date": "2026-10-15"}
        body = yaml.safe_dump({"ready_authority_records": [row]}, sort_keys=False)
    register.write_text("<!-- READY_AUTHORITY_RECORDS_START -->\n" + body +
                        "<!-- READY_AUTHORITY_RECORDS_END -->\n", encoding="utf-8")
    monkeypatch.setattr(ra, "OWNER_DECISION_REGISTER_PATH", str(register))
    return register


def _pass_gate(name):
    return lambda *args, **kwargs: {"gate": name, "status": PASS, "checks": []}


def _asw_ticket(monkeypatch, *, day=dt.date(2026, 10, 15), strategy_path=ASW_112):
    base = {"strategy_id": ASW, "strategy_version": "1.1.2", "symbol": "GBPUSD",
            "cycle": "ASIAN_LONDON", "decision": "READY", "reason_code": "BOX_DIRECTION_V1",
            "engine_reason_code": "BOX_DIRECTION_V1", "direction": "LONG", "regime": "RANGE",
            "setup": "SWEEP", "entry": 1.2700, "stop_loss": 1.2690, "risk_distance": 0.001,
            "targets": [{"leg": 1, "price": 1.2710}, {"leg": 2, "price": 1.2750}],
            "signal_timestamp": "2026-10-15T07:00:00+00:00", "entry_order_type": "MARKET",
            "spread_check": "OK", "box": {"low": 1.2690, "high": 1.2710, "mid": 1.2700}}
    monkeypatch.setattr(mt.fx, "build_fx_ticket", lambda *a, **k: dict(base))
    monkeypatch.setattr(mt, "classify_fx_ticket", lambda *a, **k: (TICKET_READY, "TICKET", None))
    for name in ("l1_determinism", "l2_rule_conformance", "l3_geometry", "l4_data_session",
                 "l5_cost", "l6_freshness"):
        gate = _pass_gate(name.upper())
        if name == "l5_cost":
            gate = lambda *a, **k: {"gate": "L5", "status": PASS,
                                    "checks": [{"id": "L5.commission_R", "note": "fixture"}]}
        monkeypatch.setattr(mt, name, gate)
    monkeypatch.setattr(mt, "lot_size", lambda *a, **k: {
        "lot": 0.1, "status": "OK", "risk_pct": 0.5, "risk_amount": 50.0,
        "symbol_meta": {"source": "TEST"},
    })
    return mt.build_manual_ticket(
        "GBPUSD", "ASIAN_LONDON", day, [], 24, [], now=NOW, data_close=NOW,
        spread=0.00007, owner={"risk_pct": 0.5, "cost_warn_R": 0.10, "cost_block_R": 0.25},
        balance=10000.0, commission_r=0.0, strategy_path=str(strategy_path),
    )


def _ccfd_registry(tmp_path: Path, monkeypatch, *, symbol="ETHUSD", direction="SHORT", window="WEEKDAY",
                   include_window=True):
    identity = logic_identity(CCFD, "1.0.0")
    scope = {"symbol": symbol, "session": window, "branch": direction, "engine_setup": direction,
             "status": "LOGIC_VERIFIED", "config_source": str(CCFD_CONTRACT.relative_to(ROOT)),
             "contract_hash": identity["contract_hash"], "engine_hash": identity["engine_identity"],
             "identity_hash": identity["digest"], "evidence": "fixture://verified-window"}
    candidate = {"config_source": str(CCFD_CONTRACT.relative_to(ROOT)),
                 "logic_verified_symbols": [{"symbol": symbol, "branches": [direction]}],
                 "logic_verified_scopes": [scope] if include_window else []}
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"strategies": {CCFD: {"candidate_versions": {"1.0.0": candidate}}}}),
                        encoding="utf-8")
    monkeypatch.setattr(ra, "REGISTRY_PATH", str(registry))


def _ccfd_result(symbol="ETHUSD", direction="SHORT"):
    from crypto_cfd_contract.contract import CONTRACT_ID, CONTRACT_VERSION
    return {"contract_id": CONTRACT_ID, "contract_version": CONTRACT_VERSION, "symbol": symbol,
            "result": "ENTRY_VALID", "reason_codes": [],
            "evidence": {"target_plan": {"entry": 100.0, "stop_loss": 110.0, "tp1": 90.0,
                                           "tp2": 80.0, "direction": direction},
                         "retest": {"candle_time_utc": (NOW - dt.timedelta(minutes=5)).isoformat()}}}


def _ccfd_ticket(result, **kw):
    policy = {"open_authorities": [], "risk_pct": 0.5, "cost_warn_R": 0.10, "cost_block_R": 0.25,
              "spread_ok_pct": 0.05, "spread_block_pct": 0.10}
    return mt.build_crypto_cfd_manual_ticket(
        result, now=NOW, window="WEEKDAY", spread=0.01, commission_r=0.0,
        quote_time=NOW - dt.timedelta(minutes=1), policy=policy, **kw,
    )


def test_asw_golden_scope_uses_od1012_and_renders_ready(tmp_path, monkeypatch):
    _write_authority(tmp_path, monkeypatch, ASW, "1.1.2", "GBPUSD", "ASIAN_LONDON", ASW_112, on=True)
    ticket = _asw_ticket(monkeypatch)
    assert ticket["state"] == TICKET_READY
    assert ticket["logic_status"] == "LOGIC_VERIFIED"
    assert ticket["owner_accept_allowed"] is True
    assert "State       TICKET_READY" in mt.render_text(ticket)


@pytest.mark.parametrize(("on", "owner_record", "remove_scope", "reason"), [
    (False, True, False, ra.READY_AUTHORITY_OFF),
    (True, False, False, ra.OWNER_DECISION_RECORD_MISSING),
    (True, True, True, ra.READY_SYMBOL_NOT_VERIFIED),
])
def test_each_missing_asw_authority_piece_blocks_with_reason(tmp_path, monkeypatch, on, owner_record,
                                                             remove_scope, reason):
    _write_authority(tmp_path, monkeypatch, ASW, "1.1.2", "GBPUSD", "ASIAN_LONDON", ASW_112,
                     on=on, owner_record=owner_record)
    if remove_scope:
        original = Path(ra.REGISTRY_PATH).read_text(encoding="utf-8")
        fixture = tmp_path / "registry.yaml"
        rows = yaml.safe_load(original)
        rows["strategies"][ASW]["candidate_versions"]["1.1.2"]["logic_verified_scopes"] = []
        fixture.write_text(yaml.safe_dump(rows), encoding="utf-8")
        monkeypatch.setattr(ra, "REGISTRY_PATH", str(fixture))
    ticket = _asw_ticket(monkeypatch)
    assert ticket["state"] == TICKET_BLOCKED
    assert ticket["primary_block_reason"] == reason


def test_ccfd_current_authority_off_blocks_even_when_window_is_verified(tmp_path, monkeypatch):
    _ccfd_registry(tmp_path, monkeypatch)
    ticket = _ccfd_ticket(_ccfd_result())
    assert ticket["decision"] == "BLOCKED"
    assert ra.READY_AUTHORITY_OFF in ticket["reason_codes"]
    assert "State" not in mt.render_text(ticket)


def test_ccfd_authority_on_and_verified_window_can_render_ready(tmp_path, monkeypatch):
    _ccfd_registry(tmp_path, monkeypatch)
    _write_authority(tmp_path, monkeypatch, CCFD, "1.0.0", "ETHUSD", "WEEKDAY", CCFD_CONTRACT, on=True)
    monkeypatch.setattr(mt, "lot_size", lambda *a, **k: {"lot": 0.1, "status": "OK"})
    ticket = _ccfd_ticket(_ccfd_result())
    assert ticket["decision"] == "READY" and ticket["owner_accept_allowed"] is True
    assert "ETHUSD WEEKDAY READY" in mt.render_text(ticket)


def test_ccfd_unrecorded_window_blocks_with_named_reason(tmp_path, monkeypatch):
    _ccfd_registry(tmp_path, monkeypatch, include_window=False)
    _write_authority(tmp_path, monkeypatch, CCFD, "1.0.0", "ETHUSD", "WEEKDAY", CCFD_CONTRACT, on=True)
    ticket = _ccfd_ticket(_ccfd_result())
    assert ticket["decision"] == "BLOCKED"
    assert "WINDOW_NOT_IN_SCOPE" in ticket["reason_codes"]


def test_btcusd_long_stays_blocked_even_if_fixture_lists_direction(tmp_path, monkeypatch):
    _ccfd_registry(tmp_path, monkeypatch, symbol="BTCUSD", direction="LONG")
    _write_authority(tmp_path, monkeypatch, CCFD, "1.0.0", "BTCUSD", "WEEKDAY", CCFD_CONTRACT, on=True)
    ticket = _ccfd_ticket(_ccfd_result("BTCUSD", "LONG"))
    assert ticket["decision"] == "BLOCKED"
    assert "BTCUSD_LONG_NOT_IN_SCOPE" in ticket["reason_codes"]


def test_lsmc_never_resolves_as_manual_ready():
    allowed, reason = mt._scoped_manual_ready("ST_LARGE_SMC_V1", "1.1.0", "BTCUSD", "CRYPTO_WEEKEND",
                                              "RANGE_SWEEP", "SHORT", setup="SWEEP")
    assert not allowed and reason == "MANUAL_STRATEGY_NOT_SUPPORTED"


def test_manual_ticket_ready_never_exceeds_ready_authority(tmp_path, monkeypatch):
    """Property over authority-on/off, owner-record and exact-scope inputs."""
    cases = [(False, True, True), (True, False, True), (True, True, False), (True, True, True)]
    for index, (on, owner_record, with_scope) in enumerate(cases):
        case_dir = tmp_path / str(index)
        case_dir.mkdir()
        _write_authority(case_dir, monkeypatch, ASW, "1.1.2", "GBPUSD", "ASIAN_LONDON", ASW_112,
                         on=on, owner_record=owner_record)
        if with_scope:
            monkeypatch.setattr(ra, "REGISTRY_PATH", str(ROOT / "strategies/registry.yaml"))
        else:
            registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))
            registry["strategies"][ASW]["candidate_versions"]["1.1.2"]["logic_verified_scopes"] = []
            path = case_dir / "registry.yaml"
            path.write_text(yaml.safe_dump(registry), encoding="utf-8")
            monkeypatch.setattr(ra, "REGISTRY_PATH", str(path))
        ticket = _asw_ticket(monkeypatch)
        contract_hash = hashlib.sha256(ASW_112.read_bytes()).hexdigest()
        owner_ready, _ = ra.ready_authority(ASW, strategy_version="1.1.2", contract_sha256=contract_hash,
                                            symbol="GBPUSD", session="ASIAN_LONDON")
        scope_ready = ra.logic_scope_verified(ASW, "1.1.2", "GBPUSD", cycle="ASIAN_LONDON",
                                             setup="SWEEP", branch="RANGE_SWEEP",
                                             contract_path=str(ASW_112))
        if not (owner_ready and scope_ready):
            assert ticket["state"] != TICKET_READY
