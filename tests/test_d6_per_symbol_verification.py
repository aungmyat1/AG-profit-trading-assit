"""D6 READY requires per-symbol verification (owner mission 2026-10-10).

READY survives only if D6 READY authority is ON AND the ticket's symbol is listed VERIFIED for the
emitting strategy version in strategies/registry.yaml (candidate_versions."<v>".verified_symbols).
Absent anything means not verified. D6 OFF behaviour is unchanged. Production D6 stays OFF.
"""
from __future__ import annotations

import datetime as dt
import types

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
def d6_on(tmp_path):
    path = tmp_path / "ready_authority.yaml"
    path.write_text(f"strategies:\n  {SID}:\n    ready: 'ON'\n", encoding="utf-8")
    return str(path)


def ready(symbol: str, version: str) -> dict:
    return {"decision": "READY", "strategy_id": SID, "strategy_version": version, "symbol": symbol,
            "reason_code": "SWEEP_V1", "entry": 1.1, "stop_loss": 1.09}


def test_verification_source_is_the_registry_and_lists_only_eurusd_for_1_1_2():
    reg = yaml.safe_load(open(ra.REGISTRY_PATH, encoding="utf-8"))["strategies"][SID]
    assert reg["candidate_versions"]["1.1.2"]["verified_symbols"] == ["EURUSD"]
    assert "verified_symbols" not in reg                         # runtime 1.1.1: nothing verified
    assert ra.symbol_verified(SID, "1.1.2", "EURUSD") is True
    for sym, ver in (("GBPUSD", "1.1.2"), ("USDJPY", "1.1.2"), ("XAUUSD", "1.1.2"), ("EURUSD", "1.1.1"),
                     ("EURUSD", None), ("EURUSD", "9.9.9")):
        assert ra.symbol_verified(SID, ver, sym) is False, (sym, ver)
    assert ra.symbol_verified("UNKNOWN_STRATEGY", "1.1.2", "EURUSD") is False


def test_unreadable_registry_means_not_verified(tmp_path, d6_on):
    missing = str(tmp_path / "nope.yaml")
    assert ra.symbol_verified(SID, "1.1.2", "EURUSD", registry_path=missing) is False
    out = ra.apply_ready_authority(ready("EURUSD", "1.1.2"), d6_on, registry_path=missing)
    assert out["decision"] == ra.SHADOW_INFO_ONLY


@pytest.mark.parametrize("symbol,version", [("GBPUSD", "1.1.2"), ("USDJPY", "1.1.2"), ("EURUSD", "1.1.1")])
def test_d6_on_and_unverified_symbol_is_not_ready(d6_on, symbol, version):
    out = ra.apply_ready_authority(ready(symbol, version), d6_on)
    assert out["decision"] == ra.SHADOW_INFO_ONLY != "READY"
    assert (out["suppressed_decision"], out["reason_code"], out["engine_reason_code"], out["ready_authority"]) == (
        "READY", ra.READY_SYMBOL_NOT_VERIFIED, "SWEEP_V1", "ON_SYMBOL_NOT_VERIFIED")
    assert (out["entry"], out["stop_loss"]) == (1.1, 1.09)         # levels kept for audit
    assert "NOT ACTIONABLE" in out["label"]


def test_d6_on_and_verified_symbol_is_ready(d6_on):
    t = ready("EURUSD", "1.1.2")
    assert ra.apply_ready_authority(t, d6_on) == t                  # untouched


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


@pytest.mark.parametrize("symbol,expected", [("EURUSD", "READY"), ("GBPUSD", ra.SHADOW_INFO_ONLY)])
def test_fx_ticket_path_applies_the_symbol_gate(monkeypatch, d6_on, symbol, expected):
    sig = types.SimpleNamespace(status="SIGNAL", reason_code="SWEEP_V1", regime="RANGE", setup="SWEEP",
                                signal_id="s1", box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                signal_timestamp=dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), direction="LONG",
                                entry=1.1665, stop_loss=1.16515, risk_distance=0.00135)
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: sig)
    monkeypatch.setattr(ra, "CONFIG_PATH", d6_on)
    bar = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1665, 1.1670, 1.1660, 1.1666)
    t = fx_tickets.build_fx_ticket(symbol, "ASIAN_LONDON", DAY, [], 2, [bar], data_source="MT5_VT_MARKETS_DEMO",
                                   evaluated_at=AT, data_close=AT, spread=0.00015, strategy_path=CANDIDATE)
    assert (t["strategy_version"], t["decision"]) == ("1.1.2", expected)
