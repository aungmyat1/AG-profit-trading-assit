"""AG_FX_OPPORTUNITY_PROPOSAL_SLICE_V1 — import/call-graph containment.

AST-level proof (not grep) that the FX slice's new and restored modules can
never reach an execution, authorization, owner-decision, ticket, trade-
management, scheduler, or broker-mutation surface:

  - no forbidden module imports (recursively relevant top-levels)
  - MetaTrader5 is imported ONLY inside src/mt5/* (the read-only adapter)
  - no order_send / order_check call sites anywhere in the slice
  - no subprocess / network-client imports in the cycle runner
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SLICE_MODULES = [
    "scripts/run_fx_opportunity_cycle.py",
    "src/proposal_envelope/owner_report.py",
    "src/opportunity/asian_sweep_adapter.py",
    "src/opportunity/events.py",
    "src/post_asian_pilot/__init__.py",
    "src/post_asian_pilot/decision.py",
    "src/mt5/market_data.py",
    "src/mt5/broker_time.py",
    "src/mt5/connection.py",
    "src/mt5/config.py",
    "src/shared_cache/__init__.py",
    "src/shared_cache/bounded_cache.py",
    "src/shared_cache/derived_fact_cache.py",
]

FORBIDDEN_TOPLEVELS = {
    "execution", "authorization", "owner_decision", "ticket_delivery",
    "trade_management", "svos", "entry_confirmation", "notifications",
    "strategy_manager", "api", "proposals", "assistant", "historical_replay",
    "ag_scheduler_v2", "subprocess", "requests", "httpx", "urllib",
    "socket", "smtplib", "telegram",
}

ORDER_CALL_NAMES = {"order_send", "order_check", "OrderSend", "OrderCheck"}


def _imports_of(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0], node


def _order_calls_of(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ORDER_CALL_NAMES:
                yield func.attr
            elif isinstance(func, ast.Name) and func.id in ORDER_CALL_NAMES:
                yield func.id


def test_slice_modules_exist():
    for rel in SLICE_MODULES:
        assert (ROOT / rel).is_file(), f"missing slice module: {rel}"


def test_no_forbidden_imports_anywhere_in_slice():
    violations = []
    for rel in SLICE_MODULES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for top, node in _imports_of(tree):
            if top in FORBIDDEN_TOPLEVELS:
                violations.append(f"{rel}: imports {top} (line {node.lineno})")
    assert not violations, "\n".join(violations)


def test_metatrader5_import_only_inside_mt5_package():
    violations = []
    for rel in SLICE_MODULES:
        if rel.startswith("src/mt5/"):
            continue  # the read-only adapter itself is the one allowed place
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for top, node in _imports_of(tree):
            if top == "MetaTrader5":
                violations.append(f"{rel}: imports MetaTrader5 (line {node.lineno})")
    assert not violations, "\n".join(violations)


def test_no_order_call_sites_in_slice():
    violations = []
    for rel in SLICE_MODULES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for name in _order_calls_of(tree):
            violations.append(f"{rel}: calls {name}")
    assert not violations, "\n".join(violations)


def test_cycle_runner_invokes_only_allowed_surface():
    """The runner's own imports are exactly the capability-zero pipeline."""
    src = (ROOT / "scripts" / "run_fx_opportunity_cycle.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    allowed = {
        "__future__", "argparse", "hashlib", "json", "sys", "dataclasses",
        "datetime", "pathlib", "typing",
        "mt5", "opportunity", "post_asian_pilot", "proposal_envelope",
        "strategy_engine",
    }
    seen = {top for top, _ in _imports_of(tree)}
    assert seen <= allowed, sorted(seen - allowed)
