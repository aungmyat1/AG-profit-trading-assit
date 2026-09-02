"""Focused tests for AG_POST_LONDON_NEWYORK_PILOT_V1_0_1 -- the LONDON_NEWYORK cycle
already defined in strategies/ST_ASIAN_SWEEP_5R_V1.yaml's session_pairs, activated as an
independent pilot alongside the existing AG_POST_ASIAN_LONDON_PILOT_V1_0_1.

Does NOT re-test snapshot/decision/ledger/governor mechanics already covered by
tests/test_post_asian_pilot.py (that logic is fully generic over session_name/pair_id and
is reused as-is, unchanged). This file tests only the actual delta: correct session-pair
wiring, and that the two cycles' opportunity quotas are genuinely independent (a proposal
in one cycle must not consume or block the other cycle's slot for the same symbol/day).
"""
from __future__ import annotations

import datetime as dt

import pytest

import session_clock as sc
from post_asian_pilot.governor import DailyTradeLedger
from post_asian_pilot.pilot_config import load_pilot_config
from post_asian_pilot.store import DEFAULT_STATE_DIR, PilotStores
from strategy_engine.engine import evaluate as evaluate_strategy
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
NY_PILOT_PATH = "config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml"
ASIAN_PILOT_PATH = "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml"


def _flat_candles(start: dt.datetime, count: int, base: float = 1.1000):
    return [Candle(time=start + dt.timedelta(minutes=15 * i), open=base, high=base + 0.0002,
                   low=base - 0.0002, close=base) for i in range(count)]


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


# --------------------------------------------------------------------------- config wiring

def test_ny_pilot_config_loads_with_correct_pair_and_windows():
    pilot = load_pilot_config(NY_PILOT_PATH)
    assert pilot.pair_id == "LONDON_NEWYORK"
    assert pilot.reference_session_name == "london_am"
    assert pilot.execution_window_start_utc == "12:00"
    assert pilot.execution_window_end_utc == "15:00"
    assert pilot.universe == ("EURUSD", "GBPUSD")
    assert pilot.state_dir == "journal/post_london_newyork_pilot"


def test_asian_pilot_config_unchanged_and_still_defaults_state_dir():
    pilot = load_pilot_config(ASIAN_PILOT_PATH)
    assert pilot.pair_id == "ASIAN_LONDON"
    assert pilot.state_dir is None  # untouched file -- falls back to DEFAULT_STATE_DIR


def test_session_clock_bounds_match_strategy_contract():
    d = dt.date(2026, 9, 2)
    london_start, london_end = sc.get_session_bounds(d, "london_am")
    ny_start, ny_end = sc.get_session_bounds(d, "new_york_am")
    assert (london_start.time(), london_end.time()) == (dt.time(6, 0), dt.time(11, 0))
    assert (ny_start.time(), ny_end.time()) == (dt.time(12, 0), dt.time(15, 0))


# ------------------------------------------------------------------- occurrence identity

def test_london_newyork_signal_identity_distinct_from_asian_london(strategy):
    d = dt.date(2026, 9, 2)
    candles = _flat_candles(dt.datetime(2026, 9, 2, 6, 0, tzinfo=UTC), 20)

    asian_signal = evaluate_strategy(strategy, "ASIAN_LONDON", "EURUSD", d, candles, 20)
    ny_signal = evaluate_strategy(strategy, "LONDON_NEWYORK", "EURUSD", d, candles, 20)

    assert asian_signal.signal_id != ny_signal.signal_id
    assert asian_signal.pair_id == "ASIAN_LONDON"
    assert ny_signal.pair_id == "LONDON_NEWYORK"
    assert asian_signal.reference_session == "Asian"
    assert ny_signal.reference_session == "London"


# ----------------------------------------------------------------- quota independence

def test_state_dir_isolates_pilot_stores(tmp_path):
    strategy_id = "ST_ASIAN_SWEEP_5R_V1"
    stores_asian = PilotStores.default(strategy_id, str(tmp_path / "asian"))
    stores_ny = PilotStores.default(strategy_id, str(tmp_path / "ny"))
    assert stores_asian.decision_store.path != stores_ny.decision_store.path
    assert stores_asian.ledger.store.path != stores_ny.ledger.store.path


def test_ledger_slot_in_one_cycle_does_not_consume_the_others_quota(tmp_path):
    """The core cycle-independence guarantee (spec section 8/9): claiming EURUSD's slot
    for ASIAN_LONDON must not block EURUSD from also claiming a LONDON_NEWYORK slot the
    same trading day -- because each cycle's pilot uses its own state_dir, and therefore
    its own DailyTradeLedger file, not a shared strategy_id-scoped one."""
    trading_date = dt.date(2026, 9, 2)
    now = dt.datetime(2026, 9, 2, 11, 5, tzinfo=UTC)

    ledger_asian = DailyTradeLedger.default(str(tmp_path / "asian" / "daily_trade_ledger.json"))
    ledger_ny = DailyTradeLedger.default(str(tmp_path / "ny" / "daily_trade_ledger.json"))

    claim_asian = ledger_asian.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", trading_date,
                                         "EURUSD", "setup-asian-1", "proposal-asian-1", now, now)
    claim_ny = ledger_ny.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", trading_date,
                                   "EURUSD", "setup-ny-1", "proposal-ny-1", now, now)

    assert claim_asian.success
    assert claim_ny.success
    assert ledger_asian.consumed_count("ST_ASIAN_SWEEP_5R_V1", trading_date) == 1
    assert ledger_ny.consumed_count("ST_ASIAN_SWEEP_5R_V1", trading_date) == 1


def test_negative_control_shared_ledger_would_have_blocked_the_second_cycle(tmp_path):
    """Documents WHY the isolated state_dir is required: a single shared ledger (the
    pre-fix shape, keyed by strategy_id+date only -- see governor.DailyTradeLedger._key)
    blocks a second same-symbol claim regardless of which cycle it came from."""
    trading_date = dt.date(2026, 9, 2)
    now = dt.datetime(2026, 9, 2, 11, 5, tzinfo=UTC)
    shared_ledger = DailyTradeLedger.default(str(tmp_path / "shared" / "daily_trade_ledger.json"))

    first = shared_ledger.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", trading_date,
                                    "EURUSD", "setup-asian-1", "proposal-asian-1", now, now)
    second = shared_ledger.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", trading_date,
                                     "EURUSD", "setup-ny-1", "proposal-ny-1", now, now)

    assert first.success
    assert not second.success
    assert second.reason_code == "BLOCKED_SYMBOL_DAILY_TRADE_LIMIT"


def test_default_state_dir_constant_matches_existing_asian_pilot_journal():
    assert DEFAULT_STATE_DIR == "journal/post_asian_pilot"
