from __future__ import annotations

import ast
import importlib
from pathlib import Path


def _python_files():
    root = Path(__file__).resolve().parents[1]
    return sorted(
        p
        for p in root.rglob("*.py")
        if ".git" not in p.parts and "__pycache__" not in p.parts
    )


def test_canonical_contracts_module_is_importable():
    module = importlib.import_module("contracts.v1")
    assert hasattr(module, "MarketState")
    assert hasattr(module, "SCHEMA_VERSION")


def test_legacy_packages_contract_imports_are_not_used():
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "packages.contracts.v1"
            ):
                raise AssertionError(f"legacy import path remains in {path}")
            if isinstance(node, ast.Import) and any(
                alias.name == "packages.contracts.v1" for alias in node.names
            ):
                raise AssertionError(f"legacy import path remains in {path}")
