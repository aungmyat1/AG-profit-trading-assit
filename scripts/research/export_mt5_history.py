from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from host_evidence.symbol_metadata import server_utc_offset_hours, OFFSET_RULE
from scripts.research.mt5_readonly_client import (ReadonlyMT5Client, MCPError, read_mt5_env_file,
                                                    verified_vt_demo_configuration)
from scripts.research.market_dataset import (DatasetError, aggregate, closed_rows, decode_tool_result,
                                               decode_symbol_listing, parse_candles, resolve_broker_crypto_symbols,
                                               sha256_file, validate)
from scripts.research.probe_history_depth import candle_args, SYMBOLS

RAW_DIR = ROOT / "data/research/raw/crypto_cfd"
DERIVED_DIR = ROOT / "data/research/derived/crypto_cfd"


def _broker_identity(client):
    if "readonly_get_account_info" not in client.tools:
        raise MCPError("read-only account info unavailable; cannot verify Demo")
    account = decode_tool_result(client.call("readonly_get_account_info", {}))
    effective_env = {**os.environ, **client._env_overrides}
    if not verified_vt_demo_configuration(effective_env):
        raise MCPError("account identity does not verify VT Markets Demo")
    if "readonly_get_all_symbols" not in client.tools:
        raise MCPError("read-only symbol authority unavailable")
    symbols = decode_symbol_listing(client.call("readonly_get_all_symbols", {}))
    present = resolve_broker_crypto_symbols(symbols)
    if not set(SYMBOLS).issubset(present):
        raise MCPError("BTCUSD/ETHUSD broker symbol identity could not be verified")
    return account, present


def export_symbol(client, symbol, requested_count, output_dir=RAW_DIR, broker_symbol=None):
    tool = client.tools.get("readonly_get_candles_latest")
    if tool is None:
        raise MCPError("read-only candle tool unavailable")
    broker_symbol = broker_symbol or symbol
    result = client.call("readonly_get_candles_latest", candle_args(tool, broker_symbol, requested_count))
    payload = decode_tool_result(result)
    frame = parse_candles(payload, source_semantics="VT_SERVER_WALL_CLOCK")
    frame = closed_rows(frame)
    frame = frame.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{symbol}_M5_RAW.parquet"
    if set(c.lower() for c in frame.columns) & {"signal", "bias", "setup", "label", "target", "entry", "sl", "tp", "future_return", "profit"}:
        raise DatasetError("strategy-derived column in raw dataset")
    frame.to_parquet(path, index=False)
    quality = validate(frame)
    try:
        file_ref = str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        file_ref = str(path)
    meta = {
        "dataset_id": f"VT_DEMO_{symbol}_M5_RAW_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "broker": "VT Markets", "environment": "Demo", "source": "mt5ReadOnly",
        "canonical_symbol": symbol, "broker_symbol": broker_symbol, "asset_class": "CRYPTO_CFD",
        "timeframe": "M5", "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "first_source_timestamp": str(frame.source_timestamp.iloc[0]) if len(frame) else None,
        "last_source_timestamp": str(frame.source_timestamp.iloc[-1]) if len(frame) else None,
        "first_timestamp_utc": quality["first_timestamp_utc"], "last_timestamp_utc": quality["last_timestamp_utc"],
        "row_count": len(frame), "source_timestamp_semantics": "VT broker server wall-clock; UTC labels (if present) are not trusted as timezone authority",
        "broker_utc_offset": server_utc_offset_hours(datetime.now(timezone.utc)),
        "broker_utc_offset_rule": OFFSET_RULE,
        "normalization_method": "server wall time minus 7h -> America/New_York wall time -> UTC using DST rules",
        "file": file_ref, "sha256": sha256_file(path),
        "quality": quality,
    }
    return path, meta, frame


def main():
    ap = argparse.ArgumentParser(description="Export strategy-blind MT5 BTC/ETH M5 to Parquet")
    ap.add_argument("--probe", default=str(RAW_DIR / "AG_CRYPTO_CFD_HISTORY_PROBE.json"))
    ap.add_argument("--env-file", help="optional local MT5 Demo env file; values are passed in memory only")
    args = ap.parse_args()
    probe = json.loads(Path(args.probe).read_text(encoding="utf-8"))
    report = {"schema": "AG_CRYPTO_CFD_RAW_PROVENANCE_V1", "datasets": [],
              "mutating_tools_executed": 0, "broker_orders_sent": 0,
              "execution_authority_added": False}
    env = read_mt5_env_file(args.env_file) if args.env_file else None
    with ReadonlyMT5Client(request_timeout=90, env_overrides=env) as client:
        _, symbols = _broker_identity(client)
        report["mt5_demo"] = True
        report["account_info_read"] = True
        report["readonly_tool_count"] = sum(n.startswith("readonly_") for n in client.tools)
        report["mutating_tool_available_to_client"] = False
        for symbol in SYMBOLS:
            rec = probe.get("symbols", {}).get(symbol, {}).get("maximum_reliable")
            if not rec or rec.get("status") != "OK" or int(rec.get("returned_count", 0)) < 1:
                raise DatasetError(f"no reliable history depth recorded for {symbol}")
            broker_symbol = symbols[symbol]
            if rec.get("broker_symbol") != broker_symbol:
                raise DatasetError(f"broker symbol authority changed for {symbol}")
            _, meta, frame = export_symbol(client, symbol, int(rec["requested_count"]), broker_symbol=broker_symbol)
            report["datasets"].append(meta)
            q = meta["quality"]
            print(json.dumps({"symbol": symbol, "rows": len(frame), "first_utc": q["first_timestamp_utc"],
                              "last_utc": q["last_timestamp_utc"], "sha256": meta["sha256"]}, separators=(",", ":")))
            if q["duplicates"] or q["nonmonotonic"] or q["invalid_ohlc"] or q["unexpected_gaps"] or q["unknown_gaps"]:
                continue
            for rule, suffix in (("15min", "M15"), ("1h", "H1"), ("1D", "D1")):
                derived = aggregate(frame, rule)
                DERIVED_DIR.mkdir(parents=True, exist_ok=True)
                out = DERIVED_DIR / f"{symbol}_{suffix}_DERIVED.parquet"
                derived.to_parquet(out, index=False)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    p = RAW_DIR / "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json"
    p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"provenance_file": str(p), "dataset_count": len(report["datasets"])}))


if __name__ == "__main__":
    main()

