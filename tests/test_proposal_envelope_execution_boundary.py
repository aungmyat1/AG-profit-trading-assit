"""Static + behavioral safety guard for proposal_envelope's structural isolation from
broker order submission ("Bounded next action" item 3's own exit criterion, and the hard
constraint: "Step 3's new canonical proposal envelope module must have ZERO execution
imports").

Two scopes, deliberately different:

  CORE (proposal_envelope/models.py + __init__.py) -- the actual Workstream 0 envelope
  contract. This is "the module" the hard constraint names: literally zero references to
  `execution` anywhere, proven both statically (AST) and behaviorally (fresh-subprocess
  sys.modules check).

  WHOLE PACKAGE (core + adapters/) -- adapters (Step 4) are explicitly required by the
  source plan to read execution.adapter.TradeProposal (the FX post_asian_pilot output
  type this repo already names that way -- see authorization/proposal_source.py) for
  lossless mapping, so a blanket "no execution import at all" rule is not applicable to
  adapters. What DOES still apply everywhere, including adapters: no import of the actual
  order-mutating surfaces (execution.executor, execution.coordinator,
  mt5.management_gateway, mt5.mt5_gateway, authorization.mt5_execution_handler,
  authorization.telegram_gateway), and no order_send/order_check-shaped call or literal
  anywhere. execution.adapter.TradeProposal itself is a plain, frozen dataclass with no
  mt5_gateway/executor import in its own chain (verified separately below).

Mirrors tests/test_ticket_delivery_execution_boundary.py's convention.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "proposal_envelope"
CORE_FILES = (PACKAGE_ROOT / "models.py", PACKAGE_ROOT / "__init__.py")

# Applies package-wide (core AND adapters): the actual order-mutating surfaces. Note this
# deliberately does NOT include bare "execution" -- adapters/fx_adapter.py legitimately
# imports execution.adapter.TradeProposal, a plain data type, per Step 4's own instruction.
FORBIDDEN_ORDER_MUTATION_IMPORT_PREFIXES = (
    "execution.executor",
    "execution.coordinator",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "authorization.mt5_execution_handler",
    "authorization.telegram_gateway",
    "notifications.trade_ticket_formatter",
)
FORBIDDEN_CALL_NAMES = {
    "order_send", "order_check", "create_order", "submit_order", "place_order",
    "execute_trade", "close_position", "modify_position",
}


def _python_files():
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _imports_of(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_package_exists_and_has_files():
    assert _python_files(), f"expected Python files under {PACKAGE_ROOT}"


def test_core_envelope_has_zero_execution_imports():
    """The exact hard constraint: proposal_envelope/models.py (+ __init__.py) must never
    import `execution` at all -- not even the data-only execution.adapter.TradeProposal
    type. That reference belongs only in adapters/fx_adapter.py (Step 4)."""
    for path in CORE_FILES:
        for name in _imports_of(path):
            assert name != "execution" and not name.startswith("execution."), (
                f"{path}: forbidden execution import {name!r} -- the CORE envelope module "
                "must have ZERO execution imports"
            )


def test_whole_package_has_no_order_mutation_imports():
    for path in _python_files():
        for name in _imports_of(path):
            for forbidden in FORBIDDEN_ORDER_MUTATION_IMPORT_PREFIXES:
                assert not name.startswith(forbidden), (
                    f"{path}: forbidden import {name!r} -- proposal_envelope must stay "
                    "structurally isolated from broker order submission"
                )


def test_no_forbidden_call_names():
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                assert name not in FORBIDDEN_CALL_NAMES, f"{path}: forbidden call {name!r}"


def test_no_order_send_literal():
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                for forbidden in ("order_send", "order_check", "approve_trade", "execute_demo"):
                    assert forbidden not in lowered, f"{path}: suspicious literal {node.value!r}"


def _env_without_pythonpath():
    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


def test_behavioral_core_import_alone_never_pulls_in_execution():
    """Behavioral companion to test_core_envelope_has_zero_execution_imports: in a FRESH
    subprocess interpreter, import ONLY proposal_envelope.models (the core envelope, not
    the adapters) and confirm no `execution` module ever lands in sys.modules -- catches
    dynamic/importlib-based imports the AST scan cannot see."""
    src_dir = str(PACKAGE_ROOT.parent)
    script = (
        "import sys, importlib\n"
        "importlib.import_module('proposal_envelope.models')\n"
        "forbidden = [m for m in sys.modules if m == 'execution' or m.startswith('execution.')]\n"
        "print('FORBIDDEN=' + repr(forbidden))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=str(PACKAGE_ROOT.parent.parent),
        env={"PYTHONPATH": src_dir, **_env_without_pythonpath()},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"subprocess import failed: {result.stderr}"
    forbidden_line = next(line for line in result.stdout.splitlines() if line.startswith("FORBIDDEN="))
    assert forbidden_line == "FORBIDDEN=[]", (
        f"proposal_envelope.models import pulled in execution modules: {forbidden_line}"
    )


def test_behavioral_whole_package_never_reaches_order_mutation_surface():
    """Behavioral companion to test_whole_package_has_no_order_mutation_imports: in a
    FRESH subprocess interpreter, import every module in the package (core + adapters)
    and confirm none of the actual order-mutating surfaces ever lands in sys.modules --
    execution.adapter (a plain data type) is expected and allowed; execution.executor /
    execution.coordinator / mt5.management_gateway / mt5.mt5_gateway are not."""
    src_dir = str(PACKAGE_ROOT.parent)
    script = (
        "import sys, importlib, pkgutil\n"
        "package = importlib.import_module('proposal_envelope')\n"
        "for _finder, name, _ispkg in pkgutil.walk_packages(package.__path__, prefix='proposal_envelope.'):\n"
        "    importlib.import_module(name)\n"
        "forbidden = [m for m in sys.modules if m in (\n"
        "    'execution.executor', 'execution.coordinator', 'mt5.management_gateway', 'mt5.mt5_gateway',\n"
        "    'authorization.mt5_execution_handler', 'authorization.telegram_gateway',\n"
        "    'notifications.trade_ticket_formatter')]\n"
        "print('FORBIDDEN=' + repr(forbidden))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=str(PACKAGE_ROOT.parent.parent),
        env={"PYTHONPATH": src_dir, **_env_without_pythonpath()},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"subprocess import failed: {result.stderr}"
    forbidden_line = next(line for line in result.stdout.splitlines() if line.startswith("FORBIDDEN="))
    assert forbidden_line == "FORBIDDEN=[]", (
        f"proposal_envelope package import reached an order-mutation surface: {forbidden_line}"
    )
