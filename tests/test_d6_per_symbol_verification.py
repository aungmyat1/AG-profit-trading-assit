"""D6 READY requires per-symbol verification (owner mission 2026-10-10).

READY survives only if D6 READY authority is ON AND the ticket's symbol is listed VERIFIED for the
emitting strategy version in strategies/registry.yaml (candidate_versions."<v>".logic_verified_symbols,
each entry with an evidence ref). Absent anything means not verified. D6 OFF behaviour is unchanged. Production D6 stays OFF.
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
            "cycle": "ASIAN_LONDON", "reason_code": "SWEEP_V1", "entry": 1.1, "stop_loss": 1.09}


def test_verification_source_is_the_registry_and_lists_only_eurusd_for_1_1_2():
    reg = yaml.safe_load(open(ra.REGISTRY_PATH, encoding="utf-8"))["strategies"][SID]
    entries = reg["candidate_versions"]["1.1.2"]["logic_verified_symbols"]
    assert entries[0] == {"symbol": "EURUSD", "evidence": "docs/status/AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.md"}
    assert [e["symbol"] for e in entries] == ["EURUSD", "GBPUSD"]
    assert (entries[1]["sessions"], entries[1]["branches"], entries[1]["engine_setups"]) == \
        (["ASIAN_LONDON"], ["RANGE_SWEEP"], ["SWEEP"])          # OD1011-SCOPE: branch-scoped
    root = __import__("pathlib").Path(ra.REGISTRY_PATH).parents[1]
    assert all((root / e["evidence"]).is_file() for e in entries)     # evidence ref resolves
    assert "logic_verified_symbols" not in reg and "verified_symbols" not in reg   # runtime 1.1.1: none
    assert ra.symbol_verified(SID, "1.1.2", "EURUSD") is True
    for sym, ver in (("GBPUSD", "1.1.2"), ("USDJPY", "1.1.2"), ("XAUUSD", "1.1.2"), ("EURUSD", "1.1.1"),
                     ("EURUSD", None), ("EURUSD", "9.9.9")):
        assert ra.symbol_verified(SID, ver, sym) is False, (sym, ver)
    assert ra.symbol_verified("UNKNOWN_STRATEGY", "1.1.2", "EURUSD") is False


def test_unreadable_registry_means_not_verified(tmp_path, d6_on):
    missing = str(tmp_path / "nope.yaml")
    assert ra.symbol_verified(SID, "1.1.2", "EURUSD", registry_path=missing) is False
    out = ra.apply_ready_authority(ready("EURUSD", "1.1.2"), d6_on, registry_path=missing,
                                   contract_path=str(Path(__file__).resolve().parents[1] / CANDIDATE))
    assert out["decision"] == ra.SHADOW_INFO_ONLY


@pytest.mark.parametrize("symbol,version", [("GBPUSD", "1.1.2"), ("USDJPY", "1.1.2"), ("EURUSD", "1.1.1")])
def test_d6_on_and_unverified_symbol_is_not_ready(d6_on, symbol, version):
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
    t = ready("EURUSD", "1.1.2")
    assert ra.apply_ready_authority(t, d6_on,
                                   contract_path=str(Path(__file__).resolve().parents[1] / CANDIDATE)) == t


@pytest.mark.parametrize("symbol,version", [("EURUSD", "1.1.2"), ("GBPUSD", "1.1.2"), ("EURUSD", "1.1.1")])
def test_d6_off_behaviour_is_unchanged(production_ready_authority, symbol, version):
    t = ready(symbol, version)
    assert ra.apply_ready_authority(t) == {
        **t, "decision": ra.SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": ra.SHADOW_LABEL,
        "engine_reason_code": "SWEEP_V1", "reason_code": ra.READY_AUTHORITY_OFF, "ready_authority": "OFF"}
    non_ready = {**t, "decision": "NO_TRADE"}
    assert ra.apply_ready_authority(non_ready) is non_ready


def test_production_d6_is_still_off():
    assert ra.ready_authority(SID) == (False, ra.READY_AUTHORITY_OFF)


@pytest.mark.parametrize("symbol,cycle,expected", [
    ("EURUSD", "ASIAN_LONDON", "READY"), ("GBPUSD", "ASIAN_LONDON", "READY"),       # GBPUSD: OD1011-SCOPE
    ("USDJPY", "ASIAN_LONDON", ra.SHADOW_INFO_ONLY)])   # out-of-scope sessions: test_scoped_entry_*
def test_fx_ticket_path_applies_the_symbol_gate(monkeypatch, d6_on, symbol, cycle, expected):
    sig = types.SimpleNamespace(status="SIGNAL", reason_code="SWEEP_V1", regime="RANGE", setup="SWEEP",
                                signal_id="s1", box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                signal_timestamp=dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), direction="LONG",
                                entry=1.1665, stop_loss=1.16515, risk_distance=0.00135)
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: sig)
    monkeypatch.setattr(ra, "CONFIG_PATH", d6_on)
    bar = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1665, 1.1670, 1.1660, 1.1666)
    t = fx_tickets.build_fx_ticket(symbol, cycle, DAY, [], 2, [bar], data_source="MT5_VT_MARKETS_DEMO",
                                   evaluated_at=AT, data_close=AT, spread=0.00015, strategy_path=CANDIDATE)
    assert (t["strategy_version"], t["decision"]) == ("1.1.2", expected)


def test_real_symbol_verified_reads_registry_without_any_stub(request):
    # No stub is active here: the opt-in `stub_symbol_verified` fixture is not requested.
    assert "stub_symbol_verified" not in request.fixturenames
    assert ra.symbol_verified.__module__ == "v1_tickets.ready_authority"
    assert ra.symbol_verified(SID, "1.1.2", "GBPUSD") is False
    assert ra.symbol_verified(SID, "1.1.1", "EURUSD") is False
    assert ra.symbol_verified(SID, "1.1.2", "EURUSD") is True


def test_entry_without_evidence_ref_is_not_verified(tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text(f"""strategies:
  {SID}:
    candidate_versions:
      "1.1.2":
        logic_verified_symbols:
          - symbol: EURUSD
          - symbol: GBPUSD
            evidence: "  "
          - USDJPY
""", encoding="utf-8")
    for sym in ("EURUSD", "GBPUSD", "USDJPY"):
        assert ra.symbol_verified(SID, "1.1.2", sym, registry_path=str(reg)) is False


def test_scoped_entry_covers_only_its_session_and_branch():
    """OD1011-SCOPE: GBPUSD is verified for ASIAN_LONDON x SWEEP only; anything else fails closed."""
    assert ra.symbol_verified(SID, "1.1.2", "GBPUSD", cycle="ASIAN_LONDON", setup="SWEEP") is True
    for cycle, setup in (("LONDON_NEWYORK", "SWEEP"), ("ASIAN_LONDON", "TREND"), ("ASIAN_LONDON", "RANGE"),
                         (None, "SWEEP"), ("ASIAN_LONDON", None)):
        assert ra.symbol_verified(SID, "1.1.2", "GBPUSD", cycle=cycle, setup=setup) is False, (cycle, setup)
    assert ra.symbol_verified(SID, "1.1.1", "GBPUSD", cycle="ASIAN_LONDON", setup="SWEEP") is False
    # unscoped EURUSD entry keeps covering every session/branch
    assert ra.symbol_verified(SID, "1.1.2", "EURUSD", cycle="LONDON_NEWYORK", setup="SWEEP") is True


def test_malformed_scope_fails_closed(tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text(f"""strategies:
  {SID}:
    candidate_versions:
      "1.1.2":
        logic_verified_symbols:
          - symbol: GBPUSD
            sessions: ASIAN_LONDON
            engine_setups: [SWEEP]
            evidence: x.md
""", encoding="utf-8")
    assert ra.symbol_verified(SID, "1.1.2", "GBPUSD", registry_path=str(reg), cycle="ASIAN_LONDON",
                              setup="SWEEP") is False


def test_apply_ready_authority_passes_ticket_scope(d6_on):
    cfg = d6_on
    base = {"decision": "READY", "strategy_id": SID, "strategy_version": "1.1.2", "symbol": "GBPUSD",
            "cycle": "ASIAN_LONDON", "setup": "SWEEP", "reason_code": "X"}
    contract = str(Path(__file__).resolve().parents[1] / CANDIDATE)
    assert ra.apply_ready_authority(base, path=str(cfg), contract_path=contract)["decision"] == "READY"
    out = ra.apply_ready_authority({**base, "setup": "TREND"}, path=str(cfg), contract_path=contract)
    assert (out["decision"], out["reason_code"]) == ("SHADOW_INFO_ONLY", ra.READY_SYMBOL_NOT_VERIFIED)
    out = ra.apply_ready_authority({**base, "cycle": "LONDON_NEWYORK"}, path=str(cfg), contract_path=contract)
    assert (out["decision"], out["reason_code"]) == ("SHADOW_INFO_ONLY", ra.READY_SYMBOL_NOT_VERIFIED)
