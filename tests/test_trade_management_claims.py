"""Tests for trade_management.claims: JSON store round-trip + fail-closed rejections
(spec section 7/8). No MT5 connection needed -- NormalizedPosition is hand-built."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trade_management.claims import (
    REASON_ALREADY_CLAIMED,
    REASON_INVALID_DIRECTION,
    REASON_INVALID_R,
    REASON_SL_MISSING,
    claim_position,
    get_claim,
    load_claims,
)
from trade_management.models import NormalizedPosition


def _position(**overrides) -> NormalizedPosition:
    defaults = dict(
        ticket=123456789,
        symbol="EURUSD",
        direction="BUY",
        volume_initial=0.40,
        volume_current=0.40,
        entry_price=1.17000,
        current_bid=1.17010,
        current_ask=1.17012,
        current_price=1.17010,
        sl=1.16800,
        tp=None,
        profit=0.0,
        swap=0.0,
        commission=None,
        magic=0,
        comment="",
        open_time=datetime(2026, 8, 27, tzinfo=timezone.utc),
        account_login=1,
        account_server="Test-Demo",
    )
    defaults.update(overrides)
    return NormalizedPosition(**defaults)


def test_claim_round_trip(tmp_path):
    path = str(tmp_path / "claims.json")
    claim, reason = claim_position(_position(), tp1=1.17600, final_r_multiple=5.0, path=path)

    assert reason is None
    assert claim.ticket == 123456789
    assert claim.initial_r_distance == pytest.approx(0.00200)

    reloaded = get_claim(123456789, path=path)
    assert reloaded == claim


def test_claim_short_direction(tmp_path):
    path = str(tmp_path / "claims.json")
    position = _position(ticket=2, direction="SELL", entry_price=1.35000, sl=1.35250)
    claim, reason = claim_position(position, tp1=None, final_r_multiple=5.0, path=path)

    assert reason is None
    assert claim.initial_r_distance == pytest.approx(0.00250)


def test_claim_rejected_missing_sl(tmp_path):
    path = str(tmp_path / "claims.json")
    claim, reason = claim_position(_position(sl=None), tp1=None, final_r_multiple=5.0, path=path)
    assert claim is None
    assert reason == REASON_SL_MISSING


def test_claim_rejected_invalid_direction(tmp_path):
    path = str(tmp_path / "claims.json")
    claim, reason = claim_position(_position(direction="LONG"), tp1=None, final_r_multiple=5.0, path=path)
    assert claim is None
    assert reason == REASON_INVALID_DIRECTION


def test_claim_rejected_zero_risk_distance(tmp_path):
    path = str(tmp_path / "claims.json")
    # SL == entry -> R distance is 0, must be rejected, never silently accepted.
    claim, reason = claim_position(_position(sl=1.17000), tp1=None, final_r_multiple=5.0, path=path)
    assert claim is None
    assert reason == REASON_INVALID_R


def test_claim_rejected_wrong_side_sl_for_buy(tmp_path):
    path = str(tmp_path / "claims.json")
    # BUY with SL above entry -> negative R distance, must be rejected.
    claim, reason = claim_position(_position(sl=1.17500), tp1=None, final_r_multiple=5.0, path=path)
    assert claim is None
    assert reason == REASON_INVALID_R


def test_reclaiming_already_claimed_ticket_is_rejected(tmp_path):
    path = str(tmp_path / "claims.json")
    claim_position(_position(), tp1=None, final_r_multiple=5.0, path=path)
    claim, reason = claim_position(_position(), tp1=None, final_r_multiple=5.0, path=path)
    assert claim is None
    assert reason == REASON_ALREADY_CLAIMED


def test_load_claims_empty_when_no_file(tmp_path):
    path = str(tmp_path / "does_not_exist.json")
    assert load_claims(path) == {}
