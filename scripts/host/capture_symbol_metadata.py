"""Step 2 of scripts/host/GO_LIVE.md: capture VT Markets symbol metadata (read-only).

    .venv\\Scripts\\python.exe scripts\\host\\capture_symbol_metadata.py --symbol USDJPY
        -> lists the broker's candidate names (symbols_get) and exits 2
    .venv\\Scripts\\python.exe scripts\\host\\capture_symbol_metadata.py --symbol USDJPY --broker-symbol USDJPY
        -> captures and writes config/symbol_metadata/host_captured/USDJPY.json

The script never picks a name fuzzily: without --broker-symbol it only lists candidates.
Captured fields are digits, point, trade_tick_size, trade_tick_value, trade_contract_size,
volume_min/step/max, trade_stops_level, trade_freeze_level, spread and currency_profit, plus
the symbol's trade_mode and the server UTC offset. The offset is derived from the broker
convention in host_evidence.symbol_metadata.OFFSET_RULE (server midnight = New York 17:00),
not detected from bars; the record stores the rule and its value at capture time. The
written record carries its sha256 and capture time. Once written, v1_tickets.fx and
large_smc_watch treat the symbol as HOST_CAPTURED (CODE_READY) instead of FIXTURE_ONLY,
and the FX ticket/watch fetches use the recorded broker_symbol.

Owner-chosen VT Markets names (2026-09-30): EURUSD-VIP, GBPUSD-VIP, USDJPY-VIP, XAUUSD-VIP
(the plain EURUSD/GBPUSD are trade_mode DISABLED), and BTCUSD / ETHUSD for the crypto
ticket config V2 venue (config/v1_tickets/crypto_ticket_v2.yaml).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import REPO_ROOT, import_mt5, mt5_initialize, utcnow  # noqa: E402

from host_evidence.symbol_metadata import (  # noqa: E402
    FIELDS, OFFSET_RULE, build_record, server_utc_offset_hours, write_record,
)

CAPTURABLE = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD")


def trade_mode_name(mt5, value) -> str:
    names = {getattr(mt5, n): n[len("SYMBOL_TRADE_MODE_"):] for n in dir(mt5) if n.startswith("SYMBOL_TRADE_MODE_")}
    return names.get(value, str(value))


def candidates(mt5, canonical: str) -> list:
    rows = mt5.symbols_get(group=f"*{canonical}*") or ()
    return sorted(r.name for r in rows)


def capture(mt5, canonical: str, broker_symbol: str, offset_fn, now_iso: str) -> dict:
    info = mt5.symbol_info(broker_symbol)
    if info is None and mt5.symbol_select(broker_symbol, True):  # Market Watch visibility only; not trading
        info = mt5.symbol_info(broker_symbol)
    if info is None:
        raise SystemExit(f"symbol_info({broker_symbol!r}) returned None: {mt5.last_error()}")
    if getattr(info, "name", broker_symbol) != broker_symbol:
        raise SystemExit(f"broker returned {info.name!r} for {broker_symbol!r}; refusing a non-exact match")
    fields = {f: getattr(info, f, None) for f in FIELDS}
    try:
        offset = offset_fn(broker_symbol)
    except Exception as exc:  # noqa: BLE001 -- offset is required evidence, fail closed with the reason
        raise SystemExit(f"server UTC offset could not be established: {exc}")
    acct = mt5.account_info()
    return build_record(canonical, broker_symbol, fields, getattr(acct, "server", "UNKNOWN"), offset, now_iso,
                        trade_mode=trade_mode_name(mt5, getattr(info, "trade_mode", None)))


def main(argv=None, mt5=None, offset_fn=None, root: str = REPO_ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbol", required=True, choices=CAPTURABLE)
    ap.add_argument("--broker-symbol", default=None, help="EXACT broker symbol name (see the candidate list)")
    ap.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH", ""))
    args = ap.parse_args(argv)
    mt5 = mt5 or import_mt5()
    if mt5 is None:
        print("MetaTrader5 package missing -- run scripts/host/diagnose_mt5.py first")
        return 1
    ok, err = mt5_initialize(mt5, args.terminal_path)
    if not ok:
        print(f"initialize() failed: {err} -- run scripts/host/diagnose_mt5.py")
        return 1
    try:
        if not args.broker_symbol:
            names = candidates(mt5, args.symbol)
            print(f"Candidates for {args.symbol}: {names or 'NONE'}")
            print("Re-run with --broker-symbol <EXACT NAME> (no fuzzy pick is ever made).")
            return 2
        now = utcnow()
        if offset_fn is None:
            offset_fn = lambda _symbol: server_utc_offset_hours(now)  # noqa: E731 -- OFFSET_RULE, not bar detection
        record = capture(mt5, args.symbol, args.broker_symbol, offset_fn, now.isoformat())
        path = write_record(record, root)
        print(f"WROTE {os.path.relpath(path, root)} broker_symbol={record['broker_symbol']} "
              f"trade_mode={record['trade_mode']} digits={record['fields']['digits']} "
              f"point={record['fields']['point']} server_utc_offset_hours={record['server_utc_offset_hours']} "
              f"sha256={record['sha256'][:16]}")
        print(f"OFFSET_RULE: {OFFSET_RULE}")
        print("STATUS: HOST_CAPTURED (FIXTURE_ONLY -> CODE_READY)")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
