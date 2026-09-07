"""Static import-boundary check for the Large-SMC live-batch watcher
(AG_PROPOSAL_RUNTIME_LARGE_SMC_WATCH_AND_PERFORMANCE_HISTORY_V1): mirrors
tests/test_btc_proposal_execution_boundary.py's package-level check. This watcher
re-runs read-only research replay (historical_replay.orchestrator.run_replay) against
live-fetched candles and persists the result to a research ledger -- it must never
import an order-placement path.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_MODULES = {"execution.executor", "mt5.management_gateway", "execution.coordinator", "execution.adapter"}
FORBIDDEN_PREFIXES = tuple(FORBIDDEN_MODULES)


def _assert_no_forbidden_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in FORBIDDEN_MODULES, f"{path.name} imports forbidden module {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in FORBIDDEN_MODULES, f"{path.name} imports forbidden module {module}"
            assert not any(module.startswith(p) for p in FORBIDDEN_PREFIXES), (
                f"{path.name} imports forbidden module path {module}"
            )


def test_run_large_smc_live_watch_script_never_imports_forbidden_modules():
    _assert_no_forbidden_imports(REPO_ROOT / "scripts" / "run_large_smc_live_watch.py")


def test_large_smc_live_ledger_module_never_imports_forbidden_modules():
    _assert_no_forbidden_imports(REPO_ROOT / "src" / "large_smc_research" / "live_ledger.py")
