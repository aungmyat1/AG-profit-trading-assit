"""Walk-forward, CPCV, PBO (CSCV) and Deflated Sharpe Ratio, plus the verdict rule.

Open-source-equivalent implementations (pypbo is unmaintained/not on the pinned
toolchain), following:
  - Bailey, Borwein, Lopez de Prado, Zhu (2016) "The Probability of Backtest
    Overfitting" -- CSCV / PBO.
  - Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio".
  - Lopez de Prado (2018) AFML ch.12 -- combinatorial purged cross-validation.
Variants are FIXED rule sets (no fitting inside folds), so CV here only partitions
evaluation periods; the multiple-testing penalty counts EVERY configuration evaluated.
"""
from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist
from typing import Dict, List, Sequence

from research.attribution.analysis import MIN_CELL_N, metrics

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def daily_matrix(trades_by_run: Dict[str, List[dict]]) -> tuple:
    """Sum of net R per trading_date per run over the union of dates (0 = no trade)."""
    dates = sorted({t["trading_date"] for ts in trades_by_run.values() for t in ts})
    idx = {d: i for i, d in enumerate(dates)}
    names = list(trades_by_run)
    mat = [[0.0] * len(names) for _ in dates]
    for j, name in enumerate(names):
        for t in trades_by_run[name]:
            mat[idx[t["trading_date"]]][j] += t["net_R"]
    return dates, names, mat


def _sharpe(x: Sequence[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mu = sum(x) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1))
    return mu / sd if sd > 0 else 0.0


def pbo_cscv(mat: List[List[float]], n_groups: int = 8) -> dict:
    """PBO via CSCV over a T x N performance matrix (rows = periods, cols = trials)."""
    t, n = len(mat), (len(mat[0]) if mat else 0)
    if n < 2 or t < n_groups * 2:
        return {"pbo": None, "status": "INSUFFICIENT", "splits": 0}
    size = t // n_groups
    groups = [list(range(g * size, (g + 1) * size if g < n_groups - 1 else t)) for g in range(n_groups)]
    logits = []
    for is_groups in combinations(range(n_groups), n_groups // 2):
        is_rows = [r for g in is_groups for r in groups[g]]
        oos_rows = [r for g in range(n_groups) if g not in is_groups for r in groups[g]]
        is_perf = [_sharpe([mat[r][j] for r in is_rows]) for j in range(n)]
        oos_perf = [_sharpe([mat[r][j] for r in oos_rows]) for j in range(n)]
        best = max(range(n), key=lambda j: is_perf[j])
        rank = sum(1 for v in oos_perf if v <= oos_perf[best])  # 1..n
        omega = rank / (n + 1)
        logits.append(math.log(omega / (1 - omega)))
    return {"pbo": sum(1 for l in logits if l <= 0) / len(logits), "status": "OK", "splits": len(logits)}


def deflated_sharpe(returns: Sequence[float], n_trials: int, trial_sharpes: Sequence[float]) -> dict:
    """DSR = P(true SR > SR0) where SR0 is the expected max SR of n_trials
    unskilled trials (per-period SR units)."""
    x = [float(v) for v in returns]
    t = len(x)
    if t < 3 or n_trials < 1:
        return {"dsr": None, "status": "INSUFFICIENT"}
    sr = _sharpe(x)
    mu = sum(x) / t
    sd = math.sqrt(sum((v - mu) ** 2 for v in x) / t) or 1e-12
    skew = sum(((v - mu) / sd) ** 3 for v in x) / t
    kurt = sum(((v - mu) / sd) ** 4 for v in x) / t
    if n_trials == 1:
        sr0 = 0.0
    else:
        s = list(trial_sharpes)
        m = sum(s) / len(s)
        var_sr = sum((v - m) ** 2 for v in s) / max(len(s) - 1, 1)
        sr0 = math.sqrt(var_sr) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
                                   + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e)))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return {"dsr": None, "status": "DEGENERATE_MOMENTS"}
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(denom)
    return {"dsr": _N.cdf(z), "sr": sr, "sr0": sr0, "n_trials": n_trials, "status": "OK"}


def cpcv_oos(mat: List[List[float]], names: List[str], n_groups: int = 6, k: int = 2,
             embargo: int = 1) -> Dict[str, dict]:
    """Per-run OOS mean daily R across all C(n_groups, k) test combinations; the
    `embargo` rows after each test block are purged from train (inert for fixed rule
    sets, kept so the split geometry matches AFML ch.12)."""
    t = len(mat)
    if t < n_groups * 2:
        return {n: {"status": "INSUFFICIENT"} for n in names}
    size = t // n_groups
    bounds = [(g * size, (g + 1) * size if g < n_groups - 1 else t) for g in range(n_groups)]
    out = {}
    for j, name in enumerate(names):
        means = []
        for test in combinations(range(n_groups), k):
            rows = [r for g in test for r in range(*bounds[g])]
            means.append(sum(mat[r][j] for r in rows) / len(rows))
        pos = sum(1 for m in means if m > 0)
        out[name] = {"status": "OK", "splits": len(means), "mean_oos_daily_R": sum(means) / len(means),
                     "share_positive_splits": pos / len(means), "embargo_rows": embargo}
    return out


def walk_forward(trades: List[dict], n_folds: int = 5) -> dict:
    """Anchored walk-forward for a FIXED rule set: dates split into n_folds+1
    chronological blocks; block 0 is the initial in-sample, blocks 1..n are OOS."""
    dates = sorted({t["trading_date"] for t in trades})
    if len(dates) < n_folds + 1:
        return {"status": "INSUFFICIENT", "oos": metrics([])}
    size = len(dates) // (n_folds + 1)
    oos_start = dates[size]
    oos = [t["net_R"] for t in sorted(trades, key=lambda t: t["entry_time"]) if t["trading_date"] >= oos_start]
    return {"status": "OK", "oos_start": oos_start, "folds": n_folds, "oos": metrics(oos)}


def verdict(oos: dict, dsr: dict, pbo: dict) -> str:
    """DEMO_READY only if net expectancy>0, PF>1, OOS N>=30, DSR>0.95, PBO<0.5.
    REJECT when OOS evidence with N>=30 is non-positive or PBO>=0.5; else RETEST."""
    n = oos.get("n", 0)
    e, pf = oos.get("expectancy_R"), oos.get("profit_factor")
    d, p = dsr.get("dsr"), pbo.get("pbo")
    if n >= MIN_CELL_N and e is not None and pf is not None and (e <= 0 or pf <= 1):
        return "REJECT"
    if p is not None and p >= 0.5:
        return "REJECT"
    if (n >= MIN_CELL_N and e is not None and e > 0 and pf is not None and pf > 1
            and d is not None and d > 0.95 and p is not None and p < 0.5):
        return "DEMO_READY"
    return "RETEST"
