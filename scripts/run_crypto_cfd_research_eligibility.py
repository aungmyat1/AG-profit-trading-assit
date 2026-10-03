#!/usr/bin/env python3
"""Build Crypto-CFD clean-window quarantine manifests without replaying C001.

This accepts only immutable PR #32 local exports plus their provenance manifest. It
preserves RAW_DATA_QUALITY=BLOCKED_UNKNOWN_GAPS and stops before R2 partitions, the
holdout ledger, candidate replay, profitability, or any broker/runtime activity.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from edge_discovery.pr32_dataset_adapter import load_pr32_raw_dataset
from edge_discovery.research_eligibility import (
    AUTHORITATIVE_RAW_SHA256, EligibilityError, EligibilityReason, ResearchWindowEligibility,
    derive_complete_timeframe, freeze_eligibility_manifest,
)


def _summary(manifest, eligible_bars) -> dict:
    return {
        "TOTAL_UTC_DAYS": len(manifest.reference_days),
        "COMPLETE_REFERENCE_DAYS": sum(record.eligible for record in manifest.reference_days),
        "QUARANTINED_REFERENCE_DAYS": sum(not record.eligible for record in manifest.reference_days),
        "ELIGIBLE_OBSERVATION_WINDOWS": sum(record.eligible for record in manifest.observation_days),
        "UNKNOWN_GAP_REFERENCE_DAYS": sum(
            EligibilityReason.UNKNOWN_GAP_REFERENCE_DAY in record.reasons for record in manifest.reference_days
        ),
        "UNKNOWN_GAP_OBSERVATION_WINDOWS": sum(
            EligibilityReason.UNKNOWN_GAP_OBSERVATION_WINDOW in record.reasons for record in manifest.observation_days
        ),
        "M15_DERIVATION_COUNT": len(derive_complete_timeframe(eligible_bars, "M15")),
        "H1_DERIVATION_COUNT": len(derive_complete_timeframe(eligible_bars, "H1")),
        "D1_DERIVATION_COUNT": len(derive_complete_timeframe(eligible_bars, "D1")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/research/raw/crypto_cfd")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "research/edge_discovery/eligibility_manifests")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "artifacts/research/edge_discovery/AG_CRYPTO_CFD_RESEARCH_ELIGIBILITY_R1.json")
    args = parser.parse_args()

    provenance = args.input_dir / "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json"
    raw_paths = {symbol: args.input_dir / f"{symbol}_M5_RAW.parquet" for symbol in AUTHORITATIVE_RAW_SHA256}
    if not provenance.is_file() or any(not path.is_file() for path in raw_paths.values()):
        report = {
            "schema_version": "AG_CRYPTO_CFD_RESEARCH_ELIGIBILITY_RUN_V1",
            "RAW_DATA_QUALITY": "BLOCKED_UNKNOWN_GAPS",
            "RAW_HASH_MATCH": "NOT_EVALUATED_SOURCE_FILES_UNAVAILABLE",
            "C001_RUN": False, "PARTITIONS_CREATED": False,
            "HOLDOUT_ACCESSED_BY_STRATEGY": False,
            "FINAL_VERDICT": "BLOCKED_INSUFFICIENT_CLEAN_DATA",
        }
    else:
        manifests = {}
        eligible_days_by_symbol = {}
        for symbol, raw_path in raw_paths.items():
            raw = load_pr32_raw_dataset(raw_path, provenance, symbol)
            engine = ResearchWindowEligibility(raw)
            manifest = freeze_eligibility_manifest(
                engine.build_manifest(), args.output_dir / f"{symbol}_RESEARCH_ELIGIBILITY_V1.json",
            )
            eligible = engine.eligible_observation_m5(manifest)
            eligible_days_by_symbol[symbol] = {
                record.utc_date for record in manifest.observation_days if record.eligible
            }
            manifests[symbol] = {
                "dataset_id": raw.dataset_id, "raw_sha256": raw.sha256,
                "manifest_path": str(manifest.path), "manifest_sha256": manifest.manifest_sha256,
                **_summary(manifest, eligible.bars),
            }
        common_eligible_days = set.intersection(*eligible_days_by_symbol.values())
        # R2's already-frozen 60/20/20 partition allocator needs five common complete
        # observation days for non-empty DEV, VALIDATION, and HOLDOUT; this is not a
        # profitability sample threshold.
        ready = len(common_eligible_days) >= 5
        report = {
            "schema_version": "AG_CRYPTO_CFD_RESEARCH_ELIGIBILITY_RUN_V1",
            "RAW_DATA_QUALITY": "BLOCKED_UNKNOWN_GAPS", "RAW_HASH_MATCH": True,
            "symbols": manifests, "COMMON_ELIGIBLE_OBSERVATION_DAYS": len(common_eligible_days),
            "C001_RUN": False, "PARTITIONS_CREATED": False,
            "HOLDOUT_ACCESSED_BY_STRATEGY": False,
            "FINAL_VERDICT": ("RESEARCH_ELIGIBILITY_READY_FOR_PARTITIONING" if ready
                              else "BLOCKED_INSUFFICIENT_CLEAN_DATA"),
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
