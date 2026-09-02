"""Tomorrow's operational readiness check (AG_TRADE_ASSISTANT_V1_0_1_PREFLIGHT).

Read-only: connects to MT5, resolves symbol metadata, validates the canonical session
contract, checks account mode, checks the daily trade slot / open-position-guard /
daily-loss-guard state stores, and reconciles via the existing
execution.coordinator.ExecutionCoordinator (reused as-is, not reimplemented). Never
calls order_check/order_send. Fails closed (PILOT_STARTUP_BLOCKED) on the first hard
failure rather than reporting a partial, possibly-misleading green state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional, Tuple

from execution.coordinator import ExecutionCoordinator
from mt5.account import Account, AccountError, account as fetch_account
from mt5.connection import MT5ConnectionError, connect, is_connected
from mt5.symbol_resolver import SymbolMetaError, get_symbol_meta
from runtime_state.store import JsonKeyValueStore, StateStoreCorrupted
from session_clock import SessionContractConflict, validate_session_contract
from strategy_engine.loader import load_strategy

from .fingerprint import fingerprint
from .governor import DailyTradeLedger
from .pilot_config import PilotConfig, load_pilot_config, load_raw_yaml
from .report import release_fingerprints
from .store import DEFAULT_STATE_DIR

STATUS_READY = "READY_TO_MONITOR"
STATUS_BLOCKED = "PILOT_STARTUP_BLOCKED"

DEFAULT_FINGERPRINT_BASELINE_PATH = "journal/post_asian_pilot/release_fingerprint_baseline.json"


@dataclass(frozen=True)
class PreflightResult:
    pilot_status: str  # STATUS_READY or STATUS_BLOCKED
    first_block_reason: Optional[str]
    checks: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)  # (check_name, PASS/FAIL[:reason])
    release_id: Optional[str] = None
    release_fingerprint: Optional[str] = None
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None
    account_mode: Optional[str] = None
    trading_date: Optional[date] = None
    daily_slot_state: Optional[str] = None
    open_positions: Optional[int] = None
    snapshot_store_state: Optional[str] = None


def run_preflight(
    release_path: str = "config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml",
    pilot_path: Optional[str] = None,
    baseline_path: str = DEFAULT_FINGERPRINT_BASELINE_PATH,
) -> PreflightResult:
    """Readiness ONLY (spec section 13): never runs a strategy cycle, never claims a
    ledger slot, never writes/mutates a snapshot, never sends an order."""
    checks = []
    first_block = None

    def _fail(name: str, reason: str) -> None:
        nonlocal first_block
        checks.append((name, f"FAIL:{reason}"))
        if first_block is None:
            first_block = reason

    def _pass(name: str) -> None:
        checks.append((name, "PASS"))

    # -- release / pilot config load --------------------------------------------------
    try:
        release_raw = load_raw_yaml(release_path)
        pilot: PilotConfig = load_pilot_config(pilot_path) if pilot_path else load_pilot_config()
        _pass("release_manifest_loaded")
    except Exception as exc:  # noqa: BLE001 -- any load failure is a hard block
        _fail("release_manifest_loaded", f"RELEASE_LOAD_FAILED:{exc}")
        return PreflightResult(STATUS_BLOCKED, first_block, tuple(checks))

    if release_raw.get("release_id") != "AG_TRADE_ASSISTANT_V1_0_2":
        _fail("release_id", "WRONG_RELEASE_LOADED")
    else:
        _pass("release_id")

    try:
        strategy = load_strategy(pilot.strategy_source_path)
        _pass("strategy_loaded")
    except Exception as exc:  # noqa: BLE001
        _fail("strategy_loaded", f"STRATEGY_LOAD_FAILED:{exc}")
        return PreflightResult(STATUS_BLOCKED, first_block, tuple(checks))

    # -- fingerprints: compare against last recorded baseline (first run establishes it) --
    fps = release_fingerprints(release_path, pilot.strategy_source_path,
                               "config/canonical_sessions.yaml", pilot.raw["risk"])
    baseline_store = JsonKeyValueStore(baseline_path)
    try:
        baseline = baseline_store.get(release_raw["release_id"])
    except StateStoreCorrupted as exc:
        _fail("fingerprint_baseline_readable", f"STATE_PERSISTENCE_UNAVAILABLE:{exc}")
        return PreflightResult(STATUS_BLOCKED, first_block, tuple(checks))

    if baseline is None:
        baseline_store.put(release_raw["release_id"], fps)
        _pass("fingerprint_baseline_established")
    else:
        mismatch_keys = [key for key in ("strategy_fingerprint", "session_fingerprint", "risk_fingerprint")
                        if baseline.get(key) != fps[key]]
        for key in mismatch_keys:
            _fail(key, f"{key.upper()}_MISMATCH")
        if not mismatch_keys:
            _pass("fingerprints_match_baseline")

    # -- canonical session contract -----------------------------------------------------
    try:
        validate_session_contract()
        _pass("canonical_session_contract")
    except SessionContractConflict as exc:
        _fail("canonical_session_contract", f"SESSION_CONTRACT_CONFLICT:{exc}")

    # -- MT5 connection / account mode ---------------------------------------------------
    account: Optional[Account] = None
    try:
        connect()
        if not is_connected():
            _fail("mt5_connection", "MT5_DISCONNECTED")
        else:
            _pass("mt5_connection")
            account = fetch_account()
            if not account.is_demo:
                _fail("account_mode", "WRONG_ACCOUNT_MODE_NOT_DEMO")
            else:
                _pass("account_mode")
    except (MT5ConnectionError, AccountError) as exc:
        _fail("mt5_connection", f"MT5_DISCONNECTED:{exc}")

    # -- symbol resolution ----------------------------------------------------------------
    for symbol in pilot.universe:
        try:
            get_symbol_meta(symbol)
            _pass(f"symbol_resolved_{symbol}")
        except SymbolMetaError as exc:
            _fail(f"symbol_resolved_{symbol}", f"SYMBOL_METADATA_MISSING:{exc}")

    # -- state stores / daily slot / open positions / reconciliation ----------------------
    trading_date = datetime.now(timezone.utc).date()
    state_dir = pilot.state_dir or DEFAULT_STATE_DIR
    daily_slot_state = None
    open_positions_count = None
    try:
        ledger = DailyTradeLedger.default(f"{state_dir}/daily_trade_ledger.json")
        slots = ledger.slots(strategy.strategy_id, trading_date)
        daily_slot_state = f"{len(slots)}/{ledger.max_slots}"
        _pass("daily_trade_ledger_readable")
    except StateStoreCorrupted as exc:
        _fail("daily_trade_ledger_readable", f"DAILY_SLOT_CORRUPT:{exc}")

    snapshot_store_state = None
    try:
        snapshot_store = JsonKeyValueStore(f"{state_dir}/session_snapshot.json")
        count = len(snapshot_store.all())
        snapshot_store_state = f"{count} frozen snapshot(s), readable"
        _pass("snapshot_store_readable")
    except StateStoreCorrupted as exc:
        _fail("snapshot_store_readable", f"ASIAN_SNAPSHOT_CORRUPT:{exc}")

    try:
        coordinator = ExecutionCoordinator.default()
        open_positions_count = coordinator.open_position_guard.open_count()
        if account is not None:
            coordinator.reconcile()
        _pass("reconciliation_healthy")
    except Exception as exc:  # noqa: BLE001 -- any reconciliation failure blocks the pilot
        _fail("reconciliation_healthy", f"RECONCILIATION_UNHEALTHY:{exc}")

    status = STATUS_BLOCKED if first_block is not None else STATUS_READY
    return PreflightResult(
        pilot_status=status, first_block_reason=first_block, checks=tuple(checks),
        release_id=release_raw.get("release_id"), release_fingerprint=fps["release_fingerprint"],
        strategy_id=strategy.strategy_id, strategy_version=strategy.version,
        account_mode=("DEMO" if (account and account.is_demo) else "LIVE" if account else None),
        trading_date=trading_date, daily_slot_state=daily_slot_state, open_positions=open_positions_count,
        snapshot_store_state=snapshot_store_state,
    )
