"""AGP-C2-SYMMAP host script -- read-only symbol capture and CANONICAL_TO_BROKER_MAP smoke.

  python scripts/host/symbol_map_smoke.py capture   # write status/evidence/host_symbol_info_<UTC timestamp>_symmap.json (never overwrites)
  python scripts/host/symbol_map_smoke.py smoke     # re-derive the map from live symbol_info, print diff

Read-only by construction: every MT5 attribute access goes through a recording proxy that only
permits ALLOWED_MT5_CALLS (initialize/shutdown/last_error, account_info for the DEMO guard,
symbol_info, symbol_info_tick, and the symbols_get/symbols_total inventory reads). No
symbol_select, no order_check/order_send, no position/order access. Market Watch visibility is
captured before and after so an unchanged terminal is shown, not assumed. Exit 0 only when the
smoke diff is empty.

Symbol lookup contract (MetaTrader5 python package, checked against installed 5.0.5735):
``symbol_info(name)`` returns None on any failure and ``last_error()`` then returns the package's
own RES_* code -- e.g. RES_E_NOT_FOUND = -4 ("Terminal: Not found"), which the package uses for
any "not found", not only for an unknown symbol. MQL5 terminal runtime codes such as 4301
(ERR_MARKET_UNKNOWN_SYMBOL) are not python-package codes. A candidate is therefore
SYMBOL_ABSENT_CONFIRMED only when symbol_info is None, last_error is RES_E_NOT_FOUND, AND the
name is missing from a complete terminal inventory (symbols_get, cross-checked against
symbols_total). Every other outcome is classified and fails closed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _host_common import REPO_ROOT, CallTimeout, call_with_timeout, import_mt5, mt5_access_lock, mt5_initialize, require_demo_account, utcnow  # noqa: E402

from mt5.canonical_broker_map import CANONICALS, DEFAULT_MAP_PATH, candidate_names, derive_map, diff_map, load_map  # noqa: E402

ALLOWED_MT5_CALLS = frozenset({"initialize", "shutdown", "last_error", "account_info", "symbol_info", "symbol_info_tick",
                               "symbols_get", "symbols_total"})
ALLOWED_MT5_ATTRIBUTES = frozenset({"__version__", "ACCOUNT_TRADE_MODE_DEMO"})
INFO_FIELDS = ("visible", "select", "trade_mode", "digits", "point", "trade_contract_size", "volume_min", "volume_step",
               "volume_max", "trade_tick_value", "trade_tick_size", "spread", "spread_float", "swap_mode", "swap_long",
               "swap_short", "swap_rollover3days", "trade_calc_mode", "trade_stops_level", "trade_freeze_level",
               "currency_base", "currency_profit", "currency_margin", "path", "description")
TICK_FIELDS = ("time", "bid", "ask")


class ReadOnlyMT5:
    """Records every MT5 callable used; refuses anything outside ALLOWED_MT5_CALLS."""

    def __init__(self, mt5):
        self._mt5 = mt5
        self.calls: dict = {}

    def __getattr__(self, name):
        if name not in ALLOWED_MT5_CALLS and name not in ALLOWED_MT5_ATTRIBUTES:
            raise PermissionError(f"MT5 attribute {name!r} is not allowed in this read-only mission")
        attr = getattr(self._mt5, name)
        if name in ALLOWED_MT5_ATTRIBUTES:
            if callable(attr):
                raise PermissionError(f"MT5 attribute {name!r} must be noncallable")
            return attr
        if not callable(attr):
            raise PermissionError(f"MT5 operation {name!r} must be callable")

        def wrapped(*a, **k):
            self.calls[name] = self.calls.get(name, 0) + 1
            return attr(*a, **k)
        return wrapped


# MQL5 ENUM_SYMBOL_TRADE_MODE / ENUM_SYMBOL_CALC_MODE / ENUM_SYMBOL_SWAP_MODE /
# ENUM_ACCOUNT_TRADE_MODE. The python package does not export all of these constants (the first
# capture labelled FULL as "4"), so the names are fixed here; unknown values stay numeric strings.
ENUM_NAMES = {
    "trade_mode": {0: "DISABLED", 1: "LONGONLY", 2: "SHORTONLY", 3: "CLOSEONLY", 4: "FULL"},
    "trade_calc_mode": {0: "FOREX", 1: "FUTURES", 2: "CFD", 3: "CFDINDEX", 4: "CFDLEVERAGE", 5: "FOREX_NO_LEVERAGE",
                        32: "EXCH_STOCKS", 33: "EXCH_FUTURES", 34: "EXCH_FUTURES_FORTS", 35: "EXCH_BONDS",
                        36: "EXCH_STOCKS_MOEX", 37: "EXCH_BONDS_MOEX", 38: "SERV_COLLATERAL"},
    "swap_mode": {0: "DISABLED", 1: "POINTS", 2: "CURRENCY_SYMBOL", 3: "CURRENCY_MARGIN", 4: "CURRENCY_DEPOSIT",
                  5: "INTEREST_CURRENT", 6: "INTEREST_OPEN", 7: "REOPEN_CURRENT", 8: "REOPEN_BID"},
    "account_trade_mode": {0: "DEMO", 1: "CONTEST", 2: "REAL"},
}


def _enum_name(kind: str, value) -> str:
    return ENUM_NAMES[kind].get(value, str(value))


SYMBOL_PRESENT = "SYMBOL_PRESENT"
SYMBOL_ABSENT_CONFIRMED = "SYMBOL_ABSENT_CONFIRMED"
MT5_API_ERROR = "MT5_API_ERROR"
MT5_TIMEOUT = "MT5_TIMEOUT"
MT5_RESPONSE_AMBIGUOUS = "MT5_RESPONSE_AMBIGUOUS"
RESOLVED_LOOKUPS = frozenset({SYMBOL_PRESENT, SYMBOL_ABSENT_CONFIRMED})

# MetaTrader5 python package RES_* result codes (module constants in 5.0.5735; pinned here because
# the read-only proxy does not expose module constants).
RES_S_OK = 1
RES_E_NOT_FOUND = -4
RES_E_INTERNAL_FAIL_TIMEOUT = -10005


class SymbolLookupBlocked(RuntimeError):
    """A candidate lookup did not resolve to PRESENT or ABSENT_CONFIRMED; the run must stop."""

    def __init__(self, name: str, classification: str, detail: str):
        super().__init__(f"symbol_info({name!r}) {classification}: {detail}")
        self.name = name
        self.classification = classification
        self.detail = detail


def symbol_inventory(mt5) -> "tuple[frozenset | None, str]":
    """Complete terminal symbol-name inventory via symbols_get(), or (None, reason) when it cannot
    be shown complete. symbols_get lists every symbol the server gave the terminal, not only
    Market Watch; it selects nothing."""
    symbols = call_with_timeout(mt5.symbols_get)
    if symbols is None:
        return None, f"symbols_get returned None: last_error={call_with_timeout(mt5.last_error)!r}"
    total = call_with_timeout(mt5.symbols_total)
    names = [getattr(s, "name", None) for s in symbols]
    if not names or type(total) is not int or total != len(names):
        return None, f"symbols_get/symbols_total inconsistent: {len(names)} vs {total!r}"
    if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        return None, "symbols_get returned missing or duplicate names"
    return frozenset(names), f"{len(names)} symbols"


def classify_symbol_lookup(name: str, info, error, inventory) -> "tuple[str, str]":
    """Pure classification of one symbol_info() outcome. ``error`` is last_error() when info is
    None; ``inventory`` is the symbol_inventory() name set, or None when it is unavailable."""
    if info is not None:
        if getattr(info, "name", None) != name:
            return MT5_RESPONSE_AMBIGUOUS, f"symbol_info returned name {getattr(info, 'name', None)!r}"
        if inventory is not None and name not in inventory:
            return MT5_RESPONSE_AMBIGUOUS, "symbol_info present but missing from symbols_get inventory"
        return SYMBOL_PRESENT, "symbol_info returned a record"
    if not isinstance(error, (tuple, list)) or len(error) != 2 or type(error[0]) is not int:
        return MT5_RESPONSE_AMBIGUOUS, f"malformed last_error {error!r}"
    code = error[0]
    if code == RES_E_NOT_FOUND:
        if inventory is None:
            return MT5_RESPONSE_AMBIGUOUS, f"last_error={tuple(error)!r} without a complete inventory"
        if name in inventory:
            return MT5_RESPONSE_AMBIGUOUS, f"last_error={tuple(error)!r} but name is in symbols_get inventory"
        return SYMBOL_ABSENT_CONFIRMED, f"last_error={tuple(error)!r}; absent from {len(inventory)}-symbol inventory"
    if code == RES_E_INTERNAL_FAIL_TIMEOUT:
        return MT5_TIMEOUT, f"last_error={tuple(error)!r}"
    if code < 0:
        return MT5_API_ERROR, f"last_error={tuple(error)!r}"
    # RES_S_OK with no record, or any non-package code (e.g. MQL5 4301): not a documented absence.
    return MT5_RESPONSE_AMBIGUOUS, f"last_error={tuple(error)!r} is not a MetaTrader5 package absence code"


def lookup_symbol(mt5, name: str, inventory) -> "tuple[object, str, str]":
    try:
        info = call_with_timeout(mt5.symbol_info, name)
        error = None if info is not None else call_with_timeout(mt5.last_error)
    except (CallTimeout, TimeoutError) as exc:
        return None, MT5_TIMEOUT, f"{type(exc).__name__}: {exc}"
    classification, detail = classify_symbol_lookup(name, info, error, inventory)
    return info, classification, detail


def capture_symbols(mt5, lookups: "dict | None" = None) -> dict:
    """Read every candidate; ``lookups`` (if given) receives name -> {classification, detail}.
    Raises SymbolLookupBlocked at the first lookup that is neither PRESENT nor ABSENT_CONFIRMED."""
    try:
        inventory, inventory_detail = symbol_inventory(mt5)
    except (CallTimeout, TimeoutError) as exc:
        raise SymbolLookupBlocked("<inventory>", MT5_TIMEOUT, f"{type(exc).__name__}: {exc}") from None
    out = {}
    for canonical in CANONICALS:
        for name in candidate_names(canonical):
            info, classification, detail = lookup_symbol(mt5, name, inventory)
            if lookups is not None:
                lookups[name] = {"classification": classification, "detail": detail}
            if classification not in RESOLVED_LOOKUPS:
                if inventory is None:
                    detail = f"{detail}; inventory: {inventory_detail}"
                raise SymbolLookupBlocked(name, classification, detail)
            if classification == SYMBOL_ABSENT_CONFIRMED:
                out[name] = None
                continue
            rec = {f: getattr(info, f, None) for f in INFO_FIELDS}
            rec["canonical"] = canonical
            rec["trade_mode_name"] = _enum_name("trade_mode", rec["trade_mode"])
            rec["trade_calc_mode_name"] = _enum_name("trade_calc_mode", rec["trade_calc_mode"])
            rec["swap_mode_name"] = _enum_name("swap_mode", rec["swap_mode"])
            tick = call_with_timeout(mt5.symbol_info_tick, name)
            rec["tick"] = None if tick is None else {f: getattr(tick, f, None) for f in TICK_FIELDS}
            rec["commission"] = "COMMISSION_UNAVAILABLE"
            out[name] = rec
    return out


def _visibility(symbols: dict) -> dict:
    return {n: (r["visible"] if r else None) for n, r in symbols.items()}


def snapshot_mapping_differences(first: dict, second: dict) -> list[str]:
    """Compare only mapping-critical metadata, not fast-moving market prices."""
    changed = []
    for canonical in CANONICALS:
        if derive_map(first, (canonical,))[canonical] != derive_map(second, (canonical,))[canonical]:
            changed.append(canonical)
    return changed


def account_gate(account, expected_server: str) -> "str | None":
    """None when the connected account is the map's server; else the BLOCKED reason. Checked
    before any symbol read, in both modes."""
    if account is None:
        return "ACCOUNT_INFO_UNAVAILABLE"
    if getattr(account, "server", None) != expected_server:
        return f"SERVER_MISMATCH expected {expected_server}"
    return None


def run(mode: str) -> int:
    real = import_mt5()
    if real is None:
        print("BLOCKED: real MetaTrader5 package unavailable")
        return 2
    mt5 = ReadOnlyMT5(real)
    symbol_map = load_map(DEFAULT_MAP_PATH)
    lookups: dict = {}
    print(f"MT5_PACKAGE_VERSION {getattr(real, '__version__', None)}")
    with mt5_access_lock():
        ok, detail = mt5_initialize(mt5)
        if not ok:
            print(f"BLOCKED: initialize failed {detail}")
            return 2
        try:
            demo_ok, demo_detail = require_demo_account(mt5)
            if not demo_ok:
                print(f"BLOCKED: {demo_detail}")
                return 2
            account = call_with_timeout(mt5.account_info)
            blocked = account_gate(account, symbol_map.server)
            if blocked:
                print(f"BLOCKED: {blocked}")
                return 2
            print(f"ACCOUNT server={account.server} trade_mode={_enum_name('account_trade_mode', account.trade_mode)}")
            try:
                first = capture_symbols(mt5, lookups)
                second = capture_symbols(mt5)  # re-read: visibility must be unchanged by our reads
            except SymbolLookupBlocked as exc:
                print(f"BLOCKED: {exc.classification} {exc}")
                return 2
        finally:
            call_with_timeout(mt5.shutdown)
    counts: dict = {}
    for item in lookups.values():
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    print(f"SYMBOL_LOOKUP_CLASSIFICATIONS {json.dumps(dict(sorted(counts.items())))}")
    visibility_unchanged = _visibility(first) == _visibility(second)
    snapshot_differences = snapshot_mapping_differences(first, second)
    if snapshot_differences:
        print(f"BLOCKED: unstable symbol metadata for {snapshot_differences}")
        return 1
    forbidden = sorted(set(mt5.calls) - ALLOWED_MT5_CALLS)
    guard = {"mt5_calls": dict(sorted(mt5.calls.items())), "forbidden_calls": forbidden,
             "market_watch_visibility_unchanged": visibility_unchanged,
             "broker_mutations": 0 if not forbidden and visibility_unchanged else "UNVERIFIED"}
    if mode == "capture":
        now = utcnow()
        evidence = {
            "mission": "AGP-C2-SYMMAP",
            "captured_at_utc": now.isoformat(timespec="seconds"),
            "source": "MetaTrader5.symbol_info / symbol_info_tick (python, read-only; no symbol_select, no orders)",
            "mt5_package_version": getattr(real, "__version__", None),
            "account": {"server": account.server, "trade_mode": _enum_name("account_trade_mode", account.trade_mode),
                        "currency": account.currency},
            "candidate_suffixes_probed": sorted({n[len(c):] for c in CANONICALS for n in candidate_names(c)}),
            "map_rule": "exactly one candidate present, visible and trade_mode FULL; else UNMAPPED",
            "commission_note": "MT5 symbol_info exposes no commission field; commission is only observable from deal history.",
            "crypto_note": "Crypto contract fields are recorded as captured only; no sizing semantics are inferred here.",
            "lookup_contract": "SYMBOL_ABSENT_CONFIRMED = symbol_info None + last_error RES_E_NOT_FOUND (-4) + name "
                               "absent from symbols_get inventory (len == symbols_total); anything else blocks",
            "symbol_lookups": lookups,
            "metadata_stability": {"snapshots": 2, "mapping_critical_differences": snapshot_differences},
            "read_only_guard": guard,
            "symbols": first,
            "derived_map": derive_map(first),
        }
        # Timestamped and exclusive-create: a capture never overwrites earlier (committed) evidence.
        path = os.path.join(REPO_ROOT, "status", "evidence", f"host_symbol_info_{now:%Y-%m-%dT%H%M%SZ}_symmap.json")
        with open(path, "x", encoding="utf-8") as f:
            json.dump(evidence, f, indent=1, sort_keys=False)
            f.write("\n")
        print(f"WROTE {os.path.relpath(path, REPO_ROOT)}")
        for c, e in evidence["derived_map"].items():
            print(f"  {c}: {e['status']} {e.get('broker_symbol') or e.get('reason')}")
    else:
        diffs = diff_map(symbol_map, first)
        print(f"MAP v{symbol_map.version} {symbol_map.broker}/{symbol_map.server} evidence={symbol_map.evidence}")
        print("METADATA_STABILITY PASS (2 snapshots, no mapping-critical differences)")
        for c, e in derive_map(first).items():
            print(f"  {c}: {e['status']} {e.get('broker_symbol') or e.get('reason')}")
        print("DIFF " + ("EMPTY" if not diffs else f"{len(diffs)} item(s)"))
        for d in diffs:
            print(f"  {d}")
        print(f"READ_ONLY_GUARD {json.dumps(guard, sort_keys=True)}")
        if diffs:
            return 1
    return 0 if guard["broker_mutations"] == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mode", choices=("capture", "smoke"))
    sys.exit(run(p.parse_args().mode))
