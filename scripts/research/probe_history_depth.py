from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.mt5_readonly_client import (ReadonlyMT5Client, MCPError, read_mt5_env_file,
                                                    verified_vt_demo_configuration)
from scripts.research.market_dataset import (decode_tool_result, decode_symbol_listing,
                                               parse_candles, resolve_broker_crypto_symbols)

COUNTS = (1_000, 5_000, 10_000, 25_000, 50_000, 100_000)
SYMBOLS = ("BTCUSD", "ETHUSD")


def candle_args(tool, symbol, count):
    props = tool.get("inputSchema", {}).get("properties", {})
    args = {}
    for key in props:
        low = key.lower()
        if low in {"symbol", "symbol_name", "instrument"}:
            args[key] = symbol
        elif low in {"timeframe", "time_frame", "period"}:
            args[key] = "M5"
        elif low in {"count", "limit", "bars", "number_of_candles"}:
            args[key] = count
    required = tool.get("inputSchema", {}).get("required", [])
    if set(required) - set(args):
        raise MCPError("candle tool schema has unsupported required fields")
    if not {"symbol", "timeframe", "count"}.issubset({"symbol" if k.lower() in {"symbol", "symbol_name", "instrument"} else "timeframe" if k.lower() in {"timeframe", "time_frame", "period"} else "count" if k.lower() in {"count", "limit", "bars", "number_of_candles"} else "" for k in props}):
        raise MCPError("candle tool schema lacks symbol/timeframe/count inputs")
    return args


def probe(client, symbol, counts=COUNTS, broker_symbol=None):
    tool = client.tools.get("readonly_get_candles_latest")
    if tool is None:
        raise MCPError("readonly candle tool unavailable")
    out = []
    best = None
    previous = -1
    for requested in counts:
        started = time.monotonic()
        try:
            result = client.call("readonly_get_candles_latest", candle_args(tool, broker_symbol or symbol, requested))
            payload = decode_tool_result(result)
            rows = parse_candles(payload, source_semantics="VT_SERVER_WALL_CLOCK")
            got = len(rows)
            first = rows.timestamp_utc.min().isoformat() if got else None
            last = rows.timestamp_utc.max().isoformat() if got else None
            status, error, error_text = "OK", None, None
        except Exception as exc:
            got, first, last = 0, None, None
            status, error, error_text = "ERROR", type(exc).__name__, str(exc)[:120]
        entry = {"symbol": symbol, "broker_symbol": broker_symbol or symbol,
                 "requested_count": requested, "returned_count": got,
                 "first_timestamp": first, "last_timestamp": last,
                 "elapsed_seconds": round(time.monotonic() - started, 3), "status": status}
        if error:
            entry["error_type"] = error
            entry["error"] = error_text
        out.append(entry)
        if status != "OK" or got <= previous:
            break
        previous = got
        best = entry
    return out, best


def main():
    ap = argparse.ArgumentParser(description="Read-only MT5 M5 history depth probe")
    ap.add_argument("--output", default=str(ROOT / "data/research/raw/crypto_cfd/AG_CRYPTO_CFD_HISTORY_PROBE.json"))
    ap.add_argument("--env-file", help="optional local MT5 Demo env file; values are passed in memory only")
    ap.add_argument("--request-timeout", type=float, default=60)
    args = ap.parse_args()
    report = {"schema": "AG_CRYPTO_CFD_HISTORY_PROBE_V1", "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
              "symbols": {}, "mutating_tools_executed": 0, "broker_orders_sent": 0}
    try:
        env = read_mt5_env_file(args.env_file) if args.env_file else None
        with ReadonlyMT5Client(request_timeout=args.request_timeout, env_overrides=env) as client:
            report["readonly_tool_count"] = sum(n.startswith("readonly_") for n in client.tools)
            report["mutating_tool_available_to_client"] = False
            if "readonly_get_account_info" in client.tools:
                # Examine in memory only. Never persist/print account number, balance, or credentials.
                info = client.call("readonly_get_account_info", {})
                decode_tool_result(info)  # valid read-only response proves the connected account query succeeded
                report["account_info_read"] = True
                effective_env = {**os.environ, **(env or {})}
                report["mt5_demo"] = verified_vt_demo_configuration(effective_env)
            else:
                report["mt5_demo"] = False
            if not report["mt5_demo"]:
                raise MCPError("read-only account identity does not verify VT Markets Demo")
            if "readonly_get_all_symbols" not in client.tools:
                raise MCPError("read-only symbol authority unavailable")
            symbol_map = resolve_broker_crypto_symbols(decode_symbol_listing(client.call("readonly_get_all_symbols", {})))
            report["symbol_authority"] = {s: symbol_map.get(s) for s in SYMBOLS}
            if not all(report["symbol_authority"].values()):
                raise MCPError("BTCUSD/ETHUSD broker symbol identity could not be verified")
            for symbol in SYMBOLS:
                rows, best = probe(client, symbol, broker_symbol=symbol_map[symbol])
                report["symbols"][symbol] = {"steps": rows, "maximum_reliable": best}
                # Compact terminal summary: never include candle bodies.
                print(json.dumps({"symbol": symbol, "steps": rows, "maximum_reliable": best}, separators=(",", ":")))
                if any(step["status"] != "OK" for step in rows):
                    report["stop_reason"] = f"history request failed for {symbol}"
                    break
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:240]
        print(json.dumps({"status": "BLOCKED_MT5_READONLY", "error_type": type(exc).__name__}))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if not report.get("error_type") else 2


if __name__ == "__main__":
    raise SystemExit(main())

