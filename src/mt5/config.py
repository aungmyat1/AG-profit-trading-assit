"""Canonical MT5 broker/account configuration -- the one place credential environment
variables are read. Populated from src/.env in development (python-dotenv, loaded once,
never overriding a variable the process environment already sets).

Demo credentials are read from VANTAGE-DEMO-LOGIN / VANTAGE-DEMO_PASSWORD /
VANTAGE-DEMO_SERVER (src/.env's own naming, mirroring its pre-existing
VANTAGE-LIVE/VANTAGE-LIVE-PASSWORD/VANTAGE-SERVER Live-section keys, which this module
does not read -- MT5_ENVIRONMENT only ever selects DEMO here; wiring LIVE credentials
in is a separate, explicitly-scoped change, not part of this loader).

Strategy code must never import this module directly (AGENTS.md Authority order):
only infrastructure -- mt5/, execution/ -- reads broker identity/credentials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
_loaded = False

BROKER_VANTAGE = "VANTAGE"
ENVIRONMENT_DEMO = "DEMO"
ENVIRONMENT_LIVE = "LIVE"
_VALID_ENVIRONMENTS = (ENVIRONMENT_DEMO, ENVIRONMENT_LIVE)


class MT5ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class MT5Config:
    broker: str
    environment: str
    login: int
    password: str
    server: str
    terminal_path: Optional[str]


def _ensure_env_loaded() -> None:
    global _loaded
    if not _loaded:
        load_dotenv(_ENV_PATH, override=False)
        _loaded = True


def load_mt5_config() -> MT5Config:
    """Fail-closed: raises MT5ConfigError naming the first missing/invalid required
    variable. Never includes the password value in any exception message."""
    _ensure_env_loaded()

    broker = os.environ.get("MT5_BROKER", "").strip()
    if not broker:
        raise MT5ConfigError("CONFIG_ERROR: MT5_BROKER is not set")

    environment = os.environ.get("MT5_ENVIRONMENT", "").strip().upper()
    if environment not in _VALID_ENVIRONMENTS:
        raise MT5ConfigError(
            f"CONFIG_ERROR: MT5_ENVIRONMENT must be one of {_VALID_ENVIRONMENTS}, got {environment!r}"
        )
    if environment == ENVIRONMENT_LIVE:
        # This loader only ever reads the VANTAGE-DEMO-* credential keys below -- wiring
        # a LIVE credential source in is a separate, explicitly-scoped change (never done
        # implicitly). Fail closed rather than silently falling back to Demo values.
        raise MT5ConfigError(
            "CONFIG_ERROR: MT5_ENVIRONMENT=LIVE is not supported by this loader "
            "(no LIVE credential source is wired in) -- refusing to proceed"
        )

    login_raw = os.environ.get("VANTAGE-DEMO-LOGIN", "").strip()
    if not login_raw:
        raise MT5ConfigError("CONFIG_ERROR: VANTAGE-DEMO-LOGIN is not set")
    try:
        login = int(login_raw)
    except ValueError:
        raise MT5ConfigError("CONFIG_ERROR: VANTAGE-DEMO-LOGIN is not a valid integer") from None

    password = os.environ.get("VANTAGE-DEMO_PASSWORD", "")
    if not password:
        raise MT5ConfigError("CONFIG_ERROR: VANTAGE-DEMO_PASSWORD is not set")

    server = os.environ.get("VANTAGE-DEMO_SERVER", "").strip()
    if not server:
        raise MT5ConfigError("CONFIG_ERROR: VANTAGE-DEMO_SERVER is not set")

    terminal_path = os.environ.get("MT5_TERMINAL_PATH", "").strip() or None

    return MT5Config(
        broker=broker,
        environment=environment,
        login=login,
        password=password,
        server=server,
        terminal_path=terminal_path,
    )
