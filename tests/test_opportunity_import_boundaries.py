"""Static import-boundary proof for src/opportunity/ (P20/P21).

Proves the prohibited dependency edges: the opportunity package (strategy-neutral
funnel/candidate infrastructure) must never import execution/broker/order-send
code, and must not import strategy engines directly (it only knows about
strategies via the registry-driven StrategyBinding).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

OPPORTUNITY_DIR = Path(__file__).resolve().parents[1] / "src" / "opportunity"

FORBIDDEN_MODULE_PREFIXES = (
    "execution",
    "mt5.executor",
    "mt5.mt5_gateway",
)


def _opportunity_source_files():
    return sorted(p for p in OPPORTUNITY_DIR.glob("*.py") if p.name != "__pycache__")


def _imported_module_names(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


@pytest.mark.parametrize("path", _opportunity_source_files(), ids=lambda p: p.name)
def test_opportunity_module_never_imports_execution_or_broker_code(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = list(_imported_module_names(tree))
    for name in imported:
        for forbidden in FORBIDDEN_MODULE_PREFIXES:
            assert not name.startswith(forbidden), (
                f"{path.name} imports {name!r}, which crosses the forbidden "
                f"opportunity-engine -> broker/order_send boundary"
            )


@pytest.mark.parametrize("path", _opportunity_source_files(), ids=lambda p: p.name)
def test_opportunity_module_never_calls_order_send(path: Path):
    """Checks actual code (Call/Attribute nodes), not prose in docstrings/comments
    that merely discuss the forbidden boundary."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        assert name != "order_send", f"{path.name} references order_send in executable code"
