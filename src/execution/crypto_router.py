"""Domain router: (execution_domain, account_environment) -> a deterministic venue
descriptor. NO live connection is made anywhere in this module -- `route()` only ever
returns a labeled, deterministic dataclass built from string constants; nothing here
opens a socket, resolves DNS, or imports `requests`/`httpx`/`urllib`.

Covered cells:
  * The original 4 the spec named: FX+DEMO, FX+REAL, BINANCE_USDTM+DEMO,
    BINANCE_USDTM+REAL. Their values are frozen and asserted unchanged by
    tests/test_crypto_router.py::test_original_four_cells_are_unchanged.
  * MT5_CRYPTO+DEMO / MT5_CRYPTO+REAL, added additively by
    AG_VANTAGE_MT5_CRYPTO_VENUE_V1 (2026-09-13) so an MT5-hosted crypto CFD order
    (Vantage's BTCUSD/ETHUSD, canonical BTCUSDT/ETHUSDT) can be LABELLED/journaled
    distinctly from the Binance USDT-M crypto path. Shaped exactly like the MT5_FX
    cells (base_url=None -- MT5 is a terminal API, not a REST base URL). This is a
    labeling/observability concept only: `route()` has no production caller in this
    repository (verified by grep -- only this module's own test imports it), so adding
    these cells grants no execution authority to anything and changes no existing
    behavior. In particular the manual MT5 demo execution bridge
    (scripts/web_execute_trade.py -> assistant.commands.execute_command ->
    execution.executor.execute) does NOT consult this router for FX today and is
    deliberately not made to consult it for crypto either -- routing a symbol through
    this module is not a prerequisite for, nor a grant of, order-submission authority.

No fallback/default for any input -- an unknown domain, unknown environment, or unknown
combination is an explicit, typed rejection (UnroutableExecutionTarget), never a
best-guess default route.
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
# MT5-hosted crypto CFDs (Vantage BTCUSD/ETHUSD). A separate domain from both MT5_FX
# (different asset class / contract shape: contract_size=1, tick_size=0.01) and
# BINANCE_USDTM (different venue entirely, different execution adapter) -- deliberately
# NOT folded into either, so a journal/reconciliation reader can always tell which of
# the two crypto venues an entry belongs to.
DOMAIN_MT5_CRYPTO = "MT5_CRYPTO"

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
    # --- AG_VANTAGE_MT5_CRYPTO_VENUE_V1 (2026-09-13), additive ------------------------
    # Same shape as the MT5_FX cells above (base_url=None, "<VENUE>_<ENV>_BROKER" label
    # pattern). Adding these does not authorize anything: see module docstring.
    (DOMAIN_MT5_CRYPTO, ENVIRONMENT_DEMO): VenueDescriptor(
        DOMAIN_MT5_CRYPTO, ENVIRONMENT_DEMO, "MT5_CRYPTO_DEMO_BROKER", None,
    ),
    (DOMAIN_MT5_CRYPTO, ENVIRONMENT_REAL): VenueDescriptor(
        DOMAIN_MT5_CRYPTO, ENVIRONMENT_REAL, "MT5_CRYPTO_REAL_BROKER", None,
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
