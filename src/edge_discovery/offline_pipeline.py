"""Offline Research Factory orchestration for the frozen ``CRYPTO_CFD_C001`` screen.

Ordered gates are intentionally explicit.  No C001 price outcome is read until local
raw-file provenance, quality, pre-outcome research sufficiency, chronological partition
freeze, and the DEV-only holdout firewall have all passed.  This is a research-only
falsification path; it has no broker, runtime, proposal, risk, or execution authority.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .contractability import AvailableDataset, evaluate_contractability
from .dataset_ledger import DatasetAccessLedger
from .freeze import FrozenIdentityError, verify_c001_rule_identity, verify_friction_identity
from .friction import SCENARIOS, SCREEN_SCENARIO
from .ingestion import DatasetIngestionError, DerivedDataset, OhlcBar, RawDataset, ingest_raw_m5
from .lanes import LaneIsolationError, assert_lane_compatible
from .models import load_manifest
from .partitions import (
    PartitionFreezeError, build_partition_manifest, freeze_partition_manifest,
    partition_dataset_id, slice_partition,
)
from .quality import QualityGateReport, normalize_and_derive, quality_gate
from .research_sufficiency import ResearchSufficiencyReport, evaluate_research_sufficiency
from .promotion import decide

C001_ID = "CRYPTO_CFD_C001"
C001_STRATEGY_ID = "ST_CRYPTO_CFD_SWEEP_RETEST_V1"


@dataclass(frozen=True)
class OfflineRunReport:
    report_schema: str
    candidate_id: str
    final_verdict: str
    c001_run: bool
    edge_verified: bool
    gates: Mapping[str, Any]
    datasets: Mapping[str, Any]
    partitions: Mapping[str, Any]
    c001: Mapping[str, Any]

    def as_dict(self) -> Mapping[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    return value


def _gate(status: str, reason_codes: Sequence[str] = (), **extra: Any) -> Mapping[str, Any]:
    return {"status": status, "reason_codes": list(reason_codes), **extra}


def _dataset_summary(dataset: RawDataset, quality: Optional[QualityGateReport] = None) -> Mapping[str, Any]:
    return {
        "dataset_id": dataset.dataset_id, "sha256": dataset.sha256, "symbol": dataset.symbol,
        "asset_class": dataset.asset_class, "timeframe": dataset.timeframe,
        "coverage": (quality.coverage if quality else dict(dataset.declared_coverage)),
        "broker": dataset.broker, "environment": dataset.environment,
        "parent_dataset_id": None, "transform_id": "RAW_M5_IMMUTABLE",
    }


def _block(
    verdict: str, gates: Mapping[str, Any], datasets: Mapping[str, Any] | None = None,
    partitions: Mapping[str, Any] | None = None, c001: Mapping[str, Any] | None = None,
) -> OfflineRunReport:
    return OfflineRunReport(
        report_schema="AG_EDGE_DISCOVERY_OFFLINE_RUN_V1", candidate_id=C001_ID,
        final_verdict=verdict, c001_run=False, edge_verified=False, gates=gates,
        datasets=datasets or {}, partitions=partitions or {},
        c001=c001 or {
            "C001_RUN": False, "C001_RULES_CHANGED": False, "FAST_SCREEN_STATUS": "NOT_EVALUATED",
            "EDGE_VERIFIED": False,
        },
    )


def _candles(bars: Sequence[OhlcBar]) -> tuple:
    # Delayed import protects all ingestion/provenance/quality block states from the
    # strategy replay dependency graph.  It runs only after every data/firewall gate.
    from strategy_engine.session import Candle
    return tuple(Candle(time=bar.time, open=bar.open, high=bar.high, low=bar.low,
                        close=bar.close, volume=bar.volume) for bar in bars)


def run_crypto_cfd_c001_offline(
    btc_raw_path: Path,
    eth_raw_path: Path,
    provenance_path: Path,
    repository_root: Path,
    artifact_root: Optional[Path] = None,
    partition_manifest_path: Optional[Path] = None,
    ledger_path: Optional[Path] = None,
    frame_loader: Optional[Callable[[Path], Sequence[Mapping[str, Any]]]] = None,
) -> OfflineRunReport:
    """Run the full ordered offline C001 factory.  A missing source is an expected,
    non-exceptional blocked outcome; malformed or mismatched source provenance fails
    closed with a structured report.  ``frame_loader`` is solely a test fixture seam.
    """
    root = Path(repository_root)
    btc_raw_path, eth_raw_path, provenance_path = map(Path, (btc_raw_path, eth_raw_path, provenance_path))
    missing = [str(path) for path in (btc_raw_path, eth_raw_path, provenance_path) if not path.is_file()]
    if missing:
        return _block(
            "BLOCKED_DATASET_UNAVAILABLE",
            {
                "DATASET_INGESTION": _gate("FAIL", ["RAW_DATASET_OR_PROVENANCE_UNAVAILABLE"], missing_paths=missing),
                "PROVENANCE_GATE": _gate("NOT_EVALUATED"),
                "QUALITY_GATE": _gate("NOT_EVALUATED"),
                "RESEARCH_SUFFICIENCY": _gate("NOT_EVALUATED"),
                "PARTITION_FREEZE": _gate("NOT_EVALUATED"),
                "HOLDOUT_FIREWALL": _gate("NOT_EVALUATED"),
            },
        )

    # Gate 1: local bytes + exporter provenance.  No fallback instrument exists.
    raw: Dict[str, RawDataset] = {}
    try:
        raw["BTCUSD"] = ingest_raw_m5(btc_raw_path, provenance_path, "BTCUSD", frame_loader)
        raw["ETHUSD"] = ingest_raw_m5(eth_raw_path, provenance_path, "ETHUSD", frame_loader)
        for symbol, dataset in raw.items():
            assert_lane_compatible("CRYPTO_CFD", dataset.asset_class, symbol)
    except (DatasetIngestionError, LaneIsolationError) as exc:
        return _block(
            "BLOCKED_PROVENANCE",
            {
                "DATASET_INGESTION": _gate("FAIL", [getattr(exc, "code", str(exc).split(":")[0])], detail=str(exc)),
                "PROVENANCE_GATE": _gate("FAIL", [getattr(exc, "code", str(exc).split(":")[0])]),
                "QUALITY_GATE": _gate("NOT_EVALUATED"),
                "RESEARCH_SUFFICIENCY": _gate("NOT_EVALUATED"),
                "PARTITION_FREEZE": _gate("NOT_EVALUATED"),
                "HOLDOUT_FIREWALL": _gate("NOT_EVALUATED"),
            }, datasets={symbol: _dataset_summary(dataset) for symbol, dataset in raw.items()},
        )

    datasets = {symbol: _dataset_summary(dataset) for symbol, dataset in raw.items()}
    gates: Dict[str, Any] = {
        "DATASET_INGESTION": _gate("PASS"),
        "PROVENANCE_GATE": _gate("PASS"),
    }

    # Gate 2: deterministic quality, with no bar fill/repair.
    quality = {symbol: quality_gate(dataset) for symbol, dataset in raw.items()}
    gates["QUALITY_GATE"] = _gate(
        "PASS" if all(report.status == "PASS" for report in quality.values()) else "FAIL",
        [code for report in quality.values() for code in report.reason_codes],
        by_symbol={symbol: _jsonable(report) for symbol, report in quality.items()},
    )
    datasets = {symbol: {**datasets[symbol], "coverage": quality[symbol].coverage}
                for symbol in datasets}
    if gates["QUALITY_GATE"]["status"] != "PASS":
        return _block("BLOCKED_DATA_QUALITY", gates, datasets=datasets)

    derived = {
        symbol: normalize_and_derive(dataset, None if artifact_root is None else str(artifact_root / symbol))
        for symbol, dataset in raw.items()
    }
    normalized = {symbol: derived[symbol]["NORMALIZED_M5"] for symbol in derived}
    for symbol, artifact_set in derived.items():
        datasets[symbol]["derived_lineage"] = {
            name: {
                "dataset_id": artifact.dataset_id, "parent_dataset_id": artifact.parent_dataset_id,
                "transform_id": artifact.transform_id, "sha256": artifact.sha256,
            }
            for name, artifact in artifact_set.items()
        }

    # Gate 3: coverage only.  This happens before any C001 outcome/replay call.
    sufficiency = evaluate_research_sufficiency(normalized)
    gates["RESEARCH_SUFFICIENCY"] = _gate(
        sufficiency.status, sufficiency.reason_codes, report=_jsonable(sufficiency),
    )
    if sufficiency.status != "PASS":
        return _block("BLOCKED_RESEARCH_INSUFFICIENCY", gates, datasets=datasets)

    # Gate 4: immutable, chronological, strategy-blind partition freeze.
    try:
        partition = build_partition_manifest(normalized)
        partition_path = partition_manifest_path or (
            root / "research/edge_discovery/partition_manifests/CRYPTO_CFD_UTC_COHORT_V1.json"
        )
        partition = freeze_partition_manifest(partition, partition_path)
    except PartitionFreezeError as exc:
        gates["PARTITION_FREEZE"] = _gate("FAIL", [exc.code], detail=str(exc))
        return _block("BLOCKED_RESEARCH_INSUFFICIENCY", gates, datasets=datasets)
    partitions = {
        "partition_policy_id": partition.policy_id, "manifest_sha256": partition.manifest_sha256,
        "manifest_path": str(partition.path),
        **{name: _jsonable(item) for name, item in partition.partitions.items()},
    }
    gates["PARTITION_FREEZE"] = _gate("PASS", manifest_sha256=partition.manifest_sha256)

    # Gate 5: current and future C001 fast-screen access is DEV-only.
    ledger = DatasetAccessLedger(ledger_path or root / "research/edge_discovery/dataset_access_ledger.jsonl")
    holdout_touched = ledger.holdout_accessed_by_c001_fast_screen()
    gates["HOLDOUT_FIREWALL"] = _gate(
        "FAIL" if holdout_touched else "PASS",
        ["HOLDOUT_ACCESSED_BY_C001_FAST_SCREEN"] if holdout_touched else [],
        HOLDOUT_ACCESSED_BY_C001_FAST_SCREEN=holdout_touched,
    )
    if holdout_touched:
        return _block("BLOCKED_DATA_QUALITY", gates, datasets=datasets, partitions=partitions)

    # Existing C001/frozen-friction identities are gates too.  A rule/model mutation is
    # not a configuration option: it needs C002+ and stops this C001 run.
    try:
        c001_identity = verify_c001_rule_identity(root)
        friction_identity = verify_friction_identity(root)
    except FrozenIdentityError as exc:
        gates["C001_FROZEN_IDENTITY"] = _gate("FAIL", [exc.code], detail=str(exc))
        return _block("BLOCKED_PROVENANCE", gates, datasets=datasets, partitions=partitions)
    gates["C001_FROZEN_IDENTITY"] = _gate("PASS", checked_files=_jsonable(c001_identity.checked_files))
    gates["FRICTION_FREEZE"] = _gate("PASS", checked_files=_jsonable(friction_identity.checked_files))

    manifest = load_manifest(root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml")
    contractability = evaluate_contractability(
        manifest,
        [AvailableDataset(partition_dataset_id(normalized[symbol], partition.partitions["DEV"]),
                          symbol, "CRYPTO_CFD", "DEV", ("M5", "M15", "H1", "D1"))
         for symbol in ("BTCUSD", "ETHUSD")],
    )
    gates["CONTRACTABILITY"] = _gate(contractability.status, contractability.reason_codes)
    if contractability.status != "PASS":
        return _block("BLOCKED_RESEARCH_INSUFFICIENCY", gates, datasets=datasets, partitions=partitions)

    # Gates pass.  C001 reads only the frozen DEV partition; VALIDATION/HOLDOUT are never
    # converted to CandleDataset objects in this fast-screen function. Delaying these
    # imports also means a missing/bad local dataset never needs any broker/runtime code.
    from .fast_screen import compute_metrics
    from .replay_c001 import CandleDataset, replay_c001, reprice_friction_scenario

    base_geometry_trades = []
    for symbol in ("BTCUSD", "ETHUSD"):
        dev = partition.partitions["DEV"]
        slice_bars = slice_partition(normalized[symbol], dev)
        dataset = CandleDataset(
            dataset_id=partition_dataset_id(normalized[symbol], dev), symbol=symbol,
            asset_class="CRYPTO_CFD", role="DEV", m5_candles=_candles(slice_bars),
            provenance=f"partition_manifest={partition.manifest_sha256}",
        )
        base_geometry_trades.extend(replay_c001(manifest, dataset, ledger, SCREEN_SCENARIO))
    # Frozen friction changes cost only, not a price outcome.  Reprice the one DEV-only
    # geometry replay rather than reading the partition again per scenario.
    scenario_metrics: Dict[str, Any] = {
        scenario: compute_metrics(reprice_friction_scenario(base_geometry_trades, scenario))
        for scenario in SCENARIOS
    }

    screen, promotion = decide(
        C001_ID, scenario_metrics[SCREEN_SCENARIO],
        [partition_dataset_id(normalized[symbol], partition.partitions["DEV"])
         for symbol in ("BTCUSD", "ETHUSD")], SCREEN_SCENARIO,
    )
    verdict = {
        "FAST_SCREEN_FAIL": "C001_FAST_SCREEN_FAIL",
        "FAST_SCREEN_INCONCLUSIVE": "C001_FAST_SCREEN_INCONCLUSIVE",
        "FAST_SCREEN_PASS": "C001_FROZEN_FOR_VERIFICATION",
    }[screen.status]
    c001 = {
        "C001_RUN": True, "C001_RULES_CHANGED": False,
        "C001_N": scenario_metrics[SCREEN_SCENARIO]["N"],
        "C001_NET_EXPECTANCY_R": scenario_metrics[SCREEN_SCENARIO]["net_expectancy_R"],
        "C001_PF_NET": scenario_metrics[SCREEN_SCENARIO]["profit_factor_net"],
        "C001_MAX_DRAWDOWN_R": scenario_metrics[SCREEN_SCENARIO]["max_drawdown_R"],
        "BASE_FRICTION": scenario_metrics["BASE"],
        "STRESS_FRICTION": scenario_metrics["STRESS"],
        "SEVERE_FRICTION": scenario_metrics["SEVERE"],
        "FAST_SCREEN_STATUS": screen.status,
        "PROMOTION_REASON_CODES": list(promotion.reason_codes),
        "NEXT_STATUS": promotion.next_status.value,
        "FULL_VERIFICATION_STATUS": promotion.full_verification_status,
        "EDGE_VERIFIED": False,
    }
    # This must remain false even after replay: a survivor is only frozen for EdgeLab.
    gates["HOLDOUT_FIREWALL"] = _gate(
        "PASS", HOLDOUT_ACCESSED_BY_C001_FAST_SCREEN=ledger.holdout_accessed_by_c001_fast_screen()
    )
    return OfflineRunReport(
        report_schema="AG_EDGE_DISCOVERY_OFFLINE_RUN_V1", candidate_id=C001_ID,
        final_verdict=verdict, c001_run=True, edge_verified=False, gates=gates,
        datasets=datasets, partitions=partitions, c001=c001,
    )


def write_run_report(report: OfflineRunReport, path: Path) -> Path:
    """Write a deterministic, standalone report.  It contains results only if gates
    admitted C001; a blocked report contains no fabricated profitability metric."""
    path = Path(path)
    payload = json.dumps(report.as_dict(), sort_keys=True, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


__all__ = ["OfflineRunReport", "run_crypto_cfd_c001_offline", "write_run_report"]
