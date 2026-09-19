"""RAW_PROSPECTIVE_ARCHIVE_V1 safety proofs -- mission P9 items 1-6, 10, 11.

Static (AST-based) proofs that the archive module and the two existing
read-only MT5 wrappers it reuses can never reach an order-mutating MT5 call,
never import the order-mutating gateways, and never import or write the
proposal ledger / SSC replay / validation-population machinery.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

ARCHIVE_MODULE_PATHS = [
    SRC_ROOT / "data_archive" / "raw_prospective_archive.py",
    SRC_ROOT / "data_archive" / "lineage_audit.py",
]
REUSED_MT5_WRAPPER_PATHS = [
    SRC_ROOT / "mt5" / "connection.py",
    SRC_ROOT / "mt5" / "market_data.py",
    SRC_ROOT / "mt5" / "broker_time.py",
]

# market_data.py also defines get_candles(), which uses copy_rates_range() --
# NOT on the mission's read allowlist. The archive module never imports or
# calls get_candles (only get_latest_candles/get_tick), so the reachability
# proof below is scoped to the functions actually reachable from the archive,
# not to every function that happens to live in the same file. Per mission
# P2, expanding the allowlist to cover copy_rates_range would require a STOP
# and a report -- unnecessary here since that call path is simply not used.
REACHABLE_FUNCTIONS_BY_PATH = {
    SRC_ROOT / "mt5" / "market_data.py": {
        "get_latest_candles",
        "get_tick",
        "_require_connected",
        "_require_symbol",
        "_broker_offset_hours",
        "_validate_monotonic",
        "_validate_ohlc",
        "_is_raw_cache_entry_valid",
        "clear_raw_candle_cache",
    },
}

# Mission P2 explicit allowlist.
ALLOWED_MT5_CALLS = {
    "initialize",
    "shutdown",
    "terminal_info",
    "account_info",
    "symbol_info",
    "symbol_info_tick",
    "copy_rates_from_pos",
    # non-mutating helpers already used inside the two reused wrapper modules
    "last_error",
    "symbol_select",
}

FORBIDDEN_IDENTIFIERS = {
    "order_send",
    "order_check",
    "positions_get",
    "position_modify",
    "TRADE_ACTION_DEAL",
    "TRADE_ACTION_SLTP",
    "positions",  # mt5.account.positions() -- not reused by the archive
}

FORBIDDEN_IMPORT_MODULES = {
    "execution.mt5_gateway",
    "mt5.management_gateway",
    "mt5.account",
    "state.proposal_ledger",
    "proposal_envelope",
    "validation_orchestrator",
    "historical_replay",
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _mt5_attribute_calls(tree: ast.Module, only_functions: set[str] | None = None) -> set[str]:
    """Every `mt5.<name>(...)` / `MetaTrader5.<name>(...)` call surfaced in the module,
    optionally restricted to the given set of top-level function names (see
    REACHABLE_FUNCTIONS_BY_PATH for why that restriction is sometimes needed)."""
    if only_functions is None:
        scan_roots: list[ast.AST] = [tree]
    else:
        scan_roots = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in only_functions
        ]

    calls = set()
    for root in scan_roots:
        for node in ast.walk(root):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                value = node.func.value
                if isinstance(value, ast.Name) and value.id in {"mt5", "MetaTrader5"}:
                    calls.add(node.func.attr)
    return calls


def _all_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _imported_module_names(tree: ast.Module) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", ARCHIVE_MODULE_PATHS + REUSED_MT5_WRAPPER_PATHS)
def test_only_allowlisted_mt5_calls_are_reachable(path: Path) -> None:
    """P9 #1 / #2: every mt5.* call in the archive package and in the two
    read-only wrappers it reuses is on the mission's explicit read allowlist;
    no order-mutation call is reachable through this code path."""
    tree = _parse(path)
    calls = _mt5_attribute_calls(tree, only_functions=REACHABLE_FUNCTIONS_BY_PATH.get(path))
    unexpected = calls - ALLOWED_MT5_CALLS
    assert not unexpected, f"{path}: non-allowlisted MT5 call(s) reachable: {unexpected}"


@pytest.mark.parametrize("path", ARCHIVE_MODULE_PATHS + REUSED_MT5_WRAPPER_PATHS)
def test_no_forbidden_identifier_present(path: Path) -> None:
    """P9 #2 (belt-and-suspenders): forbidden order-mutation / position-read
    identifiers do not appear anywhere in the archive package's own source,
    nor in the two wrapper modules it reuses."""
    tree = _parse(path)
    names = _all_names(tree)
    hit = names & FORBIDDEN_IDENTIFIERS
    assert not hit, f"{path}: forbidden identifier(s) present: {hit}"


@pytest.mark.parametrize("path", ARCHIVE_MODULE_PATHS)
def test_archive_module_never_imports_execution_or_validation_machinery(path: Path) -> None:
    """P9 #3 #4 #5 #10: the archive package cannot invoke SSC replay, cannot
    create DEV_003, cannot assign DEVELOPMENT authority, and cannot write
    state/proposal_ledger, because it never imports any of the modules that
    could do those things."""
    tree = _parse(path)
    imported = _imported_module_names(tree)
    for forbidden in FORBIDDEN_IMPORT_MODULES:
        hit = {m for m in imported if m == forbidden or m.startswith(forbidden + ".")}
        assert not hit, f"{path}: imports forbidden module(s) {hit}"


def test_archive_package_has_no_write_path_to_proposal_ledger() -> None:
    """P9 #10: no file under src/data_archive/ opens the proposal ledger file
    or references a proposal envelope ID field by name. (Prose in module
    docstrings describing the isolation boundary, e.g. "state/proposal_ledger",
    is fine and expected -- only an actual filename/field reference matters.)"""
    forbidden_strings = ("proposal_ledger.json", "proposal_envelope_id")
    for path in ARCHIVE_MODULE_PATHS:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_strings:
            assert needle not in text, f"{path}: references forbidden string {needle!r}"


def test_archive_module_importable_without_reaching_live_mt5() -> None:
    """Importing the archive module must not itself touch a live terminal
    (no MT5 call happens at import time -- only inside function bodies).

    Deliberately does NOT importlib.reload() the module: reloading would
    rebind its exception classes to new objects, breaking `isinstance`/
    `except` matching for every other test in this session that already
    imported the pre-reload classes (e.g. ArchiveImmutabilityError in
    tests/test_raw_prospective_archive_partitions.py)."""
    module = importlib.import_module("data_archive.raw_prospective_archive")
    assert hasattr(module, "collect_daily_partition")


def test_lineage_audit_flags_overlap_instead_of_assuming_independence() -> None:
    """P9 #11: two datasets with DIFFERENT population/dataset IDs but the same
    symbol, overlapping date ranges, and no declared parent relationship must
    be classified as OVERLAPPING_RAW_SAMPLE, never assumed independent merely
    because their IDs differ."""
    from datetime import date

    from data_archive.lineage_audit import DatasetLineageRef, OVERLAPPING_RAW_SAMPLE, classify_lineage

    a = DatasetLineageRef(
        dataset_id="POPULATION_A",
        symbol="EURUSD",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    b = DatasetLineageRef(
        dataset_id="POPULATION_B_DIFFERENT_ID",
        symbol="EURUSD",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 9, 10),
    )
    assert classify_lineage(a, b) == OVERLAPPING_RAW_SAMPLE


def test_lineage_audit_derived_from_prior_data_via_parent_field() -> None:
    """DEV_002's real manifest declares DEV_001 as parent_dataset -- must classify
    as DERIVED_FROM_PRIOR_DATA, not independent, regardless of the different ID."""
    from datetime import date

    from data_archive.lineage_audit import DatasetLineageRef, DERIVED_FROM_PRIOR_DATA, classify_lineage

    dev_001 = DatasetLineageRef(
        dataset_id="SSC_V1_0_1_G2_DEV_001", symbol="EURUSD",
        start_date=date(2026, 6, 21), end_date=date(2026, 8, 2),
    )
    dev_002 = DatasetLineageRef(
        dataset_id="SSC_V1_0_1_G2_DEV_002", symbol="EURUSD",
        start_date=date(2026, 6, 21), end_date=date(2026, 8, 2),
        parent_dataset="SSC_V1_0_1_G2_DEV_001",
    )
    assert classify_lineage(dev_001, dev_002) == DERIVED_FROM_PRIOR_DATA
    assert classify_lineage(dev_002, dev_001) == DERIVED_FROM_PRIOR_DATA


def test_lineage_audit_does_not_call_temporally_distant_same_version_split_an_interval_match() -> None:
    """A same-symbol, different-strategy-version pair separated by months is a
    genuinely independent period, not the same market interval under a semantic
    split -- only near/adjacent non-overlapping ranges qualify for that label."""
    from datetime import date

    from data_archive.lineage_audit import DatasetLineageRef, INDEPENDENT_RAW_SAMPLE, classify_lineage

    a = DatasetLineageRef(
        dataset_id="A", symbol="EURUSD", start_date=date(2025, 1, 1), end_date=date(2025, 1, 31),
        strategy_version_used="1.0.0",
    )
    b = DatasetLineageRef(
        dataset_id="B", symbol="EURUSD", start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        strategy_version_used="1.0.1",
    )
    assert classify_lineage(a, b) == INDEPENDENT_RAW_SAMPLE


def test_lineage_audit_flags_adjacent_version_split_as_same_interval() -> None:
    """DEV_002 (v1.0.1, ends 2026-08-02) and GEN_002 (v1.0.0 pre-remediation,
    starts 2026-08-03) are immediately adjacent on the same symbol -- this is a
    semantic split of essentially one interval, not two independent samples."""
    from datetime import date

    from data_archive.lineage_audit import (
        DatasetLineageRef,
        SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS,
        classify_lineage,
    )

    dev_002 = DatasetLineageRef(
        dataset_id="SSC_V1_0_1_G2_DEV_002", symbol="EURUSD",
        start_date=date(2026, 6, 21), end_date=date(2026, 8, 2),
        strategy_version_used="1.0.1",
    )
    gen_002 = DatasetLineageRef(
        dataset_id="SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914", symbol="EURUSD",
        start_date=date(2026, 8, 3), end_date=date(2026, 9, 14),
        strategy_version_used="1.0.0 (pre-remediation)",
    )
    assert classify_lineage(dev_002, gen_002) == SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS
