"""Static safety guard: multi-timeframe-market-context must never import or reference
anything from the broker-execution or risk-mutation surface. This is the automated
version of the manual banned-terminal-state scan performed in prior review passes --
codified so it runs with the rest of the suite instead of being re-derived by hand
every time.
"""
from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "mtf_context"

FORBIDDEN_IMPORT_PREFIXES = (
    "execution",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "trade_management.manager",
)
FORBIDDEN_CALL_NAMES = {
    "order_send", "order_check", "create_order", "submit_order", "place_order",
    "execute_trade", "close_position", "modify_position",
}
FORBIDDEN_TERMINAL_STATES = {"EXECUTE_TRADE", "PLACE_ORDER", "SEND_ORDER", "OPEN_POSITION"}


def _python_files():
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_package_exists_and_has_files():
    files = _python_files()
    assert files, f"expected Python files under {PACKAGE_ROOT}"


def test_no_forbidden_imports():
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                    assert not name.startswith(forbidden), (
                        f"{path}: forbidden import {name!r} -- MTF context must never reach the execution layer"
                    )


def test_no_forbidden_call_names():
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                assert name not in FORBIDDEN_CALL_NAMES, (
                    f"{path}: forbidden call {name!r} -- MTF context must never place/modify/close an order"
                )


def test_no_forbidden_terminal_state_strings_as_literal_values():
    """Distinguishes a real terminal-state assignment from prose that merely mentions
    the forbidden token in a comment/docstring (comments/docstrings are not part of the
    AST's string-literal nodes used as actual values)."""
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in FORBIDDEN_TERMINAL_STATES, (
                    f"{path}: forbidden terminal-state literal {node.value!r}"
                )


def test_authority_is_advisory_only():
    from mtf_context.models import AUTHORITY

    assert AUTHORITY == "ADVISORY_ONLY"
