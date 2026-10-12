"""D6 READY requires exact identity-bound logic scope.

READY survives only if D6 is ON, an owner record binds it, and the exact scope tuple plus identity hashes
are present in strategies/registry.yaml. Production allows only the approved S1 owner binding; OFF negatives use temporary config.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import types
from pathlib import Path

import pytest
import yaml

from strategy_engine.session import Candle
from v1_tickets import fx as fx_tickets
from v1_tickets import ready_authority as ra

UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 7)
AT = dt.datetime(2026, 10, 7, 7, 16, 8, tzinfo=UTC)
CANDIDATE = "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
SID = "ST_ASIAN_SWEEP_5R_V1"


@pytest.fixture
def d6_on(tmp_path, monkeypatch):
    path = tmp_path / "ready_authority.yaml"
    path.write_text(f"strategies:\n  {SID}:\n    ready: 'ON'\n", encoding="utf-8")
    contract = Path(__file__).resolve().parents[1] / CANDIDATE
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    record = {"decision_id": "TEST-FIXTURE-D6-1", "status": "CONFIRMED", "strategy_id": SID,
              "version": "1.1.2", "contract_sha256": digest,
              "symbol_scope": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
              "session_scope": ["ASIAN_LONDON", "LONDON_NEWYORK"], "date": "2026-10-10"}
    owner_register = tmp_path / "owner-register.md"
    owner_register.write_text("<!-- READY_AUTHORITY_RECORDS_START -->\n" + yaml.safe_dump(
        {"ready_authority_records": [record]}, sort_keys=False) + "<!-- READY_AUTHORITY_RECORDS_END -->\n",
        encoding="utf-8")
    monkeypatch.setattr(ra, "OWNER_DECISION_REGISTER_PATH", str(owner_register))
    return str(path)


def ready(symbol: str, version: str) -> dict:
    return {"decision": "READY", "strategy_id": SID, "strategy_version": version, "symbol": symbol,
            "cycle": "ASIAN_LONDON", "regime": "RANGE", "setup": "SWEEP",
            "reason_code": "SWEEP_V1", "entry": 1.1, "stop_loss": 1.09}


def test_verification_source_is_the_registry_eurusd_suspended_gbpusd_scoped():
    reg = yaml.safe_load(open(ra.REGISTRY_PATH, encoding="utf-8"))["strategies"][SID]
    version = reg["candidate_versions"]["1.1.2"]
    entries = version["logic_verified_scopes"]
    assert len(entries) == 1 and entries[0]["scope_id"] == "S1"
    assert (entries[0]["symbol"], entries[0]["session"], entries[0]["branch"], entries[0]["engine_setup"]) == \
        ("GBPUSD", "ASIAN_LONDON", "RANGE_SWEEP", "SWEEP")
    root = __import__("pathlib").Path(ra.REGISTRY_PATH).parents[1]
    assert not (root / entries[0]["evidence"]).exists() or entries[0]["evidence"].endswith(
        "AGP_ASW_V112_S1_60D_2026-10-11.json")
    assert entries[0]["evidence"].endswith("AGP_ASW_V112_S1_60D_2026-10-11.json")
    assert version["logic_suspended_scopes"][0]["status"] == "SUSPENDED"
    assert version["logic_suspended_scopes"][0]["symbol"] == "EURUSD"
    assert ra.logic_scope_verified(SID, "1.1.2", "GBPUSD", cycle="ASIAN_LONDON", setup="SWEEP",
                                   branch="RANGE_SWEEP") is True
    for sym, ver in (("EURUSD", "1.1.2"), ("USDJPY", "1.1.2"), ("XAUUSD", "1.1.2"), ("EURUSD", "1.1.1"),
                     ("EURUSD", None), ("EURUSD", "9.9.9")):
        assert ra.logic_scope_verified(SID, ver, sym, cycle="ASIAN_LONDON", setup="SWEEP",
                                       branch="RANGE_SWEEP") is False, (sym, ver)
    assert ra.logic_scope_verified("UNKNOWN_STRATEGY", "1.1.2", "EURUSD") is False


def test_unreadable_registry_means_not_verified(tmp_path, d6_on):
    missing = str(tmp_path / "nope.yaml")
    assert ra.logic_scope_verified(SID, "1.1.2", "EURUSD", registry_path=missing) is False
    out = ra.apply_ready_authority(ready("EURUSD", "1.1.2"), d6_on, registry_path=missing,
                                   contract_path=str(Path(__file__).resolve().parents[1] / CANDIDATE))
    assert out["decision"] == ra.SHADOW_INFO_ONLY


@pytest.mark.parametrize("symbol,version", [("GBPUSD", "1.1.2"), ("USDJPY", "1.1.2"), ("EURUSD", "1.1.1"),
                                            ("EURUSD", "1.1.2")])     # EURUSD 1.1.2: SUSPENDED
def test_d6_on_and_unverified_symbol_is_not_ready(d6_on, symbol, version):
    if symbol == "GBPUSD" and version == "1.1.2":
        pytest.skip("GBPUSD is the one S1 verified scope")
    out = ra.apply_ready_authority(ready(symbol, version), d6_on,
                                   contract_path=(str(Path(__file__).resolve().parents[1] / CANDIDATE)
                                                  if version == "1.1.2" else str(
                                                      Path(__file__).resolve().parents[1] / "strategies/ST_ASIAN_SWEEP_5R_V1.yaml")))
    assert out["decision"] == ra.SHADOW_INFO_ONLY != "READY"
    expected_reason = (ra.READY_SYMBOL_NOT_VERIFIED if version == "1.1.2"
                       else ra.OWNER_DECISION_VERSION_MISMATCH)
    expected_authority = "ON_SYMBOL_NOT_VERIFIED" if version == "1.1.2" else "OFF"
    assert (out["suppressed_decision"], out["reason_code"], out["engine_reason_code"], out["ready_authority"]) == (
        "READY", expected_reason, "SWEEP_V1", expected_authority)
    assert (out["entry"], out["stop_loss"]) == (1.1, 1.09)         # levels kept for audit
    assert "NOT ACTIONABLE" in out["label"]


def test_d6_on_and_verified_symbol_is_ready(d6_on):
    t = {**ready("GBPUSD", "1.1.2"), "setup": "SWEEP"}       # the only VERIFIED entry (scoped, OD1011-SCOPE)
    assert ra.apply_ready_authority(t, d6_on,
                                   contract_path=str(Path(__file__).resolve().parents[1] / CANDIDATE)) == t


@pytest.mark.parametrize("symbol,version", [("EURUSD", "1.1.2"), ("GBPUSD", "1.1.2"), ("EURUSD", "1.1.1")])
def test_d6_off_behaviour_is_unchanged(d6_ready_off, symbol, version):
    t = ready(symbol, version)
    assert ra.apply_ready_authority(t) == {
        **t, "decision": ra.SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": ra.SHADOW_LABEL,
        "engine_reason_code": "SWEEP_V1", "reason_code": ra.READY_AUTHORITY_OFF, "ready_authority": "OFF"}
    non_ready = {**t, "decision": "NO_TRADE"}
    assert ra.apply_ready_authority(non_ready) is non_ready


def test_temporary_d6_is_still_off(d6_ready_off):
    assert ra.ready_authority(SID) == (False, ra.READY_AUTHORITY_OFF)


@pytest.mark.parametrize("symbol,cycle,expected", [
    ("EURUSD", "ASIAN_LONDON", "LOGIC_SCOPE_NOT_VERIFIED"),
    ("GBPUSD", "ASIAN_LONDON", "S1_BUILDS"),
    ("USDJPY", "ASIAN_LONDON", "LOGIC_SCOPE_NOT_VERIFIED"),
    ("GBPUSD", "LONDON_NEWYORK", "LOGIC_SCOPE_NOT_VERIFIED")])
def test_fx_ticket_path_applies_the_symbol_gate(monkeypatch, symbol, cycle, expected):
    sig = types.SimpleNamespace(status="SIGNAL", reason_code="SWEEP_V1", regime="RANGE", setup="SWEEP",
                                signal_id="s1", box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                signal_timestamp=dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), direction="LONG",
                                entry=1.1665, stop_loss=1.16515, risk_distance=0.00135)
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: sig)
    bar = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1665, 1.1670, 1.1660, 1.1666)
    if expected == "LOGIC_SCOPE_NOT_VERIFIED":
        t = fx_tickets.build_fx_ticket(symbol, cycle, DAY, [], 2, [bar], data_source="MT5_VT_MARKETS_DEMO",
                                       evaluated_at=AT, data_close=AT, spread=0.00015, runtime_scope=True)
        assert t["decision"] == "BLOCKED"
        assert t["reason_code"] == "LOGIC_SCOPE_NOT_VERIFIED"
    else:
        t = fx_tickets.build_fx_ticket(symbol, cycle, DAY, [], 2, [bar], data_source="MT5_VT_MARKETS_DEMO",
                                       evaluated_at=AT, data_close=AT, spread=0.00015, runtime_scope=True)
        assert t["strategy_version"] == "1.1.2"
        assert t["regime"] == "RANGE" and t["setup"] == "SWEEP"
        assert t["decision"] == "READY" and t["reason_code"] == "SWEEP_V1"
    assert t["strategy_version"] == "1.1.2"


def test_real_symbol_verified_reads_registry_without_any_stub(request):
    # No stub is active here: the opt-in `stub_symbol_verified` fixture is not requested.
    assert "stub_symbol_verified" not in request.fixturenames
    assert ra.logic_scope_verified.__module__ == "v1_tickets.ready_authority"
    assert ra.logic_scope_verified(SID, "1.1.2", "GBPUSD", cycle="ASIAN_LONDON", setup="SWEEP",
                                   branch="RANGE_SWEEP") is True
    assert ra.logic_scope_verified(SID, "1.1.1", "EURUSD") is False
    assert ra.logic_scope_verified(SID, "1.1.2", "EURUSD") is False


def test_scoped_entry_covers_only_its_session_branch_and_setup():
    assert ra.logic_scope_verified(SID, "1.1.2", "GBPUSD", cycle="ASIAN_LONDON", setup="SWEEP",
                                   branch="RANGE_SWEEP")
    for symbol, cycle, setup, branch in (
        ("GBPUSD", "LONDON_NEWYORK", "SWEEP", "RANGE_SWEEP"),
        ("GBPUSD", "ASIAN_LONDON", "TREND", "TREND_SWEEP"),
        ("GBPUSD", "ASIAN_LONDON", "SWEEP", "TREND_SWEEP"),
        ("EURUSD", "ASIAN_LONDON", "SWEEP", "RANGE_SWEEP"),
        ("USDJPY", "ASIAN_LONDON", "SWEEP", "RANGE_SWEEP"),
    ):
        assert not ra.logic_scope_verified(SID, "1.1.2", symbol, cycle=cycle, setup=setup, branch=branch)


def test_engine_and_contract_hash_mismatch_fails_closed(tmp_path):
    reg = yaml.safe_load(Path(ra.REGISTRY_PATH).read_text(encoding="utf-8"))
    reg["strategies"][SID]["candidate_versions"]["1.1.2"]["logic_verified_scopes"][0]["engine_hash"] = "0" * 64
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")
    assert not ra.logic_scope_verified(SID, "1.1.2", "GBPUSD", registry_path=str(path),
                                       cycle="ASIAN_LONDON", setup="SWEEP", branch="RANGE_SWEEP")


def test_missing_owner_binding_record_blocks_s1_ready(tmp_path):
    cfg = tmp_path / "ready.yaml"
    cfg.write_text(f"strategies:\n  {SID}:\n    ready: 'ON'\n", encoding="utf-8")
    register = tmp_path / "owner.md"
    register.write_text("no owner decision record", encoding="utf-8")
    out = ra.apply_ready_authority(ready("GBPUSD", "1.1.2"), path=str(cfg),
        owner_register_path=str(register), contract_path=str(Path(__file__).resolve().parents[1] / CANDIDATE))
    assert out["decision"] == ra.SHADOW_INFO_ONLY
    assert out["reason_code"] == ra.OWNER_DECISION_RECORD_MISSING


@pytest.mark.parametrize("symbol,cycle", [
    (sym, session) for sym in fx_tickets.V1_FX_SYMBOLS for session in fx_tickets.V1_CYCLES
    if (sym, session) != ("GBPUSD", "ASIAN_LONDON")])
def test_scheduler_blocks_every_out_of_scope_combo_before_provider(tmp_path, symbol, cycle):
    from v1_tickets.daily_evaluator import evaluate_fx_pair
    result = evaluate_fx_pair(symbol, cycle, now=AT, day=DAY,
        candle_provider=lambda *_: pytest.fail("out-of-scope scheduler must not access market data"),
        archive_root=str(tmp_path), ticket_source="LIVE")
    assert result.canonical["reason_code"] == "LOGIC_SCOPE_NOT_VERIFIED"


def test_scheduler_s1_identity_mismatch_fails_closed_before_provider(tmp_path, monkeypatch):
    from v1_tickets import daily_evaluator
    monkeypatch.setattr(daily_evaluator, "SCOPED_CANDIDATE_PATH", "strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
    result = daily_evaluator.evaluate_fx_pair("GBPUSD", "ASIAN_LONDON", now=AT, day=DAY,
        candle_provider=lambda *_: pytest.fail("identity mismatch must block before data"),
        archive_root=str(tmp_path), ticket_source="LIVE")
    assert result.canonical["reason_code"] == "LOGIC_SCOPE_NOT_VERIFIED"


def test_apply_ready_authority_passes_ticket_scope(d6_on):
    cfg = d6_on
    base = {"decision": "READY", "strategy_id": SID, "strategy_version": "1.1.2", "symbol": "GBPUSD",
            "cycle": "ASIAN_LONDON", "setup": "SWEEP", "regime": "RANGE", "reason_code": "X"}
    contract = str(Path(__file__).resolve().parents[1] / CANDIDATE)
    assert ra.apply_ready_authority(base, path=str(cfg), contract_path=contract)["decision"] == "READY"
    out = ra.apply_ready_authority({**base, "setup": "TREND"}, path=str(cfg), contract_path=contract)
    assert (out["decision"], out["reason_code"]) == ("SHADOW_INFO_ONLY", ra.READY_SYMBOL_NOT_VERIFIED)
    out = ra.apply_ready_authority({**base, "cycle": "LONDON_NEWYORK"}, path=str(cfg), contract_path=contract)
    assert (out["decision"], out["reason_code"]) == ("SHADOW_INFO_ONLY", ra.READY_SYMBOL_NOT_VERIFIED)


@pytest.mark.parametrize("status,verified", [("SUSPENDED", False), ("REVOKED", False), ("", False), (None, False),
                                             ("VERIFIED", True)])
def test_entry_status_other_than_verified_is_not_verified(tmp_path, status, verified):
    """An incomplete row cannot grant logic scope, regardless of its label."""
    reg = tmp_path / "registry.yaml"
    entry = {"symbol": "EURUSD", "evidence": "x.md", "status": status}
    reg.write_text(yaml.safe_dump({"strategies": {SID: {"candidate_versions": {"1.1.2": {
        "logic_verified_scopes": [entry]}}}}}), encoding="utf-8")
    assert not ra.logic_scope_verified(SID, "1.1.2", "EURUSD", registry_path=str(reg),
                                       cycle="ASIAN_LONDON", setup="SWEEP", branch="RANGE_SWEEP")
