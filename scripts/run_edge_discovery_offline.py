#!/usr/bin/env python3
"""Run AG Edge Discovery R2 against locally exported immutable Crypto-CFD files.

Example (no MT5/broker/network dependency):
  python scripts/run_edge_discovery_offline.py --input-dir /exports/crypto-cfd

The input directory must contain BTCUSD_M5_RAW.parquet, ETHUSD_M5_RAW.parquet, and
AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json.  A missing input produces a structured blocked
report, never a fallback live fetch or BTCUSDT/ETHUSDT substitution.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The repository keeps Python packages under src/ without requiring a runtime install.
# This CLI therefore remains usable on an exporter machine with only requirements.txt.
# Root is retained for the repository's portable MetaTrader5 stub if a later C001 replay
# reaches the frozen strategy code; missing-data/provenance outcomes import none of it.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from edge_discovery.offline_pipeline import run_crypto_cfd_c001_offline, write_run_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/research/crypto_cfd_raw"))
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts/research/edge_discovery"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/research/edge_discovery/AG_EDGE_DISCOVERY_ACCELERATION_R2_report.json"))
    parser.add_argument("--ledger", type=Path, default=Path("research/edge_discovery/dataset_access_ledger.jsonl"))
    parser.add_argument("--partition-manifest", type=Path,
                        default=Path("research/edge_discovery/partition_manifests/CRYPTO_CFD_UTC_COHORT_V1.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.input_dir
    report = run_crypto_cfd_c001_offline(
        source / "BTCUSD_M5_RAW.parquet", source / "ETHUSD_M5_RAW.parquet",
        source / "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json", root,
        artifact_root=args.artifact_root, partition_manifest_path=args.partition_manifest,
        ledger_path=args.ledger,
    )
    output = write_run_report(report, args.report)
    print(f"{report.final_verdict}: {output}")
    # A blocked data/provenance state is a valid deterministic research outcome.  The
    # non-zero return is reserved for a coding/IO exception outside this classification.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
