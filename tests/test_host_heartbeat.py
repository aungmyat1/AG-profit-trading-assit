"""DOCS-LIVE-3A host heartbeat: fixture logs -> counts, UNKNOWN on missing/unlogged sources."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))

import heartbeat as hb  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=UTC)          # Thursday
T = NOW - dt.timedelta(hours=4)                             # 08:00Z, inside the ASIAN_LONDON trade window
EURUSD_READY = "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=READY reason=- ARCHIVED"


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


def test_counts_and_contract_fields(tmp_path):
    _fixture(tmp_path)
    out = hb.build(str(tmp_path), now=NOW, tasks={"AG-X": {"LastTaskResult": 0}})
    al = out["last_24h"]["fx_by_window"]["ASIAN_LONDON"]
    assert (al["READY"], al["STALE"], al["SPREAD_TOO_WIDE"], al["errors"]) == (1, 1, 1, 1)
    assert out["last_24h"]["runner_errors"]["fx"]["TIMEOUT"] == 1
    assert out["observed_at_utc"] == NOW.isoformat() and out["mt5_connected"]["value"] is True
    assert out["host_head_sha"] == hb.UNKNOWN                                   # tmp dir is not a git repo
    assert "server" not in json.dumps({k: v for k, v in out.items() if k != "execution_paths"}).lower()
    assert not any(m.startswith("ASIAN_LONDON:2026-10-08") for m in out["missed_windows"])
    assert "LONDON_NEWYORK:2026-10-07" in out["missed_windows"]


def test_missing_log_is_unknown(tmp_path):
    _log(tmp_path, "ag_v1_fx", [(T, EURUSD_READY)])
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["sources"]["ag_v1_lsmc.log"]["status"] == "MISSING"
    assert out["last_24h"]["lsmc_states"] == hb.UNKNOWN
    assert out["last_24h"]["runner_errors"]["crypto"] == hb.UNKNOWN
    assert out["duplicates"]["telegram_same_ref_sends"] == hb.UNKNOWN          # no delivery journal
    nothing = hb.build(str(tmp_path / "absent"), now=NOW, tasks=hb.UNKNOWN)
    assert nothing["last_24h"]["fx_by_window"] == hb.UNKNOWN
    assert nothing["missed_windows"] == hb.UNKNOWN
    assert nothing["observed_broker_order_calls"] == hb.UNKNOWN
    assert nothing["mt5_connected"]["value"] == hb.UNKNOWN


def test_stale_log_is_flagged_and_mt5_status_unknown(tmp_path):
    old = NOW - dt.timedelta(hours=5)
    _log(tmp_path, "ag_v1_fx", [(old, "FX EURUSD (EURUSD-VIP) ASIAN_LONDON data=FRESH decision=NO_TRADE reason=x")])
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["sources"]["ag_v1_fx.log"]["status"] == "STALE"
    assert out["mt5_connected"]["value"] == hb.UNKNOWN                          # newest MT5 line is 5 h old


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


def test_unlogged_execution_path_forces_unknown(tmp_path):
    _log(tmp_path, "ag_v1_fx", [(T, EURUSD_READY)])
    out = hb.build(str(tmp_path), now=NOW, tasks={})
    assert out["observed_broker_order_calls"] == 0
    assert out["broker_order_calls"] == hb.UNKNOWN                              # real path list has unlogged entries
    all_logged = [{"path": "p", "order_capable": True, "logged": True}]
    assert hb.broker_order_calls(0, all_logged) == 0
    assert hb.broker_order_calls(0, all_logged + [{"path": "q", "order_capable": True, "logged": False}]) == hb.UNKNOWN
    assert hb.broker_order_calls(hb.UNKNOWN, all_logged) == hb.UNKNOWN


def test_main_refuses_output_inside_host_repo(tmp_path):
    assert hb.main(["--host-repo", str(tmp_path), "--out", str(tmp_path / "x.json")]) == 2
    assert not (tmp_path / "x.json").exists()
