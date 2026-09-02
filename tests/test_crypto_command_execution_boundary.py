"""Crypto analogue of tests/test_btc_proposal_execution_boundary.py: proves
CryptoTradeCommand and every new execution/crypto_*.py module (1) cannot reach a real
send path in this phase, and (2) is architecturally distinct from execution.models.
TradeCommand -- it does not pass execution.executor.execute()'s isinstance gate either,
same as BTCSweepResearchProposal did not.

Also the AST-based static proof required by the spec's verification section: none of the
new crypto_*.py modules import execution.executor, mt5.management_gateway,
execution.coordinator, or a real network library (requests/httpx/urllib/socket) outside a
test double, and none reference os.environ/getenv/.env (secret access).
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

import execution.executor as executor_module
from execution.executor import UnsupportedExecutionDomain
from execution.crypto_models import ACCOUNT_ENVIRONMENT_DEMO, CryptoTradeCommand
from execution.models import TradeCommand

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
CRYPTO_MODULE_NAMES = [
    "crypto_models.py", "crypto_router.py", "crypto_metadata.py", "crypto_filter_refresh.py",
    "crypto_clock.py", "crypto_journal.py", "crypto_client_order_id.py",
    "crypto_reconciliation.py", "crypto_snapshot.py",
]


def _crypto_module_paths():
    return [SRC_ROOT / "execution" / name for name in CRYPTO_MODULE_NAMES]


def _make_command() -> CryptoTradeCommand:
    return CryptoTradeCommand(
        command_id="cmd-boundary", occurrence_id="occ-boundary", account_environment=ACCOUNT_ENVIRONMENT_DEMO,
        symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01,
        client_order_id="AGX-boundary", created_at=datetime.now(timezone.utc),
    )


# --- Type distinctness -------------------------------------------------------------------

def test_crypto_trade_command_is_not_a_trade_command_subclass():
    assert not issubclass(CryptoTradeCommand, TradeCommand)
    assert not issubclass(TradeCommand, CryptoTradeCommand)


def test_crypto_trade_command_instance_is_not_a_trade_command_instance():
    assert not isinstance(_make_command(), TradeCommand)


# --- Behavioral: executor rejects it, same as the BTC research proposal ------------------

def test_calling_executor_execute_with_crypto_command_raises_unsupported_domain():
    command = _make_command()
    with pytest.raises(UnsupportedExecutionDomain):
        executor_module.execute(command, user_confirmed=False)
    with pytest.raises(UnsupportedExecutionDomain):
        executor_module.execute(command, user_confirmed=True)


def test_executor_module_has_no_function_accepting_crypto_trade_command():
    assert not hasattr(executor_module, CryptoTradeCommand.__name__)
    for name, member in inspect.getmembers(executor_module, inspect.isfunction):
        try:
            sig = inspect.signature(member)
        except (TypeError, ValueError):
            continue
        for param in sig.parameters.values():
            assert param.annotation is not CryptoTradeCommand, (
                f"execution.executor.{name} must never accept a CryptoTradeCommand"
            )


# --- Static: no forbidden imports in any new crypto_*.py module --------------------------

_FORBIDDEN_ORDER_PATH_MODULES = {
    "execution.executor", "mt5.management_gateway", "execution.coordinator",
}
_FORBIDDEN_NETWORK_MODULES = {"requests", "httpx", "urllib", "urllib.request", "http.client", "socket"}


@pytest.mark.parametrize("path", _crypto_module_paths(), ids=lambda p: p.name)
def test_crypto_module_never_imports_forbidden_order_path(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in _FORBIDDEN_ORDER_PATH_MODULES, (
                    f"{path.name} imports forbidden order-path module {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in _FORBIDDEN_ORDER_PATH_MODULES, (
                f"{path.name} imports forbidden order-path module {module}"
            )


@pytest.mark.parametrize("path", _crypto_module_paths(), ids=lambda p: p.name)
def test_crypto_module_never_imports_a_network_library(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in _FORBIDDEN_NETWORK_MODULES, (
                    f"{path.name} imports forbidden network module {alias.name} -- "
                    "NETWORK_ACCESS is FORBIDDEN in this phase"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in _FORBIDDEN_NETWORK_MODULES, (
                f"{path.name} imports forbidden network module {module}"
            )


@pytest.mark.parametrize("path", _crypto_module_paths(), ids=lambda p: p.name)
def test_crypto_module_never_touches_environment_or_secrets(path: Path):
    """SECRET_ACCESS = FORBIDDEN: no os.environ, no getenv, no literal '.env' reference."""
    source = path.read_text(encoding="utf-8")
    assert "os.environ" not in source, f"{path.name} references os.environ"
    assert "getenv" not in source, f"{path.name} references getenv"
    assert ".env" not in source, f"{path.name} references .env"


def test_crypto_execution_adapter_still_returns_not_implemented():
    """Belt-and-suspenders: the existing shared CryptoExecutionAdapter (execution/adapter.py)
    that a future submit path would use is untouched by this phase and still refuses to
    do anything -- reused, not duplicated, by execution.crypto_filter_refresh.submit_step."""
    from execution.adapter import CryptoExecutionAdapter
    from execution.crypto_filter_refresh import submit_step

    adapter_result = CryptoExecutionAdapter().submit(proposal=None, user_confirmed=True)  # type: ignore[arg-type]
    assert adapter_result.status == "NOT_IMPLEMENTED"
    sequence_result = submit_step(True)
    assert sequence_result.status == "NOT_IMPLEMENTED"
