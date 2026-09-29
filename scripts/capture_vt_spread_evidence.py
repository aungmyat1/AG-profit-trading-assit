"""Capture immutable VT Markets Demo EURUSD/GBPUSD bid/ask evidence (P6-R2, evidence only).

    python scripts/capture_vt_spread_evidence.py --session POST_ASIAN|POST_LONDON|OTHER \
        [--duration-seconds 720] [--cadence-seconds 5]

Session gate (P6-R3), checked BEFORE MT5 is initialized: the current UTC time must be
inside the requested session (canonical scanner execution windows, see
spread_capture.SESSION_WINDOWS) with at least --duration-seconds remaining, otherwise the
run stops with TARGET_SESSION_NOT_ACTIVE and creates nothing. OTHER must be requested
explicitly and must also match the actual time.

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
from fx_friction_capture.quote_metadata import SYMBOL_FIELDS, TICK_FIELDS, local_constant_tables, quote_metadata  # noqa: E402
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


def _metadata_counts(rows) -> dict:
    """Presence/counts only (acquisition verification) -- no interpretation."""
    metas = [r["quote_metadata"] for r in rows if r.get("quote_metadata")]

    def values(key):
        return sorted({json.dumps(m[key], sort_keys=True) for m in metas})
    return {"metadata": {
        "rows_with_metadata": len(metas),
        "tick_flags_present": sum("flags" in m["tick"] for m in metas),
        "trade_mode_present": sum("trade_mode" in m["symbol"] for m in metas),
        "execution_mode_present": sum("trade_exemode" in m["symbol"] for m in metas),
        "filling_mode_present": sum("filling_mode" in m["symbol"] for m in metas),
        "same_tick_as_previous_sample": sum(m["same_tick_as_previous_sample"] is True for m in metas),
        "trade_mode_decoded_values": values("trade_mode_decoded"),
        "execution_mode_decoded_values": values("execution_mode_decoded"),
        "filling_mode_decoded_values": values("filling_mode_decoded"),
        "tick_flags_decoded_values": values("tick_flags_decoded"),
    }}


def _stop(status: str, **extra) -> int:
    print(json.dumps({"status": status, **extra, "broker_mutation_calls": dict(_calls)}, indent=2, default=str))
    return 2


def session_gate(session: str, start: dt.datetime, duration_seconds: int):
    """None if a capture of `duration_seconds` starting at `start` stays inside `session`,
    else a reason code. Pure, so it is unit-tested without MT5."""
    end = start + dt.timedelta(seconds=duration_seconds)
    if sc.classify_session(start) != session:
        return "TARGET_SESSION_NOT_ACTIVE"
    if session == "OTHER":
        return None if sc.classify_session(end) == "OTHER" else "TARGET_SESSION_NOT_ACTIVE"
    window_end = next(e for name, _s, e in sc.SESSION_WINDOWS if name == session)
    if end > dt.datetime.combine(start.date(), window_end, tzinfo=dt.timezone.utc):
        return "INSUFFICIENT_REMAINING_SESSION_WINDOW"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, choices=["POST_ASIAN", "POST_LONDON", "OTHER"])
    ap.add_argument("--duration-seconds", type=int, default=720)
    ap.add_argument("--cadence-seconds", type=float, default=5.0)
    args = ap.parse_args()
    if not (60 <= args.duration_seconds <= 1800 and 1.0 <= args.cadence_seconds <= 60.0):
        return _stop("VT_CAPTURE_FAILED", reason="duration/cadence outside bounded limits")
    gate = session_gate(args.session, dt.datetime.now(dt.timezone.utc), args.duration_seconds)
    if gate is not None:
        return _stop("TARGET_SESSION_NOT_ACTIVE", requested_session=args.session, reason=gate,
                     now_utc=dt.datetime.now(dt.timezone.utc).isoformat())
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
        capture_id = f"VT_SPREAD_{args.session}_" + start.strftime("%Y%m%dT%H%M%SZ") + "_" + lineage[:8]
        constants = local_constant_tables(MetaTrader5)
        last_msc = {s: None for s in SYMBOLS}
        rows = {s: [] for s in SYMBOLS}
        rounds = int(args.duration_seconds // args.cadence_seconds)
        t0 = time.monotonic()
        seq = 0
        skipped = []
        for k in range(rounds):
            action, value = sc.round_action(k, t0, time.monotonic(), args.cadence_seconds)
            if action == "SKIP_LATE":
                skipped.append({"round": k, "lateness_seconds": round(value, 3)})
                continue
            if value > 0:
                time.sleep(value)
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
                meta = quote_metadata(raw, info, constants, last_msc[s])
                last_msc[s] = meta["tick"].get("time_msc", last_msc[s])
                rows[s].append(sc.observe(
                    capture_id=capture_id, sequence=seq, sampled_at_utc=sampled, expected_symbol=broker_symbols[s],
                    observed_symbol=getattr(info, "name", None), venue=round_venue, tick=tick,
                    pip_size=instruments[s].pip_size, git_lineage=lineage,
                    session_classification=sc.classify_session(sampled), quote_metadata=meta))
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
    base_status = sc.capture_status(rows)
    if len(skipped) > sc.MAX_SKIPPED_ROUND_FRACTION * rounds:
        base_status = "VT_CAPTURE_VALIDATION_FAILED"  # cadence broken (stall): not a valid capture
    status = (f"VT_{args.session}_CAPTURE_COMPLETE" if base_status == "VT_INITIAL_FRICTION_CAPTURE_COMPLETE"
              else "VT_CAPTURE_OUTSIDE_TARGET_SESSION" if base_status == "VT_CAPTURE_OUTSIDE_TARGET_SESSION" and args.session == "OTHER"
              else "VT_SESSION_CAPTURE_FAILED")
    manifest = {
        "schema": "AG_VT_SPREAD_CAPTURE_MANIFEST_V2",
        "capture_id": capture_id,
        "requested_session": args.session,
        "status": status,
        "collector_status": base_status,
        "broker": venue.broker, "server": venue.server, "environment": venue.environment,
        "source": sc.SOURCE,
        "semantics": {"spread_price": "ask - bid", "spread_pips": "spread_price / pip_size",
                      "a5_semantic_source": "OWNER/ARCHITECT_PROVIDED_INTERFACE_CONTRACT",
                      "bar_spread_field_used": False,
                      "stale_tolerance_seconds": sc.STALE_TOLERANCE_SECONDS,
                      "zero_spread": "preserved and flagged; not interpreted as zero economic friction"},
        "quote_metadata": {
            "purpose": "observable API facts that may help explain zero-spread quotes; interprets nothing",
            "tick_fields": list(TICK_FIELDS),
            "symbol_fields": list(SYMBOL_FIELDS),
            "decode_source": "local MetaTrader5 package constant tables only",
            "local_constant_tables": constants,
            "undecodable": "codes with no local constant table are recorded raw as UNAVAILABLE_IN_LOCAL_API",
            "same_tick_as_previous_sample": "tick time_msc equals the previous sample's time_msc for that symbol",
            "not_friction_authority": ["symbol.spread", "symbol.spread_float"],
            "executability": "no field is evidence of executability",
        },
        "symbols": list(SYMBOLS),
        "instrument_spec": spec,
        "server_clock": clock,
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "duration_seconds": round((end - start).total_seconds(), 3),
        "session_classification": sessions[0] if len(sessions) == 1 else sessions,
        "sampling": {"cadence_seconds": args.cadence_seconds, "rounds": rounds,
                     "scheduled_rounds": rounds, "executed_rounds": rounds - len(skipped),
                     "skipped_late_rounds": skipped,
                     "skip_rule": "a round more than one cadence late is skipped, never burst or backfilled",
                     "max_skipped_round_fraction": sc.MAX_SKIPPED_ROUND_FRACTION,
                     "order_per_round": list(SYMBOLS), "mode": "INTERLEAVED_FIXED_CADENCE"},
        "per_symbol": {s: {**sc.symbol_counts(rows[s]), **_metadata_counts(rows[s]), "pip_size": instruments[s].pip_size,
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
    return 0 if status != "VT_SESSION_CAPTURE_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
