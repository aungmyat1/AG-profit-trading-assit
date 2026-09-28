"""Capture immutable VT Markets Demo EURUSD/GBPUSD bid/ask evidence (P6-R2, evidence only).

    python scripts/capture_vt_spread_evidence.py [--duration-seconds 720] [--cadence-seconds 5]

Attaches to the already-running, logged-in terminal (no credentials passed or read).
Gates before any tick is read: real MetaTrader5 package (repo stub refused), Demo account,
server listed for VTMARKETS, broker digits/point == instrument contract. Then samples
EURUSD and GBPUSD back-to-back each round on a fixed cadence (round k at start + k*cadence),
reading raw symbol_info_tick bid/ask. The venue identity is re-read every round; any
mismatch is recorded per row and fails the capture closed.

Writes, write-once (exclusive create, then read-only):
    artifacts/validation/VT_MARKETS_FRICTION_EVIDENCE/<capture_id>/{EURUSD,GBPUSD}_raw.jsonl
    artifacts/validation/VT_MARKETS_FRICTION_EVIDENCE/<capture_id>/manifest.json
A correction needs a new capture_id. Broker-mutation APIs are replaced by blocking counters.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)

import MetaTrader5  # noqa: E402

_BLOCKED = ("order_send", "order_check", "positions_get", "positions_total", "orders_get",
            "orders_total", "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel")
_calls = {name: 0 for name in _BLOCKED}


def _block(name):
    def _handler(*_a, **_k):
        _calls[name] += 1
        raise RuntimeError(f"MetaTrader5.{name} is blocked in the spread evidence collector")
    return _handler


for _name in _BLOCKED:
    setattr(MetaTrader5, _name, _block(_name))

from fx_friction_capture import spread_capture as sc  # noqa: E402
from fx_opportunity.instruments import check_broker_spec, get_instrument, load_brokers  # noqa: E402
from mt5.market_data import MarketDataError, server_time_provenance, server_time_timeline  # noqa: E402

SYMBOLS = ("EURUSD", "GBPUSD")
BROKER_KEY = "VTMARKETS"
OUT_ROOT = os.path.join("artifacts", "validation", "VT_MARKETS_FRICTION_EVIDENCE")


def _is_stub(module) -> bool:
    path = os.path.abspath(getattr(module, "__file__", "") or "")
    return path.startswith(os.path.abspath(_REPO) + os.sep) or hasattr(module, "MT5StubOperationAttempted")


def _git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _lineage() -> str:
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    return _git("rev-parse", "HEAD") + ("+dirty" if dirty else "")


def _file_sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _venue() -> sc.VenueIdentity:
    """Non-secret venue identity only: server name + Demo/Live mode (never the login)."""
    info = MetaTrader5.account_info()
    server = str(getattr(info, "server", "") or "") if info is not None else ""
    demo = info is not None and getattr(info, "trade_mode", None) == getattr(MetaTrader5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    broker = next((b.canonical_name for b in load_brokers().values() if server in b.servers), "UNKNOWN")
    return sc.VenueIdentity(broker=broker, server=server, environment="DEMO" if demo else "NOT_DEMO")


def _write_once(path: str, data: bytes) -> str:
    with open(path, "xb") as fh:  # exclusive create: never overwrite evidence
        fh.write(data)
    os.chmod(path, stat.S_IREAD)
    return sc.sha256(data)


def _stop(reason: str, **extra) -> int:
    print(json.dumps({"status": reason, **extra, "broker_mutation_calls": dict(_calls)}, indent=2, default=str))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration-seconds", type=int, default=720)
    ap.add_argument("--cadence-seconds", type=float, default=5.0)
    args = ap.parse_args()
    if not (60 <= args.duration_seconds <= 1800 and 1.0 <= args.cadence_seconds <= 60.0):
        return _stop("VT_CAPTURE_FAILED", reason="duration/cadence outside bounded limits")
    lineage = _lineage()
    if lineage.endswith("+dirty"):
        return _stop("VT_CAPTURE_FAILED", reason="tracked worktree is dirty; lineage must be exact")
    if _is_stub(MetaTrader5):
        return _stop("VT_DEMO_CONNECTION_UNAVAILABLE", reason="MT5_REAL_PACKAGE_UNAVAILABLE")
    if not MetaTrader5.initialize():
        return _stop("VT_DEMO_CONNECTION_UNAVAILABLE", reason=f"MT5_INITIALIZE_FAILED:{MetaTrader5.last_error()[0]}")
    try:
        venue = _venue()
        if (venue.broker, venue.server, venue.environment) != (sc.EXPECTED_BROKER, sc.EXPECTED_SERVER, sc.EXPECTED_ENVIRONMENT):
            return _stop("VT_DEMO_CONNECTION_UNAVAILABLE", venue=venue.__dict__, reason="VENUE_IDENTITY_MISMATCH")
        instruments = {s: get_instrument(s) for s in SYMBOLS}
        broker_symbols = {s: instruments[s].broker_symbol(BROKER_KEY).symbol for s in SYMBOLS}
        spec = {}
        for s in SYMBOLS:
            info = MetaTrader5.symbol_info(broker_symbols[s])
            mismatch = check_broker_spec(instruments[s], info)
            if mismatch:
                return _stop("VT_CAPTURE_VALIDATION_FAILED", symbol=s, reason=list(mismatch))
            spec[s] = {"broker_symbol": info.name, "digits": info.digits, "point": info.point,
                       "pip_size": instruments[s].pip_size}

        start = dt.datetime.now(dt.timezone.utc)
        try:
            clock = {s: server_time_provenance(broker_symbols[s], start, start) for s in SYMBOLS}
            offset = server_time_timeline(broker_symbols["EURUSD"], start, start).at_utc(start).utc_offset_hours
        except MarketDataError as exc:
            return _stop("VT_CAPTURE_FAILED", reason=exc.reason_code)
        capture_id = "VT_SPREAD_" + start.strftime("%Y%m%dT%H%M%SZ") + "_" + lineage[:8]
        rows = {s: [] for s in SYMBOLS}
        rounds = int(args.duration_seconds // args.cadence_seconds)
        t0 = time.monotonic()
        seq = 0
        for k in range(rounds):
            delay = t0 + k * args.cadence_seconds - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            round_venue = _venue()
            for s in SYMBOLS:
                sampled = dt.datetime.now(dt.timezone.utc)
                raw = MetaTrader5.symbol_info_tick(broker_symbols[s])
                info = MetaTrader5.symbol_info(broker_symbols[s])
                tick = None
                if raw is not None and int(getattr(raw, "time_msc", 0) or 0) > 0:
                    tick_utc = (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
                                + dt.timedelta(milliseconds=int(raw.time_msc)) - dt.timedelta(hours=offset))
                    tick = sc.RawTick(bid=raw.bid, ask=raw.ask, time_utc=tick_utc, time_msc=int(raw.time_msc))
                rows[s].append(sc.observe(
                    capture_id=capture_id, sequence=seq, sampled_at_utc=sampled, expected_symbol=broker_symbols[s],
                    observed_symbol=getattr(info, "name", None), venue=round_venue, tick=tick,
                    pip_size=instruments[s].pip_size, git_lineage=lineage,
                    session_classification=sc.classify_session(sampled)))
                seq += 1
        end = dt.datetime.now(dt.timezone.utc)
    finally:
        MetaTrader5.shutdown()

    out_dir = os.path.join(OUT_ROOT, capture_id)
    os.makedirs(out_dir, exist_ok=False)
    raw_files = {}
    for s in SYMBOLS:
        rel = os.path.join(out_dir, f"{s}_raw.jsonl").replace(os.sep, "/")
        raw_files[s] = {"path": rel, "sha256": _write_once(rel, sc.serialize_rows(rows[s]))}
    sessions = sorted({r["session_classification"] for rs in rows.values() for r in rs})
    manifest = {
        "schema": "AG_VT_SPREAD_CAPTURE_MANIFEST_V1",
        "capture_id": capture_id,
        "status": sc.capture_status(rows),
        "broker": venue.broker, "server": venue.server, "environment": venue.environment,
        "source": sc.SOURCE,
        "semantics": {"spread_price": "ask - bid", "spread_pips": "spread_price / pip_size",
                      "a5_semantic_source": "OWNER/ARCHITECT_PROVIDED_INTERFACE_CONTRACT",
                      "bar_spread_field_used": False,
                      "stale_tolerance_seconds": sc.STALE_TOLERANCE_SECONDS,
                      "zero_spread": "preserved and flagged; not interpreted as zero economic friction"},
        "symbols": list(SYMBOLS),
        "instrument_spec": spec,
        "server_clock": clock,
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "duration_seconds": round((end - start).total_seconds(), 3),
        "session_classification": sessions[0] if len(sessions) == 1 else sessions,
        "sampling": {"cadence_seconds": args.cadence_seconds, "rounds": rounds,
                     "order_per_round": list(SYMBOLS), "mode": "INTERLEAVED_FIXED_CADENCE"},
        "per_symbol": {s: {**sc.symbol_counts(rows[s]), "pip_size": instruments[s].pip_size,
                           "raw_path": raw_files[s]["path"], "raw_sha256": raw_files[s]["sha256"]} for s in SYMBOLS},
        "collector": {"version": sc.COLLECTOR_VERSION, "git_lineage": lineage,
                      "module_sha256": _file_sha("src/fx_friction_capture/spread_capture.py"),
                      "script_sha256": _file_sha("scripts/capture_vt_spread_evidence.py")},
        "commission_status": "UNKNOWN",
        "slippage_status": "UNKNOWN/INSUFFICIENT_SAMPLE",
        "authority": {"proposal": "NONE", "demo_trade": "NONE", "live": "NONE", "trade_ticket": "NOT_CREATED"},
        "broker_mutation_calls": dict(_calls),
    }
    sc.assert_secret_free(manifest)
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = os.path.join(out_dir, "manifest.json").replace(os.sep, "/")
    manifest_hash = _write_once(manifest_path, data)
    print(json.dumps({"capture_id": capture_id, "status": manifest["status"], "manifest": manifest_path,
                      "manifest_sha256": manifest_hash, "per_symbol": manifest["per_symbol"],
                      "broker_mutation_calls": dict(_calls)}, indent=2))
    return 0 if manifest["status"] != "VT_CAPTURE_VALIDATION_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
