"""AGP-C2-SYMMAP host script -- read-only symbol capture and CANONICAL_TO_BROKER_MAP smoke.

  python scripts/host/symbol_map_smoke.py capture   # write status/evidence/host_symbol_info_<date>_symmap.json
  python scripts/host/symbol_map_smoke.py smoke     # re-derive the map from live symbol_info, print diff

Read-only by construction: every MT5 attribute access goes through a recording proxy that only
permits ALLOWED_MT5_CALLS (initialize/shutdown/last_error, account_info for the DEMO guard,
symbol_info, symbol_info_tick). No symbol_select, no order_check/order_send, no position/order
access. Market Watch visibility is captured before and after so an unchanged terminal is shown,
not assumed. Exit 0 only when the smoke diff is empty.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _host_common import REPO_ROOT, call_with_timeout, import_mt5, mt5_access_lock, mt5_initialize, require_demo_account, utcnow  # noqa: E402

from mt5.canonical_broker_map import CANONICALS, DEFAULT_MAP_PATH, candidate_names, derive_map, diff_map, load_map  # noqa: E402

ALLOWED_MT5_CALLS = frozenset({"initialize", "shutdown", "last_error", "account_info", "symbol_info", "symbol_info_tick"})
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


def capture_symbols(mt5) -> dict:
    out = {}
    for canonical in CANONICALS:
        for name in candidate_names(canonical):
            info = call_with_timeout(mt5.symbol_info, name)
            if info is None:
                error = call_with_timeout(mt5.last_error)
                # MT5 error 4301 identifies an unknown symbol; ambiguous errors must not
                # silently become an UNMAPPED trading decision.
                code = error[0] if isinstance(error, (tuple, list)) and error else None
                if code not in (4301,):
                    raise RuntimeError(f"symbol_info({name!r}) failed or ambiguous: {error!r}")
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


def run(mode: str) -> int:
    real = import_mt5()
    if real is None:
        print("BLOCKED: real MetaTrader5 package unavailable")
        return 2
    mt5 = ReadOnlyMT5(real)
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
            first = capture_symbols(mt5)
            second = capture_symbols(mt5)  # re-read: visibility must be unchanged by our reads
        finally:
            call_with_timeout(mt5.shutdown)
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
            "read_only_guard": guard,
            "symbols": first,
            "derived_map": derive_map(first),
        }
        path = os.path.join(REPO_ROOT, "status", "evidence", f"host_symbol_info_{now.date().isoformat()}_symmap.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=1, sort_keys=False)
            f.write("\n")
        print(f"WROTE {os.path.relpath(path, REPO_ROOT)}")
        for c, e in evidence["derived_map"].items():
            print(f"  {c}: {e['status']} {e.get('broker_symbol') or e.get('reason')}")
    else:
        symbol_map = load_map(DEFAULT_MAP_PATH)
        diffs = diff_map(symbol_map, first)
        print(f"MAP v{symbol_map.version} {symbol_map.broker}/{symbol_map.server} evidence={symbol_map.evidence}")
        print(f"LIVE_SERVER {account.server}" + ("" if account.server == symbol_map.server else "  MISMATCH"))
        if account.server != symbol_map.server:
            diffs.append(f"server {symbol_map.server} -> {account.server}")
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
