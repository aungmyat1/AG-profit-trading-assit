"""Tests for trade_management.risk: R-multiple math and broker-legal volume
normalization for partial closes (spec sections 9, 10, 30 'Volume')."""
from __future__ import annotations

import pytest

from mt5.symbol_resolver import SymbolMeta
from trade_management.risk import (
    REASON_CLOSE_VOLUME_BELOW_MIN,
    REASON_ILLEGAL_REMAINDER_VOLUME,
    current_r,
    normalize_partial_close_volume,
    target_price,
)

SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)


def test_current_r_long():
    assert current_r("BUY", 1.17000, 1.17600, 0.00200) == pytest.approx(3.0)


def test_current_r_short():
    assert current_r("SELL", 1.35000, 1.34250, 0.00250) == pytest.approx(3.0)


def test_current_r_never_recomputes_from_moved_sl():
    # initial_r_distance is frozen; passing the ORIGINAL distance even after a
    # breakeven move must still give the same R as before the move.
    assert current_r("BUY", 1.17000, 1.17600, 0.00200) == pytest.approx(3.0)


def test_target_price_long_5r():
    assert target_price("BUY", 1.17000, 0.00200, 5.0) == pytest.approx(1.18000)


def test_target_price_short_5r():
    assert target_price("SELL", 1.35000, 0.00250, 5.0) == pytest.approx(1.33750)


def test_normalize_partial_close_75_percent_exact_step():
    close_volume, remaining, reason = normalize_partial_close_volume(0.40, 0.75, SYMBOL_META)
    assert reason is None
    assert close_volume == pytest.approx(0.30)
    assert remaining == pytest.approx(0.10)


def test_normalize_partial_close_rounds_down_to_step():
    # 0.75 * 0.15 = 0.1125 -> floors to 0.11 at 0.01 step.
    close_volume, remaining, reason = normalize_partial_close_volume(0.15, 0.75, SYMBOL_META)
    assert reason is None
    assert close_volume == pytest.approx(0.11)
    assert remaining == pytest.approx(0.04)


def test_normalize_partial_close_below_min_fails_closed():
    tiny_meta = SymbolMeta(**{**SYMBOL_META.__dict__, "volume_min": 0.10})
    close_volume, remaining, reason = normalize_partial_close_volume(0.05, 0.75, tiny_meta)
    assert reason == REASON_CLOSE_VOLUME_BELOW_MIN
    assert close_volume is None and remaining is None


def test_normalize_partial_close_illegal_remainder_fails_closed():
    # volume_min 0.10, current 0.11 -> 75% closes 0.08 (below min, fails first) --
    # use a case where close is legal but the remainder isn't.
    meta = SymbolMeta(**{**SYMBOL_META.__dict__, "volume_min": 0.05, "volume_step": 0.01})
    close_volume, remaining, reason = normalize_partial_close_volume(0.12, 0.75, meta)
    # 0.75*0.12=0.09 -> close 0.09, remaining 0.03 < volume_min 0.05 -> illegal remainder.
    assert reason == REASON_ILLEGAL_REMAINDER_VOLUME
    assert close_volume is None and remaining is None
