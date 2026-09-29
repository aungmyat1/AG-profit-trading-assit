"""WP-7A CANONICAL_INSTRUMENT_REGISTRY_V1: exact identity, drift, metadata, gates.

Broker facts come from the read-only VTMarkets-Demo evidence captured 2026-09-29
(artifacts/validation/CANONICAL_INSTRUMENT_REGISTRY_V1/). No MT5 contact in tests.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from fx_opportunity.instruments import get_broker, get_instrument
from instrument_registry import identity as idm
from instrument_registry.gates import envelope_for_ticket, gate_market_state
from instrument_registry.identity import (
    BROKER_METADATA_MISMATCH,
    BROKER_METADATA_UNAVAILABLE,
    BROKER_SYMBOL_DRIFT,
    INSTRUMENT_DISABLED,
    RESOLVED,
    SERVER_MISMATCH,
    UNKNOWN_CANONICAL_INSTRUMENT,
    UNKNOWN_REGISTRY_VERSION,
    VENUE_NOT_CONFIGURED,
    RegistryIntegrityError,
    load_registry,
    resolve_identity,
    resolve_many,
    snapshot_from_symbol_info,
)
from post_asian_pilot.fingerprint import fingerprint
from test_fx_opportunity_market_state import Feed, at, ready_bars, run

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads((REPO / "artifacts/validation/CANONICAL_INSTRUMENT_REGISTRY_V1/"
                       "EURUSD_VTMARKETS_DEMO_BROKER_EVIDENCE_2026-09-29.json").read_text(encoding="utf-8"))
VENUE, SERVER = "VT_MARKETS_MT5", "VTMarkets-Demo"
FIXTURE_DIR = REPO / "tests/fixtures/instrument_registry"
FIXTURE_VERSION = "instruments-test-v1"
LIVE_EXPOSED = tuple(EVIDENCE["exposed_names_containing_EURUSD"])  # ("EURUSD", "EURUSD-VIP")


def meta(symbol="EURUSD", server=SERVER, **kw):
    info = dict(EVIDENCE["symbol_info_EURUSD"], name=symbol)
    if symbol.startswith(("GBPUSD",)):
        info.update(currency_base="GBP")
    if symbol.startswith("USDJPY"):
        info.update(currency_base="USD", currency_profit="JPY", digits=3, point=0.001, trade_tick_size=0.001,
                    trade_tick_value=0.67)
    info.update(kw)
    return snapshot_from_symbol_info(SimpleNamespace(**info), venue_id=VENUE, server=server)


def resolve(cid="FX.EURUSD", *, venue=VENUE, server=SERVER, exposed=LIVE_EXPOSED, metadata="default", **kw):
    return resolve_identity(cid, venue_id=venue, observed_server=server, exposed_symbols=exposed,
                            metadata=meta() if metadata == "default" else metadata, **kw)


@pytest.fixture
def fixture_registry(monkeypatch):
    raw = yaml.safe_load((FIXTURE_DIR / f"{FIXTURE_VERSION}.yaml").read_text(encoding="utf-8"))
    monkeypatch.setitem(idm.REGISTRY_VERSIONS, FIXTURE_VERSION, fingerprint(raw))
    return dict(registry_version=FIXTURE_VERSION, registry_dir=str(FIXTURE_DIR))


# --- exact identity ------------------------------------------------------------------


def test_eurusd_exact_identity_resolves_against_live_broker_evidence():
    r = resolve()
    assert r.status == RESOLVED and r.observed_symbol == "EURUSD"
    i = r.identity
    assert (i.canonical_instrument_id, i.asset_class, i.base_asset, i.quote_asset, i.product_type) == \
        ("FX.EURUSD", "FX", "EUR", "USD", "SPOT_FX")
    assert (i.venue_id, i.server, i.venue_symbol, i.enabled, i.registry_version) == \
        (VENUE, SERVER, "EURUSD", True, "instruments-v1.0.0")
    assert r.identity_fingerprint == EVIDENCE["identity_fingerprint"] == i.fingerprint()
    assert r.metadata_fingerprint == EVIDENCE["broker_metadata_fingerprint"]
    # EURUSD-VIP is exposed by the real broker too; exact match picks EURUSD and ignores it
    assert "EURUSD-VIP" in LIVE_EXPOSED


def test_published_registry_contains_only_eurusd_and_no_crypto():
    reg = load_registry("instruments-v1.0.0")
    assert list(reg.instruments) == ["FX.EURUSD"]


def test_registry_agrees_with_platform_instrument_contract():
    ident = load_registry("instruments-v1.0.0").instruments["FX.EURUSD"][VENUE].identity
    inst, broker = get_instrument("EURUSD"), get_broker("VTMARKETS")
    assert inst.broker_symbol("VTMARKETS").symbol == ident.venue_symbol
    assert ident.server in broker.servers and broker.canonical_name == "VT_MARKETS"
    assert (inst.base_currency, inst.quote_currency) == (ident.base_asset, ident.quote_asset)
    exp = load_registry("instruments-v1.0.0").instruments["FX.EURUSD"][VENUE].expected_metadata
    assert (exp["digits"], exp["point"]) == (inst.digits, inst.point)


# --- fail-closed states --------------------------------------------------------------


def test_wrong_server():
    r = resolve(server="VTMarkets-Live")
    assert (r.status, r.expected_server, r.observed_server) == (SERVER_MISMATCH, SERVER, "VTMarkets-Live")
    assert resolve(metadata=meta(server="Other-Demo")).status == SERVER_MISMATCH


def test_wrong_venue():
    assert resolve(venue="BYBIT").status == VENUE_NOT_CONFIGURED


@pytest.mark.parametrize("observed", ["EURUSD+", "EURUSD-VIP", "EURUSD.a", "eurusd", "EURUSDm"])
def test_symbol_drift_is_exact_and_never_remapped(observed):
    r = resolve(exposed=(observed, "GBPUSD"), metadata=meta(observed))
    assert r.status == BROKER_SYMBOL_DRIFT and r.identity is None and r.identity_fingerprint is None
    assert (r.expected_symbol, r.registry_version, r.venue_id, r.observed_server) == \
        ("EURUSD", "instruments-v1.0.0", VENUE, SERVER)
    assert r.metadata_fingerprint == meta(observed).fingerprint()
    if observed.startswith("EURUSD"):
        assert r.observed_symbol == observed and r.drift_evidence_symbols == (observed,)


def test_metadata_for_a_different_symbol_is_drift_even_if_expected_is_exposed():
    r = resolve(metadata=meta("EURUSD-VIP"))
    assert (r.status, r.observed_symbol) == (BROKER_SYMBOL_DRIFT, "EURUSD-VIP")


def test_unknown_canonical_id_and_unknown_version():
    assert resolve("FX.XAUUSD").status == UNKNOWN_CANONICAL_INSTRUMENT
    assert resolve("CRYPTO.BTCUSD").status == UNKNOWN_CANONICAL_INSTRUMENT
    assert resolve(registry_version="instruments-v9.9.9").status == UNKNOWN_REGISTRY_VERSION


def test_disabled_instrument(fixture_registry):
    r = resolve("FX.AUDUSD", exposed=("AUDUSD",), metadata=meta("AUDUSD"), **fixture_registry)
    assert r.status == INSTRUMENT_DISABLED


@pytest.mark.parametrize("override, field", [
    ({"digits": 3}, "digits"), ({"point": 0.001}, "point"), ({"trade_tick_size": 0.0001}, "tick_size"),
    ({"trade_contract_size": 1000.0}, "contract_size"), ({"volume_min": 0.1}, "volume_min"),
    ({"volume_step": 0.1}, "volume_step"), ({"volume_max": 50.0}, "volume_max"),
    ({"currency_base": "GBP"}, "currency_base"), ({"currency_profit": "JPY"}, "currency_profit"),
    ({"trade_tick_value": -1.0}, "tick_value"),
])
def test_metadata_mismatch(override, field):
    r = resolve(metadata=meta(**override))
    assert r.status == BROKER_METADATA_MISMATCH and r.mismatched_fields == (field,) and r.identity is None


def test_informational_metadata_does_not_gate_identity():
    assert resolve(metadata=meta(trade_mode=4, trade_exemode=0, filling_mode=1)).status == RESOLVED
    assert EVIDENCE["symbol_info_EURUSD"]["trade_mode"] == 0  # observed DISABLED -> reported, not an identity fact


@pytest.mark.parametrize("kwargs, fields", [
    (dict(metadata=None), ()), (dict(exposed=None), ()),
    (dict(metadata="tick_value_none"), ("tick_value",)), (dict(metadata="nan_point"), ("point",)),
    (dict(metadata="no_currency"), ("currency_base",)),
])
def test_metadata_unavailable(kwargs, fields):
    special = {"tick_value_none": meta(trade_tick_value=None), "nan_point": meta(point=float("nan")),
               "no_currency": meta(currency_base=None)}
    if isinstance(kwargs.get("metadata"), str):
        kwargs = dict(kwargs, metadata=special[kwargs["metadata"]])
    r = resolve(**kwargs)
    assert r.status == BROKER_METADATA_UNAVAILABLE and r.mismatched_fields == fields


# --- fingerprints / versioning -------------------------------------------------------


def test_identity_and_metadata_fingerprints_are_deterministic_and_separate():
    a, b = resolve(), resolve()
    assert (a.identity_fingerprint, a.metadata_fingerprint) == (b.identity_fingerprint, b.metadata_fingerprint)
    later = dataclasses.replace(meta(), observed_at="2026-09-30T00:00:00+00:00", source="OTHER_PROBE")
    assert later.fingerprint() == meta().fingerprint()  # audit context excluded
    changed = resolve(metadata=meta(trade_mode=4))
    assert changed.metadata_fingerprint != a.metadata_fingerprint
    assert changed.identity_fingerprint == a.identity_fingerprint  # metadata never rewrites identity


def test_registry_version_change_alters_identity_fingerprint(fixture_registry):
    published = resolve().identity_fingerprint
    other = resolve(exposed=("EURUSD",), **fixture_registry)
    assert other.status == RESOLVED and other.identity.registry_version == FIXTURE_VERSION
    assert other.identity_fingerprint != published


def test_published_version_cannot_be_edited_in_place(tmp_path):
    shutil.copy(REPO / "config/instruments/registry/instruments-v1.0.0.yaml", tmp_path)
    p = tmp_path / "instruments-v1.0.0.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("venue_symbol: EURUSD", "venue_symbol: EURUSD+"),
                 encoding="utf-8")
    with pytest.raises(RegistryIntegrityError):
        load_registry("instruments-v1.0.0", str(tmp_path))


def test_unpinned_version_file_is_unknown(tmp_path):
    shutil.copy(REPO / "config/instruments/registry/instruments-v1.0.0.yaml", tmp_path / "instruments-v1.0.1.yaml")
    assert load_registry("instruments-v1.0.1", str(tmp_path)) is None


# --- partial platform continuity -----------------------------------------------------


def test_one_instrument_drift_does_not_block_others(fixture_registry):
    exposed = ("EURUSD+", "GBPUSD", "USDJPY")
    out = resolve_many(["FX.EURUSD", "FX.GBPUSD", "FX.USDJPY", "FX.AUDUSD", "FX.NOPE"], venue_id=VENUE,
                       observed_server=SERVER, exposed_symbols=exposed,
                       metadata_by_symbol={"GBPUSD": meta("GBPUSD"), "USDJPY": meta("USDJPY")},
                       **fixture_registry)
    assert {k: v.status for k, v in out.items()} == {
        "FX.EURUSD": BROKER_SYMBOL_DRIFT, "FX.GBPUSD": RESOLVED, "FX.USDJPY": RESOLVED,
        "FX.AUDUSD": INSTRUMENT_DISABLED, "FX.NOPE": UNKNOWN_CANONICAL_INSTRUMENT}


# --- MarketState gate ----------------------------------------------------------------

CLOCK = [{"broker": "VT_MARKETS", "server": SERVER}]


def market_state(symbol="EURUSD", mode="REAL", server_clock=CLOCK):
    return run(symbol, Feed(ready_bars(symbol)), at(7, 31), mode=mode, server_clock=server_clock).market_state


def test_resolved_identity_makes_matching_market_state_authoritative():
    g = gate_market_state(resolve(), market_state())
    assert g.authoritative and (g.opportunity, g.proposal, g.tradeticket) == ("MAY_EVALUATE",) + ("MAY_PROCEED",) * 2
    assert g.identity_fingerprint == resolve().identity_fingerprint


@pytest.mark.parametrize("resolution", [
    dict(exposed=("EURUSD+",), metadata=meta("EURUSD+")), dict(server="VTMarkets-Live"), dict(metadata=None)])
def test_identity_failure_blocks_market_state_authority(resolution):
    r = resolve(**resolution)
    g = gate_market_state(r, market_state())
    assert (g.marketstate_authority, g.market_data_readable, g.opportunity, g.proposal, g.tradeticket) == \
        ("BLOCKED", True, "NOT_EVALUATED", "BLOCKED", "BLOCKED")
    assert g.reason_codes == (r.status,)


def test_market_state_must_match_the_resolved_identity():
    assert gate_market_state(resolve(), market_state("GBPUSD")).reason_codes == ("MARKET_STATE_INSTRUMENT_MISMATCH",)
    assert gate_market_state(resolve(), market_state(server_clock=None)).reason_codes == \
        ("MARKET_STATE_SERVER_UNVERIFIED",)
    wrong = [{"broker": "VANTAGE", "server": "Vantage-Demo"}]
    assert gate_market_state(resolve(), market_state(server_clock=wrong)).reason_codes == \
        ("MARKET_STATE_SERVER_MISMATCH",)
    assert gate_market_state(resolve(), market_state(mode="REPLAY", server_clock=None)).authoritative


# --- frozen TradeTicket envelope -----------------------------------------------------


def frozen_ticket(symbol="EURUSD"):
    from test_trade_ticket_vertical_slice import prepare
    return prepare(symbol).ticket


def test_envelope_binds_frozen_ticket_without_changing_its_schema():
    t = frozen_ticket()
    env, reasons = envelope_for_ticket(t, resolve())
    assert reasons == () and env.ticket_semantic_fingerprint == t.semantic_fingerprint
    assert (env.canonical_instrument_id, env.instrument_registry_version, env.venue_id, env.venue_symbol) == \
        ("FX.EURUSD", "instruments-v1.0.0", VENUE, "EURUSD")
    assert env.instrument_identity_fingerprint == resolve().identity_fingerprint
    assert env.broker_metadata_fingerprint == resolve().metadata_fingerprint
    assert env == envelope_for_ticket(frozen_ticket(), resolve())[0]  # deterministic
    assert not {"canonical_instrument_id", "instrument_registry_version"} & set(t.to_dict())  # V1 untouched


def test_envelope_fails_closed():
    t = frozen_ticket()
    assert envelope_for_ticket(t, resolve(exposed=("EURUSD+",), metadata=meta("EURUSD+"))) == \
        (None, (BROKER_SYMBOL_DRIFT,))
    assert envelope_for_ticket(frozen_ticket("GBPUSD"), resolve())[1] == \
        ("TICKET_INSTRUMENT_MISMATCH", "TICKET_VENUE_SYMBOL_MISMATCH")
    tampered = dataclasses.replace(t, semantic_fingerprint="0" * 64)
    assert envelope_for_ticket(tampered, resolve())[1] == ("TICKET_VERIFICATION_FAILED",)


# --- containment ---------------------------------------------------------------------

PKG = REPO / "src" / "instrument_registry"
MUTATION_APIS = ("order_send", "order_check", "positions_get", "positions_total", "orders_get", "orders_total",
                 "symbol_select", "initialize", "login")
FORBIDDEN_ROOTS = ("execution", "execution_runtime", "authorization", "ticket_delivery", "notifications",
                   "owner_decision", "strategy_manager", "trade_management", "scheduler", "MetaTrader5")


def test_static_no_mt5_or_execution_capability():
    for path in PKG.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                assert name not in MUTATION_APIS, (path, name)
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            for n in names:
                assert n.split(".")[0] not in FORBIDDEN_ROOTS, (path, n)


def test_identity_module_imports_no_mt5_transitively():
    code = ("import sys; import instrument_registry.identity; "
            "bad=[m for m in sys.modules if m.split('.')[0] in ('MetaTrader5','execution','authorization',"
            "'ticket_delivery','owner_decision','scheduler')]; print(bad); sys.exit(1 if bad else 0)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_gates_transitive_imports_have_no_execution_roots():
    code = ("import sys; import instrument_registry.gates; "
            "bad=[m for m in sys.modules if m.split('.')[0] in ('execution','authorization','ticket_delivery',"
            "'owner_decision','scheduler') or m in ('mt5.connection','mt5.management_gateway','mt5.mt5_gateway')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --- WP-7A R1: registry path is independent of the process cwd -----------------------


def _envelope_from_cwd(cwd):
    proc = subprocess.run([sys.executable, str(REPO / "tests" / "_cwd_envelope_probe.py"), str(cwd)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_registry_dir_is_package_anchored_not_cwd_relative():
    assert Path(idm.REGISTRY_DIR).is_absolute()
    assert Path(idm.REGISTRY_DIR) == REPO / "config" / "instruments" / "registry"


def test_envelope_operation_is_identical_from_every_cwd(tmp_path):
    results = {name: _envelope_from_cwd(cwd) for name, cwd in (
        ("repo_root", REPO), ("scripts", REPO / "scripts"), ("src", REPO / "src"), ("temp", tmp_path))}
    root = results["repo_root"]
    assert root["status"] == RESOLVED and root["registry_version"] == "instruments-v1.0.0"
    assert root["identity_fingerprint"] == EVIDENCE["identity_fingerprint"]
    assert root["metadata_fingerprint"] == EVIDENCE["broker_metadata_fingerprint"]
    assert root["envelope"] is not None and root["reasons"] == []
    for name, out in results.items():
        assert out == root, name
