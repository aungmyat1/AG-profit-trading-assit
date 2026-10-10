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
FULL_EXPECTED = {"trade_mode_name": "FULL", "visible": True, "digits": 5, "point": 1e-05,
                 "trade_contract_size": 100000.0, "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0,
                 "trade_tick_size": 1e-05, "trade_calc_mode": 0}


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
    # The C1 capture predates trade_calc_mode, so it cannot pin a complete mapping on its own ...
    derived = cbm.derive_map(c1)
    assert {c: e.get("reason") for c, e in derived.items()} == {
        c: f"{cbm.REASON_INCOMPLETE}: trade_calc_mode" for c in EXPECTED}
    # ... but its candidate selection agrees with the symmap capture once that field is supplied.
    for rec in c1.values():
        if rec is not None:
            rec.setdefault("trade_calc_mode", 0)
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
    ({"EURUSD": {"status": "MAPPED", "broker_symbol": "X", "expected": FULL_EXPECTED},
      "GBPUSD": {"status": "MAPPED", "broker_symbol": "X", "expected": FULL_EXPECTED}}, {}),
    ({"EURUSD": {"status": "MAPPED", "broker_symbol": "X",
                 "expected": {k: v for k, v in FULL_EXPECTED.items() if k != "volume_step"}}}, {}),
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


def test_complete_pinned_map_loads(tmp_path):
    m = cbm.load_map(_write_map(tmp_path, {"EURUSD": {"status": "MAPPED", "broker_symbol": "X", "expected": FULL_EXPECTED}}))
    assert m.resolve("EURUSD") == "X"


def test_incomplete_pinned_metadata_is_unmapped(symbols):
    symbols["EURUSD-VIP"]["volume_step"] = None
    entry = cbm.derive_map(symbols)["EURUSD"]
    assert entry["status"] == cbm.UNMAPPED and entry["reason"] == f"{cbm.REASON_INCOMPLETE}: volume_step"


# --- MT5 symbol_info lookup contract (hermetic: fake terminal, no MT5 import) ----------------

def _present(name, rec):
    from types import SimpleNamespace
    skip = {"canonical", "trade_mode_name", "trade_calc_mode_name", "swap_mode_name", "tick", "commission"}
    return SimpleNamespace(name=name, **{f: v for f, v in rec.items() if f not in skip})


class FakeTerminal:
    """Fake MetaTrader5 module built from committed evidence. Every attribute that is not defined
    here raises, so the proxy can only reach what is listed."""
    ACCOUNT_TRADE_MODE_DEMO = 0
    __version__ = "fake"

    def __init__(self, evidence, missing_error=(-4, "Terminal: Not found"), server="VTMarkets-Demo",
                 inventory_extra=(), total_delta=0):
        from types import SimpleNamespace
        self._ns = SimpleNamespace
        self.records = {n: r for n, r in evidence["symbols"].items() if r is not None}
        self.missing_error = missing_error
        self.server = server
        self.inventory = sorted(self.records) + list(inventory_extra)
        self.total_delta = total_delta
        self._error = (1, "Success")
        self.log = []

    def initialize(self, **kwargs):
        self.log.append("initialize")
        return True

    def shutdown(self):
        self.log.append("shutdown")

    def last_error(self):
        return self._error

    def account_info(self):
        return self._ns(server=self.server, trade_mode=0, currency="USD")

    def symbols_get(self):
        return tuple(self._ns(name=n) for n in self.inventory)

    def symbols_total(self):
        return len(self.inventory) + self.total_delta

    def symbol_info(self, name):
        self.log.append(("symbol_info", name))
        if name in self.records:
            self._error = (1, "Success")
            return _present(name, self.records[name])
        self._error = self.missing_error
        return None

    def symbol_info_tick(self, name):
        tick = self.records[name]["tick"]
        return None if tick is None else self._ns(**tick)


@pytest.mark.parametrize("info_name, error, inventory, expected", [
    ("EURUSD-VIP", None, frozenset({"EURUSD-VIP"}), "SYMBOL_PRESENT"),
    (None, (-4, "Terminal: Not found"), frozenset({"EURUSD-VIP"}), "SYMBOL_ABSENT_CONFIRMED"),
    (None, (-4, "Terminal: Not found"), frozenset({"EURUSD.crp"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (-4, "Terminal: Not found"), None, "MT5_RESPONSE_AMBIGUOUS"),
    (None, (4301, "unknown symbol"), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (1, "Success"), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (0, ""), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (-1, "generic fail"), frozenset({"EURUSD-VIP"}), "MT5_API_ERROR"),
    (None, (-10004, "No IPC connection"), frozenset({"EURUSD-VIP"}), "MT5_API_ERROR"),
    (None, (-99, "unknown negative"), frozenset({"EURUSD-VIP"}), "MT5_API_ERROR"),
    (None, (-10005, "IPC timeout"), frozenset({"EURUSD-VIP"}), "MT5_TIMEOUT"),
    (None, None, frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, ("-4", "x"), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (-4,), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    (None, (True, "x"), frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),
    ("EURUSD", None, frozenset({"EURUSD-VIP"}), "MT5_RESPONSE_AMBIGUOUS"),     # record for another name
])
def test_symbol_lookup_classification(info_name, error, inventory, expected):
    from types import SimpleNamespace
    smoke, _ = _load_smoke()
    name = "EURUSD-VIP" if expected == "SYMBOL_PRESENT" or info_name else "EURUSD.crp"
    info = None if info_name is None else SimpleNamespace(name=info_name)
    classification, detail = smoke.classify_symbol_lookup(name, info, error, inventory)
    assert classification == expected, detail


def test_package_result_codes_match_installed_package():
    mt5 = pytest.importorskip("MetaTrader5")  # import only; no terminal contact
    mod_path = os.path.normcase(os.path.abspath(mt5.__file__))
    if mod_path.startswith(os.path.normcase(ROOT) + os.sep) and "site-packages" not in mod_path:
        pytest.skip("repo MetaTrader5 stub, not the installed package")
    smoke, _ = _load_smoke()
    assert (smoke.RES_S_OK, smoke.RES_E_NOT_FOUND, smoke.RES_E_INTERNAL_FAIL_TIMEOUT) == (
        mt5.RES_S_OK, mt5.RES_E_NOT_FOUND, mt5.RES_E_INTERNAL_FAIL_TIMEOUT)
    assert 4301 not in {getattr(mt5, k) for k in dir(mt5) if k.startswith("RES_")}


def test_capture_classifies_every_candidate(evidence):
    smoke, _ = _load_smoke()
    lookups = {}
    out = smoke.capture_symbols(smoke.ReadOnlyMT5(FakeTerminal(evidence)), lookups)
    assert out.keys() == evidence["symbols"].keys()
    for name, rec in evidence["symbols"].items():
        want = "SYMBOL_ABSENT_CONFIRMED" if rec is None else "SYMBOL_PRESENT"
        assert lookups[name]["classification"] == want
    assert cbm.diff_map(cbm.load_map(), out) == []


@pytest.mark.parametrize("fake_kwargs, classification", [
    ({"missing_error": (4301, "unknown symbol")}, "MT5_RESPONSE_AMBIGUOUS"),
    ({"missing_error": (-1, "fail")}, "MT5_API_ERROR"),
    ({"missing_error": (-10005, "IPC timeout")}, "MT5_TIMEOUT"),
    ({"missing_error": None}, "MT5_RESPONSE_AMBIGUOUS"),
    ({"inventory_extra": ("EURUSD.crp",)}, "MT5_RESPONSE_AMBIGUOUS"),   # -4 but listed in inventory
    ({"total_delta": 1}, "MT5_RESPONSE_AMBIGUOUS"),                     # incomplete inventory
])
def test_capture_blocks_unresolved_lookup(evidence, fake_kwargs, classification):
    smoke, _ = _load_smoke()
    with pytest.raises(smoke.SymbolLookupBlocked) as exc:
        smoke.capture_symbols(smoke.ReadOnlyMT5(FakeTerminal(evidence, **fake_kwargs)))
    assert exc.value.classification == classification


def test_capture_timeout_is_not_absence(evidence, monkeypatch):
    smoke, _ = _load_smoke()
    real_call = smoke.call_with_timeout

    def call(fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "wrapped" and args == ("EURUSD.crp",):
            raise smoke.CallTimeout("symbol_info exceeded 10s")
        return real_call(fn, *args, **kwargs)

    monkeypatch.setattr(smoke, "call_with_timeout", call)
    lookups = {}
    with pytest.raises(smoke.SymbolLookupBlocked) as exc:
        smoke.capture_symbols(smoke.ReadOnlyMT5(FakeTerminal(evidence)), lookups)
    assert exc.value.classification == "MT5_TIMEOUT" and exc.value.name == "EURUSD.crp"
    assert lookups["EURUSD.crp"]["classification"] == "MT5_TIMEOUT"


def test_demo_constant_must_be_noncallable():
    smoke, _ = _load_smoke()

    class Probe:
        def ACCOUNT_TRADE_MODE_DEMO(self):
            return 0

    with pytest.raises(PermissionError):
        _ = smoke.ReadOnlyMT5(Probe()).ACCOUNT_TRADE_MODE_DEMO


def test_account_gate():
    from types import SimpleNamespace
    smoke, _ = _load_smoke()
    assert smoke.account_gate(SimpleNamespace(server="VTMarkets-Demo"), "VTMarkets-Demo") is None
    assert smoke.account_gate(SimpleNamespace(server="VTMarkets-Live"), "VTMarkets-Demo").startswith("SERVER_MISMATCH")
    assert smoke.account_gate(None, "VTMarkets-Demo") == "ACCOUNT_INFO_UNAVAILABLE"


def _patch_run(smoke, monkeypatch, fake):
    import contextlib
    monkeypatch.setattr(smoke, "import_mt5", lambda: fake)
    monkeypatch.setattr(smoke, "mt5_access_lock", contextlib.nullcontext)


def test_run_smoke_end_to_end_read_only(evidence, monkeypatch, capsys):
    smoke, _ = _load_smoke()
    fake = FakeTerminal(evidence)
    _patch_run(smoke, monkeypatch, fake)
    assert smoke.run("smoke") == 0
    out = capsys.readouterr().out
    assert "DIFF EMPTY" in out and "METADATA_STABILITY PASS" in out
    counts = json.loads(out.split("SYMBOL_LOOKUP_CLASSIFICATIONS ", 1)[1].splitlines()[0])
    present = sum(r is not None for r in evidence["symbols"].values())
    assert counts == {"SYMBOL_ABSENT_CONFIRMED": len(evidence["symbols"]) - present, "SYMBOL_PRESENT": present}
    guard = json.loads(out.split("READ_ONLY_GUARD ", 1)[1].splitlines()[0])
    assert guard["forbidden_calls"] == [] and guard["broker_mutations"] == 0
    assert set(guard["mt5_calls"]) <= smoke.ALLOWED_MT5_CALLS


def test_run_server_mismatch_blocks_before_symbol_reads(evidence, monkeypatch, capsys):
    smoke, _ = _load_smoke()
    fake = FakeTerminal(evidence, server="VTMarkets-Live")
    _patch_run(smoke, monkeypatch, fake)
    for mode in ("smoke", "capture"):
        assert smoke.run(mode) == 2
        assert "SERVER_MISMATCH" in capsys.readouterr().out
    assert not any(isinstance(e, tuple) for e in fake.log)


def test_run_blocks_on_ambiguous_lookup(evidence, monkeypatch, capsys):
    smoke, _ = _load_smoke()
    fake = FakeTerminal(evidence, missing_error=(4301, "unknown symbol"))
    _patch_run(smoke, monkeypatch, fake)
    assert smoke.run("smoke") == 2
    assert "BLOCKED: MT5_RESPONSE_AMBIGUOUS" in capsys.readouterr().out
    assert fake.log[-1] == "shutdown"


def test_capture_never_overwrites_evidence(evidence, monkeypatch, tmp_path):
    import datetime as dt
    smoke, _ = _load_smoke()
    _patch_run(smoke, monkeypatch, FakeTerminal(evidence))
    (tmp_path / "status" / "evidence").mkdir(parents=True)
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    fixed = dt.datetime(2026, 10, 9, 18, 0, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(smoke, "utcnow", lambda: fixed)
    assert smoke.run("capture") == 0
    written = list((tmp_path / "status" / "evidence").iterdir())
    assert [p.name for p in written] == ["host_symbol_info_2026-10-09T180000Z_symmap.json"]
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    assert doc["metadata_stability"]["mapping_critical_differences"] == []
    assert {c: e["broker_symbol"] for c, e in doc["derived_map"].items()} == EXPECTED
    with pytest.raises(FileExistsError):
        smoke.run("capture")
