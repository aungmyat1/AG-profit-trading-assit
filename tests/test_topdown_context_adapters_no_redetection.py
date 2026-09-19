"""Static no-redetection guard for src/mtf_context/topdown_context_adapters.py (TD-3).

Mirrors tests/test_mtf_context_execution_guard.py's AST-scan approach: proves the
adapter module contains transformation/mapping logic only, never a second
implementation of swing detection, BOS/CHOCH, FVG, order-block, or liquidity
detection, and never imports SSC's or Sweep-Retest's own strategy-specific structure
semantics (which must stay untouched, per the TD-3 mission's structure-semantic
boundary).
"""
from __future__ import annotations

import ast
from pathlib import Path

ADAPTER_FILE = Path(__file__).resolve().parent.parent / "src" / "mtf_context" / "topdown_context_adapters.py"

# Anything under these prefixes is either a strategy-owned structure definition (must
# stay untouched -- SSC's hand-rolled BOS, Sweep-Retest's MSS) or a low-level detection
# library the adapter must reach only through the already-processed StructureResult
# (market_structure/analyzer.py), never directly.
FORBIDDEN_IMPORT_PREFIXES = (
    "session_sweep_continuation",       # SSC's own hand-rolled BOS/swing/FVG detector
    "strategy_engine.sweep_retest",     # Sweep-Retest's own MSS concept
    "smartmoneyconcepts",               # low-level detection library -- must go through market_structure/supply_demand
    "market_structure.smc_adapter",     # DataFrame-level SMC binding -- adapter must use analyzer.py's StructureResult only
    "supply_demand.smc_adapter",
    "execution",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "trade_management.manager",
)

# The adapter must contain mapping/transformation logic only -- no independent
# swing/pivot math, no DataFrame resampling, no order placement.
FORBIDDEN_CALL_NAMES = {
    "swing_highs_lows", "bos_choch", "resample",
    "order_send", "order_check", "create_order", "submit_order", "place_order",
}


def _tree() -> ast.AST:
    return ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"), filename=str(ADAPTER_FILE))


def test_adapter_file_exists():
    assert ADAPTER_FILE.is_file()


def test_no_forbidden_imports():
    tree = _tree()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                assert not name.startswith(forbidden), (
                    f"{ADAPTER_FILE}: forbidden import {name!r} -- adapters must not "
                    "redetect or absorb strategy-owned structure semantics"
                )


def test_no_forbidden_detection_call_names():
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name not in FORBIDDEN_CALL_NAMES, (
                f"{ADAPTER_FILE}: forbidden call {name!r} -- this must remain a thin "
                "mapping layer, not a second detector"
            )


def test_only_expected_project_authorities_are_imported():
    """Positive check complementing the negative ones above: every non-stdlib,
    non-mtf_context-relative import must be one of the specific existing authorities
    this adapter is meant to reuse."""
    tree = _tree()
    allowed_modules = {
        "daily_routine.d1_context", "daily_routine.h1_setup", "daily_routine.models",
        "market_structure", "market_structure.models",
    }
    allowed_stdlib_prefixes = ("typing", "__future__", "dataclasses", "datetime")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level and node.level > 0:
                continue  # relative import within mtf_context (topdown_contracts) -- expected
            if module.startswith(allowed_stdlib_prefixes):
                continue
            assert module in allowed_modules, f"unexpected import {module!r} in {ADAPTER_FILE}"
