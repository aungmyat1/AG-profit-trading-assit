"""Tests for market_swing_structure (P29/P30).

Covers: confirmation-timestamp derivation and the mandatory lookahead test (P6/P29),
dealing-range swing-pair selection and fail-closed behavior (P16), MTF alignment
labeling (P17-P19), and authority-boundary/conflict tests proving this package cannot
override or replace any canonical engine (P30).
"""
from __future__ import annotations

import ast
import datetime as dt

import pytest

from market_structure.models import StructurePoint, StructurePointKind, StructureResult, MarketStructureConfig
from market_structure.smc_adapter import candles_to_dataframe, latest_swings_and_breaks
from strategy_engine.session import Candle

from market_swing_structure import alignment, confirmation, dealing_range
from market_swing_structure.models import STATUS_CONFIRMED

UTC = dt.timezone.utc


def _candles(prices, start=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), step_minutes=15):
    out = []
    t = start
    for p in prices:
        out.append(Candle(time=t, open=p, high=p + 0.0005, low=p - 0.0005, close=p, volume=1.0))
        t += dt.timedelta(minutes=step_minutes)
    return out


# ---------------------------------------------------------------------------
# confirmation.py -- pure timestamp derivation
# ---------------------------------------------------------------------------


def test_confirmed_time_for_pivot_is_pivot_plus_swing_length_bars():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    confirmed = confirmation.confirmed_time_for_pivot(pivot, "M15", swing_length=3)
    assert confirmed == pivot + dt.timedelta(minutes=45)


def test_confirmed_time_for_pivot_h1():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    confirmed = confirmation.confirmed_time_for_pivot(pivot, "H1", swing_length=2)
    assert confirmed == pivot + dt.timedelta(hours=2)


def test_confirmed_time_unsupported_timeframe_fails_closed():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    with pytest.raises(confirmation.UnsupportedTimeframeError):
        confirmation.confirmed_time_for_pivot(pivot, "NOT_A_TIMEFRAME", swing_length=1)


def test_normalize_swing_point_swing_high():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    point = StructurePoint(time_utc=pivot, price=1.2345, kind=StructurePointKind.SWING_HIGH)
    swing = confirmation.normalize_swing_point(point, "M15", swing_length=3)
    assert swing.swing_type == "SWING_HIGH"
    assert swing.price == 1.2345
    assert swing.pivot_time_utc == pivot
    assert swing.confirmed_time_utc == pivot + dt.timedelta(minutes=45)
    assert swing.status == STATUS_CONFIRMED
    assert swing.confirmed_time_utc >= swing.pivot_time_utc


def test_normalize_swing_point_ignores_non_swing_kinds():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    bos_point = StructurePoint(time_utc=pivot, price=1.0, kind=StructurePointKind.BULLISH_BOS)
    assert confirmation.normalize_swing_point(bos_point, "M15", swing_length=3) is None


def test_assert_confirmed_as_of_passes_when_as_of_after_confirmation():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    point = StructurePoint(time_utc=pivot, price=1.1, kind=StructurePointKind.SWING_LOW)
    swing = confirmation.normalize_swing_point(point, "M15", swing_length=3)
    confirmation.assert_confirmed_as_of(swing, as_of_utc=swing.confirmed_time_utc)
    confirmation.assert_confirmed_as_of(swing, as_of_utc=swing.confirmed_time_utc + dt.timedelta(minutes=1))


def test_assert_confirmed_as_of_raises_before_confirmation():
    pivot = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    point = StructurePoint(time_utc=pivot, price=1.1, kind=StructurePointKind.SWING_LOW)
    swing = confirmation.normalize_swing_point(point, "M15", swing_length=3)
    with pytest.raises(confirmation.LookaheadViolationError):
        confirmation.assert_confirmed_as_of(swing, as_of_utc=swing.confirmed_time_utc - dt.timedelta(minutes=1))


# ---------------------------------------------------------------------------
# P29 mandatory lookahead test -- swing not visible before right-side confirmation
# ---------------------------------------------------------------------------


def test_swing_not_visible_before_right_side_confirmation():
    """A single, unambiguous peak at index 3 with swing_length=2 needs both right-side
    neighbors (indices 4 and 5) closed before smc's own detector will report it. This
    proves two things at once: the underlying canonical engine never reports a pivot
    before its confirming bars exist (structural no-lookahead), and
    confirmation.confirmed_time_for_pivot's derived timestamp exactly matches the moment
    the engine actually starts reporting it."""
    swing_length = 2
    prices = [1.0, 1.0, 1.0, 1.2, 1.0, 1.0, 1.0]
    candles = _candles(prices)
    pivot_time = candles[3].time

    # Only one right-side bar available (index 4) -- one short of swing_length=2.
    df_insufficient = candles_to_dataframe(candles[:5])
    latest_insufficient = latest_swings_and_breaks(df_insufficient, swing_length=swing_length, close_break=True)
    high_insufficient = latest_insufficient["latest_swing_high"]
    assert high_insufficient is None or high_insufficient.time_utc != pivot_time

    # Both right-side bars available (indices 4 and 5) -- exactly swing_length=2.
    df_sufficient = candles_to_dataframe(candles[:6])
    latest_sufficient = latest_swings_and_breaks(df_sufficient, swing_length=swing_length, close_break=True)
    high_sufficient = latest_sufficient["latest_swing_high"]
    assert high_sufficient is not None
    assert high_sufficient.time_utc == pivot_time
    assert high_sufficient.kind == StructurePointKind.SWING_HIGH

    derived_confirmed_time = confirmation.confirmed_time_for_pivot(pivot_time, "M15", swing_length)
    assert derived_confirmed_time == candles[5].time  # the last bar that made confirmation possible
    assert derived_confirmed_time > pivot_time


# ---------------------------------------------------------------------------
# alignment.py -- pure MTF label composition
# ---------------------------------------------------------------------------


def test_alignment_all_agree():
    result = alignment.compute_mtf_alignment([("H4", "BULLISH"), ("H1", "BULLISH"), ("M15", "BULLISH")])
    assert result == "ALIGNED_BULLISH"


def test_alignment_htf_bullish_ltf_conflict():
    result = alignment.compute_mtf_alignment([("H4", "BULLISH"), ("H1", "BULLISH"), ("M15", "BEARISH")])
    assert result == "HTF_BULLISH_LTF_CONFLICT"


def test_alignment_htf_bullish_ltf_transition():
    result = alignment.compute_mtf_alignment([("H4", "BULLISH"), ("M15", "STRUCTURE_STATE_UNDEFINED")])
    assert result == "HTF_BULLISH_LTF_TRANSITION"


def test_alignment_missing_data_is_unknown():
    assert alignment.compute_mtf_alignment([("H4", "BULLISH"), ("M15", None)]) == alignment.ALIGNMENT_UNKNOWN
    assert alignment.compute_mtf_alignment([("H4", "BULLISH")]) == alignment.ALIGNMENT_UNKNOWN


def test_alignment_never_resolves_conflict_to_single_direction():
    # P18: LTF cannot silently override HTF -- CONFLICT is returned, never collapsed to
    # "BULLISH" or "BEARISH" alone.
    result = alignment.compute_mtf_alignment([("H4", "BEARISH"), ("M15", "BULLISH")])
    assert "CONFLICT" in result
    assert result not in ("BULLISH", "BEARISH")


# ---------------------------------------------------------------------------
# dealing_range.py -- WHICH swing pair, fail-closed
# ---------------------------------------------------------------------------


def _structure_result(symbol="EURUSD", timeframe="H1", high=None, low=None):
    return StructureResult(
        symbol=symbol, timeframe=timeframe, status="VALID", reason_codes=(),
        latest_swing_high=high, latest_swing_low=low,
    )


def test_active_dealing_range_from_confirmed_swing_pair():
    high = StructurePoint(time_utc=dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC), price=1.1000, kind=StructurePointKind.SWING_HIGH)
    low = StructurePoint(time_utc=dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), price=1.0800, kind=StructurePointKind.SWING_LOW)
    result = _structure_result(high=high, low=low)
    snap = dealing_range.active_dealing_range_from_structure(result, current_price=1.0950)
    assert snap.swing_high == 1.1000
    assert snap.swing_low == 1.0800
    assert snap.equilibrium == pytest.approx(1.0900)
    assert snap.current_zone == "PREMIUM"
    assert snap.defining_timeframe == "H1"
    assert "structure:H1:latest_confirmed_swing_pair" == snap.source


def test_active_dealing_range_none_when_swing_missing():
    result = _structure_result(high=None, low=StructurePoint(time_utc=dt.datetime.now(UTC), price=1.08, kind=StructurePointKind.SWING_LOW))
    assert dealing_range.active_dealing_range_from_structure(result) is None


def test_active_dealing_range_none_when_degenerate():
    high = StructurePoint(time_utc=dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), price=1.0800, kind=StructurePointKind.SWING_HIGH)
    low = StructurePoint(time_utc=dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC), price=1.1000, kind=StructurePointKind.SWING_LOW)
    result = _structure_result(high=high, low=low)
    assert dealing_range.active_dealing_range_from_structure(result) is None


# ---------------------------------------------------------------------------
# P30 -- authority boundary / no duplicate engine
# ---------------------------------------------------------------------------


def test_orchestrator_imports_no_execution_or_authority_modules():
    import market_swing_structure.orchestrator as orch_module
    tree = ast.parse(open(orch_module.__file__, encoding="utf-8").read())
    forbidden_prefixes = ("execution", "authorization", "mt5.management_gateway", "trade_management")
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    for mod in imported:
        assert not any(mod == p or mod.startswith(p + ".") for p in forbidden_prefixes), (
            f"orchestrator.py imports forbidden module {mod!r}"
        )


def test_package_has_no_promotion_or_authorization_symbols():
    import market_swing_structure as mss
    forbidden_substrings = ("promote", "authorize", "submit_order", "place_order", "execute_trade")
    for module in (mss, mss.orchestrator, alignment, confirmation, dealing_range):
        names = [n.lower() for n in dir(module) if not n.startswith("_")]
        for forbidden in forbidden_substrings:
            assert not any(forbidden in n for n in names), f"{module.__name__} exposes forbidden symbol matching {forbidden!r}"


def test_result_authority_is_advisory_context_only():
    from market_swing_structure.models import AUTHORITY
    assert AUTHORITY == "ADVISORY_CONTEXT_ONLY"


def test_skill_local_analysis_cannot_replace_canonical_bos():
    # The engine's own BULLISH_BOS/BEARISH_BOS StructurePoint.kind values are relayed
    # verbatim by orchestrator._event() -- this package defines no alternative BOS
    # detector anywhere (see market_swing_structure/ directory: no swing/BOS math
    # outside confirmation.py's pure timestamp arithmetic and alignment.py's label
    # composition over already-computed states).
    import market_swing_structure.orchestrator as orch_module
    source = open(orch_module.__file__, encoding="utf-8").read()
    for forbidden in ("swing_highs_lows(", "bos_choch(", "smartmoneyconcepts"):
        assert forbidden not in source, f"orchestrator.py must not call smc primitives directly ({forbidden!r} found)"


# ---------------------------------------------------------------------------
# Live-guarded end-to-end smoke test (skipped, not failed, without MT5)
# ---------------------------------------------------------------------------


def _live_available() -> bool:
    try:
        from mt5.connection import MT5ConnectionError, connect
        connect()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _live_available(), reason="MT5 terminal not connected in this environment")
def test_analyze_live_eurusd_smoke():
    from market_swing_structure import analyze

    result = analyze("EURUSD", ("H4", "H1", "M15"))
    assert result.symbol == "EURUSD"
    assert result.authority == "ADVISORY_CONTEXT_ONLY"
    assert len(result.timeframes) == 3
    assert result.mtf_alignment != ""
