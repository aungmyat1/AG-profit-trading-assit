"""Phase 8 -- fast-screen metrics over replayed trades. Pure arithmetic, no judgment:
the promotion policy (promotion.py) interprets these numbers; this module never sets a
status. Small N is reported as-is -- no statistical significance is invented.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .replay_c001 import TradeRecord

# 4-hour UTC entry buckets -- a deterministic decomposition, not a session claim.
_TIME_BUCKETS = ("00-04", "04-08", "08-12", "12-16", "16-20", "20-24")


def _bucket(hour: int) -> str:
    return _TIME_BUCKETS[hour // 4]


def _safe_div(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def _core(trades: Sequence[TradeRecord]) -> Dict:
    n = len(trades)
    gross = sum(t.gross_r for t in trades)
    net = sum(t.net_r for t in trades)
    cost = sum(t.cost_r for t in trades)
    wins = [t.net_r for t in trades if t.net_r > 0]
    losses = [t.net_r for t in trades if t.net_r <= 0]

    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda t: t.entry_time_utc):
        equity += t.net_r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    gross_wins = sum(t.gross_r for t in trades if t.gross_r > 0)
    return {
        "N": n,
        "LONG_N": sum(1 for t in trades if t.direction == "LONG"),
        "SHORT_N": sum(1 for t in trades if t.direction == "SHORT"),
        "GROSS_R": gross,
        "NET_R": net,
        "COST_R": cost,
        "GROSS_EXPECTANCY_R": _safe_div(gross, n),
        "NET_EXPECTANCY_R": _safe_div(net, n),
        "WIN_RATE": _safe_div(float(len(wins)), n),
        "AVG_WIN_R": _safe_div(sum(wins), len(wins)),
        "AVG_LOSS_R": _safe_div(sum(losses), len(losses)),
        "PROFIT_FACTOR_NET": _safe_div(sum(wins), abs(sum(losses))) if losses else
                             (None if not wins else float("inf")),
        "MAX_DRAWDOWN_R": max_dd,
        "COST_TO_GROSS_PROFIT": _safe_div(cost, gross_wins),
    }


def compute_metrics(trades: Sequence[TradeRecord]) -> Dict:
    """Full Phase-8 metric block: combined core metrics plus per-symbol, per-side,
    time-bucket, and H1-structure regime decompositions (the H1 structure state at
    entry is the existing regime authority recorded by the frozen contract)."""
    metrics = _core(trades)
    metrics["BY_SYMBOL"] = {sym: _core([t for t in trades if t.symbol == sym])
                            for sym in sorted({t.symbol for t in trades})}
    metrics["BY_DIRECTION"] = {d: _core([t for t in trades if t.direction == d])
                               for d in ("LONG", "SHORT")}
    metrics["TIME_BUCKET_DECOMPOSITION"] = {
        b: _core([t for t in trades if _bucket(t.entry_hour_utc) == b])
        for b in _TIME_BUCKETS if any(_bucket(t.entry_hour_utc) == b for t in trades)}
    metrics["REGIME_DECOMPOSITION"] = {
        regime: _core([t for t in trades if t.h1_regime_at_entry == regime])
        for regime in sorted({t.h1_regime_at_entry for t in trades})}
    metrics["REGIME_AUTHORITY"] = "crypto_cfd_contract H1 confirmed-break structure state"
    return metrics
