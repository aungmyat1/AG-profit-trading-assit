"""Proves src/external_candidate/ carries no execution/broker authority and that
feeding its synthetic OOS evidence through the REAL (unsigned)
config/governance/economic_gate_contract.yaml still fails closed -- this new
candidate-validation layer cannot be used to bypass the R6 signature requirement.
"""
from __future__ import annotations

import ast
import os

from performance.models import ResolvedTradeSample
from performance.calculator import compute_trade_metrics
from validation_framework.economic_gate import (
    VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS,
    evaluate_economic_gate,
    load_contract,
)

_FORBIDDEN_MODULE_PREFIXES = ("mt5", "execution", "MetaTrader5")


def _iter_external_candidate_source_files():
    package_dir = os.path.join("src", "external_candidate")
    for root, _dirs, files in os.walk(package_dir):
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def test_no_execution_or_broker_imports_anywhere_in_the_package():
    for path in _iter_external_candidate_source_files():
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                if name and name.split(".")[0] in _FORBIDDEN_MODULE_PREFIXES:
                    raise AssertionError(f"{path} imports forbidden module {name!r}")


def test_synthetic_oos_evidence_cannot_bypass_unsigned_r6_contract():
    # TEST_ONLY synthetic sample -- never real strategy evidence.
    samples = [
        ResolvedTradeSample(
            source_record_id="TEST_ONLY_1", source_path="TEST_ONLY", strategy_id="ST_SYNTHETIC_TEST_ONLY_V1",
            strategy_version="1.0.0", symbol="EURUSD", cycle="c1", resolved_at="2026-09-01T00:00:00+00:00",
            gross_R=5.0, net_R=5.0, cost_status="INCLUDED_CONTRACT_CEILING", outcome="TEST_ONLY",
        )
        for _ in range(50)
    ]
    metrics = compute_trade_metrics(samples)
    real_contract = load_contract()  # reads the REAL repo file, still identity.status: PROPOSED
    verdict = evaluate_economic_gate(
        "ST_SYNTHETIC_TEST_ONLY_V1", "1.0.0", metrics, evidence_complete=True, contract=real_contract,
    )
    assert verdict.verdict == VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS
