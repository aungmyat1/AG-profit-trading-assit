"""Research-only GEN_001 replay of frozen trades under duration caps.

CONTROL preserves the supplied authoritative exit. Duration policies inspect only M1
bars strictly after entry, stop at the earlier of the original exit and duration cap,
and apply SL/optional TP first. A bar touching SL and TP is rejected as ambiguous.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

POLICIES = ("CONTROL", "30", "45", "60", "90", "120")
HORIZONS = (15, 30, 60, 90)


class EvidenceError(ValueError):
    """Fail-closed input/replay error."""


def _dt(value: str) -> datetime:
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"invalid timestamp: {value!r}") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise EvidenceError(f"timezone-aware timestamp required: {value!r}")
    return out.astimezone(timezone.utc)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    stop_loss: float
    original_exit_time: datetime
    original_exit_price: float
    take_profit: float | None = None
    spread_cost_r: float = 0.0
    commission_cost_r: float = 0.0
    slippage_cost_r: float = 0.0
    strategy_id: str = "UNKNOWN"
    strategy_version: str = "UNKNOWN"


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


def load_trades(path: str | Path) -> list[Trade]:
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    required = {"trade_id", "symbol", "side", "entry_time", "entry_price", "stop_loss", "original_exit_time", "original_exit_price", "spread_cost_r", "commission_cost_r", "slippage_cost_r"}
    if not rows or not required.issubset(rows[0]):
        raise EvidenceError(f"trade CSV missing required columns: {sorted(required)}")
    trades = []
    for r in rows:
        side = r["side"].upper()
        if side not in {"LONG", "SHORT"}:
            raise EvidenceError(f"{r['trade_id']}: side must be LONG or SHORT")
        costs = [float(r[k]) for k in ("spread_cost_r", "commission_cost_r", "slippage_cost_r")]
        if any(x < 0 for x in costs):
            raise EvidenceError(f"{r['trade_id']}: negative friction")
        entry, stop = float(r["entry_price"]), float(r["stop_loss"])
        if abs(entry - stop) <= 0:
            raise EvidenceError(f"{r['trade_id']}: invalid stop distance")
        et, xt = _dt(r["entry_time"]), _dt(r["original_exit_time"])
        if xt <= et:
            raise EvidenceError(f"{r['trade_id']}: exit must follow entry")
        trades.append(Trade(r["trade_id"], r["symbol"], side, et, entry, stop, xt,
                            float(r["original_exit_price"]), float(r["take_profit"]) if r.get("take_profit") else None,
                            *costs, r.get("strategy_id") or "UNKNOWN", r.get("strategy_version") or "UNKNOWN"))
    if len({t.trade_id for t in trades}) != len(trades):
        raise EvidenceError("duplicate trade_id")
    return trades


def load_candles(path: str | Path) -> list[Candle]:
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    required = {"symbol", "timestamp", "open", "high", "low", "close"}
    if not rows or not required.issubset(rows[0]):
        raise EvidenceError(f"candle CSV missing required columns: {sorted(required)}")
    out = [Candle(r["symbol"], _dt(r["timestamp"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])) for r in rows]
    for c in out:
        if not (c.high >= max(c.open, c.close) and c.low <= min(c.open, c.close)):
            raise EvidenceError(f"invalid OHLC at {c.timestamp.isoformat()}")
    for a, b in zip(out, out[1:]):
        if b.timestamp <= a.timestamp:
            raise EvidenceError("duplicate or unordered candles")
    return out


def entry_population_hash(trades: Sequence[Trade]) -> str:
    rows = [{"trade_id": t.trade_id, "symbol": t.symbol, "side": t.side,
             "entry_time": t.entry_time.isoformat(), "entry_price": t.entry_price,
             "stop_loss": t.stop_loss} for t in sorted(trades, key=lambda x: x.trade_id)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _r(t: Trade, price: float) -> float:
    direction = 1 if t.side == "LONG" else -1
    return direction * (price - t.entry_price) / abs(t.entry_price - t.stop_loss)


def _slice(t: Trade, candles: Sequence[Candle], end: datetime) -> list[Candle]:
    if any(c.symbol != t.symbol for c in candles):
        raise EvidenceError(f"{t.trade_id}: symbol mismatch")
    selected = [c for c in candles if t.entry_time < c.timestamp <= end]
    expected_end = max(t.original_exit_time, t.entry_time + timedelta(minutes=120))
    if not candles or candles[0].timestamp > t.entry_time + timedelta(minutes=1) or candles[-1].timestamp < expected_end:
        raise EvidenceError(f"{t.trade_id}: insufficient candle coverage")
    for a, b in zip(selected, selected[1:]):
        if b.timestamp - a.timestamp > timedelta(minutes=1):
            raise EvidenceError(f"{t.trade_id}: missing M1 candle between {a.timestamp} and {b.timestamp}")
    return selected


def _path_stats(t: Trade, path: Sequence[Candle], exit_time: datetime) -> dict:
    risk = abs(t.entry_price - t.stop_loss)
    if t.side == "LONG":
        favorable = [(c.high - t.entry_price) / risk for c in path]
        adverse = [(c.low - t.entry_price) / risk for c in path]
    else:
        favorable = [(t.entry_price - c.low) / risk for c in path]
        adverse = [(t.entry_price - c.high) / risk for c in path]
    mfe = max([0.0, *favorable]); mae = min([0.0, *adverse])
    mfe_i = favorable.index(max(favorable)) if favorable and max(favorable) > 0 else None
    def threshold(level: float):
        return next(((c.timestamp - t.entry_time).total_seconds() / 60 for c, x in zip(path, favorable) if x >= level), None)
    def horizon(minutes: int):
        values = [x for c, x in zip(path, favorable) if c.timestamp <= t.entry_time + timedelta(minutes=minutes)]
        return max([0.0, *values])
    return {"mfe_r": mfe, "mae_r": mae,
            "time_to_mfe_minutes": ((path[mfe_i].timestamp - t.entry_time).total_seconds() / 60 if mfe_i is not None else None),
            "time_to_1r_minutes": threshold(1), "time_to_2r_minutes": threshold(2), "time_to_3r_minutes": threshold(3),
            **{f"mfe_after_{h}m": horizon(h) for h in HORIZONS}}


def replay_trade(t: Trade, candles: Sequence[Candle], policy: str) -> dict:
    if policy not in POLICIES:
        raise EvidenceError(f"unsupported policy: {policy}")
    if abs(t.entry_price - t.stop_loss) <= 0:
        raise EvidenceError(f"{t.trade_id}: invalid stop distance")
    full_path = _slice(t, candles, max(t.original_exit_time, t.entry_time + timedelta(minutes=120)))
    if policy == "CONTROL":
        exit_time, exit_price, reason = t.original_exit_time, t.original_exit_price, "ORIGINAL_EXIT"
        path = [c for c in full_path if c.timestamp <= exit_time]
    else:
        cap = t.entry_time + timedelta(minutes=int(policy))
        deadline = min(cap, t.original_exit_time)
        path = [c for c in full_path if c.timestamp <= deadline]
        if not path:
            raise EvidenceError(f"{t.trade_id}: no candle after entry")
        exit_time, exit_price = deadline, path[-1].close
        reason = "ORIGINAL_EXIT" if t.original_exit_time <= cap else "TIME_STOP"
        for c in path:
            sl = c.low <= t.stop_loss if t.side == "LONG" else c.high >= t.stop_loss
            tp = t.take_profit is not None and (c.high >= t.take_profit if t.side == "LONG" else c.low <= t.take_profit)
            if sl and tp:
                raise EvidenceError(f"{t.trade_id}: ambiguous SL/TP intrabar ordering at {c.timestamp}")
            if sl or tp:
                exit_time, exit_price, reason = c.timestamp, t.stop_loss if sl else t.take_profit, "STOP_LOSS" if sl else "TAKE_PROFIT"
                path = [x for x in path if x.timestamp <= exit_time]
                break
    gross = _r(t, float(exit_price)); friction = t.spread_cost_r + t.commission_cost_r + t.slippage_cost_r
    return {"trade_id": t.trade_id, "policy": policy, "entry_time": t.entry_time.isoformat(), "exit_time": exit_time.isoformat(),
            "hold_minutes": (exit_time - t.entry_time).total_seconds() / 60, "entry_price": t.entry_price,
            "exit_price": exit_price, "stop_loss": t.stop_loss, "gross_r": gross, "net_r": gross - friction,
            "exit_reason": reason, "spread_cost_r": t.spread_cost_r, "commission_cost_r": t.commission_cost_r,
            "slippage_cost_r": t.slippage_cost_r, **_path_stats(t, path, exit_time)}


def policy_metrics(rows: Sequence[dict]) -> dict:
    ordered = sorted(rows, key=lambda r: (r["entry_time"], r["trade_id"]))
    net = [r["net_r"] for r in ordered]; positive = sum(x for x in net if x > 0); negative = sum(x for x in net if x < 0)
    pf = None if negative == 0 else positive / abs(negative)
    peak = equity = dd = 0.0
    for x in net:
        equity += x; peak = max(peak, equity); dd = max(dd, peak - equity)
    holds = [r["hold_minutes"] for r in rows]; hours = sum(holds) / 60
    winners = [r["hold_minutes"] for r in rows if r["net_r"] > 0]; losers = [r["hold_minutes"] for r in rows if r["net_r"] < 0]
    def med(xs): return statistics.median(xs) if xs else None
    buckets = {"0-30": [], "30-60": [], "60-90": [], "90-120": [], "120+": []}
    for r in rows:
        h = r["hold_minutes"]; key = "0-30" if h <= 30 else "30-60" if h <= 60 else "60-90" if h <= 90 else "90-120" if h <= 120 else "120+"
        buckets[key].append(r["net_r"])
    return {"policy": rows[0]["policy"], "trade_count": len(rows), "wins": sum(x > 0 for x in net), "losses": sum(x < 0 for x in net),
            "total_gross_r": sum(r["gross_r"] for r in rows), "total_net_r": sum(net), "net_expectancy_r": sum(net) / len(net),
            "win_rate": sum(x > 0 for x in net) / len(net), "profit_factor": pf, "max_drawdown_r": dd,
            "median_hold_minutes": med(holds), "winner_median_hold_minutes": med(winners), "loser_median_hold_minutes": med(losers),
            "total_position_hours": hours, "r_per_position_hour": sum(net) / hours if hours else None,
            "total_friction_r": sum(r["spread_cost_r"] + r["commission_cost_r"] + r["slippage_cost_r"] for r in rows),
            "mean_mfe_r": statistics.fmean(r["mfe_r"] for r in rows), "median_mfe_r": med([r["mfe_r"] for r in rows]),
            "mean_mae_r": statistics.fmean(r["mae_r"] for r in rows), "median_mae_r": med([r["mae_r"] for r in rows]),
            "expectancy_by_realized_hold_bucket": {k: (sum(v) / len(v) if v else None) for k, v in buckets.items()}}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(trades_path: str | Path, candles_path: str | Path, output: str | Path) -> dict:
    trades, candles = load_trades(trades_path), load_candles(candles_path)
    grouped = {s: [c for c in candles if c.symbol == s] for s in {t.symbol for t in trades}}
    rows = [replay_trade(t, grouped.get(t.symbol, []), p) for p in POLICIES for t in trades]
    hashes = {entry_population_hash(trades)}
    if len(hashes) != 1:
        raise EvidenceError("entry population changed across policies")
    metrics = [policy_metrics([r for r in rows if r["policy"] == p]) for p in POLICIES]
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    with (out / "per_trade_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    flat = [{k: v for k, v in m.items() if k != "expectancy_by_realized_hold_bucket"} for m in metrics]
    with (out / "policy_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(flat[0])); w.writeheader(); w.writerows(flat)
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception: commit = "UNKNOWN"
    manifest = {"experiment_id": "EXP_EXPOSURE_EFFICIENCY_V1", "generation_id": "GEN_001",
                "strategy_id": trades[0].strategy_id, "strategy_version": trades[0].strategy_version,
                "entry_population_hash": next(iter(hashes)), "trade_ledger_hash": _sha(Path(trades_path)),
                "candle_dataset_hash": _sha(Path(candles_path)), "friction_model": "PER_TRADE_R_COMPONENTS",
                "policies": list(POLICIES), "repository_commit": commit,
                "evaluator_hash": _sha(Path(__file__)), "timezone": "UTC", "created_at": datetime.now(timezone.utc).isoformat()}
    (out / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "input_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "exposure_efficiency_results.json").write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# GEN_001 Exposure Efficiency Report", "", f"Entry population: `{manifest['entry_population_hash']}`", "", "| Policy | Trades | Net R | Expectancy R | PF | Max DD R | Median Hold | Exposure H | R/H |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m in metrics: lines.append(f"| {m['policy']} | {m['trade_count']} | {m['total_net_r']:.4f} | {m['net_expectancy_r']:.4f} | {m['profit_factor']} | {m['max_drawdown_r']:.4f} | {m['median_hold_minutes']:.1f} | {m['total_position_hours']:.2f} | {m['r_per_position_hour']} |")
    (out / "GEN_001_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"manifest": manifest, "metrics": metrics, "rows": rows}


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Research-only GEN_001 exposure-efficiency replay")
    p.add_argument("--trades", required=True); p.add_argument("--candles", required=True); p.add_argument("--output", required=True)
    a = p.parse_args(argv); run(a.trades, a.candles, a.output); return 0


if __name__ == "__main__":
    raise SystemExit(main())
