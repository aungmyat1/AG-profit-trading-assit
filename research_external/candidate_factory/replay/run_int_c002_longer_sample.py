"""DEV replay runner for AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1.

Diagnostic follow-up to the parent AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 campaign's
INT_C002 (ST_MTF_CONTROL_SHIFT_V1, PR #34) HOLD_SAMPLE_REQUIRED verdict. Reuses the
EXACT SAME byte-identical engine copy and the EXACT SAME M15 decision population
(HIST1Y dataset, 2025-09-14..2026-09-15) as the parent run. The only change: D1 and H4
are derived from a genuinely longer H1 series (extended back to 2025-01-01 via the
SSC_V1_0_1_G2_DEV_002 package's pre-HIST1Y H1 history) and passed to evaluate() as the
FULL closed-to-date series at each decision point -- no bounded tail-window truncation
(TAIL_D1=40 / TAIL_H4=80 bars from the parent run are removed here). This directly
tests whether that bounded-tail-window approximation was material to the parent run's
zero-signal result (explanations C/D in docs/plans/AG_MTF_CONTROL_SHIFT_SAMPLE_ADEQUACY_R1.md).

No strategy rule, threshold, or session window is changed. Frozen prereg:
research_external/candidate_factory/PREREG_MTF_LONGER_SAMPLE_R1.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research_external.candidate_factory.internal_reference.mtf_control_shift import (  # noqa: E402
    Candle as MCandle,
    evaluate as mtf_evaluate,
)
from research_external.candidate_factory.replay.common import (  # noqa: E402
    compute_metrics,
    load_mt5_csv,
    resample_ohlc,
    resolve_two_leg_trade,
    sha256_of_file,
)

PREREG_PATH = REPO_ROOT / "research_external/candidate_factory/PREREG_MTF_LONGER_SAMPLE_R1.json"
H1_EXTENDED_PATH = REPO_ROOT / "research_external/candidate_factory/data/EURUSD_H1_WARMUP_EXTENDED_JAN2025_SEP2026.csv"
H1_HIST1Y_PATH = REPO_ROOT / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_H1.csv"
M15_PATH = REPO_ROOT / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_M15.csv"

SESSION_WINDOWS = {
    "ASIAN_LONDON": (time(6, 0), time(9, 0)),
    "LONDON_NEWYORK": (time(11, 0), time(14, 0)),
}
TAIL_H1, TAIL_M15 = 60, 150  # unchanged from parent run; only D1/H4 truncation is removed
FORCE_FLAT_TIME = time(21, 0)

# Funnel stage ordering, mapped from the engine's own reason codes (see engine.py).
FUNNEL_STAGES = ["CONTEXT", "LOCATION", "H1_CONTROL_SHIFT", "M15_REFINEMENT", "GEOMETRY", "SESSION", "TRADE"]
REASON_TO_FAIL_STAGE = {
    "HTF_BIAS_NOT_ALIGNED": "CONTEXT",
    "NO_FRESH_H4_POI": "LOCATION",
    "HTF_POI_NOT_REACHED": "LOCATION",
    "NO_VALID_H1_CONTROL_SHIFT": "H1_CONTROL_SHIFT",
    # FALSE_CHOCH_* are dynamic suffixes handled separately below
    "NO_M15_ENTRY_REFINEMENT": "M15_REFINEMENT",
    "NON_POSITIVE_ENTRY_ZONE": "GEOMETRY",
    "NON_POSITIVE_RISK": "GEOMETRY",
    "NO_VALID_HTF_FINAL_TARGET": "GEOMETRY",
    "READY_RESEARCH_SHADOW": "TRADE",
}


def df_to_candles(df: pd.DataFrame) -> list:
    return [MCandle(time=row.time.to_pydatetime(), open=row.open, high=row.high,
                     low=row.low, close=row.close) for row in df.itertuples()]


def fail_stage_for(reason: str) -> str:
    if reason in REASON_TO_FAIL_STAGE:
        return REASON_TO_FAIL_STAGE[reason]
    if reason.startswith("FALSE_CHOCH_"):
        return "H1_CONTROL_SHIFT"
    return "UNMAPPED:" + reason


def run(cycle: str, symbol: str = "EURUSD"):
    prereg_sha = sha256_of_file(str(PREREG_PATH))
    h1_extended = load_mt5_csv(str(H1_EXTENDED_PATH))  # full Jan2025..Sep2026 series, D1/H4 source only
    h1_recent = load_mt5_csv(str(H1_HIST1Y_PATH))       # unchanged HIST1Y H1, used for H1 tail (as parent run)
    m15_raw = load_mt5_csv(str(M15_PATH))               # unchanged decision population

    d1_full = resample_ohlc(h1_extended, "1D")
    h4_full = resample_ohlc(h1_extended, "4h")

    start_hm, end_hm = SESSION_WINDOWS[cycle]
    days = sorted(set(m15_raw["time"].dt.floor("D")))

    decisions, trade_rows, trades_r = [], [], []
    funnel_reached = {s: 0 for s in FUNNEL_STAGES}
    funnel_failed_at = {s: 0 for s in FUNNEL_STAGES}
    unmapped_reasons: dict = {}

    for day in days:
        win_start = datetime.combine(day.date(), start_hm, tzinfo=timezone.utc)
        win_end = datetime.combine(day.date(), end_hm, tzinfo=timezone.utc)

        d1_closed = d1_full[d1_full["time"] + pd.Timedelta(days=1) <= win_start]       # FULL history, no tail()
        h4_closed = h4_full[h4_full["time"] + pd.Timedelta(hours=4) <= win_start]      # FULL history, no tail()
        h1_closed = h1_recent[h1_recent["time"] + pd.Timedelta(hours=1) <= win_end]
        m15_closed = m15_raw[m15_raw["time"] + pd.Timedelta(minutes=15) <= win_end]

        h1_tail = h1_closed.tail(TAIL_H1)
        m15_tail = m15_closed.tail(TAIL_M15)

        if len(d1_closed) < 10 or len(h4_closed) < 10 or len(h1_tail) < 10 or len(m15_tail) < 10:
            continue  # insufficient warm-up this early in the series

        d1_c, h4_c, h1_c, m15_c = (df_to_candles(x) for x in (d1_closed, h4_closed, h1_tail, m15_tail))
        try:
            decision = mtf_evaluate(symbol, cycle, d1_c, h4_c, h1_c, m15_c)
        except Exception as exc:  # defensive: record and continue, never silently fabricate
            decisions.append({"day": str(day.date()), "status": "ENGINE_ERROR", "reason": str(exc)})
            continue

        decisions.append({
            "day": str(day.date()), "status": decision.status, "reason": decision.reason_code,
            "n_d1_bars": len(d1_c), "n_h4_bars": len(h4_c),
        })

        # Funnel accounting: every stage up to (and not including) the failing stage is "reached".
        stage = fail_stage_for(decision.reason_code)
        if stage.startswith("UNMAPPED:"):
            unmapped_reasons[decision.reason_code] = unmapped_reasons.get(decision.reason_code, 0) + 1
        else:
            fail_idx = FUNNEL_STAGES.index(stage)
            for i in range(fail_idx + 1):
                funnel_reached[FUNNEL_STAGES[i]] += 1
            funnel_failed_at[stage] += 1

        if decision.status != "SIGNAL":
            continue

        after = m15_raw[m15_raw["time"] > decision.signal_timestamp]
        bars_after = df_to_candles(after)
        cutoff = datetime.combine(decision.signal_timestamp.date(), FORCE_FLAT_TIME, tzinfo=timezone.utc)

        result = resolve_two_leg_trade(
            direction=decision.direction,
            entry_price=decision.entry,
            initial_stop=decision.stop_loss,
            leg1_fraction=0.5,
            leg1_r_multiple=None,
            leg1_price_target=decision.tp1,
            leg2_r_multiple=None,
            leg2_price_target=decision.tp2,
            stage2_stop_is_breakeven=True,
            bars_after_decision=bars_after,
            order_type="LIMIT",
            limit_level=decision.entry,
            limit_expiry_time=decision.expiry_timestamp,
            hard_cutoff_time=cutoff,
            max_bars=700,
        )
        if result["filled"]:
            trades_r.append(result["realized_r"])
        trade_rows.append({
            "day": str(day.date()), "direction": decision.direction, "entry": decision.entry,
            "stop": decision.stop_loss, "tp1": decision.tp1, "tp2": decision.tp2,
            "signal_time": decision.signal_timestamp.isoformat(),
            "filled": result["filled"], "outcome": result["outcome"],
            "realized_r": result["realized_r"], "bars_used": result["bars_used"], "detail": result["detail"],
        })

    n_signals_total = len(trade_rows)
    n_unfilled = sum(1 for r in trade_rows if not r["filled"])
    metrics_gross = compute_metrics(trades_r, cost_r_per_trade=0.0)

    run_id = f"INT_C002_MTF_CONTROL_SHIFT_V1__{symbol}__{cycle}__LONGER_SAMPLE_R1"
    out_dir = REPO_ROOT / "research_external/candidate_factory/dev_replay" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(decisions).to_csv(out_dir / "decisions.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(out_dir / "trades.csv", index=False)
    funnel_report = {
        "stages": FUNNEL_STAGES,
        "n_days_evaluated": len(decisions),
        "reached_count": funnel_reached,
        "failed_at_count": funnel_failed_at,
        "unmapped_reasons": unmapped_reasons,
    }
    manifest = {
        "run_id": run_id,
        "candidate_id": "INT_C002",
        "strategy_id": "ST_MTF_CONTROL_SHIFT_V1",
        "strategy_version": "1.0.0",
        "trial_id": f"{cycle}_EURUSD_LONGER_SAMPLE_R1_v1",
        "prereg_id": "AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1_PREREG_V1",
        "prereg_sha256": prereg_sha,
        "parent_prereg_id": "AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_PREREG_V1",
        "parent_prereg_sha256": "342482c9972d1029d85b5ce4ab4792d4d147617d110aa88a6b020e32b707912b",
        "dataset_id": "DEV_EURUSD_H1_D1H4_WARMUP_EXTENDED_V1 (D1/H4) + DEV_EURUSD_H1_M15_HIST1Y_V1 (M15 decision population, unchanged)",
        "dataset_sha256": {
            "EURUSD_H1_WARMUP_EXTENDED_JAN2025_SEP2026.csv": sha256_of_file(str(H1_EXTENDED_PATH)),
            "HIST1Y_EURUSD_H1.csv": sha256_of_file(str(H1_HIST1Y_PATH)),
            "HIST1Y_EURUSD_M15.csv": sha256_of_file(str(M15_PATH)),
        },
        "engine_source": "research_external/candidate_factory/internal_reference/mtf_control_shift (copy of PR #34 @ 1d1c75c92a7fda80696a56d4e1ccbe402f3ab71a) -- IDENTICAL to parent run, not modified",
        "symbol": symbol, "cycle": cycle,
        "n_days_evaluated": len(decisions),
        "n_signals_total": n_signals_total,
        "n_signals_unfilled_limit": n_unfilled,
        "n_trades_filled": len(trades_r),
        "fill_rate": (len(trades_r) / n_signals_total) if n_signals_total else None,
        "replay_assumptions": [
            "D1/H4 derived from a longer, real H1 series (2025-01-01..2026-09-15) by causal OHLC resample",
            "D1/H4 passed to evaluate() as the FULL closed-to-date series (no tail-window truncation) -- the only "
            "deliberate change vs the parent run",
            "H1 and M15 still passed as bounded tail windows (60/150 bars), unchanged from the parent run",
            "stop-first-on-same-bar-collision (not defined by source spec), unchanged from parent run",
            "force-flat fill approximated at the bar OPEN of the first M15 bar at/after 21:00 UTC, unchanged from parent run",
        ],
        "metrics_gross_r": metrics_gross,
        "diagnostic_funnel": funnel_report,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with open(out_dir / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(metrics_gross, f, indent=2)
    with open(out_dir / "diagnostic_funnel.json", "w") as f:
        json.dump(funnel_report, f, indent=2)
    print(json.dumps({"run_id": run_id, "metrics": metrics_gross, "n_signals_total": n_signals_total,
                       "funnel_reached": funnel_reached, "funnel_failed_at": funnel_failed_at}, indent=2, default=str))
    return manifest, metrics_gross, funnel_report


if __name__ == "__main__":
    run("LONDON_NEWYORK")
    run("ASIAN_LONDON")
