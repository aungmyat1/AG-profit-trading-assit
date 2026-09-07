"""Large-SMC execution-boundary invariant guard (RESEARCH_ONLY / RESEARCH_DRAFT,
proposal_generation_authorized: false). Same static-import-scan convention as
tests/test_btc_proposal_execution_boundary.py's
test_btc_sweep_research_package_never_imports_forbidden_modules -- reused, not
reinvented, per this repo's own established project convention for research-package
execution isolation.

Ensures src/large_smc_research/ (and its runner scripts) can never import broker/
order-placement infrastructure, regardless of C10/C14 governance state.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
RESEARCH_DIR = SRC_ROOT / "large_smc_research"

# Same forbidden set tests/test_btc_proposal_execution_boundary.py already protects
# (execution.executor, execution.coordinator, execution.adapter, mt5.management_gateway),
# plus two clearly authoritative equivalents this guard also covers: execution.mt5_gateway
# (the only module allowed to call order_check/order_send for an existing position --
# execution/mt5_gateway.py's own docstring) and mt5.deals (real broker deal/position
# history, mt5/deals.py). Not "src.execution" -- this repo's own import convention is
# "execution.<module>", never "src.execution.<module>" (verified against the BTC guard).
FORBIDDEN_MODULES = {
    "execution.executor",
    "execution.coordinator",
    "execution.adapter",
    "execution.mt5_gateway",
    "mt5.management_gateway",
    "mt5.deals",
}


def _research_files():
    assert RESEARCH_DIR.exists(), "src/large_smc_research directory missing"
    return sorted(RESEARCH_DIR.glob("*.py"))


def _scan(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_MODULES:
                    violations.append(f"{path}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_MODULES:
                violations.append(f"{path}: from {module} import ...")
    return violations


@pytest.mark.parametrize("path", _research_files(), ids=lambda p: p.name)
def test_large_smc_research_package_never_imports_execution_modules(path: Path):
    violations = _scan(path)
    assert not violations, f"Execution boundary breached in Large-SMC research layer: {violations}"


@pytest.mark.parametrize(
    "script_name",
    ["run_large_smc_discovery.py", "run_large_smc_outcome_lifecycle_check.py"],
)
def test_large_smc_runner_scripts_never_import_execution_modules(script_name: str):
    script_path = REPO_ROOT / "scripts" / script_name
    assert script_path.exists(), f"{script_path} missing"
    violations = _scan(script_path)
    assert not violations, f"Execution boundary breached in {script_name}: {violations}"
