"""Proves research_external/ carries no execution/broker-order authority. Same AST
static-scan technique as test_external_candidate_governance_invariance.py.
"""
from __future__ import annotations

import ast
import os

_FORBIDDEN_MODULE_PREFIXES = ("execution",)
_FORBIDDEN_CALL_NAMES = {"order_send", "order_check", "authorize_demo_execution"}


def _iter_research_external_source_files():
    root_dir = os.path.join("research_external")
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ("runs", "datasets", "__pycache__")]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def test_no_execution_module_imports():
    for path in _iter_research_external_source_files():
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


def test_no_order_execution_calls():
    for path in _iter_research_external_source_files():
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_CALL_NAMES:
                raise AssertionError(f"{path} references forbidden call {node.attr!r}")
            if isinstance(node, ast.Name) and node.id in _FORBIDDEN_CALL_NAMES:
                raise AssertionError(f"{path} references forbidden name {node.id!r}")
