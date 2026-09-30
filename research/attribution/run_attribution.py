"""AG_RULE_ATTRIBUTION_V1 orchestrator -- ordered, fail-fast gates (research only).

    python -m research.attribution.run_attribution

G0 admission -> G1 semantic -> G2 data -> 1 ledger -> 2 categories -> 3 ablation ->
4 diagnosis -> 5 preregistration -> 6 validation -> 7 verdicts. When a gate fails, every
later step is recorded NOT_EVALUATED and nothing further runs. No broker/exchange call,
no network, no protected (CONFIRM/HOLDOUT/OOS/H2) data: the only admissible input is the
public DEVELOPMENT manifest named in ADMISSION.yaml, ending before 2025-09-14.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from research.attribution import analysis, frozen_engine, ledger, validation  # noqa: E402

REPORT_DIR = os.path.join(HERE, "reports")
PIP_SIZE = {"EURUSD": 0.0001, "GBPUSD": 0.0001}
# Recorded once (AGENTS.md token rule 4: not re-probed by this script).
PUBLIC_SOURCE_PROBE = {
    "probed_utc": "2026-09-30T07:43:02Z", "environment": "Claude Code cloud container (agent proxy)",
    "datafeed.dukascopy.com:443": "CONNECT 403 (network policy denial)",
    "www.histdata.com:443": "CONNECT 403 (network policy denial)",
    "in_repo_pre_cutoff_data": "none admissible: SSC1D_WP1_OOS_EURUSD_2024Q1 is OOS (protected); "
                               "DEV_002 pre-2025-09-14 span is EURUSD H1 warm-up only (no M15/M1, broker source)",
}
STEPS = ("1_ledger", "2_categories", "3_ablation", "4_diagnosis", "5_preregistration",
         "6_validation", "7_verdicts")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gate_admission(adm: dict) -> dict:
    out = {}
    for sid, rec in adm["strategies"].items():
        eligible = (rec.get("backtest_status") == "ECONOMIC_GATE_FAIL" and rec.get("optimization_eligible") is True
                    and rec.get("data_role") == "DEVELOPMENT_ONLY" and rec.get("holdout_access") == "FORBIDDEN")
        out[sid] = {"backtest_status": rec.get("backtest_status"),
                    "optimization_eligible": eligible,
                    "status": "PASS" if eligible else "CHECKS_ONLY"}
    return out


def gate_semantic() -> dict:
    ssc = frozen_engine.semantic_check()
    asian_path = os.path.join(REPO_ROOT, "strategies", "ST_ASIAN_SWEEP_5R_V1.yaml")
    with open(asian_path, encoding="utf-8") as fh:
        asian_cfg = yaml.safe_load(fh)
    with open(os.path.join(REPO_ROOT, "strategies", "registry.yaml"), encoding="utf-8") as fh:
        registry = yaml.safe_load(fh)
    registered = "ST_ASIAN_SWEEP_5R_V1" in (registry.get("strategies") or registry)
    engine_present = os.path.isdir(os.path.join(REPO_ROOT, "src", "strategy_engine", "session"))
    asian_ok = asian_cfg.get("version") == "1.1.1" and registered and engine_present
    return {
        "ST_SESSION_SWEEP_CONTINUATION_V1": ssc,
        "ST_ASIAN_SWEEP_5R_V1": {
            "status": "PASS" if asian_ok else "FAIL", "version": asian_cfg.get("version"),
            "config_sha256": _sha256(asian_path), "registered": registered,
            "engine_present": engine_present,
            "instruments": asian_cfg.get("instruments") or asian_cfg.get("symbols"),
        },
    }


def gate_data(adm: dict, instruments_by_strategy: dict) -> dict:
    spec = adm["public_dev_data"]
    path = os.path.join(REPO_ROOT, spec["manifest_path"])
    if not os.path.isfile(path):
        reason = "PUBLIC_DEV_MANIFEST_MISSING"
        return {sid: {"status": "FAIL", "reason": reason, "manifest_path": spec["manifest_path"]}
                for sid in instruments_by_strategy}
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    out = {}
    for sid, instruments in instruments_by_strategy.items():
        problems = []
        if manifest.get("data_role") != "DEVELOPMENT_ONLY":
            problems.append("DATA_ROLE_NOT_DEVELOPMENT_ONLY")
        for sym in instruments or []:
            for tf in spec["required_timeframes"]:
                f = (manifest.get("files") or {}).get(f"{sym}_{tf}")
                if not f:
                    problems.append(f"MISSING:{sym}_{tf}")
                    continue
                if f.get("source") not in spec["allowed_sources"]:
                    problems.append(f"SOURCE_NOT_PUBLIC:{sym}_{tf}")
                if not f.get("end_utc") or f["end_utc"] >= spec["end_exclusive_utc"]:
                    problems.append(f"END_NOT_BEFORE_CUTOFF:{sym}_{tf}")
                fp = os.path.join(REPO_ROOT, f.get("path", ""))
                if not os.path.isfile(fp) or _sha256(fp) != f.get("sha256"):
                    problems.append(f"HASH_OR_FILE_MISMATCH:{sym}_{tf}")
            if not (manifest.get("h1_symbol_metadata_manifests") or {}).get(sym):
                problems.append(f"H1_METADATA_MANIFEST_MISSING:{sym}")
        out[sid] = {"status": "FAIL" if problems else "PASS", "problems": problems}
    out["_manifest"] = manifest
    return out


# ------------------------------------------------------------------ pipeline (data PASS)
def _load_candles(Candle, path: str):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = datetime.fromisoformat(r["time"].replace("Z", "+00:00"))
            t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            rows.append(Candle(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                               float(r.get("volume") or 0) or None))
    return rows


def run_pipeline(manifest: dict, prereg: dict) -> dict:
    replay = frozen_engine.load()
    config = frozen_engine.load_config()
    from strategy_engine.session.candles import Candle  # frozen tree
    from historical_replay.candle_store import HistoricalCandleStore
    from session_sweep_continuation.h1_bias import load_and_validate_h1_manifest, resolve_h1_market_bias
    from session_sweep_continuation.sessions import session_windows_from_config

    files = manifest["files"]
    windows = session_windows_from_config(config)
    pairs = [p["pair_id"] for p in config["session_pairs"]]
    runs = {"BASELINE": {}, "ALL_RELAXED": {"relax": ledger.ALL_RELAXED}}
    runs.update({f"LOO_{g}": {"relax": {g}} for g in ledger.GATES})
    runs.update({s: {"swap": s} for s in ledger.SWAPS})
    variants = prereg.get("variants") or [] if prereg.get("status") == "PREREGISTERED" else []
    for v in variants[:3]:
        runs[f"VARIANT_{v['version']}"] = {"relax": set(v.get("relax") or ()), "swap": v.get("swap"),
                                           "exclude": v.get("exclude") or ()}
    trades = {name: [] for name in runs}
    rows = []
    for sym in config["instruments"]:
        m15 = _load_candles(Candle, os.path.join(REPO_ROOT, files[f"{sym}_M15"]["path"]))
        m1 = _load_candles(Candle, os.path.join(REPO_ROOT, files[f"{sym}_M1"]["path"]))
        h1_path = os.path.join(REPO_ROOT, files[f"{sym}_H1"]["path"])
        store = HistoricalCandleStore()
        store.load_series(sym, "H1", _load_candles(Candle, h1_path))
        meta = load_and_validate_h1_manifest(
            os.path.join(REPO_ROOT, manifest["h1_symbol_metadata_manifests"][sym]), h1_path, sym)
        d, last = m15[0].time.date(), m15[-1].time.date()
        while d <= last:
            if d.weekday() < 5:
                for pair in pairs:
                    ref_end = windows[pair]["reference"].bounds_for_date(d)[1]
                    bias = resolve_h1_market_bias(store, meta, sym, ref_end, pair)
                    out = {name: ledger.run_cycle(replay, m15, config, sym, pair, d, PIP_SIZE[sym],
                                                  bias_result=bias, m1=m1, **kw)
                           for name, kw in runs.items()}
                    res, rec = out["ALL_RELAXED"]
                    rows += ledger.ledger_rows(res, rec, out["BASELINE"][0], PIP_SIZE[sym],
                                               f"{bias.bias}/{bias.confidence}")
                    for name, (r, _) in out.items():
                        trades[name] += ledger.trade_returns(r, PIP_SIZE[sym])
            d += timedelta(days=1)
    return {"rows": rows, "trades": trades, "variants": [f"VARIANT_{v['version']}" for v in variants[:3]]}


def evaluate(rows, trades, variant_names) -> dict:
    cats = analysis.category_table(rows, population="frozen_baseline")
    cats_all = analysis.category_table(rows, population="all_candidates")
    base = [t["net_R"] for t in trades["BASELINE"]]
    abl = analysis.ablation_deltas(base, {k: [t["net_R"] for t in v] for k, v in trades.items() if k != "BASELINE"})
    diag = analysis.failure_diagnosis(cats)
    trial_names = list(trades)  # EVERY configuration evaluated counts as a trial
    dates, names, mat = validation.daily_matrix(trades)
    pbo = validation.pbo_cscv(mat)
    cpcv = validation.cpcv_oos(mat, names)
    sharpes = [validation._sharpe([row[j] for row in mat]) for j in range(len(names))]
    verdicts = {}
    for v in variant_names:
        wf = validation.walk_forward(trades[v])
        j = names.index(v)
        dsr = validation.deflated_sharpe([row[j] for row in mat], len(trial_names), sharpes)
        verdicts[v] = {"walk_forward": wf, "cpcv": cpcv.get(v), "dsr": dsr, "pbo": pbo,
                       "verdict": validation.verdict(wf["oos"], dsr, pbo)}
    return {"categories": cats, "categories_all_candidates": cats_all,
            "rule_rejections": analysis.rule_rejection_table(rows, ledger.GATES),
            "ablation": abl, "diagnosis": diag, "trial_count": len(trial_names),
            "trials": trial_names, "pbo_all_trials": pbo, "variant_verdicts": verdicts}


def main() -> int:
    with open(os.path.join(HERE, "ADMISSION.yaml"), encoding="utf-8") as fh:
        adm = yaml.safe_load(fh)
    with open(os.path.join(HERE, "PREREGISTRATION.yaml"), encoding="utf-8") as fh:
        prereg = yaml.safe_load(fh)
    report = {"mission_id": adm["mission_id"],
              "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                                     text=True).stdout.strip(),
              "invariants": {"broker_calls": 0, "network_calls": 0, "protected_data_access_count": 0,
                             "frozen_rules_edited": False, "live_demo_code_changed": False}}
    report["G0_admission"] = gate_admission(adm)
    report["G1_semantic"] = gate_semantic()
    instruments = {"ST_SESSION_SWEEP_CONTINUATION_V1": frozen_engine.load_config()["instruments"],
                   "ST_ASIAN_SWEEP_5R_V1": report["G1_semantic"]["ST_ASIAN_SWEEP_5R_V1"]["instruments"]}
    data = gate_data(adm, instruments)
    manifest = data.pop("_manifest", None)
    report["G2_data"] = data
    report["G2_public_source_probe"] = PUBLIC_SOURCE_PROBE
    ssc = "ST_SESSION_SWEEP_CONTINUATION_V1"
    failed = next((g for g in ("G0_admission", "G1_semantic", "G2_data") if report[g][ssc]["status"] != "PASS"), None)
    if failed:
        report["stopped_at"] = failed
        report["ledger_n"] = 0
        report["steps"] = {s: "NOT_EVALUATED" for s in STEPS}
        report["trial_count"] = 0
    else:
        out = run_pipeline(manifest, prereg)
        report["ledger_n"] = len(out["rows"])
        report.update(evaluate(out["rows"], out["trades"], out["variants"]))
        report["steps"] = {s: "EVALUATED" for s in STEPS}
        if prereg.get("status") != "PREREGISTERED":
            report["steps"].update({"5_preregistration": "PENDING_OWNER_WRITE",
                                    "6_validation": "NOT_EVALUATED", "7_verdicts": "NOT_EVALUATED"})
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, "ledger_v1.jsonl"), "w", encoding="utf-8") as fh:
            for r in out["rows"]:
                fh.write(json.dumps(r, sort_keys=True) + "\n")
    report["ST_ASIAN_SWEEP_5R_V1_scope"] = "ADMISSION_DATA_SEMANTIC_CHECKS_ONLY -- not optimized"
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "attribution_report_v1.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, default=str)
    print(json.dumps({"stopped_at": report.get("stopped_at"), "ledger_n": report["ledger_n"],
                      "trial_count": report["trial_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
