"""AG_STRATEGY_DIRECTION_CONTRACT_V1 core tests (P54/P55 subset -- M1 milestone scope
only). Does not test Session Trade migration (M3+, not attempted this milestone)."""
from __future__ import annotations

import dataclasses
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from daytrading.decision.models import MarketBias, MarketBiasDirection  # noqa: E402
from market_intelligence.models import (  # noqa: E402
    MarketBiasResult, InvalidBiasStateError, compute_input_fingerprint, make_decision_cycle_id,
)
from market_intelligence.bias_resolver import (  # noqa: E402
    resolve_from_daytrading_market_bias, resolve_unavailable,
)

DT = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)


def _bias(direction, **kw):
    return MarketBias(direction=direction, timeframe="H1", **kw)


# ---------------------------------------------------------------------------
# Invariant 2/31: exactly three states, unknowns fail closed.
# ---------------------------------------------------------------------------


def test_bullish_result():
    r = resolve_from_daytrading_market_bias(
        _bias(MarketBiasDirection.BULLISH.value, external_structure_direction="BULLISH"),
        "EURUSD", DT, "ASIAN_LONDON",
    )
    assert r.bias == "BULLISH"


def test_bearish_result():
    r = resolve_from_daytrading_market_bias(
        _bias(MarketBiasDirection.BEARISH.value, external_structure_direction="BEARISH"),
        "EURUSD", DT, "ASIAN_LONDON",
    )
    assert r.bias == "BEARISH"


def test_neutral_result():
    r = resolve_from_daytrading_market_bias(_bias(MarketBiasDirection.NEUTRAL.value), "EURUSD", DT, "ASIAN_LONDON")
    assert r.bias == "NEUTRAL"


def test_indeterminate_maps_to_neutral_not_a_fourth_state():
    r = resolve_from_daytrading_market_bias(
        _bias(MarketBiasDirection.INDETERMINATE.value), "EURUSD", DT, "ASIAN_LONDON",
    )
    assert r.bias == "NEUTRAL"  # fail-closed, never a raw INDETERMINATE leaking through


def test_unknown_label_fails_closed_never_raises_bullish_or_bearish():
    r = resolve_from_daytrading_market_bias(_bias("SOMETHING_ELSE"), "EURUSD", DT, "ASIAN_LONDON")
    assert r.bias == "NEUTRAL"


def test_invalid_bias_state_construction_rejected():
    with pytest.raises(InvalidBiasStateError):
        MarketBiasResult(
            bias="UPTREND", confidence="X", decision_cycle_id="X", symbol="EURUSD",
            decision_time=DT, htf_structure="X", mtf_alignment="X", liquidity_context="X",
            session_context="X", reason_codes=(), model_version="V1", input_fingerprint="X",
        )


# ---------------------------------------------------------------------------
# Missing data -> NEUTRAL (P32), never bullish/bearish by default.
# ---------------------------------------------------------------------------


def test_missing_data_resolves_unavailable_to_neutral():
    r = resolve_unavailable("EURUSD", DT, "ASIAN_LONDON", "INSUFFICIENT_H1_WARMUP")
    assert r.bias == "NEUTRAL"
    assert r.confidence == "UNAVAILABLE"
    assert "INSUFFICIENT_H1_WARMUP" in r.reason_codes


# ---------------------------------------------------------------------------
# Determinism / fingerprint stability.
# ---------------------------------------------------------------------------


def test_determinism_same_inputs_same_bias_and_fingerprint():
    a = resolve_from_daytrading_market_bias(
        _bias(MarketBiasDirection.BULLISH.value, protected_level=1.1000, protected_level_type="PROTECTED_LOW"),
        "EURUSD", DT, "ASIAN_LONDON",
    )
    b = resolve_from_daytrading_market_bias(
        _bias(MarketBiasDirection.BULLISH.value, protected_level=1.1000, protected_level_type="PROTECTED_LOW"),
        "EURUSD", DT, "ASIAN_LONDON",
    )
    assert a.bias == b.bias
    assert a.input_fingerprint == b.input_fingerprint


def test_input_fingerprint_changes_when_evidence_changes():
    base_fp = compute_input_fingerprint("A", "B", "C")
    changed_fp = compute_input_fingerprint("A", "B", "D")
    assert base_fp != changed_fp


# ---------------------------------------------------------------------------
# Immutability (P6) + timestamp integrity (P33).
# ---------------------------------------------------------------------------


def test_market_bias_result_is_frozen():
    r = resolve_unavailable("EURUSD", DT, "ASIAN_LONDON", "X")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.bias = "BULLISH"


def test_naive_decision_time_rejected():
    with pytest.raises(ValueError):
        resolve_unavailable("EURUSD", datetime(2026, 9, 10, 7, 0), "ASIAN_LONDON", "X")


# ---------------------------------------------------------------------------
# Invariant 11/12: bias carries no execution/entry fields whatsoever.
# ---------------------------------------------------------------------------


def test_market_bias_result_has_no_execution_fields():
    field_names = {f.name for f in dataclasses.fields(MarketBiasResult)}
    forbidden = {"entry_price", "stop_loss", "take_profit", "lot_size", "order_type", "entry", "tp", "sl"}
    assert field_names.isdisjoint(forbidden)


# ---------------------------------------------------------------------------
# Decision cycle identity (P7) -- reuses existing SYMBOL:DATE:CYCLE convention.
# ---------------------------------------------------------------------------


def test_decision_cycle_id_matches_existing_convention():
    cid = make_decision_cycle_id("EURUSD", date(2026, 9, 10), "ASIAN_LONDON")
    assert cid == "EURUSD:2026-09-10:ASIAN_LONDON"
