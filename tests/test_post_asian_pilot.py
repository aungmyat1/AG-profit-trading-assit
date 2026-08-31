"""Focused tests for AG_POST_ASIAN_LONDON_PILOT_V1: session snapshot validation, decision
normalization, risk-sized proposal construction, daily governor, simultaneous-READY
tie-break, persistence idempotency, execution-boundary (zero order_check/order_send), and
release-manifest fingerprints. Uses tmp_path-backed JsonKeyValueStore files throughout --
never touches the real journal/ directory.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from execution.adapter import TradeProposal
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
    map_trade_signal_to_decision,
)
from post_asian_pilot.fingerprint import fingerprint
from post_asian_pilot.governor import (
    PORTFOLIO_BLOCKED,
    PORTFOLIO_ELIGIBLE,
    REASON_DAILY_TRADE_LIMIT,
    REASON_MAX_OPEN_POSITIONS,
    REASON_STRATEGY_DAILY_LOSS_LOCK,
    DailyTradeSlot,
    evaluate_daily_governor,
)
from post_asian_pilot.pilot_config import load_pilot_config, load_raw_yaml
from post_asian_pilot.proposal import build_entry_proposal
from post_asian_pilot.report import release_fingerprints
from post_asian_pilot.snapshot import build_asian_session_snapshot, validate_candle_array
from post_asian_pilot.store import decision_from_record, save_decision, save_proposal, save_snapshot
from post_asian_pilot.tiebreak import RESULT_CLAIMED, RESULT_UNRESOLVED, resolve_tiebreak
from strategy_engine.session import Candle

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


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


# --------------------------------------------------------------------------- decision mapping

def _signal(status, setup, reason_code, direction=None, entry=None, stop_loss=None, risk_distance=None):
    return TradeSignal(
        signal_id="SID", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="EURUSD",
        pair_id="ASIAN_LONDON", reference_session="Asian", session_date=dt.date(2026, 1, 5),
        box_high=1.10, box_low=1.09, box_mid=1.095, regime="RANGE", setup=setup, status=status,
        reason_code=reason_code, direction=direction, entry=entry, stop_loss=stop_loss, risk_distance=risk_distance,
    )


def test_decision_sweep_signal_is_ready():
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", 1.0995, 1.101, 0.0015)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    assert decision.status == STATUS_READY


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

def test_build_entry_proposal_ready_geometry_and_risk(strategy, symbol_meta):
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    assert decision.status == STATUS_READY

    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "READY"
    tp = result.proposal.trade_proposal
    assert tp.entry == 1.10000
    assert tp.stop_loss == 1.10150
    # SHORT: TP1 = box_low (opposing boundary), TP2 = entry - 5R
    assert tp.tp1 == pytest.approx(1.09)
    assert tp.tp2 == pytest.approx(1.10000 - 5 * 0.00150)
    assert tp.risk_percent == 0.5
    # risk_budget = 10000 * 0.005 = 50; never exceeds it
    assert tp.risk_amount <= 50.0 + 1e-6
    assert result.proposal.execution_authorized is False
    assert result.proposal.user_confirmation_required is True
    assert result.proposal.execution_status == "CONFIRMATION_REQUIRED"


def test_build_entry_proposal_min_volume_exceeds_budget_blocked(strategy):
    tiny_meta = SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                           volume_min=100.0, volume_max=200.0, volume_step=0.01, digits=5)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=tiny_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "BLOCKED"
    assert result.reason_code == "VOLUME_BELOW_MIN"


# --------------------------------------------------------------------------- daily governor

def test_governor_max_open_positions_blocks(tmp_path):
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    open_guard.register_open("POS-1", "ST_ASIAN_SWEEP_5R_V1", "EURUSD")
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    slot = DailyTradeSlot.default(str(tmp_path / "slot.json"))
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), "GBPUSD",
                                     open_guard, loss_guard, slot, -1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED
    assert result.reason_code == REASON_MAX_OPEN_POSITIONS


def test_governor_strategy_minus_1r_lock_blocks(tmp_path):
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    loss_guard.record_trade_result(dt.date(2026, 1, 5), -1.0)
    slot = DailyTradeSlot.default(str(tmp_path / "slot.json"))
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), "EURUSD",
                                     open_guard, loss_guard, slot, -1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED
    assert result.reason_code == REASON_STRATEGY_DAILY_LOSS_LOCK


def test_governor_project_minus_2r_guard_unmodified(tmp_path):
    """The project-wide -2R guard still fires independently of the pilot's -1R lock,
    and is never weakened by this pilot's own gate."""
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    loss_guard.record_trade_result(dt.date(2026, 1, 5), -2.0)
    assert loss_guard.is_blocked(dt.date(2026, 1, 5))  # still -2.0 project circuit, untouched
    slot = DailyTradeSlot.default(str(tmp_path / "slot.json"))
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), "EURUSD",
                                     open_guard, loss_guard, slot, -1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED


def test_governor_daily_trade_limit_blocks_second_symbol(tmp_path):
    open_guard = OpenPositionGuard.default(str(tmp_path / "open.json"))
    loss_guard = DailyLossGuard.default("ST_ASIAN_SWEEP_5R_V1", str(tmp_path / "loss.json"))
    slot = DailyTradeSlot.default(str(tmp_path / "slot.json"))
    slot.claim("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), "EURUSD", "SETUP-1",
              dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    result = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), "GBPUSD",
                                     open_guard, loss_guard, slot, -1.0)
    assert result.portfolio_state == PORTFOLIO_BLOCKED
    assert result.reason_code == REASON_DAILY_TRADE_LIMIT

    # the claiming symbol itself remains eligible (idempotent re-check, not a second claim)
    same = evaluate_daily_governor("ST_ASIAN_SWEEP_5R_V1", dt.date(2026, 1, 5), "EURUSD",
                                   open_guard, loss_guard, slot, -1.0)
    assert same.portfolio_state == PORTFOLIO_ELIGIBLE


# --------------------------------------------------------------------------- tie-break

def _ready_decision(symbol, evaluation_time):
    signal = TradeSignal(signal_id="SID", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
                         symbol=symbol, pair_id="ASIAN_LONDON", reference_session="Asian",
                         session_date=dt.date(2026, 1, 5), box_high=1.10, box_low=1.09, box_mid=1.095,
                         regime="RANGE", setup="SWEEP", status="SIGNAL",
                         reason_code="UPPER_SWEEP_STRICT_PENETRATION", direction="SHORT", entry=1.0995,
                         stop_loss=1.101, risk_distance=0.0015)
    return map_trade_signal_to_decision(signal, "SNAP", evaluation_time, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC))


def test_tiebreak_same_timestamp_unresolved():
    t = dt.datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    result = resolve_tiebreak([_ready_decision("EURUSD", t), _ready_decision("GBPUSD", t)])
    assert result.status == RESULT_UNRESOLVED
    assert result.claimed_symbol is None


def test_tiebreak_different_timestamp_earliest_claims():
    t1 = dt.datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    t2 = dt.datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
    result = resolve_tiebreak([_ready_decision("GBPUSD", t2), _ready_decision("EURUSD", t1)])
    assert result.status == RESULT_CLAIMED
    assert result.claimed_symbol == "EURUSD"


def test_tiebreak_no_candidates():
    result = resolve_tiebreak([])
    assert result.claimed_symbol is None


# --------------------------------------------------------------------------- persistence / idempotency

def test_save_decision_idempotent_no_duplicate_write(tmp_path):
    store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", 1.0995, 1.101, 0.0015)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)

    assert save_decision(store, decision) is True
    assert save_decision(store, decision) is False  # unchanged re-detection -> no duplicate write

    record = store.get(f"{decision.strategy_id}|{decision.symbol}|{decision.trading_date.isoformat()}|"
                       f"{decision.reference_session}")
    restored = decision_from_record(record)
    assert restored.status == decision.status
    assert restored.evaluation_time == decision.evaluation_time
    assert restored.trading_date == decision.trading_date


def test_save_proposal_idempotent(strategy, symbol_meta, tmp_path):
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
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


# --------------------------------------------------------------------------- release manifest / fingerprints

def test_pilot_config_loads():
    pilot = load_pilot_config()
    assert pilot.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert pilot.universe == ("EURUSD", "GBPUSD")
    assert pilot.risk_per_trade_pct == 0.5
    assert pilot.max_new_trades_per_day == 1
    assert pilot.max_open_positions == 1
    assert pilot.strategy_daily_loss_limit_r == -1.0


def test_release_fingerprints_deterministic():
    a = release_fingerprints("config/releases/AG_TRADE_ASSISTANT_V1_0.yaml", STRATEGY_PATH,
                             "config/canonical_sessions.yaml", {"risk_per_trade_pct": 0.5})
    b = release_fingerprints("config/releases/AG_TRADE_ASSISTANT_V1_0.yaml", STRATEGY_PATH,
                             "config/canonical_sessions.yaml", {"risk_per_trade_pct": 0.5})
    assert a == b
    assert len({a["release_fingerprint"], a["strategy_fingerprint"], a["session_fingerprint"],
               a["risk_fingerprint"]}) == 4  # all distinct


def test_fingerprint_stable_for_same_content():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
