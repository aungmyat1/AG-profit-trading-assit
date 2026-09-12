"""AG_ST_SESSION_SWEEP_CONTINUATION_REPLAY_BLOCKER_REMEDIATION -- R20/R21.

Proves MarketBiasResult is the ONE final directional authority for this strategy:
regime.py's own TREND/RANGE/TRANSITION classification still decides which setup
BRANCH is eligible (unchanged, not tested here -- see the pre-existing
test_session_sweep_continuation_setups.py / test_session_sweep_continuation_regime.py),
but never which DIRECTION is allowed. bias_gate.py decides direction, and only it.
"""
from datetime import date, datetime, timedelta, timezone

from market_intelligence.models import MarketBiasResult
from session_sweep_continuation.bias_gate import (
    BIAS_DIRECTION_MISMATCH,
    BIAS_MISSING,
    BIAS_SYMBOL_MISMATCH,
    LONG,
    NO_TRADE,
    SHORT,
    allowed_directions,
    rejection_reason,
)
from session_sweep_continuation.config import load_config
from session_sweep_continuation.replay import run_replay
from strategy_engine.session.candles import Candle

PIP = 0.0001
DAY = date(2026, 9, 10)
SYMBOL = "EURUSD"


def _bias(bias: str, symbol: str = SYMBOL):
    return MarketBiasResult(
        bias=bias, confidence="EVIDENCE_BACKED",
        decision_cycle_id=f"{symbol}:{DAY}:ASIAN_LONDON",
        symbol=symbol, decision_time=datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc),
        htf_structure="TEST_FIXTURE", mtf_alignment="NOT_EVALUATED_M1",
        liquidity_context="NOT_EVALUATED_M1", session_context="NOT_EVALUATED_M1",
        reason_codes=("TEST_FIXTURE",), model_version="TEST_FIXTURE", input_fingerprint="TEST_FIXTURE",
    )


def _unavailable_bias(symbol: str = SYMBOL):
    # Mirrors market_intelligence.bias_resolver.resolve_unavailable: UNAVAILABLE
    # confidence, bias forced to NEUTRAL -- MarketBiasResult structurally cannot carry
    # a fourth bias state (InvalidBiasStateError).
    return MarketBiasResult(
        bias="NEUTRAL", confidence="UNAVAILABLE",
        decision_cycle_id=f"{symbol}:{DAY}:ASIAN_LONDON",
        symbol=symbol, decision_time=datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc),
        htf_structure="NOT_EVALUATED_M1", mtf_alignment="NOT_EVALUATED_M1",
        liquidity_context="NOT_EVALUATED_M1", session_context="NOT_EVALUATED_M1",
        reason_codes=("NO_H1_DATA",), model_version="TEST_FIXTURE", input_fingerprint="TEST_FIXTURE",
    )


# --- R20: pure bias-authority unit tests --------------------------------------------

def test_bullish_permits_long_only():
    assert allowed_directions(_bias("BULLISH"), SYMBOL) == LONG


def test_bearish_permits_short_only():
    assert allowed_directions(_bias("BEARISH"), SYMBOL) == SHORT


def test_neutral_permits_nothing():
    assert allowed_directions(_bias("NEUTRAL"), SYMBOL) == NO_TRADE


def test_unavailable_permits_nothing():
    assert allowed_directions(_unavailable_bias(), SYMBOL) == NO_TRADE


def test_missing_bias_permits_nothing():
    assert allowed_directions(None, SYMBOL) == NO_TRADE
    assert rejection_reason(None, SYMBOL) == BIAS_MISSING


def test_symbol_mismatch_permits_nothing():
    mismatched = _bias("BULLISH", symbol="GBPUSD")
    assert allowed_directions(mismatched, SYMBOL) == NO_TRADE
    assert rejection_reason(mismatched, SYMBOL) == BIAS_SYMBOL_MISMATCH


def test_neutral_rejection_reason_is_direction_mismatch():
    assert rejection_reason(_bias("NEUTRAL"), SYMBOL) == BIAS_DIRECTION_MISMATCH


# --- R21: branch-level integration -- opposite-direction candidate is blocked -------

def _build_synthetic_range_and_sweep_day(sweep_low: bool):
    """One tight ASIAN reference range, then either a low-side sweep-and-reclaim
    (candidate direction LONG) or a high-side sweep-and-reclaim (candidate direction
    SHORT) in the LONDON trade session -- the same S1 shape
    test_session_sweep_continuation_replay_determinism.py already exercises for LONG,
    mirrored here for SHORT so both directions are covered against bias gating."""
    candles = []
    t0 = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    price = 1.1000
    for i in range(24):
        t = t0 + timedelta(minutes=15 * i)
        o = price
        h = price + 0.0004
        l = price - 0.0004
        c = price + (0.0001 if i % 2 == 0 else -0.0001)
        candles.append(Candle(t, o, h, l, c))
        price = c

    ref_high = max(c.high for c in candles)
    ref_low = min(c.low for c in candles)

    t_trade0 = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)
    for i in range(16):
        t = t_trade0 + timedelta(minutes=15 * i)
        if i == 0:
            if sweep_low:
                o, h, l, c = 1.1000, 1.1005, ref_low - 0.0010, 1.1000
            else:
                # low must stay strictly above ref_low, else this candle would also
                # swept_low and setups.py's own dual-side AMBIGUOUS_NO_TRADE guard
                # would fire, producing no candidate at all (not the SHORT candidate
                # this fixture intends to test).
                o, h, l, c = 1.1000, ref_high + 0.0010, ref_low + 0.0002, 1.1000
        else:
            o, h, l, c = 1.1000, 1.1006, 1.0994, 1.1000
        candles.append(Candle(t, o, h, l, c))
    return candles


def _config():
    cfg = dict(load_config(repo_root="."))
    cfg["regime"] = dict(cfg["regime"])
    cfg["regime"]["ema_fast_period"] = 3
    cfg["regime"]["ema_slow_period"] = 5
    cfg["regime"]["min_reference_candles"] = 8
    return cfg


def test_bearish_blocks_a_structurally_valid_long_s1_candidate():
    """The S1 sweep-low -> LONG candidate is structurally valid (regime RANGE, wick
    breach + close-back-inside) exactly as in the BULLISH-bias determinism fixture --
    but under a BEARISH bias it must be rejected, never overridden."""
    candles = _build_synthetic_range_and_sweep_day(sweep_low=True)
    result = run_replay(candles, _config(), SYMBOL, "ASIAN_LONDON", DAY, PIP, bias_result=_bias("BEARISH"))
    assert result.campaign is None
    assert any(r.get("direction") == "LONG" and r.get("reason") == BIAS_DIRECTION_MISMATCH for r in result.rejected_setups)


def test_bullish_blocks_a_structurally_valid_short_s1_candidate():
    candles = _build_synthetic_range_and_sweep_day(sweep_low=False)
    result = run_replay(candles, _config(), SYMBOL, "ASIAN_LONDON", DAY, PIP, bias_result=_bias("BULLISH"))
    assert result.campaign is None
    assert any(r.get("direction") == "SHORT" and r.get("reason") == BIAS_DIRECTION_MISMATCH for r in result.rejected_setups)


def test_bearish_permits_the_matching_short_s1_candidate():
    """Sanity check: BEARISH does not block a direction-consistent SHORT candidate --
    proves R6 is a directional filter, not a blanket suppression."""
    candles = _build_synthetic_range_and_sweep_day(sweep_low=False)
    result = run_replay(candles, _config(), SYMBOL, "ASIAN_LONDON", DAY, PIP, bias_result=_bias("BEARISH"))
    assert not any(r.get("reason") == BIAS_DIRECTION_MISMATCH for r in result.rejected_setups)
