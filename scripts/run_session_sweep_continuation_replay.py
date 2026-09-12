"""Canonical EURUSD replay driver for ST_SESSION_SWEEP_CONTINUATION_V1 (OFFLINE_RESEARCH
only), against the ONE owner-approved historical dataset in this repository:
config/historical_datasets/EURUSD_M5_202504211715_202607310000.yaml.

RESEARCH ONLY. This script does not place orders, does not touch demo_eligible /
demo_authorized / live_authorized, and does not modify any strategy parameter -- it only
drives session_sweep_continuation.replay.run_replay across every trading date the
dataset covers and aggregates the results via the existing, strategy-neutral
performance/calculator.py.

Data pipeline (reuses existing, owner-approved components; no new data source):
  1. session_tribranch_research.data_loader.load_eurusd_m5_utc() -- fingerprint-verified
     M5 load, true-UTC conversion (broker offset auto-detected from the weekend gap).
  2. historical_replay.resampler.resample(candles, "M5", "M15") -- deterministic,
     gap-safe M5->M15 aggregation (an incomplete M15 bucket is dropped, never
     fabricated).
  3. session_sweep_continuation.replay.run_replay(...) once per (session_pair,
     trading_date) covered by the M15 series.

GBPUSD is NOT run by this script -- there is no owner-approved historical dataset for
GBPUSD in this repository (config/historical_datasets/ contains only the EURUSD manifest
above); running GBPUSD would require fabricating or silently reusing unapproved data,
which this script refuses to do.
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.resampler import resample  # noqa: E402
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from session_sweep_continuation.config import compute_config_hash, load_config  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_tribranch_research.data_loader import (  # noqa: E402
    DATASET_ID,
    EXPECTED_FINGERPRINT,
    load_eurusd_m5_utc,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0


def _trading_dates(m15_candles):
    """Every distinct UTC calendar date present in the M15 series -- the outer loop of
    the replay walks each one, for each configured session_pair. No date is invented;
    this is derived purely from what the dataset actually contains."""
    return sorted({c.time.date() for c in m15_candles})


def run_symbol_replay(config: dict) -> dict:
    candles_m5, broker_offset, fingerprint, _spreads = load_eurusd_m5_utc()
    if fingerprint != EXPECTED_FINGERPRINT:
        raise SystemExit(f"FINGERPRINT_MISMATCH: {fingerprint} != {EXPECTED_FINGERPRINT}")

    candles_m15 = resample(candles_m5, "M5", "M15")
    dates = _trading_dates(candles_m15)
    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]

    decision_cycles = 0
    known_regime_cycles = 0
    unknown_regime_cycles = 0
    setup_counts = {"S1": 0, "S2": 0, "S3": 0}
    orders = 0
    fills = 0
    expired = 0
    resolved_samples = []
    resolved_trade_records = []
    cost_statuses = set()

    for trading_date in dates:
        for pair_id in session_pairs:
            decision_cycles += 1
            try:
                # AG_ST_SESSION_SWEEP_CONTINUATION_REPLAY_BLOCKER_REMEDIATION: MarketBiasResult
                # is now the mandatory directional authority (bias_gate.py) -- omitting it
                # (bias_result=None, its explicit fail-closed default) means every candidate
                # this cycle is rejected BIAS_MISSING. This script has no H1 bias source wired
                # yet (analyze_structure_tiers over H1 requires either a live MT5 connection or
                # an owner-authorized EURUSD H1 tick_size manifest, neither of which exists for
                # this driver today -- see the remediation status report); wiring a real bias
                # resolution here is explicitly out of scope for this task and deferred to
                # RUN_FIRST_CANONICAL_HISTORICAL_REPLAY. Running this script as-is now produces
                # zero accepted trades by design (fail-closed), not a silent bias bypass.
                result = run_replay(candles_m15, config, SYMBOL, pair_id, trading_date, PIP_SIZE, PIP_VALUE_PER_LOT, bias_result=None)
            except KeyError:
                # trade/reference session window not fully covered by this date's data
                # (e.g. dataset boundary date) -- not a decision cycle, skip cleanly.
                decision_cycles -= 1
                continue

            if result.regime is None:
                # reference session itself had zero candles (dataset gap) -- not a real
                # decision cycle either.
                decision_cycles -= 1
                continue
            if result.regime == "UNKNOWN":
                unknown_regime_cycles += 1
                continue
            known_regime_cycles += 1

            for setup in result.accepted_setups:
                model = setup["setup_model"]
                if model.startswith("S1"):
                    setup_counts["S1"] += 1
                elif model.startswith("S2"):
                    setup_counts["S2"] += 1
                elif model.startswith("S3"):
                    setup_counts["S3"] += 1
                orders += 1
                outcome = setup["outcome"]
                # This strategy's every accepted entry is filled by construction (S1/S2/S3
                # entry_price is the trigger candle's own close, no resting/pending-order
                # phase -- see outcome_resolution.py module docstring): order_state is
                # therefore always ORDER_FILLED, and there is no ORDER_PENDING/EXPIRED
                # order state to count here. `expired` stays 0 for this reason (reported
                # honestly, not omitted).
                if outcome["order_state"] == "ORDER_FILLED":
                    fills += 1
                if outcome["gross_R"] is not None:
                    cost_statuses.add(outcome["cost_status"])
                    source_id = f"{pair_id}_{trading_date}_{setup['entry_time']}_{model}"
                    resolved_samples.append(ResolvedTradeSample(
                        source_record_id=source_id,
                        source_path="session_sweep_continuation.replay.run_replay",
                        strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
                        strategy_version=config.get("version", "1.0.0"),
                        symbol=SYMBOL,
                        cycle=pair_id,
                        resolved_at=setup["entry_time"],
                        gross_R=outcome["gross_R"],
                        net_R=outcome["net_R"],
                        cost_status=outcome["cost_status"],
                        outcome=outcome["terminal_state"],
                    ))
                    resolved_trade_records.append({
                        "session_pair": pair_id, "trading_date": str(trading_date),
                        "setup_model": model, "terminal_state": outcome["terminal_state"],
                        "gross_R": outcome["gross_R"], "net_R": outcome["net_R"],
                        "cost_status": outcome["cost_status"],
                    })

    metrics = compute_trade_metrics(resolved_samples)
    cost_status = cost_statuses.pop() if len(cost_statuses) == 1 else ("MIXED" if len(cost_statuses) > 1 else "NOT_EVALUATED")

    return {
        "symbol": SYMBOL,
        "dataset_id": DATASET_ID,
        "dataset_fingerprint": fingerprint,
        "coverage": {"first_date": str(dates[0]), "last_date": str(dates[-1]), "m15_bar_count": len(candles_m15)},
        "session_pairs": session_pairs,
        "decision_cycles": decision_cycles,
        "known_regime_cycles": known_regime_cycles,
        "unknown_regime_cycles": unknown_regime_cycles,
        "setup_counts": setup_counts,
        "orders": orders,
        "fills": fills,
        "expired": expired,
        "resolved_trades": len(resolved_samples),
        "wins": metrics.wins,
        "losses": metrics.losses,
        "breakevens": metrics.breakevens,
        "gross_total_R": metrics.gross_total_R,
        "gross_expectancy_R": metrics.gross_expectancy_R,
        "net_total_R": metrics.net_total_R,
        "net_expectancy_R": metrics.net_expectancy_R,
        "profit_factor": metrics.profit_factor,
        "max_drawdown_R": metrics.max_drawdown_R,
        "cost_status": cost_status,
        "resolved_trade_records": resolved_trade_records,
    }


def main():
    config = load_config(repo_root=str(REPO_ROOT))
    config_hash = compute_config_hash(config)
    result = run_symbol_replay(config)
    result["config_hash"] = config_hash
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
