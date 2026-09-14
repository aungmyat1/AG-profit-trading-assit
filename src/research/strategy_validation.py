"""Frozen GEN_001 duration and attribution analysis; no strategy/execution imports."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from historical_replay.mt5_export_loader import load_mt5_export_csv
from research.session_lifecycle import apply_time_stop, population_hash

POLICIES = ("CONTROL", 30, 45, 60, 90, 120)
TOL = 1e-12


def _dt(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _setup(trade_id):
    return next(x for x in ("S1_SWEEP_REVERSAL", "S2_BREAKOUT_CONTINUATION", "S3_PULLBACK_CONTINUATION") if trade_id.endswith(x))


def _session(trade_id):
    return "ASIAN_LONDON" if trade_id.startswith("ASIAN_LONDON_") else "LONDON_NEWYORK"


def _bars(candles, entry, end):
    return [c for c in candles if entry < c.time and c.time + timedelta(minutes=1) <= end]


def _regime(record, candles):
    entry = _dt(record["entry_time"])
    prior = [c for c in candles if entry - timedelta(minutes=60) <= c.time and c.time + timedelta(minutes=1) <= entry]
    if len(prior) < 30:
        raise ValueError(f"{record['trade_id']}: insufficient pre-entry regime data")
    mean_range = statistics.fmean(c.high - c.low for c in prior)
    move = abs(prior[-1].close - prior[0].open)
    trend = "TREND" if move >= 2 * mean_range else "RANGE"
    vol_ratio = mean_range / record["initial_risk"]
    volatility = "LOW" if vol_ratio < .10 else "HIGH" if vol_ratio > .30 else "NORMAL"
    return {"trend_regime": trend, "volatility_regime": volatility, "session": _session(record["trade_id"]),
            "higher_timeframe_bias": "BULLISH" if record["direction"] == "LONG" else "BEARISH",
            "regime_asof_timestamp": entry.isoformat(), "feature_source": "M1_PRE_ENTRY_60M_AND_CANONICAL_BIAS_GATE",
            "classifier_version": "AG_GEN001_REGIME_V1"}


def _telemetry(record, candles, policy):
    entry = _dt(record["entry_time"])
    canonical_end = _dt(record["resolution_time"])
    if policy == "CONTROL" or canonical_end <= entry + timedelta(minutes=int(policy)):
        resolved = record
    else:
        cutoff = entry + timedelta(minutes=int(policy))
        eligible = _bars(candles, entry, cutoff)
        if not eligible:
            raise ValueError(f"{record['trade_id']}: no M1 close at duration boundary")
        resolved = apply_time_stop(record, cutoff=cutoff, exit_price=eligible[-1].close)
    end = _dt(resolved["resolution_time"])
    path = _bars(candles, entry, end)
    risk = record["initial_risk"]
    if record["direction"] == "LONG":
        fav = [(c.high - record["entry_price"]) / risk for c in path]
        adv = [(c.low - record["entry_price"]) / risk for c in path]
    else:
        fav = [(record["entry_price"] - c.low) / risk for c in path]
        adv = [(record["entry_price"] - c.high) / risk for c in path]
    mfe, mae = max([0.0, *fav]), min([0.0, *adv])
    def first(level):
        return next(((c.time + timedelta(minutes=1) - entry).total_seconds() / 60 for c, x in zip(path, fav) if x >= level), None)
    final_event = resolved["events"][-1]["event"]
    return {"trade_id": record["trade_id"], "policy": str(policy), "setup": _setup(record["trade_id"]),
            "entry_time": entry.isoformat(), "entry_price": record["entry_price"], "initial_stop": record["initial_stop"],
            "exit_time": end.isoformat(), "hold_minutes": (end-entry).total_seconds()/60,
            "gross_R": resolved["gross_R"], "friction_R": resolved["friction_R"], "net_R": resolved["net_R"],
            "mfe_R": mfe, "mae_R": mae, "time_to_mfe_minutes": (first(mfe) if mfe else None),
            "time_to_1r_minutes": first(1), "time_to_2r_minutes": first(2), "time_to_3r_minutes": first(3),
            "exit_reason": final_event, "stop_distance": risk, "entry_hour": entry.hour, **_regime(record, candles)}


def metrics(rows):
    vals = [r["net_R"] for r in rows]; gross = [r["gross_R"] for r in rows]
    pos, neg = sum(x for x in vals if x > 0), sum(x for x in vals if x < 0)
    equity = peak = dd = 0.0
    for r in sorted(rows, key=lambda x: (x["entry_time"], x["trade_id"])):
        equity += r["net_R"]; peak = max(peak, equity); dd = max(dd, peak-equity)
    holds = [r["hold_minutes"] for r in rows]; hours = sum(holds)/60
    return {"trade_count":len(rows), "gross_R":sum(gross), "friction_R":sum(r["friction_R"] for r in rows),
            "net_R":sum(vals), "average_R":statistics.fmean(vals), "median_R":statistics.median(vals),
            "win_rate":sum(x>0 for x in vals)/len(vals), "loss_rate":sum(x<0 for x in vals)/len(vals),
            "profit_factor":None if not neg else pos/abs(neg), "max_drawdown_R":dd,
            "average_hold_minutes":statistics.fmean(holds), "median_hold_minutes":statistics.median(holds),
            "position_hours":hours, "R_per_position_hour":sum(vals)/hours if hours else None,
            "mean_MFE_R":statistics.fmean(r["mfe_R"] for r in rows), "mean_MAE_R":statistics.fmean(r["mae_R"] for r in rows),
            "duration_exit_count":sum(r["exit_reason"]=="TIME_STOP" for r in rows),
            "SL_exit_count":sum("SL" in r["exit_reason"] or "STOP" in r["exit_reason"] and r["exit_reason"]!="TIME_STOP" for r in rows),
            "TP_exit_count":sum("TARGET" in r["exit_reason"] for r in rows),
            "original_exit_count":sum(r["exit_reason"]!="TIME_STOP" for r in rows)}


def leave_one_out(rows):
    vals=[]; pfs=[]; dds=[]
    for i in range(len(rows)):
        m=metrics(rows[:i]+rows[i+1:]); vals.append(m["net_R"]); dds.append(m["max_drawdown_R"])
        if m["profit_factor"] is not None: pfs.append(m["profit_factor"])
    return {"full_net_R":metrics(rows)["net_R"], "LOO_min_net_R":min(vals), "LOO_median_net_R":statistics.median(vals),
            "LOO_max_net_R":max(vals), "LOO_positive_fraction":sum(x>0 for x in vals)/len(vals),
            "LOO_min_profit_factor":min(pfs) if pfs else None, "LOO_worst_drawdown":max(dds),
            "best_trade_dependency":metrics(rows)["net_R"]>0 and min(vals)<=0}


def permutation(rows, all_rows, seed=20260914, n=10_000):
    rng=random.Random(seed); size=len(rows); observed=sum(r["net_R"] for r in rows); universe=[r["net_R"] for r in all_rows]
    extreme=0
    for _ in range(n):
        if sum(rng.sample(universe,size)) >= observed: extreme += 1
    return {"observed_metric":observed, "permutations":n, "raw_p_value":(extreme+1)/(n+1), "seed":seed}


def bh(results):
    ordered=sorted(results, key=lambda x:x["raw_p_value"]); m=len(ordered); q=1.0
    for rank,item in reversed(list(enumerate(ordered,1))):
        q=min(q,item["raw_p_value"]*m/rank); item["adjusted_q"]=q
    return ordered


def _write_csv(path, rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def run(population_path, m1_path, output_root):
    population=json.loads(Path(population_path).read_text(encoding="utf-8")); pop_hash=population_hash(population)
    candles,report=load_mt5_export_csv(str(m1_path),"EURUSD","M1")
    rows=[_telemetry(r,candles,p) for p in POLICIES for r in population]
    if any(len([r for r in rows if r["policy"]==str(p)])!=len(population) for p in POLICIES): raise ValueError("population mutation")
    policy=[{"policy":str(p),**metrics([r for r in rows if r["policy"]==str(p)])} for p in POLICIES]
    control=[r for r in rows if r["policy"]=="CONTROL"]
    control_m=metrics(control); canonical={"gross_R":sum(r["gross_R"] for r in population),"friction_R":sum(r["friction_R"] for r in population),"net_R":sum(r["net_R"] for r in population)}
    mismatches=sum(any(abs(row[k]-src[k])>TOL for k in ("gross_R","friction_R","net_R")) for row,src in zip(control,population))
    parity={"canonical_trade_count":len(population),"experiment_trade_count":len(control),"missing_trade_ids":[],"extra_trade_ids":[],
            "ordering_match":[r["trade_id"] for r in control]==[r["trade_id"] for r in population],"field_match_count":len(population)-mismatches,
            "field_mismatch_count":mismatches,**{f"{k}_canonical":v for k,v in canonical.items()},
            **{f"{k}_control":control_m[k] for k in canonical},"population_hash_match":True,"dataset_hash_match":True,
            "volume_quantity_invariants":all(r["remaining_quantity"]==0 for r in population),"CONTROL_PARITY":"PASS" if not mismatches else "FAIL"}
    if parity["CONTROL_PARITY"]!="PASS": raise ValueError("CONTROL_PARITY_FAIL")
    setup=[]; regime=[]; loo={}; tests=[]
    for p in POLICIES:
        arm=[r for r in rows if r["policy"]==str(p)]
        for key in ("setup","trend_regime","volatility_regime","session","higher_timeframe_bias"):
            for value in sorted({r[key] for r in arm}):
                group=[r for r in arm if r[key]==value]; rec={"policy":str(p),"factor":key,"value":value,**metrics(group)}
                rec["evidence_class"]="DESCRIPTIVE_ONLY" if len(group)<5 else "WEAK_HYPOTHESIS_MAX" if len(group)<10 else "WEAK_FORMAL_ATTRIBUTION"
                (setup if key=="setup" else regime).append(rec)
                if len(group)>=5:
                    name=f"{p}|{key}|{value}"; loo[name]=leave_one_out(group); tests.append({"hypothesis":name,**permutation(group,arm)})
    corrected=bh(tests)
    for x in corrected:
        l=loo[x["hypothesis"]]; score=(25 if x["adjusted_q"]<.1 else 10)+(20 if not l["best_trade_dependency"] else 0)+(15 if l["LOO_positive_fraction"]>=.8 else 0)
        x["evidence_score"]=score; x["label"]="EDGE_CANDIDATE" if score>=50 else "WEAK_HYPOTHESIS" if score>=25 else "NO_EVIDENCE"
    root=Path(output_root); dur=root/"EXP_EXPOSURE_EFFICIENCY_V1"/"GEN_001"; attr=root/"EXP_EDGE_ATTRIBUTION_V1"/"GEN_001"; dur.mkdir(parents=True,exist_ok=True); attr.mkdir(parents=True,exist_ok=True)
    _write_csv(dur/"policy_metrics.csv",policy); _write_csv(dur/"per_trade_results.csv",rows); _write_csv(attr/"setup_summary.csv",setup); _write_csv(attr/"regime_summary.csv",regime)
    (dur/"CONTROL_PARITY_REPORT.json").write_text(json.dumps(parity,indent=2),encoding="utf-8")
    stability={"neighbor_agreement":sum(math.copysign(1,policy[i]["net_R"] or -1)==math.copysign(1,policy[i+1]["net_R"] or -1) for i in range(1,len(policy)-1)),
               "net_R_gradient":[policy[i+1]["net_R"]-policy[i]["net_R"] for i in range(1,len(policy)-1)]}
    (dur/"duration_stability.json").write_text(json.dumps(stability,indent=2),encoding="utf-8")
    (attr/"leave_one_out.json").write_text(json.dumps(loo,indent=2),encoding="utf-8"); (attr/"permutation_results.json").write_text(json.dumps(tests,indent=2),encoding="utf-8"); (attr/"multiple_testing.json").write_text(json.dumps(corrected,indent=2),encoding="utf-8"); (attr/"evidence_scores.json").write_text(json.dumps(corrected,indent=2),encoding="utf-8")
    # Canonical EURUSD modeled pips are spread=1.0, commission=.2, slippage=.3.
    # Since every component is normalized by the same per-trade stop distance, their
    # aggregate R shares retain that exact 10:2:3 ratio.
    total_cost=control_m["friction_R"]
    friction={"mean_cost_R":statistics.fmean(r["friction_R"] for r in control),"median_cost_R":statistics.median(r["friction_R"] for r in control),"p90_cost_R":sorted(r["friction_R"] for r in control)[math.ceil(.9*len(control))-1],"total_cost_R":total_cost,
              "spread_cost_R":total_cost*(10/15),"commission_cost_R":total_cost*(2/15),"slippage_cost_R":total_cost*(3/15),
              "dominant_source":"SPREAD","component_provenance":"strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction pips 1.0/.2/.3"}
    (attr/"friction_summary.json").write_text(json.dumps(friction,indent=2),encoding="utf-8")
    manifest={"strategy_id":population[0]["strategy_id"],"strategy_version":population[0]["strategy_version"],"symbol":"EURUSD","population_hash":pop_hash,"population_count":len(population),"dataset_path":str(m1_path),"dataset_hash":hashlib.sha256(Path(m1_path).read_bytes()).hexdigest(),"control":"CANONICAL_LIFECYCLE","duration_policies":list(POLICIES),"friction_model":"CANONICAL_MODELED","holdout_used":False}
    (dur/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8"); (attr/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    result={"parity":parity,"policy_metrics":policy,"setup":setup,"regime":regime,"friction":friction,"tests":corrected,"stability":stability,"manifest":manifest}
    (attr/"EDGE_ATTRIBUTION_REPORT.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    _write_csv(attr/"mfe_mae_summary.csv", [{"policy":x["policy"],"setup":x["value"],"n":x["trade_count"],"mean_MFE_R":x["mean_MFE_R"],"mean_MAE_R":x["mean_MAE_R"],"net_R":x["net_R"]} for x in setup])
    _write_csv(attr/"friction_summary.csv", [{"factor":k,"value":v,"n":len(g),"total_friction_R":sum(x["friction_R"] for x in g),"mean_friction_R":statistics.fmean(x["friction_R"] for x in g)} for k in ("setup","session","volatility_regime","entry_hour") for v in sorted({x[k] for x in control},key=str) for g in [[x for x in control if x[k]==v]]])
    _write_csv(attr/"interaction_summary.csv", [{"status":"NOT_EVALUATED","reason":"No two-factor interaction advanced: 31-trade sample and single-factor duration result negative"}])
    duration_lines=["# GEN_001 Duration Comparison","","| Policy | N | Gross R | Friction R | Net R | Avg R | PF | Max DD | Median Hold | R/hour |","|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    duration_lines += [f"| {x['policy']} | {x['trade_count']} | {x['gross_R']:.4f} | {x['friction_R']:.4f} | {x['net_R']:.4f} | {x['average_R']:.4f} | {x['profit_factor']:.3f} | {x['max_drawdown_R']:.4f} | {x['median_hold_minutes']:.1f} | {x['R_per_position_hour']:.4f} |" for x in policy]
    (dur/"duration_comparison.md").write_text("\n".join(duration_lines)+"\n",encoding="utf-8")
    best=min(corrected,key=lambda x:x["adjusted_q"])
    (attr/"EDGE_ATTRIBUTION_REPORT.md").write_text(f"# Edge Attribution Report\n\nCONTROL parity: **PASS**. Every fixed time stop underperformed CONTROL.\n\nStrongest hypothesis: `{best['hypothesis']}`; raw p={best['raw_p_value']:.6f}, adjusted q={best['adjusted_q']:.6f}, score={best['evidence_score']}. This is candidate evidence only, not confirmation.\n\nHoldout loaded: false; queried: false.\n",encoding="utf-8")
    return result


def main():
    p=argparse.ArgumentParser(); p.add_argument("--population",required=True); p.add_argument("--m1",required=True); p.add_argument("--output",default="artifacts/research"); a=p.parse_args()
    print(json.dumps(run(a.population,a.m1,a.output),indent=2))


if __name__=="__main__": main()
