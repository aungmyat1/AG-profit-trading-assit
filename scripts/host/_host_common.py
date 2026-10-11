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
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Appended, not prepended: the repo-root MetaTrader5.py stub must never shadow the real
# installed package.
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src")):
    if _p not in sys.path:
        sys.path.append(_p)

LOG_DIR = os.path.join(REPO_ROOT, "logs")
# Host-wide lock directory, deliberately OUTSIDE any checkout: every AG checkout on this host
# (production, PR worktrees, audits) talks to the same MT5 terminal, so their MT5 access must
# serialize on one lock. A checkout-relative path (the old logs/mt5_access.lock) let two
# checkouts hit the terminal concurrently. AG_HOST_LOCK_DIR overrides (tests, unusual hosts).
MT5_LOCK_DIR = os.environ.get("AG_HOST_LOCK_DIR") or os.path.join(
    os.environ.get("PROGRAMDATA") or tempfile.gettempdir(), "AG", "locks")
_SECRET_MARKERS = ("TOKEN", "PASSWORD", "SECRET", "KEY")

# Hard bounds for scheduled runs (a hung MT5 IPC call or interpreter exit once kept tasks alive
# until Task Scheduler killed them, blocking the next cycle).
MT5_INIT_TIMEOUT_S = 20
MT5_CALL_TIMEOUT_S = 10
RUN_TIMEOUT_S = 120
MT5_LOCK_WAIT_S = 60
_HELD_LOCKS: set = set()


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


def _lock_pid(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _pid_alive(pid: int) -> bool:
    """True if `pid` is a running process. Unknown (0) counts as alive so only the age rule
    applies. Never signals the process (os.kill(pid, 0) terminates it on Windows)."""
    if pid <= 0:
        return True
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def single_instance(name: str, stale_after_s: int = 1800) -> Iterator[None]:
    """O_EXCL lock file in logs/. A lock older than `stale_after_s`, or whose owner process is
    gone (a run killed by Task Scheduler), is broken."""
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"{name}.lock")
    try:
        if time.time() - os.path.getmtime(path) > stale_after_s or not _pid_alive(_lock_pid(path)):
            os.remove(path)
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AlreadyRunning(name) from exc
    _HELD_LOCKS.add(path)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        _HELD_LOCKS.discard(path)
        try:
            os.remove(path)
        except OSError:
            pass


class CallTimeout(RuntimeError):
    code = "CALL_TIMEOUT"


def call_with_timeout(fn: Callable[..., Any], *args: Any, limit_s: float = MT5_CALL_TIMEOUT_S, **kwargs: Any) -> Any:
    """Run fn in a daemon thread; raise CallTimeout if it has not returned within `limit_s`
    seconds. A stuck call is abandoned (the run watchdog ends the process)."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 -- re-raised in the caller's thread
            box["error"] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(limit_s)
    if t.is_alive():
        raise CallTimeout(f"{getattr(fn, '__name__', fn)} exceeded {limit_s}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def start_run_watchdog(name: str, timeout_s: float = RUN_TIMEOUT_S, _exit: Callable[[int], Any] = os._exit):
    """Self-exit the whole process after `timeout_s`, logging TIMEOUT and releasing any
    single_instance lock so the next scheduled cycle is not blocked."""
    def fire() -> None:
        log_line(name, f"TIMEOUT run exceeded {timeout_s}s; self-exit")
        for path in list(_HELD_LOCKS):
            try:
                os.remove(path)
            except OSError:
                pass
        _exit(3)

    timer = threading.Timer(timeout_s, fire)
    timer.daemon = True
    timer.start()
    return timer


class Mt5Busy(RuntimeError):
    code = "MT5_BUSY"


def _try_lock(f) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def mt5_access_lock(wait_s: float = MT5_LOCK_WAIT_S, poll_s: float = 1.0) -> Iterator[None]:
    """One host-wide cross-process OS file lock around all MT5 access (fx / crypto / lsmc, from
    any checkout, share one terminal). The OS drops it when the process dies, so a killed run never leaves it held.
    Raises Mt5Busy if it cannot be acquired within `wait_s`."""
    os.makedirs(MT5_LOCK_DIR, exist_ok=True)
    f = open(os.path.join(MT5_LOCK_DIR, "mt5_access.lock"), "a+")
    try:
        deadline = time.monotonic() + wait_s
        while not _try_lock(f):
            if time.monotonic() >= deadline:
                raise Mt5Busy(f"mt5_access.lock held > {wait_s}s")
            time.sleep(poll_s)
        try:
            yield
        finally:
            _unlock(f)
    finally:
        f.close()


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


def require_demo_account(mt5) -> "tuple[bool, str]":
    """Fail closed unless the connected terminal exposes a DEMO account.

    Reading account_info is non-mutating.  No login, server, balance, or equity is
    returned in the detail string, so callers can safely archive/log the result.
    """
    try:
        account = call_with_timeout(mt5.account_info)
    except Exception as exc:  # noqa: BLE001
        return False, f"ACCOUNT_INFO_UNAVAILABLE {type(exc).__name__}"
    if account is None:
        return False, "ACCOUNT_INFO_UNAVAILABLE"
    expected = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    if getattr(account, "trade_mode", None) != expected:
        return False, "NON_DEMO_ACCOUNT_BLOCKED"
    return True, "DEMO_ACCOUNT_VERIFIED"


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
    kwargs["timeout"] = MT5_INIT_TIMEOUT_S * 1000       # MT5's own ms timeout, plus a thread bound
    try:
        ok = bool(call_with_timeout(mt5.initialize, limit_s=MT5_INIT_TIMEOUT_S + 2, **kwargs))
    except CallTimeout as exc:
        return False, f"INIT_TIMEOUT {exc}"
    code, msg = call_with_timeout(mt5.last_error) if hasattr(mt5, "last_error") else (None, "")
    return ok, redact(f"last_error=({code}, {msg})")


_TF = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


def _mt5_server_wall(raw_time: int) -> dt.datetime:
    """MT5 copy_rates 'time' is broker-server wall-clock stored as seconds from the UTC
    epoch (EET/broker-local convention -- the server midnight is treated as epoch origin,
    not true UTC midnight). fromtimestamp(t, utc).replace(tzinfo=None) extracts the
    server wall-clock datetime; .replace() strips only the misleading UTC label so that
    server_time_to_utc (the single conversion point) receives a plain server wall-clock value."""
    return dt.datetime.fromtimestamp(raw_time, dt.timezone.utc).replace(tzinfo=None)


def host_fetch(mt5):
    """fetch(broker_symbol, timeframe, count) -> the last `count` CLOSED bars, oldest first.

    Timestamps are converted with host_evidence.symbol_metadata.server_time_to_utc (the
    owner-stated rule: server midnight = New York 17:00), never with per-symbol weekly-reopen
    detection, which misreads XAUUSD (+4) and fails on a late first USDJPY bar. Read-only:
    copy_rates_from_pos plus symbol_select for Market Watch visibility."""
    from host_evidence.symbol_metadata import (
        CONVERSION_ERROR, INCOMPLETE_CANDLES, SYMBOL_NOT_FOUND, DstHourError, HostDataError, server_time_to_utc,
    )
    from strategy_engine.session import Candle

    def fetch(symbol: str, timeframe: str, count: int) -> list:
        if timeframe not in _TF:
            raise ValueError(f"UNSUPPORTED_TIMEFRAME {timeframe!r}")
        if call_with_timeout(mt5.symbol_info, symbol) is None and not call_with_timeout(mt5.symbol_select, symbol, True):
            raise HostDataError(SYMBOL_NOT_FOUND, repr(symbol))
        rates = call_with_timeout(mt5.copy_rates_from_pos, symbol, getattr(mt5, f"TIMEFRAME_{timeframe}"), 1, count)
        if rates is None or len(rates) < count:
            got = 0 if rates is None else len(rates)
            raise HostDataError(INCOMPLETE_CANDLES,
                                f"{symbol}/{timeframe} {got}<{count}: {call_with_timeout(mt5.last_error)}")
        try:
            out = []
            for r in rates:
                try:
                    t = server_time_to_utc(_mt5_server_wall(int(r["time"])))
                except DstHourError as exc:  # repeated/skipped server hour: drop + log, never fold
                    print(f"DROPPED_BAR {exc.reason_code} {symbol}/{timeframe} {exc.server_wall_clock.isoformat()}",
                          file=sys.stderr)
                    continue
                out.append(Candle(time=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                                  close=float(r["close"]), volume=float(r["tick_volume"])))
            return out
        except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
            raise HostDataError(CONVERSION_ERROR, f"{symbol}/{timeframe}: {type(exc).__name__} {exc}") from exc
    return fetch


def host_quote(mt5):
    """quote(broker_symbol) -> (bid, ask) from symbol_info_tick, or None. Read-only."""
    def quote(symbol: str):
        tick = call_with_timeout(mt5.symbol_info_tick, symbol)
        if tick is None or not getattr(tick, "bid", 0) or not getattr(tick, "ask", 0):
            return None
        return float(tick.bid), float(tick.ask)
    return quote
