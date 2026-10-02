"""Offline Research Factory R2 safety tests.

All fixtures are local byte files plus injected rows.  They do not call MT5, a broker,
an exchange, or a network service; the .parquet suffix is intentional because the
provenance gate must verify the immutable file before any decoder is chosen.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from edge_discovery.dataset_ledger import (
    C001_FAST_SCREEN_STAGE, FAST_SCREEN_ROLE_FORBIDDEN, DatasetAccessLedger,
)
from edge_discovery.freeze import (
    C001_MUTATION_REQUIRES_VERSION_BUMP, FrozenIdentityError,
    verify_c001_rule_identity, verify_friction_identity,
)
from edge_discovery.ingestion import DatasetIngestionError, ingest_raw_m5
from edge_discovery.models import load_manifest
from edge_discovery.offline_pipeline import run_crypto_cfd_c001_offline
from edge_discovery.partitions import (
    PartitionFreezeError, build_partition_manifest, freeze_partition_manifest,
)
from edge_discovery.quality import normalize_and_derive, quality_gate

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
C001 = load_manifest(ROOT / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml")


def _rows(start: datetime, count: int) -> list[dict]:
    return [
        {
            "timestamp": (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0,
        }
        for index in range(count)
    ]


def _fixture_bundle(tmp_path: Path, days: int = 1) -> tuple[Path, Path, Path, dict[str, list[dict]]]:
    """Create immutable raw bytes and a matching exporter manifest; decoded rows are
    supplied through the ingestion test seam rather than requiring a Parquet engine."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = {symbol: _rows(start, days * 288) for symbol in ("BTCUSD", "ETHUSD")}
    entries = []
    paths = {}
    for symbol in ("BTCUSD", "ETHUSD"):
        path = tmp_path / f"{symbol}_M5_RAW.parquet"
        path.write_bytes(f"immutable-{symbol}-fixture".encode("ascii"))
        paths[symbol] = path
        entries.append({
            "dataset_id": f"RAW_{symbol}_FIXTURE", "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "symbol": symbol,
            "asset_class": "CRYPTO_CFD", "timeframe": "M5", "broker": "TEST", "environment": "TEST",
            "timestamp_normalization": {
                "source_timezone": "UTC", "normalized_timezone": "UTC", "timestamp_column": "timestamp",
                "timestamp_convention": "OPEN_TIME", "normalization_complete": True,
            },
            "schema": {"columns": ["timestamp", "open", "high", "low", "close", "volume"]},
            "row_count": len(rows[symbol]),
            "coverage": {"start_utc": rows[symbol][0]["timestamp"], "end_utc": rows[symbol][-1]["timestamp"]},
        })
    provenance = tmp_path / "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json"
    provenance.write_text(json.dumps({
        "schema_version": "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE_V1", "datasets": entries,
    }), encoding="utf-8")
    return paths["BTCUSD"], paths["ETHUSD"], provenance, rows


def _loader(rows: dict[str, list[dict]]):
    return lambda path: rows["BTCUSD" if path.name.startswith("BTCUSD") else "ETHUSD"]


def test_provenance_hash_match_and_local_immutable_source(tmp_path):
    btc, _, provenance, rows = _fixture_bundle(tmp_path)
    dataset = ingest_raw_m5(btc, provenance, "BTCUSD", _loader(rows))
    assert dataset.dataset_id == "RAW_BTCUSD_FIXTURE"
    assert dataset.sha256 == hashlib.sha256(btc.read_bytes()).hexdigest()
    assert btc.read_bytes() == b"immutable-BTCUSD-fixture"  # ingestion never rewrites raw bytes


def test_provenance_hash_mismatch_fails_closed(tmp_path):
    btc, _, provenance, rows = _fixture_bundle(tmp_path)
    doc = json.loads(provenance.read_text(encoding="utf-8"))
    doc["datasets"][0]["sha256"] = "0" * 64
    provenance.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DatasetIngestionError, match="PROVENANCE_HASH_MISMATCH"):
        ingest_raw_m5(btc, provenance, "BTCUSD", _loader(rows))


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("symbol", "BTC" + "USDT", "CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN"),
        ("asset_class", "CRYPTO_USDT_PERP", "ASSET_CLASS_MISMATCH"),
    ],
)
def test_wrong_symbol_asset_class_and_perp_cfd_substitution_are_rejected(tmp_path, field, value, code):
    btc, _, provenance, rows = _fixture_bundle(tmp_path)
    doc = json.loads(provenance.read_text(encoding="utf-8"))
    doc["datasets"][0][field] = value
    provenance.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DatasetIngestionError, match=code):
        ingest_raw_m5(btc, provenance, "BTCUSD", _loader(rows))


def test_duplicate_timestamp_and_gap_fail_without_repair(tmp_path):
    btc, _, provenance, rows = _fixture_bundle(tmp_path)
    duplicate_rows = {key: [dict(row) for row in value] for key, value in rows.items()}
    duplicate_rows["BTCUSD"][4]["timestamp"] = duplicate_rows["BTCUSD"][3]["timestamp"]
    duplicate = ingest_raw_m5(btc, provenance, "BTCUSD", _loader(duplicate_rows))
    duplicate_report = quality_gate(duplicate)
    assert duplicate_report.status == "FAIL"
    assert "DUPLICATE_TIMESTAMPS" in duplicate_report.reason_codes

    gap_rows = {key: [dict(row) for row in value] for key, value in rows.items()}
    gap_rows["BTCUSD"].pop(20)
    doc = json.loads(provenance.read_text(encoding="utf-8"))
    doc["datasets"][0]["row_count"] -= 1
    provenance.write_text(json.dumps(doc), encoding="utf-8")
    gap = ingest_raw_m5(btc, provenance, "BTCUSD", _loader(gap_rows))
    gap_report = quality_gate(gap)
    assert gap_report.status == "FAIL"
    assert "UNEXPECTED_M5_GAP" in gap_report.reason_codes
    assert len(gap.bars) == 287  # missing bar was not filled


def test_utc_d1_boundary_and_independent_derived_lineage(tmp_path):
    btc, _, provenance, rows = _fixture_bundle(tmp_path)
    raw = ingest_raw_m5(btc, provenance, "BTCUSD", _loader(rows))
    assert quality_gate(raw).status == "PASS"
    derived = normalize_and_derive(raw, str(tmp_path / "derived"))
    normalized, d1 = derived["NORMALIZED_M5"], derived["D1"]
    assert d1.bars[0].time == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert d1.parent_dataset_id == normalized.dataset_id
    assert d1.transform_id == "UTC_RESAMPLE_D1_V1"
    assert d1.sha256 and d1.artifact_path and d1.artifact_path.is_file()


def test_chronological_nonoverlap_and_immutable_partition_freeze(tmp_path):
    btc, eth, provenance, rows = _fixture_bundle(tmp_path, days=10)
    btc_raw = ingest_raw_m5(btc, provenance, "BTCUSD", _loader(rows))
    eth_raw = ingest_raw_m5(eth, provenance, "ETHUSD", _loader(rows))
    normalized = {
        "BTCUSD": normalize_and_derive(btc_raw)["NORMALIZED_M5"],
        "ETHUSD": normalize_and_derive(eth_raw)["NORMALIZED_M5"],
    }
    manifest = build_partition_manifest(normalized)
    dev, validation, holdout = (manifest.partitions[name] for name in ("DEV", "VALIDATION", "HOLDOUT"))
    assert dev.end_utc <= validation.start_utc <= validation.end_utc <= holdout.start_utc
    assert not set(dev.days) & set(validation.days)
    assert not set(validation.days) & set(holdout.days)
    target = tmp_path / "partitions.json"
    frozen = freeze_partition_manifest(manifest, target)
    assert freeze_partition_manifest(manifest, target).manifest_sha256 == frozen.manifest_sha256
    target.write_text("tampered", encoding="utf-8")
    with pytest.raises(PartitionFreezeError, match="PARTITION_MANIFEST_IMMUTABILITY_VIOLATION"):
        freeze_partition_manifest(manifest, target)


def test_c001_fast_screen_holdout_denial_and_ledger_recording(tmp_path):
    ledger = DatasetAccessLedger(tmp_path / "ledger.jsonl")
    dev = ledger.request_fast_screen_access(C001, "BTC_DEV", "DEV", "FAST_SCREEN_DEV_REPLAY")
    assert dev.granted and dev.access_stage == C001_FAST_SCREEN_STAGE
    mutated = dataclasses.replace(C001, dataset_roles_allowed=("DEV", "HOLDOUT"))
    denied = ledger.request_fast_screen_access(mutated, "BTC_HOLD", "HOLDOUT", "FAST_SCREEN_HOLDOUT")
    assert not denied.granted and denied.denial_reason == FAST_SCREEN_ROLE_FORBIDDEN
    assert ledger.records()[-1].access_stage == C001_FAST_SCREEN_STAGE
    assert ledger.holdout_accessed_by_c001_fast_screen() is False


def test_c001_cannot_run_before_quality_and_sufficiency_gates(tmp_path):
    btc, eth, provenance, rows = _fixture_bundle(tmp_path)
    bad_rows = {key: [dict(row) for row in value] for key, value in rows.items()}
    bad_rows["BTCUSD"].pop(5)
    doc = json.loads(provenance.read_text(encoding="utf-8"))
    doc["datasets"][0]["row_count"] -= 1
    provenance.write_text(json.dumps(doc), encoding="utf-8")
    ledger_path = tmp_path / "ledger.jsonl"
    report = run_crypto_cfd_c001_offline(
        btc, eth, provenance, ROOT, ledger_path=ledger_path, frame_loader=_loader(bad_rows),
        artifact_root=tmp_path / "derived", partition_manifest_path=tmp_path / "partition.json",
    )
    assert report.final_verdict == "BLOCKED_DATA_QUALITY"
    assert report.c001_run is False
    assert report.gates["QUALITY_GATE"]["status"] == "FAIL"
    assert not ledger_path.exists() or not DatasetAccessLedger(ledger_path).records()


def test_c001_runs_only_after_all_offline_gates_and_never_reads_holdout(tmp_path):
    # Ten complete days allocate 6/2/2 under the frozen chronological policy.  Constant
    # candles are a non-economic plumbing fixture; a zero-trade result is expected and
    # remains INCONCLUSIVE rather than becoming a synthetic edge claim.
    btc, eth, provenance, rows = _fixture_bundle(tmp_path, days=10)
    ledger_path = tmp_path / "ledger.jsonl"
    report = run_crypto_cfd_c001_offline(
        btc, eth, provenance, ROOT, ledger_path=ledger_path, frame_loader=_loader(rows),
        artifact_root=tmp_path / "derived", partition_manifest_path=tmp_path / "partition.json",
    )
    assert report.c001_run is True
    assert report.gates["PROVENANCE_GATE"]["status"] == "PASS"
    assert report.gates["QUALITY_GATE"]["status"] == "PASS"
    assert report.gates["RESEARCH_SUFFICIENCY"]["status"] == "PASS"
    assert report.gates["PARTITION_FREEZE"]["status"] == "PASS"
    assert report.gates["HOLDOUT_FIREWALL"]["HOLDOUT_ACCESSED_BY_C001_FAST_SCREEN"] is False
    assert report.c001["FAST_SCREEN_STATUS"] == "FAST_SCREEN_INCONCLUSIVE"
    assert report.c001["EDGE_VERIFIED"] is False
    required_metrics = {
        "N", "wins", "losses", "win_rate", "gross_R", "net_R", "gross_expectancy_R",
        "net_expectancy_R", "profit_factor_gross", "profit_factor_net", "max_drawdown_R",
        "average_win_R", "average_loss_R", "long_count", "short_count", "BTCUSD_count", "ETHUSD_count",
    }
    assert required_metrics.issubset(report.c001["BASE_FRICTION"])
    assert all(record.dataset_role == "DEV" for record in DatasetAccessLedger(ledger_path).records())


def test_c001_and_friction_frozen_identity_and_mutation_version_bump_rejection(tmp_path):
    assert verify_c001_rule_identity(ROOT).status == "PASS"
    assert verify_friction_identity(ROOT).status == "PASS"
    record = json.loads((ROOT / "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json").read_text())
    clone = tmp_path / "clone"
    for relative in record["contract_file_sha256"]:
        source, target = ROOT / relative, clone / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in (
        "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml",
        "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json",
    ):
        source, target = ROOT / relative, clone / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    rules = clone / "src/crypto_cfd_contract/rules.py"
    rules.write_text(rules.read_text(encoding="utf-8") + "\n# attempted post-result mutation\n", encoding="utf-8")
    with pytest.raises(FrozenIdentityError, match=C001_MUTATION_REQUIRES_VERSION_BUMP):
        verify_c001_rule_identity(clone)
