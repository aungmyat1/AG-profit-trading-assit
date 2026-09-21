"""Static safety guard: scripts/run_fx_session_daytrade.py must have no import path or
call/literal reference to broker order submission. Mirrors
tests/test_proposal_envelope_execution_boundary.py's AST-based convention.

This wrapper is a thin CLI dispatcher over src/post_asian_pilot/* (the same package
scripts/run_post_asian_pilot.py already delegates to, already proven order-send-free by
that script's own docstring contract and by this repo's existing execution-boundary
tests) -- it forks no execution/order logic of its own, so it must show zero references
to the real order-mutating surfaces.
"""
from __future__ import annotations

import ast
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_fx_session_daytrade.py"

FORBIDDEN_ORDER_MUTATION_IMPORT_PREFIXES = (
    "execution.executor",
    "execution.coordinator",
    "execution.mt5_gateway",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "authorization.mt5_execution_handler",
    "authorization.telegram_gateway",
)
FORBIDDEN_CALL_NAMES = {
    "order_send", "order_check", "create_order", "submit_order", "place_order",
    "execute_trade", "close_position", "modify_position", "execute",
}


def _tree():
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"), filename=str(SCRIPT_PATH))


def _imports():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_wrapper_script_exists():
    assert SCRIPT_PATH.is_file(), f"expected wrapper at {SCRIPT_PATH}"


def test_wrapper_has_no_order_mutation_imports():
    for name in _imports():
        for forbidden in FORBIDDEN_ORDER_MUTATION_IMPORT_PREFIXES:
            assert not name.startswith(forbidden), (
                f"{SCRIPT_PATH}: forbidden import {name!r} -- the FX session daytrade "
                "wrapper must stay structurally isolated from broker order submission"
            )


def test_wrapper_imports_only_expected_modules():
    """Belt-and-braces: the wrapper's own import set must stay confined to the same
    proposal-only surface scripts/run_post_asian_pilot.py already uses -- no accidental
    new dependency on an execution/broker module."""
    allowed_prefixes = (
        "__future__", "argparse", "json", "sys", "pathlib",
        "mt5.connection", "post_asian_pilot.",
    )
    for name in _imports():
        assert any(name == p or name.startswith(p) for p in allowed_prefixes), (
            f"{SCRIPT_PATH}: unexpected import {name!r} outside the proposal-only surface"
        )


def test_wrapper_has_no_forbidden_call_names():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name not in FORBIDDEN_CALL_NAMES, f"{SCRIPT_PATH}: forbidden call {name!r}"


def test_wrapper_has_no_order_send_literal():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            for forbidden in ("order_send", "order_check", "approve_trade", "execute_demo"):
                assert forbidden not in lowered, f"{SCRIPT_PATH}: suspicious literal {node.value!r}"
