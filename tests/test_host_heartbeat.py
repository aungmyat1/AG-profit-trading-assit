"""DOCS-LIVE-3A host heartbeat: fixture logs/archives/history -> counts, UNKNOWN on unreadable sources."""
from __future__ import annotations

import ast
import contextlib
import datetime as dt
import json
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))

import heartbeat as hb  # noqa: E402

from host_evidence.symbol_metadata import NY, SERVER_MINUS_NY_HOURS  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=UTC)          # Thursday 18:30 MMT: inside the daily awake window
T = NOW - dt.timedelta(hours=4)                             # 08:00Z, inside the ASIAN_LONDON trade window
EURUSD_READY = "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=READY reason=- ARCHIVED"
ORDERS_HDR = "time_setup,ticket,magic,symbol"
DEALS_HDR = "time,ticket,type,magic,symbol"


def _log(root: Path, name: str, lines):
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs" / f"{name}.log").write_text("".join(f"{t.isoformat()} {m}\n" for t, m in lines), encoding="utf-8")


def _fixture(root: Path):
    _log(root, "ag_v1_fx", [
        (NOW - dt.timedelta(hours=30), EURUSD_READY),                  # outside 24 h
        (T, EURUSD_READY),
        (T, "FX GBPUSD (GBPUSD-VIP) ASIAN_LONDON data=FRESH decision=STALE reason=STALE_SIGNAL"),
        (T, "FX USDJPY (USDJPY-VIP) ASIAN_LONDON data=FRESH decision=SPREAD_TOO_WIDE reason=x"),
        (T, "FX XAUUSD (XAUUSD-VIP) ASIAN_LONDON data=FRESH decision=DATA_ERROR reason=x"),
        (T, "TIMEOUT run exceeded 120 s"),
        (NOW - dt.timedelta(minutes=5), "FX NOTHING_IN_WINDOW"),
    ])
    _log(root, "ag_v1_lsmc", [(NOW - dt.timedelta(minutes=3), "LSMC XAUUSD data=FRESH state=OPPORTUNITY source=X alerts=[]")])
    _log(root, "ag_v1_crypto", [(NOW - dt.timedelta(minutes=4), "CRYPTO BTCUSDT OUTSIDE_WINDOW (BEFORE_WINDOW)")])


def _server(t: dt.datetime) -> str:
    """UTC -> broker server wall-clock text (inverse of server_time_to_utc)."""
    return (t.astimezone(NY).replace(tzinfo=None) + dt.timedelta(hours=SERVER_MINUS_NY_HOURS)).strftime("%Y-%m-%d %H:%M:%S")


OK_RES = {"status": "OK"}


def _fetch(orders: str, deals: str):
    return lambda a, b: {"readonly_get_orders": orders, "readonly_get_deals": deals}


def _mcp(fetch):
    return lambda now: hb.broker_history(now, fetch)


def test_counts_and_contract_fields(tmp_path):
    _fixture(tmp_path)
    out = hb.build(str(tmp_path), now=NOW, tasks={"AG-X": {"LastTaskResult": 0}}, resources=OK_RES)
    al = out["last_24h"]["fx_by_window_per_cycle"]["ASIAN_LONDON"]
    assert (al["READY"], al["STALE"], al["SPREAD_TOO_WIDE"], al["errors"]) == (1, 1, 1, 1)
    assert out["last_24h"]["lsmc_states_per_cycle"] == {"OPPORTUNITY": 1}
    assert out["last_24h"]["runner_errors"]["fx"]["TIMEOUT"] == 1
    assert out["observed_at_utc"] == NOW.isoformat() and out["mt5_connected"]["value"] is True
    assert out["host_head_sha"] == hb.UNKNOWN and out["host_ref"] == hb.UNKNOWN and out["status"] == hb.UNKNOWN
    assert "server" not in json.dumps({k: v for k, v in out.items() if k != "execution_paths"}).lower()
    assert not any(m.startswith("ASIAN_LONDON:2026-10-08") for m in out["missed_windows"])
    assert "LONDON_NEWYORK:2026-10-07" in out["missed_windows"]


def test_missing_log_is_unknown(tmp_path):
    _log(tmp_path, "ag_v1_fx", [(T, EURUSD_READY)])
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["sources"]["ag_v1_lsmc.log"]["status"] == "MISSING"
    assert out["last_24h"]["lsmc_states_per_cycle"] == hb.UNKNOWN
    assert out["last_24h"]["lsmc_unique_opportunities_24h"] == hb.UNKNOWN       # no archive
    assert out["last_24h"]["runner_errors"]["crypto"] == hb.UNKNOWN
    assert out["duplicates"]["telegram_same_ref_sends"] == hb.UNKNOWN          # no delivery journal
    nothing = hb.build(str(tmp_path / "absent"), now=NOW, tasks=hb.UNKNOWN)
    assert nothing["last_24h"]["fx_by_window_per_cycle"] == hb.UNKNOWN
    assert nothing["missed_windows"] == hb.UNKNOWN
    assert nothing["observed_broker_order_calls"] == hb.UNKNOWN
    assert nothing["mt5_connected"]["value"] == hb.UNKNOWN


def test_stale_log_is_flagged_and_mt5_status_unknown(tmp_path):
    _log(tmp_path, "ag_v1_fx", [(NOW - dt.timedelta(hours=5), "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=NO_TRADE")])
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["sources"]["ag_v1_fx.log"]["status"] == "STALE"                 # inside awake window, 5 h quiet
    assert out["mt5_connected"]["value"] == hb.UNKNOWN                          # newest MT5 line is 5 h old


def test_schedule_aware_staleness():
    old = [(NOW - dt.timedelta(days=4), "LSMC BTCUSDT data=FRESH state=IDLE")]
    weekend = hb.SOURCE_WINDOWS["lsmc-weekend"]
    assert hb.source_status(old, NOW, weekend)["status"] == "INACTIVE_EXPECTED"   # Thursday: outside Sun/Mon window
    sun_0330 = dt.datetime(2026, 10, 11, 3, 30, tzinfo=hb.MMT)                    # 20 min into the Sunday window
    assert hb.source_status(old, sun_0330, weekend)["status"] == "OK"
    sun_0540 = dt.datetime(2026, 10, 11, 5, 40, tzinfo=hb.MMT)                    # 2.5 h in, still quiet
    assert hb.source_status(old, sun_0540, weekend)["status"] == "STALE"
    mon_0400 = dt.datetime(2026, 10, 12, 4, 0, tzinfo=hb.MMT)
    assert hb.active_window_start(weekend, mon_0400) is not None
    tue_0400 = dt.datetime(2026, 10, 13, 4, 0, tzinfo=hb.MMT)
    assert hb.active_window_start(weekend, tue_0400) is None
    night = dt.datetime(2026, 10, 9, 0, 30, tzinfo=hb.MMT)                       # 00:30 MMT: daily window crosses midnight
    assert hb.active_window_start(hb.SOURCE_WINDOWS["fx"], night) is not None
    assert hb.source_status(old, dt.datetime(2026, 10, 9, 2, 0, tzinfo=hb.MMT), hb.SOURCE_WINDOWS["fx"])["status"] \
        == "INACTIVE_EXPECTED"                                                  # Friday 02:00 MMT: host asleep


OVERNIGHT_LAST = dt.datetime(2026, 10, 7, 12, 0, tzinfo=hb.MMT).astimezone(UTC)   # last runner line
OVERNIGHT_NOW = dt.datetime(2026, 10, 8, 3, 0, tzinfo=hb.MMT).astimezone(UTC)     # inside the old sleep span


def test_overnight_silence_is_expected_only_under_the_observed_wake_sleep_mode():
    """2026-10-08 01:30 MMT sits inside the retired AG-Sleep-Night span (00:45-12:25 MMT)."""
    lines = [(OVERNIGHT_LAST, "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=NO_TRADE")]
    windows = hb.SOURCE_WINDOWS["fx"]
    assert hb.active_window_start(windows, OVERNIGHT_NOW) is None
    assert hb.source_status(lines, OVERNIGHT_NOW, windows, "wake_sleep")["status"] == "INACTIVE_EXPECTED"


def test_always_on_mode_never_reports_overnight_silence_as_inactive_expected():
    """SCHED-R1-B: the wake/sleep tasks are retired, so the sleep span no longer exists.

    A runner that stopped overnight must be STALE, not INACTIVE_EXPECTED -- otherwise a dead
    runner is relabelled "expected quiet" for the whole 00:45-12:25 MMT span (PR #81 review P1).
    """
    lines = [(OVERNIGHT_LAST, "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=NO_TRADE")]
    windows = hb.source_windows("always_on", "fx")
    assert windows == hb.ALWAYS_ON_WINDOWS
    assert hb.active_window_start(windows, OVERNIGHT_NOW) is not None      # no minute is "asleep"
    got = hb.source_status(lines, OVERNIGHT_NOW, windows, "always_on")
    assert got["status"] == "STALE" and got["power_mode"] == "always_on"
    # Every runner, including the weekend-only one, loses its sleep exemption under always_on.
    for name in hb.RUNNER_LOGS:
        quiet = [(OVERNIGHT_LAST, "LSMC BTCUSDT data=FRESH state=IDLE")]
        assert hb.source_status(quiet, OVERNIGHT_NOW, hb.source_windows("always_on", name),
                                "always_on")["status"] == "STALE", name


def test_unknown_power_mode_fails_closed_to_the_always_on_rule():
    """An unrecognised mode must not invent a sleep span that hides a stopped runner."""
    lines = [(OVERNIGHT_LAST, "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=NO_TRADE")]
    windows = hb.source_windows("definitely_not_a_mode", "fx")
    assert windows == hb.ALWAYS_ON_WINDOWS
    assert hb.source_status(lines, OVERNIGHT_NOW, windows, "definitely_not_a_mode")["status"] == "STALE"


def test_build_records_the_power_mode_and_the_windows_it_actually_applied(tmp_path):
    _log(tmp_path, "ag_v1_fx", [(OVERNIGHT_LAST, "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=NO_TRADE")])
    out = hb.build(str(tmp_path), now=OVERNIGHT_NOW, tasks={}, resources=OK_RES, power_mode="always_on")
    assert out["host_power_mode"] == "always_on"
    assert "SCHED-R1-B" in out["host_power_mode_source"]
    assert "always_on" in out["reader_rule"] and "no sleep span" in out["reader_rule"]
    assert out["source_windows"]["fx"] == ["ALWAYS_ON"]
    assert out["sources"]["ag_v1_fx.log"]["status"] == "STALE"          # not INACTIVE_EXPECTED
    assert out["sources"]["ag_v1_fx.log"]["power_mode"] == "always_on"
    legacy = hb.build(str(tmp_path), now=OVERNIGHT_NOW, tasks={}, resources=OK_RES)
    assert legacy["host_power_mode"] == "wake_sleep"                     # default = observed state
    assert legacy["sources"]["ag_v1_fx.log"]["status"] == "INACTIVE_EXPECTED"
    assert legacy["source_windows"]["fx"] == ["AWAKE_DAILY", "WEEKEND_CRYPTO"]


def test_mt5_connect_failure_reports_false(tmp_path):
    _log(tmp_path, "ag_v1_lsmc", [(NOW - dt.timedelta(minutes=20), "LSMC EURUSD data=FRESH state=IDLE source=X"),
                                  (NOW - dt.timedelta(minutes=2), "MT5_INITIALIZE_FAILED last_error=(-6, x)")])
    assert hb.build(str(tmp_path), now=NOW, tasks={})["mt5_connected"]["value"] is False


def test_duplicate_ticket_is_counted(tmp_path):
    stale = "FX GBPUSD (GBPUSD-VIP) ASIAN_LONDON data=FRESH decision=STALE reason=STALE_SIGNAL ARCHIVED"
    _log(tmp_path, "ag_v1_fx", [(T, EURUSD_READY), (T + dt.timedelta(minutes=15), EURUSD_READY),
                                (T + dt.timedelta(minutes=30), EURUSD_READY), (T, stale), (T, stale)])
    (tmp_path / "journal" / "ticket_delivery" / "delivery_status").mkdir(parents=True)
    rows = [{"status": "SENT", "ref": "fx:EURUSD:2026-10-08", "recorded_at": T.isoformat()}] * 2
    (tmp_path / "journal" / "ticket_delivery" / "delivery_status" / "2026-10-08.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["duplicates"] == {"fx_archive": {"ready_ticket_duplicates": 2, "non_ready_rearchives": 1},
                                "telegram_same_ref_sends": 1}


def _transition(root: Path, symbol: str, tid: str, to_state: str, ref: str, at: dt.datetime):
    d = root / hb.LSMC_ARCHIVE / symbol / f"LSMC_WATCH-{tid}" / str(at.year)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{at.date().isoformat()}.json").write_text(json.dumps({"payload": {
        "symbol": symbol, "to_state": to_state, "reference_id": ref, "evaluated_at": at.isoformat()}}))


def test_lsmc_unique_opportunities(tmp_path):
    _transition(tmp_path, "XAUUSD", "a", "OPPORTUNITY", "XAU:OPP:1", T)
    _transition(tmp_path, "XAUUSD", "b", "OPPORTUNITY", "XAU:OPP:1", T + dt.timedelta(hours=1))   # same zone again
    _transition(tmp_path, "XAUUSD", "c", "OPPORTUNITY", "XAU:OPP:2", T)
    _transition(tmp_path, "EURUSD", "d", "OPPORTUNITY", "EUR:OPP:1", T)
    _transition(tmp_path, "EURUSD", "e", "NEAR_POI", "EUR:POI:9", T)                              # not an opportunity
    _transition(tmp_path, "EURUSD", "f", "OPPORTUNITY", "EUR:OPP:0", NOW - dt.timedelta(hours=30))  # older than 24 h
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["last_24h"]["lsmc_unique_opportunities_24h"] == {"count": 3, "by_symbol": {"EURUSD": 1, "XAUUSD": 2}}


def test_broker_history_counts_only(tmp_path):
    inside, old = NOW - dt.timedelta(hours=2), NOW - dt.timedelta(hours=30)
    orders = "\n".join([ORDERS_HDR, f"{_server(inside)},1,21099,EURUSD-VIP", f"{_server(inside)},2,0,EURUSD-VIP",
                        f"{_server(inside)},3,0,BTCUSD", f"{_server(old)},4,21099,EURUSD-VIP"])
    deals = "\n".join([DEALS_HDR, f"{_server(inside)},5,0,21099,EURUSD-VIP", f"{_server(inside)},6,1,0,EURUSD-VIP",
                       f"{_server(inside)},7,2,0,", f"{_server(old)},8,0,0,EURUSD-VIP"])
    out = hb.build(str(tmp_path), now=NOW, tasks={}, history=_mcp(_fetch(orders, deals)), resources=OK_RES)
    assert out["broker_history_24h"] == {"source": "MCP_PROXY", "orders": 3, "deals": 2, "by_magic": {"21099": 1},
                                         "manual_or_zero_magic": 2}
    assert out["broker_order_calls"] == 3
    text = json.dumps(out["broker_history_24h"])
    assert "EURUSD" not in text and "1.1" not in text                           # no symbols, tickets or prices


def test_broker_history_empty_unreachable_and_malformed(tmp_path):
    empty = hb.build(str(tmp_path), now=NOW, tasks={}, history=_mcp(_fetch('""\r\n', '""\r\n')), resources=OK_RES)
    assert empty["broker_history_24h"] == {"source": "MCP_PROXY", "orders": 0, "deals": 0, "by_magic": {},
                                           "manual_or_zero_magic": 0}
    assert empty["broker_order_calls"] == 0
    for history in (None, _mcp(None), _mcp(lambda a, b: None), _mcp(_fetch("not,a,history\n1,2,3", '""'))):
        out = hb.build(str(tmp_path), now=NOW, tasks={}, history=history, resources=OK_RES)
        assert out["broker_history_24h"] == hb.UNKNOWN and out["broker_order_calls"] == hb.UNKNOWN
    assert hb.mcp_history(str(tmp_path / "missing_launcher.mjs"), "2026-10-06", "2026-10-09") is None


def test_unlogged_paths_keep_log_count_separate(tmp_path):
    _log(tmp_path, "ag_v1_fx", [(T, EURUSD_READY), (T, "something order_send attempted")])
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["observed_broker_order_calls"] == 1
    assert out["broker_order_calls"] == hb.UNKNOWN                              # no history -> never the log count
    assert any(not p["logged"] for p in out["execution_paths"] if p["order_capable"])


def test_host_ref_on_main_and_detached(tmp_path):
    repo = tmp_path / "host"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q", "-b", "main")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    on = hb.build(str(repo), now=NOW, tasks={}, resources=OK_RES)
    assert (on["host_ref"], on["host_on_main"], on["status"]) == ("main", True, "OK")
    git("checkout", "-q", "--detach")
    off = hb.build(str(repo), now=NOW, tasks={}, resources=OK_RES)
    assert off["host_ref"] == f"DETACHED@{off['host_head_sha'][:7]}"
    assert (off["host_on_main"], off["status"]) == (False, "HOST_NOT_ON_MAIN")


def test_main_refuses_output_inside_host_repo(tmp_path):
    assert hb.main(["--host-repo", str(tmp_path), "--out", str(tmp_path / "x.json"), "--no-broker-history"]) == 2


def test_out_on_other_drive_is_not_inside_repo():
    import ntpath
    assert hb._is_inside(r"D:\hb\heartbeat.json", r"C:\host\repo", ntpath) is False
    assert hb._is_inside(r"C:\host\repo\status\hb.json", r"C:\host\repo", ntpath) is True
    assert hb._is_inside(r"C:\host\other\hb.json", r"C:\host\repo", ntpath) is False


def test_main_cross_drive_out_is_written_not_refused(tmp_path, monkeypatch, capsys):
    def cross_drive(paths):
        raise ValueError("Paths don't have the same drive")
    monkeypatch.setattr(hb.os.path, "commonpath", cross_drive)
    monkeypatch.setattr(hb, "build", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(hb, "write", lambda payload, out: out)
    out = str(tmp_path / "hb.json")
    assert hb.main(["--host-repo", "C:/repo", "--out", out, "--no-broker-history"]) == 0
    assert f"HEARTBEAT_WRITTEN {out}" in capsys.readouterr().out
    assert not (tmp_path / "x.json").exists()


TOOL_SHAPED = re.compile(
    r"^(readonly_[a-z_]+|mt5_[a-z_]*status|(get|place|modify|close|cancel)_[a-z_]+|order_(send|check)|position_[a-z_]+)$")


def test_mcp_tool_allowlist_is_exact_and_enforced():
    assert hb.MCP_TOOL_ALLOWLIST == {"readonly_get_orders", "readonly_get_deals",
                                     "readonly_get_account_info", "mt5_setup_status"}
    assert set(hb.HISTORY_TOOLS) <= hb.MCP_TOOL_ALLOWLIST
    tree = ast.parse((ROOT / "scripts" / "host" / "heartbeat.py").read_text(encoding="utf-8"))
    names = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and TOOL_SHAPED.match(n.value)}
    assert names, "tool-name scan found nothing; pattern drifted"
    assert names <= hb.MCP_TOOL_ALLOWLIST, f"non-allowlisted MCP tool names in heartbeat.py: {names - hb.MCP_TOOL_ALLOWLIST}"


MT5_ALLOWED = {"initialize", "shutdown", "terminal_info", "account_info", "history_orders_get",
               "history_deals_get", "last_error"}


def test_mt5_attribute_allowlist_is_exact_and_enforced():
    assert hb.MT5_ATTRIBUTE_ALLOWLIST == MT5_ALLOWED
    tree = ast.parse((ROOT / "scripts" / "host" / "heartbeat.py").read_text(encoding="utf-8"))
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "mt5"}
    assert used, "no mt5.* attribute found; scan drifted"
    assert used <= MT5_ALLOWED, f"non-allowlisted mt5 attributes: {used - MT5_ALLOWED}"
    for n in ast.walk(tree):          # no dynamic access and no direct import that could bypass the scan
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("getattr", "vars", "__import__"):
            assert not (n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == "mt5"), "dynamic mt5 access"
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names] + ([n.module] if isinstance(n, ast.ImportFrom) and n.module else [])
            assert "MetaTrader5" not in names, "import MetaTrader5 only via _host_common.import_mt5"


Order = namedtuple("Order", "time_setup magic")
Deal = namedtuple("Deal", "time type")


class FakeMt5:
    def __init__(self, init_ok=True, orders=(), deals=()):
        self.init_ok, self.orders, self.deals = init_ok, orders, deals
        self.calls, self.init_kwargs = [], None

    def initialize(self, **kw):
        self.calls.append("initialize")
        self.init_kwargs = kw
        return self.init_ok

    def shutdown(self):
        self.calls.append("shutdown")

    def last_error(self):
        return (-6, "Terminal: Authorization failed for account 12345678")

    def terminal_info(self):
        return namedtuple("T", "connected path")(True, r"C:\Program Files\MetaTrader 5")

    def account_info(self):
        return namedtuple("A", "login server")(12345678, "VTMarkets-Demo")

    def history_orders_get(self, lo, hi):
        return self.orders

    def history_deals_get(self, lo, hi):
        return self.deals


def _raw(t: dt.datetime) -> int:
    """UTC -> MT5 raw time (server wall-clock seconds), inverse of server_time_to_utc(_mt5_server_wall())."""
    wall = t.astimezone(NY).replace(tzinfo=None) + dt.timedelta(hours=SERVER_MINUS_NY_HOURS)
    return int(wall.replace(tzinfo=UTC).timestamp())


def _attach(monkeypatch, fake):
    monkeypatch.setattr(hb, "import_mt5", lambda: fake)
    monkeypatch.setattr(hb, "mt5_access_lock", contextlib.nullcontext)
    monkeypatch.delenv("MT5_TERMINAL_PATH", raising=False)


def test_attach_backend_counts_without_credentials_and_always_shuts_down(monkeypatch, tmp_path):
    inside, old = NOW - dt.timedelta(hours=1), NOW - dt.timedelta(hours=40)
    fake = FakeMt5(orders=(Order(_raw(inside), 21099), Order(_raw(inside), 0), Order(_raw(old), 0)),
                   deals=(Deal(_raw(inside), 0), Deal(_raw(inside), 2), Deal(_raw(old), 1)))
    _attach(monkeypatch, fake)
    out = hb.build(str(tmp_path), now=NOW, tasks={}, history=hb.attach_history, resources=OK_RES)
    h = out["broker_history_24h"]
    assert (h["source"], h["orders"], h["deals"], h["by_magic"], h["manual_or_zero_magic"]) == \
        ("LIVE_ATTACH", 2, 1, {"21099": 1}, 1)
    assert out["broker_order_calls"] == 2 and out["broker_history_error"] is None
    assert not {"login", "password", "server"} & set(fake.init_kwargs) and "path" not in fake.init_kwargs
    assert fake.calls == ["initialize", "shutdown"]
    text = json.dumps(out)
    assert "12345678" not in text and "VTMarkets" not in text                   # no login / server emitted


def test_attach_backend_failures_are_unknown_with_error_code(monkeypatch, tmp_path):
    for fake, err in ((FakeMt5(init_ok=False), "INITIALIZE_FAILED code=-6"),
                      (FakeMt5(orders=None), "HISTORY_READ_FAILED code=-6")):
        _attach(monkeypatch, fake)
        out = hb.build(str(tmp_path), now=NOW, tasks={}, history=hb.attach_history, resources=OK_RES)
        assert out["broker_history_24h"] == hb.UNKNOWN and out["broker_order_calls"] == hb.UNKNOWN
        assert out["broker_history_error"] == err and "12345678" not in json.dumps(out)
        assert fake.calls[-1] == "shutdown"
    monkeypatch.setattr(hb, "import_mt5", lambda: None)
    assert hb.attach_history(NOW) == {"error": "MT5_PACKAGE_MISSING"}
    fake = FakeMt5()
    _attach(monkeypatch, fake)
    monkeypatch.setenv("MT5_TERMINAL_PATH", r"C:\T\terminal64.exe")
    hb.attach_history(NOW)
    assert fake.init_kwargs["path"] == r"C:\T\terminal64.exe"                    # same path rule as the runners


def test_host_resources_thresholds_and_status(tmp_path):
    ok = hb.assess_resources(4000, {"C": 50.0, "D": 20.0})
    assert ok["status"] == "OK" and ok["thresholds"]["state"] == "PROPOSED_OWNER_CONFIRM"
    low = hb.assess_resources(800, {"C": 5.8, "D": 20.0})
    assert low["status"] == "DEGRADED_RESOURCES" and low["reasons"] == ["RAM<1200MB", "C:<10GB"]
    assert hb.assess_resources(hb.UNKNOWN, hb.UNKNOWN)["status"] == hb.UNKNOWN
    out = hb.build(str(tmp_path), now=NOW, tasks={}, resources=low)
    assert out["status"] == "DEGRADED_RESOURCES" and out["status_reasons"] == ["DEGRADED_RESOURCES"]
    live = hb.host_resources()                                                   # real call; shape only
    assert set(live) >= {"free_ram_mb", "free_disk_gb", "status", "thresholds"}
