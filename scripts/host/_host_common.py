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
# Appended, not prepended: the repo-root MetaTrader5.py stub must never shadow the real
# installed package.
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.append(_p)

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


def _is_repo_module(mt5) -> bool:
    """True when the module file lives in the repo itself (the stub), not in an installed
    site-packages -- a .venv inside the repo is still an installed package."""
    path = os.path.normcase(os.path.abspath(str(getattr(mt5, "__file__", "") or "")))
    root = os.path.normcase(REPO_ROOT)
    try:
        inside = os.path.commonpath([path, root]) == root
    except ValueError:  # different drives
        inside = False
    return inside and "site-packages" not in path.split(os.sep)


def import_mt5():
    """Return the real MetaTrader5 module or None. Never falls back to the test stub.

    The import runs with the repo root / src (and a cwd equal to either) removed from
    sys.path and any cached stub evicted, so the installed package wins even when the stub
    is first on the path. sys.path and sys.modules are restored afterwards."""
    cached = sys.modules.get("MetaTrader5")
    if cached is not None and _is_real(cached):
        return cached
    repo_dirs = {os.path.normcase(REPO_ROOT), os.path.normcase(os.path.join(REPO_ROOT, "src"))}
    saved_path = sys.path[:]
    sys.modules.pop("MetaTrader5", None)
    sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or os.getcwd())) not in repo_dirs]
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except Exception:  # noqa: BLE001
        mt5 = None
    finally:
        sys.path[:] = saved_path
        if cached is not None:
            sys.modules["MetaTrader5"] = cached
    return mt5 if mt5 is not None and _is_real(mt5) else None


def _is_real(mt5) -> bool:
    names = getattr(mt5, "__dict__", {})
    return "MT5StubOperationAttempted" not in names and not _is_repo_module(mt5) and "initialize" in names


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


_TF = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


def host_fetch(mt5):
    """fetch(broker_symbol, timeframe, count) -> the last `count` CLOSED bars, oldest first.

    Timestamps are converted with host_evidence.symbol_metadata.server_time_to_utc (the
    owner-stated rule: server midnight = New York 17:00), never with per-symbol weekly-reopen
    detection, which misreads XAUUSD (+4) and fails on a late first USDJPY bar. Read-only:
    copy_rates_from_pos plus symbol_select for Market Watch visibility."""
    from host_evidence.symbol_metadata import server_time_to_utc
    from strategy_engine.session import Candle

    def fetch(symbol: str, timeframe: str, count: int) -> list:
        if timeframe not in _TF:
            raise ValueError(f"UNSUPPORTED_TIMEFRAME {timeframe!r}")
        if mt5.symbol_info(symbol) is None and not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"SYMBOL_NOT_FOUND {symbol!r}")
        rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, f"TIMEFRAME_{timeframe}"), 1, count)
        if rates is None or len(rates) < count:
            raise RuntimeError(f"DATA_MISSING {symbol}/{timeframe}: {mt5.last_error()}")
        return [Candle(time=server_time_to_utc(dt.datetime.fromtimestamp(int(r["time"]), dt.timezone.utc).replace(tzinfo=None)),
                       open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                       close=float(r["close"]), volume=float(r["tick_volume"])) for r in rates]
    return fetch
