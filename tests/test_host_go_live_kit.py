"""AG V1 host go-live kit: every script path that can run without MT5 (MetaTrader5 is faked),
plus static checks on the PowerShell scripts and on the read-only / no-secret invariants."""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOST = ROOT / "scripts" / "host"
sys.path.insert(0, str(HOST))

import _host_common as hc  # noqa: E402
import capture_symbol_metadata as cap  # noqa: E402
import diagnose_mt5 as diag  # noqa: E402
import live_candles_smoke as smoke  # noqa: E402
import verify_objective as objective  # noqa: E402
from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars  # noqa: E402

from host_delivery import telegram_message as tg  # noqa: E402
from host_evidence import symbol_metadata as sm  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

UTC = dt.timezone.utc


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    for canonical in ("EURUSD", "GBPUSD"):                              # the VT Markets -VIP host captures
        _vip_record(canonical, str(tmp_path / "evidence"))
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "MT5_PASSWORD", "VTMARKETS_DEMO_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


def _vip_record(canonical, root, broker=None):
    fields = {f: 1 for f in sm.FIELDS}
    fields.update(digits=5, point=0.00001, currency_profit="USD")
    sm.write_record(sm.build_record(canonical, broker or f"{canonical}-VIP", fields, "VTMarkets-Demo", 3, "t",
                                    trade_mode="FULL"), root)


class FakeMT5(types.SimpleNamespace):
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self, init_ok=True, account=True, trade_mode=0, symbols=("USDJPY", "USDJPY.vip")):
        super().__init__(calls=[], init_ok=init_ok, _account=account, _mode=trade_mode, _symbols=symbols)

    def initialize(self, **kw):
        self.calls.append(("initialize", sorted(kw)))
        return self.init_ok

    def last_error(self):
        return (1, "Success") if self.init_ok else (-6, "Terminal: Authorization failed")

    def account_info(self):
        return types.SimpleNamespace(login=123456, server="VTMarkets-Demo", trade_mode=self._mode,
                                     balance=98765.43, equity=98765.43) if self._account else None

    def symbols_get(self, group=None):
        pat = re.compile(group.replace("*", ".*"))
        return [types.SimpleNamespace(name=n) for n in self._symbols if pat.fullmatch(n)]

    def symbol_info(self, name):
        if name not in self._symbols:
            return None
        return types.SimpleNamespace(name=name, digits=3, point=0.001, trade_tick_size=0.001, trade_tick_value=0.64,
                                     trade_contract_size=100000.0, volume_min=0.01, volume_step=0.01, volume_max=100.0,
                                     trade_stops_level=0, trade_freeze_level=0, spread=12, currency_profit="JPY")

    def symbol_select(self, name, enable):
        return name in self._symbols

    tick_offset_h = None                                                # None = the owner-rule offset now

    def symbol_info_tick(self, name):
        import time
        off = self.tick_offset_h if self.tick_offset_h is not None else sm.server_utc_offset_hours(
            dt.datetime.now(UTC))
        return types.SimpleNamespace(time=int(time.time()) + 3600 * off, bid=1.0, ask=1.0001)

    def shutdown(self):
        self.calls.append(("shutdown",))


# ------------------------------------------------------------------ 1 diagnose

def _appdata(tmp_path, entry=True, absolute=True):
    d = tmp_path / "appdata" / "Claude"
    (d / "logs").mkdir(parents=True)
    (d / "logs" / "mcp-server-mt5ReadOnly.log").write_text("x")
    script = str(tmp_path / "start_mt5_mcp.mjs") if absolute else "web/scripts/start_mt5_mcp.mjs"
    cfg = {"mcpServers": {"mt5ReadOnly": {"command": "node", "args": [script]}}} if entry else {"mcpServers": {}}
    (d / "claude_desktop_config.json").write_text(json.dumps(cfg))
    return str(tmp_path / "appdata")


def test_diagnose_all_ok_prints_no_balances(tmp_path, capsys):
    results = diag.run(FakeMT5(), "", _appdata(tmp_path))
    by = {r["check"]: r for r in results}
    assert by["initialize"]["ok"] and by["demo_account"]["ok"] and by["claude_desktop_mt5ReadOnly"]["ok"]
    assert "login=123456 server=VTMarkets-Demo trade_mode=0" == by["account_info"]["detail"]
    assert "98765" not in json.dumps(results)


@pytest.mark.parametrize("mt5,key", [
    (None, "PACKAGE_MISSING"), (FakeMT5(init_ok=False), "TERMINAL_NOT_RUNNING"),
    (FakeMT5(account=False), "NOT_LOGGED_IN"), (FakeMT5(trade_mode=2), "NOT_DEMO"),
])
def test_diagnose_failures_print_exact_fixes(tmp_path, mt5, key):
    fixes = [r["fix"] for r in diag.run(mt5, "", _appdata(tmp_path)) if not r["ok"]]
    assert diag.FIXES[key] in fixes


def test_diagnose_mcp_checklist_and_terminal_path(tmp_path):
    fixes = [r["fix"] for r in diag.check_claude_desktop(_appdata(tmp_path, absolute=False))]
    assert diag.FIXES["MCP_CONFIG"] in fixes
    assert diag.check_terminal_path(str(tmp_path / "nope.exe"))["fix"] == diag.FIXES["TERMINAL_PATH"]


def test_initialize_passes_credentials_but_never_prints_password(monkeypatch):
    monkeypatch.setenv("VTMARKETS_DEMO_LOGIN", "123456")
    monkeypatch.setenv("VTMARKETS_DEMO_PASSWORD", "s3cretPass!")
    monkeypatch.setenv("VTMARKETS_DEMO_SERVER", "VTMarkets-Demo")
    fake = FakeMT5()
    ok, detail = hc.mt5_initialize(fake)
    assert ok and fake.calls[0] == ("initialize", ["login", "password", "server", "timeout"])
    assert "s3cretPass!" not in detail and hc.redact("pw=s3cretPass!") == "pw=***"


# ------------------------------------------------------------------ 2 capture metadata

def test_capture_without_exact_name_only_lists_candidates(tmp_path, capsys):
    rc = cap.main(["--symbol", "USDJPY"], mt5=FakeMT5(), offset_fn=lambda s: 2, root=str(tmp_path / "evidence"))
    assert rc == 2 and "USDJPY.vip" in capsys.readouterr().out
    assert not glob.glob(str(tmp_path / "evidence" / "**" / "USDJPY*.json"), recursive=True)


def test_capture_writes_verified_record_and_promotes_to_code_ready(tmp_path, monkeypatch):
    from large_smc_watch import contract as C
    from v1_tickets import fx
    assert fx.metadata_status("USDJPY") == "FIXTURE_ONLY" and C.resolve_point("USDJPY")[1] == "MISSING"
    rc = cap.main(["--symbol", "USDJPY", "--broker-symbol", "USDJPY.vip"], mt5=FakeMT5(),
                  offset_fn=lambda s: 2, root=str(tmp_path / "evidence"))
    assert rc == 0
    rec = sm.load_record("USDJPY")
    assert rec["broker_symbol"] == "USDJPY.vip" and rec["server_utc_offset_hours"] == 2 and len(rec["sha256"]) == 64
    assert set(sm.FIELDS) <= set(rec["fields"]) and rec["captured_at_utc"]
    assert fx.metadata_status("USDJPY") == "HOST_CAPTURED" and fx.broker_symbol("USDJPY") == "USDJPY.vip"
    assert C.resolve_point("USDJPY") == (0.001, "HOST_CAPTURED")
    assert fx.metadata_status("XAUUSD") == "FIXTURE_ONLY"


def test_tampered_or_mismatched_record_fails_closed(tmp_path):
    cap.main(["--symbol", "USDJPY", "--broker-symbol", "USDJPY"], mt5=FakeMT5(), offset_fn=lambda s: 3,
             root=str(tmp_path / "evidence"))
    path = sm.evidence_path("USDJPY", str(tmp_path / "evidence"))
    rec = json.loads(open(path).read())
    rec["fields"]["point"] = 0.01
    Path(path).write_text(json.dumps(rec))
    from v1_tickets import fx
    assert sm.load_record("USDJPY") is None and fx.metadata_status("USDJPY") == "FIXTURE_ONLY"


def test_capture_refuses_unknown_symbol_and_missing_offset(tmp_path):
    with pytest.raises(SystemExit):
        cap.capture(FakeMT5(), "USDJPY", "USDJPYX", lambda s: 0, "t")
    with pytest.raises(SystemExit):
        cap.capture(FakeMT5(), "USDJPY", "USDJPY", lambda s: (_ for _ in ()).throw(RuntimeError("NO_WEEKEND_GAP")), "t")


# ------------------------------------------------------------------ 3 smoke / scheduled runner

def _m15_day(now):
    out = []
    start = dt.datetime.combine(now.date(), dt.time(0, 0), tzinfo=UTC)
    for i in range(int((now - start).total_seconds() // 900)):
        t = start + dt.timedelta(minutes=15 * i)
        o, h, l, c = 1.1000, 1.1030, 1.0970, 1.1005
        if i == 0:
            h, l = 1.1050, 1.0950
        if t == start + dt.timedelta(hours=7, minutes=15):
            o, h, l, c = 1.1005, 1.1060, 1.1000, 1.1048
        out.append(Candle(t, o, h, l, c))
    return out


def fake_fetch(now=NOW):
    data = {"D1": d1_bars(), "H1": h1_bars(), "M5": m5_bars(), "M15": _m15_day(now)}

    def fetch(symbol, tf, count):
        if symbol not in ("EURUSD-VIP", "GBPUSD-VIP"):                  # only the -VIP broker symbols exist
            raise sm.HostDataError(sm.SYMBOL_NOT_FOUND, repr(symbol))
        return data[tf][-count:]
    return fetch


def test_smoke_prints_states_and_archives_only(tmp_path):
    lines = smoke.run_smoke(fake_fetch(), NOW, str(tmp_path / "journal"))
    text = "\n".join(lines)
    assert "BARS EURUSD (EURUSD-VIP) status=FRESH" in text
    # The fixture's box-direction SIGNAL carries no engine signal time: STALE-FIX-1 fails it closed
    # instead of borrowing the first trade-session bar.
    assert "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=DATA_ERROR reason=SIGNAL_TIME_UNAVAILABLE" in text
    assert "LSMC EURUSD data=FRESH state=REJECTED" in text and "LSMC GBPUSD" in text
    # Objective symbols are never silently omitted: unavailable metadata/data is visible.
    assert "FX USDJPY" in text and "decision=DATA_ERROR" in text
    assert glob.glob(str(tmp_path / "journal" / "ticket_delivery" / "archive" / "**" / "*.json"), recursive=True)


def test_smoke_includes_usdjpy_once_metadata_captured(tmp_path):
    cap.main(["--symbol", "USDJPY", "--broker-symbol", "USDJPY"], mt5=FakeMT5(), offset_fn=lambda s: 2,
             root=str(tmp_path / "evidence"))
    lines = smoke.run_smoke(fake_fetch(), NOW, str(tmp_path / "journal"))
    assert any(ln.startswith("FX USDJPY") for ln in lines)          # attempted (fake has no USDJPY data)


def test_fx_never_falls_back_to_plain_symbols(tmp_path):
    for canonical in ("EURUSD", "GBPUSD"):
        os.remove(sm.evidence_path(canonical))
    _vip_record("EURUSD", sm.evidence_root(), broker="EURUSD")             # a plain-symbol capture is not accepted
    from v1_tickets import fx
    assert fx.metadata_status("EURUSD") == "FIXTURE_ONLY"
    with pytest.raises(sm.HostDataError) as exc:
        fx.broker_symbol("EURUSD")
    assert exc.value.code == "METADATA_MISSING" and "EURUSD-VIP" in str(exc.value)
    fetched = []
    lines = smoke.run_fx(lambda s, tf, n: fetched.append(s) or [], NOW, str(tmp_path / "j"), gated=False)
    assert not fetched and all("DATA_ERROR reason=METADATA_MISSING" in ln for ln in lines if ln.startswith("FX EUR"))


def test_fx_mode_ready_requires_fresh_signal_and_spread(tmp_path):
    lines = smoke.run_fx(fake_fetch(), NOW, str(tmp_path / "j"), gated=False, quote=lambda b: (1.1000, 1.1001))
    assert lines and not any("decision=READY" in ln and "spread_check=PASS" not in ln for ln in lines)
    no_quote = smoke.run_fx(fake_fetch(), NOW, str(tmp_path / "j2"), gated=False)
    assert not any("decision=READY" in ln for ln in no_quote)


def test_fx_runtime_projects_only_eligible_ready_to_idempotent_paper_ledger(tmp_path, monkeypatch):
    now = dt.datetime(2026, 1, 6, 8, 0, tzinfo=UTC)
    monkeypatch.setattr(smoke, "fx_symbols", lambda: ["EURUSD"])

    def ready(symbol, cycle, m15, at, data_close=None, spread=None):
        return {
            "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
            "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1",
            "symbol": symbol, "cycle": cycle, "session_date": at.date().isoformat(),
            "signal_id": f"{cycle}-signal", "signal_close_utc": (at - dt.timedelta(minutes=5)).isoformat(),
            "direction": "LONG", "entry_order_type": "MARKET", "entry": 1.1, "stop_loss": 1.09,
            "risk_distance": 0.01,
            "targets": [{"leg": 1, "volume_pct": 0.75, "type": "BOUNDARY", "price": 1.11},
                        {"leg": 2, "volume_pct": 0.25, "type": "5R", "price": 1.15}],
            "evaluated_at": at.isoformat(), "metadata_status": "HOST_CAPTURED", "spread_check": "PASS",
            "decision": "READY", "reason_code": "SIGNAL", "data_source": "MT5_VT_MARKETS_DEMO",
            "delivery_mode": "ARCHIVE_ONLY",
        }

    monkeypatch.setattr(smoke, "fx_ticket_for", ready)
    journal = str(tmp_path / "journal")
    first = smoke.run_fx(lambda *args: [], now, journal, gated=False, notify=False,
                         quote=lambda b: (1.0, 1.0001))
    second = smoke.run_fx(lambda *args: [], now, journal, gated=False, notify=False,
                          quote=lambda b: (1.0, 1.0001))
    assert sum("paper=OPENED" in line for line in first) == 2
    assert sum("paper=ALREADY_RECORDED" in line for line in second) == 2
    papers = glob.glob(str(tmp_path / "journal" / "paper_trades" / "**" / "*.json"), recursive=True)
    assert len(papers) == 2
    assert all(json.loads(Path(path).read_text())["label"] == "PAPER TRADE ONLY -- NO BROKER ORDER" for path in papers)


def test_fx_data_acquisition_errors_are_archived_and_never_paper_traded(tmp_path):
    def broken_fetch(symbol, timeframe, count):
        raise sm.HostDataError(sm.INCOMPLETE_CANDLES, f"{symbol}/{timeframe} 0<{count}")

    journal = str(tmp_path / "journal")
    lines = smoke.run_fx(broken_fetch, NOW, journal, gated=False)
    assert lines and all("decision=DATA_ERROR" in line and "ARCHIVED" in line for line in lines)
    paths = glob.glob(str(tmp_path / "journal" / "ticket_delivery" / "archive" / "**" / "*.json"), recursive=True)
    assert len(paths) == 8                         # complete 4-symbol objective x 2 cycles
    assert not glob.glob(str(tmp_path / "journal" / "paper_trades" / "**" / "*.json"), recursive=True)
    for path in paths:
        record = json.loads(Path(path).read_text())
        assert record["cycle_state"] == "DATA_ERROR"
        assert record["payload"]["reason_code"] in (sm.INCOMPLETE_CANDLES, sm.METADATA_MISSING)
        assert "entry" not in record["payload"]


def test_runtime_requires_demo_account():
    assert hc.require_demo_account(FakeMT5())[0]
    ok, reason = hc.require_demo_account(FakeMT5(trade_mode=2))
    assert not ok and reason == "NON_DEMO_ACCOUNT_BLOCKED"
    assert hc.require_demo_account(FakeMT5(account=False)) == (False, "ACCOUNT_INFO_UNAVAILABLE")


def test_fx_mode_is_window_bounded_and_idempotent(tmp_path):
    j = str(tmp_path / "journal")
    assert smoke.run_fx(fake_fetch(), dt.datetime(2026, 1, 6, 5, 0, tzinfo=UTC), j, gated=True) == []
    first = smoke.run_fx(fake_fetch(), NOW, j, gated=True)
    second = smoke.run_fx(fake_fetch(), NOW, j, gated=True)
    assert any("ARCHIVED" in ln for ln in first) and not any("ARCHIVED" in ln for ln in second)


def test_market_closed_and_stale_classification():
    sat = dt.datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    assert smoke.classify("EURUSD", m5_bars(), sat) == "MARKET_CLOSED"
    assert smoke.classify("BTCUSDT", m5_bars(), sat) == "STALE"
    assert smoke.classify("EURUSD", m5_bars(), NOW) == "FRESH"
    assert smoke.classify("EURUSD", [], NOW) == "NO_DATA"


def test_cycle_windows_follow_frozen_gmt_config():
    w = smoke.cycle_windows(NOW)
    assert (w["ASIAN_LONDON"]["trade"][0].hour, w["ASIAN_LONDON"]["trade"][1].hour) == (7, 11)
    assert (w["LONDON_NEWYORK"]["trade"][0].hour, w["LONDON_NEWYORK"]["trade"][1].hour) == (12, 15)


def test_crypto_mode_window_and_idempotence(tmp_path):
    from test_v1_tickets import IN_WINDOW, _FakeFeed
    j = str(tmp_path / "journal")
    first = smoke.run_crypto(IN_WINDOW, j, _FakeFeed())
    assert any("source=BYBIT_LINEAR_PERP ARCHIVED" in ln for ln in first)
    assert not any("ARCHIVED" in ln for ln in smoke.run_crypto(IN_WINDOW, j, _FakeFeed()))
    assert all("OUTSIDE_WINDOW" in ln for ln in smoke.run_crypto(IN_WINDOW + dt.timedelta(hours=3), j, _FakeFeed()))


def test_crypto_main_outside_window_takes_no_runner_or_mt5_lock_and_never_imports_mt5(monkeypatch):
    now = dt.datetime(2026, 11, 2, 13, 59, tzinfo=UTC)  # 08:59 EST, before the V3 weekday window
    monkeypatch.setattr(smoke, "utcnow", lambda: now)
    monkeypatch.setattr(hc, "utcnow", lambda: now)

    def forbidden(*args, **kwargs):
        pytest.fail("outside-window crypto run must not acquire a lock or touch MT5")

    monkeypatch.setattr(smoke, "single_instance", forbidden)
    monkeypatch.setattr(smoke, "mt5_access_lock", forbidden)
    monkeypatch.setattr(smoke, "import_mt5", forbidden)
    monkeypatch.setattr(smoke, "mt5_initialize", forbidden)

    assert smoke.main(["--mode", "crypto"]) == 0
    log = (Path(hc.LOG_DIR) / "ag_v1_crypto.log").read_text(encoding="utf-8").splitlines()
    assert log == [f"{now.isoformat()} CRYPTO OUTSIDE_WINDOW (BEFORE_WINDOW)"]


def test_crypto_main_inside_window_keeps_mt5_runner_path(monkeypatch):
    from contextlib import contextmanager

    now = dt.datetime(2026, 11, 2, 14, 0, tzinfo=UTC)  # 09:00 EST, inclusive V3 weekday start
    calls, logged = [], []
    monkeypatch.setattr(smoke, "utcnow", lambda: now)

    @contextmanager
    def single_lock(name):
        calls.append(("single_instance", name))
        yield

    @contextmanager
    def mt5_lock():
        calls.append(("mt5_access_lock",))
        yield

    mt5 = types.SimpleNamespace(shutdown=lambda: calls.append(("shutdown",)))
    monkeypatch.setattr(smoke, "single_instance", single_lock)
    monkeypatch.setattr(smoke, "mt5_access_lock", mt5_lock)
    monkeypatch.setattr(smoke, "import_mt5", lambda: calls.append(("import_mt5",)) or mt5)
    monkeypatch.setattr(smoke, "mt5_initialize", lambda *_: calls.append(("initialize",)) or (True, "ok"))
    monkeypatch.setattr(smoke, "require_demo_account", lambda *_: calls.append(("demo",)) or (True, "ok"))
    monkeypatch.setattr(smoke, "host_fetch", lambda _: lambda *_: [])
    monkeypatch.setattr(smoke, "host_quote", lambda _: lambda *_: None)

    def run_crypto(run_now, journal, feed, config=None, **kwargs):
        calls.append(("run_crypto", run_now, config["version"], type(feed).__name__))
        return ["CRYPTO IN_WINDOW"]

    monkeypatch.setattr(smoke, "run_crypto", run_crypto)
    monkeypatch.setattr(smoke, "log_line", lambda name, message: logged.append((name, message)))

    assert smoke.main(["--mode", "crypto"]) == 0
    assert [call[0] for call in calls] == ["single_instance", "import_mt5", "mt5_access_lock",
                                          "initialize", "demo", "run_crypto", "shutdown"]
    assert calls[-2][1:] == (now, 3, "Mt5CryptoFeed")
    assert logged == [("ag_v1_crypto", "CRYPTO IN_WINDOW")]


def test_single_instance_lock():
    with hc.single_instance("t"):
        with pytest.raises(hc.AlreadyRunning):
            with hc.single_instance("t"):
                pass
    with hc.single_instance("t"):
        pass


def test_single_instance_breaks_lock_of_dead_process(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "LOG_DIR", str(tmp_path))
    (tmp_path / "d.lock").write_text("2147480000")                    # no such pid: killed run
    with hc.single_instance("d"):
        pass
    (tmp_path / "d.lock").write_text(str(os.getpid()))                 # live owner: still held
    with pytest.raises(hc.AlreadyRunning):
        with hc.single_instance("d"):
            pass


def test_call_with_timeout_bounds_a_stuck_call_and_passes_results():
    import threading
    assert hc.call_with_timeout(lambda a, b=0: a + b, 1, b=2, limit_s=1) == 3
    with pytest.raises(ZeroDivisionError):
        hc.call_with_timeout(lambda: 1 / 0, limit_s=1)
    gate = threading.Event()
    with pytest.raises(hc.CallTimeout):
        hc.call_with_timeout(gate.wait, limit_s=0.1)
    gate.set()


def test_initialize_timeout_fails_closed(monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(hc, "MT5_INIT_TIMEOUT_S", -1.9)          # thread bound = 0.1 s
    fake = types.SimpleNamespace(initialize=lambda **kw: gate.wait(), last_error=lambda: (0, ""))
    ok, detail = hc.mt5_initialize(fake)
    gate.set()
    assert not ok and detail.startswith("INIT_TIMEOUT")


def test_run_watchdog_logs_timeout_and_releases_lock(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(hc, "LOG_DIR", str(tmp_path))
    exited = threading.Event()
    with hc.single_instance("wd"):
        hc.start_run_watchdog("wd", timeout_s=0.05, _exit=lambda rc: exited.set())
        assert exited.wait(2)
        assert not (tmp_path / "wd.lock").exists()
    assert "TIMEOUT run exceeded" in (tmp_path / "wd.log").read_text()


def test_mt5_access_lock_is_exclusive_and_reports_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "MT5_LOCK_DIR", str(tmp_path))
    with hc.mt5_access_lock(wait_s=0):
        with pytest.raises(hc.Mt5Busy):
            with hc.mt5_access_lock(wait_s=0.2, poll_s=0.05):
                pass
    with hc.mt5_access_lock(wait_s=0):
        pass


def test_mt5_access_lock_is_host_wide_not_checkout_relative():
    """Two checkouts share one MT5 terminal, so the lock must live outside every checkout."""
    root = os.path.normcase(os.path.abspath(hc.REPO_ROOT))
    lock_dir = os.path.normcase(os.path.abspath(hc.MT5_LOCK_DIR))
    try:
        inside = os.path.commonpath([lock_dir, root]) == root
    except ValueError:      # different drives
        inside = False
    assert not inside


@pytest.mark.parametrize("now,open_", [
    (dt.datetime(2026, 10, 3, 20, 45, tzinfo=UTC), True),     # Sat 20:45 UTC (start inclusive)
    (dt.datetime(2026, 10, 4, 23, 14, tzinfo=UTC), True),     # Sun 23:14 UTC
    (dt.datetime(2026, 10, 4, 23, 15, tzinfo=UTC), False),    # end exclusive
    (dt.datetime(2026, 10, 3, 20, 44, tzinfo=UTC), False),
    (dt.datetime(2026, 10, 2, 21, 0, tzinfo=UTC), False),     # Friday
])
def test_lsmc_weekend_gate_is_sat_sun_2045_2315_utc(now, open_):
    assert smoke.lsmc_weekend_open(now) is open_


def test_lsmc_weekend_mode_watches_btc_eth_only(tmp_path):
    fetched = []

    class Feed:
        symbols = {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"}

        def fetch_bundle(self, symbol, req):
            fetched.append(symbol)
            raise RuntimeError("no data in test")

    lines = smoke.run_lsmc(lambda s, tf, n: fetched.append(s) or [], dt.datetime(2026, 10, 3, 21, 0, tzinfo=UTC),
                           str(tmp_path), crypto_feed=Feed(), notify=False, fx=False, window="WEEKEND")
    # LSMC 1.1.0 is VT-only: it watches BTCUSD/ETHUSD, fetched through the feed keys mapped to them.
    assert fetched == ["BTCUSDT", "ETHUSDT"] and all(ln.startswith(("LSMC BTCUSD ", "LSMC ETHUSD ")) for ln in lines)


def test_lsmc_crypto_uses_mt5_venue_never_public_feed():
    from v1_tickets.crypto import Mt5CryptoFeed
    mt5_cfg = {"venue": {"kind": "MT5", "symbols": {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"},
                         "source_id": "MT5_VT_MARKETS_DEMO"}}
    feed = smoke.lsmc_crypto_feed(mt5_cfg, lambda s, tf, n: [])
    assert isinstance(feed, Mt5CryptoFeed) and feed.symbols == {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"}
    assert smoke.lsmc_crypto_feed({"venue": {"kind": "PUBLIC_PERP"}}, lambda s, tf, n: []) is None
    assert "FallbackPublicCryptoFeed()" not in (HOST / "live_candles_smoke.py").read_text().split("def main")[1]


def _load_repo_stub():
    import importlib.util
    spec = importlib.util.spec_from_file_location("MetaTrader5", ROOT / "MetaTrader5.py")
    stub = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stub)
    return stub


def _stub_first_path(*extra):
    rest = [p for p in sys.path if "site-packages" not in p and Path(p or ".").resolve() != ROOT]
    return [str(ROOT), *map(str, extra), *rest]


def test_import_mt5_never_returns_the_repo_stub():
    mt5 = hc.import_mt5()               # Linux CI: None; Windows host: the installed package
    assert mt5 is None or (not hc._is_repo_module(mt5) and "MT5StubOperationAttempted" not in vars(mt5))


def test_import_mt5_skips_stub_on_path_and_resolves_installed_package(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    (site / "MetaTrader5").mkdir(parents=True)
    (site / "MetaTrader5" / "__init__.py").write_text("def initialize(*a, **k):\n    return True\n")
    stub = _load_repo_stub()
    monkeypatch.setitem(sys.modules, "MetaTrader5", stub)
    path = _stub_first_path(site)
    monkeypatch.setattr(sys, "path", path[:])
    mt5 = hc.import_mt5()
    assert mt5 is not None and Path(mt5.__file__).resolve().parent.parent == site.resolve()
    assert sys.modules["MetaTrader5"] is stub and sys.path == path      # both restored


def test_import_mt5_rejects_stub_when_no_package_is_installed(monkeypatch):
    stub = _load_repo_stub()
    monkeypatch.setitem(sys.modules, "MetaTrader5", stub)
    monkeypatch.setattr(sys, "path", _stub_first_path())
    assert hc.import_mt5() is None


def test_import_mt5_real_package_wins_over_stub_first_on_path(monkeypatch):
    from importlib.machinery import PathFinder
    real = PathFinder.find_spec("MetaTrader5", [p for p in sys.path if Path(p or ".").resolve() != ROOT])
    if real is None or "site-packages" not in (real.origin or ""):
        pytest.skip("real MetaTrader5 package not installed on this host")
    monkeypatch.setitem(sys.modules, "MetaTrader5", _load_repo_stub())
    monkeypatch.setattr(sys, "path", [str(ROOT), *sys.path])
    mt5 = hc.import_mt5()
    assert mt5 is not None and "site-packages" in Path(mt5.__file__).parts


# ------------------------------------------------------------------ 5 telegram

class _Sess:
    def __init__(self, status=200, ok=True, boom=False):
        self.status, self.ok, self.boom, self.posts = status, ok, boom, []

    def post(self, url, data=None, timeout=None):
        if self.boom:
            raise ConnectionError(f"failed to reach {url}")
        self.posts.append((url, data))
        return types.SimpleNamespace(status_code=self.status, json=lambda: {"ok": self.ok})


def test_telegram_default_archive_only_and_scoped_override(tmp_path):
    assert tg.load_mode(str(tmp_path))["mode"] == "ARCHIVE_ONLY"
    assert not tg.should_send("TICKET", "READY", str(tmp_path))
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    r = str(tmp_path)
    assert tg.should_send("TICKET", "READY", r) and tg.should_send("LSMC", "OPPORTUNITY", r)
    for kind, v in (("TICKET", "NO_TRADE"), ("TICKET", "DATA_ERROR"), ("LSMC", "WATCH"), ("LSMC", "INFO")):
        assert not tg.should_send(kind, v, r)


def test_local_delivery_scope_can_only_narrow_tracked_policy(tmp_path):
    import shutil
    from telegram_delivery.adapter import Config
    from telegram_delivery.scope_policy import resolve

    (tmp_path / "config").mkdir()
    shutil.copy2(ROOT / "config/ticket_delivery.yaml", tmp_path / "config/ticket_delivery.yaml")
    local = tmp_path / "config/local"
    local.mkdir()
    override = local / "delivery_override.yaml"
    override.write_text("mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY]\n", encoding="utf-8")
    resolved = resolve(tmp_path, sender="legacy")
    assert resolved["effective"] == ("TICKET_READY",)
    assert resolved["error"] is None
    assert tg.should_send("TICKET", "READY", str(tmp_path))
    assert not tg.should_send("LSMC", "OPPORTUNITY", str(tmp_path))

    override.write_text("mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY]\n", encoding="utf-8")
    (local / "canonical_ticket_delivery.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nimmediate_send_scopes: [LSMC_OPPORTUNITY]\n", encoding="utf-8")
    legacy = resolve(tmp_path, sender="legacy")
    canonical = Config.from_env(str(tmp_path))
    assert legacy["effective"] == ("TICKET_READY",) and legacy["error"] is None
    assert canonical.immediate_scopes == frozenset({"LSMC_OPPORTUNITY"})
    assert canonical.scope_error is None

    (local / "canonical_ticket_delivery.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nimmediate_send_scopes: [WATCH_READY]\n", encoding="utf-8")
    canonical_widening = Config.from_env(str(tmp_path))
    assert canonical_widening.immediate_scopes == frozenset()
    assert canonical_widening.scope_error == "SCOPE_WIDENING_REJECTED"
    assert resolve(tmp_path, sender="legacy")["effective"] == ("TICKET_READY",)

    override.write_text("mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, MANUAL_TICKET_READY]\n",
                        encoding="utf-8")
    rejected = resolve(tmp_path, sender="legacy")
    assert rejected["effective"] == ()
    assert rejected["error"] == "SCOPE_WIDENING_REJECTED"
    assert tg.load_mode(str(tmp_path))["error"] == "SCOPE_WIDENING_REJECTED"
    assert not tg.should_send("TICKET", "READY", str(tmp_path))
    (local / "canonical_ticket_delivery.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nimmediate_send_scopes: [LSMC_OPPORTUNITY]\n", encoding="utf-8")
    assert Config.from_env(str(tmp_path)).immediate_scopes == frozenset({"LSMC_OPPORTUNITY"})


def test_objective_reports_both_sender_scopes_independently(monkeypatch):
    from telegram_delivery.adapter import Config
    from telegram_delivery.scope_policy import resolve

    def distinct(root=".", sender="legacy"):
        if sender == "legacy" and Path(root) == Path(objective.REPO_ROOT):
            return {"tracked": ("TICKET_READY", "LSMC_OPPORTUNITY"), "disabled": (),
                    "effective": ("TICKET_READY",), "error": None}
        return resolve(root, sender=sender)
    monkeypatch.setattr(objective, "resolve_immediate_scope", distinct)
    monkeypatch.setattr(Config, "from_env", classmethod(
        lambda cls, root=".": cls(immediate_scopes=frozenset({"LSMC_OPPORTUNITY"}))))
    report = objective.verify()
    row = next(item for item in report["checks"] if item["check"] == "telegram_report_scope")
    assert row["status"] == "PASS"
    assert "legacy effective=['TICKET_READY']" in row["detail"]
    assert "canonical effective=['LSMC_OPPORTUNITY']" in row["detail"]


def test_objective_fails_when_legacy_override_widens_policy(monkeypatch):
    from telegram_delivery.scope_policy import resolve

    def widened_legacy(root=".", sender="legacy"):
        if sender == "legacy":
            return {"tracked": ("TICKET_READY", "LSMC_OPPORTUNITY"), "disabled": (),
                    "effective": (), "error": "SCOPE_WIDENING_REJECTED"}
        return resolve(root, sender=sender)
    monkeypatch.setattr(objective, "resolve_immediate_scope", widened_legacy)
    report = objective.verify()
    row = next(item for item in report["checks"] if item["check"] == "telegram_report_scope")
    assert row["status"] == "FAIL"
    assert "legacy effective=[] error=SCOPE_WIDENING_REJECTED" in row["detail"]


def test_objective_fails_when_canonical_effective_scope_exceeds_policy(monkeypatch):
    from telegram_delivery.adapter import Config

    monkeypatch.setattr(Config, "from_env", classmethod(
        lambda cls, root=".": cls(immediate_scopes=frozenset({"WATCH_READY"}))))
    report = objective.verify()
    scope_check = next(row for row in report["checks"] if row["check"] == "telegram_report_scope")
    assert scope_check["status"] == "FAIL"
    assert "canonical effective=['WATCH_READY']" in scope_check["detail"]


def test_host_notification_router_reports_only_ready_proposals_and_opportunities(tmp_path, monkeypatch):
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    sent = []
    monkeypatch.setattr(tg, "send_message", sent.append)
    smoke._notify("TICKET", "READY", "rendered proposal", str(tmp_path))
    smoke._notify("TICKET", "NO_TRADE", "must not send", str(tmp_path))
    smoke._notify("LSMC", "OPPORTUNITY", "rendered opportunity", str(tmp_path))
    smoke._notify("LSMC", "WATCH", "must not send", str(tmp_path))
    assert sent == ["rendered proposal", "rendered opportunity"]


def test_telegram_send_is_message_only_and_never_leaks_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN-VALUE")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    s = _Sess()
    tg.send_message("hello", session=s)
    assert set(s.posts[0][1]) == {"chat_id", "text", "disable_web_page_preview"}   # no reply_markup / buttons
    with pytest.raises(tg.TelegramSendError) as exc:
        tg.send_message("x", session=_Sess(boom=True))
    assert "SECRET-TOKEN-VALUE" not in str(exc.value)
    with pytest.raises(tg.TelegramSendError):
        tg.send_message("x", session=_Sess(status=401, ok=False))


@pytest.mark.parametrize(("status", "expected"), [
    (401, "DELIVERY_FAILED"), (429, "RETRYABLE_REJECTED"), (500, "DELIVERY_UNCERTAIN"),
    (408, "DELIVERY_UNCERTAIN"),
])
def test_telegram_send_classifies_http_outcomes_conservatively(monkeypatch, status, expected):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN-VALUE")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    with pytest.raises(tg.TelegramSendError) as exc:
        tg.send_message("x", session=_Sess(status=status, ok=False))
    assert exc.value.delivery_state == expected
    assert "SECRET-TOKEN-VALUE" not in str(exc.value)


def test_telegram_validation_proposal_uses_real_renderer_and_is_unambiguous():
    ticket = tg.validation_proposal(dt.datetime(2026, 10, 1, 8, 0, tzinfo=UTC))
    text = tg.format_ticket(ticket)
    assert text.startswith("SIMULATED TELEGRAM DELIVERY VALIDATION -- NOT A MARKET SIGNAL")
    assert "decision=READY" in text and "ticket_id:" in text
    assert "entry: 1.1  stop: 1.099" in text
    assert "target leg 1" in text and "target leg 2" in text
    assert "spread_check: PASS" in text and "VALID UNTIL" in text


def test_scheduled_lsmc_rejection_never_reaches_transport(tmp_path, monkeypatch):
    local = tmp_path / "config" / "local"
    local.mkdir(parents=True)
    (local / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    sent = []
    monkeypatch.setattr(tg, "send_message", sent.append)
    journal = tmp_path / "journal"
    lines = smoke.run_lsmc(fake_fetch(), NOW, str(journal))
    assert any("state=REJECTED" in line for line in lines)
    assert sent == []
    assert list((journal / "ticket_delivery" / "archive").rglob("*.json"))


def test_scheduled_lsmc_run_reports_rendered_opportunity_exactly_once(tmp_path, monkeypatch):
    monkeypatch.setattr("large_smc_watch.watch.c11_causal_target", lambda *args: 1.12)
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    sent = []
    monkeypatch.setattr(tg, "send_message", sent.append)
    j = str(tmp_path / "journal")
    first = smoke.run_lsmc(fake_fetch(), NOW, j)
    after_first = list(sent)
    second = smoke.run_lsmc(fake_fetch(), NOW, j)                      # same state: no repeat alert
    assert any("LSMC EURUSD data=FRESH state=OPPORTUNITY" in ln for ln in first)
    assert all("alerts=[]" in ln for ln in second if "alerts=" in ln)
    assert sent == after_first and len(after_first) == 2                # EURUSD + GBPUSD, transition only
    assert all(m.startswith("LARGE-SMC ALERT -- INFORMATIONAL -- NOT A BROKER ORDER") for m in after_first)
    assert "EURUSD OPPORTUNITY (OPPORTUNITY)" in after_first[0] and "liquidity target:" in after_first[0]
    assert "stop (C10):" in after_first[0] and "expires_at:" in after_first[0]


def test_scheduled_fx_run_reports_ready_proposals_and_nothing_else(tmp_path, monkeypatch):
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    sent = []
    monkeypatch.setattr(tg, "send_message", sent.append)
    j = str(tmp_path / "journal")

    archived = smoke.run_fx(fake_fetch(), NOW, j, gated=False)        # DATA_ERROR only (two causes)
    assert any("decision=DATA_ERROR reason=SIGNAL_TIME_UNAVAILABLE" in ln for ln in archived)
    assert any("decision=DATA_ERROR reason=" in ln and "SIGNAL_TIME_UNAVAILABLE" not in ln
               for ln in archived)                                     # acquisition failure, distinct cause
    assert all("ARCHIVED" in ln for ln in archived) and sent == []     # archived, never reported

    ready = dict(tg.validation_proposal(NOW), strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
                 label="INFORMATIONAL TICKET -- NOT A BROKER ORDER", reason_code="SETUP_CONFIRMED",
                 metadata_status="HOST_CAPTURED", data_source="MT5_VT_MARKETS_DEMO",
                 evaluated_at=NOW.isoformat())
    monkeypatch.setattr(smoke, "fx_ticket_for", lambda symbol, cycle, *a, **k: dict(ready, symbol=symbol, cycle=cycle))
    first = smoke.run_fx(fake_fetch(), NOW, j, gated=False)
    after_first = list(sent)
    smoke.run_fx(fake_fetch(), NOW, j, gated=False)                   # replayed cycle: nothing re-sent
    assert any("decision=READY" in ln for ln in first) and sent == after_first
    assert [m.splitlines()[1] for m in after_first] == [
        "EURUSD LONG (ASIAN_LONDON)", "GBPUSD LONG (ASIAN_LONDON)",
        "EURUSD LONG (LONDON_NEWYORK)", "GBPUSD LONG (LONDON_NEWYORK)"]
    for message in after_first:
        assert "decision=NOT_READY" in message and "ticket_id:" in message and "VALID UNTIL" in message
        assert "logic_status: NOT_VERIFIED" in message and "EDGE_VERIFIED=FALSE" in message
        assert "entry:" in message and "target leg 1" in message and "NOT A BROKER ORDER" in message


def test_scheduled_telegram_send_failure_never_breaks_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr("large_smc_watch.watch.c11_causal_target", lambda *args: 1.12)
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(hc, "LOG_DIR", str(tmp_path / "logs"))

    def boom(_text):
        raise tg.TelegramSendError("send failed (ConnectionError)")

    monkeypatch.setattr(tg, "send_message", boom)
    lines = smoke.run_lsmc(fake_fetch(), NOW, str(tmp_path / "journal"))
    assert any("state=OPPORTUNITY" in ln for ln in lines)              # archive/watch path unaffected
    assert "TELEGRAM_SEND_DELIVERY_UNCERTAIN" in (tmp_path / "logs" / "telegram.log").read_text()


@pytest.mark.parametrize(("mode", "journal_status"),
                         [("http_500", "FAILED"), ("timeout", "FAILED"), ("unknown", "ERROR")])
def test_ambiguous_lsmc_delivery_is_never_auto_resent(tmp_path, monkeypatch, mode, journal_status):
    """A 5xx/timed-out/unknown OPPORTUNITY send is DELIVERY_UNCERTAIN in the dedup ledger.

    The legacy JSONL row keeps its frozen FAILED / ERROR vocabulary, but the ledger must never
    treat the ambiguous confirmation as a known failure eligible for a later blind resend.
    """
    monkeypatch.setattr("large_smc_watch.watch.c11_causal_target", lambda *args: 1.12)
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN-VALUE")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    attempts = []
    original = tg.send_message

    def ambiguous(text):
        attempts.append(text)
        if mode == "unknown":
            raise RuntimeError("transport outcome unknown")
        original(text, session=_Sess(status=500, ok=False) if mode == "http_500" else _Sess(boom=True))

    monkeypatch.setattr(tg, "send_message", ambiguous)
    journal = tmp_path / "journal"
    first = smoke.run_lsmc(fake_fetch(), NOW, str(journal))
    assert len(attempts) == 2                                     # EURUSD + GBPUSD OPPORTUNITY
    assert any("LSMC_DELIVERY EURUSD DELIVERY_UNCERTAIN" in ln for ln in first)
    ledger = json.loads((journal / "large_smc_watch" / "delivered_confirmations.json").read_text())
    assert {row["state"] for row in ledger.values()} == {"DELIVERY_UNCERTAIN"}
    rows = [json.loads(ln) for ln in (journal / "ticket_delivery" / "delivery_status" /
                                      f"{NOW.date().isoformat()}.jsonl").read_text().splitlines()]
    assert len(rows) == 2 and {row["status"] for row in rows} == {journal_status}

    # A later cycle re-enters OPPORTUNITY for the same confirmation (tracker restart): the
    # ambiguous send is suppressed, never retried.
    os.remove(journal / "large_smc_watch" / "state.json")
    second = smoke.run_lsmc(fake_fetch(), NOW, str(journal))
    assert len(attempts) == 2
    assert any("LSMC_DELIVERY EURUSD SUPPRESSED_UNCERTAIN_CONFIRMATION" in ln for ln in second)


def test_telegram_proposal_cli_sends_rendered_validation(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(tg, "send_message", sent.append)
    assert tg.main(["--test-proposal"]) == 0
    assert len(sent) == 1 and sent[0].startswith("SIMULATED TELEGRAM DELIVERY VALIDATION")
    assert "entry:" in sent[0] and "target leg 2" in sent[0] and "VALID UNTIL" in sent[0]
    assert "TELEGRAM_PROPOSAL_TEST: OK" in capsys.readouterr().out


def test_telegram_status_requires_override_scopes_and_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN-VALUE")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert tg.main(["--status"]) == 1
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    assert tg.main(["--status"]) == 0
    output = capsys.readouterr().out
    assert "credentials=PRESENT" in output and "SECRET-TOKEN-VALUE" not in output


def test_telegram_missing_env_fails_closed():
    with pytest.raises(tg.TelegramSendError):
        tg.send_message("x", session=_Sess())


def test_repo_default_delivery_stays_archive_only():
    import yaml
    assert yaml.safe_load((ROOT / "config" / "ticket_delivery.yaml").read_text())["mode"] == "ARCHIVE_ONLY"
    assert not (ROOT / "config" / "local" / "delivery_override.yaml").exists()


def test_notify_logs_sent_ok_and_failure_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "should_send", lambda *a: True)
    monkeypatch.setattr(tg, "send_message", lambda text: None)
    smoke._notify("TICKET", "READY", "x", str(tmp_path))

    def boom(text):
        raise tg.TelegramSendError("send failed (HTTP 401)", delivery_state="DELIVERY_FAILED")
    monkeypatch.setattr(tg, "send_message", boom)
    smoke._notify("LSMC", "OPPORTUNITY", "x", str(tmp_path))
    log = (tmp_path / "logs" / "telegram.log").read_text()
    assert "TELEGRAM_SENT_OK TICKET=READY" in log
    assert "TELEGRAM_SEND_DELIVERY_FAILED LSMC=OPPORTUNITY send failed (HTTP 401)" in log


def _status_host(tmp_path, override=True, venv=True, log="", runner_age_h=1.0):
    import telegram_status as ts
    now = dt.datetime(2026, 10, 4, 12, tzinfo=UTC)
    if override:
        (tmp_path / "config" / "local").mkdir(parents=True)
        (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
            "﻿# comment\nmode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n",
            encoding="utf-8")
    if venv:
        (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
        (tmp_path / ".venv" / "Scripts" / "python.exe").write_text("")
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "telegram.log").write_text(log)
    runner = tmp_path / "logs" / "ag_v1_crypto.log"
    runner.write_text("x")
    stamp = (now - dt.timedelta(hours=runner_age_h)).timestamp()
    os.utime(runner, (stamp, stamp))
    creds = {n: {"process": False, "user": True} for n in ts.CRED_VARS}
    return ts, ts.build_report(str(tmp_path), now=now, creds=creds)


def test_telegram_status_ok_disabled_and_down(tmp_path):
    ok_line = "2026-10-04T08:00:00+00:00 TELEGRAM_SENT_OK TICKET=READY\n"
    ts, r = _status_host(tmp_path / "a", log=ok_line)
    assert r["status"] == "OK" and r["reasons"] == []
    assert r["telegram_log"]["last_ok"]["at"].startswith("2026-10-04T08")
    _, r = _status_host(tmp_path / "b", override=False)
    assert r["status"] == "DISABLED" and r["delivery"]["mode"] == "ARCHIVE_ONLY"
    _, r = _status_host(tmp_path / "c", venv=False)
    assert r["status"] == "DOWN" and any(".venv" in x for x in r["reasons"])
    report = ts.build_report(str(tmp_path / "a"), now=dt.datetime(2026, 10, 4, 12, tzinfo=UTC),
                             creds={n: {"process": True, "user": False} for n in ts.CRED_VARS})
    assert report["status"] == "DOWN" and sum("User environment" in x for x in report["reasons"]) == 2


def test_telegram_status_degraded_on_failure_or_silent_runner(tmp_path):
    log = ("2026-10-03T08:00:00+00:00 TELEGRAM_SENT_OK TICKET=READY\n"
           "2026-10-04T08:00:00+00:00 TELEGRAM_SEND_FAILED TICKET=READY send failed (HTTP 401)\n")
    _, r = _status_host(tmp_path / "a", log=log)
    assert r["status"] == "DEGRADED" and "HTTP 401" in r["reasons"][0]
    _, r = _status_host(tmp_path / "b", runner_age_h=30)
    assert r["status"] == "DEGRADED" and "26h" in r["reasons"][0]
    manual = tmp_path / "b" / "logs" / "ag_v1_smoke.log"
    manual.write_text("x")                                   # a manual smoke run is not runner activity
    import telegram_status as ts
    r = ts.build_report(str(tmp_path / "b"), now=dt.datetime(2026, 10, 4, 12, tzinfo=UTC),
                        creds={n: {"process": False, "user": True} for n in ts.CRED_VARS})
    assert r["status"] == "DEGRADED"


def test_telegram_status_never_prints_credential_values(tmp_path, monkeypatch, capsys):
    import telegram_status as ts
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN-VALUE")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    _status_host(tmp_path)
    ts.main(["--root", str(tmp_path)])
    ts.main(["--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert "SECRET-TOKEN-VALUE" not in out and "987654321" not in out and "TELEGRAM_REPORT_STATUS:" in out


# ------------------------------------------------------------------ static invariants (4, 5, 6)

def test_complete_six_instrument_objective_preflight(monkeypatch):
    monkeypatch.delenv("AG_EVIDENCE_ROOT", raising=False)  # verify committed host captures
    report = objective.verify(ROOT)
    assert report["result"] == "PASS", report["failures"]
    assert {c["check"] for c in report["checks"]} >= {"telegram_report_scope", "safe_delivery_default"}
    assert report["objective"] == {
        "fx_majors": ["EURUSD", "GBPUSD", "USDJPY"], "gold": ["XAUUSD"],
        "crypto": ["BTCUSDT", "ETHUSDT"],
        "watch_universe": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"],
        "cycles": ["ASIAN_LONDON", "LONDON_NEWYORK"],
    }


def test_no_order_or_position_calls_anywhere_in_the_kit():
    files = list(HOST.glob("*.py")) + list((ROOT / "src" / "host_evidence").glob("*.py")) + \
        list((ROOT / "src" / "host_delivery").glob("*.py"))
    for f in files:
        src = f.read_text(encoding="utf-8")
        for call in ("order_send(", "order_check(", "positions_get(", "position_close(", "orders_get("):
            assert call not in src, f"{f.name}: {call}"


def test_powershell_scripts_default_to_whatif_and_hold_no_secrets():
    install = (HOST / "install_tasks.ps1").read_text()
    uninstall = (HOST / "uninstall_tasks.ps1").read_text()
    verify = (HOST / "verify_tasks.ps1").read_text()
    telegram = (HOST / "enable_telegram.ps1").read_text()
    verify_telegram = (HOST / "verify_telegram.ps1").read_text()
    for s in (install, uninstall):
        assert "param([switch]$Apply)" in s and "WhatIf: no changes made" in s
    for name in ("AG-V1-FX-Cycles", "AG-V1-Crypto-Daily", "AG-V1-LSMC-Watch"):
        assert name in install and name in uninstall
    assert ".venv\\Scripts\\python.exe" in install and "MultipleInstances IgnoreNew" in install
    assert "--mode {1}" in install and "--mode {1}{2}" in install
    assert "Name = 'AG-V1-FX-Cycles';    Mode = 'fx';     Minutes = 15; Canonical = $true" in install
    # scripts/docs/build_context_pack.py reads the plan rows positionally (Name; Mode; Minutes;),
    # so a new field must never be inserted between Mode and Minutes or CONTEXT_PACK loses the tasks.
    assert len(re.findall(r"@\{\s*Name\s*=\s*'([^']+)';\s*Mode\s*=\s*'([^']+)';\s*Minutes\s*=\s*(\d+);", install)) == 3
    assert "Name = 'AG-V1-LSMC-Watch';   Mode = 'lsmc'" in install
    assert "ExecutionTimeLimit (New-TimeSpan -Minutes 4) -Priority 4" in install   # default 7 = low I/O
    runner = (HOST / "live_candles_smoke.py").read_text(encoding="utf-8")
    assert runner.index("start_run_watchdog(f\"ag_v1_") < runner.index("from large_smc_watch import")
    assert "--canonical" in runner and "manual_lines = run_manual_jobs(fetch, now, journal)" in runner
    assert runner.index("manual_lines = run_manual_jobs(fetch, now, journal)") < runner.index("provider = snapshot_provider(GuardedMT5(mt5))")
    assert "--canonical" in verify and "$e.Canonical" in verify
    starts = re.findall(r"StartAt = '(\d\d:\d\d:\d\d)'", install)
    assert starts == ["00:01:00", "00:02:30", "00:04:15"]   # FX, crypto tickets, six-symbol LSMC (stagger rule)
    assert "-Execute $PythonW" in install and ".venv\\Scripts\\pythonw.exe" in verify
    assert "AG-V1-LSMC-Crypto-Weekend" in install and "AG-V1-LSMC-Crypto-Weekend" in uninstall
    assert "REMOVED SUPERSEDED" in install             # prevent duplicate weekend watch polling
    assert "verify_objective.py" in install and "verify_tasks.ps1" in install
    assert "RESULT: PASS (3/3 scheduled task bindings valid; no duplicate weekend watcher)" in verify
    for name in ("AG-V1-FX-Cycles", "AG-V1-Crypto-Daily", "AG-V1-LSMC-Watch"):
        assert name in verify
    assert "superseded duplicate task is still installed" in verify
    assert not re.search(r"Write-Host[^\n]*TELEGRAM_BOT_TOKEN\b(?!\s+and)", telegram.replace("MISSING TELEGRAM_BOT_TOKEN", ""))
    assert "reply_markup" not in telegram and "delivery_override.yaml" in telegram
    assert "ticket_delivery.yaml" in telegram and "Set-Content" in telegram
    assert "--test-proposal" in telegram and "--status" in verify_telegram and "--test-proposal" in verify_telegram
    assert "RESULT: PASS -- simulated proposal rendered and accepted by Telegram." in verify_telegram
    for s in (install, uninstall, telegram, verify_telegram):
        assert not re.search(r"\d{6,}:[A-Za-z0-9_-]{20,}", s)          # no bot-token-shaped literal


DECL_RE = re.compile(r"@\{ Name = '([^']+)'; Path = '([^']*)'; Managed = '(\w+)'; Status = '(\w+)'\s*"
                     r"Registered = '[^']*'(?:; DeleteAfter = '([\d-]+)')?\s*Target = @\{ State = '(\w+)'(.*?)\}\s*;?\s*Note = ",
                     re.S)


def _host_declarations():
    text = (HOST / "install_tasks.ps1").read_text(encoding="utf-8")
    return text, [dict(zip(("name", "path", "managed", "status", "delete_after", "state", "rest"), m))
                  for m in DECL_RE.findall(text)]


def _comment_facts(text: str, tag: str) -> dict:
    """`# <tag>: K=V; K=V` -> {K: V}; the format the host facts collector parses."""
    line = re.search(rf"^# {tag}: (.+)$", text, re.M).group(1)
    return dict(kv.strip().split("=", 1) for kv in line.split(";"))


def test_install_tasks_declares_host_timezone_and_always_on_power_policy_without_applying_it():
    text, _ = _host_declarations()
    assert _comment_facts(text, "AG-HOST-TIMEZONE") == {
        "Id": "Myanmar Standard Time", "Abbrev": "MMT", "UtcOffset": "+06:30", "DST": "false"}
    assert _comment_facts(text, "AG-HOST-POWER-POLICY") == {
        "AC_STANDBY_TIMEOUT_MIN": "0", "AC_HIBERNATE_TIMEOUT_MIN": "0", "MODE": "ALWAYS_ON"}
    script = text.split("#>", 1)[1]                                  # after the header comment block
    code = [re.sub(r"'[^']*'", "''", ln) for ln in script.splitlines() if not ln.lstrip().startswith("#")]
    assert not any(re.search(r"powercfg|SetSuspendState|Set-.*Power", ln, re.I) for ln in code)  # declared data only


def test_install_tasks_declarations_parse_to_the_always_on_target():
    text, decl = _host_declarations()
    assert text.count("@{ Name = '") - 3 == len(decl) == 17     # 3 $Plan rows + 16 registered + 1 new
    by = {d["name"]: d for d in decl}
    assert len(by) == len(decl)
    statuses = {"ACTIVE", "NEW", "RETIRED", "REMOVE", "DISABLED", "DISABLE_AFTER_PARITY"}
    assert {d["status"] for d in decl} <= statuses
    for d in decl:
        assert d["state"] == {"RETIRED": "ABSENT", "REMOVE": "ABSENT", "DISABLED": "DISABLED"}.get(d["status"], "ENABLED")
    # The optional Canonical field (main) sits between Minutes and StartAt (SCHED-R1-B); the regex
    # must tolerate it or the loop below silently passes on an empty match.
    plan = re.findall(r"Name = '(AG-V1-[\w-]+)';\s+Mode = '(\w+)';\s+Minutes = (\d+);"
                      r"(?:\s*Canonical = \$(true|false);)?\s*StartAt = '([\d:]+)'", text)
    assert len(plan) == 3, plan                                     # never accept a vacuous match
    for name, mode, minutes, canonical, start in plan:               # $Plan and its declaration agree
        d = by[name]
        assert (d["managed"], d["status"]) == ("INSTALLER", "ACTIVE")
        # The target action is what -Apply installs: $Plan Canonical = true adds --canonical.
        suffix = " --canonical" if canonical == "true" else ""
        assert "pythonw.exe" in d["rest"] and f"--mode {mode}{suffix}'" in d["rest"], (name, d["rest"])
        assert f"Days = 'DAILY'; Start = '{start}'; EveryMin = {minutes} " in d["rest"]
    assert by["AG-V1-LSMC-Crypto-Weekend"]["managed"] == "RETIRE"
    assert {n for n, d in by.items() if d["status"] == "RETIRED"} == {
        "AG-V1-LSMC-Crypto-Weekend", "AG-Wake-MT5", "AG-Wake-Weekend-Crypto", "AG-Sleep-Night", "AG-Sleep-Weekend-Crypto"}
    friction = [d for n, d in by.items() if n.startswith("AG_LSMC_EURUSD_Friction_Window")]
    assert len(friction) == 4 and all(d["status"] == "DISABLED" and d["delete_after"] == "2026-10-15" for d in friction)
    assert {n for n, d in by.items() if d["status"] == "REMOVE"} == {"AG_FX_ASIAN_LONDON_SHADOW", "AG_FX_LONDON_NEWYORK_SHADOW"}
    assert by["AG Profit Trading - BTC Daily Decision"]["status"] == "DISABLE_AFTER_PARITY"
    hb = by["AG-Heartbeat-Local"]
    assert hb["status"] == "NEW" and "heartbeat.py" in hb["rest"] and "EveryMin = 60" in hb["rest"]
    assert "{TELEMETRY}" in hb["rest"] and "<HOST_SCRATCHPAD>" in hb["rest"]
    # PR #84 review P1: the always-on target heartbeat must not fall back to the wake_sleep default,
    # or overnight runner silence would read INACTIVE_EXPECTED instead of STALE.
    target_args = re.search(r"Args = '([^']*)'", hb["rest"]).group(1)
    assert target_args.count("--host-power-mode always_on") == 1, target_args
    assert not re.search(r"S-1-5-\d|C:\\Users\\(?!%)[A-Za-z]", text)  # sanitized: no SIDs or user-profile paths
    # AGENTS.md host-evidence rule: a private checkout root is never committed (PR #78 review P1).
    assert not re.search(r"[A-Z]:\\\\(wp3-main-integ|ddev|ag-telemetry)", text), text


def test_go_live_doc_lists_the_six_steps_in_order():
    doc = (HOST / "GO_LIVE.md").read_text()
    order = ["diagnose_mt5.py", "capture_symbol_metadata.py", "live_candles_smoke.py",
             "install_tasks.ps1", "install_tasks.ps1 -Apply", "enable_telegram.ps1"]
    idx = [doc.index(k) for k in order]
    assert idx == sorted(idx)


# ------------------------------------------------------------------ server-time rule / VT venue

def test_offset_rule_is_new_york_plus_seven():
    assert sm.server_utc_offset_hours(dt.datetime(2026, 9, 30, 12, tzinfo=UTC)) == 3        # EDT
    assert sm.server_utc_offset_hours(dt.datetime(2026, 12, 1, 12, tzinfo=UTC)) == 2        # EST
    # FX weekly reopen: server 00:00 = 21:00 UTC (EDT); XAUUSD's later reopen 01:00 = 22:00 UTC, not "+4"
    assert sm.server_time_to_utc(dt.datetime(2026, 9, 28, 0, 0)) == dt.datetime(2026, 9, 27, 21, 0, tzinfo=UTC)
    assert sm.server_time_to_utc(dt.datetime(2026, 9, 28, 1, 0)) == dt.datetime(2026, 9, 27, 22, 0, tzinfo=UTC)
    # USDJPY-VIP's late first bar (00:15) simply maps to 21:15 UTC -- no ambiguity error
    assert sm.server_time_to_utc(dt.datetime(2026, 9, 14, 0, 15)) == dt.datetime(2026, 9, 13, 21, 15, tzinfo=UTC)
    assert sm.server_time_to_utc(dt.datetime(2026, 11, 9, 0, 0)) == dt.datetime(2026, 11, 8, 22, 0, tzinfo=UTC)


class VenueMT5(FakeMT5):
    SYMBOL_TRADE_MODE_DISABLED, SYMBOL_TRADE_MODE_FULL = 0, 4
    TIMEFRAME_M5 = 5

    def __init__(self):
        super().__init__(symbols=("EURUSD", "EURUSD-VIP", "BTCUSD"))

    def symbol_info(self, name):
        info = super().symbol_info(name)
        if info is not None:
            info.trade_mode = 0 if name == "EURUSD" else 4
        return info

    def copy_rates_from_pos(self, symbol, tf, start, count):
        self.calls.append(("copy_rates_from_pos", symbol, tf, start, count))
        t0 = int(dt.datetime(2026, 9, 28, 0, 0, tzinfo=UTC).timestamp())        # server wall clock 00:00
        return [{"time": t0 + 300 * i, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "tick_volume": 7}
                for i in range(count)]


def test_capture_derives_offset_from_rule_and_records_it(tmp_path):
    rc = cap.main(["--symbol", "EURUSD", "--broker-symbol", "EURUSD-VIP"], mt5=VenueMT5(), root=str(tmp_path / "evidence"))
    assert rc == 0
    rec = sm.load_record("EURUSD")
    at = dt.datetime.fromisoformat(rec["captured_at_utc"])
    assert rec["schema"] == "AG_HOST_SYMBOL_METADATA_V2" and rec["server_utc_offset_rule"] == sm.OFFSET_RULE
    assert rec["server_utc_offset_hours"] == sm.server_utc_offset_hours(at) and rec["trade_mode"] == "FULL"
    from v1_tickets import fx
    assert fx.broker_symbol("EURUSD") == "EURUSD-VIP" and fx.metadata_status("EURUSD") == "HOST_CAPTURED"
    assert set(cap.CAPTURABLE) == {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"}


def test_v1_schema_record_still_verifies():
    rec = sm.build_record("USDJPY", "USDJPY", {f: 1 for f in sm.FIELDS}, "S", 3, "t")
    payload = {k: v for k, v in rec.items() if k not in ("sha256", "server_utc_offset_rule", "trade_mode")}
    payload["schema"] = "AG_HOST_SYMBOL_METADATA_V1"
    import hashlib
    old = {**payload, "sha256": hashlib.sha256(sm._canonical(payload).encode()).hexdigest()}
    assert sm.verify(old) and sm.verify(rec)


def test_host_fetch_reason_codes():
    mt5 = VenueMT5()
    with pytest.raises(sm.HostDataError) as missing:
        hc.host_fetch(mt5)("NOPE", "M5", 3)
    mt5.copy_rates_from_pos = lambda *a: []
    with pytest.raises(sm.HostDataError) as short:
        hc.host_fetch(mt5)("BTCUSD", "M5", 3)
    mt5.copy_rates_from_pos = lambda *a: [{"time": "x", "open": 1}] * 3
    with pytest.raises(sm.HostDataError) as bad:
        hc.host_fetch(mt5)("BTCUSD", "M5", 3)
    assert (missing.value.code, short.value.code, bad.value.code) == (
        "SYMBOL_NOT_FOUND", "INCOMPLETE_CANDLES", "CONVERSION_ERROR")


def test_diagnose_server_offset_live_check():
    """Audit 2 / Codex CRITICAL (818e3cd): measured tick.time - time.time() must equal the rule offset."""
    now = dt.datetime(2026, 9, 30, 15, 0, tzinfo=UTC).timestamp()        # US DST -> rule UTC+3
    ok = FakeMT5(symbols=("BTCUSD",))
    ok.symbol_info_tick = lambda s: types.SimpleNamespace(time=int(now) + 10798)   # host evidence: +3.0h
    r = diag.check_server_offset(ok, now)
    assert r["ok"] and "measured=UTC+3 rule=UTC+3" in r["detail"]
    bad = FakeMT5()
    bad.symbol_info_tick = lambda s: types.SimpleNamespace(time=int(now) + 2 * 3600)
    r = diag.check_server_offset(bad, now)
    assert not r["ok"] and r["fix"] == diag.FIXES["SERVER_OFFSET"]
    stale = FakeMT5()
    stale.symbol_info_tick = lambda s: types.SimpleNamespace(time=int(now) - 3 * 86400 + 1234)
    assert diag.check_server_offset(stale, now)["fix"] == diag.FIXES["SERVER_OFFSET_NO_TICK"]
    assert sm.measured_server_offset_hours(now + 10798, now) == 3 and sm.measured_server_offset_hours(now + 5400, now) is None


def test_host_fetch_uses_rule_and_closed_bars_only():
    mt5 = VenueMT5()
    bars = hc.host_fetch(mt5)("BTCUSD", "M5", 3)
    assert [b.time for b in bars] == [dt.datetime(2026, 9, 27, 21, 0, tzinfo=UTC) + dt.timedelta(minutes=5 * i)
                                      for i in range(3)]
    assert ("copy_rates_from_pos", "BTCUSD", 5, 1, 3) in mt5.calls                   # position 1: forming bar excluded


def test_mt5_server_wall_london_open_summer_and_winter():
    """CRITICAL-1 regression: MT5 server-wall-clock extraction + rule conversion produces
    correct UTC for London open in both US DST and non-DST seasons; no bar timestamped after
    its data-available time (position=1 in copy_rates_from_pos excludes the forming bar)."""
    # Summer 2026-09-29: EDT active, NY = UTC-4, VT server = UTC+3.
    # London BST open 08:00 BST = 07:00 UTC = 10:00 server.
    # MT5 stores server time as "server wall-clock seconds from UTC epoch".
    summer_raw = int(dt.datetime(2026, 9, 29, 10, 0, tzinfo=UTC).timestamp())
    # Winter 2026-12-01: EST active, NY = UTC-5, VT server = UTC+2.
    # London winter open 08:00 UTC = 10:00 server.
    winter_raw = int(dt.datetime(2026, 12, 1, 10, 0, tzinfo=UTC).timestamp())

    from host_evidence.symbol_metadata import server_time_to_utc
    assert server_time_to_utc(hc._mt5_server_wall(summer_raw)) == dt.datetime(2026, 9, 29, 7, 0, tzinfo=UTC)
    assert server_time_to_utc(hc._mt5_server_wall(winter_raw)) == dt.datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def test_smoke_includes_vt_crypto_with_v2_config(tmp_path):
    from test_v1_tickets import _cfg
    fetch = fake_fetch()

    def fetch_all(symbol, tf, count):
        return fetch("EURUSD-VIP" if symbol in ("BTCUSD", "ETHUSD") else symbol, tf, count)
    lines = smoke.run_smoke(fetch_all, NOW, str(tmp_path / "journal"), _cfg(2))
    text = "\n".join(lines)
    assert "BARS BTCUSDT (BTCUSD) status=" in text and "BARS ETHUSDT (ETHUSD) status=" in text
    assert re.search(r"CRYPTO BTCUSDT (OUTSIDE_WINDOW|decision=)", text)


def test_flush_std_streams_tolerates_pythonw_none_streams(monkeypatch):
    """pythonw.exe (Task Scheduler) runs with sys.stdout/sys.stderr = None; exit must not raise."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    smoke.flush_std_streams()


def test_target_heartbeat_args_parse_to_always_on_mode():
    """PR #84 P1: the declared AG-Heartbeat-Local target arguments, parsed by heartbeat.py's own
    CLI, select always_on, so a stopped runner overnight is STALE, never INACTIVE_EXPECTED."""
    import shlex
    import heartbeat as hb_module
    _, decl = _host_declarations()
    rest = {d["name"]: d for d in decl}["AG-Heartbeat-Local"]["rest"]
    args = shlex.split(re.search(r"Args = '([^']*)'", rest).group(1), posix=True)[1:]  # drop the script path
    captured = {}

    def fake_build(*a, **kw):
        captured.update(kw)
        return {}
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(hb_module, "build", fake_build)
        mp.setattr(hb_module, "write", lambda payload, out: out)
        try:
            hb_module.main(args)
        except SystemExit as exc:
            assert exc.code in (0, None), exc
    assert captured.get("power_mode") == "always_on", captured
