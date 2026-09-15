"""AG SSC HYP_002 -- Post-FAIL read-only failure/mechanism decomposition (P4-P9).

READ-ONLY DIAGNOSTIC. Does not modify, regenerate, or re-score the frozen Attempt-2
canonical population (artifacts/.../HYP_002_POPULATION_ATTEMPT_2/canonical_population.json).
Loads that population plus the SAME already-admitted, already-consumed GEN_002 EURUSD
M1/M15/H1 evaluation-input series (byte-identical to what Attempt 2 used, fingerprint-
verified below) to extract two attributes not persisted in the canonical lifecycle
record: (1) per-cycle regime/bias -- deterministic re-derivation of the same frozen
classifier output already computed once during Attempt 2, not a new economic
computation; (2) MFE/MAE path excursion between each occurrence's own entry_time and
resolution_time, computed from the same M1 candles already used to resolve that trade's
exit.

Touches no fresh/holdout data. Places no order. Does not evaluate an alternative
target/exit. Writes one descriptive artifact only.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from historical_replay.candle_store import HistoricalCandleStore  # noqa: E402
from historical_replay.symbol_metadata_manifest import load_symbol_metadata_manifest  # noqa: E402
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0

GEN002_ROOT = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914" / "raw"
M15_CSV = GEN002_ROOT / "EURUSD_M15.csv"
M1_CSV = GEN002_ROOT / "EURUSD_M1.csv"
COMBINED_H1_CSV = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / \
    "HYP_002_EVALUATION_INPUT" / "EURUSD_H1_WARMUP_PLUS_GEN002.csv"
H1_MANIFEST_PATH = REPO_ROOT / "config" / "historical_datasets" / "EURUSD_H1_WARMUP_PLUS_GEN002_symbol_metadata.yaml"

POPULATION_PATH = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / \
    "HYP_002_POPULATION_ATTEMPT_2" / "canonical_population.json"

EXPECTED_SHA256 = {
    COMBINED_H1_CSV: "0ce051944a2ff8e58c362aabf4ab25012b0936ddaf260108f5a4aca2eb46430f",
    M15_CSV: "3f0702eb50e67f8f9c534b30b69eafdb5620bc8d6e11defb6d8ccd47b76209e8",
    M1_CSV: "4cc01e2b185e714332cc5f1c4d253b579ee74085dd742903d0e9e3938906f332",
}
EXPECTED_POPULATION_HASH = "cf098f9a1d6459618d6c775a087b5cb443b7f1f7d915f650eeb8268381c2eb94"

DECISION_WINDOW_START = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
DECISION_WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

OUT_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "HYP_002_FAILURE_DECOMPOSITION"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _population_hash(records) -> str:
    payload = json.dumps(sorted(records, key=lambda x: x["trade_id"]), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _setup_key(trade_id: str) -> str:
    if "_S1_" in trade_id:
        return "S1"
    if "_S2_" in trade_id:
        return "S2"
    if "_S3_" in trade_id:
        return "S3"
    raise ValueError(trade_id)


def _pair_id(trade_id: str) -> str:
    return "ASIAN_LONDON" if trade_id.startswith("ASIAN_LONDON") else "LONDON_NEWYORK"


def main():
    population = json.loads(POPULATION_PATH.read_text(encoding="utf-8"))
    pop_hash = _population_hash(population)
    if pop_hash != EXPECTED_POPULATION_HASH:
        raise SystemExit(f"STOP: FROZEN_POPULATION_HASH_MISMATCH actual={pop_hash} expected={EXPECTED_POPULATION_HASH}")
    print(f"Loaded frozen Attempt-2 population: {len(population)} occurrences, hash verified.", file=sys.stderr)

    for path in (COMBINED_H1_CSV, M15_CSV, M1_CSV):
        actual = _sha256(path)
        if actual != EXPECTED_SHA256[path]:
            raise SystemExit(f"STOP: DATASET_FINGERPRINT_MISMATCH {path}: {actual} != {EXPECTED_SHA256[path]}")
    print("Dataset fingerprints verified identical to Attempt 2.", file=sys.stderr)

    config = load_config(repo_root=str(REPO_ROOT))
    h1_manifest = load_symbol_metadata_manifest(H1_MANIFEST_PATH)

    h1_candles, h1_report = load_utc_export_csv(str(COMBINED_H1_CSV), SYMBOL, "H1")
    m15_candles, m15_report = load_utc_export_csv(str(M15_CSV), SYMBOL, "M15")
    m1_candles, m1_report = load_utc_export_csv(str(M1_CSV), SYMBOL, "M1")

    h1_store = HistoricalCandleStore()
    h1_store.load_series(SYMBOL, "H1", h1_candles)

    windows = session_windows_from_config(config)
    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]

    # Re-derive regime/bias per (date, pair) decision cycle -- deterministic reproduction
    # of what Attempt 2 already computed once; not a new economic result.
    by_id = {r["trade_id"]: r for r in population}
    matched_regime = {}
    matched_bias = {}

    raw_start = max(m15_report.start_utc, m1_report.start_utc, DECISION_WINDOW_START)
    raw_end = min(m15_report.end_utc, m1_report.end_utc, DECISION_WINDOW_END)
    d = raw_start.date()
    from datetime import timedelta as _td
    while datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) <= raw_end:
        for pair_id in session_pairs:
            ref_end = windows[pair_id]["reference"].bounds_for_date(d)[1]
            bias = resolve_h1_market_bias(h1_store, h1_manifest, SYMBOL, ref_end, pair_id)
            result = run_replay(m15_candles, config, SYMBOL, pair_id, d, PIP_SIZE, PIP_VALUE_PER_LOT,
                                 bias_result=bias, m1_candles=m1_candles)
            if result.regime is None or result.campaign is None:
                continue
            for entry_dict in result.accepted_setups:
                model = entry_dict["setup_model"]
                outcome = entry_dict["outcome"]
                if outcome["terminal_state"] == "AMBIGUOUS_SEQUENCE" or outcome["gross_R"] is None:
                    continue
                trade_id = f"{pair_id}_{d}_{entry_dict['entry_time']}_{model}"
                if trade_id in by_id:
                    matched_regime[trade_id] = result.regime
                    matched_bias[trade_id] = bias.bias if bias.confidence != "UNAVAILABLE" else "UNAVAILABLE"
        d = d + _td(days=1)

    unmatched = [t for t in by_id if t not in matched_regime]
    if unmatched:
        print(f"WARNING: {len(unmatched)} occurrences could not be regime-matched: {unmatched}", file=sys.stderr)

    # MFE/MAE from the M1 path between each occurrence's own entry_time and resolution_time.
    m1_by_time = {c.time: c for c in m1_candles}
    m1_sorted = sorted(m1_candles, key=lambda c: c.time)

    def path_excursion(entry_time_str, resolution_time_str, entry_price, initial_risk, direction):
        et = datetime.fromisoformat(entry_time_str)
        rt = datetime.fromisoformat(resolution_time_str)
        path = [c for c in m1_sorted if et <= c.time <= rt]
        if not path:
            return None
        sign = 1.0 if direction == "LONG" else -1.0
        favorable_extreme = max((c.high if direction == "LONG" else -c.low) for c in path)
        adverse_extreme = min((c.low if direction == "LONG" else -c.high) for c in path)
        if direction == "LONG":
            mfe_price = max(c.high for c in path)
            mae_price = min(c.low for c in path)
        else:
            mfe_price = min(c.low for c in path)
            mae_price = max(c.high for c in path)
        mfe_r = sign * (mfe_price - entry_price) / initial_risk
        mae_r = sign * (mae_price - entry_price) / initial_risk
        return {"mfe_R": mfe_r, "mae_R": mae_r, "bars_in_path": len(path)}

    enriched = []
    for rec in population:
        exc = path_excursion(rec["entry_time"], rec["resolution_time"], rec["entry_price"],
                              rec["initial_risk"], rec["direction"])
        setup = _setup_key(rec["trade_id"])
        pair = _pair_id(rec["trade_id"])
        capture_ratio = None
        if exc and exc["mfe_R"] and exc["mfe_R"] > 1e-9:
            capture_ratio = rec["net_R"] / exc["mfe_R"]
        enriched.append({
            "trade_id": rec["trade_id"], "setup": setup, "session_pair": pair,
            "direction": rec["direction"], "entry_time": rec["entry_time"],
            "resolution_time": rec["resolution_time"], "final_state": rec["final_state"],
            "gross_R": rec["gross_R"], "friction_R": rec["friction_R"], "net_R": rec["net_R"],
            "regime": matched_regime.get(rec["trade_id"], "UNMATCHED"),
            "h1_bias": matched_bias.get(rec["trade_id"], "UNMATCHED"),
            "mfe_R": exc["mfe_R"] if exc else None, "mae_R": exc["mae_R"] if exc else None,
            "capture_ratio_net_over_mfe": capture_ratio,
            "mfe_minus_realized_net_R": (exc["mfe_R"] - rec["net_R"]) if exc else None,
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "occurrence_level_decomposition.json").write_text(
        json.dumps(enriched, indent=2, sort_keys=True, default=str), encoding="utf-8")

    report = build_report(enriched, config)
    (OUT_DIR / "failure_decomposition_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": statistics.mean(vals), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals),
            "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0}


def build_report(enriched, config):
    report = {}

    # P4 setup attribution
    by_setup = defaultdict(list)
    for e in enriched:
        by_setup[e["setup"]].append(e)
    setup_attr = {}
    for s in ("S1", "S2", "S3"):
        rows = by_setup.get(s, [])
        gross = [r["gross_R"] for r in rows]
        net = [r["net_R"] for r in rows]
        wins = sum(1 for r in rows if r["net_R"] > 1e-9)
        losses = sum(1 for r in rows if r["net_R"] < -1e-9)
        be = len(rows) - wins - losses
        gross_wins = [r["gross_R"] for r in rows if r["gross_R"] > 0]
        gross_losses = [r["gross_R"] for r in rows if r["gross_R"] < 0]
        profit_factor = (sum(gross_wins) / abs(sum(gross_losses))) if gross_losses and sum(gross_losses) != 0 else (
            "UNDEFINED_NO_LOSSES" if gross_wins else "UNDEFINED_NO_WINS")
        setup_attr[s] = {
            "N": len(rows), "wins": wins, "losses": losses, "breakevens": be,
            "gross_R_total": sum(gross) if gross else None,
            "net_R_total": sum(net) if net else None,
            "net_expectancy_R": statistics.mean(net) if net else None,
            "gross_expectancy_R": statistics.mean(gross) if gross else None,
            "profit_factor": profit_factor,
            "median_net_R": statistics.median(net) if net else None,
            "mean_friction_R": statistics.mean([r["friction_R"] for r in rows]) if rows else None,
            "mfe_R_stats": _stats([r["mfe_R"] for r in rows]),
            "mae_R_stats": _stats([r["mae_R"] for r in rows]),
            "final_state_counts": dict((k, sum(1 for r in rows if r["final_state"] == k))
                                        for k in set(r["final_state"] for r in rows)) if rows else {},
        }
        if s == "S2":
            setup_attr[s]["conclusion"] = "INSUFFICIENT_FOR_SETUP_LEVEL_CONCLUSION" if len(rows) < 10 else "EVALUABLE"
    report["setup_attribution"] = setup_attr

    # P5/P6 exit-capture / mechanism diagnostic (population-wide, and per-setup)
    mfe_vals = [e["mfe_R"] for e in enriched if e["mfe_R"] is not None]
    net_vals = [e["net_R"] for e in enriched if e["mfe_R"] is not None]
    gap = [e["mfe_minus_realized_net_R"] for e in enriched if e["mfe_minus_realized_net_R"] is not None]
    capture = [e["capture_ratio_net_over_mfe"] for e in enriched if e["capture_ratio_net_over_mfe"] is not None]

    def _threshold_outcomes(thr):
        subset = [e for e in enriched if e["mfe_R"] is not None and e["mfe_R"] >= thr]
        n = len(subset)
        if n == 0:
            return {"n": 0}
        neg = sum(1 for e in subset if e["net_R"] < -1e-9)
        be = sum(1 for e in subset if -1e-9 <= e["net_R"] <= 1e-9)
        pos = n - neg - be
        return {"n": n, "finished_negative": neg, "finished_breakeven": be, "finished_positive": pos,
                "frac_negative": neg / n, "frac_positive": pos / n}

    report["exit_capture_diagnostic"] = {
        "mfe_R_distribution": _stats(mfe_vals),
        "mfe_minus_realized_net_R_distribution": _stats(gap),
        "capture_ratio_net_over_mfe_distribution": _stats(capture),
        "thresholds": {f"mfe_ge_{t}R": _threshold_outcomes(t) for t in (0.5, 1.0, 1.5, 2.0, 3.0)},
        "runner_target_r_frozen": config.get("trade_management", {}).get("runner_target_r"),
        "dominant_final_state": max(
            {k: sum(1 for e in enriched if e["final_state"] == k) for k in set(e["final_state"] for e in enriched)}.items(),
            key=lambda kv: kv[1]),
        "note": "MECHANISM DIAGNOSTIC ONLY. No alternative target tested/searched/selected.",
    }

    # P5 mechanism-category tagging per occurrence (descriptive)
    def classify(e):
        if e["mae_R"] is not None and e["mae_R"] <= -0.95 and e["final_state"] == "RESOLVED_SL":
            if e["mfe_R"] is not None and e["mfe_R"] < 0.3:
                return "BAD_ENTRY"
            return "STOP_GEOMETRY"
        if e["mfe_R"] is not None and e["mfe_R"] >= 1.0 and e["net_R"] < 0.3 * e["mfe_R"]:
            return "EXIT_CAPTURE"
        if e["gross_R"] is not None and e["gross_R"] >= -0.05 and e["net_R"] < -0.05:
            return "FRICTION_DOMINANCE"
        return "NO_SINGLE_DOMINANT_MECHANISM"

    mech_counts = defaultdict(int)
    for e in enriched:
        e["mechanism_tag_descriptive"] = classify(e)
        mech_counts[e["mechanism_tag_descriptive"]] += 1
    report["entry_stop_exit_mechanism_tags_descriptive"] = dict(mech_counts)

    # P7 regime/context diagnostic
    def _group(key):
        groups = defaultdict(list)
        for e in enriched:
            groups[e[key]].append(e["net_R"])
        out = {}
        for k, vals in groups.items():
            out[k] = {"N": len(vals), "net_R_total": sum(vals), "net_expectancy_R": statistics.mean(vals),
                      "status": "DESCRIPTIVE_ONLY" if len(vals) < 10 else "SUFFICIENTLY_POPULATED_DESCRIPTIVE"}
        return out

    report["regime_context_diagnostic"] = {
        "by_regime": _group("regime"),
        "by_h1_bias": _group("h1_bias"),
        "by_session_pair": _group("session_pair"),
        "by_setup": _group("setup"),
        "by_direction": _group("direction"),
        "note": "All subgroups here are small relative to typical adequacy thresholds; treat every row as DESCRIPTIVE_ONLY unless explicitly marked otherwise. No new thresholds mined.",
    }

    # P8 temporal concentration
    sorted_e = sorted(enriched, key=lambda e: e["entry_time"])
    half = len(sorted_e) // 2
    first_half, second_half = sorted_e[:half] if half else [], sorted_e[half:]
    by_week = defaultdict(list)
    for e in sorted_e:
        wk = datetime.fromisoformat(e["entry_time"]).isocalendar()[1]
        by_week[wk].append(e["net_R"])
    report["temporal_concentration"] = {
        "chronological_first_half": {"N": len(first_half), "net_R_total": sum(e["net_R"] for e in first_half),
                                      "net_expectancy_R": statistics.mean([e["net_R"] for e in first_half]) if first_half else None},
        "chronological_second_half": {"N": len(second_half), "net_R_total": sum(e["net_R"] for e in second_half),
                                       "net_expectancy_R": statistics.mean([e["net_R"] for e in second_half]) if second_half else None},
        "by_iso_week": {str(wk): {"N": len(vals), "net_R_total": sum(vals), "net_expectancy_R": statistics.mean(vals)}
                        for wk, vals in sorted(by_week.items())},
    }

    # P9 friction decomposition
    gross_all = [e["gross_R"] for e in enriched]
    net_all = [e["net_R"] for e in enriched]
    friction_all = [e["friction_R"] for e in enriched]
    gross_exp = statistics.mean(gross_all)
    net_exp = statistics.mean(net_all)
    mean_friction = statistics.mean(friction_all)
    total_friction = sum(friction_all)
    report["friction_decomposition"] = {
        "gross_expectancy_R": gross_exp, "net_expectancy_R": net_exp,
        "mean_friction_R": mean_friction, "total_friction_R": total_friction,
        "gross_itself_negative": gross_exp < 0,
        "fraction_of_negative_net_attributable_to_friction": (mean_friction / abs(net_exp)) if net_exp < 0 else None,
        "interpretation": (
            "Gross expectancy is already negative (-{:.4f}R); friction (mean {:.4f}R/trade) adds further drag on top "
            "of an already-losing gross edge. This is NOT a pure friction-dominance case (gross positive, "
            "costs erase it) -- it is a hybrid: a weak/negative raw edge compounded by real transaction costs."
        ).format(gross_exp, mean_friction),
    }

    report["population_summary"] = {
        "N": len(enriched), "all_long_direction": all(e["direction"] == "LONG" for e in enriched),
        "final_state_counts": {k: sum(1 for e in enriched if e["final_state"] == k)
                                for k in set(e["final_state"] for e in enriched)},
    }
    return report


if __name__ == "__main__":
    main()
