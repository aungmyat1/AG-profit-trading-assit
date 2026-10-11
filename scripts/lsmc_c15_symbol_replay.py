"""C15-LSMC: per-symbol L1-L6 replay of ST_LARGE_SMC_V1@1.1.0 on recorded VT MT5 bars (off-host, read-only).

Reuses the frozen engine (large_smc_watch.evaluate_snapshot) and the existing gate
(v1_tickets.lsmc_logic_gate L1-L4/L6). Nothing here changes a rule. Two lanes:

* operational: evaluate_snapshot exactly as shipped (includes the in-engine delivery gate,
  which needs the host-only owner threshold config/local/actionability_policy.yaml);
* signal: the same call with large_smc_watch.watch.gate_opportunity replaced by identity in
  this process only, so the pre-actionability OPPORTUNITY output can be checked (L2/L3).

Each scan feeds the host's rolling windows (scripts/host/live_candles_smoke.py COUNTS: D1 30,
H1 200, M5 300) of bars opened at or before the decision time, so the forming bar (with its
recorded future OHLC) is present and must be dropped by the engine (L1 truncation check).
Scans run at every M5 close once the H1/M5 windows are full. L5 follows OD1011-L5: PASS only
with accepted spread + commission evidence and a cost gate that applies it; otherwise WARN
naming the missing source. Alerts stay ARCHIVE_ONLY (WatchTracker archives to a temp dir).

    python scripts/lsmc_c15_symbol_replay.py --symbol BTCUSD [--out PATH.json] [--limit N]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
os.environ["AG_EVIDENCE_ROOT"] = str(ROOT)   # committed VT host captures only

if "MetaTrader5" not in sys.modules:   # import-only Linux shim (as scripts/lsmc_v110_logic_verification.py)
    _spec = importlib.util.spec_from_file_location("lsmc_gate_test_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))

import yaml  # noqa: E402

from host_evidence.symbol_metadata import load_record  # noqa: E402
from large_smc_watch import contract as C  # noqa: E402
from large_smc_watch import watch as W  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import lsmc_logic_gate as G  # noqa: E402
from v1_tickets.logic_gate import (  # noqa: E402
    NOT_APPLICABLE,
    PASS,
    WARN,
    _check,
    _gate,
)

DATASET_DIR = ROOT / "tests/fixtures/ccfd_v100/recorded_60d"
HOST_COUNTS = {"D1": 30, "H1": 200, "M5": 300}
FILES = ("d1", "h1", "m5", "d1_meta", "h1_meta", "m5_meta")
DETECTION_FILES = ("src/large_smc_watch/detect.py", "src/large_smc_watch/contract.py", "src/fx_discovery/features.py")
REAL_GATE = W.gate_opportunity


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(symbol: str):
    bars, spread = {}, {}
    for tf in ("D1", "H1", "M5"):
        rows = list(csv.DictReader((DATASET_DIR / f"{symbol}_{tf.lower()}.csv").open(encoding="utf-8")))
        bars[tf] = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]), float(r["open"]), float(r["high"]),
                           float(r["low"]), float(r["close"]), None) for r in rows]
        meta = list(csv.DictReader((DATASET_DIR / f"{symbol}_{tf.lower()}_meta.csv").open(encoding="utf-8")))
        spread[tf] = {dt.datetime.fromisoformat(r["timestamp_utc"]): float(r["spread_price"]) for r in meta
                      if r.get("spread_price")}
    return bars, spread


def window(bars, times, tf, now):
    j = bisect.bisect_right(times[tf], now)   # opened at or before now: includes the forming bar
    return bars[tf][max(0, j - HOST_COUNTS[tf]):j]


def identity(spec_path: Path) -> dict:
    registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))["strategies"]
    entry = registry[C.STRATEGY_ID]
    contract_sha = sha256(spec_path)
    engine = G.engine_sha256()
    return {
        "strategy": f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION}",
        "contract_path": str(spec_path.relative_to(ROOT)), "contract_sha256": contract_sha,
        "registry_contract_sha256": entry.get("contract_sha256"),
        "contract_matches_registry": contract_sha == entry.get("contract_sha256"),
        "engine_sha256": engine, "registry_engine_sha256": entry.get("engine_sha256"),
        "engine_matches_registry": engine == entry.get("engine_sha256"),
        "engine_file_sha256": {f: G.file_sha256(f) for f in G.ENGINE_FILES},
        "detection_file_sha256": {f: G.file_sha256(f) for f in DETECTION_FILES},
        "dependency_sha256": {f: G.file_sha256(f) for f in G.DEPENDENCY_FILES},
        "eurusd_detection_record": (entry.get("detection_logic_verification") or {}).get("identity"),
    }


def l5_evidence(opp: dict, now: dt.datetime, spread: dict, host_spread: float) -> dict:
    """OD1011-L5. Records every available cost source; PASS needs all of them plus an applying gate."""
    bar_spread = spread["M5"].get(now - dt.timedelta(minutes=5))
    conservative = max(x for x in (bar_spread, host_spread) if x is not None) if (bar_spread or host_spread) else None
    entry, stop = opp.get("entry_reference"), opp.get("stop_c10")
    risk = abs(entry - stop) if entry is not None and stop is not None else None
    checks = [
        _check("L5.spread_source", "conservative spread = max(recorded M5 bar spread, host symbol_info snapshot)",
               conservative, None, PASS if conservative is not None else WARN,
               "VT recorded MqlRates spread + host capture" if conservative is not None else "SPREAD NOT AVAILABLE"),
        _check("L5.stop_distance", "stop distance for cost_in_R", risk, None, PASS if risk else WARN,
               "" if risk else f"STOP_NOT_DEFINED:{opp.get('stop_reason') or 'NO_STOP'}"),
        _check("L5.commission_R", "OD1011-COMMISSION bound to the runtime account", None, None, WARN,
               "COMMISSION_UNBOUND_OFF_HOST: binding needs config/local/owner_ticket.yaml account_login"),
        _check("L5.cost_gate_applied", "a cost gate applies spread+commission (0.10R warn / 0.25R block)", None,
               None, WARN, "NO_COST_GATE_IN_LSMC_1_1_0_ALERT_PATH"),
    ]
    return _gate("L5", checks, advisory=True)


def run(symbol: str, limit: int | None = None) -> dict:
    spec = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))
    bars, spread = load(symbol)
    times = {tf: [b.time for b in v] for tf, v in bars.items()}
    record = load_record(symbol)
    point = (record or {}).get("fields", {}).get("point")
    host_spread = (record["fields"]["spread"] * point) if record and point else None
    capture = json.loads((DATASET_DIR / "capture_report.json").read_text(encoding="utf-8"))

    m5 = bars["M5"]
    first = next(i for i, b in enumerate(m5) if b.time + dt.timedelta(minutes=5) >= max(
        bars["H1"][HOST_COUNTS["H1"]].time, m5[HOST_COUNTS["M5"]].time))
    scan_idx = range(first, len(m5))
    if limit:
        scan_idx = scan_idx[:limit]

    windows = ("full_d1", "short_d1")
    gate_counts = {w: {g: Counter() for g in ("L1", "L2", "L3", "L4", "L5", "L6")} for w in windows}
    states = {w: {"signal": Counter(), "operational": Counter()} for w in windows}
    reasons_operational = {w: Counter() for w in windows}
    scan_counts = Counter()
    failures, opportunities, d1_short = [], {}, 0
    snaps = {"signal": [], "operational": []}
    for i in scan_idx:
        now = m5[i].time + dt.timedelta(minutes=5)
        case = {"case_id": f"{symbol}:{now.isoformat()}", "symbol": symbol, "now": now,
                "fixture": str(DATASET_DIR.relative_to(ROOT)), "classification": "VT_RECORDED",
                "D1": window(bars, times, "D1", now), "H1": window(bars, times, "H1", now),
                "M5": window(bars, times, "M5", now)}
        d1_short += len(case["D1"]) < HOST_COUNTS["D1"]
        cls = "full_d1" if len(case["D1"]) >= HOST_COUNTS["D1"] else "short_d1"
        scan_counts[cls] += 1
        W.gate_opportunity = REAL_GATE
        op = W.evaluate_snapshot(symbol, case["D1"], case["H1"], case["M5"], now)
        states[cls]["operational"][op.state] += 1
        if op.state == "REJECTED":
            reasons_operational[cls][op.reason_codes[0]] += 1
        snaps["operational"].append(op)
        W.gate_opportunity = lambda snap, price: snap
        res = G.evaluate_case(spec, case)
        snap = W.evaluate_snapshot(symbol, case["D1"], case["H1"], case["M5"], now)
        snaps["signal"].append(snap)
        states[cls]["signal"][res["state"]] += 1
        if res["state"] == "OPPORTUNITY":
            res["gates"]["L5"] = l5_evidence(snap.opportunity, now, spread, host_spread)
            res["gate_status"]["L5"] = res["gates"]["L5"]["status"]
            o = snap.opportunity
            key = o.get("opportunity_id") or o.get("reference_id") or f"{o['direction']}@{o['entry_reference']}"
            opportunities.setdefault(key, {
                "first_seen": now.isoformat(), "direction": o["direction"], "entry_reference": o["entry_reference"],
                "stop_c10": o.get("stop_c10"), "stop_reason": o.get("stop_reason"), "target_c11": o.get("target_c11"),
                "target_reason": o.get("target_reason"), "sweep_extreme": o.get("sweep_extreme"),
                "expires_at": o.get("expires_at"), "scans": 0, "first_seen_window": cls,
                "operational_state": op.state, "operational_reason": (op.reason_codes or [None])[0]})
            opportunities[key]["scans"] += 1
        for g, status in res["gate_status"].items():
            gate_counts[cls][g][status] += 1
        if res["blocking_failures"] and len(failures) < 50:
            failures.append({"case_id": res["case_id"], "state": res["state"], "failures": res["blocking_failures"],
                             "gates": {g: res["gates"][g] for g in res["blocking_failures"]}})
    W.gate_opportunity = REAL_GATE

    parity = streaming_parity(symbol, snaps)
    scans = len(scan_idx)
    def l1_l4_pass(w):
        return all(gate_counts[w][g][PASS] + gate_counts[w][g][NOT_APPLICABLE] == scan_counts[w]
                   for g in ("L1", "L2", "L3", "L4"))
    blocking_pass = scan_counts["full_d1"] > 0 and all(l1_l4_pass(w) for w in windows)
    full_opps = [o for o in opportunities.values() if o["first_seen_window"] == "full_d1"]
    directions = Counter(o["direction"] for o in opportunities.values())
    stop_defined = sum(1 for o in opportunities.values() if o["stop_c10"] is not None)
    return {
        "schema": "AGP_C15_LSMC_SYMBOL_REPLAY_V1",
        "mission": "C15-LSMC (docs/governance/AGP_C15_THREE_STRATEGY_LOGIC_FIRST_2026-10-11.md, PR #156)",
        "symbol": symbol,
        "identity": identity(G.CONTRACT_PATH),
        "dataset": {
            "path": str(DATASET_DIR.relative_to(ROOT)), "server": capture.get("server"),
            "sha256": {f"{symbol}_{name}.csv": sha256(DATASET_DIR / f"{symbol}_{name}.csv") for name in FILES},
            "capture_report_sha256": sha256(DATASET_DIR / "capture_report.json"),
            "bars": {tf: len(v) for tf, v in bars.items()},
            "first_bar_utc": m5[0].time.isoformat(), "last_bar_utc": m5[-1].time.isoformat(),
        },
        "replay": {
            "host_window_counts": HOST_COUNTS, "cadence": "every M5 close",
            "first_scan_utc": (m5[scan_idx[0]].time + dt.timedelta(minutes=5)).isoformat(),
            "last_scan_utc": (m5[scan_idx[-1]].time + dt.timedelta(minutes=5)).isoformat(),
            "scans": scans, "scans_full_d1_window": scan_counts["full_d1"],
            "scans_with_short_d1_window": d1_short,
            "headline_scope": "full_d1 scans only (30 D1 bars, as on the host); short_d1 scans reported separately",
            "d1_window_note": "D1 feeds only the informational d1_context (watch.evaluate_snapshot); bias is H1.",
        },
        "spread_provenance": {
            "recorded_bar_spread": "MqlRates spread per bar (VT MT5, server " + str(capture.get("server")) + ")",
            "m5_bars_with_spread": len(spread["M5"]), "m5_bars": len(m5),
            "host_capture_sha256": (record or {}).get("sha256"), "host_capture_server": (record or {}).get("server"),
            "host_snapshot_spread_price": host_spread, "point": point,
            "rule": "conservative spread = max(bar spread, host snapshot spread); bar spread alone is a lower bound",
        },
        "verdict": "NOT_VERIFIED",
        "verdict_reasons": ["L5 WARN (OD1011-L5: no stop distance, commission unbound off-host, no cost gate)",
                            "stop geometry NOT_APPLICABLE: C10_PIP_SIZE_NOT_EVIDENCED for " + symbol,
                            f"operational REJECT_NO_STOP on {sum(r['REJECT_NO_STOP'] for r in reasons_operational.values())}"
                            f"/{sum(states[w]['signal']['OPPORTUNITY'] for w in windows)} OPPORTUNITY scans"],
        "states": {k: dict(v) for k, v in states["full_d1"].items()},
        "operational_rejection_reasons": dict(reasons_operational["full_d1"]),
        "gate_status_counts": {g: dict(c) for g, c in gate_counts["full_d1"].items()},
        "short_d1_window": {"scans": scan_counts["short_d1"],
                            "states": {k: dict(v) for k, v in states["short_d1"].items()},
                            "operational_rejection_reasons": dict(reasons_operational["short_d1"]),
                            "gate_status_counts": {g: dict(c) for g, c in gate_counts["short_d1"].items()},
                            "blocking_L1_L4_pass": l1_l4_pass("short_d1")},
        "blocking_L1_L4_pass_full_d1": l1_l4_pass("full_d1"),
        "blocking_L1_L4_pass": blocking_pass,
        "blocking_failures_sample": failures,
        "opportunities": {"distinct": len(opportunities), "by_direction": dict(directions),
                          "distinct_full_d1": len(full_opps),
                          "by_direction_full_d1": dict(Counter(o["direction"] for o in full_opps)),
                          "with_c10_stop": stop_defined, "items": opportunities},
        "streaming_parity": parity,
        "delivery_mode": W.DELIVERY_MODE,
        "authority": "none: logic evidence only; no registry, READY, demo or live change",
    }


def _sig(s) -> str:
    return json.dumps(G._payload(s), sort_keys=True, default=str)


def streaming_parity(symbol: str, snaps: dict) -> dict:
    """WatchTracker fed scan-by-scan (streaming) vs the same replay cut at prefixes: every event at or
    before the cut is identical. Archive-only, temp dir."""
    out = {}
    for lane, seq in snaps.items():
        def replay(upto):
            with tempfile.TemporaryDirectory() as tmp:
                tracker = W.WatchTracker(str(Path(tmp) / "state.json"), str(Path(tmp) / "archive"))
                events = []
                for s in seq[:upto]:
                    events += [json.dumps({k: v for k, v in e.__dict__.items() if k != "transition_id"},
                                          sort_keys=True, default=str) for e in tracker.poll(s)]
                return events
        full = replay(len(seq))
        cuts = sorted({len(seq) * k // 8 for k in range(1, 8)})
        mism = 0
        for cut in cuts:
            prefix = replay(cut)
            mism += prefix != full[:len(prefix)]
        out[lane] = {"events": len(full), "prefix_cuts": cuts, "prefix_mismatches": mism,
                     "verdict": PASS if mism == 0 else "FAIL"}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    report = run(args.symbol, args.limit)
    text = json.dumps(report, indent=1, sort_keys=True, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("states", "gate_status_counts", "blocking_L1_L4_pass",
                                             "streaming_parity")}, default=str))
    return 0 if report["blocking_L1_L4_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
