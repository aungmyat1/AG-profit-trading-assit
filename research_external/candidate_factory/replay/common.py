"""Shared, candidate-neutral replay utilities for AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1.

This module is NEW for this mission. No equivalent generic replay/metrics module exists
elsewhere in this repository: `performance/` and `src/external_candidate/` are referenced
by several docs and scripts but are not physically present anywhere in this git history
(verified: `git log --all -- src/external_candidate` and a repo-wide `performance` module
search both return nothing; `scripts/generate_economic_evidence_report.py` and
`research_external/run_s2r_baseline.py` both currently fail with
`ModuleNotFoundError: No module named 'performance'` on a clean checkout of this branch).
This is documented in docs/status/AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_STATUS.md as a
pre-existing documentation/implementation drift finding, not something this mission
caused. `research_external/semantic/s2r.py` + `research_external/adapters/backtesting_py.py`
remain strategy-specific to S2R and are not reused here because they encode S2R's own
signal semantics; the generic OHLC loading / resampling / R-multiple bookkeeping below is
new but deliberately minimal and single-purpose for this mission's candidates.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Sequence

import pandas as pd


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_mt5_csv(path: str) -> pd.DataFrame:
    """Load an MT5-exported OHLC CSV with a `timestamp_utc` column (this repo's own
    data/research/*/raw/*.csv convention). Returns a UTC-indexed, sorted, deduplicated
    OHLC frame. Never invents bars; never fills gaps."""
    df = pd.read_csv(path)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df = df.rename(columns={"timestamp_utc": "time"})
    df = df.sort_values("time").drop_duplicates(subset="time")
    return df.set_index("time", drop=False)


def load_train_parquet_slice(path: str, start_utc: str, end_utc: str) -> pd.DataFrame:
    """Load the EURUSD_M5_S2R_RESEARCH parquet and return ONLY rows in [start_utc, end_utc).

    This performs the TRAIN-partition slice declared in
    research_external/datasets/manifests/TRAIN.json. It never reads past `end_utc`;
    callers must pass the TRAIN boundary only (never the VALIDATION or FINAL_HOLDOUT
    boundary) to keep this mission's sealed-data guarantee mechanical, not just a
    convention.
    """
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").drop_duplicates(subset="time")
    mask = (df["time"] >= pd.Timestamp(start_utc, tz="UTC")) & (df["time"] < pd.Timestamp(end_utc, tz="UTC"))
    out = df.loc[mask].set_index("time", drop=False)
    return out


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Simple causal OHLC resample: open=first, high=max, low=min, close=last.
    Bars are labeled/closed at the LEFT edge of their period (bar-open-time convention,
    matching this repo's own MT5 CSV export convention), and only periods with at least
    one source row are emitted (no synthetic/interpolated bars)."""
    agg = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    agg = agg.dropna(how="any")
    agg["time"] = agg.index
    return agg


def closed_before(df: pd.DataFrame, period_minutes: int, cutoff_utc: pd.Timestamp) -> pd.DataFrame:
    """Rows whose bar PERIOD has fully closed at/before cutoff_utc, i.e. bar_open_time +
    period <= cutoff_utc. Prevents using a still-forming higher-timeframe bar."""
    bar_close = df["time"] + pd.Timedelta(minutes=period_minutes)
    return df[bar_close <= cutoff_utc]


@dataclass
class TradeOutcome:
    candidate_id: str
    trial_id: str
    symbol: str
    cycle: str
    setup: str
    direction: str
    signal_time: datetime
    entry_order_type: str
    entry: float
    stop: float
    risk: float
    realized_r: float
    outcome: str
    leg_detail: str


def resolve_two_leg_trade(
    *,
    direction: str,
    entry_price: float,
    initial_stop: float,
    leg1_fraction: float,
    leg1_r_multiple: Optional[float],
    leg1_price_target: Optional[float],
    leg2_r_multiple: Optional[float],
    leg2_price_target: Optional[float],
    stage2_stop_is_breakeven: bool,
    bars_after_decision: Sequence,
    order_type: str,
    limit_level: Optional[float] = None,
    limit_expiry_time: Optional[datetime] = None,
    hard_cutoff_time: Optional[datetime] = None,
    max_bars: int = 700,
) -> dict:
    """Deterministic, closed-bar, stop-first-on-ambiguity trade resolver.

    Stop-first-on-same-bar collision is an explicit REPLAY_ASSUMPTION of this harness
    (neither SESSION_TRADE_V2 nor ST_MTF_CONTROL_SHIFT_V1's own spec defines same-M15-bar
    SL/TP sequencing); it is conservative (never reports a better outcome than what a
    pessimistic ordering would give) and is reported in every run_manifest.json produced
    by this harness, consistent with this repository's own documented awareness of the
    same ambiguity in docs/specs/EXTERNAL_SOURCE_STRATEGY_SPEC_DRAFT.md (#18).

    Returns a dict with: outcome, realized_r (in units of the ORIGINAL leg1 risk),
    bars_used, filled (bool), detail (str).
    """
    sign = 1.0 if direction == "LONG" else -1.0
    risk = abs(entry_price - initial_stop)
    if risk <= 0:
        return {"outcome": "INVALID_RISK", "realized_r": 0.0, "bars_used": 0, "filled": False, "detail": "non-positive risk"}

    bars = list(bars_after_decision)
    idx = 0
    filled = order_type == "MARKET"
    fill_price = entry_price if filled else None

    if not filled:
        while idx < len(bars):
            b = bars[idx]
            if limit_expiry_time is not None and b.time > limit_expiry_time:
                return {"outcome": "LIMIT_EXPIRED_UNFILLED", "realized_r": 0.0, "bars_used": idx, "filled": False, "detail": "limit never touched before expiry"}
            if b.low <= limit_level <= b.high:
                filled = True
                fill_price = limit_level
                idx += 1  # resolution starts the bar AFTER the fill bar (conservative; a
                          # same-bar fill+resolve is not derivable from OHLC alone)
                break
            idx += 1
        if not filled:
            return {"outcome": "LIMIT_EXPIRED_UNFILLED", "realized_r": 0.0, "bars_used": idx, "filled": False, "detail": "limit never touched"}

    stage1_target_price = leg1_price_target if leg1_price_target is not None else fill_price + sign * leg1_r_multiple * risk
    stage = 1
    stage2_stop_price = fill_price  # breakeven
    stage2_target_price = leg2_price_target if leg2_price_target is not None else (
        fill_price + sign * leg2_r_multiple * risk if leg2_r_multiple is not None else None
    )
    bars_used = idx
    leg1_r = None
    leg2_r = None

    while idx < len(bars) and bars_used < max_bars:
        b = bars[idx]
        if hard_cutoff_time is not None and b.time >= hard_cutoff_time:
            # force-flat at first bar at/after the cutoff, using that bar's open as the
            # best available non-lookahead approximation of the force-close fill.
            mtm_price = b.open
            if stage == 1:
                return {
                    "outcome": "FORCE_FLAT_STAGE1",
                    "realized_r": sign * (mtm_price - fill_price) / risk,
                    "bars_used": bars_used, "filled": True,
                    "detail": f"force-flat at cutoff {hard_cutoff_time.isoformat()}",
                }
            leg2_r = sign * (mtm_price - fill_price) / risk
            total = leg1_fraction * leg1_r + (1 - leg1_fraction) * leg2_r
            return {"outcome": "FORCE_FLAT_STAGE2", "realized_r": total, "bars_used": bars_used,
                    "filled": True, "detail": f"leg1={leg1_r:.3f}R force-flat leg2={leg2_r:.3f}R"}
        if stage == 1:
            hit_stop = (b.low <= initial_stop) if direction == "LONG" else (b.high >= initial_stop)
            hit_target = (b.high >= stage1_target_price) if direction == "LONG" else (b.low <= stage1_target_price)
            if hit_stop and hit_target:
                hit_target = False  # stop-first-on-ambiguity REPLAY_ASSUMPTION
            if hit_stop:
                return {"outcome": "STOPPED_STAGE1_FULL_LOSS", "realized_r": -1.0, "bars_used": bars_used + 1,
                        "filled": True, "detail": "initial stop hit before leg1 target; both legs out"}
            if hit_target:
                leg1_r = sign * (stage1_target_price - fill_price) / risk
                stage = 2
                if not stage2_stop_is_breakeven:
                    stage2_stop_price = initial_stop
        else:
            hit_stop2 = (b.low <= stage2_stop_price) if direction == "LONG" else (b.high >= stage2_stop_price)
            hit_target2 = False
            if stage2_target_price is not None:
                hit_target2 = (b.high >= stage2_target_price) if direction == "LONG" else (b.low <= stage2_target_price)
            if hit_stop2 and hit_target2:
                hit_target2 = False
            if hit_stop2:
                leg2_r = sign * (stage2_stop_price - fill_price) / risk
                total = leg1_fraction * leg1_r + (1 - leg1_fraction) * leg2_r
                return {"outcome": "STAGE2_STOPPED", "realized_r": total, "bars_used": bars_used + 1,
                        "filled": True, "detail": f"leg1={leg1_r:.3f}R leg2_stopped={leg2_r:.3f}R"}
            if hit_target2:
                leg2_r = sign * (stage2_target_price - fill_price) / risk
                total = leg1_fraction * leg1_r + (1 - leg1_fraction) * leg2_r
                return {"outcome": "STAGE2_TARGET_HIT", "realized_r": total, "bars_used": bars_used + 1,
                        "filled": True, "detail": f"leg1={leg1_r:.3f}R leg2={leg2_r:.3f}R"}
        idx += 1
        bars_used += 1

    # ran out of bars/budget without full resolution
    if stage == 1:
        mtm = bars[-1].close if bars else fill_price
        return {"outcome": "OPEN_AT_CUTOFF_STAGE1", "realized_r": sign * (mtm - fill_price) / risk,
                "bars_used": bars_used, "filled": True, "detail": "no resolution within max_bars"}
    mtm = bars[-1].close if bars else fill_price
    leg2_r = sign * (mtm - fill_price) / risk
    total = leg1_fraction * leg1_r + (1 - leg1_fraction) * leg2_r
    return {"outcome": "OPEN_AT_CUTOFF_STAGE2", "realized_r": total, "bars_used": bars_used,
            "filled": True, "detail": f"leg1={leg1_r:.3f}R leg2_open={leg2_r:.3f}R"}


def compute_metrics(trade_r: List[float], cost_r_per_trade: float = 0.0) -> dict:
    """R-multiple metrics on a list of already-resolved trade R values (gross). Applies a
    flat per-trade cost in R units (friction) to produce net figures. NEW module (see
    header docstring for why no existing repo module is reused/duplicated)."""
    n = len(trade_r)
    if n == 0:
        return {"n": 0, "note": "no trades"}
    net = [r - cost_r_per_trade for r in trade_r]
    wins = [r for r in net if r > 0]
    losses = [r for r in net if r <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    run = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in net:
        run += r
        peak = max(peak, run)
        max_dd = max(max_dd, peak - run)
        equity.append(run)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    largest_abs = max((abs(r) for r in net), default=0.0)
    total_abs_net = sum(abs(r) for r in net) or 1.0
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n,
        "gross_r": sum(trade_r),
        "net_r": sum(net),
        "expectancy_r": sum(net) / n,
        "profit_factor": pf,
        "max_drawdown_r": max_dd,
        "largest_single_trade_r": largest_abs,
        "largest_trade_pct_of_total_abs_net_r": largest_abs / total_abs_net,
        "cost_r_per_trade_applied": cost_r_per_trade,
    }
