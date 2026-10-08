"""Pure deterministic evaluation rules of AG_CRYPTO_CFD_STRATEGY_CONTRACT_V1.

evaluate() is a pure function of its closed-candle inputs: identical inputs produce an
identical result dict (no wall-clock read, no MT5 call, no mutation anywhere). It only
ever classifies -- it produces no order, no proposal ticket, and carries hard-False
authority fields.

Reused asset-independent primitives (explicitly shared across asset classes per
strategy_engine/sweep_retest/profile.py's own contract -- these are NOT the perp
profile):

  - strategy_engine.session.build_reference_box  (generic window high/low/mid formula)
  - strategy_engine.sweep_retest.sweep.find_qualified_sweep
  - strategy_engine.sweep_retest.mss.find_mss
  - strategy_engine.sweep_retest.retest.find_retest / ENTRY_TTL_M5_BARS
  - strategy_engine.sweep_retest.targets.build_target_plan / MIN_TP2_R_MULTIPLE
  - market_structure.structural_breaks_for_candles  (D1/H1 structure authority)

Deliberately NOT imported: the perp tick-model module of strategy_engine.sweep_retest,
any execution/broker module, any FX session clock, any FX pip helper.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from market_structure import structural_breaks_for_candles
from market_structure.config import load_market_structure_config
from market_structure.models import MarketStructureConfig
from strategy_engine.session import Candle, ReferenceBox, build_reference_box
from strategy_engine.sweep_retest.mss import find_mss
from strategy_engine.sweep_retest.retest import ENTRY_TTL_M5_BARS, find_retest
from strategy_engine.sweep_retest.sweep import SWEEP_HIGH, SWEEP_LOW, find_qualified_sweep
from strategy_engine.sweep_retest.targets import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    GEOMETRY_VALID,
    MIN_TP2_R_MULTIPLE,
    build_target_plan,
)

from .contract import (
    ASSET_CLASS,
    CONTRACT_ID,
    CONTRACT_VERSION,
    ENTRY_TIMING,
    EXECUTION_AUTHORIZED,
    INSTRUMENTS,
    PROPOSAL_AUTHORITY,
    REFERENCE_EXPECTED_M5_BARS,
    REFERENCE_LABEL,
    RISK_POLICY_STATUS,
    SESSION_POLICY,
    SPREAD_POLICY,
    STOP_BUFFER_PRICE,
    SYMBOL_NOT_IN_CONTRACT,
    TP1_ACTION,
    TP1_VOLUME_PCT,
)

# ------------------------------------------------------------------ structure vocabulary
STRUCTURE_BULLISH = "BULLISH"
STRUCTURE_BEARISH = "BEARISH"
STRUCTURE_UNRESOLVED = "UNRESOLVED"

PERMISSION_LONG = "LONG_ALLOWED"
PERMISSION_SHORT = "SHORT_ALLOWED"
PERMISSION_NONE = "NO_DIRECTION"

# ------------------------------------------------------------------ result vocabulary
RESULT_SYMBOL_NOT_IN_CONTRACT = SYMBOL_NOT_IN_CONTRACT
RESULT_REFERENCE_INCOMPLETE = "REFERENCE_INCOMPLETE"
RESULT_NO_DIRECTION = "NO_TRADE_DIRECTION"
RESULT_WAITING_SWEEP = "WAITING_SWEEP"
RESULT_WAITING_MSS = "WAITING_MSS"
RESULT_WAITING_RETEST = "WAITING_RETEST"
RESULT_ENTRY_WINDOW_PASSED = "SIGNAL_ENTRY_WINDOW_PASSED"  # Checklist V1.1 reason code
RESULT_NO_TRADE_TARGET_GEOMETRY = "NO_TRADE_TARGET_GEOMETRY"
RESULT_INVALID_STOP_DISTANCE = "INVALID_STOP_DISTANCE"
RESULT_ENTRY_VALID = "ENTRY_VALID"

REASON_H1_UNRESOLVED = "H1_STRUCTURE_UNRESOLVED"
REASON_HTF_CONFLICT = "HTF_DIRECTION_CONFLICT"  # Checklist V1.1 taxonomy


def utc_day_window(now: datetime) -> Tuple[datetime, datetime]:
    """Current UTC calendar day of `now`, [start, end) half-open."""
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def previous_utc_day_window(now: datetime) -> Tuple[datetime, datetime]:
    """Previous UTC calendar day, [start, end) half-open -- the liquidity lookback."""
    start, _ = utc_day_window(now)
    return start - timedelta(days=1), start


def previous_day_reference(m5_candles: Sequence[Candle], now: datetime) -> Optional[ReferenceBox]:
    """PREV_UTC_DAY_HIGH/LOW/MID from closed M5 candles of the previous UTC day.

    Completeness rule (frozen): exactly REFERENCE_EXPECTED_M5_BARS closed bars must fall
    inside the window, else the reference is INCOMPLETE and None is returned
    (fail-closed; no partial-day extreme is ever used as a liquidity level)."""
    start, end = previous_utc_day_window(now)
    window = [c for c in m5_candles if start <= c.time < end]
    if len(window) != REFERENCE_EXPECTED_M5_BARS:
        return None
    return build_reference_box(REFERENCE_LABEL, window, REFERENCE_EXPECTED_M5_BARS)


def confirmed_direction(candles: Sequence[Candle],
                        config: Optional[MarketStructureConfig] = None) -> str:
    """Direction of the most recent CONFIRMED structural break (BOS/CHOCH) by event
    time -- the same rule the frozen crypto observation layer applies on D1/H1."""
    config = config or load_market_structure_config()
    if len(candles) < 3:
        return STRUCTURE_UNRESOLVED
    events = structural_breaks_for_candles(list(candles), config)
    if not events:
        return STRUCTURE_UNRESOLVED
    latest = max(events, key=lambda p: p.time_utc)
    return STRUCTURE_BULLISH if "BULLISH" in latest.kind.value else STRUCTURE_BEARISH


def direction_permission(d1_direction: str, h1_direction: str) -> Tuple[str, Optional[str]]:
    """Context permission (never an entry): H1 is the directional authority; a CONFIRMED
    D1 direction opposing H1 vetoes it (HTF_DIRECTION_CONFLICT, Checklist V1.1 taxonomy);
    an UNRESOLVED D1 leaves H1 governing alone (observed live: D1 structural history for
    these CFDs can be insufficient)."""
    if h1_direction not in (STRUCTURE_BULLISH, STRUCTURE_BEARISH):
        return PERMISSION_NONE, REASON_H1_UNRESOLVED
    if d1_direction in (STRUCTURE_BULLISH, STRUCTURE_BEARISH) and d1_direction != h1_direction:
        return PERMISSION_NONE, REASON_HTF_CONFLICT
    return (PERMISSION_LONG, None) if h1_direction == STRUCTURE_BULLISH else (PERMISSION_SHORT, None)


def _authority_block() -> dict:
    """Hard-frozen non-authority surface attached to every result."""
    return {
        "session_policy": SESSION_POLICY,
        "spread_policy": SPREAD_POLICY,
        "risk_policy_status": RISK_POLICY_STATUS,
        "proposal_authority": PROPOSAL_AUTHORITY,
        "proposal_eligible": False,
        "execution_authorized": EXECUTION_AUTHORIZED,
    }


def _result(symbol: str, result: str, reason_codes: Sequence[str], evidence: dict) -> dict:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "asset_class": ASSET_CLASS,
        "symbol": symbol,
        "result": result,
        "reason_codes": list(reason_codes),
        "evidence": evidence,
        **_authority_block(),
    }


def evaluate(symbol: str, now: datetime, d1_candles: Sequence[Candle],
             h1_candles: Sequence[Candle], m5_candles: Sequence[Candle],
             m15_candles: Sequence[Candle] = (),
             structure_config: Optional[MarketStructureConfig] = None) -> dict:
    """Evaluate the full deterministic chain for one CFD at `now` using CLOSED candles
    only (caller passes closed bars; candles timestamped at/after `now` are ignored).

    Chain: instrument authority -> previous-UTC-day reference -> D1/H1 permission ->
    M5 sweep -> M5 MSS -> M5 retest (TTL 3) -> SL/TP geometry. M15 structure, when
    supplied, is recorded as evidence only -- it gates nothing in V1.

    The evaluation-time filter is applied to EVERY supplied timeframe, not just M5. A
    candle whose timestamp is at or after `now` has not closed yet, so it may not
    influence the result -- a future D1/H1 break would otherwise grant direction
    permission retroactively and turn an unresolved historical setup into an entry,
    which is look-ahead bias. `tests/test_crypto_cfd_strategy_contract_v1.py` proves a
    future HTF candle cannot change an earlier evaluation's outcome."""
    if symbol not in INSTRUMENTS:
        return _result(symbol, RESULT_SYMBOL_NOT_IN_CONTRACT, ["SYMBOL_NOT_IN_CONTRACT"],
                       {"instruments": list(INSTRUMENTS), "asset_class": ASSET_CLASS})

    # Evaluation-time causal filter, applied uniformly to every supplied timeframe.
    def _closed(candles: Sequence[Candle]) -> List[Candle]:
        return [c for c in candles if c.time < now]

    supplied = {"d1": list(d1_candles), "h1": list(h1_candles), "m5": list(m5_candles),
                "m15": list(m15_candles)}
    m5, d1_candles, h1_candles, m15_candles = (_closed(supplied["m5"]), _closed(supplied["d1"]),
                                               _closed(supplied["h1"]), _closed(supplied["m15"]))
    dropped = {name: len(raw) - len(kept) for name, raw, kept in
               (("d1", supplied["d1"], d1_candles), ("h1", supplied["h1"], h1_candles),
                ("m5", supplied["m5"], m5), ("m15", supplied["m15"], m15_candles))}
    evidence: dict = {"now_utc": now.astimezone(timezone.utc).isoformat(),
                      "causal_filter": {
                          "rule": "a candle timestamped at or after `now` has not closed and is ignored",
                          "closed_candles": {"d1": len(d1_candles), "h1": len(h1_candles),
                                             "m5": len(m5), "m15": len(m15_candles)},
                          "dropped_unclosed": dropped}}

    reference = previous_day_reference(m5, now)
    if reference is None:
        start, end = previous_utc_day_window(now)
        evidence["reference"] = {
            "kind": "PREVIOUS_UTC_DAY", "window_utc": [start.isoformat(), end.isoformat()],
            "expected_m5_bars": REFERENCE_EXPECTED_M5_BARS, "status": "INCOMPLETE",
        }
        return _result(symbol, RESULT_REFERENCE_INCOMPLETE, ["REFERENCE_INCOMPLETE"], evidence)
    evidence["reference"] = {
        "kind": "PREVIOUS_UTC_DAY", "high": reference.session_high,
        "low": reference.session_low, "mid": reference.session_mid,
        "bar_count": reference.bar_count, "status": "COMPLETE",
    }

    d1_direction = confirmed_direction(d1_candles, structure_config)
    h1_direction = confirmed_direction(h1_candles, structure_config)
    evidence["context"] = {"d1_structure": d1_direction, "h1_structure": h1_direction}
    if m15_candles:
        evidence["context"]["m15_structure"] = confirmed_direction(m15_candles, structure_config)
        evidence["context"]["m15_role"] = "OBSERVATION_ONLY"

    permission, permission_reason = direction_permission(d1_direction, h1_direction)
    evidence["context"]["direction_permission"] = permission
    if permission == PERMISSION_NONE:
        return _result(symbol, RESULT_NO_DIRECTION, [permission_reason], evidence)

    required_sweep = SWEEP_LOW if permission == PERMISSION_LONG else SWEEP_HIGH
    trade_direction = DIRECTION_LONG if permission == PERMISSION_LONG else DIRECTION_SHORT

    day_start, day_end = utc_day_window(now)
    today: List[Candle] = [c for c in m5 if day_start <= c.time < day_end]

    sweep = find_qualified_sweep(today, reference.session_high, reference.session_low,
                                 required_direction=required_sweep)
    if sweep is None:
        return _result(symbol, RESULT_WAITING_SWEEP, ["NO_TRIGGER"], evidence)
    evidence["sweep"] = {
        "direction": sweep.direction, "swept_level": sweep.swept_level,
        "level_name": sweep.level_name, "extreme_price": sweep.extreme_price,
        "candle_time_utc": sweep.candle_time.isoformat(),
    }

    up_to_sweep = [c for c in today if c.time <= sweep.candle_time]
    after_sweep = [c for c in today if c.time > sweep.candle_time]
    mss = find_mss(sweep, up_to_sweep, after_sweep, structure_config)
    if mss is None:
        return _result(symbol, RESULT_WAITING_MSS, ["NO_TRIGGER"], evidence)
    evidence["mss"] = {
        "kind": mss.kind, "broken_swing_price": mss.broken_swing_price,
        "confirmed_at_utc": mss.confirmed_at.isoformat(),
    }

    after_mss = [c for c in today if c.time > mss.confirming_candle.time]
    retest = find_retest(mss, after_mss, ttl_bars=ENTRY_TTL_M5_BARS)
    if retest is None:
        if len(after_mss) >= ENTRY_TTL_M5_BARS:
            evidence["expiry"] = {"ttl_m5_bars": ENTRY_TTL_M5_BARS,
                                  "bars_elapsed": len(after_mss), "retest_found": False}
            return _result(symbol, RESULT_ENTRY_WINDOW_PASSED,
                           ["SIGNAL_ENTRY_WINDOW_PASSED"], evidence)
        return _result(symbol, RESULT_WAITING_RETEST, ["NO_TRIGGER"], evidence)
    evidence["retest"] = {
        "entry_price": retest.entry_price, "candle_time_utc": retest.candle_time.isoformat(),
        "bars_after_mss": retest.bars_after_mss, "tolerance_price": 0.0,
    }

    plan = build_target_plan(
        direction=trade_direction,
        entry=retest.entry_price,
        sweep_extreme=sweep.extreme_price,
        ref_mid=reference.session_mid,
        ref_high=reference.session_high,
        ref_low=reference.session_low,
        stop_buffer_price=STOP_BUFFER_PRICE,
    )
    evidence["target_plan"] = {
        "status": plan.status, "direction": plan.direction, "entry": plan.entry,
        "stop_loss": plan.stop_loss, "tp1": plan.tp1, "tp2": plan.tp2,
        "risk_distance": plan.risk_distance, "tp2_r_multiple": plan.tp2_r_multiple,
        "min_tp2_r_multiple": MIN_TP2_R_MULTIPLE,
        "tp1_volume_pct": TP1_VOLUME_PCT, "tp1_action": TP1_ACTION,
        "stop_buffer_price": STOP_BUFFER_PRICE,
    }
    if plan.status != GEOMETRY_VALID:
        if plan.risk_distance is None:  # stop distance not strictly positive
            return _result(symbol, RESULT_INVALID_STOP_DISTANCE,
                           ["INVALID_STOP_DISTANCE"], evidence)
        return _result(symbol, RESULT_NO_TRADE_TARGET_GEOMETRY,
                       ["NO_TRADE_TARGET_GEOMETRY"], evidence)

    evidence["entry_timing"] = ENTRY_TIMING
    return _result(symbol, RESULT_ENTRY_VALID, [], evidence)
