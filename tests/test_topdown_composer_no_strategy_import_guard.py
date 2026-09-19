"""TD-7/TD-8: static guard proving src/mtf_context/topdown_composer.py never imports
any strategy-decision, proposal, risk, or execution module. Mirrors the AST-scan
technique already used by tests/test_shared_cache_no_strategy_import_guard.py and
tests/test_topdown_context_adapters_no_redetection.py. This is IN ADDITION to (not a
replacement for) tests/test_mtf_context_execution_guard.py, which already AST-scans
every *.py under src/mtf_context (including this new module) for a different, narrower
forbidden list (execution/, mt5.management_gateway, trade_management.manager, and
forbidden call names/terminal-state literals) -- this file covers the wider
strategy/proposal/risk surface the TD-7 mission names explicitly.

TD-8 UPDATE: `historical_replay` is now a deliberate, additive import (replay
substitution infrastructure for HISTORICAL_AS_OF composition) -- explicitly allowed
below, not forbidden, and not a strategy/proposal/risk/execution module itself (see
test_historical_replay_module_is_not_itself_forbidden)."""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSER_PATH = REPO_ROOT / "src" / "mtf_context" / "topdown_composer.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "session_sweep_continuation",
    "session_sweep_continuation_pilot",
    "strategy_engine.sweep_retest",
    "post_asian_pilot",
    "large_smc_research",
    "btc_sweep_research",
    "proposals",
    "proposal_envelope",
    "risk",
    "execution",
    "execution_runtime",
    "trade_management",
    "strategy_manager",
)


def _imports_of(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_topdown_composer_exists():
    assert COMPOSER_PATH.is_file()


def test_topdown_composer_never_imports_a_strategy_proposal_risk_or_execution_module():
    for name in _imports_of(COMPOSER_PATH):
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            assert not name.startswith(forbidden), (
                f"{COMPOSER_PATH}: forbidden import {name!r} -- TD-7 is infrastructure "
                "only and must never reach strategy/proposal/risk/execution logic"
            )


def test_topdown_composer_only_imports_from_within_its_own_package_and_stdlib():
    """A slightly stronger, positive assertion: every non-stdlib import this module
    makes is either from within mtf_context itself (the existing tier builders/
    contracts it composes) or a name it doesn't need to reach outside this package at
    all -- TD-7 must depend only on the existing context-producer interfaces, never on
    MT5 or any other external surface directly (see module docstring's TD-6 CACHE
    BOUNDARY / replay-boundary discussion)."""
    allowed_external_prefixes = ("__future__", "hashlib", "datetime", "typing", ".")
    for name in _imports_of(COMPOSER_PATH):
        is_relative_or_allowed = name.startswith(allowed_external_prefixes)
        is_within_package = name.startswith("mtf_context") or name.startswith("topdown_")
        # TD-8: historical_replay is the one deliberate additive cross-package
        # dependency -- the existing, already-tested replay-substitution mechanism
        # (HistoricalCandleStore, historical_data_context, ReplayDatasetIdentity),
        # reused verbatim for HISTORICAL_AS_OF composition, not a strategy module.
        is_historical_replay = name.startswith("historical_replay")
        assert is_relative_or_allowed or is_within_package or is_historical_replay, (
            f"{COMPOSER_PATH}: unexpected external import {name!r} -- composer should "
            "depend only on existing mtf_context context-producer interfaces plus the "
            "historical_replay substitution mechanism for HISTORICAL_AS_OF"
        )


def test_topdown_composer_never_imports_mt5_directly():
    for name in _imports_of(COMPOSER_PATH):
        assert not name.startswith("mt5") and name != "MetaTrader5", (
            f"{COMPOSER_PATH}: composer must depend on existing context-producer "
            "interfaces, never on MT5 directly"
        )


def test_historical_replay_module_is_not_itself_forbidden():
    """historical_replay is deliberately NOT in FORBIDDEN_IMPORT_PREFIXES -- assert
    that explicitly so a future edit accidentally adding it there fails loudly and
    obviously, rather than silently breaking HISTORICAL_AS_OF composition."""
    assert not any("historical_replay".startswith(p) or p.startswith("historical_replay")
                   for p in FORBIDDEN_IMPORT_PREFIXES)
