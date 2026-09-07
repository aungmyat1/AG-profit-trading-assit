"""Focused tests for AG_POST_ASIAN_LONDON_PILOT_V1 / V1_0_1: session snapshot validation,
decision normalization, ready_at semantics (never evaluation_time), risk-sized proposal
construction, the two-slot daily opportunity ledger (atomic cross-process claim, one slot
per symbol, terminal-state consumption, crash recovery), deterministic candidate
ordering, execution-boundary (zero order_check/order_send, non-owner execution blocked),
and release-manifest fingerprints. Uses tmp_path-backed JsonKeyValueStore files
throughout -- never touches the real journal/ directory.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from mt5.symbol_resolver import SymbolMeta
from runtime_state.store import JsonKeyValueStore
from strategy_engine.loader import load_strategy
from strategy_engine.models import TradeSignal

from post_asian_pilot.decision import (
    STATUS_DATA_ERROR,
    STATUS_EXPIRED,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
    data_error_decision,
    map_trade_signal_to_decision,
    watch_decision,
)
from post_asian_pilot.fingerprint import fingerprint
from post_asian_pilot.governor import (
    PORTFOLIO_BLOCKED,
    PORTFOLIO_ELIGIBLE,
    REASON_AGGREGATE_OPEN_RISK,
    REASON_DAILY_TRADE_LIMIT,
    REASON_OPEN_POSITION_LIMIT,
    REASON_STRATEGY_DAILY_LOSS_LOCK,
    REASON_SYMBOL_DAILY_TRADE_LIMIT,
    DailyTradeLedger,
    evaluate_daily_governor,
    evaluate_execution_eligibility,
    strategy_open_position_count,
    strategy_open_risk_pct,
    validate_slot_ownership,
)
from post_asian_pilot.pilot_config import (
    V1_0_PILOT_CONFIG_PATH,
    V1_0_RELEASE_CONFIG_PATH,
    load_pilot_config,
    load_raw_yaml,
)
from post_asian_pilot.proposal import build_entry_proposal
from post_asian_pilot.report import release_fingerprints
from post_asian_pilot.snapshot import build_asian_session_snapshot, validate_candle_array
from post_asian_pilot.store import (
    SnapshotImmutabilityViolation,
    decision_from_record,
    save_decision,
    save_proposal,
    save_snapshot,
)
from post_asian_pilot.tiebreak import order_candidates
from strategy_engine.session import Candle

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
RELEASE_PATH = "config/releases/AG_TRADE_ASSISTANT_V1_0_1.yaml"


def _m15_candles(start: dt.datetime, count: int, base: float = 1.1000, step: float = 0.0001):
    out = []
    price = base
    for i in range(count):
        t = start + dt.timedelta(minutes=15 * i)
        out.append(Candle(time=t, open=price, high=price + step, low=price - step, close=price))
        price += step * 0.1
    return out


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


@pytest.fixture()
def symbol_meta():
    return SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5)


# --------------------------------------------------------------------------- Asian snapshot

def test_snapshot_exact_24_bars_valid():
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = _m15_candles(start, 24)
    reasons = validate_candle_array(candles, expected_bar_count=24, as_of=start + dt.timedelta(hours=6))
    assert reasons == ()


def test_snapshot_23_bars_data_error():
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = _m15_candles(start, 23)
    reasons = validate_candle_array(candles, expected_bar_count=24, as_of=start + dt.timedelta(hours=6))
    assert any(r.startswith("BAR_COUNT_MISMATCH") for r in reasons)


def test_snapshot_duplicate_bar_data_error():
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = list(_m15_candles(start, 23)) + [_m15_candles(start, 24)[-2]]
    reasons = validate_candle_array(candles, expected_bar_count=24, as_of=start + dt.timedelta(hours=6))
    assert "DUPLICATE_BAR_TIME" in reasons


def test_snapshot_out_of_order_data_error():
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = _m15_candles(start, 24)
    swapped = list(candles)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    reasons = validate_candle_array(swapped, expected_bar_count=24, as_of=start + dt.timedelta(hours=6))
    assert "OUT_OF_ORDER_BARS" in reasons


def test_snapshot_forming_last_bar_data_error():
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = _m15_candles(start, 24)
    as_of = candles[-1].time + dt.timedelta(minutes=5)  # last bar not yet closed
    reasons = validate_candle_array(candles, expected_bar_count=24, as_of=as_of)
    assert "FORMING_CANDLE_INCLUDED" in reasons


def test_snapshot_immutable_and_builds_correctly():
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = _m15_candles(start, 24)
    result = build_asian_session_snapshot(
        "ST_ASIAN_SWEEP_5R_V1", "EURUSD", dt.date(2026, 1, 5), "asian", start,
        start + dt.timedelta(hours=6), candles, 24, as_of=start + dt.timedelta(hours=6),
    )
    assert result.status == "VALID"
    with pytest.raises(Exception):
        result.snapshot.high = 999.0  # frozen dataclass


# --------------------------------------------------------------------------- decision mapping / ready_at

def _signal(status, setup, reason_code, direction=None, entry=None, stop_loss=None, risk_distance=None,
           signal_timestamp=None, symbol="EURUSD"):
    return TradeSignal(
        signal_id="SID", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol=symbol,
        pair_id="ASIAN_LONDON", reference_session="Asian", session_date=dt.date(2026, 1, 5),
        box_high=1.10, box_low=1.09, box_mid=1.095, regime="RANGE", setup=setup, status=status,
        reason_code=reason_code, direction=direction, entry=entry, stop_loss=stop_loss,
        risk_distance=risk_distance, signal_timestamp=signal_timestamp,
    )


def test_decision_sweep_signal_is_ready_with_ready_at_from_signal_timestamp():
    qualifying_candle_time = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", 1.0995, 1.101, 0.0015,
                     signal_timestamp=qualifying_candle_time)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    polling_time = dt.datetime(2026, 1, 5, 8, 1, 15, tzinfo=UTC)  # deliberately NOT the qualifying candle time
    decision = map_trade_signal_to_decision(signal, "SNAP-1", polling_time, window_end)
    assert decision.status == STATUS_READY
    assert decision.ready_at == qualifying_candle_time
    assert decision.ready_at != decision.evaluation_time  # ready_at must never be polling/wall-clock time


def test_decision_ready_sweep_without_signal_timestamp_raises():
    """STOP CONDITION: ready_at must be derivable from authoritative strategy evidence."""
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", 1.0995, 1.101, 0.0015,
                     signal_timestamp=None)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)


def test_decision_trend_signal_out_of_scope_no_trade():
    signal = _signal("SIGNAL", "TREND", "BOX_DIRECTION_V1", "LONG", 1.095, 1.09, 0.005)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    assert decision.status == STATUS_NO_TRADE
    assert "NON_SWEEP_SETUP_OUT_OF_SCOPE" in decision.reason_codes


def test_decision_no_setup_before_window_end_is_watch():
    signal = _signal("NO_TRADE", "RANGE", "NO_SETUP_BY_WINDOW_END")
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    assert decision.status == STATUS_WATCH
    assert decision.missing_condition == "WAITING_REFERENCE_SWEEP"


def test_decision_no_setup_at_window_end_is_expired():
    signal = _signal("NO_TRADE", "RANGE", "NO_SETUP_BY_WINDOW_END")
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", window_end, window_end)
    assert decision.status == STATUS_EXPIRED


def test_decision_ambiguous_dual_sweep_is_no_trade():
    signal = _signal("NO_TRADE", "SWEEP", "AMBIGUOUS_DUAL_SWEEP")
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    assert decision.status == STATUS_NO_TRADE


# --------------------------------------------------------------------------- proposal / risk sizing

def _ready_decision(symbol, ready_at, evaluation_time=None):
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.0995,
                     stop_loss=1.101, risk_distance=0.0015, signal_timestamp=ready_at, symbol=symbol)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    return map_trade_signal_to_decision(signal, "SNAP", evaluation_time or ready_at, window_end)


def test_build_entry_proposal_ready_geometry_and_risk(strategy, symbol_meta):
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    assert decision.status == STATUS_READY

    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "READY"
    tp = result.proposal.trade_proposal
    assert tp.entry == 1.10000
    assert tp.stop_loss == 1.10150
    assert tp.tp1 == pytest.approx(1.09)
    assert tp.tp2 == pytest.approx(1.10000 - 5 * 0.00150)
    assert tp.risk_percent == 0.5
    assert tp.risk_amount <= 50.0 + 1e-6
    assert result.proposal.execution_authorized is False
    assert result.proposal.user_confirmation_required is True
    assert result.proposal.execution_status == "CONFIRMATION_REQUIRED"
    assert result.proposal.actionable is False  # not actionable until an atomic ledger claim succeeds


def test_build_entry_proposal_min_volume_exceeds_budget_blocked(strategy):
    tiny_meta = SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                           volume_min=100.0, volume_max=200.0, volume_step=0.01, digits=5)
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=tiny_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "BLOCKED"
    assert result.reason_code == "VOLUME_BELOW_MIN"


# --------------------------------------------------------------------------- candidate ordering (A/B/C/D/E)

def test_order_A_one_ready():
    t = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ordered = order_candidates([_ready_decision("EURUSD", t)], priority=("EURUSD", "GBPUSD"))
    assert [d.symbol for d in ordered] == ["EURUSD"]


def test_order_B_different_qualifying_timestamps_earliest_first():
    t1 = dt.datetime(2026, 1, 5, 7, 45, tzinfo=UTC)
    t2 = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ordered = order_candidates([_ready_decision("EURUSD", t2), _ready_decision("GBPUSD", t1)],
                               priority=("EURUSD", "GBPUSD"))
    assert [d.symbol for d in ordered] == ["GBPUSD", "EURUSD"]


def test_order_C_same_qualifying_timestamp_eurusd_priority_first():
    t = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ordered = order_candidates([_ready_decision("GBPUSD", t), _ready_decision("EURUSD", t)],
                               priority=("EURUSD", "GBPUSD"))
    assert [d.symbol for d in ordered] == ["EURUSD", "GBPUSD"]


def test_order_D_polling_times_differ_qualifying_same_priority_applies():
    """Spec CASE A: evaluation_time differs (08:01:10 vs 08:01:15) but ready_at is
    identical (08:00) -- exact-timestamp priority still applies."""
    ready_at = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    eurusd = _ready_decision("EURUSD", ready_at, evaluation_time=dt.datetime(2026, 1, 5, 8, 1, 10, tzinfo=UTC))
    gbpusd = _ready_decision("GBPUSD", ready_at, evaluation_time=dt.datetime(2026, 1, 5, 8, 1, 15, tzinfo=UTC))
    ordered = order_candidates([gbpusd, eurusd], priority=("EURUSD", "GBPUSD"))
    assert [d.symbol for d in ordered] == ["EURUSD", "GBPUSD"]


def test_order_E_polling_times_same_qualifying_differs_earlier_candle_wins():
    """Spec CASE B: evaluation_time identical (08:01:10) but ready_at differs
    (08:00 vs 07:45) -- the earlier qualifying candle wins regardless of polling time."""
    polling = dt.datetime(2026, 1, 5, 8, 1, 10, tzinfo=UTC)
    eurusd = _ready_decision("EURUSD", dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), evaluation_time=polling)
    gbpusd = _ready_decision("GBPUSD", dt.datetime(2026, 1, 5, 7, 45, tzinfo=UTC), evaluation_time=polling)
    ordered = order_candidates([eurusd, gbpusd], priority=("EURUSD", "GBPUSD"))
    assert [d.symbol for d in ordered] == ["GBPUSD", "EURUSD"]


def test_order_no_candidates():
    assert order_candidates([]) == ()


# --------------------------------------------------------------------------- daily governor (loss gates only)

def test_governor_strategy_minus_1r_lock_blocks(tmp_path):
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    loss_guard.record_trade_result(dt.date(2026, 1, 5), -1.0)
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), loss_guard, -1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED
    assert result.reason_code == REASON_STRATEGY_DAILY_LOSS_LOCK


def test_governor_project_minus_2r_guard_unmodified(tmp_path):
    """The project-wide -2R guard still fires independently of the pilot's -1R lock,
    and is never weakened by this pilot's own gate."""
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    loss_guard.record_trade_result(dt.date(2026, 1, 5), -2.0)
    assert loss_guard.is_blocked(dt.date(2026, 1, 5))  # still -2.0 project circuit, untouched
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), loss_guard, -1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED


def test_governor_open_position_not_checked_at_selection_time(tmp_path):
    """Spec section 17: daily trade capacity and open-position capacity are separate --
    an open position must NOT block selection/claiming, only execution."""
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), loss_guard, -1.0)
    assert result.portfolio_state == PORTFOLIO_ELIGIBLE  # no open-position guard consulted at all


# --------------------------------------------------------------------------- daily opportunity ledger

def test_ledger_two_symbols_both_claim_slots(tmp_path):
    """Spec section 12: EURUSD and GBPUSD both READY -- both get a slot, capacity=2."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    r1 = ledger.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "AG_TRADE_ASSISTANT_V1_0_1", dt.date(2026, 1, 5),
                          "EURUSD", "SETUP-A", "PROPOSAL-A", now, now)
    r2 = ledger.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "AG_TRADE_ASSISTANT_V1_0_1", dt.date(2026, 1, 5),
                          "GBPUSD", "SETUP-B", "PROPOSAL-B", now, now)
    assert r1.success and r2.success
    assert r1.slot["slot_index"] == 1
    assert r2.slot["slot_index"] == 2
    assert ledger.consumed_count("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5)) == 2


def test_ledger_third_candidate_blocked_capacity_exhausted(tmp_path):
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"), max_slots=2)
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "A", "PA", now, now)
    ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "GBPUSD", "B", "PB", now, now)
    r3 = ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "USDJPY", "C", "PC", now, now)
    assert not r3.success
    assert r3.reason_code == REASON_DAILY_TRADE_LIMIT


def test_ledger_same_symbol_second_setup_blocked(tmp_path):
    """Spec section 14: max one setup per symbol -- a second EURUSD setup is blocked
    even though ledger capacity (2) is not exhausted."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    t1 = dt.datetime(2026, 1, 5, 7, 45, tzinfo=UTC)
    t2 = dt.datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", t1, t1)
    r2 = ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-B", "PROPOSAL-B", t2, t2)
    assert not r2.success
    assert r2.reason_code == REASON_SYMBOL_DAILY_TRADE_LIMIT


def test_ledger_idempotent_reclaim_same_identity_crash_recovery(tmp_path):
    """Spec section 14/H: a process that crashed after claiming but before persisting
    its proposal can safely re-claim the IDENTICAL identity on restart."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    first = ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", now, now)
    second = ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", now, now)
    assert first.success and second.success
    assert ledger.consumed_count("S", dt.date(2026, 1, 5)) == 1  # no duplicate slot


def test_ledger_terminal_states_never_free_capacity(tmp_path):
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", now, now)
    ledger.transition("S", dt.date(2026, 1, 5), "EURUSD", "EXPIRED", terminal_reason="WINDOW_CLOSED", now=now)
    assert ledger.consumed_count("S", dt.date(2026, 1, 5)) == 1
    # A different setup on EURUSD is still blocked -- EXPIRED does not free the symbol slot.
    r2 = ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-B", "PROPOSAL-B", now, now)
    assert not r2.success
    assert r2.reason_code == REASON_SYMBOL_DAILY_TRADE_LIMIT


def test_ledger_restart_terminal_state_preserved(tmp_path):
    """Spec I-L: restart with each terminal state preserves it -- fresh instance, same
    backing file."""
    path = str(tmp_path / "ledger.json")
    ledger = DailyTradeLedger.default(path)
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", now, now)
    ledger.transition("S", dt.date(2026, 1, 5), "EURUSD", "DECLINED", terminal_reason="USER_DECLINED", now=now)

    ledger_after_restart = DailyTradeLedger.default(path)
    slot = ledger_after_restart.symbol_slot("S", dt.date(2026, 1, 5), "EURUSD")
    assert slot["state"] == "DECLINED"
    assert ledger_after_restart.consumed_count("S", dt.date(2026, 1, 5)) == 1


def test_ledger_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{not valid json", encoding="utf-8")
    from runtime_state.store import StateStoreCorrupted
    ledger = DailyTradeLedger.default(str(path))
    with pytest.raises(StateStoreCorrupted):
        ledger.slots("S", dt.date(2026, 1, 5))


def test_ledger_concurrent_claims_exactly_one_per_symbol(tmp_path):
    """Spec section 16, CASE A: two candidates concurrently claim an empty ledger --
    both succeed (different symbols), no overwrite, unique slot indexes. Uses a
    ThreadPoolExecutor racing on the SAME real OS-level exclusive-file-creation lock
    every process would use -- the mechanism under test is process-agnostic."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)

    def _claim(symbol, setup_id, proposal_id):
        return ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), symbol, setup_id, proposal_id, now, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_claim, "EURUSD", "SETUP-A", "PROPOSAL-A")
        f2 = pool.submit(_claim, "GBPUSD", "SETUP-B", "PROPOSAL-B")
        r1, r2 = f1.result(), f2.result()

    assert r1.success and r2.success
    assert {r1.slot["slot_index"], r2.slot["slot_index"]} == {1, 2}
    assert ledger.consumed_count("S", dt.date(2026, 1, 5)) == 2


def test_ledger_concurrent_third_candidate_blocked(tmp_path):
    """Spec section 16, CASE B: three concurrent claims, capacity 2 -- exactly two
    succeed, the third is blocked."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"), max_slots=2)
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)

    def _claim(symbol, setup_id, proposal_id):
        return ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), symbol, setup_id, proposal_id, now, now)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_claim, sym, f"SETUP-{sym}", f"PROPOSAL-{sym}")
                  for sym in ("EURUSD", "GBPUSD", "USDJPY")]
        results = [f.result() for f in futures]

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) == 2
    assert len(failures) == 1
    assert failures[0].reason_code == REASON_DAILY_TRADE_LIMIT
    assert ledger.consumed_count("S", dt.date(2026, 1, 5)) == 2


def test_ledger_concurrent_same_symbol_one_wins(tmp_path):
    """Spec section 16, CASE C: two concurrent EURUSD setups -- one succeeds, one is
    blocked with the symbol-limit reason."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)

    def _claim(setup_id, proposal_id):
        return ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", setup_id, proposal_id, now, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_claim, "SETUP-A", "PROPOSAL-A")
        f2 = pool.submit(_claim, "SETUP-B", "PROPOSAL-B")
        r1, r2 = f1.result(), f2.result()

    successes = [r for r in (r1, r2) if r.success]
    failures = [r for r in (r1, r2) if not r.success]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].reason_code == REASON_SYMBOL_DAILY_TRADE_LIMIT
    assert ledger.consumed_count("S", dt.date(2026, 1, 5)) == 1


# --------------------------------------------------------------------------- execution eligibility / ownership

def _eligibility(symbol, ledger, open_guard, loss_guard, tmp_path, equity=10_000.0, candidate_risk=50.0):
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    if not ledger.symbol_slot("S", dt.date(2026, 1, 5), symbol):
        ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), symbol, "SETUP-X", "PROPOSAL-X", now, now)
    return evaluate_execution_eligibility("S", dt.date(2026, 1, 5), symbol, "SETUP-X", "PROPOSAL-X",
                                          ledger, open_guard, loss_guard, -1.0,
                                          max_open_positions=2, max_aggregate_open_risk_pct=1.0,
                                          equity=equity, candidate_risk_amount=candidate_risk)


def test_execution_eligibility_zero_open_may_proceed(tmp_path):
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    loss_guard = DailyLossGuard.default("S", str(tmp_path / "loss.json"))
    result = _eligibility("EURUSD", ledger, open_guard, loss_guard, tmp_path)
    assert result.portfolio_state == PORTFOLIO_ELIGIBLE


def test_execution_eligibility_one_open_other_symbol_may_proceed_within_risk_budget(tmp_path):
    """Spec section 15/26: one EURUSD open (0.5% risk) + a GBPUSD candidate (0.5%) may
    still proceed -- max_open_positions=2, aggregate risk 1.0% exactly at the cap."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    open_guard.register_open("POS-1", "S", "EURUSD", risk_amount=50.0)  # 0.5% of 10,000
    loss_guard = DailyLossGuard.default("S", str(tmp_path / "loss.json"))
    result = _eligibility("GBPUSD", ledger, open_guard, loss_guard, tmp_path, candidate_risk=50.0)
    assert result.portfolio_state == PORTFOLIO_ELIGIBLE


def test_execution_eligibility_two_open_blocks_third(tmp_path):
    """Spec section 26: 2 open positions -> BLOCKED_OPEN_POSITION_LIMIT regardless of risk."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    open_guard.register_open("POS-1", "S", "EURUSD", risk_amount=10.0)
    open_guard.register_open("POS-2", "S", "GBPUSD", risk_amount=10.0)
    loss_guard = DailyLossGuard.default("S", str(tmp_path / "loss.json"))
    result = _eligibility("USDJPY", ledger, open_guard, loss_guard, tmp_path, candidate_risk=1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED
    assert result.reason_code == REASON_OPEN_POSITION_LIMIT


def test_execution_eligibility_aggregate_risk_exceeded_blocks(tmp_path):
    """Spec section 26: existing risk 0.65% + candidate 0.5% = 1.15% > 1.0% cap -> blocked."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    open_guard.register_open("POS-1", "S", "EURUSD", risk_amount=65.0)  # 0.65% of 10,000
    loss_guard = DailyLossGuard.default("S", str(tmp_path / "loss.json"))
    result = _eligibility("GBPUSD", ledger, open_guard, loss_guard, tmp_path, candidate_risk=50.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED
    assert result.reason_code == REASON_AGGREGATE_OPEN_RISK


def test_strategy_open_position_count_filters_by_strategy_id(tmp_path):
    """The shared global OpenPositionGuard is never modified -- only a strategy-scoped
    read over the same store, so a position from a DIFFERENT strategy_id doesn't count
    against this pilot's own max_open_positions."""
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    open_guard.register_open("POS-1", "ST_ASIAN_SWEEP_5R_V1", "EURUSD")
    open_guard.register_open("POS-2", "ST_LIQUIDITY_SWEEP_RETEST_V1", "GBPUSD")
    assert strategy_open_position_count(open_guard, "ST_ASIAN_SWEEP_5R_V1") == 1
    assert open_guard.open_count() == 2  # the shared global guard still sees both, unmodified


def test_strategy_open_risk_pct_conservative_initial_risk(tmp_path):
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    open_guard.register_open("POS-1", "ST_ASIAN_SWEEP_5R_V1", "EURUSD", risk_amount=50.0)
    assert strategy_open_risk_pct(open_guard, "ST_ASIAN_SWEEP_5R_V1", 10_000.0) == pytest.approx(0.5)


def test_non_owner_proposal_cannot_reach_execution(tmp_path):
    """Spec section 21/28: a losing/non-selected candidate's proposal must never pass
    ownership validation, regardless of any other gate."""
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))
    now = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    ledger.try_claim("S", "1.1.1", "R", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", now, now)
    result = validate_slot_ownership("S", dt.date(2026, 1, 5), "GBPUSD", "SETUP-B", "PROPOSAL-B", ledger)
    assert result.success is False
    assert result.reason_code == "PROPOSAL_NOT_DAILY_SLOT_OWNER"

    owner_result = validate_slot_ownership("S", dt.date(2026, 1, 5), "EURUSD", "SETUP-A", "PROPOSAL-A", ledger)
    assert owner_result.success is True


# --------------------------------------------------------------------------- persistence / idempotency

def test_save_decision_idempotent_no_duplicate_write(tmp_path):
    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", 1.0995, 1.101, 0.0015,
                     signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)

    assert save_decision(store, decision) is True
    assert save_decision(store, decision) is False  # unchanged re-detection -> no duplicate write

    record = store.get(f"{decision.strategy_id}|{decision.symbol}|{decision.trading_date.isoformat()}|"
                       f"{decision.reference_session}")
    restored = decision_from_record(record)
    assert restored.status == decision.status
    assert restored.evaluation_time == decision.evaluation_time
    assert restored.trading_date == decision.trading_date
    assert restored.ready_at == decision.ready_at


def test_save_proposal_idempotent(strategy, symbol_meta, tmp_path):
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    store = JsonKeyValueStore(str(tmp_path / "proposal.json"))
    assert save_proposal(store, result.proposal) is True
    assert save_proposal(store, result.proposal) is False


# --------------------------------------------------------------------------- execution boundary

def test_no_execution_imports_in_pilot_package():
    """The pilot package must never import execution.executor or execution.mt5_gateway --
    grepping the actual source is a stronger guarantee than mocking, since it proves the
    call path is structurally unreachable, not merely unexercised in this test run."""
    import pathlib
    pkg_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "post_asian_pilot"
    forbidden_imports = (
        "from execution.executor", "from execution import executor",
        "from execution.mt5_gateway", "from execution import mt5_gateway",
        "import execution.executor", "import execution.mt5_gateway",
    )
    for py_file in pkg_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in text, (py_file, forbidden)
        assert "order_check(" not in text, py_file
        assert "order_send(" not in text, py_file


def test_journal_post_asian_pilot_is_gitignored():
    """Spec section 28/44: runtime JSON under journal/post_asian_pilot/ must not become
    staged by normal operation."""
    import subprocess
    result = subprocess.run(["git", "check-ignore", "-q", "journal/post_asian_pilot/decision.json"],
                            capture_output=True)
    assert result.returncode == 0, "journal/post_asian_pilot/ must be covered by .gitignore"


def test_no_env_credential_references_in_pilot_package():
    """Nothing in this package reads .env / os.environ -- MT5 connects via the already
    logged-in desktop terminal (mt5.connection.connect() -> mt5.initialize(), no
    credentials), so no secret can end up in a fingerprint, status doc, or exception
    message from this code."""
    import pathlib
    pkg_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "post_asian_pilot"
    for py_file in pkg_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert ".env" not in text, py_file
        assert "os.environ" not in text, py_file
        assert "getenv" not in text, py_file


# --------------------------------------------------------------------------- release manifest / fingerprints

def test_pilot_config_loads():
    pilot = load_pilot_config()
    assert pilot.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert pilot.universe == ("EURUSD", "GBPUSD")
    assert pilot.risk_per_trade_pct == 0.5
    assert pilot.max_new_trades_per_day == 2
    assert pilot.max_new_trades_per_symbol_per_day == 1
    assert pilot.max_open_positions == 2
    assert pilot.max_aggregate_open_risk_pct == 1.0
    assert pilot.strategy_daily_loss_limit_r == -1.0
    assert pilot.tie_break_priority == ("EURUSD", "GBPUSD")


def test_v1_0_pilot_config_unchanged_and_still_reproducible():
    pilot_v1_0 = load_pilot_config(V1_0_PILOT_CONFIG_PATH)
    assert pilot_v1_0.pilot_id == "AG_POST_ASIAN_LONDON_PILOT_V1"
    assert pilot_v1_0.tie_break_priority == ()  # no priority key in the unchanged V1.0 file
    assert pilot_v1_0.max_new_trades_per_day == 1  # V1.0's own single-slot policy, unchanged
    assert pilot_v1_0.universe == ("EURUSD", "GBPUSD")
    assert pilot_v1_0.risk_per_trade_pct == 0.5


def test_release_fingerprints_deterministic_and_distinct():
    a = release_fingerprints(RELEASE_PATH, STRATEGY_PATH, "config/canonical_sessions.yaml",
                             {"risk_per_trade_pct": 0.5})
    b = release_fingerprints(RELEASE_PATH, STRATEGY_PATH, "config/canonical_sessions.yaml",
                             {"risk_per_trade_pct": 0.5})
    assert a == b
    values = {a["release_fingerprint"], a["strategy_fingerprint"], a["session_fingerprint"],
             a["risk_fingerprint"], a["selection_policy_fingerprint"]}
    assert len(values) == 5  # all distinct


def test_v1_0_1_release_fingerprint_distinct_from_v1_0():
    fp_v1_0 = release_fingerprints(V1_0_RELEASE_CONFIG_PATH, STRATEGY_PATH,
                                   "config/canonical_sessions.yaml", {"risk_per_trade_pct": 0.5})
    fp_v1_0_1 = release_fingerprints(RELEASE_PATH, STRATEGY_PATH, "config/canonical_sessions.yaml",
                                     {"risk_per_trade_pct": 0.5})
    assert fp_v1_0["release_fingerprint"] != fp_v1_0_1["release_fingerprint"]
    # strategy/session fingerprints are identical -- neither strategy nor session config changed
    assert fp_v1_0["strategy_fingerprint"] == fp_v1_0_1["strategy_fingerprint"]
    assert fp_v1_0["session_fingerprint"] == fp_v1_0_1["session_fingerprint"]
    # V1.0 has no selection_policy section at all -- its fingerprint is over an empty policy
    assert fp_v1_0["selection_policy_fingerprint"] != fp_v1_0_1["selection_policy_fingerprint"]


def test_fingerprint_stable_for_same_content():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


# --------------------------------------------------------------------------- preflight

def test_preflight_first_run_establishes_baseline_and_ready(tmp_path, monkeypatch):
    import post_asian_pilot.preflight as preflight_mod
    from mt5.account import Account
    from mt5.symbol_resolver import SymbolMeta as _SM

    monkeypatch.setattr(preflight_mod, "connect", lambda: None)
    monkeypatch.setattr(preflight_mod, "is_connected", lambda: True)
    monkeypatch.setattr(preflight_mod, "fetch_account", lambda: Account(
        login=1, server="Demo", is_demo=True, balance=10_000.0, equity=10_000.0,
        trade_allowed=True, is_hedging_account=False))
    monkeypatch.setattr(preflight_mod, "get_symbol_meta", lambda symbol: _SM(
        symbol=symbol, tick_size=0.00001, tick_value=1.0, contract_size=100000,
        volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5))
    monkeypatch.setattr(preflight_mod, "validate_session_contract", lambda: None)

    class _FakeCoordinator:
        def __init__(self):
            self.open_position_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))

        def reconcile(self, **kw):
            return []

    monkeypatch.setattr(preflight_mod.ExecutionCoordinator, "default", classmethod(lambda cls: _FakeCoordinator()))
    monkeypatch.setattr(preflight_mod, "DailyTradeLedger",
                        type("_L", (), {"default": staticmethod(
                            lambda *a, **kw: DailyTradeLedger.default(str(tmp_path / "ledger.json")))}))

    result = preflight_mod.run_preflight(baseline_path=str(tmp_path / "baseline.json"))
    assert result.pilot_status == "READY_TO_MONITOR"
    assert result.first_block_reason is None
    assert result.account_mode == "DEMO"
    assert any(name == "fingerprint_baseline_established" for name, _ in result.checks)


def test_ready_decision_restart_recovery_preserves_signal(tmp_path):
    """Spec section 5: a persisted READY decision must reload with its authoritative
    signal intact (not None), so the proposal builder still sees READY, not NOT_READY."""
    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    save_decision(store, decision)

    key = f"{decision.strategy_id}|{decision.symbol}|{decision.trading_date.isoformat()}|{decision.reference_session}"
    restored = decision_from_record(store.get(key))
    assert restored.status == STATUS_READY
    assert restored.signal is not None
    assert restored.signal.direction == "SHORT"
    assert restored.signal.entry == 1.10000
    assert restored.signal.stop_loss == 1.10150

    from post_asian_pilot.proposal import build_entry_proposal
    result = build_entry_proposal(restored, load_strategy(STRATEGY_PATH), equity=10_000.0,
                                  symbol_meta=SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0,
                                                         contract_size=100000, volume_min=0.01, volume_max=100.0,
                                                         volume_step=0.01, digits=5),
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "READY"  # proves it does NOT downgrade to NOT_READY after reload
    assert result.proposal.setup_id == build_entry_proposal(
        decision, load_strategy(STRATEGY_PATH), equity=10_000.0,
        symbol_meta=SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                               volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5),
        risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1").proposal.setup_id  # same identity before/after restart


# --------------------------------------------------------------------------- snapshot immutability

def _snapshot_for(tmp_path, high=1.10, trading_date=dt.date(2026, 1, 5)):
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = _m15_candles(start, 24, base=1.09)
    # force a specific high so two calls can differ deterministically
    candles = list(candles)
    candles[0] = Candle(time=candles[0].time, open=candles[0].open, high=high,
                        low=candles[0].low, close=candles[0].close)
    return build_asian_session_snapshot("S", "EURUSD", trading_date, "asian", start,
                                        start + dt.timedelta(hours=6), candles, 24,
                                        as_of=start + dt.timedelta(hours=6)).snapshot


def test_snapshot_same_write_idempotent(tmp_path):
    store = JsonKeyValueStore(str(tmp_path / "snap.json"))
    snap = _snapshot_for(tmp_path)
    assert save_snapshot(store, snap) is True
    assert save_snapshot(store, snap) is False  # identical re-freeze, no mutation, no error


def test_snapshot_conflicting_write_fails_closed(tmp_path):
    store = JsonKeyValueStore(str(tmp_path / "snap.json"))
    snap_a = _snapshot_for(tmp_path, high=1.10)
    snap_b = _snapshot_for(tmp_path, high=1.11)  # same identity, different OHLC
    save_snapshot(store, snap_a)
    with pytest.raises(SnapshotImmutabilityViolation):
        save_snapshot(store, snap_b)
    # the original frozen snapshot is provably untouched
    key = f"S|EURUSD|{snap_a.trading_date.isoformat()}|asian"
    assert store.get(key)["high"] == 1.10


def test_snapshot_corrupt_store_fails_closed(tmp_path):
    path = tmp_path / "snap.json"
    path.write_text("{not valid json", encoding="utf-8")
    from runtime_state.store import StateStoreCorrupted
    store = JsonKeyValueStore(str(path))
    with pytest.raises(StateStoreCorrupted):
        save_snapshot(store, _snapshot_for(tmp_path))


# --------------------------------------------------------------------------- entry ticket / end report

def test_entry_ticket_complete_fields(strategy, symbol_meta):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import release_fingerprints, render_entry_ticket

    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1", swept_level=1.10)

    ledger = DailyTradeLedger.default()  # not used for a real claim here; symbol_slot() -> None is fine
    fps = release_fingerprints("config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml", STRATEGY_PATH,
                               "config/canonical_sessions.yaml", {"risk_per_trade_pct": 0.5})
    ticket = render_entry_ticket(result.proposal, decision, strategy, "AG_TRADE_ASSISTANT_V1_0_2",
                                 fps["release_fingerprint"], fps["strategy_fingerprint"],
                                 ledger, dt.date(2099, 1, 1))  # unused date -> guaranteed empty slot

    assert ticket["application"]["release_fingerprint"] == fps["release_fingerprint"]
    assert ticket["strategy"]["strategy_fingerprint"] == fps["strategy_fingerprint"]
    assert ticket["identity"]["proposal_id"] == result.proposal.proposal_id
    assert ticket["market"]["direction"] == "SHORT"
    assert ticket["session"]["swept_level"] == 1.10
    assert ticket["entry"]["entry"] == 1.10000
    assert ticket["allocation"] == {"tp1_pct": 75, "runner_pct": 25}
    assert ticket["risk"]["raw_volume"] is not None
    assert ticket["risk"]["normalized_volume"] == result.proposal.trade_proposal.volume
    assert ticket["portfolio"]["aggregate_open_risk_pct"] == "UNAVAILABLE_NOT_WIRED"  # honestly not fabricated
    assert ticket["decision"] == "READY"
    assert ticket["execution"]["execution_authorized"] is False


def test_end_report_no_trade_day_uses_journal_evidence(tmp_path, strategy):
    from post_asian_pilot.report import render_pilot_end_report
    from post_asian_pilot.store import PilotStores

    stores = PilotStores.default("ST_ASIAN_SWEEP_5R_V1", state_dir=str(tmp_path))
    pilot = load_pilot_config()  # real V1.0.1 pilot config -- universe (EURUSD, GBPUSD) is what matters here
    trading_date = dt.date(2026, 1, 5)

    for symbol in pilot.universe:
        decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                  pilot.reference_session_name, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC),
                                  "NO_SETUP_BY_WINDOW_END")
        save_decision(stores.decision_store, dataclasses.replace(decision, status="NO_TRADE"))

    report = render_pilot_end_report(pilot, strategy, "AG_TRADE_ASSISTANT_V1_0_3", trading_date, stores)
    assert report["report"] == "AG_TRADE_ASSISTANT_V1_0_3_PILOT_END"
    assert report["result"] == "PASS"
    assert report["portfolio"]["slots_used"] == 0
    for symbol in pilot.universe:
        assert report["pairs"][symbol]["final_strategy_state"] == "NO_TRADE"


def test_end_report_data_error_day_is_pass_with_observations(tmp_path, strategy):
    from post_asian_pilot.report import render_pilot_end_report
    from post_asian_pilot.store import PilotStores

    stores = PilotStores.default("ST_ASIAN_SWEEP_5R_V1", state_dir=str(tmp_path))
    pilot = load_pilot_config()
    trading_date = dt.date(2026, 1, 5)
    stores.counters.increment(strategy.strategy_id, trading_date, "data_errors")

    for symbol in pilot.universe:
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC),
                                       ("DATA_MISSING",))
        save_decision(stores.decision_store, decision)

    report = render_pilot_end_report(pilot, strategy, "AG_TRADE_ASSISTANT_V1_0_3", trading_date, stores)
    assert report["result"] == "PASS_WITH_OBSERVATIONS"

    import post_asian_pilot.preflight as preflight_mod
    bad_release = tmp_path / "bad_release.yaml"
    bad_release.write_text('release_id: "SOME_OTHER_RELEASE"\n', encoding="utf-8")
    result = preflight_mod.run_preflight(release_path=str(bad_release),
                                         baseline_path=str(tmp_path / "baseline.json"))
    assert result.pilot_status == "PILOT_STARTUP_BLOCKED"
    assert result.first_block_reason == "WRONG_RELEASE_LOADED"


# --------------------------------------------------------------------------- find_decision /
# reference_session casing tolerance (AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION)

def test_find_decision_exact_match_fast_path(tmp_path, strategy):
    """A record saved under the pilot config's own reference_session_name (e.g. every
    pre-close WATCH/DATA_ERROR decision, unaffected by this remediation) must still be
    found exactly as before."""
    from post_asian_pilot.store import find_decision

    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    trading_date = dt.date(2026, 1, 5)
    decision = watch_decision(strategy.strategy_id, strategy.version, "EURUSD", trading_date,
                              "asian", dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC),
                              "WAITING_REFERENCE_SESSION_COMPLETION")
    save_decision(store, decision)

    found = find_decision(store, strategy.strategy_id, "EURUSD", trading_date, "asian")
    assert found is not None
    assert found.status == STATUS_WATCH


def test_find_decision_tolerates_strategy_yaml_casing_mismatch(tmp_path, strategy):
    """Reproduces the real AG_V1_0_3_FX_SHADOW_SERIES_002 Day 001 defect: a real
    strategy-engine-produced decision is persisted with reference_session="Asian"
    (strategies/ST_ASIAN_SWEEP_5R_V1.yaml's session_pairs display name), but the pilot
    config's own reference_session_name is "asian" (config/canonical_sessions.yaml).
    find_decision must locate it read-only, without any change to how it was written."""
    from post_asian_pilot.store import find_decision

    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    trading_date = dt.date(2026, 1, 5)
    ready_at = dt.datetime(2026, 1, 5, 7, 45, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    assert decision.reference_session == "Asian"  # confirms the real-world casing this test reproduces
    save_decision(store, decision)

    found = find_decision(store, strategy.strategy_id, "EURUSD", trading_date, "asian")
    assert found is not None
    assert found.status == STATUS_READY
    assert found.ready_at == ready_at


def test_find_decision_no_record_returns_none(tmp_path, strategy):
    from post_asian_pilot.store import find_decision

    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    assert find_decision(store, strategy.strategy_id, "EURUSD", dt.date(2026, 1, 5), "asian") is None


def test_find_decision_tolerates_non_casing_name_mismatch(tmp_path, strategy):
    """LONDON_NEWYORK's real defect variant: the pilot config's reference_session_name
    is "london_am" (config/canonical_sessions.yaml) but strategies/ST_ASIAN_SWEEP_5R_V1.yaml's
    session_pairs entry for that pair is just "London" -- not a casing difference at
    all ("london" != "london_am"), so a case-insensitive-equality fallback would still
    miss this. find_decision must fall back to (strategy_id, symbol, trading_date)
    alone and find it anyway."""
    from post_asian_pilot.store import find_decision

    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    trading_date = dt.date(2026, 1, 5)
    decision = data_error_decision(strategy.strategy_id, strategy.version, "EURUSD", trading_date,
                                   "London", dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC), ("DATA_MISSING",))
    save_decision(store, decision)

    found = find_decision(store, strategy.strategy_id, "EURUSD", trading_date, "london_am")
    assert found is not None
    assert found.status == STATUS_DATA_ERROR


def test_find_decision_prefers_latest_when_ambiguous(tmp_path, strategy):
    """A stale pre-close WATCH (lowercase key) and a later real evaluation (strategy-YAML-
    cased key) can legitimately coexist as two distinct dict entries under the same
    (strategy_id, symbol, trading_date) prefix. The most recently evaluated one --
    the terminal, authoritative state -- must win."""
    from post_asian_pilot.store import find_decision

    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    trading_date = dt.date(2026, 1, 5)
    stale = watch_decision(strategy.strategy_id, strategy.version, "EURUSD", trading_date,
                           "asian", dt.datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
                           "WAITING_REFERENCE_SESSION_COMPLETION")
    save_decision(store, stale)

    ready_at = dt.datetime(2026, 1, 5, 7, 45, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at)
    real = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC))
    save_decision(store, real)

    found = find_decision(store, strategy.strategy_id, "EURUSD", trading_date, "asian")
    assert found is not None
    assert found.status == STATUS_READY  # the real, terminal decision -- not the stale WATCH


def test_end_report_surfaces_ready_decision_despite_casing_mismatch(tmp_path, strategy, symbol_meta):
    """End-to-end reproduction of the Day 001 defect through render_pilot_end_report
    itself: previously this returned final_strategy_state="NO_RECORD" for a symbol with
    a real, legitimately-claimed READY proposal."""
    from post_asian_pilot.report import render_pilot_end_report
    from post_asian_pilot.store import PilotStores

    stores = PilotStores.default("ST_ASIAN_SWEEP_5R_V1", state_dir=str(tmp_path))
    pilot = load_pilot_config()
    trading_date = dt.date(2026, 1, 5)
    ready_at = dt.datetime(2026, 1, 5, 7, 45, tzinfo=UTC)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)

    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at, symbol="EURUSD")
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    save_decision(stores.decision_store, decision)

    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1", swept_level=1.10)
    stores.ledger.try_claim(strategy.strategy_id, strategy.version, "AG_TRADE_ASSISTANT_V1_0_3", trading_date,
                            "EURUSD", result.proposal.setup_id, result.proposal.proposal_id, ready_at, ready_at)

    report = render_pilot_end_report(pilot, strategy, "AG_TRADE_ASSISTANT_V1_0_3", trading_date, stores)
    assert report["pairs"]["EURUSD"]["final_strategy_state"] == STATUS_READY  # was NO_RECORD before the fix
    assert report["pairs"]["EURUSD"]["proposal_id"] == result.proposal.proposal_id
    assert report["pairs"]["GBPUSD"]["final_strategy_state"] == "NO_RECORD"  # genuinely no record -- unaffected


# --------------------------------------------------------------------------- Entry Ticket
# per-cycle operational wiring (AG_TRADE_ASSISTANT_V1_0_3_FX_COMPLETE_ENTRY_TICKET_WIRING)

def _pair_result_for(strategy, symbol_meta, status, symbol="EURUSD", trading_date=dt.date(2026, 1, 5)):
    """Builds a single PairResult the way run_pilot_cycle would, for each decision
    family the wiring must handle. READY includes a real, persisted-style proposal
    (same build_entry_proposal() call already used by test_entry_ticket_complete_fields)."""
    from post_asian_pilot.pipeline import PairResult

    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    if status == STATUS_READY:
        ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                         stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at, symbol=symbol)
        decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
        result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                      risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1", swept_level=1.10)
        return PairResult(symbol, decision, "SELECTED", None, result.proposal)
    if status == STATUS_DATA_ERROR:
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       "asian", dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), ("DATA_MISSING",))
        return PairResult(symbol, decision, "ELIGIBLE", None, None)
    if status == STATUS_EXPIRED:
        signal = _signal("NO_TRADE", "NONE", "NO_SETUP_BY_WINDOW_END", symbol=symbol)
        decision = map_trade_signal_to_decision(signal, "SNAP-1", window_end, window_end)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)
    if status == STATUS_NO_TRADE:
        signal = _signal("NO_TRADE", "TREND", "TREND_NOT_SWEEP", symbol=symbol)
        decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
                                                window_end)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)
    assert status == STATUS_WATCH
    decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date, "asian",
                              dt.datetime(2026, 1, 5, 2, 0, tzinfo=UTC), "WAITING_REFERENCE_SESSION_COMPLETION")
    return PairResult(symbol, decision, "ELIGIBLE", None, None)


def _cycle_result_for(pilot, strategy, *pair_results, trading_date=dt.date(2026, 1, 5)):
    from post_asian_pilot.pipeline import PilotCycleResult
    return PilotCycleResult(
        pilot_config=pilot, strategy=strategy, release_id="AG_TRADE_ASSISTANT_V1_0_3",
        evaluation_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), trading_date=trading_date,
        pairs=tuple(pair_results), ledger_slots_used=len(pair_results), ledger_max_slots=2,
    )


@pytest.fixture()
def ticket_fingerprints():
    from post_asian_pilot.report import release_fingerprints
    return release_fingerprints("config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml", STRATEGY_PATH,
                               "config/canonical_sessions.yaml", {"risk_per_trade_pct": 0.5})


def test_ready_json_contains_matching_entry_ticket(tmp_path, strategy, symbol_meta, ticket_fingerprints):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import ENTRY_TICKET_RENDERED, cycle_to_dict

    pilot = load_pilot_config()
    pr = _pair_result_for(strategy, symbol_meta, STATUS_READY, "EURUSD")
    result = _cycle_result_for(pilot, strategy, pr)
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))

    payload = cycle_to_dict(result, ledger, ticket_fingerprints["release_fingerprint"],
                            ticket_fingerprints["strategy_fingerprint"])
    entry = payload["pairs"][0]
    assert entry["entry_ticket_status"] == ENTRY_TICKET_RENDERED
    assert entry["entry_ticket_error"] is None
    ticket = entry["entry_ticket"]
    assert ticket is not None
    tp = pr.proposal.trade_proposal
    assert ticket["entry"]["entry"] == tp.entry == entry["proposal"]["entry"]
    assert ticket["entry"]["stop_loss"] == tp.stop_loss == entry["proposal"]["stop_loss"]
    assert ticket["identity"]["proposal_id"] == pr.proposal.proposal_id == entry["proposal"]["proposal_id"]
    assert ticket["decision"] == "READY"
    assert ticket["execution"]["execution_authorized"] is False


def test_ready_json_without_ticket_context_omits_entry_ticket_fields(strategy, symbol_meta):
    """Backward compatibility: no ledger/fingerprints supplied -> byte-identical to the
    pre-wiring schema, no entry_ticket* keys at all."""
    from post_asian_pilot.report import cycle_to_dict

    pilot = load_pilot_config()
    pr = _pair_result_for(strategy, symbol_meta, STATUS_READY, "EURUSD")
    result = _cycle_result_for(pilot, strategy, pr)

    payload = cycle_to_dict(result)
    entry = payload["pairs"][0]
    assert "entry_ticket" not in entry
    assert "entry_ticket_status" not in entry
    assert "entry_ticket_error" not in entry


def test_entry_ticket_render_error_never_changes_decision_or_proposal(
    tmp_path, strategy, symbol_meta, ticket_fingerprints, monkeypatch,
):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import ENTRY_TICKET_RENDER_ERROR
    import post_asian_pilot.report as report_mod

    def _boom(*a, **kw):
        raise RuntimeError("simulated renderer failure")
    monkeypatch.setattr(report_mod, "render_entry_ticket", _boom)

    pilot = load_pilot_config()
    pr = _pair_result_for(strategy, symbol_meta, STATUS_READY, "EURUSD")
    result = _cycle_result_for(pilot, strategy, pr)
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))

    payload = report_mod.cycle_to_dict(result, ledger, ticket_fingerprints["release_fingerprint"],
                                       ticket_fingerprints["strategy_fingerprint"])
    entry = payload["pairs"][0]
    assert entry["strategy_state"] == STATUS_READY  # decision itself unaffected
    assert entry["proposal"]["proposal_id"] == pr.proposal.proposal_id  # proposal unaffected
    assert entry["entry_ticket"] is None
    assert entry["entry_ticket_status"] == ENTRY_TICKET_RENDER_ERROR
    assert entry["entry_ticket_error"] == "ENTRY_TICKET_RENDER_FAILED:RuntimeError"
    assert "simulated" not in entry["entry_ticket_error"]  # safe reason code, not the raw exception text


@pytest.mark.parametrize("status", [STATUS_WATCH, STATUS_NO_TRADE, STATUS_DATA_ERROR, STATUS_EXPIRED])
def test_non_ready_states_never_get_a_fabricated_entry_ticket(
    tmp_path, strategy, symbol_meta, ticket_fingerprints, status,
):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import ENTRY_TICKET_NOT_APPLICABLE, cycle_to_dict

    pilot = load_pilot_config()
    pr = _pair_result_for(strategy, symbol_meta, status, "EURUSD")
    result = _cycle_result_for(pilot, strategy, pr)
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))

    payload = cycle_to_dict(result, ledger, ticket_fingerprints["release_fingerprint"],
                            ticket_fingerprints["strategy_fingerprint"])
    entry = payload["pairs"][0]
    assert entry["strategy_state"] == status
    assert entry["entry_ticket"] is None
    assert entry["entry_ticket_status"] == ENTRY_TICKET_NOT_APPLICABLE
    assert entry["entry_ticket_error"] is None


def test_entry_ticket_wiring_works_for_london_newyork_pilot_and_gbpusd(
    tmp_path, strategy, symbol_meta, ticket_fingerprints,
):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import ENTRY_TICKET_RENDERED, cycle_to_dict

    pilot = load_pilot_config("config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml")
    pr = _pair_result_for(strategy, symbol_meta, STATUS_READY, "GBPUSD")
    result = _cycle_result_for(pilot, strategy, pr)
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))

    payload = cycle_to_dict(result, ledger, ticket_fingerprints["release_fingerprint"],
                            ticket_fingerprints["strategy_fingerprint"])
    entry = payload["pairs"][0]
    assert entry["symbol"] == "GBPUSD"
    assert entry["entry_ticket_status"] == ENTRY_TICKET_RENDERED
    assert entry["entry_ticket"]["market"]["direction"] == "SHORT"


def test_human_output_ready_shows_entry_ticket_section_without_implying_execution(
    tmp_path, strategy, symbol_meta, ticket_fingerprints,
):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import human_readable_report

    pilot = load_pilot_config()
    pr = _pair_result_for(strategy, symbol_meta, STATUS_READY, "EURUSD")
    result = _cycle_result_for(pilot, strategy, pr)
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))

    text = human_readable_report(result, ledger, ticket_fingerprints["release_fingerprint"],
                                 ticket_fingerprints["strategy_fingerprint"])
    assert "ENTRY TICKET" in text
    assert "execution disabled" in text
    assert "order sent" not in text.lower()
    assert "order_send" not in text
    assert "MT5 ticket" not in text


@pytest.mark.parametrize("status", [STATUS_WATCH, STATUS_NO_TRADE, STATUS_DATA_ERROR])
def test_human_output_non_ready_has_no_entry_ticket_section(
    tmp_path, strategy, symbol_meta, ticket_fingerprints, status,
):
    from post_asian_pilot.governor import DailyTradeLedger
    from post_asian_pilot.report import human_readable_report

    pilot = load_pilot_config()
    pr = _pair_result_for(strategy, symbol_meta, status, "EURUSD")
    result = _cycle_result_for(pilot, strategy, pr)
    ledger = DailyTradeLedger.default(str(tmp_path / "ledger.json"))

    text = human_readable_report(result, ledger, ticket_fingerprints["release_fingerprint"],
                                 ticket_fingerprints["strategy_fingerprint"])
    assert "ENTRY TICKET" not in text


def test_canonical_daily_report_schema_unchanged_by_entry_ticket_wiring(tmp_path, strategy):
    """AG_FX_DAILY_REPORT_V1 (render_pilot_end_report / daily_fx_report.py) must never
    gain an entry_ticket field -- that schema is explicitly out of scope for this wiring."""
    from post_asian_pilot.report import render_pilot_end_report
    from post_asian_pilot.store import PilotStores

    stores = PilotStores.default("ST_ASIAN_SWEEP_5R_V1", state_dir=str(tmp_path))
    pilot = load_pilot_config()
    trading_date = dt.date(2026, 1, 5)
    for symbol in pilot.universe:
        decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                  pilot.reference_session_name, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC),
                                  "NO_SETUP_BY_WINDOW_END")
        save_decision(stores.decision_store, dataclasses.replace(decision, status="NO_TRADE"))

    report = render_pilot_end_report(pilot, strategy, "AG_TRADE_ASSISTANT_V1_0_3", trading_date, stores)
    import json as _json
    serialized = _json.dumps(report, default=str)
    assert "entry_ticket" not in serialized
    for symbol in pilot.universe:
        assert "entry_ticket" not in report["pairs"][symbol]


def test_entry_ticket_wiring_source_never_references_execution_send_path():
    import post_asian_pilot.report as report_mod

    assert not hasattr(report_mod, "order_send")
    assert not any(name.startswith("execution") for name in vars(report_mod))


# --------------------------------------------------------------------------- determinism
# (AG_EGSVF_V1_CROSS_STRATEGY_DETERMINISM_EVIDENCE_RECONCILIATION)
#
# Exercises the actual canonical FX semantic pipeline boundary: fixed session/post-session
# candles -> strategy_engine.engine.evaluate() (the same public entry point
# post_asian_pilot.pipeline._evaluate_pair calls) -> TradeSignal -> map_trade_signal_to_
# decision() -> PostAsianDecision. Both functions are pure (no MT5, no wall-clock, no
# randomness) given explicit candles/timestamps -- this is not a new determinism
# framework, just the smallest fixed fixture needed to drive them twice and compare.
# The candle geometry is the same shape as tests/test_session_router.py's
# test_range_with_sweep_routes_to_entry_2 (a real SHORT sweep-and-reject), reused here
# rather than re-derived, translated onto ST_ASIAN_SWEEP_5R_V1's real ASIAN_LONDON pair.


def _fx_determinism_fixture_candles():
    session_date = dt.date(2026, 1, 5)
    session_candles = [
        Candle(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(dt.datetime(2026, 1, 5, 0, 15, tzinfo=UTC), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    session_high = 1.1050
    sweep_candle = Candle(
        dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC), 1.1005, session_high + 0.0010, 1.1000, session_high - 0.0002
    )
    return session_date, session_candles, [sweep_candle]


def _run_fx_pipeline_once(strategy):
    from strategy_engine.engine import evaluate as evaluate_strategy

    session_date, session_candles, post_session_candles = _fx_determinism_fixture_candles()
    signal = evaluate_strategy(
        strategy, "ASIAN_LONDON", "EURUSD", session_date, session_candles, 2, post_session_candles
    )
    decision = map_trade_signal_to_decision(
        signal,
        session_snapshot_id="DETERMINISM-TEST-SNAPSHOT",
        evaluation_time=dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC),
        window_end_utc=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC),
    )
    return signal, decision


def test_fx_full_pipeline_is_deterministic_for_fixed_fixture(strategy):
    """Same fixed candles + same strategy config + same injected evaluation/window
    timestamps must yield byte-identical TradeSignal and PostAsianDecision across
    repeated calls -- the real semantic pipeline boundary, not just one helper."""
    session_date, session_candles, post_session_candles = _fx_determinism_fixture_candles()
    before = (tuple(session_candles), tuple(post_session_candles))

    runs = [_run_fx_pipeline_once(strategy) for _ in range(3)]

    signal_1, decision_1 = runs[0]
    assert signal_1.status == "SIGNAL"
    assert signal_1.setup == "SWEEP"
    assert signal_1.direction == "SHORT"
    assert decision_1.status == STATUS_READY

    for signal, decision in runs[1:]:
        assert signal == signal_1
        assert decision == decision_1

    # Fixture candles must not have been mutated by any run.
    after = _fx_determinism_fixture_candles()
    assert before == (tuple(after[1]), tuple(after[2]))


def test_fx_pipeline_changed_input_changes_output(strategy):
    """Control test: this fixture is not vacuously deterministic -- a materially
    different sweep candle (no breach of the session high) must yield a different
    semantic outcome (no SIGNAL), proving the equality assertions above are meaningful."""
    session_date, session_candles, _ = _fx_determinism_fixture_candles()
    from strategy_engine.engine import evaluate as evaluate_strategy

    boring_candle = Candle(dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC), 1.1005, 1.1006, 1.1004, 1.1005)
    signal = evaluate_strategy(strategy, "ASIAN_LONDON", "EURUSD", session_date, session_candles, 2, [boring_candle])
    assert signal.status == "NO_TRADE"
