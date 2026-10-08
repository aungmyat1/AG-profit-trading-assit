"""DOCS-LIVE-3A host heartbeat: fixture logs/archives/history -> counts, UNKNOWN on unreadable sources."""
from __future__ import annotations

import ast
import datetime as dt
import re
import json
import subprocess
import sys
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


def _fetch(orders: str, deals: str):
    return lambda a, b: {"readonly_get_orders": orders, "readonly_get_deals": deals}


def test_counts_and_contract_fields(tmp_path):
    _fixture(tmp_path)
    out = hb.build(str(tmp_path), now=NOW, tasks={"AG-X": {"LastTaskResult": 0}})
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
    out = hb.build(str(tmp_path), now=NOW, tasks={}, history_fetch=_fetch(orders, deals))
    assert out["broker_history_24h"] == {"orders": 3, "deals": 2, "by_magic": {"21099": 1}, "manual_or_zero_magic": 2}
    assert out["broker_order_calls"] == 3
    text = json.dumps(out["broker_history_24h"])
    assert "EURUSD" not in text and "1.1" not in text                           # no symbols, tickets or prices


def test_broker_history_empty_unreachable_and_malformed(tmp_path):
    empty = hb.build(str(tmp_path), now=NOW, tasks={}, history_fetch=_fetch('""\r\n', '""\r\n'))
    assert empty["broker_history_24h"] == {"orders": 0, "deals": 0, "by_magic": {}, "manual_or_zero_magic": 0}
    assert empty["broker_order_calls"] == 0
    for fetch in (None, lambda a, b: None, _fetch("not,a,history\n1,2,3", '""')):
        out = hb.build(str(tmp_path), now=NOW, tasks={}, history_fetch=fetch)
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
    on = hb.build(str(repo), now=NOW, tasks={})
    assert (on["host_ref"], on["host_on_main"], on["status"]) == ("main", True, "OK")
    git("checkout", "-q", "--detach")
    off = hb.build(str(repo), now=NOW, tasks={})
    assert off["host_ref"] == f"DETACHED@{off['host_head_sha'][:7]}"
    assert (off["host_on_main"], off["status"]) == (False, "HOST_NOT_ON_MAIN")


def test_main_refuses_output_inside_host_repo(tmp_path):
    assert hb.main(["--host-repo", str(tmp_path), "--out", str(tmp_path / "x.json"), "--no-broker-history"]) == 2
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
