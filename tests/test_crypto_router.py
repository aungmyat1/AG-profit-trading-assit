"""Tests for execution/crypto_router.py: the domain router. No live connection is made
anywhere -- asserted by construction (route() only ever returns string constants).

Originally a 4-cell table (MT5_FX x {DEMO,REAL}, BINANCE_USDTM x {DEMO,REAL}).
AG_VANTAGE_MT5_CRYPTO_VENUE_V1 (2026-09-13) added MT5_CRYPTO x {DEMO,REAL} additively;
test_original_four_cells_are_unchanged below pins the original four so that addition can
never silently alter them."""
from __future__ import annotations

import pytest

from execution.crypto_router import (
    BINANCE_USDTM_TESTNET_BASE_URL,
    DOMAIN_BINANCE_USDTM,
    DOMAIN_MT5_CRYPTO,
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


# --- AG_VANTAGE_MT5_CRYPTO_VENUE_V1: the original 4 cells are frozen -----------------

def test_original_four_cells_are_unchanged():
    """Regression pin: the 4 cells that existed before MT5_CRYPTO was added must keep
    their exact execution_domain / account_environment / venue_label / base_url values.
    Any future additive venue work that perturbs one of these fails here."""
    expected = {
        (DOMAIN_MT5_FX, ENVIRONMENT_DEMO): ("MT5_DEMO_BROKER", None),
        (DOMAIN_MT5_FX, ENVIRONMENT_REAL): ("MT5_REAL_BROKER", None),
        (DOMAIN_BINANCE_USDTM, ENVIRONMENT_DEMO): ("BINANCE_USDTM_TESTNET", "https://testnet.binancefuture.com"),
        (DOMAIN_BINANCE_USDTM, ENVIRONMENT_REAL): ("BINANCE_USDTM_PRODUCTION", "https://fapi.binance.com"),
    }
    for (domain, env), (label, base_url) in expected.items():
        descriptor = route(domain, env)
        assert descriptor.execution_domain == domain
        assert descriptor.account_environment == env
        assert descriptor.venue_label == label
        assert descriptor.base_url == base_url


@pytest.mark.parametrize("env,expected_label", [
    (ENVIRONMENT_DEMO, "MT5_CRYPTO_DEMO_BROKER"),
    (ENVIRONMENT_REAL, "MT5_CRYPTO_REAL_BROKER"),
])
def test_mt5_crypto_cells_exist_and_mirror_the_mt5_fx_shape(env, expected_label):
    descriptor = route(DOMAIN_MT5_CRYPTO, env)
    assert descriptor.execution_domain == DOMAIN_MT5_CRYPTO
    assert descriptor.account_environment == env
    assert descriptor.venue_label == expected_label
    # base_url is None for every MT5 domain -- MT5 is a terminal API, not a REST base URL.
    assert descriptor.base_url is None
    assert route(DOMAIN_MT5_FX, env).base_url is None


def test_mt5_crypto_is_a_distinct_domain_from_both_mt5_fx_and_binance():
    """The new cells must be separately identifiable in a journal/reconciliation read --
    never collapsed into the FX domain or into the Binance crypto domain."""
    assert DOMAIN_MT5_CRYPTO not in (DOMAIN_MT5_FX, DOMAIN_BINANCE_USDTM)
    crypto = route(DOMAIN_MT5_CRYPTO, ENVIRONMENT_DEMO)
    assert crypto.venue_label != route(DOMAIN_MT5_FX, ENVIRONMENT_DEMO).venue_label
    assert crypto.venue_label != route(DOMAIN_BINANCE_USDTM, ENVIRONMENT_DEMO).venue_label


@pytest.mark.parametrize("domain,env", [
    ("UNKNOWN_DOMAIN", ENVIRONMENT_DEMO),
    (DOMAIN_MT5_CRYPTO, "UNKNOWN_ENV"),
    ("MT5_CRYPTO_DEMO", ENVIRONMENT_DEMO),   # venue_label is not a domain key
    ("mt5_crypto", ENVIRONMENT_DEMO),         # exact-match only, no case folding
    (DOMAIN_BINANCE_USDTM, "UNKNOWN_ENV"),
    ("", ""),
    (None, None),
])
def test_unknown_combinations_are_explicitly_rejected_no_fallback(domain, env):
    with pytest.raises(UnroutableExecutionTarget):
        route(domain, env)
