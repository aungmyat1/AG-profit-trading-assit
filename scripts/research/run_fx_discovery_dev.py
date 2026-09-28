"""Single development run of the three FX_DISCOVERY_V1 families (IN_SAMPLE / DEVELOPMENT only).

    python scripts/research/run_fx_discovery_dev.py

Verifies both development dataset hashes and refuses anything else (SEALED_OOS is never
read). It evaluates each ledger family once and applies the pre-registered selection
criteria. The evidence file is write-once.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import random
import statistics
import sys
from collections import Counter
from dataclasses import asdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))
os.chdir(REPO)

import yaml  # noqa: E402

from fx_discovery.families import FAMILIES, Market  # noqa: E402
from fx_discovery.resolver import RESOLVED, resolve  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

LEDGER = "config/research/FX_DISCOVERY_V1_HYPOTHESIS_LEDGER.yaml"
OUT = "artifacts/research/FX_DISCOVERY_V1/DEVELOPMENT_RUN_V1.json"
UTC = dt.timezone.utc


def sha(path, lf=False):
    data = open(path, "rb").read()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if lf else data).hexdigest()


def load(path):
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(Candle(time=dt.datetime.strptime(r["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC),
                              open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def stats(rows):
    vals = [r["net_R"] for r in rows if r["state"] in RESOLVED]
    gross = [r["gross_R"] for r in rows if r["state"] in RESOLVED]
    wins, losses = [v for v in vals if v > 0], [v for v in vals if v < 0]
    s = {"n_plans": len(rows), "states": dict(Counter(r["state"] for r in rows)), "n_resolved": len(vals),
         "n_win": len(wins), "n_loss": len(losses),
         "mean_gross_R": statistics.fmean(gross) if gross else None,
         "mean_net_R": statistics.fmean(vals) if vals else None,
         "median_net_R": statistics.median(vals) if vals else None,
         "total_net_R": sum(vals),
         "profit_factor_net": (sum(wins) / abs(sum(losses))) if losses else None,
         "mean_friction_R": statistics.fmean([r["friction_R"] for r in rows if r["state"] in RESOLVED]) if vals else None,
         "median_risk_pips": statistics.median([r["risk_distance"] / 0.0001 for r in rows if r["state"] in RESOLVED]) if vals else None}
    if len(vals) > 3:
        top = sorted(vals, reverse=True)[3:]
        s["leave_top_3_out_mean_net_R"] = statistics.fmean(top)
    if len(vals) >= 2:
        rng = random.Random(20260928)
        means = sorted(statistics.fmean(rng.choices(vals, k=len(vals))) for _ in range(10_000))
        s["bootstrap95_mean_net_R"] = [means[249], means[9749]]
    return s


def main():
    if os.path.exists(OUT):
        print(json.dumps({"error": "DEVELOPMENT_RUN_ALREADY_EXISTS", "path": OUT}))
        return 3
    ledger = yaml.safe_load(open(LEDGER, encoding="utf-8"))
    dd = ledger["development_data"]
    windows = {}
    if sha(dd["DEV2025"]["file"], lf=True) != dd["DEV2025"]["sha256_lf"]:
        raise SystemExit("DEV2025 hash mismatch")
    if sha(dd["G2_DEV_001"]["m1"]["file"]) != dd["G2_DEV_001"]["m1"]["sha256"]:
        raise SystemExit("G2_DEV_001 M1 hash mismatch")
    windows["DEV2025"] = (load(dd["DEV2025"]["file"]), 5, dd["DEV2025"]["evaluation_days_utc"])
    windows["G2_DEV_001"] = (load(dd["G2_DEV_001"]["m1"]["file"]), 1, dd["G2_DEV_001"]["evaluation_days_utc"])

    rows = []
    for wname, (base, step, span) in windows.items():
        mkt = Market(base)
        d0, d1 = dt.date.fromisoformat(span["from"]), dt.date.fromisoformat(span["to"])
        days = sorted({b.time.date() for b in base if d0 <= b.time.date() <= d1 and b.time.weekday() < 5})
        for fname, fn in FAMILIES.items():
            for d in days:
                p = fn(mkt, d)
                if p is None:
                    continue
                r = asdict(resolve(p, base, step))
                r["window"] = wname
                rows.append(r)

    report = {"schema": "FX_DISCOVERY_V1_DEVELOPMENT_RUN", "label": "IN_SAMPLE / DEVELOPMENT -- not OOS validation",
              "ledger": LEDGER, "ledger_sha256_lf": sha(LEDGER, lf=True), "friction": "CEILING_3PIP (commission UNVERIFIED)",
              "families": {}, "observations": rows}
    crit = {}
    for f in FAMILIES:
        fr = [r for r in rows if r["family"] == f]
        pooled, dev, g2 = stats(fr), stats([r for r in fr if r["window"] == "DEV2025"]), stats([r for r in fr if r["window"] == "G2_DEV_001"])
        checks = {
            "N_resolved>=40": pooled["n_resolved"] >= 40,
            "mean_net_R>0": (pooled["mean_net_R"] or -1) > 0,
            "PF_net>=1.20": (pooled["profit_factor_net"] or 0) >= 1.20,
            "leave_top_3_out>0": (pooled.get("leave_top_3_out_mean_net_R") or -1) > 0,
            "DEV2025_mean_net_R>0": (dev["mean_net_R"] or -1) > 0,
        }
        crit[f] = all(checks.values())
        report["families"][f] = {"pooled": pooled, "DEV2025": dev, "G2_DEV_001": g2, "criteria": checks, "passes": crit[f]}
    passing = [f for f in FAMILIES if crit[f]]
    best = max(passing, key=lambda f: report["families"][f]["pooled"]["bootstrap95_mean_net_R"][0]) if passing else None
    report["selection"] = {"passing": passing, "selected": best,
                           "classification": "OOS_CANDIDATE_READY" if best else "NO_DEVELOPMENT_CANDIDATE"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
