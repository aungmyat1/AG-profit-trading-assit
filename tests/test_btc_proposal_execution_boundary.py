"""Enforces the hard constraint that BTCSweepResearchProposal (spec section 24's
execution_domain=CRYPTO_RESEARCH / execution_authority=DISABLED contract) can never reach
a real order-placement path, and that btc_sweep_research's own runtime never imports one.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import execution.executor as executor_module
import mt5.management_gateway as gateway_module
from btc_sweep_research.proposal import (
    EXECUTION_AUTHORITY_DISABLED,
    EXECUTION_DOMAIN_CRYPTO_RESEARCH,
    BTCSweepResearchProposal,
)

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


def _proposal_type_name():
    return BTCSweepResearchProposal.__name__


def test_proposal_declares_disabled_execution_domain():
    import dataclasses
    fields = {f.name: f.default for f in dataclasses.fields(BTCSweepResearchProposal)}
    assert fields["execution_domain"] == EXECUTION_DOMAIN_CRYPTO_RESEARCH
    assert fields["execution_authority"] == EXECUTION_AUTHORITY_DISABLED


def test_executor_module_has_no_function_accepting_btc_proposal():
    """execution.executor's public functions are all typed around TradeCommand/
    ExecutionReport (MT5-shaped) -- assert none of its callables mention
    BTCSweepResearchProposal in a type annotation, and (belt-and-suspenders) that the type
    is not importable from that module's namespace."""
    assert not hasattr(executor_module, _proposal_type_name())
    for name, member in inspect.getmembers(executor_module, inspect.isfunction):
        try:
            sig = inspect.signature(member)
        except (TypeError, ValueError):
            continue
        for param in sig.parameters.values():
            assert param.annotation is not BTCSweepResearchProposal, (
                f"execution.executor.{name} must never accept a BTCSweepResearchProposal"
            )


def test_management_gateway_has_no_function_accepting_btc_proposal():
    assert not hasattr(gateway_module, _proposal_type_name())
    for name, member in inspect.getmembers(gateway_module, inspect.isfunction):
        try:
            sig = inspect.signature(member)
        except (TypeError, ValueError):
            continue
        for param in sig.parameters.values():
            assert param.annotation is not BTCSweepResearchProposal, (
                f"mt5.management_gateway.{name} must never accept a BTCSweepResearchProposal"
            )


def test_calling_executor_execute_with_btc_proposal_raises_type_mismatch():
    """execute() expects a TradeCommand (execution.models.TradeCommand) with specific
    attributes (command_id, symbol, direction, ...) that BTCSweepResearchProposal simply
    does not have -- attempting to route a BTC research proposal through it fails fast
    with an AttributeError rather than silently doing something order-shaped."""
    from btc_sweep_research.pipeline import DEFAULT_RESEARCH_EQUITY_USDT  # noqa: F401 -- sanity import stays in-package

    fake_proposal = BTCSweepResearchProposal(
        strategy="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="2.0.0", authority="RESEARCH_ONLY",
        exchange="BINANCE_USDT_M_PERP", instrument="BTCUSDT", direction="SHORT",
        reference_day=None, reference_high=42000.0, reference_low=40700.0,
        sweep={}, confirmation={}, entry=41620.0, stop=42151.0, target={"tp1": 41350.0, "tp2": 40700.0},
        RR=1.6, estimated_fees=1.0, funding_assumption={}, data_timestamp=None, expiry=None,
        occurrence_id="BTC-OCC-test",
    )
    with pytest.raises(AttributeError):
        executor_module.execute(fake_proposal, user_confirmed=False)


def _package_files():
    pkg_dir = SRC_ROOT / "btc_sweep_research"
    return list(pkg_dir.glob("*.py"))


@pytest.mark.parametrize("path", _package_files(), ids=lambda p: p.name)
def test_btc_sweep_research_package_never_imports_execution_order_paths(path: Path):
    """Static check: no module inside src/btc_sweep_research/ may import
    execution.executor, mt5.management_gateway, execution.coordinator, or
    execution.adapter (spec hard constraint: the BTC research runner must never import
    an order_send path)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_prefixes = ("execution.executor", "mt5.management_gateway", "execution.coordinator", "execution.adapter")
    forbidden_modules = {"execution.executor", "mt5.management_gateway", "execution.coordinator", "execution.adapter"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, f"{path.name} imports forbidden module {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden_modules, f"{path.name} imports forbidden module {module}"
            assert not any(module.startswith(p) for p in forbidden_prefixes), (
                f"{path.name} imports forbidden module path {module}"
            )


def test_run_btc_sweep_research_script_never_imports_forbidden_modules():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "run_btc_sweep_research.py"
    tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
    forbidden_modules = {"execution.executor", "mt5.management_gateway", "execution.coordinator", "execution.adapter"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "") not in forbidden_modules
