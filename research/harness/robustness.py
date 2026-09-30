"""Robustness matrix over a canonical engine ledger (strategy-independent).

cost 1x/1.5x/2x, entry delay 1/2 bars, leave-one-symbol-out, leave-one-month-out,
drop best 1/5/10% trades, and a moving-block bootstrap CI of mean net R.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.harness import costs as _costs
from research.harness.fills import delay_entry

COST_MULTIPLIERS = (1.0, 1.5, 2.0)
ENTRY_DELAYS = (1, 2)
DROP_BEST = (0.01, 0.05, 0.10)


def summarize(net_r) -> dict:
    x = np.asarray(list(net_r), dtype=float)
    if x.size == 0:
        return {"n": 0, "total_R": 0.0, "mean_R": None, "win_rate": None, "profit_factor": None}
    wins, losses = x[x > 0].sum(), -x[x < 0].sum()
    return {"n": int(x.size), "total_R": float(x.sum()), "mean_R": float(x.mean()),
            "win_rate": float((x > 0).mean()),
            "profit_factor": float(wins / losses) if losses > 0 else (math.inf if wins > 0 else None)}


def block_bootstrap_ci(net_r, n_boot: int = 2000, block: int | None = None, alpha: float = 0.05,
                       seed: int = 0) -> dict:
    """Moving-block bootstrap of the mean over the exit-time-ordered trade sequence."""
    x = np.asarray(list(net_r), dtype=float)
    n = x.size
    if n < 2:
        return {"n": int(n), "block": None, "ci_low": None, "ci_high": None, "mean_R": summarize(x)["mean_R"]}
    b = block or max(1, math.ceil(n ** (1 / 3)))
    b = min(b, n)
    rng = np.random.default_rng(seed)
    k = math.ceil(n / b)
    starts = rng.integers(0, n - b + 1, size=(n_boot, k))
    idx = (starts[:, :, None] + np.arange(b)).reshape(n_boot, -1)[:, :n]
    means = x[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {"n": int(n), "block": int(b), "n_boot": n_boot, "seed": seed, "alpha": alpha,
            "mean_R": float(x.mean()), "ci_low": float(lo), "ci_high": float(hi)}


def drop_best(net_r, frac: float) -> dict:
    x = np.sort(np.asarray(list(net_r), dtype=float))[::-1]
    k = math.ceil(x.size * frac) if x.size else 0
    return {"dropped": int(k), **summarize(x[k:])}


def leave_one_out(costed: pd.DataFrame, key: pd.Series) -> dict:
    return {str(g): summarize(costed.loc[key != g, "net_R"]) for g in sorted(key.unique())}


def delayed_ledger(ledger: pd.DataFrame, bars_by_symbol: dict, delay: int,
                   max_bars: int | None = None) -> tuple[pd.DataFrame, int]:
    rows, skipped = [], 0
    for t in ledger.itertuples(index=False):
        d = delay_entry(t, bars_by_symbol[t.symbol], delay, max_bars)
        if d is None:
            skipped += 1
            continue
        rows.append({**t._asdict(), **d})
    out = pd.DataFrame(rows, columns=list(ledger.columns))
    return out.sort_values(["exit_time", "trade_id"], kind="stable").reset_index(drop=True), skipped


def run_matrix(ledger: pd.DataFrame, cost_model, bars_by_symbol: dict | None = None,
               max_bars: int | None = None, n_boot: int = 2000, seed: int = 0) -> dict:
    """ledger: output of ledger.load_engine_ledger. bars_by_symbol is needed only for entry delay."""
    base = _costs.apply_costs(ledger, cost_model, 1.0)
    out = {"baseline": {**summarize(base["net_R"]), "gross": summarize(base["gross_R"]),
                        "cost_breakdown_R": {c: float(base[c].sum()) for c in _costs.COST_COLUMNS}},
           "rollover_hour_utc": cost_model.rollover_hour_utc}
    out["cost"] = {f"{m}x": summarize(_costs.apply_costs(ledger, cost_model, m)["net_R"])
                   for m in COST_MULTIPLIERS}
    if bars_by_symbol is None:
        out["entry_delay"] = "NOT_EVALUATED: bars_by_symbol not supplied"
    else:
        out["entry_delay"] = {}
        for d in ENTRY_DELAYS:
            dl, skipped = delayed_ledger(ledger, bars_by_symbol, d, max_bars)
            s = summarize(_costs.apply_costs(dl, cost_model, 1.0)["net_R"]) if len(dl) else summarize([])
            out["entry_delay"][f"{d}_bar"] = {**s, "skipped_no_valid_fill": skipped}
    out["leave_one_symbol_out"] = leave_one_out(base, base["symbol"])
    out["leave_one_month_out"] = leave_one_out(base, base["exit_time"].dt.strftime("%Y-%m"))
    out["drop_best"] = {f"{int(f * 100)}pct": drop_best(base["net_R"], f) for f in DROP_BEST}
    out["block_bootstrap"] = block_bootstrap_ci(base["net_R"], n_boot=n_boot, seed=seed)
    return out
