Warning: truncated output (original token count: 12956)
Total output lines: 1008

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
    assert re.search(r"FX EURUSD \(EURUSD-VIP\) ASIAN_LONDON data=FRESH decision=(READY|NO_TRADE|STALE) reason=", text)
    assert "LSMC EURUSD data=FRESH state=OPPORTUNITY" in text and "LSMC GBPUSD" in text
    # Objective symbols are never silently omitted: unavailable metadata/data is visible.
    assert "FX USDJPY" in text and "decision=DATA_ERROR" in text
    assert glob.glob(str(tmp_path / "journal" / "ticket_delivery" / "archive" / "**" / "*.json"), recursive=True)


def test_smoke_includes_usdjpy_once_metadata_captured(tmp_path):
    cap.main(["--symbol", "USDJPY", "--broker-symbol", "USDJPY"], mt5=FakeMT5(), offset_fn=lambda s: 2,
             root=s…7956 tokens truncated…      assert name in install and name in uninstall
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
    offsets = [int(o) for o in re.findall(r"Offset = (\d+)", install)]
    assert offsets == [1, 2, 3]                        # FX, crypto tickets, continuous six-symbol LSMC
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
