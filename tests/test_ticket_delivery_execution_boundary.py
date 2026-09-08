"""Static safety guard: ticket_delivery must never import or reference the execution/
broker-order-submission surface. Informational delivery only -- see package docstring.
"""
from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "ticket_delivery"

FORBIDDEN_IMPORT_PREFIXES = (
    "execution",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "authorization.mt5_execution_handler",
    "authorization.telegram_gateway",  # approval/execution-callback surface -- ticket_delivery is message-only
)
FORBIDDEN_CALL_NAMES = {
    "order_send", "order_check", "create_order", "submit_order", "place_order",
    "execute_trade", "close_position", "modify_position",
}


def _python_files():
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_package_exists_and_has_files():
    assert _python_files(), f"expected Python files under {PACKAGE_ROOT}"


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
                        f"{path}: forbidden import {name!r} -- ticket_delivery must stay informational-only"
                    )


def test_no_forbidden_call_names():
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                assert name not in FORBIDDEN_CALL_NAMES, f"{path}: forbidden call {name!r}"


def test_no_approval_or_callback_or_order_send_literal():
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                for forbidden in ("order_send", "order_check", "approve_trade", "execute_demo"):
                    assert forbidden not in lowered, f"{path}: suspicious literal {node.value!r}"
