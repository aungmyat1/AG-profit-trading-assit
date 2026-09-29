"""WP-7B: canonical identity gate in front of FX Opportunity evaluation.

Fixture candles + the recorded VTMarkets-Demo broker evidence; no broker contact.
"""
from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import MetaTrader5
import pytest

from fx_opportunity import scanner
from instrument_registry import fx_gated_scan as gs
from instrument_registry.fx_gated_scan import (
    CANONICAL_IDENTITY_NOT_CONFIGURED,
    IDENTITY_BLOCKED,
    MARKETSTATE_FINGERPRINT_DIVERGENCE,
    MARKETSTATE_UNAVAILABLE,
    canonical_id_for,
    gated_scan_symbol,
    venue_for_broker,
)
from mt5.market_data import MarketDataError
from test_fx_opportunity_market_state import Feed, at, ready_bars
from test_instrument_registry_v1 import EVIDENCE, LIVE_EXPOSED, SERVER, VENUE, meta

REPO = Path(__file__).resolve().parents[1]
CTX = scanner.load_cycle_context("POST_ASIAN")
NOW = at(7, 31)
CLOCK = [{"broker": "VT_MARKETS", "server": SERVER}]
_DEFAULT = object()


class Calls:
    def __init__(self):
        self.clock = self.spread = 0


def gscan(symbol="EURUSD", *, exposed=LIVE_EXPOSED, metadata=_DEFAULT, server=SERVER, venue=VENUE, mode="REAL",
          clock=CLOCK, feed=None, calls=None, **kw):
    feed = feed or Feed(ready_bars(symbol))
    calls = calls or Calls()

    def clock_provider():
        calls.clock += 1
        return clock

    def spread_provider():
        calls.spread += 1
        return 0.00008, "fixture"

    res = gated_scan_symbol(
        CTX, symbol, venue_id=venue, observed_server=server, exposed_symbols=exposed,
        metadata=meta() if metadata is _DEFAULT else metadata, trading_date=NOW.date(), now=NOW,
        fetch_candles=feed, market_data_mode=mode, source="fixture", application_lineage="LINEAGE-FIXTURE",
        server_clock_provider=clock_provider, spread_provider=spread_provider, **kw)
    return res, feed, calls


# --- authoritative path --------------------------------------------------------------


def test_eurusd_resolved_is_authoritative_and_opportunity_evaluates():
    res, feed, calls = gscan()
    s = res.summary()
    assert res.canonical_instrument_id == "FX.EURUSD" and res.resolution.status == "RESOLVED"
    assert (s["marketstate_authority"], s["opportunity"]) == ("AUTHORITATIVE", "MAY_EVALUATE")
    assert res.opportunity_evaluated and res.status == "OPPORTUNITY"
    assert (s["proposal"], s["trade_ticket"], s["execution_authority"]) == ("NO_PROPOSAL_AUTHORITY", "NOT_CREATED", "NONE")
    assert s["scan"]["proposal"] == "NO_PROPOSAL_AUTHORITY" and s["scan"]["trade_ticket"] == "NOT_CREATED"
    assert (calls.clock, calls.spread) == (1, 1)
    # MemoFetch: every broker window is read once although MarketState is built twice
    assert len(feed.calls) == len(set(feed.calls))


def test_gated_result_is_identical_to_ungated_scanner_semantics():
    res, _, _ = gscan()
    plain = scanner.scan_symbol(CTX, "EURUSD", trading_date=NOW.date(), now=NOW, fetch_candles=Feed(ready_bars("EURUSD")),
                                market_data_mode="REAL", source="fixture", spread_price=0.00008,
                                spread_source="fixture", application_lineage="LINEAGE-FIXTURE", server_clock=CLOCK)
    assert res.scan.summary() == plain.summary()
    assert res.market_state.fingerprint == res.scan.market_state.fingerprint == plain.market_state.fingerprint


def test_trade_mode_zero_does_not_block_read_only_evaluation():
    assert meta().trade_mode == EVIDENCE["symbol_info_EURUSD"]["trade_mode"] == 0
    res, _, _ = gscan()
    assert res.opportunity_evaluated and res.summary()["broker_metadata"]["trade_mode"] == 0


def test_provenance_recorded():
    s = gscan()[0].summary()
    ci = s["canonical_identity"]
    assert (ci["canonical_instrument_id"], ci["registry_version"], ci["venue_id"], ci["server"], ci["venue_symbol"]) == \
        ("FX.EURUSD", "instruments-v1.0.0", VENUE, SERVER, "EURUSD")
    assert ci["instrument_identity_fingerprint"] == EVIDENCE["identity_fingerprint"]
    assert ci["broker_metadata_fingerprint"] == EVIDENCE["broker_metadata_fingerprint"]
    opp = s["scan"]["opportunity"]
    assert list(opp["market_state"]["server_clock"]) == CLOCK  # time-authority provenance
    assert opp["provenance"]["market_state_fingerprint"] and opp["provenance"]["lineage_fingerprint"]
    assert opp["provenance"]["application_lineage"] == "LINEAGE-FIXTURE"
    text = repr(s).lower()
    assert "login" not in text and "password" not in text


# --- fail-closed before Opportunity evaluation ---------------------------------------


@pytest.mark.parametrize("kwargs, reason", [
    (dict(exposed=("EURUSD+",), metadata=meta("EURUSD+")), "BROKER_SYMBOL_DRIFT"),
    (dict(exposed=("EURUSD-VIP",), metadata=meta("EURUSD-VIP")), "BROKER_SYMBOL_DRIFT"),
    (dict(metadata=meta("EURUSD-VIP")), "BROKER_SYMBOL_DRIFT"),
    (dict(server="VTMarkets-Live"), "SERVER_MISMATCH"),
    (dict(metadata=meta(digits=3)), "BROKER_METADATA_MISMATCH"),
    (dict(metadata=meta(trade_contract_size=1000.0)), "BROKER_METADATA_MISMATCH"),
    (dict(metadata=None), "BROKER_METADATA_UNAVAILABLE"),
    (dict(exposed=None), "BROKER_METADATA_UNAVAILABLE"),
    (dict(registry_version="instruments-v9.9.9"), "UNKNOWN_REGISTRY_VERSION"),
    (dict(venue=None), "VENUE_NOT_CONFIGURED"),
])
def test_identity_failure_blocks_before_any_market_data_or_strategy(kwargs, reason):
    res, feed, calls = gscan(**kwargs)
    s = res.summary()
    assert res.status == IDENTITY_BLOCKED and res.reason_codes == (reason,)
    assert (s["marketstate_authority"], s["opportunity"], s["proposal"], s["trade_ticket"]) == \
        ("BLOCKED", "NOT_EVALUATED", "BLOCKED", "BLOCKED")
    assert res.scan is None and res.market_state is None
    assert feed.calls == [] and (calls.clock, calls.spread) == (0, 0)  # nothing read


@pytest.mark.parametrize("symbol", ["GBPUSD", "USDJPY"])
def test_unmapped_production_symbols_are_not_configured_and_never_fall_back(symbol):
    res, feed, calls = gscan(symbol, metadata=None)
    s = res.summary()
    assert (res.status, res.reason_codes) == (CANONICAL_IDENTITY_NOT_CONFIGURED, (CANONICAL_IDENTITY_NOT_CONFIGURED,))
    assert s["canonical_identity"]["resolution"] == CANONICAL_IDENTITY_NOT_CONFIGURED
    assert (s["opportunity"], s["proposal"], s["trade_ticket"]) == ("NOT_EVALUATED", "BLOCKED", "BLOCKED")
    assert feed.calls == [] and calls.clock == 0
    assert canonical_id_for(symbol, VENUE) is None


def test_canonical_lookup_is_exact_registry_driven():
    assert venue_for_broker("VT_MARKETS") == VENUE and venue_for_broker("VANTAGE") is None
    assert canonical_id_for("EURUSD", VENUE) == "FX.EURUSD"
    for alias in ("EURUSD+", "EURUSD-VIP", "eurusd", "EUR/USD"):
        assert canonical_id_for(alias, VENUE) is None


def test_market_state_server_mismatch_blocks_strategy_even_when_identity_resolves():
    res, feed, _ = gscan(clock=[{"broker": "VANTAGE", "server": "Vantage-Demo"}])
    assert res.resolution.status == "RESOLVED" and res.reason_codes == ("MARKET_STATE_SERVER_MISMATCH",)
    s = res.summary()
    assert (s["marketstate_authority"], s["market_data_readable"], s["opportunity"]) == ("BLOCKED", True, "NOT_EVALUATED")
    assert res.scan is None and s["market_state"]["symbol"] == "EURUSD"


def test_time_authority_failure_is_marketstate_unavailable():
    def failing():
        raise MarketDataError("SERVER_TIME_AUTHORITY_UNRESOLVED", "fixture")
    res = gated_scan_symbol(CTX, "EURUSD", venue_id=VENUE, observed_server=SERVER, exposed_symbols=LIVE_EXPOSED,
                            metadata=meta(), trading_date=NOW.date(), now=NOW, fetch_candles=Feed(ready_bars("EURUSD")),
                            market_data_mode="REAL", source="fixture", server_clock_provider=failing)
    assert (res.status, res.reason_codes, res.scan) == (MARKETSTATE_UNAVAILABLE, ("SERVER_TIME_AUTHORITY_UNRESOLVED",), None)


def test_marketstate_divergence_fails_closed(monkeypatch):
    real = scanner.scan_symbol

    def diverging(*a, **k):
        out = real(*a, **k)
        return dataclasses.replace(out, market_state=dataclasses.replace(out.market_state, fingerprint="0" * 64))
    monkeypatch.setattr(gs.scanner, "scan_symbol", diverging)
    res, _, _ = gscan()
    assert res.status == MARKETSTATE_FINGERPRINT_DIVERGENCE and res.scan is None
    assert res.summary()["opportunity"] == "NOT_EVALUATED"


# --- entrypoint ----------------------------------------------------------------------

SCRIPT = REPO / "scripts" / "run_fx_opportunity_once.py"


def test_live_runner_starts_safely_from_a_foreign_cwd(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "--cycle" in proc.stdout


def test_entrypoint_routes_every_symbol_through_the_identity_gate():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
             for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "gated_scan_symbol" in calls and "scan_symbol" not in calls  # no raw-symbol fallback
    assert not calls & {"order_send", "order_check", "positions_get", "positions_total", "orders_get"}
    assert "os.chdir(_REPO)" in SCRIPT.read_text(encoding="utf-8")


# --- containment ---------------------------------------------------------------------

MUTATION_APIS = ("order_send", "order_check", "positions_get", "positions_total", "orders_get", "orders_total",
                 "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel", "symbol_select")


def test_static_gated_scan_has_no_mt5_calls_or_execution_imports():
    tree = ast.parse((REPO / "src/instrument_registry/fx_gated_scan.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            assert name not in MUTATION_APIS + ("initialize", "login", "symbols_get", "symbol_info"), name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                assert m.split(".")[0] not in ("MetaTrader5", "execution", "authorization", "ticket_delivery",
                                               "owner_decision", "scheduler", "trade_management"), m


def test_transitive_imports_have_no_execution_roots():
    code = ("import sys; import instrument_registry.fx_gated_scan; "
            "bad=[m for m in sys.modules if m.split('.')[0] in ('execution','authorization','ticket_delivery',"
            "'owner_decision','scheduler','trade_management') or m in ('mt5.connection','mt5.management_gateway',"
            "'mt5.mt5_gateway')]; print(bad); sys.exit(1 if bad else 0)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_runtime_zero_broker_mutation_calls(monkeypatch):
    hits = []
    for api in MUTATION_APIS:
        monkeypatch.setattr(MetaTrader5, api, lambda *a, _n=api, **k: hits.append(_n), raising=False)
    gscan()
    gscan(exposed=("EURUSD+",), metadata=meta("EURUSD+"))
    gscan("GBPUSD", metadata=None)
    assert hits == []
