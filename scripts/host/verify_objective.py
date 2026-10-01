"""Verify the complete six-instrument host objective before installing schedules.

This is a repository/host-evidence preflight; it performs no network, MT5, Telegram, or
broker operation.  The Windows-only live connection is verified separately by
``diagnose_mt5.py``.  Exit 0 means every required ticket/watch/schedule binding is
present and internally consistent.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

HOST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOST_DIR.parent.parent
for path in (str(REPO_ROOT), str(REPO_ROOT / "src"), str(HOST_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

# smartmoneyconcepts prints a promotional banner during the strategy import.  A preflight
# must keep --json output valid and deterministic.
with contextlib.redirect_stdout(io.StringIO()):
    import live_candles_smoke as runner  # noqa: E402
    from host_evidence.symbol_metadata import SWAP_FIELDS, load_record  # noqa: E402
    from large_smc_watch import contract as lsmc  # noqa: E402
    from strategy_engine import load_strategy  # noqa: E402
    from v1_tickets import crypto, fx  # noqa: E402

import yaml  # noqa: E402

FX_MAJORS = ("EURUSD", "GBPUSD", "USDJPY")
GOLD = ("XAUUSD",)
CRYPTO = ("BTCUSDT", "ETHUSDT")
WATCH_UNIVERSE = FX_MAJORS + GOLD + CRYPTO
EXPECTED_BROKERS = {
    "EURUSD": "EURUSD-VIP", "GBPUSD": "GBPUSD-VIP", "USDJPY": "USDJPY-VIP",
    "XAUUSD": "XAUUSD-VIP", "BTCUSD": "BTCUSD", "ETHUSD": "ETHUSD",
}
EXPECTED_TASKS = {
    "AG-V1-FX-Cycles": "fx",
    "AG-V1-Crypto-Daily": "crypto",
    "AG-V1-LSMC-Watch": "lsmc",
}


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def verify(root: Path = REPO_ROOT) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_check(
        "fx_ticket_universe",
        tuple(runner.FX_MAJORS) == FX_MAJORS and tuple(runner.FX_METALS) == GOLD
        and tuple(runner.fx_symbols()) == FX_MAJORS + GOLD
        and tuple(fx.V1_FX_SYMBOLS) == FX_MAJORS + GOLD,
        f"majors={list(FX_MAJORS)} gold={list(GOLD)}",
    ))
    checks.append(_check(
        "fx_cycles", tuple(fx.V1_CYCLES) == ("ASIAN_LONDON", "LONDON_NEWYORK"),
        f"cycles={list(fx.V1_CYCLES)}",
    ))
    strategy = load_strategy(fx.STRATEGY_PATH)
    strategy_instruments = tuple(strategy.instruments)
    checks.append(_check(
        "fx_strategy_coverage", all(symbol in strategy_instruments for symbol in FX_MAJORS + GOLD),
        f"strategy={strategy.strategy_id}@{strategy.version} instruments={list(strategy_instruments)}",
    ))

    metadata_detail = []
    metadata_ok = True
    for canonical, broker in EXPECTED_BROKERS.items():
        record = load_record(canonical)
        ok = bool(record and record.get("broker_symbol") == broker and record.get("trade_mode") == "FULL"
                  and "Demo" in str(record.get("server", "")))
        if canonical in ("BTCUSD", "ETHUSD") and record:
            ok = ok and all(record.get("fields", {}).get(field) is not None for field in SWAP_FIELDS)
        metadata_ok = metadata_ok and ok
        metadata_detail.append(f"{canonical}->{broker}:{'OK' if ok else 'MISSING_OR_INVALID'}")
    checks.append(_check("host_symbol_metadata", metadata_ok, ", ".join(metadata_detail)))

    cfg = crypto.load_ticket_config(crypto.ACTIVE_CONFIG, str(root))
    crypto_map = cfg.get("venue", {}).get("symbols", {})
    checks.append(_check(
        "crypto_daily_tickets",
        tuple(crypto.V1_CRYPTO_SYMBOLS) == CRYPTO and cfg.get("venue", {}).get("kind") == "MT5"
        and crypto_map == {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"},
        f"config={cfg.get('config_id')}@v{cfg.get('version')} status={cfg.get('status')} symbols={crypto_map}",
    ))

    strategy_yaml = yaml.safe_load((root / "strategies" / "ST_LARGE_SMC_V1_1_1_0.yaml").read_text(encoding="utf-8"))
    checks.append(_check(
        "large_smc_watch_universe",
        tuple(lsmc.V1_SYMBOLS) == WATCH_UNIVERSE
        and tuple(strategy_yaml.get("instruments", ())) == WATCH_UNIVERSE
        and strategy_yaml.get("status") == "SHADOW_ALERTS_ONLY",
        f"symbols={list(lsmc.V1_SYMBOLS)} alert_levels={lsmc.ALERT_LEVEL}",
    ))

    install = (root / "scripts" / "host" / "install_tasks.ps1").read_text(encoding="utf-8")
    uninstall = (root / "scripts" / "host" / "uninstall_tasks.ps1").read_text(encoding="utf-8")
    schedule_ok = all(name in install and name in uninstall and f"Mode = '{mode}'" in install
                      for name, mode in EXPECTED_TASKS.items())
    schedule_ok = schedule_ok and "verify_tasks.ps1" in install and "MultipleInstances IgnoreNew" in install
    checks.append(_check(
        "scheduled_tasks", schedule_ok,
        ", ".join(f"{name}:{mode}" for name, mode in EXPECTED_TASKS.items()),
    ))

    delivery = yaml.safe_load((root / "config" / "ticket_delivery.yaml").read_text(encoding="utf-8"))
    checks.append(_check(
        "safe_delivery_default", delivery.get("mode") == "ARCHIVE_ONLY",
        f"mode={delivery.get('mode')} (Telegram remains host-local opt-in)",
    ))

    failures = [item["check"] for item in checks if item["status"] == "FAIL"]
    return {
        "schema": "AG_HOST_OBJECTIVE_PREFLIGHT_V1",
        "objective": {
            "fx_majors": list(FX_MAJORS), "gold": list(GOLD), "crypto": list(CRYPTO),
            "watch_universe": list(WATCH_UNIVERSE),
            "cycles": list(fx.V1_CYCLES),
        },
        "checks": checks,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "live_mt5": "NOT_CHECKED_RUN_DIAGNOSE_MT5_ON_WINDOWS_HOST",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = verify()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["checks"]:
            print(f"[{item['status']:<4}] {item['check']}: {item['detail']}")
        print(f"RESULT: {report['result']}")
        print(f"LIVE_MT5: {report['live_mt5']}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
