"""Apply the frozen VT EURUSD-VIP parity + spread-to-dev-stop screen preregistration.

    python scripts/research/analyze_vt_vip_parity_screen.py [--write]

Reads only: the preregistration YAML, parity captures under
artifacts/validation/VT_EURUSD_VIP_PARITY_V1/, and (only if parity is acceptable) the
preregistered development-stop source. Order is enforced: parity -> spread authority ->
screen. If parity is not PASS / PASS_WITH_KNOWN_DIFFERENCES the development file is never
opened. Outcome fields of the development file are never read. No MT5, no network.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/PREREGISTRATION.yaml"
CAPTURE_ROOT = REPO / "artifacts/validation/VT_EURUSD_VIP_PARITY_V1"
REPORT_DIR = REPO / "artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1"
PLAIN, VIP = "EURUSD", "EURUSD-VIP"
PIP = 0.0001
SESSIONS = ("POST_ASIAN", "POST_LONDON")


def _pct(xs: List[float], q: float) -> float:
    return float(np.percentile(np.asarray(xs, dtype=float), q, method="linear"))


def describe(xs: List[float]) -> Dict:
    if not xs:
        return {"N": 0}
    return {"N": len(xs), "min": min(xs), "median": _pct(xs, 50), "mean": float(np.mean(xs)),
            "p75": _pct(xs, 75), "p90": _pct(xs, 90), "p95": _pct(xs, 95), "p99": _pct(xs, 99), "max": max(xs),
            "zero_fraction": sum(x == 0 for x in xs) / len(xs)}


def load_captures(root: Path = CAPTURE_ROOT) -> List[Dict]:
    caps = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = {}
        for s in (PLAIN, VIP):
            raw = (manifest_path.parent / f"{s}_raw.jsonl").read_bytes()
            if hashlib.sha256(raw).hexdigest() != m["files"][s]["sha256"]:
                raise ValueError(f"raw hash mismatch: {manifest_path.parent.name}/{s}")
            rows[s] = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        m1 = json.loads((manifest_path.parent / "m1_bars.json").read_text(encoding="utf-8"))
        caps.append({"manifest": m, "rows": rows, "m1": m1})
    return caps


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=0.0)
        except (TypeError, ValueError):
            return False
    return a == b


def _paired(cap: Dict):
    by_round = {s: {r["round"]: r for r in cap["rows"][s]} for s in (PLAIN, VIP)}
    for k in sorted(set(by_round[PLAIN]) & set(by_round[VIP])):
        a, b = by_round[PLAIN][k], by_round[VIP][k]
        if a["validity"] == "VALID" and b["validity"] == "VALID":
            yield a, b


def evaluate_parity(caps: List[Dict], crit: Dict) -> Dict:
    static_mismatch, known_diff = set(), set()
    mid, bid_gt, ask_gt, lag, close_d, hl_d = [], 0, 0, [], [], []
    availability, per_session_complete = [], {s: 0 for s in SESSIONS}
    for cap in caps:
        m = cap["manifest"]
        snap = m["symbol_metadata"]["start"]
        for f in crit["required_static_equal"]:
            if not _same(snap[PLAIN].get(f), snap[VIP].get(f)):
                static_mismatch.add(f)
        for f in crit["known_difference_fields"]:
            if not _same(snap[PLAIN].get(f), snap[VIP].get(f)):
                known_diff.add(f)
        planned = m["sampling"]["rounds_planned"]
        for s in (PLAIN, VIP):
            valid = sum(r["validity"] == "VALID" for r in cap["rows"][s])
            availability.append({"capture_id": m["capture_id"], "symbol": s, "valid_fraction": valid / planned})
        pairs = list(_paired(cap))
        for a, b in pairs:
            mid.append(abs((b["bid"] + b["ask"]) / 2 - (a["bid"] + a["ask"]) / 2) / PIP)
            bid_gt += b["bid"] > a["bid"]
            ask_gt += b["ask"] > a["ask"]
            lag.append(abs(b["tick_time_msc_broker_clock"] - a["tick_time_msc_broker_clock"]))
        if len(pairs) >= 120 and m["requested_session"] in per_session_complete \
                and m["session_classification"] == [m["requested_session"]]:
            per_session_complete[m["requested_session"]] += 1
        bars = {s: {b["open_utc"]: b for b in cap["m1"].get(s, [])} for s in (PLAIN, VIP)}
        for t in sorted(set(bars[PLAIN]) & set(bars[VIP])):
            a, b = bars[PLAIN][t], bars[VIP][t]
            close_d.append(abs(b["close"] - a["close"]) / PIP)
            hl_d += [abs(b["high"] - a["high"]) / PIP, abs(b["low"] - a["low"]) / PIP]

    def ok(xs, med, p95):
        return bool(xs) and _pct(xs, 50) <= med and _pct(xs, 95) <= p95

    pc, mc = crit["price"], crit["m1"]
    checks = {
        "minimum_evidence": all(per_session_complete[s] >= 1 for s in SESSIONS),
        "static": not static_mismatch,
        "price": ok(mid, 0.2, 0.5),
        "m1_close": ok(close_d, 0.2, 0.5),
        "m1_high_low": ok(hl_d, 0.3, 1.0),
        "availability": bool(availability) and all(a["valid_fraction"] >= 0.95 for a in availability),
    }
    if not checks["minimum_evidence"]:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif not all(checks.values()):
        verdict = "FAIL"
    else:
        verdict = "PASS_WITH_KNOWN_DIFFERENCES" if known_diff else "PASS"
    n = len(mid)
    return {
        "EURUSD_VIP_PARITY": verdict,
        "criteria_source": {"price_pass": pc["pass"], "m1_close_pass": mc["close_diff_pips_pass"],
                            "m1_high_low_pass": mc["high_low_diff_pips_pass"]},
        "checks": checks,
        "complete_captures_per_session": per_session_complete,
        "static_mismatch_fields": sorted(static_mismatch),
        "known_difference_fields": sorted(known_diff),
        "mid_diff_pips": describe(mid),
        "m1_close_diff_pips": describe(close_d),
        "m1_high_low_diff_pips": describe(hl_d),
        "descriptive": {"paired_rounds": n, "vip_bid_above_plain_fraction": bid_gt / n if n else None,
                        "vip_ask_above_plain_fraction": ask_gt / n if n else None,
                        "tick_time_msc_abs_lag": describe(lag)},
        "availability": availability,
    }


def vip_spread_distributions(caps: List[Dict]) -> Dict:
    pooled = {s: [] for s in SESSIONS}
    days = {s: set() for s in SESSIONS}
    for cap in caps:
        for r in cap["rows"][VIP]:
            if r["validity"] == "VALID" and r["session_classification"] in pooled:
                pooled[r["session_classification"]].append(r["spread_pips"])
                days[r["session_classification"]].add(r["timestamp_utc"][:10])
    return {s: {**describe(pooled[s]), "distinct_days": len(days[s]),
                "reported_as": "INITIAL" if len(days[s]) < 5 else "FULL"} for s in SESSIONS}


def run_screen(dev_path: Path, dev_sha256: str, dists: Dict, threshold: float) -> Dict:
    raw = dev_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != dev_sha256:
        raise ValueError("development source hash mismatch")
    obs = json.loads(raw)["observations"]
    population, excluded = [], 0
    for o in obs:   # only cycle, risk_distance and identity are read; outcome fields are not
        rd = o.get("risk_distance")
        if o.get("cycle") not in SESSIONS or not isinstance(rd, (int, float)) or not math.isfinite(rd) or rd <= 0:
            excluded += 1
            continue
        population.append({"opportunity_id": o.get("opportunity_id"), "session": o["cycle"], "stop_pips": rd / PIP})
    scenarios = {}
    for name, key in (("median", "median"), ("p90", "p90"), ("p95", "p95")):
        per = {}
        for sess in SESSIONS + ("COMBINED",):
            pop = [p for p in population if sess == "COMBINED" or p["session"] == sess]
            passes = [dists[p["session"]][key] / p["stop_pips"] <= threshold for p in pop]
            per[sess] = {"N": len(pop), "pass": sum(passes), "pass_rate": sum(passes) / len(pop) if pop else None}
        scenarios[name] = {"spread_pips": {s: dists[s][key] for s in SESSIONS},
                           "implied_min_stop_pips": {s: dists[s][key] / threshold for s in SESSIONS},
                           "pass": per}
    return {"population": len(population), "excluded": excluded, "threshold": threshold, "scenarios": scenarios}


def analyze(prereg_path: Path = PREREG, capture_root: Path = CAPTURE_ROOT, repo: Path = REPO) -> Dict:
    prereg = yaml.safe_load(prereg_path.read_text(encoding="utf-8"))
    threshold = prereg["owner_decision"]["max_friction_to_risk"]
    caps = load_captures(capture_root)
    parity = evaluate_parity(caps, prereg["parity_criteria"])
    report = {
        "schema": "AG_VT_VIP_PARITY_SPREAD_SCREEN_REPORT_V1",
        "screen_id": prereg["screen_id"],
        "preregistration_sha256": hashlib.sha256(prereg_path.read_bytes()).hexdigest(),
        "MAX_FRICTION_TO_RISK": threshold,
        "captures": [c["manifest"]["capture_id"] for c in caps],
        "parity": parity,
        "boundary": prereg["boundary"],
        "COMMISSION_STATUS": "UNKNOWN", "SLIPPAGE_STATUS": "UNKNOWN/INSUFFICIENT_SAMPLE",
        "SEALED_OOS_ECONOMIC_ACCESS": "NO",
        "authority": prereg["authority"],
    }
    if parity["EURUSD_VIP_PARITY"] not in ("PASS", "PASS_WITH_KNOWN_DIFFERENCES"):
        report["spread_authority"] = "NOT_ESTABLISHED"
        report["SPREAD_TO_DEV_STOP_R_SCREEN"] = "NOT_EVALUATED_PARITY_" + parity["EURUSD_VIP_PARITY"]
        return report
    dists = vip_spread_distributions(caps)
    report["spread_authority"] = "EURUSD-VIP"
    report["vip_spread_pips"] = dists
    if any(dists[s]["N"] == 0 for s in SESSIONS):
        report["SPREAD_TO_DEV_STOP_R_SCREEN"] = "NOT_EVALUATED_NO_SPREAD_EVIDENCE"
        return report
    src = prereg["screen"]["development_source"]
    report["screen"] = run_screen(repo / src["path"], src["sha256"], dists, threshold)
    report["SPREAD_TO_DEV_STOP_R_SCREEN"] = "EVALUATED"
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write a write-once timestamped report")
    args = ap.parse_args(argv)
    report = analyze()
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    print(text)
    if args.write:
        path = REPORT_DIR / ("SCREEN_REPORT_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        with open(path, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"written {path.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
