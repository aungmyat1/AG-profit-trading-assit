"""Read-only per-scope verification status (OD1012-ROUTING): every family x pair x session scope
resolves from the registry, fails closed, and is never routable from this module."""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest
import yaml

from v1_tickets import scope_status as ss
from v1_tickets.authority import load_registry

ROOT = Path(__file__).resolve().parents[1]
ALL_SCOPES = [(family, symbol, session) for family, spec in ss.FAMILIES.items()
              for session in spec["sessions"] for symbol in spec["pairs"]]


def test_family_pair_map_is_the_owner_universe_without_audusd():
    assert ss.FAMILIES[ss.SESSION_FX_GOLD]["pairs"] == ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
    assert ss.FAMILIES[ss.SESSION_FX_GOLD]["sessions"] == ("ASIAN_LONDON", "LONDON_NEWYORK")
    assert ss.FAMILIES[ss.CRYPTO_CFD]["pairs"] == ("BTCUSD", "ETHUSD")
    assert ss.FAMILIES[ss.LARGE_SMC]["pairs"] == ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD")
    assert all("AUDUSD" not in spec["pairs"] for spec in ss.FAMILIES.values())
    assert len(ALL_SCOPES) == 8 + 4 + 6


def test_family_versions_match_runtime_and_registry():
    from strategy_engine import load_strategy
    from v1_tickets import fx
    registry = load_registry()
    assert load_strategy(fx.SCOPED_CANDIDATE_PATH).version == ss.FAMILIES[ss.SESSION_FX_GOLD]["strategy_version"]
    assert ss.FAMILIES[ss.CRYPTO_CFD]["strategy_version"] in registry["ST_CRYPTO_CFD_SWEEP_RETEST_V1"]["candidate_versions"]
    assert registry["ST_LARGE_SMC_V1"]["version"] == ss.FAMILIES[ss.LARGE_SMC]["strategy_version"]


@pytest.mark.parametrize("family,symbol,session", ALL_SCOPES)
def test_every_scope_resolves_report_only_with_reason(family, symbol, session):
    status = ss.scope_status(family, symbol, session)
    assert status.route == ss.REPORT_ONLY
    assert status.route_reason
    assert status.verification_status in {ss.UNVERIFIED, ss.IN_VERIFICATION, ss.LOGIC_VERIFIED,
                                          ss.STALE_IDENTITY, ss.SUSPENDED}


def test_current_registry_statuses():
    s1 = ss.scope_status(ss.SESSION_FX_GOLD, "GBPUSD", "ASIAN_LONDON")
    assert (s1.verification_status, s1.route_reason) == (ss.LOGIC_VERIFIED, "READY_AUTHORITY_OFF_D6")
    assert ss.scope_status(ss.SESSION_FX_GOLD, "GBPUSD", "LONDON_NEWYORK").verification_status == ss.UNVERIFIED
    eur = ss.scope_status(ss.SESSION_FX_GOLD, "EURUSD", "ASIAN_LONDON")
    assert (eur.verification_status, eur.route_reason) == (ss.SUSPENDED, "L3_REPAINT_UNRESOLVED_2026-07-31")
    for symbol in ("USDJPY", "XAUUSD"):
        assert ss.scope_status(ss.SESSION_FX_GOLD, symbol, "ASIAN_LONDON").route_reason == ss.LOGIC_NOT_VERIFIED
    btc = ss.scope_status(ss.CRYPTO_CFD, "BTCUSD", ss.CRYPTO_DAY)
    assert (btc.verification_status, btc.detail) == (ss.STALE_IDENTITY, "branches=SHORT")
    eur_lsmc = ss.scope_status(ss.LARGE_SMC, "EURUSD", ss.WATCH)
    assert (eur_lsmc.verification_status, eur_lsmc.route_reason, eur_lsmc.detail) == (
        ss.UNVERIFIED, ss.ENTRY_LOGIC_NOT_VERIFIED, "detection=LOGIC_VERIFIED")
    assert ss.scope_status(ss.LARGE_SMC, "BTCUSD", ss.WATCH).detail == "detection=NOT_VERIFIED"


@pytest.mark.parametrize("registry", [{}, {"ST_ASIAN_SWEEP_5R_V1": "junk"},
                                      {"ST_ASIAN_SWEEP_5R_V1": {"registered": True}}])
def test_missing_or_malformed_registry_fails_closed(registry):
    status = ss.scope_status(ss.SESSION_FX_GOLD, "GBPUSD", "ASIAN_LONDON", registry=registry)
    assert (status.verification_status, status.route, status.route_reason) == (
        ss.UNVERIFIED, ss.REPORT_ONLY, ss.REGISTRY_ENTRY_MISSING)


def test_ccfd_verified_claim_with_stale_identity_is_not_verified():
    registry = copy.deepcopy(load_registry())
    registry["ST_CRYPTO_CFD_SWEEP_RETEST_V1"]["candidate_versions"]["1.0.0"]["logic_status"] = ss.LOGIC_VERIFIED
    status = ss.scope_status(ss.CRYPTO_CFD, "ETHUSD", ss.CRYPTO_WEEKEND, registry=registry)
    assert status.verification_status == ss.STALE_IDENTITY   # recorded digest no longer matches the code


def test_unknown_scope_is_a_caller_error():
    with pytest.raises(ValueError):
        ss.scope_status(ss.SESSION_FX_GOLD, "AUDUSD", "ASIAN_LONDON")
    with pytest.raises(ValueError):
        ss.scope_status(ss.LARGE_SMC, "EURUSD", "ASIAN_LONDON")


def test_family_statuses_order_and_registry_failure(monkeypatch):
    rows = ss.family_statuses(ss.CRYPTO_CFD, ss.CRYPTO_DAY)
    assert [row["symbol"] for row in rows] == ["BTCUSD", "ETHUSD"]

    def broken():
        raise yaml.YAMLError("corrupt")
    monkeypatch.setattr("v1_tickets.authority.load_registry", broken)
    rows = ss.family_statuses(ss.SESSION_FX_GOLD, "ASIAN_LONDON")
    assert {row["route_reason"] for row in rows} == {ss.REGISTRY_ENTRY_MISSING}


def test_module_has_no_execution_or_broker_imports():
    tree = ast.parse((ROOT / "src" / "v1_tickets" / "scope_status.py").read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(n.startswith(("execution", "mt5", "MetaTrader5", "assistant")) for n in names)
    assert "DEMO_ORDER" not in (ROOT / "src" / "v1_tickets" / "scope_status.py").read_text(encoding="utf-8")
