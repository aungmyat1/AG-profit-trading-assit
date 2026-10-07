"""DEV replay runner for OSS_FX_C001 = Opening Range Breakout (ORB), the LONDON_NEWYORK
external comparator.

RULE EXTRACTION ONLY (per the EXTERNAL CODE RULE: no external package is installed,
imported, or executed). The rule below is transcribed directly from:

  - Zarattini, C. & Aziz, A. (2023), "Can Day Trading Really Be Profitable? Evidence of
    Sustainable Long-term Profits from Opening Range Breakout (ORB) Day Trading Strategy
    vs. Benchmark in the US Stock Market", SSRN 4416622.
  - Secondary summary: cxoadvisory.com "Day Trading with an Opening Range Breakout
    Strategy" (2023-05-08), used to confirm the rule-by-rule description below.
  - Independent replication for methodology cross-check only (not executed, not
    imported): github.com/giovannibrusco/zarattini-2023-orb-qqq (MIT license).

Original source rule (US equities, QQQ, 5-minute bars, NYSE open):
  1. If the first 5-minute bar of the session closes above its open, go LONG at the
     OPEN of the second 5-minute bar; if it closes below its open, go SHORT; if
     "about the same", take no position (doji filter; the paper's exact numeric
     threshold for "about the same" is not given in the secondary summary available to
     this mission -- UNKNOWN. This harness uses |close-open| < 0.1 * (high-low) of the
     opening bar as its OWN operational threshold, NOT sourced from the paper -- flagged
     REPLAY_ASSUMPTION).
  2. Stop-loss at the low (long) / high (short) of the first 5-minute bar.
  3. Profit target at 10x the absolute entry-to-stop distance.
  4. Flat by session end if neither is hit.

Venue/session translation for this mission (explicit, not inherited from the source):
  - Source market: US equities cash session open (9:30 ET / 13:30 UTC during EDT).
  - This candidate: EURUSD, FX, "opening bar" = the first CLOSED M5 bar of AG's own
    LONDON_NEWYORK trade window (11:00-11:05 UTC), i.e. the overlap session this mission
    is asked to prioritize discovery for. This is a TRANSLATION_FIDELITY=
    MATERIAL_DEVIATION from the source (different instrument, different venue, different
    "opening" definition) -- the source's reported backtest performance (annualized alpha
    33% net of commissions on QQQ 2016-2023) is explicitly NOT inherited as evidence for
    this FX candidate. Only the mechanical rule is reused.
  - "Session end" = end of the LONDON_NEWYORK trade window (14:00 UTC), not a single
    daily market close (FX has none).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research_external.candidate_factory.replay.common import (  # noqa: E402
    compute_metrics,
    load_train_parquet_slice,
    resolve_two_leg_trade,
    sha256_of_file,
)

PREREG_PATH = REPO_ROOT / "research_external/candidate_factory/PREREG_CANDIDATE_FACTORY_R1.json"
PARQUET_PATH = REPO_ROOT / "research_external/datasets/EURUSD_M5_S2R_RESEARCH.parquet"
TRAIN_START = "2025-07-01"
TRAIN_END = "2026-04-01"
WINDOW_START = (11, 0)
WINDOW_END = (14, 0)
DOJI_FRACTION = 0.10  # REPLAY_ASSUMPTION, see module docstring
TARGET_R_MULTIPLE = 10.0


class SimpleBar:
    __slots__ = ("time", "open", "high", "low", "close")

    def __init__(self, time, open_, high, low, close):
        self.time, self.open, self.high, self.low, self.close = time, open_, high, low, close


def run(symbol: str = "EURUSD"):
    prereg_sha = sha256_of_file(str(PREREG_PATH))
    m5 = load_train_parquet_slice(str(PARQUET_PATH), TRAIN_START, TRAIN_END)
    days = sorted(set(m5["time"].dt.floor("D")))

    decisions, trade_rows, trades_r = [], [], []

    for day in days:
        win_start = day.replace(hour=WINDOW_START[0], minute=WINDOW_START[1])
        win_end = day.replace(hour=WINDOW_END[0], minute=WINDOW_END[1])
        window = m5[(m5["time"] >= win_start) & (m5["time"] < win_end)]
        if len(window) < 2:
            continue
        rows = list(window.itertuples())
        opening = rows[0]
        rng = opening.high - opening.low
        if rng <= 0:
            continue
        body = opening.close - opening.open
        if abs(body) < DOJI_FRACTION * rng:
            decisions.append({"day": str(day.date()), "status": "NO_TRADE", "reason": "DOJI_FILTER"})
            continue
        direction = "LONG" if body > 0 else "SHORT"
        second = rows[1]
        entry = second.open
        stop = opening.low if direction == "LONG" else opening.high
        risk = abs(entry - stop)
        if risk <= 0:
            decisions.append({"day": str(day.date()), "status": "NO_TRADE", "reason": "NON_POSITIVE_RISK"})
            continue
        decisions.append({"day": str(day.date()), "status": "SIGNAL", "reason": "READY", "direction": direction})

        bars_after = [SimpleBar(r.time.to_pydatetime(), r.open, r.high, r.low, r.close) for r in rows[2:]]
        cutoff = win_end
        result = resolve_two_leg_trade(
            direction=direction, entry_price=entry, initial_stop=stop,
            leg1_fraction=1.0, leg1_r_multiple=TARGET_R_MULTIPLE, leg1_price_target=None,
            leg2_r_multiple=None, leg2_price_target=None, stage2_stop_is_breakeven=True,
            bars_after_decision=bars_after, order_type="MARKET",
            hard_cutoff_time=cutoff, max_bars=100,
        )
        if result["filled"]:
            trades_r.append(result["realized_r"])
        trade_rows.append({
            "day": str(day.date()), "direction": direction, "entry": entry, "stop": stop,
            "risk": risk, "outcome": result["outcome"], "realized_r": result["realized_r"],
            "bars_used": result["bars_used"], "detail": result["detail"],
        })

    metrics_gross = compute_metrics(trades_r, cost_r_per_trade=0.0)
    run_id = f"OSS_FX_C001_ORB_NY_OPEN__{symbol}__LONDON_NEWYORK__TRAIN"
    out_dir = REPO_ROOT / "research_external/candidate_factory/dev_replay" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(decisions).to_csv(out_dir / "decisions.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(out_dir / "trades.csv", index=False)
    manifest = {
        "run_id": run_id, "candidate_id": "OSS_FX_C001", "strategy_id": "OSS_FX_C001_ORB_NY_OPEN",
        "source": "Zarattini & Aziz 2023 (SSRN 4416622); rule extracted, no code imported/executed",
        "trial_id": "EURUSD_LONDON_NEWYORK_TRAIN_v1",
        "prereg_id": "AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_PREREG_V1", "prereg_sha256": prereg_sha,
        "dataset_id": "DEV_EURUSD_M5_TRAIN_V1", "dataset_sha256_parent": sha256_of_file(str(PARQUET_PATH)),
        "symbol": symbol, "cycle": "LONDON_NEWYORK",
        "n_days_evaluated": len(decisions), "n_trades_filled": len(trades_r),
        "replay_assumptions": [
            "doji filter threshold |close-open|<0.10*range is this harness's own operationalization, not sourced from the paper (UNKNOWN exact threshold)",
            "venue/instrument translation is MATERIAL_DEVIATION (US equities 5-min ORB -> FX EURUSD M5 at the LONDON_NEWYORK window open); source paper's reported results are NOT inherited as evidence",
            "stop-first-on-same-bar-collision",
            "flat at window end (14:00 UTC) if unresolved, mark-to-market at that bar's open",
        ],
        "metrics_gross_r": metrics_gross,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with open(out_dir / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(metrics_gross, f, indent=2)
    print(json.dumps({"run_id": run_id, "metrics": metrics_gross}, indent=2, default=str))
    return manifest, metrics_gross


if __name__ == "__main__":
    run()
