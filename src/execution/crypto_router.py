"""Domain router: (execution_domain, account_environment) -> a deterministic venue
descriptor. NO live connection is made anywhere in this module -- `route()` only ever
returns a labeled, deterministic dataclass built from string constants; nothing here
opens a socket, resolves DNS, or imports `requests`/`httpx`/`urllib`.

Covers exactly the 4 cells the spec names: FX+DEMO, FX+REAL, BINANCE_USDTM+DEMO,
BINANCE_USDTM+REAL. No fallback/default for any input -- an unknown domain, unknown
environment, or unknown combination is an explicit, typed rejection (UnroutableExecutionTarget),
never a best-guess default route.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from execution_runtime.binance_usdtm_feed import FAPI_BASE_URL

# Binance USDT-M Futures TESTNET base URL -- a new, explicit constant (per spec: "add the
# testnet one as a new explicit constant, do not derive it from the production one by
# string substitution or a boolean flag"). Recalled from prior discovery in this project;
# FAPI_BASE_URL (production, "https://fapi.binance.com") is imported, not duplicated, from
# execution_runtime/binance_usdtm_feed.py -- the module that already owns that constant.
BINANCE_USDTM_TESTNET_BASE_URL = "https://testnet.binancefuture.com"

DOMAIN_MT5_FX = "MT5_FX"
DOMAIN_BINANCE_USDTM = "BINANCE_USDTM"

ENVIRONMENT_DEMO = "DEMO"
ENVIRONMENT_REAL = "REAL"


class UnroutableExecutionTarget(RuntimeError):
    """Raised by route() for any (execution_domain, account_environment) pair that is not
    one of the 4 explicitly-registered cells -- deliberately no fallback/default route."""


@dataclass(frozen=True)
class VenueDescriptor:
    execution_domain: str
    account_environment: str
    venue_label: str
    # None for MT5_FX: MT5 is not a REST-base-URL concept in this repo (broker connection
    # is via the MetaTrader5 terminal API, not an HTTP base URL) -- left explicitly None
    # rather than inventing a placeholder URL that nothing would ever call.
    base_url: Optional[str]


_ROUTES = {
    (DOMAIN_MT5_FX, ENVIRONMENT_DEMO): VenueDescriptor(
        DOMAIN_MT5_FX, ENVIRONMENT_DEMO, "MT5_DEMO_BROKER", None,
    ),
    (DOMAIN_MT5_FX, ENVIRONMENT_REAL): VenueDescriptor(
        DOMAIN_MT5_FX, ENVIRONMENT_REAL, "MT5_REAL_BROKER", None,
    ),
    (DOMAIN_BINANCE_USDTM, ENVIRONMENT_DEMO): VenueDescriptor(
        DOMAIN_BINANCE_USDTM, ENVIRONMENT_DEMO, "BINANCE_USDTM_TESTNET", BINANCE_USDTM_TESTNET_BASE_URL,
    ),
    (DOMAIN_BINANCE_USDTM, ENVIRONMENT_REAL): VenueDescriptor(
        DOMAIN_BINANCE_USDTM, ENVIRONMENT_REAL, "BINANCE_USDTM_PRODUCTION", FAPI_BASE_URL,
    ),
}


def route(execution_domain: str, account_environment: str) -> VenueDescriptor:
    """Deterministic, offline lookup only -- see module docstring. Raises
    UnroutableExecutionTarget for anything not one of the 4 registered cells."""
    key = (execution_domain, account_environment)
    descriptor = _ROUTES.get(key)
    if descriptor is None:
        raise UnroutableExecutionTarget(
            f"no route registered for execution_domain={execution_domain!r}, "
            f"account_environment={account_environment!r}"
        )
    return descriptor
