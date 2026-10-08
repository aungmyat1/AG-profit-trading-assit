"""DEV replay runner for INT_C002 = ST_MTF_CONTROL_SHIFT_V1 (PR #34, research/shadow, OPEN).

Reproduces the ACTUAL candidate engine (byte-identical copy under
research_external/candidate_factory/internal_reference/mtf_control_shift/, provenance in
PROVENANCE.json in that directory) against the preregistered EURUSD H1+M15 ~1-year
dataset. D1 and H4 are derived from the real H1 series by simple causal OHLC resampling
(open=first, high=max, low=min, close=last); no separate D1/H4 acquisition exists in this
checkout, so this is the only way to feed the engine's declared 4-layer timeframe stack
without re-fetching data this sandbox does not have.

Performance note: the source engine's own zones()/structure_bias() helpers are O(n) per
call over whatever candle array is passed. All of the strategy's own lookback
requirements (swing strength=2, OB search 6 bars, H1 shift max age 4 bars, POI touch
lookback 4 bars, 3-candle FVG) are local/recent, so this harness passes bounded TAIL
WINDOWS (not the full history) at each evaluation step for computational tractability.
This is reported as an implementation choice, not a semantic change: a tail window is
mathematically equivalent to the full history for every function this engine calls,
EXCEPT `latest_fresh_zone`, which could in principle find an older fresh H4 zone further
back than the window if the window contains no fresh zone at all. The only possible bias
from this truncation is therefore towards MORE `NO_FRESH_H4_POI` / NO_TRADE outcomes, never
towards fabricating a signal that the full-history engine would not produce.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time, timedelta, timezone
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

PREREG_PATH = REPO_ROOT / "research_external/candidate_factory/PREREG_CANDIDATE_FACTORY_R1.json"
H1_PATH = REPO_ROOT / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_H1.csv"
M15_PATH = REPO_ROOT / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_M15.csv"

SESSION_WINDOWS = {
    "ASIAN_LONDON": (time(6, 0), time(9, 0)),
    "LONDON_NEWYORK": (time(11, 0), time(14, 0)),
}
TAIL_D1, TAIL_H4, TAIL_H1, TAIL_M15 = 40, 80, 60, 150
FORCE_FLAT_TIME = time(21, 0)


def df_to_candles(df: pd.DataFrame) -> list:
    return [MCandle(time=row.time.to_pydatetime(), open=row.open, high=row.high,
                     low=row.low, close=row.close) for row in df.itertuples()]


def run(cycle: str, symbol: str = "EURUSD"):
    prereg_sha = sha256_of_file(str(PREREG_PATH))
    h1_raw = load_mt5_csv(str(H1_PATH))
    m15_raw = load_mt5_csv(str(M15_PATH))
    d1_full = resample_ohlc(h1_raw, "1D")
    h4_full = resample_ohlc(h1_raw, "4h")

    start_hm, end_hm = SESSION_WINDOWS[cycle]
    days = sorted(set(m15_raw["time"].dt.floor("D")))

    decisions, trade_rows, trades_r = [], [], []

    for day in days:
        win_start = datetime.combine(day.date(), start_hm, tzinfo=timezone.utc)
        win_end = datetime.combine(day.date(), end_hm, tzinfo=timezone.utc)

        d1_closed = d1_full[d1_full["time"] + pd.Timedelta(days=1) <= win_start]
        h4_closed = h4_full[h4_full["time"] + pd.Timedelta(hours=4) <= win_start]
        h1_closed = h1_raw[h1_raw["time"] + pd.Timedelta(hours=1) <= win_end]
        m15_closed = m15_raw[m15_raw["time"] + pd.Timedelta(minutes=15) <= win_end]

        d1_tail = d1_closed.tail(TAIL_D1)
        h4_tail = h4_closed.tail(TAIL_H4)
        h1_tail = h1_closed.tail(TAIL_H1)
        m15_tail = m15_closed.tail(TAIL_M15)

        if len(d1_tail) < 10 or len(h4_tail) < 10 or len(h1_tail) < 10 or len(m15_tail) < 10:
            continue  # insufficient warm-up this early in the series

        d1_c, h4_c, h1_c, m15_c = (df_to_candles(x) for x in (d1_tail, h4_tail, h1_tail, m15_tail))
        try:
            decision = mtf_evaluate(symbol, cycle, d1_c, h4_c, h1_c, m15_c)
        except Exception as exc:  # defensive: record and continue, never silently fabricate
            decisions.append({"day": str(day.date()), "status": "ENGINE_ERROR", "reason": str(exc)})
            continue

        decisions.append({"day": str(day.date()), "status": decision.status, "reason": decision.reason_code})
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

    run_id = f"INT_C002_MTF_CONTROL_SHIFT_V1__{symbol}__{cycle}__HIST1Y"
    out_dir = REPO_ROOT / "research_external/candidate_factory/dev_replay" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(decisions).to_csv(out_dir / "decisions.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(out_dir / "trades.csv", index=False)
    manifest = {
        "run_id": run_id,
        "candidate_id": "INT_C002",
        "strategy_id": "ST_MTF_CONTROL_SHIFT_V1",
        "strategy_version": "1.0.0",
        "trial_id": f"{cycle}_EURUSD_HIST1Y_v1",
        "prereg_id": "AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_PREREG_V1",
        "prereg_sha256": prereg_sha,
        "dataset_id": "DEV_EURUSD_H1_M15_HIST1Y_V1",
        "dataset_sha256": {"EURUSD_H1.csv": sha256_of_file(str(H1_PATH)), "EURUSD_M15.csv": sha256_of_file(str(M15_PATH))},
        "engine_source": "research_external/candidate_factory/internal_reference/mtf_control_shift (copy of PR #34 @ 1d1c75c92a7fda80696a56d4e1ccbe402f3ab71a)",
        "symbol": symbol, "cycle": cycle,
        "n_days_evaluated": len(decisions),
        "n_signals_total": n_signals_total,
        "n_signals_unfilled_limit": n_unfilled,
        "n_trades_filled": len(trades_r),
        "fill_rate": (len(trades_r) / n_signals_total) if n_signals_total else None,
        "replay_assumptions": [
            "D1/H4 derived from real H1 by causal OHLC resample; no separate D1/H4 acquisition in this checkout",
            f"bounded tail windows passed to evaluate(): D1={TAIL_D1} H4={TAIL_H4} H1={TAIL_H1} M15={TAIL_M15} bars (see module docstring)",
            "stop-first-on-same-bar-collision (not defined by source spec)",
            "force-flat fill approximated at the bar OPEN of the first M15 bar at/after 21:00 UTC (no intrabar price available)",
        ],
        "metrics_gross_r": metrics_gross,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with open(out_dir / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(metrics_gross, f, indent=2)
    print(json.dumps({"run_id": run_id, "metrics": metrics_gross, "n_signals_total": n_signals_total}, indent=2, default=str))
    return manifest, metrics_gross


if __name__ == "__main__":
    run("LONDON_NEWYORK")
