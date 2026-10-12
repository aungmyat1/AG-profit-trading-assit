"""AGP-L3-0731 reproducer: attribute an FX branch decision revision (L3) failure to its cause.

Read-only, hermetic, off-host: recorded fixture only, no broker/network/MT5 call, no rule or
gate change. Drives the unchanged `scripts/asw_v112_logic_verification.py` harness internals
(load_candles / split / ticket / semantic) plus the frozen `strategy_engine.session` setup
functions, and records for one symbol x cycle x date:

  * the per-prefix engine output (decision/setup/direction/entry/stop/risk/signal time),
  * the first-emission semantic vs the full-window semantic and their differing fields,
  * the per-candle Entry-2 (sweep) and Entry-3 (range) qualification with risk distances,
  * one future-mutation replay exactly as the harness performs it.

Nothing here re-implements market logic: the per-candle rows are the frozen setup functions
called with a one-candle window, which yields the same first-qualifying decision the router
reaches when that candle is the first to qualify.

    python scripts/asw_v112_l3_repro_0731.py --symbol EURUSD --cycle ASIAN_LONDON \
        --date 2026-07-31 --dataset d60 --out PATH.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
if "MetaTrader5" not in sys.modules:                      # import-only Linux portability shim
    _spec = importlib.util.spec_from_file_location("l3_repro_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))

import scripts.asw_v112_logic_verification as h  # noqa: E402
from strategy_engine.session import reference_box as rb  # noqa: E402
from strategy_engine.session import setups

DATASETS = {"d60": "D60_SYMBOLS", "r2": "R2_SYMBOLS", "default": "SYMBOLS"}
ENTRY_BY_CYCLE = {"ASIAN_LONDON": "Asian", "LONDON_NEWYORK": "London"}


def sha256_file(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def _setup_row(decision) -> Dict[str, Any]:
    return {"setup": decision.setup_type.value if decision.setup_type else None,
            "regime": decision.regime.value if decision.regime else None,
            "decision_status": decision.decision_status.value,
            "reason_code": decision.reason_code,
            "direction": decision.direction.value if decision.direction else None,
            "entry_reference": decision.entry_reference, "stop_reference": decision.stop_reference,
            "risk_distance": decision.risk_distance,
            "signal_timestamp": decision.signal_timestamp.isoformat() if decision.signal_timestamp else None}


def per_candle(symbol: str, cycle: str, session, post, session_date: dt.date) -> List[Dict[str, Any]]:
    box = rb.build_reference_box(ENTRY_BY_CYCLE[cycle], session, h.CYCLES[cycle][1])
    rows = []
    for c in post:
        rows.append({
            "time": c.time.isoformat(), "open": c.open, "high": c.high, "low": c.low, "close": c.close,
            "box_high": box.session_high, "box_low": box.session_low,
            "entry_2_sweep": _setup_row(setups.entry_2_sweep(h.STRATEGY_ID, symbol, box, session_date, [c])),
            "entry_3_range": _setup_row(setups.entry_3_range(h.STRATEGY_ID, symbol, box, session_date, [c])),
        })
    return rows


def build(symbol: str, cycle: str, session_date: dt.date, dataset: str) -> Dict[str, Any]:
    saved = h.SYMBOLS
    h.SYMBOLS = {k: getattr(h, DATASETS[dataset])[k] for k in (symbol,)} if symbol != "EURUSD" else \
        {k: h.D60_SYMBOLS[k] for k in ("EURUSD",)}
    try:
        candles = h.load_candles(symbol)
        fixture = h.SYMBOLS[symbol]["fixture"]
        by_day: Dict[str, List[Any]] = {}
        for c in candles:
            by_day.setdefault(c.time.date().isoformat(), []).append(c)
        day = session_date.isoformat()
        w, now, session, post = h.split(by_day[day], cycle, session_date)
        prefixes = []
        for k in range(len(post) + 1):
            t = h.ticket(cycle, session_date, session, post[:k], now, symbol=symbol)
            prefixes.append({"k": k, "decision": t.get("decision"), "setup": t.get("setup"),
                             "direction": t.get("direction"), "entry": t.get("entry"),
                             "stop_loss": t.get("stop_loss"), "risk_distance": t.get("risk_distance"),
                             "signal_timestamp": t.get("signal_timestamp")})
        full_sem = h.semantic(h.ticket(cycle, session_date, session, post, now, symbol=symbol))
        first = next((p["k"] for p in prefixes if p["direction"] is not None), None)
        emission = None
        differing = None
        if first is not None:
            emission = h.semantic(h.ticket(cycle, session_date, session, post[:first], now, symbol=symbol))
            differing = {k: {"emission": emission.get(k), "full": full_sem.get(k)}
                         for k in sorted(set(emission) | set(full_sem)) if emission.get(k) != full_sem.get(k)}
        mutation = h.causality(cycle, session_date, session, post, now, __import__("random").Random(h.SEED), symbol)
        return {
            "schema": "AG_L3_DECISION_REVISION_REPRODUCER_V1",
            "authority": "none: logic evidence only; no registry, READY, demo, live or rule change",
            "strategy": f"{h.STRATEGY_ID}@{h.VERSION}", "contract_path": h.CANDIDATE,
            "contract_sha256": sha256_file(h.CANDIDATE),
            "symbol": symbol, "cycle": cycle, "session_date": day,
            "dataset": {"id": dataset, "fixture": fixture, "sha256": sha256_file(fixture)},
            "window": {"reference": [w["ref"][0].isoformat(), w["ref"][1].isoformat()],
                       "trade": [w["trade"][0].isoformat(), w["trade"][1].isoformat()],
                       "evaluated_at": now.isoformat(), "post_bars": len(post)},
            "prefixes": prefixes,
            "first_emission_prefix_k": first,
            "emission_semantic": emission, "full_semantic": full_sem,
            "differing_fields": differing,
            "causality": mutation,
            "per_candle": per_candle(symbol, cycle, session, post, session_date),
            "registry_modified": False, "demo_authorized": False, "live_authorized": False,
            "broker_calls": 0, "ORDER_API_CALLS": 0, "BROKER_MUTATION_COUNT": 0,
        }
    finally:
        h.SYMBOLS = saved


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--cycle", default="ASIAN_LONDON", choices=sorted(h.CYCLES))
    ap.add_argument("--date", required=True)
    ap.add_argument("--dataset", default="d60", choices=sorted(DATASETS))
    ap.add_argument("--out", help="write the reproducer JSON here")
    ap.add_argument("--contract", default=h.CANDIDATE, help="candidate contract path (default v1.1.2)")
    ap.add_argument("--version", default=h.VERSION, help="candidate version; must match the contract")
    args = ap.parse_args(argv)
    h.use_candidate(args.contract, args.version)
    report = build(args.symbol, args.cycle, dt.date.fromisoformat(args.date), args.dataset)
    if args.out:
        (ROOT / args.out).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / args.out).write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"{report['schema']} {report['strategy']} {report['symbol']}x{report['cycle']} {report['session_date']}")
    for row in report["per_candle"]:
        e2, e3 = row["entry_2_sweep"], row["entry_3_range"]
        if e2["decision_status"] == "VALID" or e3["decision_status"] == "VALID":
            print(f"  {row['time']} entry_2={e2['setup']}/{e2['reason_code']} risk={e2['risk_distance']} | "
                  f"entry_3={e3['setup']}/{e3['reason_code']} risk={e3['risk_distance']}")
    print(f"  first_emission_k={report['first_emission_prefix_k']} "
          f"future_mutation_mismatches={report['causality']['future_mutation_mismatches']}/"
          f"{report['causality']['future_mutations']} prefix_mismatches={report['causality']['prefix_mismatches']}")
    if report["differing_fields"]:
        print("  revised fields: " + ", ".join(report["differing_fields"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
