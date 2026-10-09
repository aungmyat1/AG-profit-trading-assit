"""AGP-C2-SYMMAP -- hermetic tests for the versioned CANONICAL_TO_BROKER_MAP, driven by the
committed host evidence. No MT5 import."""
import copy
import importlib.util
import json
import os
import sys

import pytest
import yaml

from mt5 import broker_symbol_resolver, canonical_broker_map as cbm, mt5_candles_readonly

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
EVIDENCE = os.path.join(ROOT, "status", "evidence", "host_symbol_info_2026-10-09_symmap.json")
C1_EVIDENCE = os.path.join(ROOT, "status", "evidence", "host_symbol_info_2026-10-09.json")
EXPECTED = {"EURUSD": "EURUSD-VIP", "GBPUSD": "GBPUSD-VIP", "USDJPY": "USDJPY-VIP",
            "XAUUSD": "XAUUSD-VIP", "BTCUSD": "BTCUSD", "ETHUSD": "ETHUSD"}


@pytest.fixture(scope="module")
def evidence():
    with open(EVIDENCE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def symbols(evidence):
    return copy.deepcopy(evidence["symbols"])


def _write_map(tmp_path, entries, **over):
    raw = {"schema": cbm.SCHEMA, "map_version": 1, "broker": "VT_MARKETS", "server": "VTMarkets-Demo",
           "evidence": "x.json", "entries": entries, **over}
    p = tmp_path / "map.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return str(p)


# --- committed map vs committed evidence ---------------------------------------------------

def test_committed_map_maps_all_six(evidence):
    m = cbm.load_map()
    assert m.version == 1 and m.broker == cbm.BROKER and m.server == evidence["account"]["server"]
    assert m.evidence == os.path.relpath(EVIDENCE, ROOT).replace(os.sep, "/")
    assert m.mapped_symbols() == EXPECTED


def test_committed_map_equals_rule_applied_to_evidence(evidence):
    assert cbm.derive_map(evidence["symbols"]) == evidence["derived_map"]
    assert cbm.diff_map(cbm.load_map(), evidence["symbols"]) == []


def test_evidence_is_demo_read_only(evidence):
    assert evidence["account"]["trade_mode"] == "DEMO"
    guard = evidence["read_only_guard"]
    assert guard["forbidden_calls"] == [] and guard["broker_mutations"] == 0
    assert guard["market_watch_visibility_unchanged"] is True
    assert set(guard["mt5_calls"]) <= {"initialize", "shutdown", "last_error", "account_info", "symbol_info",
                                       "symbol_info_tick"}


def test_prior_c1_capture_derives_the_same_names():
    with open(C1_EVIDENCE, encoding="utf-8") as f:
        c1 = json.load(f)["symbols"]
    derived = cbm.derive_map(c1)
    assert {c: e.get("broker_symbol") for c, e in derived.items()} == EXPECTED


# --- map rule: fail-closed cases -----------------------------------------------------------

def test_disabled_only_is_unmapped(symbols):
    symbols["EURUSD-VIP"]["trade_mode_name"] = "DISABLED"
    entry = cbm.derive_map(symbols)["EURUSD"]
    assert entry == {"status": cbm.UNMAPPED, "reason": cbm.REASON_NO_FULL}  # never falls back to plain EURUSD


def test_hidden_full_is_unmapped(symbols):
    symbols["XAUUSD-VIP"]["visible"] = False
    assert cbm.derive_map(symbols)["XAUUSD"]["status"] == cbm.UNMAPPED


def test_absent_symbol_is_unmapped(symbols):
    symbols["BTCUSD"] = None
    assert cbm.derive_map(symbols)["BTCUSD"] == {"status": cbm.UNMAPPED, "reason": cbm.REASON_NO_FULL}


def test_ambiguous_full_candidates_are_unmapped(symbols):
    symbols["GBPUSD"]["trade_mode_name"] = "FULL"
    entry = cbm.derive_map(symbols)["GBPUSD"]
    assert entry["status"] == cbm.UNMAPPED and entry["reason"].startswith(cbm.REASON_AMBIGUOUS)
    assert "GBPUSD-VIP" in entry["reason"]


def test_diff_reports_live_drift(symbols):
    symbols["USDJPY-VIP"]["digits"] = 2
    symbols["ETHUSD"]["trade_mode_name"] = "CLOSEONLY"
    diffs = cbm.diff_map(cbm.load_map(), symbols)
    assert "USDJPY: digits 3 -> 2" in diffs
    assert any(d.startswith("ETHUSD: status MAPPED -> UNMAPPED") for d in diffs)


# --- loader / resolve ----------------------------------------------------------------------

def test_unmapped_resolve_is_typed_blocked(tmp_path):
    path = _write_map(tmp_path, {"XAUUSD": {"status": "UNMAPPED", "reason": cbm.REASON_NO_FULL}})
    m = cbm.load_map(path)
    for canonical in ("XAUUSD", "AUDUSD"):
        with pytest.raises(cbm.SymbolUnmapped) as e:
            m.resolve(canonical)
        assert e.value.terminal_status == "BLOCKED" and e.value.reason_code == cbm.REASON_UNMAPPED
    with pytest.raises(cbm.SymbolUnmapped) as exc:
        m.mapped_symbols()
    assert exc.value.canonical == "XAUUSD"
    assert exc.value.terminal_status == "BLOCKED"
    assert exc.value.reason_code == cbm.REASON_UNMAPPED


@pytest.mark.parametrize("entries, over", [
    ({"EURUSD": {"status": "MAPPED", "broker_symbol": "EURUSD", "expected": {"trade_mode_name": "DISABLED"}}}, {}),
    ({"EURUSD": {"status": "UNMAPPED", "reason": "x", "broker_symbol": "EURUSD"}}, {}),
    ({"EURUSD": {"status": "UNMAPPED"}}, {}),
    ({"EURUSD": {"status": "GUESS", "broker_symbol": "EURUSD"}}, {}),
    ({"EURUSD": {"status": "MAPPED", "broker_symbol": "X", "expected": {"trade_mode_name": "FULL"}},
      "GBPUSD": {"status": "MAPPED", "broker_symbol": "X", "expected": {"trade_mode_name": "FULL"}}}, {}),
    ({}, {"schema": "OTHER"}),
])
def test_malformed_map_is_rejected(tmp_path, entries, over):
    with pytest.raises(cbm.SymbolMapError):
        cbm.load_map(_write_map(tmp_path, entries, **over))


# --- consumers resolve through the loader --------------------------------------------------

def test_broker_symbol_resolver_vt_markets_uses_map():
    for canonical, broker in EXPECTED.items():
        assert broker_symbol_resolver.resolve_broker_symbol(canonical, "VT_MARKETS") == broker
    with pytest.raises(broker_symbol_resolver.BrokerSymbolMapError):
        broker_symbol_resolver.resolve_broker_symbol("AUDUSD", "VT_MARKETS")


def test_candle_adapter_default_map_comes_from_loader():
    expected = {c: EXPECTED[c] for c in mt5_candles_readonly.SUPPORTED_SYMBOLS}
    assert mt5_candles_readonly.default_symbol_map() == expected


# --- host smoke script stays read-only -----------------------------------------------------

def _load_smoke():
    path = os.path.join(ROOT, "scripts", "host", "symbol_map_smoke.py")
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("symbol_map_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def test_smoke_proxy_refuses_mutating_calls():
    smoke, path = _load_smoke()

    class Fake:
        def symbol_info(self, name):
            return None

        def symbol_select(self, name, enable):
            raise AssertionError("must never be reached")

        def order_send(self, req):
            raise AssertionError("must never be reached")

    proxy = smoke.ReadOnlyMT5(Fake())
    assert proxy.symbol_info("EURUSD") is None and proxy.calls == {"symbol_info": 1}
    for name in ("symbol_select", "order_send"):
        with pytest.raises(PermissionError):
            getattr(proxy, name)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    for banned in (".order_send", ".order_check", ".symbol_select", ".positions_", ".orders_"):
        assert banned not in src


def test_explicit_partial_mapping_fails_closed():
    symbol_map = cbm.load_map()
    for requested in (("EURUSD", "UNKNOWN"), ("EURUSD", "AUDUSD")):
        with pytest.raises(cbm.SymbolUnmapped) as exc:
            symbol_map.mapped_symbols(requested)
        assert exc.value.terminal_status == "BLOCKED"
        assert exc.value.reason_code == cbm.REASON_UNMAPPED


def test_smoke_proxy_checks_allowlist_before_underlying_getattr():
    smoke, _ = _load_smoke()

    class Probe:
        def __init__(self):
            self.accessed = []

        def __getattr__(self, name):
            self.accessed.append(name)
            raise AssertionError("unexpected underlying attribute read")

        def symbol_info(self, symbol):
            return None

    target = Probe()
    proxy = smoke.ReadOnlyMT5(target)
    for forbidden in ("order_send", "symbol_select", "account_password", "positions_get"):
        with pytest.raises(PermissionError):
            getattr(proxy, forbidden)
    assert target.accessed == []
    assert proxy.symbol_info("EURUSD") is None


def test_smoke_proxy_explicitly_allows_demo_constant_only():
    smoke, _ = _load_smoke()

    class Probe:
        ACCOUNT_TRADE_MODE_DEMO = 0

        def __init__(self):
            self.accessed = []

        def __getattr__(self, name):
            self.accessed.append(name)
            raise AssertionError("unexpected underlying attribute read")

    target = Probe()
    proxy = smoke.ReadOnlyMT5(target)
    assert proxy.ACCOUNT_TRADE_MODE_DEMO == 0
    with pytest.raises(PermissionError):
        _ = proxy.account_password
    assert target.accessed == []


def test_two_snapshots_detect_pinned_metadata_drift(symbols):
    other = copy.deepcopy(symbols)
    other["EURUSD-VIP"]["volume_step"] = 0.02
    smoke, _ = _load_smoke()
    assert smoke.snapshot_mapping_differences(symbols, other) == ["EURUSD"]


def test_two_snapshots_ignore_market_ticks(symbols):
    other = copy.deepcopy(symbols)
    other["EURUSD-VIP"]["tick"]["bid"] += 0.0001
    smoke, _ = _load_smoke()
    assert smoke.snapshot_mapping_differences(symbols, other) == []
