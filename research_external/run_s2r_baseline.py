"""AG_S2R_BASELINE_RESEARCH_V1 orchestrator -- EXPERIMENTAL RESEARCH ONLY.

Pipeline: capture real EURUSD M5 -> validate -> persist+hash -> cross-check vs
smc-lss-platform CSV -> freeze TRAIN/VALIDATION/FINAL_HOLDOUT (holdout locked) ->
run ONE baseline S2R configuration against TRAIN only -> export signal/trade
ledgers + metrics + integrity manifest -> re-run once more to prove semantic
reproducibility.

Runs no optimization (Backtest.optimize is never imported/called anywhere in this
file or in research_external/adapters/backtesting_py.py). Never touches
FINAL_HOLDOUT (enforced by research_external.tools.partitions.require_not_holdout,
not by convention alone). Never invokes src/external_candidate/admission.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))
sys.path.insert(0, _REPO_ROOT)

import yaml  # noqa: E402
from post_asian_pilot.fingerprint import fingerprint  # noqa: E402
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import NOT_EVALUATED, ResolvedTradeSample  # noqa: E402

from research_external.adapters.backtesting_py import rejected_order_count, run_baseline  # noqa: E402
from research_external.semantic.s2r import (  # noqa: E402
    REASON_READY_LONG,
    REASON_READY_SHORT,
    run_s2r_over_history,
)
from research_external.tooling import artifact_io  # noqa: E402
from research_external.tooling import mt5_capture  # noqa: E402
from research_external.tools.dataset_validation import validate_dataset  # noqa: E402
from research_external.tools.partitions import (  # noqa: E402
    ROLE_FINAL_HOLDOUT,
    ROLE_TRAIN,
    ROLE_VALIDATION,
    freeze_partitions,
    require_not_holdout,
)

RUN_DIR = os.path.join(_HERE, "runs", "S2R_BASELINE_001")
DATASET_DIR = os.path.join(_HERE, "datasets")
MANIFEST_DIR = os.path.join(DATASET_DIR, "manifests")
SPEC_PATH = os.path.join(_HERE, "specs", "S2R_BREAKOUT_RETEST_CONTINUATION_V1.yaml")

REQUESTED_SYMBOL = "EURUSD"
REQUESTED_TIMEFRAME = "M5"
REQUESTED_COUNT = 90_000  # terminal maxbars ceiling, confirmed via probe this session

SMC_LSS_CSV = r"D:\ddev\smc-lss-platform\data\EURUSD_M5.csv"


def load_spec() -> dict:
    with open(SPEC_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def capture_primary_dataset() -> list:
    bars = mt5_capture.capture_closed_bars(REQUESTED_SYMBOL, REQUESTED_TIMEFRAME, REQUESTED_COUNT)
    return [
        {
            "time": b.timestamp_utc, "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "tick_volume": b.tick_volume, "spread": b.spread, "real_volume": b.real_volume,
        }
        for b in bars
    ]


def persist_primary_dataset(candles: list) -> dict:
    dataset_path = os.path.join(DATASET_DIR, "EURUSD_M5_S2R_RESEARCH.parquet")
    artifact = artifact_io.write_parquet(dataset_path, candles)
    reopened = artifact_io.read_parquet(dataset_path)
    reopen_sha256 = artifact_io.sha256_of_file(dataset_path)

    manifest = {
        "dataset_id": "EURUSD_M5_S2R_RESEARCH",
        "symbol": REQUESTED_SYMBOL,
        "timeframe": REQUESTED_TIMEFRAME,
        "source": "REAL_OBSERVED_MARKET (MT5 copy_rates_from_pos, position 0 = last closed bar)",
        "broker": mt5_capture.broker_server_name(),
        "requested_count": REQUESTED_COUNT,
        "requested_start": None,
        "requested_end": None,
        "actual_start": candles[0]["time"],
        "actual_end": candles[-1]["time"],
        "rows": len(candles),
        "file_path": os.path.relpath(dataset_path, _REPO_ROOT).replace("\\", "/"),
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256_pass2,
        "sha256_reopen": reopen_sha256,
        "hash_match": reopen_sha256 == artifact.sha256_pass2,
        "row_count_reopened": len(reopened),
        "limitation_note": (
            "MT5 terminal maxbars=100000 caps copy_rates_from_pos depth; a wide "
            "copy_rates_range back to 2023-01-01/2020-01-01 both returned no/partial "
            "data (probed this session). Maximum trustworthy contiguous EURUSD M5 "
            "history actually available from this terminal is ~14.4 months, not the "
            "originally targeted 2023-2026 multi-year span. Documented, not silently "
            "substituted."
        ),
    }
    os.makedirs(MANIFEST_DIR, exist_ok=True)
    manifest_path = os.path.join(MANIFEST_DIR, "dataset_manifest.json")
    artifact_io.write_json_manifest(manifest_path, manifest)
    return manifest


def cross_check_against_smc_lss(candles: list) -> dict:
    if not os.path.isfile(SMC_LSS_CSV):
        return {"status": "NOT_PROVABLE", "reason": f"{SMC_LSS_CSV} not found"}

    import csv as csv_mod
    smc_rows = {}
    with open(SMC_LSS_CSV, "r", encoding="utf-8") as fh:
        reader = csv_mod.DictReader(fh)
        for row in reader:
            # smc-lss CSV timestamps are naive "YYYY-MM-DD HH:MM" -- no explicit
            # UTC marker. Tested this session (see report note): comparing against
            # our own UTC-labeled MT5 candles at identical wall-clock strings shows
            # sensible, small price deviations (same order of magnitude as normal
            # broker/feed spread differences), so a 0-hour offset is used and
            # reported as an explicit, checked assumption -- not asserted as
            # verified UTC without evidence.
            key = row["time"].replace(" ", "T") + ":00+00:00"
            smc_rows[key] = row

    by_time = {c["time"]: c for c in candles}
    common_keys = sorted(set(by_time) & set(smc_rows))
    if not common_keys:
        return {"status": "NOT_PROVABLE", "reason": "no overlapping timestamps found under the 0h-offset assumption"}

    sample_positions = sorted(set([0, len(common_keys) // 2, len(common_keys) - 1]))
    deviations = []
    samples = []
    for key in common_keys:
        ag = by_time[key]
        smc = smc_rows[key]
        dev = abs(float(ag["close"]) - float(smc["close"]))
        deviations.append(dev)
    for pos in sample_positions:
        key = common_keys[pos]
        samples.append({
            "timestamp": key,
            "ag_close": by_time[key]["close"],
            "smc_lss_close": float(smc_rows[key]["close"]),
            "deviation": abs(by_time[key]["close"] - float(smc_rows[key]["close"])),
        })

    return {
        "status": "COMPARED",
        "assumption": "0-hour offset (smc-lss CSV timestamps treated as already UTC)",
        "overlap_start": common_keys[0],
        "overlap_end": common_keys[-1],
        "overlap_row_count": len(common_keys),
        "median_price_deviation": sorted(deviations)[len(deviations) // 2],
        "max_price_deviation": max(deviations),
        "samples": samples,
        "interpretation": (
            "Small (sub-pip to few-pip) deviations are expected broker/feed price "
            "differences, not corruption. Large (>>1 pip) or systematically shifted "
            "deviations would indicate timezone/timestamp corruption -- see "
            "max_price_deviation above for this run's actual result."
        ),
    }


def build_partitions(candles: list, dataset_sha256: str) -> dict:
    dates = sorted({str(c["time"])[:10] for c in candles})
    first_date, last_date = dates[0], dates[-1]
    # Clean month boundaries closest to a 60/20/20 split of the ~14.4-month span
    # actually captured this session (2025-06/07 through 2026-09) -- computed from
    # the real captured range, not hardcoded in advance of knowing it.
    boundaries = {
        ROLE_TRAIN: ("2025-07-01", "2026-04-01"),
        ROLE_VALIDATION: ("2026-04-01", "2026-07-01"),
        ROLE_FINAL_HOLDOUT: ("2026-07-01", "2026-12-31"),
    }
    partitions = freeze_partitions(candles, dataset_sha256, boundaries)
    for role, partition in partitions.items():
        path = os.path.join(MANIFEST_DIR, f"{role}.json")
        artifact_io.write_json_manifest(path, {
            "partition_id": partition.partition_id, "role": partition.role,
            "parent_dataset_sha256": partition.parent_dataset_sha256,
            "start": partition.start, "end": partition.end, "rows": partition.rows,
            "partition_sha256": partition.partition_sha256, "locked": partition.locked,
        })
    return partitions


def _resolve_exit_reason(row, price_tol: float) -> str:
    exit_price = float(row["ExitPrice"])
    sl, tp = row.get("SL"), row.get("TP")
    if tp is not None and abs(exit_price - float(tp)) <= price_tol:
        return "TARGET_HIT"
    if sl is not None and abs(exit_price - float(sl)) <= price_tol:
        return "STOP_HIT"
    return "END_OF_DATA"


def run_baseline_once(train_candles: list, spec: dict, run_label: str) -> dict:
    signals = run_s2r_over_history(train_candles, spec)
    ready = [s for s in signals if s.reason_code in (REASON_READY_LONG, REASON_READY_SHORT)]

    friction = spec["friction"]
    reference_price = sum(float(c["close"]) for c in train_candles) / len(train_candles)
    pip_size = 0.0001
    spread_frac = (float(friction["provisional_spread_pips"]) * pip_size) / reference_price
    commission_frac = (float(friction["provisional_commission_pips"]) * pip_size) / reference_price

    stats, trades = run_baseline(train_candles, signals, spread=spread_frac, commission=commission_frac)
    rejected_count = rejected_order_count(stats)

    resolved_samples = []
    trade_rows = []
    price_tol = 1e-9
    for i, row in trades.reset_index().iterrows():
        direction = "LONG" if row["Size"] > 0 else "SHORT"
        entry_price, exit_price = float(row["EntryPrice"]), float(row["ExitPrice"])
        risk_distance = float(row["Tag"])
        sign = 1 if direction == "LONG" else -1
        gross_R = ((exit_price - entry_price) * sign) / risk_distance
        exit_reason = _resolve_exit_reason(row, price_tol)

        trade_id = f"{run_label}-T{i:04d}"
        trade_rows.append({
            "trade_id": trade_id, "entry_timestamp": row["EntryTime"].isoformat(),
            "exit_timestamp": row["ExitTime"].isoformat(), "direction": direction,
            "entry_price": entry_price, "exit_price": exit_price,
            "stop": float(row["SL"]) if row["SL"] is not None else None,
            "target": float(row["TP"]) if row["TP"] is not None else None,
            "gross_R": gross_R, "net_R": None,
            "bars_held": int(row["ExitBar"] - row["EntryBar"]),
            "exit_reason": exit_reason, "commission_cash": float(row["Commission"]),
        })
        resolved_samples.append(ResolvedTradeSample(
            source_record_id=trade_id, source_path="research_external (in-memory baseline replay)",
            strategy_id=spec["strategy_id"], strategy_version="EXPERIMENTAL",
            symbol=REQUESTED_SYMBOL, cycle=None, resolved_at=row["ExitTime"].isoformat(),
            gross_R=gross_R, net_R=None, cost_status="INCLUDED_PROVISIONAL_SPREAD_ONLY_COMMISSION_NOT_IN_R",
            outcome=exit_reason,
        ))

    metrics = compute_trade_metrics(resolved_samples)

    signal_rows = [{
        "run_id": run_label, "strategy_id": spec["strategy_id"], "setup_id": spec["setup_id"],
        "decision_timestamp": s.decision_timestamp, "data_available_through": s.data_available_through,
        "direction": s.direction, "reference_high": s.reference_high, "reference_low": s.reference_low,
        "atr": s.atr, "breakout_price": s.breakout_price, "displacement_atr": s.displacement_body,
        "retest_price": s.retest_price, "entry": s.entry, "stop": s.stop, "target": s.target,
        "risk_distance": s.risk_distance, "reason_code": s.reason_code,
    } for s in signals]

    return {
        "signals": signals, "signal_rows": signal_rows, "trade_rows": trade_rows,
        "metrics": metrics, "ready_count": len(ready), "rejected_order_count": rejected_count,
    }


def main() -> None:
    print("=== capturing primary EURUSD M5 dataset ===")
    candles = capture_primary_dataset()
    print(f"captured {len(candles)} bars: {candles[0]['time']} .. {candles[-1]['time']}")

    validation = validate_dataset(candles)
    print("dataset_validation:", validation)
    if not validation.passed:
        print("DATASET_VALIDATION_FAILED -- stopping.")
        return

    dataset_manifest = persist_primary_dataset(candles)
    print("dataset persisted:", dataset_manifest["file_path"], dataset_manifest["sha256"])

    crosscheck = cross_check_against_smc_lss(candles)
    artifact_io.write_json_manifest(os.path.join(MANIFEST_DIR, "smc_lss_crosscheck.json"), crosscheck)
    print("crosscheck:", crosscheck.get("status"), crosscheck.get("median_price_deviation"))

    partitions = build_partitions(candles, dataset_manifest["sha256"])
    for role, p in partitions.items():
        print(f"partition {role}: {p.start}..{p.end} rows={p.rows} locked={p.locked}")

    train_candles = require_not_holdout(partitions[ROLE_TRAIN])

    spec = load_spec()
    parameter_sha256 = fingerprint(spec)
    print("parameter_sha256:", parameter_sha256)

    os.makedirs(RUN_DIR, exist_ok=True)
    artifact_io.write_json_manifest(os.path.join(RUN_DIR, "strategy_spec_snapshot.json"), spec)
    artifact_io.write_json_manifest(os.path.join(RUN_DIR, "parameters.json"), {
        "parameter_sha256": parameter_sha256, "label": spec["baseline_parameters_label"],
    })

    print("=== baseline run 1 (TRAIN only) ===")
    run1 = run_baseline_once(train_candles, spec, "S2R_BASELINE_001_RUN1")
    print("run1 ready signals:", run1["ready_count"], "trades:", len(run1["trade_rows"]), "rejected:", run1["rejected_order_count"])
    print("run1 metrics:", run1["metrics"])

    print("=== baseline run 2 (reproducibility check) ===")
    run2 = run_baseline_once(train_candles, spec, "S2R_BASELINE_001_RUN2")

    signal_parity = run1["signal_rows"] == [dict(r, run_id="S2R_BASELINE_001_RUN1") for r in run2["signal_rows"]]
    trades_1_comparable = [{k: v for k, v in t.items() if k != "trade_id"} for t in run1["trade_rows"]]
    trades_2_comparable = [{k: v for k, v in t.items() if k != "trade_id"} for t in run2["trade_rows"]]
    trade_parity = trades_1_comparable == trades_2_comparable
    metrics_parity = run1["metrics"] == run2["metrics"]

    print("signal_parity:", signal_parity, "trade_parity:", trade_parity, "metrics_parity:", metrics_parity)

    engine_metadata = {
        "engine": "backtesting.py", "engine_version": __import__("backtesting").__version__,
        "python_version": sys.version, "pandas_version": __import__("pandas").__version__,
        "numpy_version": __import__("numpy").__version__, "pyarrow_version": __import__("pyarrow").__version__,
        "optimization_used": False, "holdout_used": False,
    }
    artifact_io.write_json_manifest(os.path.join(RUN_DIR, "engine_metadata.json"), engine_metadata)

    signal_ledger_artifact = artifact_io.write_parquet(os.path.join(RUN_DIR, "signal_ledger.parquet"), run1["signal_rows"])
    trade_ledger_artifact = artifact_io.write_parquet(os.path.join(RUN_DIR, "trade_ledger.parquet"), run1["trade_rows"]) if run1["trade_rows"] else None

    metrics_payload = {
        "run_id": "S2R_BASELINE_001", "label": "BASELINE_NON_OPTIMIZED_RESEARCH_EVIDENCE",
        "dataset_role": "TRAIN", "optimization_used": False, "holdout_used": False,
        "trade_count": run1["metrics"].sample_size, "wins": run1["metrics"].wins, "losses": run1["metrics"].losses,
        "win_rate": run1["metrics"].win_rate, "gross_total_R": run1["metrics"].gross_total_R,
        "net_total_R": run1["metrics"].net_total_R, "expectancy_R": run1["metrics"].gross_expectancy_R,
        "profit_factor": run1["metrics"].profit_factor, "max_drawdown_R": run1["metrics"].max_drawdown_R,
        "friction_authority": spec["friction"]["model_status"],
        "rejected_order_count": run1["rejected_order_count"],
        "reproducibility": {"signal_parity": signal_parity, "trade_parity": trade_parity, "metrics_parity": metrics_parity},
    }
    artifact_io.write_json_manifest(os.path.join(RUN_DIR, "metrics.json"), metrics_payload)

    data_validation_payload = {
        "row_count": validation.row_count, "monotonic": validation.monotonic,
        "duplicate_timestamp_count": validation.duplicate_timestamp_count,
        "future_row_count": validation.future_row_count, "invalid_ohlc_count": validation.invalid_ohlc_count,
    }
    artifact_io.write_json_manifest(os.path.join(RUN_DIR, "data_validation.json"), data_validation_payload)

    integrity_entries = []
    for name, artifact in [
        ("signal_ledger.parquet", signal_ledger_artifact),
        ("trade_ledger.parquet", trade_ledger_artifact),
    ]:
        if artifact is None:
            continue
        integrity_entries.append({"filename": name, "size_bytes": artifact.size_bytes, "sha256": artifact.sha256_pass2, "reproducible": artifact.reproducible})
    for name in ["strategy_spec_snapshot.json", "parameters.json", "engine_metadata.json", "metrics.json", "data_validation.json"]:
        path = os.path.join(RUN_DIR, name)
        integrity_entries.append({"filename": name, "size_bytes": os.path.getsize(path), "sha256": artifact_io.sha256_of_file(path)})

    artifact_io.write_json_manifest(os.path.join(RUN_DIR, "integrity_manifest.json"), {"run_id": "S2R_BASELINE_001", "entries": integrity_entries})

    print()
    print("=== DONE ===")
    print(json.dumps(metrics_payload, indent=2, default=str))


if __name__ == "__main__":
    main()
