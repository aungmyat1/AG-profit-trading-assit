"""Static proof that the VirtualBroker / SVOS package has ZERO reach to MT5 order
mutation (P9 hard invariant: MT5_ORDER_SEND_REACHABLE_FROM_VIRTUAL_BROKER = false).

Uses the AST so that prose/docstrings cannot trigger false positives: it asserts that
no src/svos/ module imports src.execution / src.mt5 / MetaTrader5, and that no code
references order_send / order_check.
"""
from __future__ import annotations

import ast
from pathlib import Path

SVOS_DIR = Path(__file__).resolve().parents[1] / "src" / "svos"

FORBIDDEN_MODULES = ("execution", "mt5", "MetaTrader5")
FORBIDDEN_IDENTIFIERS = ("order_send", "order_check")


def _py_files():
    return sorted(str(p) for p in SVOS_DIR.rglob("*.py"))


def _module_imports_and_names(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    imported = set()
    names = set()
    attrs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            attrs.add(node.attr)
    return imported, names, attrs


def test_svos_package_exists_and_has_modules():
    assert SVOS_DIR.is_dir()
    assert len(_py_files()) >= 8


def test_no_execution_or_mt5_imports():
    for path in _py_files():
        imported, _, _ = _module_imports_and_names(path)
        overlap = imported & set(FORBIDDEN_MODULES)
        assert not overlap, f"{path} imports forbidden module(s) {sorted(overlap)}"


def test_no_order_mutation_identifiers():
    for path in _py_files():
        _, names, attrs = _module_imports_and_names(path)
        code_names = names | attrs
        overlap = code_names & set(FORBIDDEN_IDENTIFIERS)
        assert not overlap, f"{path} references {sorted(overlap)}"
