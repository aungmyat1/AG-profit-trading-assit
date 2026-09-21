"""Focused tests for AG_FX_SESSION_DAYTRADE_EURUSD_V1 -- the EURUSD-only, 1-slot/cycle
book built on the two ASIAN_LONDON / LONDON_NEWYORK session_pairs entries already defined
in strategies/ST_ASIAN_SWEEP_5R_V1.yaml@1.1.1 and already proven generic/cycle-independent
by tests/test_post_asian_pilot.py and tests/test_post_london_newyork_pilot.py.

Does NOT re-test snapshot/decision/ledger/governor mechanics -- those are fully generic
over pair_id/state_dir and reused unchanged. This file proves only the book-specific
delta: correct overlay wiring (universe, strategy identity, cycle mapping, isolated
state_dir, 1-slot capacity), that registry/trading-mode safety gates remain untouched,
and that the wrapper's --cycle routing resolves to the intended overlay.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

import datetime as dt

from post_asian_pilot.governor import DailyTradeLedger
from post_asian_pilot.pilot_config import load_pilot_config
from post_asian_pilot.store import PilotStores

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER_SCRIPT_PATH = REPO_ROOT / "scripts" / "run_fx_session_daytrade.py"


def _load_wrapper_module():
    spec = importlib.util.spec_from_file_location("run_fx_session_daytrade_under_test", WRAPPER_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

AL_PILOT_PATH = "config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_ASIAN_LONDON_V1.yaml"
LNY_PILOT_PATH = "config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_LONDON_NEWYORK_V1.yaml"

SIBLING_ASIAN_STATE_DIR = "journal/post_asian_pilot"
SIBLING_NY_STATE_DIR = "journal/post_london_newyork_pilot"


# --------------------------------------------------------------------------- T1/T3: parsing + identity

def test_asian_london_overlay_loads_and_binds_frozen_strategy():
    pilot = load_pilot_config(AL_PILOT_PATH)
    assert pilot.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert pilot.strategy_version == "1.1.1"
    assert pilot.strategy_source_path == "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


def test_london_newyork_overlay_loads_and_binds_frozen_strategy():
    pilot = load_pilot_config(LNY_PILOT_PATH)
    assert pilot.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert pilot.strategy_version == "1.1.1"
    assert pilot.strategy_source_path == "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


# --------------------------------------------------------------------------- T2: EURUSD-only

def test_asian_london_universe_is_eurusd_only():
    pilot = load_pilot_config(AL_PILOT_PATH)
    assert pilot.universe == ("EURUSD",)
    assert pilot.tie_break_priority == ("EURUSD",)


def test_london_newyork_universe_is_eurusd_only():
    pilot = load_pilot_config(LNY_PILOT_PATH)
    assert pilot.universe == ("EURUSD",)
    assert pilot.tie_break_priority == ("EURUSD",)


# --------------------------------------------------------------------------- T4: cycle mapping

def test_asian_london_cycle_mapping():
    pilot = load_pilot_config(AL_PILOT_PATH)
    assert pilot.pair_id == "ASIAN_LONDON"
    assert pilot.reference_session_name == "asian"
    assert pilot.execution_window_start_utc == "07:00"
    assert pilot.execution_window_end_utc == "11:00"


def test_london_newyork_cycle_mapping():
    pilot = load_pilot_config(LNY_PILOT_PATH)
    assert pilot.pair_id == "LONDON_NEWYORK"
    assert pilot.reference_session_name == "london_am"
    assert pilot.execution_window_start_utc == "12:00"
    assert pilot.execution_window_end_utc == "15:00"


# --------------------------------------------------------------------------- T5/T9(state): isolation

def test_state_dirs_are_isolated_from_each_other_and_from_sibling_pilots():
    al = load_pilot_config(AL_PILOT_PATH)
    lny = load_pilot_config(LNY_PILOT_PATH)

    assert al.state_dir == "journal/fx_session_daytrade/asian_london"
    assert lny.state_dir == "journal/fx_session_daytrade/london_newyork"

    all_dirs = {al.state_dir, lny.state_dir, SIBLING_ASIAN_STATE_DIR, SIBLING_NY_STATE_DIR}
    assert len(all_dirs) == 4, "one of this book's state_dirs collides with a sibling pilot's"


# --------------------------------------------------------------------------- T6/T7: capacity caps

def test_asian_london_capped_at_one_slot_per_day():
    pilot = load_pilot_config(AL_PILOT_PATH)
    assert pilot.max_new_trades_per_day == 1
    assert pilot.max_new_trades_per_symbol_per_day == 1
    assert pilot.max_open_positions == 1


def test_london_newyork_capped_at_one_slot_per_day():
    pilot = load_pilot_config(LNY_PILOT_PATH)
    assert pilot.max_new_trades_per_day == 1
    assert pilot.max_new_trades_per_symbol_per_day == 1
    assert pilot.max_open_positions == 1


def test_book_theoretical_maximum_is_two_slots_per_day():
    al = load_pilot_config(AL_PILOT_PATH)
    lny = load_pilot_config(LNY_PILOT_PATH)
    assert al.max_new_trades_per_day + lny.max_new_trades_per_day == 2


def test_actual_ledger_enforces_one_eurusd_slot_per_cycle_per_day(tmp_path):
    """Known limitation (documented in the implementation status doc): pilot_config.py
    parses max_new_trades_per_day off the overlay YAML, but src/post_asian_pilot/store.py's
    PilotStores.default() never passes it into governor.DailyTradeLedger.default() --
    ledger capacity is always governor.DEFAULT_MAX_SLOTS (2), regardless of a pilot
    config's own max_new_trades_per_day value. This is a pre-existing gap shared with
    both sibling pilots (AG_POST_ASIAN_LONDON_PILOT_V1_0_1, AG_POST_LONDON_NEWYORK_PILOT_V1_0_1),
    not introduced by this book, and out of scope to fix here (mission section 20/27).

    This book's actual 1-slot/cycle/day cap is real anyway, as an emergent property of
    governor.DEFAULT_MAX_SLOTS_PER_SYMBOL (1) combined with this book's EURUSD-only
    universe: with only one symbol ever competing for a slot, the per-symbol cap alone
    is sufficient to block a second EURUSD claim the same trading date, independent of
    the (currently unused) max_slots=2 headroom. This test proves that real mechanism
    directly, using PilotStores.default() exactly as pipeline.run_pilot_cycle() does."""
    strategy_id = "ST_ASIAN_SWEEP_5R_V1"
    stores = PilotStores.default(strategy_id, str(tmp_path / "asian_london"))
    trading_date = dt.date(2026, 9, 21)
    now = dt.datetime(2026, 9, 21, 8, 0, tzinfo=dt.timezone.utc)

    first = stores.ledger.try_claim(strategy_id, "1.1.1", "REL", trading_date,
                                    "EURUSD", "setup-1", "proposal-1", now, now)
    second = stores.ledger.try_claim(strategy_id, "1.1.1", "REL", trading_date,
                                     "EURUSD", "setup-2", "proposal-2", now, now)

    assert first.success
    assert not second.success
    assert stores.ledger.consumed_count(strategy_id, trading_date) == 1


# --------------------------------------------------------------------------- T8: proposal-only

def test_both_overlays_are_proposal_only():
    for path in (AL_PILOT_PATH, LNY_PILOT_PATH):
        with open(REPO_ROOT / path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        assert raw["execution"]["mode"] == "PROPOSAL_ONLY"
        assert raw["execution"]["automatic_execution"] is False
        assert raw["execution"]["live_execution"] is False


# --------------------------------------------------------------------------- T10/T11: safety gates untouched

def test_registry_authorization_remains_false_for_bound_strategy():
    with open(REPO_ROOT / "strategies/registry.yaml", "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    entry = registry["strategies"]["ST_ASIAN_SWEEP_5R_V1"]
    assert entry["demo_authorized"] is False
    assert entry["live_authorized"] is False


def test_trading_config_remains_analysis_mode_no_order_send():
    with open(REPO_ROOT / "config/trading.yaml", "r", encoding="utf-8") as f:
        trading = yaml.safe_load(f)
    assert trading["mode"] == "ANALYSIS"
    assert trading["execution"]["allow_order_send"] is False
    assert trading["account"]["allow_live_trading"] is False


# --------------------------------------------------------------------------- T15: wrapper --cycle routing

def _run_wrapper(*args):
    # 150s: this repo's post_asian_pilot import chain has an observed ~30s cold-import
    # cost (unrelated to this wrapper -- a third-party package banner/import delay),
    # which can grow further under concurrent test/system load.
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_fx_session_daytrade.py"), *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=150,
    )


def test_wrapper_requires_cycle_argument():
    result = _run_wrapper("--preflight")
    assert result.returncode != 0
    assert "--cycle is required" in result.stderr


def test_wrapper_rejects_both_cycle_for_once():
    result = _run_wrapper("--once", "--cycle", "BOTH")
    assert result.returncode == 2
    assert "does not accept --cycle BOTH" in result.stderr


def test_wrapper_cycle_paths_resolve_to_intended_overlays():
    module = _load_wrapper_module()
    assert module._CYCLE_PATHS["ASIAN_LONDON"] == AL_PILOT_PATH
    assert module._CYCLE_PATHS["LONDON_NEWYORK"] == LNY_PILOT_PATH
