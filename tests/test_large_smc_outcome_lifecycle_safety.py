"""OUTCOME_LIFECYCLE_V1 safety checks (task section 25 'Safety' category): confirms
this phase added no path toward execution authority, and that outcome records are
structurally immutable once produced."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from large_smc_research.pending_entry import PendingEntryOutcome

_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "large_smc_research"
_FORBIDDEN_MODULE_PREFIXES = ("execution", "assistant.commands", "mt5.mt5",  # order_send/order_check live in execution/mt5 gateways
                              "assistant.runtime")


def _imported_modules(py_file: Path):
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_no_execution_or_assistant_command_imports_anywhere_in_the_package():
    for py_file in _PACKAGE_DIR.glob("*.py"):
        for module in _imported_modules(py_file):
            assert not any(module.startswith(p) for p in _FORBIDDEN_MODULE_PREFIXES), (
                f"{py_file.name} imports {module!r} -- execution/assistant-command authority "
                "must never enter src/large_smc_research/"
            )


def test_no_order_send_or_order_check_reference_anywhere_in_the_package():
    for py_file in _PACKAGE_DIR.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "order_send" not in text
        assert "order_check" not in text


def test_pending_entry_outcome_is_frozen_and_immutable():
    outcome = PendingEntryOutcome(
        candidate_occurrence_id="OCCURRENCE-x", setup_family_id="SETUP-x",
        eligibility_interval_id="INTERVAL-x", combination="E1M2", direction="LONG",
        ready_time=None, status="FILLED",
    )
    with pytest.raises((AttributeError, TypeError)):
        outcome.status = "INVALIDATED_BEFORE_FILL"  # type: ignore[misc]
