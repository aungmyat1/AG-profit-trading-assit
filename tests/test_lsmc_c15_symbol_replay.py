"""C15-LSMC BTCUSD replay: evidence is bound to the dataset and frozen identity, and a short re-run reproduces it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lsmc_c15_symbol_replay as R  # noqa: E402

REPORT = ROOT / "artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_btcusd_vt_recorded_60d/replay_report.json"


def test_committed_report_is_bound_to_the_recorded_dataset_and_contract():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    for name, digest in report["dataset"]["sha256"].items():
        assert R.sha256(R.DATASET_DIR / name) == digest
    ident = report["identity"]
    assert ident["contract_matches_registry"] is True
    assert ident["detection_file_sha256"] == R.identity(R.G.CONTRACT_PATH)["detection_file_sha256"]
    assert report["delivery_mode"] == "ARCHIVE_ONLY"
    assert report["dataset"]["server"] == "VTMarkets-Demo"


def test_committed_report_verdicts():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    counts = report["gate_status_counts"]   # headline: full 30-bar D1 windows only
    scans = report["replay"]["scans_full_d1_window"]
    assert scans + report["short_d1_window"]["scans"] == report["replay"]["scans"]
    assert report["blocking_L1_L4_pass"] is True and report["blocking_L1_L4_pass_full_d1"] is True
    assert report["verdict"] == "NOT_VERIFIED"
    for gate in ("L1", "L2", "L3", "L4"):
        assert counts[gate].get("PASS", 0) + counts[gate].get("NOT_APPLICABLE", 0) == scans
    # OD1011-L5: no cost gate and no bound commission off-host -> WARN, never PASS.
    assert set(counts["L5"]) == {"WARN"}
    assert all(p["prefix_mismatches"] == 0 for p in report["streaming_parity"].values())
    # No C10 pip evidence for BTCUSD: no stop, and the operational lane rejects every opportunity.
    assert report["opportunities"]["with_c10_stop"] == 0
    assert "OPPORTUNITY" not in report["states"]["operational"]
    assert "OPPORTUNITY" not in report["short_d1_window"]["states"]["operational"]


def test_short_rerun_matches_gate_contract():
    report = R.run("BTCUSD", limit=40)   # early scans: short D1 windows only
    assert report["short_d1_window"]["blocking_L1_L4_pass"] is True
    assert report["streaming_parity"]["signal"]["prefix_mismatches"] == 0
    assert report["spread_provenance"]["m5_bars_with_spread"] == report["spread_provenance"]["m5_bars"]
