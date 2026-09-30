"""Shared helpers for the Windows MT5 host go-live kit (scripts/host/*).

Read-only by construction: nothing here, or in any scripts/host module, calls order_send,
order_check or any position function (tests/test_host_go_live_kit.py enforces this
statically). Secrets are never printed. redact() masks any value taken from a *TOKEN*,
*PASSWORD*, *SECRET* or *KEY* environment variable.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from contextlib import contextmanager
from typing import Iterator

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LOG_DIR = os.path.join(REPO_ROOT, "logs")
_SECRET_MARKERS = ("TOKEN", "PASSWORD", "SECRET", "KEY")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def redact(text: str) -> str:
    for name, value in os.environ.items():
        if value and len(value) >= 6 and any(m in name.upper() for m in _SECRET_MARKERS):
            text = text.replace(value, "***")
    return text


def log_line(name: str, message: str) -> None:
    """Append one redacted line to logs/<name>.log and echo it."""
    line = redact(f"{utcnow().isoformat()} {message}")
    print(line)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"{name}.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def single_instance(name: str, stale_after_s: int = 1800) -> Iterator[None]:
    """O_EXCL lock file in logs/. A lock older than `stale_after_s` (a crashed run) is broken."""
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"{name}.lock")
    try:
        if time.time() - os.path.getmtime(path) > stale_after_s:
            os.remove(path)
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AlreadyRunning(name) from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def import_mt5():
    """Return the real MetaTrader5 module or None. Never falls back to the test stub."""
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except Exception:  # noqa: BLE001
        return None
    names = getattr(mt5, "__dict__", {})
    stub = ("MT5StubOperationAttempted" in names
            or str(getattr(mt5, "__file__", "") or "").endswith(os.path.join(REPO_ROOT, "MetaTrader5.py")))
    if stub or "initialize" not in names:
        return None
    return mt5


def mt5_initialize(mt5, terminal_path: str = "") -> "tuple[bool, str]":
    """initialize() against the VT Markets demo terminal. Credentials come only from the
    environment (VTMARKETS-DEMO-LOGIN / VTMARKETS_DEMO_LOGIN / MT5_LOGIN, etc.). The
    password is passed to MT5 and never printed."""
    kwargs = {}
    path = terminal_path or os.environ.get("MT5_TERMINAL_PATH", "")
    if path:
        kwargs["path"] = path

    def env(*names):
        return next((os.environ[n] for n in names if os.environ.get(n)), None)

    login = env("VTMARKETS-DEMO-LOGIN", "VTMARKETS_DEMO_LOGIN", "MT5_LOGIN")
    password = env("VTMARKETS-DEMO-PASSWORD", "VTMARKETS_DEMO_PASSWORD", "MT5_PASSWORD")
    server = env("VTMARKETS-DEMO-SERVER", "VTMARKETS_DEMO_SERVER", "MT5_SERVER")
    if login and password and server:
        kwargs.update(login=int(login), password=password, server=server)
    ok = bool(mt5.initialize(**kwargs))
    code, msg = mt5.last_error() if hasattr(mt5, "last_error") else (None, "")
    return ok, redact(f"last_error=({code}, {msg})")
