"""AGP-C18-R4: process-wide read-only MT5 guard. Fake brokers only -- the positive control (a deliberate
order_send / order_check attempt) never runs against a real MT5 account."""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest
import yaml

from mt5 import readonly_guard as G

ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


class FakeBroker(types.ModuleType):
    """Stands in for the real MetaTrader5 module; records every call that reaches it."""

    def __init__(self, orders=(), deals=()):
        super().__init__("FakeMetaTrader5")
        self.reached, self.TIMEFRAME_M5 = [], 5
        self._orders, self._deals = list(orders), list(deals)

    def _hit(self, name, value=None):
        self.reached.append(name)
        return value

    def copy_rates_from_pos(self, *a):
        return self._hit("copy_rates_from_pos", [1, 2])

    def symbol_info_tick(self, *a):
        return self._hit("symbol_info_tick", types.SimpleNamespace(bid=1.0, ask=1.1, time=0))

    def symbol_info(self, *a):
        return self._hit("symbol_info", object())

    def order_calc_margin(self, *a):
        return self._hit("order_calc_margin", 1.0)

    def order_send(self, *a):
        return self._hit("order_send")

    def order_check(self, *a):
        return self._hit("order_check")

    def history_orders_get(self, *a):
        return self._hit("history_orders_get", self._orders)

    def history_deals_get(self, *a):
        return self._hit("history_deals_get", self._deals)


@pytest.fixture
def isolated_modules(monkeypatch):
    monkeypatch.setitem(sys.modules, "MetaTrader5", sys.modules.get("MetaTrader5"))
    yield


def test_reads_are_forwarded_and_counted(isolated_modules):
    real = FakeBroker()
    guard = G.install(real, "run-a")
    assert guard.copy_rates_from_pos("EURUSD", guard.TIMEFRAME_M5, 1, 2) == [1, 2]
    assert guard.symbol_info_tick("EURUSD").bid == 1.0 and guard.symbol_info("EURUSD") is not None
    assert guard.order_calc_margin() == 1.0                         # read-only calculator stays allowed
    c = G.counters_of(guard).as_dict()
    assert c["MT5_READ_CALLS"] == 4 and c["PROHIBITED_ORDER_API_ATTEMPTS"] == 0
    assert real.reached == ["copy_rates_from_pos", "symbol_info_tick", "symbol_info", "order_calc_margin"]


@pytest.mark.parametrize("call,key", [("order_send", "ORDER_SEND_ATTEMPTS"), ("order_check", "ORDER_CHECK_ATTEMPTS"),
                                      ("order_modify_anything", None)])
def test_positive_control_prohibited_calls_never_reach_the_fake_broker(isolated_modules, call, key):
    real = FakeBroker()
    guard = G.install(real, "run-b")
    with pytest.raises(G.ProhibitedBrokerCall):
        getattr(guard, call)({"action": 1})
    c = G.counters_of(guard).as_dict()
    assert c["PROHIBITED_ORDER_API_ATTEMPTS"] == 1 and (key is None or c[key] == 1)
    assert c["BROKER_MUTATION_REQUESTS_FORWARDED"] == 0 and real.reached == []
    assert c["PROHIBITED_CALL_SITES"][0]["site"].startswith("tests/test_mt5_readonly_guard.py:")


def test_alternate_references_are_replaced_and_coverage_is_complete(isolated_modules, monkeypatch):
    real = FakeBroker()
    holder = types.ModuleType("alt_holder")
    holder.mt5 = real                                   # like `import MetaTrader5 as mt5` in another module
    monkeypatch.setitem(sys.modules, "alt_holder", holder)
    monkeypatch.setitem(sys.modules, "MetaTrader5", real)
    guard = G.install(real, "run-c")
    assert sys.modules["MetaTrader5"] is guard and holder.mt5 is guard
    assert G.remaining_references(real) == [] and G.counters_of(guard).coverage_status == "COMPLETE"
    with pytest.raises(G.ProhibitedBrokerCall):
        holder.mt5.order_send({})
    assert real.reached == []


def test_unreplaceable_reference_reports_incomplete_coverage(isolated_modules, monkeypatch):
    real = FakeBroker()

    class Frozen(types.ModuleType):
        def __setattr__(self, name, value):
            if name == "mt5" and "mt5" in self.__dict__:
                raise AttributeError("read-only")
            super().__setattr__(name, value)
    frozen = Frozen("frozen_holder")
    frozen.mt5 = real
    monkeypatch.setitem(sys.modules, "frozen_holder", frozen)
    guard = G.install(real, "run-d")
    assert G.counters_of(guard).coverage_status == "INCOMPLETE"


def test_counters_are_partitioned_per_run(isolated_modules):
    real = FakeBroker()
    first = G.install(real, "run-1")
    first.symbol_info("X")
    second = G.install(real, "run-2")
    assert G.counters_of(second).as_dict()["MT5_READ_CALLS"] == 0
    assert G.counters_of(second).run_id == "run-2" and G.counters_of(first).read_calls == 1


def test_guard_is_immutable(isolated_modules):
    guard = G.install(FakeBroker(), "run-e")
    with pytest.raises(AttributeError):
        guard.order_send = lambda *a: None


def test_broker_history_window_states(isolated_modules):
    start, end = dt.datetime(2026, 10, 13, 7, tzinfo=UTC), dt.datetime(2026, 10, 13, 8, tzinfo=UTC)
    clean = G.install(FakeBroker(), "h1")
    assert G.broker_history_window(clean, start, end)["status"] == "BROKER_HISTORY_CLEAN"
    rec = types.SimpleNamespace(ticket=123456789, magic=777001, time_setup=100, time=100)
    busy = G.install(FakeBroker(orders=[rec], deals=[rec]), "h2")
    out = G.broker_history_window(busy, start, end)
    assert out["status"] == "BROKER_HISTORY_AMBIGUOUS" and out["order_records"][0]["ticket_suffix"] == "6789"
    outside = G.broker_history_window(busy, start, end, to_utc=lambda epoch: start - dt.timedelta(hours=3))
    assert outside["status"] == "BROKER_HISTORY_CLEAN"                 # filtered by the record's own time

    class Broken(FakeBroker):
        def history_orders_get(self, *a):
            raise OSError("terminal gone")
    assert G.broker_history_window(G.install(Broken(), "h3"), start, end)["status"] == "BROKER_HISTORY_UNAVAILABLE"


def test_runner_installs_the_guard_for_every_mt5_mode_before_any_call():
    src = (ROOT / "scripts" / "host" / "live_candles_smoke.py").read_text(encoding="utf-8")
    block = src[src.index("mt5 = import_mt5()"):]
    assert block.index("mt5 = install_mt5_guard(mt5, run_id)") < block.index("mt5_initialize(mt5")
    assert src.count("mt5 = import_mt5()") == 1                       # one shared MT5 branch for fx/crypto/lsmc
    assert "evidence = mt5_guard_evidence(mt5, journal, now, args.mode)" in src
    assert 'return 3' in src and "MT5_GUARD RUN_FAILED" in src


def test_execution_authority_and_identities_are_unchanged():
    scope = yaml.safe_load((ROOT / "config" / "demo_execution_s1.yaml").read_text(encoding="utf-8"))
    assert scope["enabled"] is False and scope["per_order_confirm_required"] is True
    registry = yaml.safe_load((ROOT / "strategies" / "registry.yaml").read_text(encoding="utf-8"))["strategies"]
    assert all(v.get("live_authorized") is not True for v in registry.values())
    assert all(v.get("demo_authorized") is not True for v in registry.values())
    from v1_tickets.authority import logic_identity
    from v1_tickets.lsmc_logic_gate import engine_sha256
    assert logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2")["digest"].startswith("d7a8ebe5")
    assert logic_identity("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0")["digest"].startswith("7a0946e4")
    assert engine_sha256().startswith("88dd9f1f")


def test_runner_writes_machine_readable_guard_evidence(isolated_modules, tmp_path):
    sys.path.insert(0, str(ROOT / "scripts" / "host"))
    import live_candles_smoke as smoke
    guard = G.install(FakeBroker(), "fx-20261013T070000Z-1")
    guard.symbol_info("EURUSD-VIP")
    started = dt.datetime(2026, 10, 13, 7, tzinfo=UTC)
    record = smoke.mt5_guard_evidence(guard, str(tmp_path), started, "fx")
    import json
    rows = [json.loads(line) for line in
            (tmp_path / "ticket_delivery" / "mt5_guard" / "2026-10-13.jsonl").read_text().splitlines()]
    assert rows[0]["RUN_ID"] == "fx-20261013T070000Z-1" and rows[0]["MT5_READ_CALLS"] >= 1
    assert rows[0]["PROHIBITED_ORDER_API_ATTEMPTS"] == 0 and rows[0]["GUARD_COVERAGE_STATUS"] == "COMPLETE"
    assert rows[0]["broker_history"]["status"] == "BROKER_HISTORY_CLEAN"
    assert record["summary_line"].startswith("MT5_GUARD RUN_ID=fx-20261013T070000Z-1 ")
