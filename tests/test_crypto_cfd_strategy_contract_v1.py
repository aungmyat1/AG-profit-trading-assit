"""AG_CRYPTO_CFD_STRATEGY_CONTRACT_V1 tests (src/crypto_cfd_contract/).

Deterministic synthetic fixtures only -- no MT5/live connection, same idiom as
tests/test_liquidity_sweep_retest_strategy.py. Covers the mission matrix:

  BTCUSD long/short, ETHUSD long/short, valid/invalid sweep, valid/invalid CHoCH-MSS,
  valid retest, expired setup, invalidation (reference rotation + target geometry),
  target construction, no FX-session leakage, no perp-contract leakage.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
import yaml

from market_structure.models import MarketStructureConfig
from strategy_engine.session import Candle

from crypto_cfd_contract import contract, rules
from crypto_cfd_contract.rules import evaluate

UTC = dt.timezone.utc
# swing_length=1 keeps fixtures compact; the production default stays the shared frozen
# market-structure config (swing_length=5), injected the same way the existing
# sweep-retest tests inject it.
CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=50)

PREV_DAY = 6   # previous UTC day: 2026-01-06
CUR_DAY = 7    # current UTC day:  2026-01-07
NOW = dt.datetime(2026, 1, CUR_DAY, 1, 0, tzinfo=UTC)


# ------------------------------------------------------------------ fixture builders

def _prev_day_m5(base, hi, lo, day=PREV_DAY):
    """A complete previous UTC day: exactly 288 flat M5 bars, one setting the day high,
    one setting the day low."""
    t0 = dt.datetime(2026, 1, day, 0, 0, tzinfo=UTC)
    out = []
    for i in range(288):
        t = t0 + dt.timedelta(minutes=5 * i)
        h = hi if i == 100 else base
        lo_i = lo if i == 150 else base
        out.append(Candle(time=t, open=base, high=h, low=lo_i, close=base, volume=1.0))
    return out


def _m5(idx, o, h, lo, c, day=CUR_DAY, hour=0):
    return Candle(time=dt.datetime(2026, 1, day, hour, 5 * idx, tzinfo=UTC),
                  open=o, high=h, low=lo, close=c, volume=1.0)


def _h1_candles(prices, wick):
    out, t = [], dt.datetime(2026, 1, 1, tzinfo=UTC)
    for p in prices:
        out.append(Candle(time=t, open=p, high=p + wick, low=p - wick, close=p, volume=1.0))
        t += dt.timedelta(hours=1)
    return out


def _descending(start, step, amplitude, cycles=25):
    prices = []
    for i in range(cycles):
        high = start - i * step
        prices.extend([high, high - amplitude])
    return prices


def _ascending(start, step, amplitude, cycles=25):
    prices = []
    for i in range(cycles):
        low = start + i * step
        prices.extend([low, low + amplitude])
    return prices


BTC_H1_BEARISH = _h1_candles(_descending(90000.0, 300.0, 900.0), wick=5.0)
BTC_H1_BULLISH = _h1_candles(_ascending(80000.0, 300.0, 900.0), wick=5.0)
ETH_H1_BEARISH = _h1_candles(_descending(3000.0, 10.0, 30.0), wick=0.5)
ETH_H1_BULLISH = _h1_candles(_ascending(2400.0, 10.0, 30.0), wick=0.5)

D1_FLAT = [Candle(time=dt.datetime(2026, 1, d, tzinfo=UTC), open=1.0, high=1.0, low=1.0,
                  close=1.0, volume=1.0) for d in range(1, 3)]  # < 3 bars -> UNRESOLVED


# BTCUSD SHORT: prev day hi=85000 lo=82500 (mid 83750). Sweep of 85000, swing low 84180
# broken -> MSS, retest -> entry 84180, SL 85120, TP2 R = 1680/940 ~ 1.787.
BTC_REF_SHORT = dict(base=84000.0, hi=85000.0, lo=82500.0)
BTC_SHORT_DAY = [
    _m5(0, 84400, 84450, 84350, 84400),
    _m5(1, 84300, 84350, 84180, 84200),   # swing low candidate 84180
    _m5(2, 84250, 84500, 84220, 84480),   # rally
    _m5(3, 84480, 85120, 84300, 84360),   # SWEEP: high>85000, close<85000
    _m5(4, 84360, 84400, 84250, 84300),   # holds above swing low
    _m5(5, 84300, 84320, 84050, 84100),   # MSS: close 84100 < 84180
    _m5(6, 84100, 84200, 84020, 84060),   # RETEST: high 84200 >= 84180
]

# BTCUSD LONG: prev day lo=84000 hi=86200 (mid 85100). Sweep of 84000, swing high 84720
# broken -> MSS, retest -> entry 84720, SL 83880, TP2 R = 1480/840 ~ 1.762.
BTC_REF_LONG = dict(base=84500.0, hi=86200.0, lo=84000.0)
BTC_LONG_DAY = [
    _m5(0, 84400, 84450, 84350, 84400),
    _m5(1, 84450, 84720, 84400, 84600),   # swing high candidate 84720
    _m5(2, 84480, 84520, 84300, 84350),   # decline
    _m5(3, 84350, 84400, 83880, 84080),   # SWEEP: low<84000, close>84000
    _m5(4, 84080, 84650, 84050, 84600),   # holds below swing high
    _m5(5, 84600, 84800, 84550, 84760),   # MSS: close 84760 > 84720
    _m5(6, 84760, 84780, 84700, 84740),   # RETEST: low 84700 <= 84720
]

# ETHUSD SHORT: prev day hi=2700 lo=2440 (mid 2570). Entry 2612, SL 2712, R = 172/100.
ETH_REF_SHORT = dict(base=2650.0, hi=2700.0, lo=2440.0)
ETH_SHORT_DAY = [
    _m5(0, 2640, 2645, 2635, 2640),
    _m5(1, 2635, 2640, 2612, 2620),       # swing low candidate 2612
    _m5(2, 2625, 2655, 2618, 2650),
    _m5(3, 2650, 2712, 2630, 2640),       # SWEEP: high>2700, close<2700
    _m5(4, 2640, 2645, 2616, 2630),
    _m5(5, 2630, 2632, 2596, 2600),       # MSS: close 2600 < 2612
    _m5(6, 2600, 2615, 2590, 2598),       # RETEST: high 2615 >= 2612
]

# ETHUSD LONG: prev day hi=2820 lo=2600 (mid 2710). Entry 2672, SL 2588, R = 148/84.
ETH_REF_LONG = dict(base=2700.0, hi=2820.0, lo=2600.0)
ETH_LONG_DAY = [
    _m5(0, 2640, 2645, 2635, 2640),
    _m5(1, 2650, 2672, 2645, 2660),       # swing high candidate 2672
    _m5(2, 2648, 2652, 2630, 2635),
    _m5(3, 2635, 2640, 2588, 2608),       # SWEEP: low<2600, close>2600
    _m5(4, 2608, 2665, 2605, 2660),
    _m5(5, 2660, 2680, 2655, 2676),       # MSS: close 2676 > 2672
    _m5(6, 2676, 2678, 2670, 2674),       # RETEST: low 2670 <= 2672
]


def _run(symbol, ref, day_candles, h1, d1=None, now=NOW):
    m5 = _prev_day_m5(**ref) + list(day_candles)
    return evaluate(symbol, now, d1 if d1 is not None else D1_FLAT, h1, m5,
                    structure_config=CFG)


# ------------------------------------------------------------------ four instrument examples

def test_btcusd_short_example_entry_valid():
    r = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_ENTRY_VALID
    plan = r["evidence"]["target_plan"]
    assert plan["direction"] == "SHORT"
    assert plan["entry"] == pytest.approx(84180.0)
    assert plan["stop_loss"] == pytest.approx(85120.0)   # sweep high + 0.00 buffer
    assert plan["tp1"] == pytest.approx(83750.0)         # previous-day mid
    assert plan["tp2"] == pytest.approx(82500.0)         # opposing liquidity (PDL)
    assert plan["tp2_r_multiple"] == pytest.approx(1680.0 / 940.0)
    assert r["proposal_eligible"] is False and r["execution_authorized"] is False


def test_btcusd_long_example_entry_valid():
    r = _run("BTCUSD", BTC_REF_LONG, BTC_LONG_DAY, BTC_H1_BULLISH)
    assert r["result"] == rules.RESULT_ENTRY_VALID
    plan = r["evidence"]["target_plan"]
    assert plan["direction"] == "LONG"
    assert plan["entry"] == pytest.approx(84720.0)
    assert plan["stop_loss"] == pytest.approx(83880.0)   # sweep low - 0.00 buffer
    assert plan["tp1"] == pytest.approx(85100.0)
    assert plan["tp2"] == pytest.approx(86200.0)
    assert plan["tp2_r_multiple"] == pytest.approx(1480.0 / 840.0)


def test_ethusd_short_example_entry_valid():
    r = _run("ETHUSD", ETH_REF_SHORT, ETH_SHORT_DAY, ETH_H1_BEARISH)
    assert r["result"] == rules.RESULT_ENTRY_VALID
    plan = r["evidence"]["target_plan"]
    assert plan["direction"] == "SHORT"
    assert plan["entry"] == pytest.approx(2612.0)
    assert plan["stop_loss"] == pytest.approx(2712.0)
    assert plan["tp1"] == pytest.approx(2570.0)
    assert plan["tp2"] == pytest.approx(2440.0)
    assert plan["tp2_r_multiple"] == pytest.approx(172.0 / 100.0)


def test_ethusd_long_example_entry_valid():
    r = _run("ETHUSD", ETH_REF_LONG, ETH_LONG_DAY, ETH_H1_BULLISH)
    assert r["result"] == rules.RESULT_ENTRY_VALID
    plan = r["evidence"]["target_plan"]
    assert plan["direction"] == "LONG"
    assert plan["entry"] == pytest.approx(2672.0)
    assert plan["stop_loss"] == pytest.approx(2588.0)
    assert plan["tp1"] == pytest.approx(2710.0)
    assert plan["tp2"] == pytest.approx(2820.0)
    assert plan["tp2_r_multiple"] == pytest.approx(148.0 / 84.0)


# ------------------------------------------------------------------ sweep predicate

def test_valid_sweep_recorded_with_exact_levels():
    day = BTC_SHORT_DAY[:4]  # up to and including the sweep candle
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_WAITING_MSS
    sweep = r["evidence"]["sweep"]
    assert sweep["direction"] == "HIGH_SWEEP"
    assert sweep["swept_level"] == pytest.approx(85000.0)
    assert sweep["extreme_price"] == pytest.approx(85120.0)


def test_invalid_sweep_close_beyond_level_is_not_a_sweep():
    day = BTC_SHORT_DAY[:3] + [_m5(3, 84480, 85120, 84300, 85050)]  # closes ABOVE 85000
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_WAITING_SWEEP
    assert "sweep" not in r["evidence"]


def test_invalid_sweep_dual_side_candle_is_ambiguous_and_skipped():
    dual = _m5(3, 84480, 85120, 82400, 84360)  # pierces BOTH 85000 and 82500, closes inside
    r = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY[:3] + [dual], BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_WAITING_SWEEP


def test_wrong_direction_sweep_blocked_by_h1_permission():
    # Bearish H1 -> SHORT_ALLOWED -> a LOW sweep is not a candidate.
    r = _run("BTCUSD", BTC_REF_LONG, BTC_LONG_DAY, BTC_H1_BEARISH, d1=D1_FLAT)
    assert r["result"] in (rules.RESULT_WAITING_SWEEP, rules.RESULT_NO_DIRECTION)
    assert r["result"] == rules.RESULT_WAITING_SWEEP  # H1 resolved, just no HIGH sweep


# ------------------------------------------------------------------ CHoCH / MSS predicate

def test_valid_mss_requires_close_beyond_swing():
    day = BTC_SHORT_DAY[:6]  # through the MSS-confirming candle
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_WAITING_RETEST
    mss = r["evidence"]["mss"]
    assert mss["kind"] == "MSS_BEARISH"
    assert mss["broken_swing_price"] == pytest.approx(84180.0)


def test_invalid_structure_break_intrabar_penetration_does_not_confirm():
    day = BTC_SHORT_DAY[:5] + [_m5(5, 84300, 84320, 84050, 84250)]  # low<84180, close above
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_WAITING_MSS
    assert "mss" not in r["evidence"]


# ------------------------------------------------------------------ retest / expiry

def test_valid_retest_exact_touch_tolerance_zero():
    r = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH)
    retest = r["evidence"]["retest"]
    assert retest["entry_price"] == pytest.approx(84180.0)
    assert retest["tolerance_price"] == 0.0
    assert retest["bars_after_mss"] == 1


def test_near_miss_retest_does_not_trigger():
    # High 84179.99 < 84180.00 -> no touch within TTL -> expiry, not a tolerant entry.
    day = BTC_SHORT_DAY[:6] + [
        _m5(6, 84100, 84179.99, 84020, 84060),
        _m5(7, 84060, 84150.00, 84000, 84040),
        _m5(8, 84040, 84100.00, 83980, 84000),
    ]
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_ENTRY_WINDOW_PASSED


def test_expired_setup_emits_signal_entry_window_passed():
    day = BTC_SHORT_DAY[:6] + [
        _m5(6, 84100, 84140, 84060, 84120),
        _m5(7, 84120, 84150, 84080, 84100),
        _m5(8, 84100, 84130, 84050, 84090),
    ]
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == "SIGNAL_ENTRY_WINDOW_PASSED"
    assert r["reason_codes"] == ["SIGNAL_ENTRY_WINDOW_PASSED"]
    assert r["evidence"]["expiry"]["ttl_m5_bars"] == 3


def test_retest_window_still_open_is_waiting_not_expired():
    day = BTC_SHORT_DAY[:6] + [_m5(6, 84100, 84140, 84060, 84120)]  # 1 of 3 TTL bars
    r = _run("BTCUSD", BTC_REF_SHORT, day, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_WAITING_RETEST


# ------------------------------------------------------------------ invalidation

def test_invalidation_by_utc_day_rotation():
    # Same candles one day later: the old reference is dead and the new previous UTC
    # day (7 bars) fails the 288-bar completeness rule -> fail-closed.
    r = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH,
             now=NOW + dt.timedelta(days=1))
    assert r["result"] == rules.RESULT_REFERENCE_INCOMPLETE
    assert r["evidence"]["reference"]["status"] == "INCOMPLETE"


def test_invalidation_by_target_geometry():
    # PDL raised to 83900 -> mid 84450 lands ABOVE the short entry 84180 -> rejected,
    # no substitute target invented.
    ref = dict(base=84000.0, hi=85000.0, lo=83900.0)
    r = _run("BTCUSD", ref, BTC_SHORT_DAY, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_NO_TRADE_TARGET_GEOMETRY
    assert r["evidence"]["target_plan"]["status"] == "NO_TRADE_TARGET_GEOMETRY"


def test_incomplete_previous_day_reference_fails_closed():
    short_prev = _prev_day_m5(**BTC_REF_SHORT)[:287]  # one bar missing
    r = evaluate("BTCUSD", NOW, D1_FLAT, BTC_H1_BEARISH, short_prev + BTC_SHORT_DAY,
                 structure_config=CFG)
    assert r["result"] == rules.RESULT_REFERENCE_INCOMPLETE


def test_d1_conflict_vetoes_h1_direction():
    r = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH,
             d1=[Candle(time=c.time - dt.timedelta(days=200), open=c.open, high=c.high,
                        low=c.low, close=c.close, volume=1.0) for c in BTC_H1_BULLISH])
    assert r["result"] == rules.RESULT_NO_DIRECTION
    assert r["reason_codes"] == ["HTF_DIRECTION_CONFLICT"]


def test_unresolved_h1_gives_no_direction():
    r = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, h1=D1_FLAT)
    assert r["result"] == rules.RESULT_NO_DIRECTION
    assert r["reason_codes"] == ["H1_STRUCTURE_UNRESOLVED"]


# ------------------------------------------------------------------ target construction

def test_target_construction_partial_plus_runner_contract():
    r = _run("ETHUSD", ETH_REF_SHORT, ETH_SHORT_DAY, ETH_H1_BEARISH)
    plan = r["evidence"]["target_plan"]
    assert plan["tp1_volume_pct"] == 0.5
    assert plan["tp1_action"] == "MOVE_REMAINING_TO_BREAKEVEN"
    assert plan["min_tp2_r_multiple"] == 1.5          # contractual family value, not RR>=2
    assert plan["stop_buffer_price"] == 0.0           # frozen zero-point buffer
    assert plan["risk_distance"] == pytest.approx(100.0)


def test_min_tp2_r_multiple_enforced():
    # PDL raised so TP2 reward/risk < 1.5 while TP1 stays below entry -> rejected.
    ref = dict(base=84000.0, hi=85000.0, lo=83000.0)  # mid 84000 < 84180, reward 1180/940 < 1.5
    r = _run("BTCUSD", ref, BTC_SHORT_DAY, BTC_H1_BEARISH)
    assert r["result"] == rules.RESULT_NO_TRADE_TARGET_GEOMETRY
    assert r["evidence"]["target_plan"]["tp2_r_multiple"] == pytest.approx(1180.0 / 940.0)


# ------------------------------------------------------------------ no FX-session leakage

def test_no_fx_session_gating_setup_valid_at_any_utc_hour():
    # Identical sequence placed at 20:00-20:30 UTC (inside no FX strategy window) still
    # produces ENTRY_VALID: the only time authority is the UTC-day reference rotation.
    late = [Candle(time=c.time + dt.timedelta(hours=20), open=c.open, high=c.high,
                   low=c.low, close=c.close, volume=1.0) for c in BTC_SHORT_DAY]
    r = _run("BTCUSD", BTC_REF_SHORT, late, BTC_H1_BEARISH,
             now=dt.datetime(2026, 1, CUR_DAY, 21, 0, tzinfo=UTC))
    assert r["result"] == rules.RESULT_ENTRY_VALID
    assert r["session_policy"] == "BROKER_DEFINED / 24H_OBSERVATION"


def test_no_fx_session_policy_constants():
    assert contract.SESSION_POLICY == "BROKER_DEFINED / 24H_OBSERVATION"
    assert contract.FX_SESSION_GATE_APPLIED is False
    assert contract.EXECUTION_WINDOWS == ()  # no FX windows, no perp activity window


# ------------------------------------------------------------------ no perp-contract leakage

def test_perp_symbols_rejected_fail_closed():
    for perp in ("BTC" + "USDT", "ETH" + "USDT"):
        r = evaluate(perp, NOW, D1_FLAT, BTC_H1_BEARISH, [], structure_config=CFG)
        assert r["result"] == "SYMBOL_NOT_IN_CONTRACT"
        assert contract.contract_status(perp)["status"] == "SYMBOL_NOT_IN_CONTRACT"


def test_no_perp_or_fx_identity_in_package_source():
    pkg = pathlib.Path(__file__).resolve().parents[1] / "src" / "crypto_cfd_contract"
    source = "\n".join(p.read_text(encoding="utf-8") for p in sorted(pkg.glob("*.py")))
    forbidden = [
        "BTC" + "USDT", "ETH" + "USDT",            # perp instrument identities
        "crypto_" + "symbols",                      # perp tick model module
        "funding_rate",                             # perp funding model
        "13:" + "30",                               # perp activity window
        "pip_" + "size", "forex_sl_buffer_price",   # FX pip conventions
        "ASIAN_" + "SESSION", "session_" + "pairs", # FX session gating
        "from mt5", "import mt5",                   # broker surface
        "order_" + "send", "management_" + "gateway", "execution." + "executor",
    ]
    for token in forbidden:
        assert token not in source, f"forbidden identity {token!r} leaked into crypto_cfd_contract"


def test_broker_native_units_not_fx_pips():
    assert contract.BROKER_POINT == 0.01 and contract.EXPECTED_DIGITS == 2
    assert contract.SPREAD_UNITS == ("BROKER_POINTS", "PRICE", "PERCENT")
    assert contract.STOP_BUFFER_POINTS == 0 and contract.STOP_BUFFER_PRICE == 0.0


# ------------------------------------------------------------------ contract authority surface

def test_contract_yaml_matches_code_authority():
    root = pathlib.Path(__file__).resolve().parents[1]
    doc = yaml.safe_load((root / "strategies" / "ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml").read_text(encoding="utf-8"))
    assert doc["strategy_id"] == contract.CONTRACT_ID
    assert doc["instrument_authority"]["asset_class"] == "CRYPTO_CFD"
    assert doc["instrument_authority"]["instruments"] == ["BTCUSD", "ETHUSD"]
    assert doc["session_time_policy"]["policy"] == contract.SESSION_POLICY
    assert doc["session_time_policy"]["fx_session_gate_applied"] is False
    assert doc["session_time_policy"]["execution_windows"] == []
    assert doc["spread_cost_policy"]["threshold"] == "SPREAD_POLICY_UNDEFINED"
    assert doc["risk_policy_interface"]["status"] == "RISK_POLICY_AMBIGUOUS"
    assert doc["risk_policy_interface"]["risk_percent"] == "NOT_ASSIGNED"
    assert doc["research_separation"] == {
        "STRATEGY_CONTRACT_VALID": True, "EDGE_VERIFIED": False, "RISK_AUTHORIZED": False}
    assert doc["contract_status"]["BTCUSD"] == "CONTRACT_COMPLETE"
    assert doc["contract_status"]["ETHUSD"] == "CONTRACT_COMPLETE"
    assert doc["contract_status"]["execution_authorized"] is False


def test_contract_status_blocks_all_authority():
    for symbol in ("BTCUSD", "ETHUSD"):
        status = contract.contract_status(symbol)
        assert status["status"] == "CONTRACT_COMPLETE"
        assert status["edge_verified"] is False
        assert status["risk_authorized"] is False
        assert status["proposal_authority"] == "BLOCKED"
        assert status["execution_authorized"] is False
        assert "SPREAD_POLICY_UNDEFINED" in status["open_authorities"]
        assert "RISK_POLICY_AMBIGUOUS" in status["open_authorities"]


def test_every_result_carries_frozen_non_authority_block():
    results = [
        _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH),
        _run("BTCUSD", BTC_REF_SHORT, [], BTC_H1_BEARISH),
        evaluate("XAUUSD", NOW, D1_FLAT, BTC_H1_BEARISH, [], structure_config=CFG),
    ]
    for r in results:
        assert r["proposal_eligible"] is False
        assert r["execution_authorized"] is False
        assert r["spread_policy"] == "SPREAD_POLICY_UNDEFINED"
        assert r["risk_policy_status"] == "RISK_POLICY_AMBIGUOUS"


def test_evaluate_is_deterministic():
    a = _run("ETHUSD", ETH_REF_LONG, ETH_LONG_DAY, ETH_H1_BULLISH)
    b = _run("ETHUSD", ETH_REF_LONG, ETH_LONG_DAY, ETH_H1_BULLISH)
    assert a == b


# ------------------------------------------------------------------ causal (no look-ahead) gate

def _without_causal_filter(result: dict) -> dict:
    """Result minus the input-composition accounting block.

    `causal_filter` legitimately reports how many candles were supplied and dropped, so it is the
    one block that may differ between two calls that differ only in their unclosed inputs. Every
    market fact, decision, reason code and level must be identical.
    """
    out = dict(result)
    evidence = dict(out.get("evidence") or {})
    evidence.pop("causal_filter", None)
    out["evidence"] = evidence
    return out


def _future_h1(count=4, start=90000.0, step=500.0):
    """`count` H1 bars timestamped at/after NOW, forming a strong bullish break."""
    out = []
    for i in range(count):
        t = NOW + dt.timedelta(hours=i + 1)
        price = start + step * i
        out.append(Candle(time=t, open=price, high=price + 50.0, low=price - 50.0,
                          close=price, volume=1.0))
    return out


def test_future_h1_break_cannot_grant_direction_permission():
    """P1 (PR #30 review): HTF inputs must be filtered at the evaluation timestamp.

    A bullish H1 break that has not happened yet at `now` must not turn an unresolved
    historical setup into a direction-permitted one.
    """
    before = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH)
    after = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH + _future_h1())
    assert _without_causal_filter(before) == _without_causal_filter(after)
    assert before["evidence"]["causal_filter"]["dropped_unclosed"]["h1"] == 0
    assert after["evidence"]["causal_filter"]["dropped_unclosed"]["h1"] == 4
    assert after["evidence"]["context"]["h1_structure"] == before["evidence"]["context"]["h1_structure"]
    # The future bars must not even be counted as closed evidence.
    assert after["evidence"]["causal_filter"]["closed_candles"]["h1"] == len(BTC_H1_BEARISH)


def test_future_d1_break_cannot_change_the_result():
    future_d1 = D1_FLAT + [Candle(time=NOW + dt.timedelta(days=1), open=1.0, high=9.0,
                                  low=1.0, close=9.0, volume=1.0)]
    before = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH)
    after = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH, d1=future_d1)
    assert _without_causal_filter(before) == _without_causal_filter(after)
    assert after["evidence"]["causal_filter"]["dropped_unclosed"]["d1"] == 1
    assert after["evidence"]["context"]["d1_structure"] == before["evidence"]["context"]["d1_structure"]


def test_future_m15_candles_cannot_change_the_result():
    """M15 is observation-only in V1, but it is still recorded as evidence, so a future
    M15 bar must not appear in that evidence either."""
    future_m15 = [Candle(time=NOW + dt.timedelta(minutes=15 * (i + 1)), open=1.0, high=9.0,
                         low=1.0, close=9.0, volume=1.0) for i in range(3)]
    m5 = _prev_day_m5(**BTC_REF_SHORT) + list(BTC_SHORT_DAY)
    before = evaluate("BTCUSD", NOW, D1_FLAT, BTC_H1_BEARISH, m5, structure_config=CFG)
    after = evaluate("BTCUSD", NOW, D1_FLAT, BTC_H1_BEARISH, m5, future_m15, structure_config=CFG)
    assert _without_causal_filter(before) == _without_causal_filter(after)
    assert after["evidence"]["causal_filter"]["dropped_unclosed"]["m15"] == 3
    assert "m15_structure" not in after["evidence"]["context"]


def test_causal_filter_records_what_it_dropped_for_every_timeframe():
    """The filter must be auditable: each timeframe reports what it kept and what it dropped."""
    m5 = _prev_day_m5(**BTC_REF_SHORT) + list(BTC_SHORT_DAY)
    late_m5 = [Candle(time=NOW + dt.timedelta(minutes=5), open=1.0, high=1.0, low=1.0,
                      close=1.0, volume=1.0)]
    r = evaluate("BTCUSD", NOW,
                 D1_FLAT + [Candle(time=NOW, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)],
                 BTC_H1_BEARISH + _future_h1(), m5 + late_m5, (), structure_config=CFG)
    assert r["evidence"]["causal_filter"]["dropped_unclosed"] == {"d1": 1, "h1": 4, "m5": 1, "m15": 0}
    assert r["evidence"]["causal_filter"]["closed_candles"] == {
        "d1": 2, "h1": len(BTC_H1_BEARISH), "m5": len(m5), "m15": 0}


def test_unclosed_current_m5_bar_is_ignored_but_closed_history_is_kept():
    """Regression guard: the pre-existing M5 filter still behaves exactly as before."""
    m5 = _prev_day_m5(**BTC_REF_SHORT) + list(BTC_SHORT_DAY)
    r = evaluate("BTCUSD", NOW, D1_FLAT, BTC_H1_BEARISH, m5, structure_config=CFG)
    assert r["evidence"]["causal_filter"]["dropped_unclosed"]["m5"] == 0
    assert r["evidence"]["causal_filter"]["closed_candles"]["m5"] == len(m5)


def test_every_supplied_timeframe_is_filtered_not_just_m5():
    """The regression the review asked for: no timeframe may bypass the evaluation-time filter."""
    source = (pathlib.Path(__file__).resolve().parents[1] / "src" / "crypto_cfd_contract"
              / "rules.py").read_text(encoding="utf-8")
    body = source.split("def evaluate(", 1)[1]
    # Exactly one place may compare a candle time to `now`, and every timeframe must be routed
    # through it -- otherwise a new HTF input can silently bypass the causal filter again.
    comparisons = [line.strip() for line in body.splitlines() if "c.time < now" in line]
    assert len(comparisons) == 1 and comparisons[0].startswith("return [c for c in candles"), comparisons
    assign = re.search(r"^\s*m5, d1_candles, h1_candles, m15_candles = \(", body, re.M)
    assert assign, "every supplied timeframe must be reassigned from the causal filter"
    assert body[assign.start():].count("_closed(") >= 4, "one timeframe bypasses the filter"
    # ...and the filtered values, not the raw parameters, are what the rest of evaluate() uses.
    assert "confirmed_direction(d1_candles" in body and "confirmed_direction(h1_candles" in body
