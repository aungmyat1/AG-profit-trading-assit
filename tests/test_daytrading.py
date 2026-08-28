"""Focused tests for the daytrading package: NARRATIVE_BIAS, LIQUIDITY_AFFINITY,
LTF_EXECUTION, RISK_MANAGEMENT, and the pipeline's derive_trade_state() (spec sections
15-20). Pure/offline -- no MT5 connection, no candle fetch."""
from __future__ import annotations

from datetime import datetime, timezone

from daytrading.liquidity_affinity import evaluate_liquidity_affinity
from daytrading.ltf_execution import evaluate_ltf_execution
from daytrading.models import (
    AFFINITY_PARTIAL,
    AFFINITY_RESOLVED,
    AFFINITY_UNRESOLVED,
    BIAS_BALANCED,
    BIAS_BEARISH,
    BIAS_BULLISH,
    BIAS_TRANSITION,
    BIAS_UNRESOLVED,
    LTF_CONFIRMED,
    LTF_DORMANT,
    LTF_NOT_CONFIRMED,
    LTF_WAITING,
    NarrativeBiasResult,
    RISK_FAIL,
    RISK_PASS,
    RISK_UNRESOLVED,
    STATE_INVALIDATED,
    STATE_NO_TRADE,
    STATE_TRADE_READY_LONG,
    STATE_WAIT_AFFINITY,
    STATE_WAIT_LTF_EXECUTION,
    STATE_WAIT_RISK,
)
from daytrading.narrative_bias import evaluate_narrative_bias
from daytrading.pipeline import derive_trade_state
from daytrading.risk_management import evaluate_risk_management
from entry_confirmation import CandidateDirection
from liquidity.models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED, StructureResult
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle
from supply_demand.native_zones import dealing_range_zones
from trade_management.models import TradeManagementRequest

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _structure(state, status="VALID") -> StructureResult:
    return StructureResult(symbol="EURUSD", timeframe="D1", status=status, reason_codes=(), state=state)


def _level(side, price, status=LiquidityStatus.UNSWEPT) -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe="D1", side=side, source="SWING", price=price,
                           origin_time=NOW, status=status)


def _liquidity(nearest_buy=None, nearest_sell=None, status="LIQUIDITY_OK") -> LiquidityResult:
    levels = tuple(l for l in (nearest_buy, nearest_sell) if l is not None)
    return LiquidityResult(symbol="EURUSD", timeframe="D1", status=status, levels=levels,
                            nearest_buy_side=nearest_buy, nearest_sell_side=nearest_sell)


def _meta(**overrides) -> SymbolMeta:
    defaults = dict(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                     volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=0.00001)
    defaults.update(overrides)
    return SymbolMeta(**defaults)


# =========================================================================== NARRATIVE_BIAS (see also
# tests/test_narrative_bias.py for the full DAYTRADING_NARRATIVE_BIAS_V1 profile/causality/true-day suite --
# these keep exercising evaluate_narrative_bias() through the DAYTRADING_BASIC_SKILLS_V1 `bias` field that
# liquidity_affinity/ltf_execution/pipeline consume, now derived from expected_profile.)

_H1_UP = [Candle(time=datetime(2026, 1, 1, 5, tzinfo=timezone.utc), open=1.1000, high=1.1050, low=1.1000,
                  close=1.1000),
          Candle(time=datetime(2026, 1, 1, 9, tzinfo=timezone.utc), open=1.1000, high=1.1050, low=1.1000,
                  close=1.1050)]
_H1_DOWN = [Candle(time=datetime(2026, 1, 1, 5, tzinfo=timezone.utc), open=1.1900, high=1.1900, low=1.1600,
                    close=1.1900),
            Candle(time=datetime(2026, 1, 1, 9, tzinfo=timezone.utc), open=1.1900, high=1.1900, low=1.1600,
                    close=1.1600)]
_EVAL_TIME = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)  # 05:00 NY, same trading_date as the H1 candles above


def test_narrative_bias_clear_bullish():
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900))
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_BULLISH), liq,
                                      evaluation_time=_EVAL_TIME, h1_candles=_H1_UP)
    assert result.bias == BIAS_BULLISH
    assert result.primary_draw == "BUY_SIDE"
    assert result.major_target == 1.1900


def test_narrative_bias_clear_bearish():
    liq = _liquidity(nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1600))
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_BEARISH), liq,
                                      evaluation_time=_EVAL_TIME, h1_candles=_H1_DOWN)
    assert result.bias == BIAS_BEARISH
    assert result.primary_draw == "SELL_SIDE"


def test_narrative_bias_balanced_range():
    dr = dealing_range_zones("EURUSD", 1.1700, 1.1900, source="previous_day", current_price=1.1800)
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_UNDEFINED), _liquidity(), dr)
    assert result.bias == BIAS_BALANCED


def test_narrative_bias_draw_already_reached_is_unresolved_not_flipped():
    # Prior draw satisfied -- narrative must not keep asserting continuation past it, and must not
    # be silently forced into a directional profile either (fail closed, spec section 22/26).
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900, status=LiquidityStatus.CONSUMED))
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_BULLISH), liq)
    assert result.bias == BIAS_UNRESOLVED


def test_narrative_bias_conflicting_evidence_recorded_not_flipped():
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900),
                      nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1600))  # opposite side still unswept
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_BULLISH), liq,
                                      evaluation_time=_EVAL_TIME, h1_candles=_H1_UP)
    assert result.bias == BIAS_BULLISH  # structure remains authoritative
    assert result.contradictory_evidence  # but the conflict is recorded, not hidden


def test_narrative_bias_insufficient_data_is_unresolved_not_forced():
    result = evaluate_narrative_bias("EURUSD", "D1", None, None)
    assert result.bias == BIAS_UNRESOLVED
    assert result.status == "INSUFFICIENT_DATA"


# =========================================================================== LIQUIDITY_AFFINITY (section 17)

def test_liquidity_affinity_clear_buy_side_draw():
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900),
                      nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1750))
    result = evaluate_liquidity_affinity("EURUSD", narrative, liq)
    assert result.status == AFFINITY_RESOLVED
    assert result.primary_draw == "BUY_SIDE"
    assert result.target_side_liquidity == "BUY_SIDE"
    assert result.entry_side_liquidity == "SELL_SIDE"


def test_liquidity_affinity_clear_sell_side_draw():
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BEARISH, status="OK")
    liq = _liquidity(nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1600),
                      nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1750))
    result = evaluate_liquidity_affinity("EURUSD", narrative, liq)
    assert result.status == AFFINITY_RESOLVED
    assert result.target_side_liquidity == "SELL_SIDE"
    assert result.entry_side_liquidity == "BUY_SIDE"


def test_liquidity_affinity_partial_without_entry_side():
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900))  # no sell-side level at all
    result = evaluate_liquidity_affinity("EURUSD", narrative, liq)
    assert result.status == AFFINITY_PARTIAL


def test_liquidity_affinity_already_consumed_is_unresolved():
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900, status=LiquidityStatus.CONSUMED))
    result = evaluate_liquidity_affinity("EURUSD", narrative, liq)
    assert result.status == AFFINITY_UNRESOLVED


def test_liquidity_affinity_insufficient_evidence():
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_UNRESOLVED, status="OK")
    result = evaluate_liquidity_affinity("EURUSD", narrative, None)
    assert result.status == AFFINITY_UNRESOLVED


def test_liquidity_detection_differs_from_liquidity_affinity_labels():
    # SMC liquidity result uses BUY_SIDE/SELL_SIDE levels; DayTrading affinity relabels
    # the SAME levels as PRIMARY_DRAW/ENTRY_SIDE/TARGET_SIDE -- never collapsed together.
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900),
                      nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1750))
    result = evaluate_liquidity_affinity("EURUSD", narrative, liq)
    assert result.primary_draw == "BUY_SIDE"
    assert not hasattr(result, "nearest_buy_side")  # not a re-export of LiquidityResult's own shape


# =========================================================================== LTF_EXECUTION (section 18)

def _bullish_narrative():
    return NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")


def _resolved_affinity():
    narrative = _bullish_narrative()
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.1900),
                      nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1750))
    return evaluate_liquidity_affinity("EURUSD", narrative, liq)


def test_ltf_execution_valid_context_no_confirmation_data_is_waiting():
    result = evaluate_ltf_execution("EURUSD", "M5", _bullish_narrative(), _resolved_affinity(),
                                     CandidateDirection.LONG, ec_request=None)
    assert result.status == LTF_WAITING
    assert result.context_valid is True


def test_ltf_execution_no_narrative_stays_dormant():
    unresolved = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_UNRESOLVED, status="OK")
    affinity = evaluate_liquidity_affinity("EURUSD", unresolved, None)
    result = evaluate_ltf_execution("EURUSD", "M5", unresolved, affinity, CandidateDirection.LONG, ec_request=None)
    assert result.status == LTF_DORMANT


def test_ltf_execution_no_affinity_stays_dormant():
    narrative = _bullish_narrative()
    unresolved_affinity = evaluate_liquidity_affinity("EURUSD", narrative, None)
    result = evaluate_ltf_execution("EURUSD", "M5", narrative, unresolved_affinity, CandidateDirection.LONG, ec_request=None)
    assert result.status == LTF_DORMANT


def test_ltf_execution_mismatched_candidate_direction_is_waiting():
    result = evaluate_ltf_execution("EURUSD", "M5", _bullish_narrative(), _resolved_affinity(),
                                     CandidateDirection.SHORT, ec_request=None)
    assert result.status == LTF_WAITING


def test_ltf_execution_a_ltf_signal_alone_cannot_create_a_trade():
    # No ec_request supplied at all (i.e. nothing to confirm against) -- even with valid
    # context this can only ever reach WAITING, never CONFIRMED, from context alone.
    result = evaluate_ltf_execution("EURUSD", "M5", _bullish_narrative(), _resolved_affinity(),
                                     CandidateDirection.LONG, ec_request=None)
    assert result.status != LTF_CONFIRMED


# =========================================================================== RISK_MANAGEMENT (section 19)

def test_risk_management_valid_sizing_passes():
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.1800, stop_loss=1.1750,
                                  take_profit=1.1900, risk_percent=1.0, equity=10000.0, symbol_meta=_meta())
    result = evaluate_risk_management("EURUSD", req)
    assert result.status == RISK_PASS
    assert result.trade_management.sizing.normalized_volume is not None


def test_risk_management_invalid_sl_distance_fails():
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.1800, stop_loss=1.1800,
                                  risk_percent=1.0, equity=10000.0, symbol_meta=_meta())
    result = evaluate_risk_management("EURUSD", req)
    assert result.status == RISK_FAIL


def test_risk_management_volume_below_min_fails_never_rounds_up():
    # Tiny risk budget -> raw_volume rounds below volume_min; must FAIL, never round up
    # past the requested risk (spec: "never round risk upward unintentionally").
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.1800, stop_loss=1.1750,
                                  risk_percent=0.0001, equity=100.0, symbol_meta=_meta())
    result = evaluate_risk_management("EURUSD", req)
    assert result.status == RISK_FAIL
    assert result.trade_management.sizing.normalized_volume is None


def test_risk_management_no_request_is_unresolved_not_failed():
    result = evaluate_risk_management("EURUSD", None)
    assert result.status == RISK_UNRESOLVED


# =========================================================================== PIPELINE / TRADE_STATE (section 15/20)

def test_pipeline_example_a_trade_ready_long():
    narrative = _bullish_narrative()
    affinity = _resolved_affinity()
    from daytrading.models import LTFExecutionResult

    ltf = LTFExecutionResult(symbol="EURUSD", execution_timeframe="M5", direction="LONG",
                              context_valid=True, status=LTF_CONFIRMED)
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.1800, stop_loss=1.1750,
                                  take_profit=1.1900, risk_percent=1.0, equity=10000.0, symbol_meta=_meta())
    risk = evaluate_risk_management("EURUSD", req)

    result = derive_trade_state(narrative, affinity, ltf, risk)
    assert result.trade_state == STATE_TRADE_READY_LONG
    assert result.direction == "LONG"


def test_pipeline_example_b_no_trade_on_unresolved_narrative():
    unresolved = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_UNRESOLVED, status="OK")
    result = derive_trade_state(unresolved, None, None, None)
    assert result.trade_state == STATE_NO_TRADE
    assert result.liquidity_affinity is None
    assert result.ltf_execution is None


def test_pipeline_waits_before_each_stage_is_evaluated():
    narrative = _bullish_narrative()
    assert derive_trade_state(narrative, None, None, None).trade_state == STATE_WAIT_AFFINITY
    affinity = _resolved_affinity()
    assert derive_trade_state(narrative, affinity, None, None).trade_state == STATE_WAIT_LTF_EXECUTION
    from daytrading.models import LTFExecutionResult
    ltf = LTFExecutionResult(symbol="EURUSD", execution_timeframe="M5", direction="LONG",
                              context_valid=True, status=LTF_CONFIRMED)
    assert derive_trade_state(narrative, affinity, ltf, None).trade_state == STATE_WAIT_RISK


def test_pipeline_ltf_invalidated_stops_pipeline():
    from daytrading.models import LTFExecutionResult
    narrative = _bullish_narrative()
    affinity = _resolved_affinity()
    ltf = LTFExecutionResult(symbol="EURUSD", execution_timeframe="M5", direction="LONG",
                              context_valid=True, status="INVALIDATED")
    result = derive_trade_state(narrative, affinity, ltf, None)
    assert result.trade_state == STATE_INVALIDATED


def test_pipeline_risk_fail_yields_no_trade():
    from daytrading.models import LTFExecutionResult
    narrative = _bullish_narrative()
    affinity = _resolved_affinity()
    ltf = LTFExecutionResult(symbol="EURUSD", execution_timeframe="M5", direction="LONG",
                              context_valid=True, status=LTF_CONFIRMED)
    bad_req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.1800, stop_loss=1.1800,
                                      risk_percent=1.0, equity=10000.0, symbol_meta=_meta())
    risk = evaluate_risk_management("EURUSD", bad_req)
    result = derive_trade_state(narrative, affinity, ltf, risk)
    assert result.trade_state == STATE_NO_TRADE
