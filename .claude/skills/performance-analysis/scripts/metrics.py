#!/usr/bin/env python3
"""Calculate basic metrics from a CSV of periodic decimal returns. Standard library only."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_file", type=Path)
    p.add_argument("--return-column", default="return")
    p.add_argument("--date-column", default="date")
    p.add_argument("--periods-per-year", type=float, required=True)
    p.add_argument("--annual-risk-free-rate", type=float, default=0.0, help="Decimal annual rate")
    p.add_argument("--output", type=Path, help="Optional JSON output path")
    return p


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def main() -> int:
    args = parser().parse_args()
    if args.periods_per_year <= 0:
        raise SystemExit("--periods-per-year must be positive")

    returns: list[float] = []
    dates: list[str] = []
    with args.csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if args.return_column not in fields:
            raise SystemExit(f"Missing return column {args.return_column!r}; available: {fields}")
        for line, row in enumerate(reader, start=2):
            try:
                value = float(row[args.return_column])
            except (TypeError, ValueError):
                raise SystemExit(f"Invalid return at CSV row {line}: {row.get(args.return_column)!r}")
            if not math.isfinite(value) or value <= -1:
                raise SystemExit(f"Return at CSV row {line} must be finite and greater than -1: {value}")
            returns.append(value)
            dates.append(row.get(args.date_column, ""))

    if not returns:
        raise SystemExit("No return observations found")

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    max_drawdown_index = 0
    for index, value in enumerate(returns):
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_drawdown_index = index

    count = len(returns)
    mean_return = statistics.fmean(returns)
    period_volatility = statistics.stdev(returns) if count >= 2 else 0.0
    annual_volatility = period_volatility * math.sqrt(args.periods_per_year)
    cumulative_return = equity - 1.0
    annualized_return = equity ** (args.periods_per_year / count) - 1.0
    periodic_rf = (1.0 + args.annual_risk_free_rate) ** (1.0 / args.periods_per_year) - 1.0
    sharpe = safe_ratio((mean_return - periodic_rf) * math.sqrt(args.periods_per_year), period_volatility)

    downside_squares = [min(0.0, value - periodic_rf) ** 2 for value in returns]
    downside_deviation = math.sqrt(statistics.fmean(downside_squares))
    sortino = safe_ratio((mean_return - periodic_rf) * math.sqrt(args.periods_per_year), downside_deviation)
    calmar = safe_ratio(annualized_return, abs(max_drawdown))

    positives = [value for value in returns if value > 0]
    negatives = [value for value in returns if value < 0]
    average_gain = statistics.fmean(positives) if positives else None
    average_loss = statistics.fmean(negatives) if negatives else None
    payoff_ratio = safe_ratio(average_gain, abs(average_loss)) if average_gain is not None and average_loss is not None else None

    report = {
        "input": {
            "file": str(args.csv_file),
            "observations": count,
            "start": dates[0] if dates else "",
            "end": dates[-1] if dates else "",
            "periods_per_year": args.periods_per_year,
            "annual_risk_free_rate": args.annual_risk_free_rate,
            "return_unit": "decimal",
        },
        "metrics": {
            "cumulative_return": cumulative_return,
            "annualized_return": annualized_return,
            "annualized_volatility": annual_volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "maximum_drawdown": max_drawdown,
            "maximum_drawdown_date": dates[max_drawdown_index] if dates else "",
            "calmar_ratio": calmar,
            "positive_period_rate": len(positives) / count,
            "average_positive_period": average_gain,
            "average_negative_period": average_loss,
            "period_payoff_ratio": payoff_ratio,
            "best_period": max(returns),
            "worst_period": min(returns),
        },
        "warnings": [
            "These are periodic-return metrics, not trade-level statistics.",
            "No correction is made for serial correlation, overlapping returns, non-normal tails, or multiple testing.",
            "Annualization is an assumption and can be misleading for short samples.",
            "Historical metrics do not predict or bound future results.",
        ],
    }
    payload = json.dumps(report, indent=2, allow_nan=False)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
