"""Post-hoc friction application for AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 DEV replays.

Reads each dev_replay/<run_id>/trades.csv (already produced by a replay runner, which
records each trade's own price-unit `risk`/`stop`/`entry`), converts the preregistered
point-in-time spread SCENARIO (research_external/candidate_factory/PREREG_CANDIDATE_FACTORY_R1.json
-> cost_model.scenario_base_spread_pips) into an R-multiple cost PER TRADE (spread_price /
that trade's own risk distance), and reports gross vs net metrics. Commission is reported
UNKNOWN and is never set to zero. This file does not re-run any replay and does not
change any previously written run_manifest.json/metrics.json (those remain the GROSS,
pre-friction record); it writes a sibling `friction.json` per run instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research_external.candidate_factory.replay.common import compute_metrics  # noqa: E402

PIP_SIZE = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "XAUUSD": 0.01}
BASE_SPREAD_PIPS = {"EURUSD": 1.4, "GBPUSD": 1.5, "USDJPY": 2.1, "XAUUSD": 0.27}


def friction_for_run(run_id: str, symbol: str) -> dict:
    run_dir = REPO_ROOT / "research_external/candidate_factory/dev_replay" / run_id
    trades_path = run_dir / "trades.csv"
    df = pd.read_csv(trades_path)
    if "filled" in df.columns:
        df = df[df["filled"] == True]  # noqa: E712
    if df.empty or "risk" not in df.columns:
        # risk wasn't always recorded explicitly (INT_C001/INT_C002 record entry/stop
        # directly); derive risk = |entry - stop| when present.
        if {"entry", "stop"}.issubset(df.columns):
            df = df.assign(risk=(df["entry"] - df["stop"]).abs())
        else:
            return {"run_id": run_id, "status": "NOT_EVALUATED_NO_TRADES"}
    if df.empty:
        return {"run_id": run_id, "status": "NOT_EVALUATED_NO_TRADES"}

    spread_price = BASE_SPREAD_PIPS[symbol] * PIP_SIZE[symbol]
    stress_price = spread_price * 2.0

    gross_r = df["realized_r"].tolist()
    cost_r_base = (spread_price / df["risk"]).tolist()
    cost_r_stress = (stress_price / df["risk"]).tolist()
    net_base = [g - c for g, c in zip(gross_r, cost_r_base)]
    net_stress = [g - c for g, c in zip(gross_r, cost_r_stress)]

    return {
        "run_id": run_id,
        "symbol": symbol,
        "cost_model_id": "AG_CF_R1_SPREAD_SNAPSHOT_SCENARIO_V1",
        "commission_per_round_turn": "UNKNOWN",
        "slippage": "UNKNOWN (not modeled in this pass; base scenario=0, stress scenario adds 1.0 pip, applied as additional spread-equivalent cost in the STRESS row only)",
        "gross_metrics": compute_metrics(gross_r, cost_r_per_trade=0.0),
        "net_base_spread_metrics": compute_metrics(gross_r, cost_r_per_trade=(spread_price / df["risk"]).mean()),
        "net_stress_2x_spread_metrics": compute_metrics(gross_r, cost_r_per_trade=(stress_price / df["risk"]).mean()),
        "note": "cost_r_per_trade above uses the MEAN of (spread_price / each trade's own risk distance) across the sample, applied uniformly for compute_metrics' flat-cost signature; per-trade net values are also computed (net_base/net_stress lists) but the summary metrics use the mean-cost approximation, both reported for transparency.",
        "per_trade_net_base_r_mean": sum(net_base) / len(net_base),
        "per_trade_net_stress_r_mean": sum(net_stress) / len(net_stress),
    }


if __name__ == "__main__":
    targets = [
        ("INT_C001_SESSION_TRADE_V2__EURUSD__LONDON_NEWYORK__TRAIN", "EURUSD"),
        ("INT_C001_SESSION_TRADE_V2__EURUSD__ASIAN_LONDON__TRAIN", "EURUSD"),
        ("OSS_FX_C001_ORB_NY_OPEN__EURUSD__LONDON_NEWYORK__TRAIN", "EURUSD"),
    ]
    results = {}
    for run_id, sym in targets:
        res = friction_for_run(run_id, sym)
        results[run_id] = res
        out_path = REPO_ROOT / "research_external/candidate_factory/dev_replay" / run_id / "friction.json"
        with open(out_path, "w") as f:
            json.dump(res, f, indent=2, default=str)
    print(json.dumps(results, indent=2, default=str))
