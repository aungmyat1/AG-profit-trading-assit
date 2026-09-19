"""TD-2: closed-candle acquisition tests for TopDownContext V1's six canonical
timeframes (W1/D1/H4/H1/M15/M5). Deterministic/unit tests need no live terminal; a
narrow live-MT5 smoke test (marked live_mt5) separately verifies real closed candles
on this dev box's connected account -- read-only, no order operation. See
docs/status/TD2_TOPDOWN_DATA_FOUNDATION_STATUS.md.
"""
from __future__ import annotations

import datetime as dt

import MetaTrader5 as mt5
import pytest

from mt5.market_data import _TIMEFRAMES
from mtf_context.topdown_contracts import (
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M1,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    TOPDOWN_TIMEFRAMES,
    InvalidTimeframeError,
)
from mtf_context.topdown_market_data import closed_snapshot_for_topdown_timeframe
from strategy_contract.market_snapshot import _TIMEFRAME_MINUTES


def _mt5_available() -> bool:
    return mt5.initialize()


# ---------------------------------------------------------------------------
# 1-6. Canonical TD-1 timeframe -> existing MT5 acquisition mapping
# ---------------------------------------------------------------------------

def test_w1_registered_in_mt5_acquisition_mapping():
    assert TIMEFRAME_W1 in _TIMEFRAMES
    assert _TIMEFRAMES[TIMEFRAME_W1] == mt5.TIMEFRAME_W1


@pytest.mark.parametrize("timeframe,mt5_constant", [
    (TIMEFRAME_D1, mt5.TIMEFRAME_D1),
    (TIMEFRAME_H4, mt5.TIMEFRAME_H4),
    (TIMEFRAME_H1, mt5.TIMEFRAME_H1),
    (TIMEFRAME_M15, mt5.TIMEFRAME_M15),
    (TIMEFRAME_M5, mt5.TIMEFRAME_M5),
])
def test_topdown_timeframe_already_registered_in_mt5_acquisition_mapping(timeframe, mt5_constant):
    """D1/H4/H1/M15/M5 were already present in mt5/market_data.py::_TIMEFRAMES before
    TD-2 (TD-0 audit finding) -- this proves that remains true, not that TD-2 added it."""
    assert timeframe in _TIMEFRAMES
    assert _TIMEFRAMES[timeframe] == mt5_constant


def test_w1_registered_in_market_snapshot_minute_mapping():
    assert TIMEFRAME_W1 in _TIMEFRAME_MINUTES
    assert _TIMEFRAME_MINUTES[TIMEFRAME_W1] == 7 * 24 * 60


# ---------------------------------------------------------------------------
# 7. M1 (and M30) remain backward-compatible -- unrestricted, unchanged
# ---------------------------------------------------------------------------

def test_m1_and_m30_remain_backward_compatible_in_mt5_acquisition_mapping():
    assert _TIMEFRAMES[TIMEFRAME_M1] == mt5.TIMEFRAME_M1
    assert _TIMEFRAMES["M30"] == mt5.TIMEFRAME_M30


def test_m1_remains_outside_topdown_context_v1_scope():
    assert TIMEFRAME_M1 not in TOPDOWN_TIMEFRAMES


# ---------------------------------------------------------------------------
# 9. Unsupported / out-of-scope timeframe fails closed before any I/O is attempted
# ---------------------------------------------------------------------------

def test_closed_snapshot_rejects_m1_before_any_io():
    """M1 is a valid MT5 timeframe but NOT one of TopDownContext V1's six -- this
    entrypoint must reject it even though the underlying acquisition call would
    succeed, proving the restriction is enforced here, not accidentally inherited."""
    with pytest.raises(InvalidTimeframeError):
        closed_snapshot_for_topdown_timeframe("EURUSD", TIMEFRAME_M1)


def test_closed_snapshot_rejects_unknown_timeframe_before_any_io():
    with pytest.raises(InvalidTimeframeError):
        closed_snapshot_for_topdown_timeframe("EURUSD", "W2")


# ---------------------------------------------------------------------------
# Live MT5 smoke verification (read-only, no order operation). Skips honestly if no
# terminal is connected -- never substitutes synthetic/replay data as evidence.
# ---------------------------------------------------------------------------

@pytest.mark.live_mt5
@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
@pytest.mark.parametrize("timeframe", list(TOPDOWN_TIMEFRAMES))
def test_live_closed_snapshot_for_each_topdown_timeframe(timeframe):
    from mt5.connection import connect

    connect()
    snapshot = closed_snapshot_for_topdown_timeframe("EURUSD", timeframe)

    assert snapshot.symbol == "EURUSD"
    assert snapshot.timeframe == timeframe
    assert snapshot.source == "VANTAGE_DEMO_MT5"
    assert snapshot.market_data_mode == "REAL"
    assert snapshot.is_closed is True
    # Forming-bar exclusion invariant: a genuinely closed bar's close time cannot be in
    # the future relative to wall-clock now -- if position=0 (the forming bar) had been
    # used instead of position=1, this could fail.
    assert snapshot.bar_close_time <= dt.datetime.now(dt.timezone.utc)
    assert snapshot.fingerprint  # non-empty deterministic identity
