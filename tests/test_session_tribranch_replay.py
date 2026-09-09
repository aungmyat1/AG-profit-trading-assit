"""AG_SESSION_TRADE_V120 mandatory tests (P41) for the new, independent Sweep/Range/
Trend research candidate (src/session_tribranch_research/). Does not touch, and never
imports, ST_ASIAN_SWEEP_5R_V1's own frozen v1.1.1 evidence."""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from strategy_engine.session.candles import Candle  # noqa: E402
from strategy_engine.session.reference_box import build_reference_box  # noqa: E402
from strategy_engine.session.setups import Direction  # noqa: E402
from session_tribranch_research.replay import (  # noqa: E402
    _fill_scan, _resolve_exit, _is_range_regime, MAX_RANGE_PIPS_EURUSD, PIP_SIZE,
)


def _c(hh, mm, o, h, l, c):
    return Candle(time=datetime(2026, 1, 5, hh, mm, tzinfo=timezone.utc), open=o, high=h, low=l, close=c)


# ---------------------------------------------------------------------------
# Mandatory: no-fill must never create a trade (Range/Trend phantom-fill elimination).
# ---------------------------------------------------------------------------


def test_range_target_hit_without_entry_touch_does_not_create_trade():
    """Price rallies straight past a would-be target without ever touching the LIMIT
    entry level -- must be NO_FILL, never a synthetic winner."""
    entry = 1.1000  # never touched below this in the candles below
    candles = [
        _c(7, 0, 1.1030, 1.1040, 1.1025, 1.1038),
        _c(7, 5, 1.1038, 1.1060, 1.1035, 1.1055),  # rallies straight through a hypothetical target
    ]
    fill = _fill_scan(Direction.LONG, entry, candles)
    assert fill is None  # NO_FILL -- price never traded down to 1.1000


def test_trend_target_hit_without_midpoint_fill_does_not_create_trade():
    entry = 1.1020  # session midpoint, never revisited
    candles = [
        _c(7, 0, 1.1040, 1.1080, 1.1038, 1.1078),  # starts above entry, rallies away
        _c(7, 5, 1.1078, 1.1090, 1.1076, 1.1088),
    ]
    fill = _fill_scan(Direction.LONG, entry, candles)
    assert fill is None


# ---------------------------------------------------------------------------
# Mandatory: stop/target evaluated only AFTER a real fill; no phantom pre-entry outcome.
# ---------------------------------------------------------------------------


def test_stop_before_entry_does_not_close_nonexistent_position():
    """A candle sequence where price never reaches the entry level on the first candle
    (so no position exists yet) must not be interpreted as a loss even though price is
    already close to where the stop would sit once filled."""
    entry, stop, tp1, tp2 = 1.1000, 1.0990, 1.1020, 1.1050
    pre_entry_candles = [_c(7, 0, 1.1010, 1.1012, 1.1002, 1.1005)]  # low stays ABOVE entry -- never fills
    fill_scan_candles = [_c(7, 5, 1.1005, 1.1008, 1.0999, 1.1000)]  # touches down to entry, fills here
    fill = _fill_scan(Direction.LONG, entry, pre_entry_candles + fill_scan_candles)
    assert fill is fill_scan_candles[0]  # fills on the SECOND candle, not the first
    assert fill.time > pre_entry_candles[0].time  # the earlier non-touching candle is correctly bypassed


def test_target_before_entry_does_not_create_profit():
    """Price touches a would-be target level before the entry itself ever fills -- must
    not be credited as a win; only candles at/after the real fill count."""
    entry, stop, tp1, tp2, tp1_R = 1.1000, 1.0990, 1.1030, 1.1050, 3.0
    pre_entry_candles = [_c(7, 0, 1.1010, 1.1032, 1.1005, 1.1008)]  # touches tp1 level (1.1030) but entry (1.1000) never touched here
    fill_candle = [_c(7, 5, 1.1008, 1.1009, 1.0995, 1.1000)]        # entry fills here
    after_fill = [_c(7, 10, 1.1000, 1.1005, 1.0998, 1.1002)]        # nothing happens after
    all_candles = pre_entry_candles + fill_candle + after_fill
    fill = _fill_scan(Direction.LONG, entry, all_candles)
    assert fill is fill_candle[0]
    candles_after_fill = [c for c in all_candles if c.time > fill.time]
    terminal_state, realized_R, exit_time = _resolve_exit(
        Direction.LONG, entry, stop, tp1, tp2, tp1_R, candles_after_fill,
    )
    assert terminal_state != "RESOLVED_TP1_TP2"
    assert terminal_state != "RESOLVED_TP1_BE"
    assert realized_R != tp1_R  # the pre-fill tp1 touch must never be credited


# ---------------------------------------------------------------------------
# fill_time <= exit_time; no outcome-generating event before fill_time.
# ---------------------------------------------------------------------------


def test_fill_time_before_exit_time_invariant():
    entry, stop, tp1, tp2, tp1_R = 1.1000, 1.0990, 1.1030, 1.1050, 3.0
    fill_candle = _c(7, 0, 1.1005, 1.1006, 1.0999, 1.1000)
    after = [_c(7, 5, 1.1000, 1.1001, 1.0989, 1.0995)]  # SL hit here
    terminal_state, realized_R, exit_time = _resolve_exit(
        Direction.LONG, entry, stop, tp1, tp2, tp1_R, after,
    )
    assert terminal_state == "RESOLVED_SL"
    assert exit_time > fill_candle.time


def test_no_candles_after_fill_yields_unresolved_not_phantom_win():
    terminal_state, realized_R, exit_time = _resolve_exit(
        Direction.LONG, 1.1000, 1.0990, 1.1030, 1.1050, 3.0, [],
    )
    assert terminal_state == "UNRESOLVED_NO_DATA"
    assert realized_R is None


# ---------------------------------------------------------------------------
# Same-bar ambiguity: conservative tie-break, documented and deterministic.
# ---------------------------------------------------------------------------


def test_same_candle_sl_and_tp_resolves_conservatively_to_sl():
    entry, stop, tp1, tp2, tp1_R = 1.1000, 1.0990, 1.1030, 1.1050, 3.0
    ambiguous = [_c(7, 5, 1.1000, 1.1035, 1.0985, 1.1010)]  # high >= tp1 AND low <= stop, same candle
    terminal_state, realized_R, exit_time = _resolve_exit(
        Direction.LONG, entry, stop, tp1, tp2, tp1_R, ambiguous,
    )
    assert terminal_state == "AMBIGUOUS_SEQUENCE_RESOLVED_CONSERVATIVE"
    assert realized_R == -1.0  # conservative: never the favorable (TP) outcome


# ---------------------------------------------------------------------------
# Regime classification: this candidate's own family gate, not ER_ONLY_V2.
# ---------------------------------------------------------------------------


def test_range_regime_uses_strategy_own_25_pip_gate_not_efficiency_ratio():
    ref_candles = [_c(h, m, 1.1000, 1.1010, 1.0995, 1.1005) for h in range(6) for m in (0, 30)]
    # Construct a box with range exactly at the 25-pip boundary.
    wide_candles = list(ref_candles)
    wide_candles[0] = _c(0, 0, 1.1000, 1.1000 + 0.0026, 1.1000, 1.1000)  # 26 pips -- exceeds cap
    box_wide = build_reference_box("Asian", wide_candles, len(wide_candles))
    assert box_wide.session_range / PIP_SIZE > MAX_RANGE_PIPS_EURUSD
    assert _is_range_regime(box_wide) is False  # correctly TREND-regime, range gate exceeded

    tight_candles = ref_candles
    box_tight = build_reference_box("Asian", tight_candles, len(tight_candles))
    assert box_tight.session_range / PIP_SIZE <= MAX_RANGE_PIPS_EURUSD
    assert _is_range_regime(box_tight) is True
