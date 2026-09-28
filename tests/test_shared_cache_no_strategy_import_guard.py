"""TD-6: static guard proving the shared_cache package is never imported by, and
never imports, any strategy-specific module. Mirrors the AST-scan technique already
used by tests/test_mtf_context_execution_guard.py and
tests/test_topdown_context_adapters_no_redetection.py.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_CACHE_ROOT = REPO_ROOT / "src" / "shared_cache"
SRC_ROOT = REPO_ROOT / "src"

STRATEGY_MODULE_PREFIXES = (
    "session_sweep_continuation",
    "strategy_engine.sweep_retest",
    "post_asian_pilot",
    "large_smc_research",
    "btc_sweep_research",
    "session_sweep_continuation_pilot",
)


def _imports_of(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_shared_cache_never_imports_a_strategy_module():
    for path in sorted(SHARED_CACHE_ROOT.rglob("*.py")):
        for name in _imports_of(path):
            for forbidden in STRATEGY_MODULE_PREFIXES:
                assert not name.startswith(forbidden), (
                    f"{path}: forbidden import {name!r} -- shared_cache must never "
                    "depend on strategy-specific logic"
                )


def test_no_strategy_module_imports_shared_cache():
    """Integration boundary check: TD-6 must not be imported into SSC/Sweep-Retest/
    AS5R/Large-SMC strategy logic (mission's explicit instruction) -- strategies may
    only benefit indirectly through the shared authorities they already call."""
    strategy_dirs = [
        SRC_ROOT / "session_sweep_continuation",
        SRC_ROOT / "strategy_engine" / "sweep_retest",
        SRC_ROOT / "post_asian_pilot",
        SRC_ROOT / "large_smc_research",
    ]
    for directory in strategy_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            for name in _imports_of(path):
                assert not name.startswith("shared_cache"), (
                    f"{path}: strategy module must not import shared_cache directly"
                )


def test_shared_cache_package_exists_and_has_files():
    files = sorted(SHARED_CACHE_ROOT.rglob("*.py"))
    assert files, f"expected Python files under {SHARED_CACHE_ROOT}"
