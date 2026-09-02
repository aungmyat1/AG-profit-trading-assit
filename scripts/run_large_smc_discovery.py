"""Phase B discovery replay for ST_LARGE_SMC_V1 (RESEARCH_ONLY_FUNNEL_V1, corrected in
REPLAY_METADATA_DECOUPLING_V1).

Reuses the same real-CSV replay machinery `scripts/run_historical_replay.py` already
uses (`historical_replay.orchestrator.run_replay` -- zero E1/E2/E3/M1/M2/M3
redetection) and re-expresses `FunnelTracker`'s distinct-occurrence counts in the
funnel shape the research task asked for. C10 (broker stop) remains unsigned (owner
decision: block outcome simulation rather than guess -- see
docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md), so fill/invalidated-
before-fill/expired-unfilled/intrabar-ambiguity/completed-outcome resolution are
reported as NOT_ATTEMPTED, never fabricated. Pending-entry expiry is separately
RESOLVED_BY_REUSE (v1.0.6) -- see large_smc_research/pending_entry.py -- and does not
affect this funnel-level report.

As of REPLAY_METADATA_DECOUPLING_V1, an owner-approved, dataset-fingerprint-validated
`HistoricalSymbolMetadataManifest` (see historical_replay.symbol_metadata_manifest) is
loaded and threaded into `run_replay`, restoring `market_structure.tiers.
analyze_structure_tiers`'s tick_size lookup during replay -- this is what M1's
inducement-candidate detection depends on (see
docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md for the discovered gap).
If no manifest exists for the requested (dataset, symbol), this script fails closed
rather than silently reverting to the old, incomplete replay behavior.

No proposal, demo, live, execution, or risk-sizing authority is exercised here --
read-only research replay only.

Usage:
    python scripts/run_large_smc_discovery.py <csv_path> <symbol> <start_iso> <end_iso> <out_json_path> [manifest_path]

Example:
    python scripts/run_large_smc_discovery.py D:\\EURUSD_M5_202504211715_202607310000.csv \\
        EURUSD 2025-08-01T00:00:00 2025-08-15T00:00:00 docs/status/large_smc_discovery_sample.json \\
        config/historical_datasets/EURUSD_M5_202504211715_202607310000.yaml
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay import (  # noqa: E402
    HistoricalCandleStore,
    SymbolMetadataManifestError,
    load_mt5_export_csv,
    load_symbol_metadata_manifest,
    resample,
    resample_broker_aligned,
    validate_manifest_for_dataset,
)
from historical_replay.orchestrator import run_replay  # noqa: E402
from large_smc_research.engine import FROZEN_INSTRUMENT_UNIVERSE, STRATEGY_VERSION  # noqa: E402
from large_smc_research.decision import STRATEGY_ID  # noqa: E402

NOT_ATTEMPTED = "NOT_ATTEMPTED_BLOCKED_UNSIGNED_CONTRACT"


def main() -> None:
    args = sys.argv[1:7]
    csv_path, symbol, start_iso, end_iso, out_path = args[:5]
    manifest_path = args[5] if len(args) > 5 else None
    if symbol not in FROZEN_INSTRUMENT_UNIVERSE:
        raise SystemExit(
            f"SYMBOL_NOT_IN_FROZEN_UNIVERSE: {symbol!r} not in {FROZEN_INSTRUMENT_UNIVERSE} "
            "(C01 -- no dynamic or inferred symbol inclusion; see strategies/ST_LARGE_SMC_V1.yaml)"
        )
    start_utc = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
    end_utc = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)

    manifest = None
    if manifest_path:
        try:
            manifest = load_symbol_metadata_manifest(manifest_path)
            validate_manifest_for_dataset(manifest, csv_path, symbol)
        except SymbolMetadataManifestError as exc:
            raise SystemExit(f"BLOCKED_DATASET_METADATA_PROVENANCE: {exc}") from exc

    t0 = time.time()
    candles, ingestion_report = load_mt5_export_csv(csv_path, symbol, "M5")
    store = HistoricalCandleStore()
    store.load_series(symbol, "M5", candles)
    derived = {}
    for tf in ("M15", "H1"):
        d = resample(candles, "M5", tf)
        store.load_series(symbol, tf, d)
        derived[tf] = len(d)
    for tf in ("H4", "D1"):
        d = resample_broker_aligned(candles, ingestion_report.broker_times, "M5", tf)
        store.load_series(symbol, tf, d)
        derived[tf] = len(d)
    load_time = time.time() - t0

    t0 = time.time()
    result = run_replay(store, symbol, candles, start_utc, end_utc, symbol_metadata_manifest=manifest)
    replay_time = time.time() - t0

    combos = tuple(result.per_combination.keys())
    composed_candidates = sum(v["M_STARTED"] for v in result.per_combination.values())
    ready_equivalent = sum(v["READY"] for v in result.per_combination.values())
    e_qualified = sum(v["E_QUALIFIED"] for v in result.per_e.values())
    m_confirmed = sum(v.get("M_CONFIRMED", 0) for v in result.per_m.values())
    entry_arrays_created = sum(v.get("ENTRY_ARRAY_CREATED", 0) for v in result.per_m.values())

    report = {
        "STRATEGY": {"STRATEGY_ID": STRATEGY_ID, "STRATEGY_VERSION": STRATEGY_VERSION,
                     "AUTHORITY": "RESEARCH_ONLY -- no proposal/demo/live/execution/risk-sizing authority exercised"},
        "SYMBOL_METADATA": {
            "MANIFEST_USED": manifest_path if manifest is not None else None,
            "TICK_SIZE": manifest.tick_size if manifest is not None else None,
            "SCOPE": manifest.metadata_scope if manifest is not None else None,
            "M1_INDUCEMENT_DETECTION_LIVE_MT5_REQUIRED": manifest is None,
        },
        "DATA": {
            "SOURCE": csv_path, "SYMBOL": symbol, "BASE_RESOLUTION": "M5",
            "DATE_RANGE_REQUESTED": [start_iso, end_iso],
            "FULL_DATASET_RANGE": [ingestion_report.start_utc.isoformat(), ingestion_report.end_utc.isoformat()],
            "SOURCE_TIMEZONE": ingestion_report.source_timezone, "NORMALIZED_TIMEZONE": "UTC",
            "TOTAL_M5_ROWS": ingestion_report.rows,
            "UNEXPECTED_GAPS": len(ingestion_report.unexpected_gaps),
            "DERIVED_TIMEFRAME_ROWS": derived,
        },
        "REPLAY": {
            "LOAD_TIME_SECONDS": round(load_time, 2), "REPLAY_TIME_SECONDS": round(replay_time, 2),
            "SECONDS_PER_STEP": round(replay_time / result.valid_steps, 4) if result.valid_steps else None,
        },
        "FUNNEL": {
            "1_RAW_PERIODS": result.steps,
            "2_VALID_DATA_PERIODS": result.valid_steps,
            "WARMUP_PERIODS_EXCLUDED": result.warmup_steps,
            "3_E_QUALIFIED_EVENTS": e_qualified,
            "4_M_CONFIRMED_EVENTS": m_confirmed,
            "5_COMPOSED_CANDIDATES": composed_candidates,
            "6_SELECTED_CANDIDATES": composed_candidates,  # C18: RECORD_ALL_INDEPENDENTLY -- no narrowing
            "7_ENTRY_ARRAY_CREATED": entry_arrays_created,
            "8_READY_EQUIVALENT_BLOCKED_PENDING_OWNER_DECISION": ready_equivalent,
            "9_FILLED_ENTRIES": NOT_ATTEMPTED,
            "10_INVALIDATED_BEFORE_FILL": NOT_ATTEMPTED,
            "11_EXPIRED_UNFILLED": NOT_ATTEMPTED,
            "12_INTRABAR_AMBIGUOUS": NOT_ATTEMPTED,
            "13_UNAMBIGUOUS_COMPLETED_OUTCOMES": NOT_ATTEMPTED,
            "BLOCKED_REASON": (
                "C10 (broker stop-loss distance) is unsigned (owner decision, 2026-09-01: "
                "block outcome simulation and write a decision packet rather than guess). "
                "Stages 9-13 require it and were not attempted. Stage 8's count is exactly "
                "how many candidates are pending that decision -- see "
                "docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md. (Pending-entry "
                "expiry is separately RESOLVED_BY_REUSE, v1.0.6 -- not a factor here.)"
            ),
        },
        "IDENTITY": {
            "IDENTITY_COLLISIONS": result.identity_collisions,
            "READY_LIFECYCLE_CREATED_EVENTS": result.ready_lifecycle_created_events,
        },
        "PER_COMBINATION": result.per_combination,
        "PER_E": result.per_e,
        "PER_M": result.per_m,
    }

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Wrote {out_path}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
