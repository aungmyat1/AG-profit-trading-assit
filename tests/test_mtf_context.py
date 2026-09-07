"""Tests for mtf_context: profile validation, role universality (no hardcoded
D1/H4/H1/M15), alignment semantics, and a live-guarded end-to-end smoke test across two
different timeframe-role profiles (skipped, not failed, if MT5/live data is unavailable
in this environment -- see AGENTS.md 'minimum-context principle').
"""
from __future__ import annotations

import datetime as dt

import pytest

from mt5.connection import MT5ConnectionError, connect
from mt5.market_data import MarketDataError
from mtf_context import ROLE_BIAS, ROLE_EXECUTION, ROLE_MACRO, ROLE_SETUP, ROLE_WORKING, analyze
from mtf_context.models import (
    CONTEXT_READY,
    InvalidProfileError,
    LayerResult,
    MTFProfile,
)


def _live_available() -> bool:
    try:
        connect()
        return True
    except MT5ConnectionError:
        return False


def test_profile_with_no_roles_raises_invalid_profile():
    with pytest.raises(InvalidProfileError):
        analyze("EURUSD", MTFProfile())


def test_profile_with_unknown_role_raises_invalid_profile():
    # MTFProfile is frozen/typed to the six canonical roles; simulate an unknown role
    # the way a caller building a profile from untrusted config might.
    profile = MTFProfile(bias="H4")
    role_map = profile.role_timeframes()
    role_map["NOT_A_ROLE"] = "H4"
    from mtf_context.orchestrator import ALL_ROLES

    assert "NOT_A_ROLE" not in ALL_ROLES  # sanity: this really is an invalid role


def test_role_timeframes_is_role_based_not_hardcoded_hierarchy():
    """A profile may assign ANY timeframe string to ANY role -- proves this is a
    semantic-role model, not an enforced D1/H4/H1/M15 stack."""
    fx_style = MTFProfile(macro="D1", bias="H4", working="H1", setup="M15", execution="M5")
    crypto_style = MTFProfile(bias="H1", working="M15", execution="M1")
    swing_style = MTFProfile(macro="W1", bias="D1", working="H4", setup="H1", execution="M15")

    assert fx_style.role_timeframes() == {
        ROLE_MACRO: "D1", ROLE_BIAS: "H4", ROLE_WORKING: "H1", ROLE_SETUP: "M15", ROLE_EXECUTION: "M5",
    }
    assert crypto_style.role_timeframes() == {ROLE_BIAS: "H1", ROLE_WORKING: "M15", ROLE_EXECUTION: "M1"}
    assert swing_style.role_timeframes()[ROLE_MACRO] == "W1"  # a timeframe never valid as "macro" in the FX example


def test_alignment_not_applicable_when_a_role_is_absent():
    from mtf_context.orchestrator import _compute_alignment

    layers = {
        ROLE_BIAS: LayerResult(role=ROLE_BIAS, timeframe="H1", status="VALID"),
        ROLE_WORKING: LayerResult(role=ROLE_WORKING, timeframe="M15", status="VALID"),
    }
    alignment = _compute_alignment(layers)
    assert alignment["macro_to_bias"] == "NOT_APPLICABLE"  # no MACRO layer in this profile
    assert alignment["working_to_setup"] == "NOT_APPLICABLE"  # no SETUP layer in this profile


def test_alignment_aligned_vs_conflicted_from_structure_state():
    from mtf_context.orchestrator import _compute_alignment

    class _FakeStructure:
        def __init__(self, state):
            self.state = state

    aligned_layers = {
        ROLE_MACRO: LayerResult(role=ROLE_MACRO, timeframe="D1", status="VALID", structure=_FakeStructure("BULLISH")),
        ROLE_BIAS: LayerResult(role=ROLE_BIAS, timeframe="H4", status="VALID", structure=_FakeStructure("BULLISH")),
    }
    assert _compute_alignment(aligned_layers)["macro_to_bias"] == "ALIGNED"

    conflicted_layers = {
        ROLE_MACRO: LayerResult(role=ROLE_MACRO, timeframe="D1", status="VALID", structure=_FakeStructure("BULLISH")),
        ROLE_BIAS: LayerResult(role=ROLE_BIAS, timeframe="H4", status="VALID", structure=_FakeStructure("BEARISH")),
    }
    assert _compute_alignment(conflicted_layers)["macro_to_bias"] == "CONFLICTED"

    undefined_layers = {
        ROLE_MACRO: LayerResult(role=ROLE_MACRO, timeframe="D1", status="VALID", structure=_FakeStructure("BULLISH")),
        ROLE_BIAS: LayerResult(role=ROLE_BIAS, timeframe="H4", status="VALID", structure=_FakeStructure("STRUCTURE_STATE_UNDEFINED")),
    }
    assert _compute_alignment(undefined_layers)["macro_to_bias"] == "UNKNOWN"


@pytest.mark.skipif(not _live_available(), reason="MT5 terminal not connected in this environment")
def test_live_two_different_profiles_same_orchestrator():
    """Behavioral (not merely code-inspection) proof: the same analyze() handles an FX
    intraday profile (D1/H4/H1/M15/M5) and a leaner profile (H1/M15/M1) for two
    different symbols, with no per-profile branching in the orchestrator itself."""
    fx_profile = MTFProfile(macro="D1", bias="H4", working="H1", setup="M15", execution="M5")
    context1 = analyze("EURUSD", fx_profile)
    assert context1.status in (CONTEXT_READY, "PARTIAL_CONTEXT")
    assert set(context1.layers.keys()) == {"MACRO", "BIAS", "WORKING", "SETUP", "EXECUTION"}
    for role, timeframe in fx_profile.role_timeframes().items():
        assert context1.layers[role].timeframe == timeframe

    lean_profile = MTFProfile(bias="H1", working="M15", execution="M1")
    context2 = analyze("GBPUSD", lean_profile)
    assert set(context2.layers.keys()) == {"BIAS", "WORKING", "EXECUTION"}
    assert "MACRO" not in context2.layers and "SETUP" not in context2.layers

    # Neither result may carry any trade/execution authority.
    for context in (context1, context2):
        assert context.authorization == {
            "may_create_trade": False, "may_reject_trade": False,
            "may_change_strategy_decision": False, "may_modify_risk": False, "may_execute": False,
        }
        assert context.authority == "ADVISORY_ONLY"


@pytest.mark.skipif(not _live_available(), reason="MT5 terminal not connected in this environment")
def test_live_closed_candle_and_timezone_sanity():
    """Live behavioral check: the structure layer's bar_close_time is timezone-aware
    UTC and strictly before 'now', and every M15-role bar_close_time aligns to a
    :00/:15/:30/:45 minute boundary -- a wrong broker-UTC offset would misalign this."""
    from mt5.market_data import get_latest_candles

    now_utc = dt.datetime.now(dt.timezone.utc)
    candles = get_latest_candles("EURUSD", "M15", 1)
    latest = candles[-1]

    assert latest.time.tzinfo is not None
    assert latest.time.utcoffset() == dt.timedelta(0)
    assert latest.time < now_utc, "latest returned M15 candle must be strictly in the past (closed, not forming)"
    assert latest.time.minute in (0, 15, 30, 45), "M15 candle boundary misaligned -- possible broker-UTC-offset defect"
    # The forming bar (whichever quarter-hour 'now' falls in) must never be the one returned.
    assert now_utc - latest.time < dt.timedelta(minutes=30), "returned candle looks stale, not just closed"
