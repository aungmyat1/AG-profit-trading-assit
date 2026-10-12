"""OD1012-ACCOUNT runtime account pin (read-only, no broker calls).

The ticket/scan runtime reads ``account_info`` once at start and evaluates only when the connected
terminal is the pinned account: server, login suffix and DEMO trade mode must all match
``config/account_pin.yaml``. Anything else, including a missing or malformed pin or account read,
fails closed with ``ACCOUNT_PIN_MISMATCH``. The detail never carries the login, balance or equity.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = Path("config/account_pin.yaml")
ACCOUNT_PIN_MISMATCH = "ACCOUNT_PIN_MISMATCH"
ACCOUNT_PIN_VERIFIED = "ACCOUNT_PIN_VERIFIED"


def load_pin(root: Path = REPO_ROOT) -> Optional[dict]:
    """The committed pin, or None when missing/malformed (callers fail closed)."""
    try:
        raw = yaml.safe_load((Path(root) / PIN_PATH).read_text(encoding="utf-8")) or {}
        pin = raw["account_pin"]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return None
    suffix, server = pin.get("login_suffix"), pin.get("server")
    if not (isinstance(suffix, str) and suffix.isdigit() and 3 <= len(suffix) <= 4
            and isinstance(server, str) and server and pin.get("trade_mode") == "DEMO"):
        return None
    return pin


def check_account(info: Any, pin: Optional[dict], demo_trade_mode: Any) -> Tuple[bool, str]:
    """(ok, status). ``info`` is MT5 account_info() (or None); ``demo_trade_mode`` is
    ``mt5.ACCOUNT_TRADE_MODE_DEMO``. Status is ACCOUNT_PIN_VERIFIED or ``ACCOUNT_PIN_MISMATCH <reason>``."""
    if pin is None:
        return False, f"{ACCOUNT_PIN_MISMATCH} PIN_UNAVAILABLE"
    if info is None:
        return False, f"{ACCOUNT_PIN_MISMATCH} ACCOUNT_INFO_UNAVAILABLE"
    if getattr(info, "server", None) != pin["server"]:
        return False, f"{ACCOUNT_PIN_MISMATCH} SERVER"
    login = getattr(info, "login", None)
    if login is None or not str(login).endswith(pin["login_suffix"]):
        return False, f"{ACCOUNT_PIN_MISMATCH} LOGIN_SUFFIX"
    if getattr(info, "trade_mode", None) != demo_trade_mode:
        return False, f"{ACCOUNT_PIN_MISMATCH} TRADE_MODE"
    return True, ACCOUNT_PIN_VERIFIED
