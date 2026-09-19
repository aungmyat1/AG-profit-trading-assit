"""Static no-redetection guard for src/mtf_context/topdown_new_builders.py (TD-4).

Mirrors tests/test_topdown_context_adapters_no_redetection.py's AST-scan approach for
TD-3's adapter file. Proves the W1/H4/M15 builder module contains transformation/
mapping logic only, never a second implementation of swing detection, BOS/CHOCH, FVG,
order-block, or liquidity detection, and never imports SSC's, Sweep-Retest's, or any
other strategy-specific structure/setup semantics.
"""
from __future__ import annotations

import ast
from pathlib import Path

BUILDER_FILE = Path(__file__).resolve().parent.parent / "src" / "mtf_context" / "topdown_new_builders.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "session_sweep_continuation",       # SSC's own hand-rolled BOS/swing/FVG/regime/campaign
    "strategy_engine.sweep_retest",     # Sweep-Retest's own MSS concept
    "post_asian_pilot",                 # Asian-Sweep-5R setup qualification
    "large_smc_research",               # Large-SMC's own decision/qualification logic
    "smartmoneyconcepts",               # low-level detection library -- must go through market_structure/supply_demand
    "market_structure.smc_adapter",     # DataFrame-level SMC binding -- must use analyzer.py's StructureResult only
    "supply_demand.smc_adapter",
    "execution",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "trade_management.manager",
)

FORBIDDEN_CALL_NAMES = {
    "swing_highs_lows", "bos_choch", "resample",
    "order_send", "order_check", "create_order", "submit_order", "place_order",
}

# Strategy-specific labels that must never appear as literal string values anywhere in
# this module (a real assignment/comparison, not prose -- AST string-constant nodes
# exclude comments/docstrings used only as documentation text within triple-quoted
# strings... actually docstrings ARE Constant string nodes too, so this scan
# necessarily also covers documentation mentions; the module docstring deliberately
# avoids using these as bare tokens for exactly this reason -- see its own wording).
FORBIDDEN_LITERAL_LABELS = {"S1", "S2", "S3", "MSS"}


def _tree() -> ast.AST:
    return ast.parse(BUILDER_FILE.read_text(encoding="utf-8"), filename=str(BUILDER_FILE))


def test_builder_file_exists():
    assert BUILDER_FILE.is_file()


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
                    f"{BUILDER_FILE}: forbidden import {name!r} -- TD-4 builders must not "
                    "redetect or absorb strategy-owned structure/setup semantics"
                )


def test_no_forbidden_detection_call_names():
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name not in FORBIDDEN_CALL_NAMES, (
                f"{BUILDER_FILE}: forbidden call {name!r} -- this must remain a thin "
                "mapping layer, not a second detector"
            )


def test_only_expected_project_authorities_are_imported():
    tree = _tree()
    allowed_modules = {
        "liquidity", "liquidity.models", "market_structure", "market_structure.models", "supply_demand",
    }
    allowed_stdlib_prefixes = ("typing", "__future__")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level and node.level > 0:
                continue  # relative import within mtf_context (topdown_contracts, topdown_context_adapters) -- expected
            if module.startswith(allowed_stdlib_prefixes):
                continue
            assert module in allowed_modules, f"unexpected import {module!r} in {BUILDER_FILE}"


def test_no_strategy_specific_literal_labels():
    """The only structure_definition_id this module can ever write is the SMC one
    (StructureFact's own __post_init__ enforces the whitelist) -- this additionally
    proves no SSC/Sweep-Retest-specific label ever appears as a literal string
    constant anywhere in the module's source."""
    tree = _tree()
    literal_strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not (literal_strings & FORBIDDEN_LITERAL_LABELS)
