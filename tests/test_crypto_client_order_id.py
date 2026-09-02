"""Tests for execution/crypto_client_order_id.py: deterministic generation, charset,
length, and collision behavior. Never sent anywhere -- these tests only call the pure
generator function."""
from __future__ import annotations

import pytest

from execution.crypto_client_order_id import (
    MAX_CLIENT_ORDER_ID_LEN,
    _VALID_CHARS,
    generate_client_order_id,
)


def test_deterministic_for_same_identity():
    a = generate_client_order_id("cmd-1", "occ-1")
    b = generate_client_order_id("cmd-1", "occ-1")
    assert a == b


def test_different_identity_produces_different_id():
    a = generate_client_order_id("cmd-1", "occ-1")
    b = generate_client_order_id("cmd-2", "occ-1")
    c = generate_client_order_id("cmd-1", "occ-2")
    assert len({a, b, c}) == 3


def test_charset_is_valid_for_binance_client_order_id():
    generated = generate_client_order_id("cmd-1", "occ-1")
    assert _VALID_CHARS.match(generated)


def test_length_well_under_binance_max():
    generated = generate_client_order_id("cmd-1", "occ-1")
    assert len(generated) <= MAX_CLIENT_ORDER_ID_LEN
    assert len(generated) < MAX_CLIENT_ORDER_ID_LEN  # strictly under, not just at the cap


def test_no_collisions_across_many_ids():
    ids = {generate_client_order_id(f"cmd-{i}", f"occ-{i}") for i in range(2000)}
    assert len(ids) == 2000


def test_empty_identity_rejected():
    with pytest.raises(ValueError):
        generate_client_order_id("", "occ-1")
    with pytest.raises(ValueError):
        generate_client_order_id("cmd-1", "")
