"""Category breakdown, ablation deltas and failure diagnosis over ledger/trade rows.

Pure functions over plain dicts. Cells with N < MIN_CELL_N are INSUFFICIENT and carry
no metric-based conclusion; diagnosis only ever reads cells with N >= MIN_CELL_N.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Sequence

MIN_CELL_N = 30

CATEGORY_FIELDS = {
    "symbol": "symbol",
    "session": "session_pair",
    "direction": "direction",
    "regime": "regime",
    "setup_type": "setup_model",
    "entry": "entry_number",
    "exit": "outcome_class",
}


def metrics(returns: Sequence[float]) -> dict:
    """N, expectancy (mean R), profit factor, max drawdown (R, peak-to-trough of the
    cumulative sequence), win rate. Empty input -> N=0 and None metrics."""
    r = [float(x) for x in returns]
    n = len(r)
    if n == 0:
        return {"n": 0, "expectancy_R": None, "profit_factor": None, "max_drawdown_R": None, "win_rate": None}
    gains = sum(x for x in r if x > 0)
    losses = -sum(x for x in r if x < 0)
    peak = cum = mdd = 0.0
    for x in r:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return {
        "n": n,
        "expectancy_R": sum(r) / n,
        "profit_factor": (gains / losses) if losses > 0 else (float("inf") if gains > 0 else None),
        "max_drawdown_R": mdd,
        "win_rate": sum(1 for x in r if x > 0) / n,
    }


def category_table(rows: Iterable[dict], value_field: str = "vt_net_R",
                   population: str = "frozen_baseline") -> List[dict]:
    """One row per (category, value). population='frozen_baseline' keeps only candidates
    the frozen engine actually filled; 'all_candidates' uses every counterfactual fill."""
    rows = [r for r in rows if r.get(value_field) is not None]
    if population == "frozen_baseline":
        rows = [r for r in rows if r.get("in_frozen_baseline")]
    out = []
    for category, field in CATEGORY_FIELDS.items():
        cells: Dict[object, List[float]] = defaultdict(list)
        for r in rows:
            cells[r.get(field)].append(r[value_field])
        for value in sorted(cells, key=str):
            m = metrics(cells[value])
            status = "OK" if m["n"] >= MIN_CELL_N else "INSUFFICIENT"
            if status == "INSUFFICIENT":
                m = {"n": m["n"], "expectancy_R": None, "profit_factor": None,
                     "max_drawdown_R": None, "win_rate": None}
            out.append({"category": category, "value": str(value), "population": population,
                        "status": status, **m})
    return out


def rule_rejection_table(rows: Iterable[dict], gates: Sequence[str]) -> List[dict]:
    """Counterfactual economics of candidates each gate rejected (ALL_RELAXED path)."""
    rows = [r for r in rows if r.get("vt_net_R") is not None]
    out = []
    for g in gates:
        vals = [r["vt_net_R"] for r in rows if r.get(g) == "FAIL"]
        m = metrics(vals)
        status = "OK" if m["n"] >= MIN_CELL_N else "INSUFFICIENT"
        out.append({"gate": g, "status": status, **(m if status == "OK" else {"n": m["n"]})})
    return out


def ablation_deltas(baseline: Sequence[float], variants: Dict[str, Sequence[float]]) -> List[dict]:
    """Delta expectancy / PF / drawdown / N of each re-run versus the frozen baseline."""
    b = metrics(baseline)
    out = []
    for name, rets in variants.items():
        m = metrics(rets)

        def d(key):
            if m[key] is None or b[key] is None:
                return None
            if float("inf") in (m[key], b[key]):
                return None
            return m[key] - b[key]
        out.append({"run": name, **m, "delta_n": m["n"] - b["n"],
                    "delta_expectancy_R": d("expectancy_R"), "delta_profit_factor": d("profit_factor"),
                    "delta_max_drawdown_R": d("max_drawdown_R"),
                    "status": "OK" if m["n"] >= MIN_CELL_N and b["n"] >= MIN_CELL_N else "INSUFFICIENT"})
    return out


def failure_diagnosis(cells: Iterable[dict], top: int = 3) -> List[dict]:
    """Top loss causes = the N>=30 cells with the most negative total R contribution
    (expectancy x N). INSUFFICIENT cells are never eligible."""
    eligible = [c for c in cells if c.get("status") == "OK" and c.get("expectancy_R") is not None
                and c["expectancy_R"] < 0]
    ranked = sorted(eligible, key=lambda c: c["expectancy_R"] * c["n"])
    return [{"rank": i + 1, "category": c["category"], "value": c["value"], "n": c["n"],
             "expectancy_R": c["expectancy_R"], "total_R": c["expectancy_R"] * c["n"]}
            for i, c in enumerate(ranked[:top])]
