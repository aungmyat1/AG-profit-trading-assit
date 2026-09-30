"""AG V1 owner decision 1: the sizing/guard boundary used by frozen engines is broker-free.

src/sizing_math holds byte-exact copies of src/execution/{risk,daily_loss_guard,
position_guard}.py @ 2b75bbf. This test pins three things:
- none of its modules import broker, order, network or forbidden packages, directly or
  through their own imports;
- none of them call an MT5 order or position function;
- the frozen crypto engine reaches sizing only through this boundary.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOUNDARY = ROOT / "src" / "sizing_math"
FORBIDDEN_PREFIXES = (
    "execution", "trade_management", "authorization", "owner_decision", "svos", "ticket_delivery",
    "MetaTrader5", "requests", "httpx", "urllib", "socket", "http", "aiohttp", "telegram", "notifications",
    "mt5.market_data", "mt5.management_gateway", "mt5.connection", "api",
)
FORBIDDEN_CALLS = {"order_send", "order_check", "positions_get", "position_close", "initialize", "login"}
ALLOWED_IMPORTS = {"mt5.symbol_resolver", "runtime_state.store"}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_boundary_modules_have_no_broker_order_or_network_imports():
    for path in sorted(BOUNDARY.glob("*.py")):
        for name in _imports(path):
            if name in ALLOWED_IMPORTS:
                continue
            assert not name.startswith(FORBIDDEN_PREFIXES), f"{path.name} imports {name}"


def test_boundary_modules_never_call_order_or_position_functions():
    for path in sorted(BOUNDARY.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in FORBIDDEN_CALLS, f"{path.name} calls {name}"


def test_boundary_is_byte_exact_with_pre_wipe_execution_modules():
    for name in ("risk", "daily_loss_guard", "position_guard"):
        try:
            original = subprocess.run(
                ["git", "show", f"2b75bbf:src/execution/{name}.py"], cwd=ROOT,
                capture_output=True, check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            import pytest
            pytest.skip("git history for 2b75bbf not available in this checkout")
        assert (BOUNDARY / f"{name}.py").read_bytes() == original, name


def test_importing_the_frozen_crypto_engine_loads_no_forbidden_package():
    code = (
        "import sys; sys.path[:0]=['.','src'];"
        "import strategy_engine.sweep_retest.engine, btc_sweep_research.pipeline;"
        "bad=[m for m in sys.modules if m.split('.')[0] in "
        "('execution','trade_management','authorization','owner_decision','svos','telegram')"
        " or m in ('mt5.management_gateway',)];"
        "print('FORBIDDEN=' + ','.join(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    marker = [ln for ln in out.stdout.splitlines() if ln.startswith("FORBIDDEN=")]
    assert marker == ["FORBIDDEN="], out.stdout


def test_frozen_crypto_engine_sizing_goes_through_the_boundary_only():
    src = (ROOT / "src/strategy_engine/sweep_retest/engine.py").read_text(encoding="utf-8")
    assert "from sizing_math.risk import size_position" in src
    assert "from execution." not in src
