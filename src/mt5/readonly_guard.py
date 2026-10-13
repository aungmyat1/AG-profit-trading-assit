"""Process-wide fail-closed read-only MT5 boundary (AGP-C18-R4).

`install(real_module, run_id)` wraps the real MetaTrader5 module in ReadOnlyMT5Guard and replaces every
reference to it -- sys.modules["MetaTrader5"] and any module attribute bound to the real module (e.g.
mt5.market_data.mt5) -- so no import path in the process reaches the broker unguarded. Prohibited
broker-mutation calls (order_send, order_check and any other order_* except the read-only calculators)
never reach MT5: they increment counters, record a redacted call site and raise ProhibitedBrokerCall.
Read-only queries (rates, ticks, symbols, account/terminal info, positions/orders/history) are
forwarded and counted. This module never imports MetaTrader5 itself.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import traceback
from typing import Any, Dict, List, Optional

PROHIBITED = frozenset({"order_send", "order_check"})
READ_ONLY_ORDER_CALCULATORS = frozenset({"order_calc_margin", "order_calc_profit"})


def is_prohibited(name: str) -> bool:
    """order_send/order_check, and fail closed on any other order_* entry point."""
    return name in PROHIBITED or (name.startswith("order_") and name not in READ_ONLY_ORDER_CALCULATORS)


class ProhibitedBrokerCall(PermissionError):
    """A broker-mutating MT5 call was attempted in a read-only reporting process."""


class GuardCounters:
    def __init__(self, run_id: str):
        self.run_id, self.pid = run_id, os.getpid()
        self.read_calls = 0
        self.prohibited: List[Dict[str, str]] = []
        self.forwarded_mutations = 0
        self.coverage_status = "NOT_INSTALLED"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "RUN_ID": self.run_id, "PID": self.pid,
            "MT5_READ_CALLS": self.read_calls,
            "PROHIBITED_ORDER_API_ATTEMPTS": len(self.prohibited),
            "ORDER_SEND_ATTEMPTS": sum(p["call"] == "order_send" for p in self.prohibited),
            "ORDER_CHECK_ATTEMPTS": sum(p["call"] == "order_check" for p in self.prohibited),
            "BROKER_MUTATION_REQUESTS_FORWARDED": self.forwarded_mutations,
            "GUARD_COVERAGE_STATUS": self.coverage_status,
            "PROHIBITED_CALL_SITES": list(self.prohibited),
        }

    def summary_line(self) -> str:
        d = self.as_dict()
        keys = ("RUN_ID", "MT5_READ_CALLS", "PROHIBITED_ORDER_API_ATTEMPTS", "ORDER_SEND_ATTEMPTS",
                "ORDER_CHECK_ATTEMPTS", "BROKER_MUTATION_REQUESTS_FORWARDED", "GUARD_COVERAGE_STATUS")
        return "MT5_GUARD " + " ".join(f"{k}={d[k]}" for k in keys)


def _call_site() -> str:
    """Redacted call site: repo-relative module path and line of the first frame outside this module."""
    for frame in reversed(traceback.extract_stack()[:-1]):
        if os.path.abspath(frame.filename) != os.path.abspath(__file__):
            name = frame.filename.replace("\\", "/")
            for marker in ("/src/", "/scripts/", "/tests/"):
                if marker in name:
                    name = name[name.rindex(marker) + 1:]
                    break
            else:
                name = os.path.basename(name)
            return f"{name}:{frame.lineno}"
    return "UNKNOWN"


class ReadOnlyMT5Guard:
    """Attribute proxy over the real MetaTrader5 module."""

    def __init__(self, real: Any, counters: GuardCounters):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_counters", counters)
        object.__setattr__(self, "__ag_readonly_guard__", True)

    def __getattr__(self, name: str) -> Any:
        counters: GuardCounters = object.__getattribute__(self, "_counters")
        if is_prohibited(name):
            def refused(*_args, **_kwargs):
                counters.prohibited.append({"call": name, "site": _call_site()})
                raise ProhibitedBrokerCall(f"MT5 {name} refused by the read-only guard (run {counters.run_id})")
            return refused
        value = getattr(object.__getattribute__(self, "_real"), name)
        if not callable(value):
            return value

        def forwarded(*args, **kwargs):
            if is_prohibited(name):                      # unreachable by construction; counted if ever hit
                counters.forwarded_mutations += 1
            counters.read_calls += 1
            return value(*args, **kwargs)
        return forwarded

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ReadOnlyMT5Guard is immutable")


def install(real: Any, run_id: str) -> ReadOnlyMT5Guard:
    """Guard the real module process-wide; coverage is COMPLETE only if no direct reference remains."""
    counters = GuardCounters(run_id)
    guard = ReadOnlyMT5Guard(real, counters)
    sys.modules["MetaTrader5"] = guard
    for module in list(sys.modules.values()):
        if module is None or module is guard:
            continue
        try:
            names = [n for n, v in vars(module).items() if v is real]
        except TypeError:
            continue
        for n in names:
            try:
                setattr(module, n, guard)
            except (AttributeError, TypeError):
                pass
    counters.coverage_status = "INCOMPLETE" if remaining_references(real) else "COMPLETE"
    return guard


def remaining_references(real: Any) -> List[str]:
    found = []
    for mod_name, module in list(sys.modules.items()):
        if isinstance(module, ReadOnlyMT5Guard):        # the guard's own wrapped reference is the point
            continue
        try:
            found += [f"{mod_name}.{n}" for n, v in vars(module).items() if v is real]
        except TypeError:
            continue
    return found


def counters_of(guard: Any) -> Optional[GuardCounters]:
    try:
        return object.__getattribute__(guard, "_counters")
    except AttributeError:
        return None


def broker_history_window(guard: Any, start: dt.datetime, end: dt.datetime, *,
                          to_utc=None) -> Dict[str, Any]:
    """Timestamp-bounded, read-only order/deal history for [start, end] (UTC). MT5 history uses server
    time, so the query is padded by a day and each record's own timestamp is converted with `to_utc`
    (epoch seconds -> aware UTC) and filtered; without a converter every padded record counts (fails
    toward AMBIGUOUS). Any record in the window is BROKER_HISTORY_AMBIGUOUS (this runner never places
    orders but cannot attribute other processes); none is BROKER_HISTORY_CLEAN; a failed query is
    BROKER_HISTORY_UNAVAILABLE."""
    pad = dt.timedelta(days=1)
    try:
        orders = guard.history_orders_get(start - pad, end + pad)
        deals = guard.history_deals_get(start - pad, end + pad)
    except Exception as exc:  # noqa: BLE001 -- evidence, never a guess
        return {"status": "BROKER_HISTORY_UNAVAILABLE", "error": type(exc).__name__}
    if orders is None or deals is None:
        return {"status": "BROKER_HISTORY_UNAVAILABLE", "error": "NONE_RETURNED"}

    def inside(row, attr):
        if to_utc is None:
            return True
        try:
            return start <= to_utc(int(getattr(row, attr))) <= end
        except Exception:  # noqa: BLE001 -- an unconvertible timestamp counts (fails toward AMBIGUOUS)
            return True
    orders = [r for r in orders if inside(r, "time_setup")]
    deals = [r for r in deals if inside(r, "time")]

    def brief(rows):
        return [{"ticket_suffix": str(getattr(r, "ticket", ""))[-4:], "magic": getattr(r, "magic", None)}
                for r in rows]
    status = "BROKER_HISTORY_CLEAN" if len(orders) == 0 and len(deals) == 0 else "BROKER_HISTORY_AMBIGUOUS"
    return {"status": status, "window_start_utc": start.isoformat(), "window_end_utc": end.isoformat(),
            "orders": len(orders), "deals": len(deals), "order_records": brief(orders), "deal_records": brief(deals)}
