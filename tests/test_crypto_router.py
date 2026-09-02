"""Tests for execution/crypto_router.py: the 4-cell domain router. No live connection is
made anywhere -- asserted by construction (route() only ever returns string constants)."""
from __future__ import annotations

import pytest

from execution.crypto_router import (
    BINANCE_USDTM_TESTNET_BASE_URL,
    DOMAIN_BINANCE_USDTM,
    DOMAIN_MT5_FX,
    ENVIRONMENT_DEMO,
    ENVIRONMENT_REAL,
    UnroutableExecutionTarget,
    route,
)
from execution_runtime.binance_usdtm_feed import FAPI_BASE_URL


def test_fx_demo_route():
    descriptor = route(DOMAIN_MT5_FX, ENVIRONMENT_DEMO)
    assert descriptor.venue_label == "MT5_DEMO_BROKER"
    assert descriptor.base_url is None


def test_fx_real_route():
    descriptor = route(DOMAIN_MT5_FX, ENVIRONMENT_REAL)
    assert descriptor.venue_label == "MT5_REAL_BROKER"
    assert descriptor.base_url is None


def test_binance_usdtm_demo_routes_to_testnet():
    descriptor = route(DOMAIN_BINANCE_USDTM, ENVIRONMENT_DEMO)
    assert descriptor.venue_label == "BINANCE_USDTM_TESTNET"
    assert descriptor.base_url == BINANCE_USDTM_TESTNET_BASE_URL
    assert descriptor.base_url == "https://testnet.binancefuture.com"


def test_binance_usdtm_real_routes_to_production():
    descriptor = route(DOMAIN_BINANCE_USDTM, ENVIRONMENT_REAL)
    assert descriptor.venue_label == "BINANCE_USDTM_PRODUCTION"
    assert descriptor.base_url == FAPI_BASE_URL
    assert descriptor.base_url == "https://fapi.binance.com"


def test_testnet_and_production_urls_are_independently_defined_constants():
    """The testnet URL must be its own constant, not derived from the production one by
    string substitution or a boolean flag."""
    assert BINANCE_USDTM_TESTNET_BASE_URL != FAPI_BASE_URL
    assert "testnet" in BINANCE_USDTM_TESTNET_BASE_URL


@pytest.mark.parametrize("domain,env", [
    ("UNKNOWN_DOMAIN", ENVIRONMENT_DEMO),
    (DOMAIN_BINANCE_USDTM, "UNKNOWN_ENV"),
    ("", ""),
    (None, None),
])
def test_unknown_combinations_are_explicitly_rejected_no_fallback(domain, env):
    with pytest.raises(UnroutableExecutionTarget):
        route(domain, env)
