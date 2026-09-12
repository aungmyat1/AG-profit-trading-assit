"""TEST_ONLY. SYNTHETIC. NOT_STRATEGY_EVIDENCE. NOT_R6_EVIDENCE.

Fixture helpers for src/external_candidate/ tests. Every value below is invented
purely to exercise the admission/parity/OOS/walk-forward code paths -- it is not a
real Gemini candidate, must never be cited as strategy performance evidence, and
must never be fed into validation_framework/economic_gate.py as if it were real.
This module is not itself a test file (pytest's default `test_*.py` collection
pattern does not match it) -- it is imported by the real test modules.
"""
from __future__ import annotations

from external_candidate.models import (
    SCHEMA_VERSION,
    CandidateProvenance,
    CandidateRules,
    DatasetPartition,
    DatasetRole,
    ExternalCandidatePackage,
    FrictionAssumptions,
    HoldoutDeclaration,
)

SYNTHETIC_STRATEGY_ID = "ST_SYNTHETIC_TEST_ONLY_V1"

_ALL_RULE_SECTIONS = {
    "entry_rules": "TEST_ONLY: enter on synthetic sweep confirmation",
    "exit_rules": "TEST_ONLY: exit at synthetic target or stop",
    "direction_rules": "TEST_ONLY: long only",
    "regime_rules": "TEST_ONLY: RANGE only",
    "session_rules": "TEST_ONLY: ASIAN_LONDON only",
    "filters": "TEST_ONLY: none",
    "sl_logic": "TEST_ONLY: fixed 10 pip stop",
    "tp_logic": "TEST_ONLY: fixed 20 pip target",
    "trade_management_logic": "TEST_ONLY: no partials",
    "position_risk_assumptions": "TEST_ONLY: 0.5% risk per trade",
}


def make_dataset(role: DatasetRole, dataset_id: str, start: str, end: str, fingerprint: str = "sha256:test") -> DatasetPartition:
    return DatasetPartition(
        role=role, dataset_id=dataset_id, symbol="EURUSD", timeframe="M15",
        utc_start=start, utc_end=end, dataset_fingerprint=fingerprint,
        source="TEST_ONLY", timezone_status="BROKER_OFFSET_CONFIRMED",
    )


def make_candidate_package(
    *, candidate_version: str = "1.1.0", parent_strategy_version=None,
    candidate_frozen: bool = True, holdout_used_for_optimization: bool = False,
    rules_changed_after_holdout: bool = False, config_hash: str = "sha256:candidate-config-test",
    strategy_config_ref: str = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml",
    holdout_start: str = "2026-07-01T00:00:00+00:00", holdout_end: str = "2026-07-31T00:00:00+00:00",
    optimization_start: str = "2026-01-01T00:00:00+00:00", optimization_end: str = "2026-06-30T00:00:00+00:00",
    strategy_id: str = SYNTHETIC_STRATEGY_ID,
) -> ExternalCandidatePackage:
    holdout_ds = make_dataset(DatasetRole.HOLDOUT, "SYNTHETIC_HOLDOUT_2026H2", holdout_start, holdout_end, "sha256:holdout-test")
    optimization_ds = make_dataset(DatasetRole.OPTIMIZATION, "SYNTHETIC_OPT_2026H1", optimization_start, optimization_end, "sha256:opt-test")

    return ExternalCandidatePackage(
        schema_version=SCHEMA_VERSION,
        candidate_id="CANDIDATE_TEST_ONLY_0001",
        strategy_id=strategy_id,
        candidate_version=candidate_version,
        parent_strategy_version=parent_strategy_version,
        frozen_at_utc="2026-09-12T00:00:00+00:00",
        candidate_frozen=candidate_frozen,
        rules=CandidateRules(
            strategy_config_ref=strategy_config_ref,
            rule_sections=dict(_ALL_RULE_SECTIONS),
            parameters={"risk_per_trade_pct": 0.5, "stop_pips": 10, "target_pips": 20},
        ),
        datasets=(holdout_ds, optimization_ds),
        holdout=HoldoutDeclaration(
            holdout_dataset_id="SYNTHETIC_HOLDOUT_2026H2",
            holdout_used_for_optimization=holdout_used_for_optimization,
            rules_changed_after_holdout=rules_changed_after_holdout,
        ),
        friction=FrictionAssumptions(
            spread=2.0, spread_unit="pips", commission=0.0, commission_unit="per_lot",
            slippage=1.0, slippage_unit="pips",
        ),
        provenance=CandidateProvenance(
            candidate_config_hash=config_hash,
            dataset_fingerprints=("sha256:holdout-test", "sha256:opt-test"),
            research_source="TEST_ONLY_SYNTHETIC_GEMINI_STUB",
            research_run_id="TEST_RUN_0001",
        ),
    )
