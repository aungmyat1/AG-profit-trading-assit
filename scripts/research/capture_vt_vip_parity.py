"""Read-only VT EURUSD / EURUSD-VIP parity capture (research evidence only).

    python scripts/research/capture_vt_vip_parity.py --session POST_ASIAN|POST_LONDON

Preregistration: artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/PREREGISTRATION.yaml.

Each round samples EURUSD then EURUSD-VIP back to back (interleaved, fixed 5 s cadence,
720 s). Row validity/spread semantics are Unit F's (fx_friction_capture.spread_capture
.observe). Symbol metadata is snapshotted at capture start and end; matched M1 bars are
read for the capture window after sampling.

Session containment (Unit F R1 semantics): only POST_ASIAN / POST_LONDON may be requested;
the capture must fit in the window, checked before MT5 initialize and again with a fresh
clock immediately before the first sample.

Read-only: order_check/order_send/positions/orders/trade_* are replaced by blocking
counters; symbol_select is never called. Writes write-once, sha256-pinned evidence under
artifacts/validation/VT_EURUSD_VIP_PARITY_V1/<capture_id>/.
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

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)

import MetaTrader5  # noqa: E402

_BLOCKED = ("order_send", "order_check", "positions_get", "positions_total", "orders_get",
            "orders_total", "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel",
            "symbol_select")
_calls = {name: 0 for name in _BLOCKED}


def _block(name):
    def _handler(*_a, **_k):
        _calls[name] += 1
        raise RuntimeError(f"MetaTrader5.{name} is blocked in the parity collector")
    return _handler


for _name in _BLOCKED:
    setattr(MetaTrader5, _name, _block(_name))

from fx_friction_capture import spread_capture as sc  # noqa: E402
from fx_opportunity.instruments import load_brokers  # noqa: E402
from mt5.market_data import MarketDataError, server_time_timeline  # noqa: E402

SYMBOLS = ("EURUSD", "EURUSD-VIP")
ROLES = {"EURUSD": "ANALYSIS_FEED_REFERENCE", "EURUSD-VIP": "EXECUTION_FRICTION_CANDIDATE"}
PIP_SIZE = 0.0001
DURATION_SECONDS = 720
CADENCE_SECONDS = 5.0
CAPTURE_REQUEST_SESSIONS = ("POST_ASIAN", "POST_LONDON")
SYMBOL_FIELDS = ("name", "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size",
                 "volume_min", "volume_max", "volume_step", "trade_mode", "trade_exemode", "filling_mode",
                 "currency_base", "currency_profit", "currency_margin", "description", "path")
OUT_ROOT = os.path.join("artifacts", "validation", "VT_EURUSD_VIP_PARITY_V1")
COLLECTOR_VERSION = "AG_VT_VIP_PARITY_COLLECTOR_V1"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _lineage() -> str:
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    return _git("rev-parse", "HEAD") + ("+dirty" if dirty else "")


def _is_stub(module) -> bool:
    path = os.path.abspath(getattr(module, "__file__", "") or "")
    return path.startswith(os.path.abspath(_REPO) + os.sep) or hasattr(module, "MT5StubOperationAttempted")


def _stop(status: str, **extra) -> int:
    print(json.dumps({"status": status, **extra, "broker_mutation_calls": dict(_calls)}, indent=2, default=str))
    return 2


def session_gate(session: str, start: dt.datetime, duration_seconds: int):
    """None if [start, start + duration] fits inside the weekday `session` window, else a reason."""
    if session not in CAPTURE_REQUEST_SESSIONS:
        return "UNSUPPORTED_CAPTURE_SESSION"
    if sc.classify_session(start) != session:
        return "TARGET_SESSION_NOT_ACTIVE"
    window_end = next(e for name, _s, e in sc.SESSION_WINDOWS if name == session)
    if start + dt.timedelta(seconds=duration_seconds) > dt.datetime.combine(start.date(), window_end,
                                                                             tzinfo=dt.timezone.utc):
        return "INSUFFICIENT_REMAINING_SESSION_WINDOW"
    return None


def _venue() -> sc.VenueIdentity:
    info = MetaTrader5.account_info()
    server = str(getattr(info, "server", "") or "") if info is not None else ""
    demo = info is not None and getattr(info, "trade_mode", None) == getattr(MetaTrader5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    broker = next((b.canonical_name for b in load_brokers().values() if server in b.servers), "UNKNOWN")
    return sc.VenueIdentity(broker=broker, server=server, environment="DEMO" if demo else "NOT_DEMO")


def symbol_snapshot(info) -> dict:
    if info is None:
        return {"available": False}
    return {"available": True, **{f: getattr(info, f, None) for f in SYMBOL_FIELDS}}


def _utc_from_broker_seconds(seconds: float, offset_hours: float) -> dt.datetime:
    return (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=seconds)
            - dt.timedelta(hours=offset_hours))


def _m1_bars(symbol: str, start: dt.datetime, end: dt.datetime, offset_hours: float) -> list:
    """Closed M1 bars with UTC open >= start's minute and open + 1 min <= end."""
    first = start.replace(second=0, microsecond=0)
    shift = dt.timedelta(hours=offset_hours)
    rates = MetaTrader5.copy_rates_range(symbol, MetaTrader5.TIMEFRAME_M1,
                                         (first + shift).replace(tzinfo=None), (end + shift).replace(tzinfo=None))
    bars = []
    for r in (rates if rates is not None else []):
        t = _utc_from_broker_seconds(int(r["time"]), offset_hours)
        if first <= t and t + dt.timedelta(minutes=1) <= end:
            bars.append({"open_utc": t.isoformat(), "open": float(r["open"]), "high": float(r["high"]),
                         "low": float(r["low"]), "close": float(r["close"]), "tick_volume": int(r["tick_volume"]),
                         "bar_spread_points": int(r["spread"])})
    return bars


def _write_once(path: str, data: bytes) -> str:
    with open(path, "xb") as fh:
        fh.write(data)
    os.chmod(path, stat.S_IREAD)
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    args = ap.parse_args()
    now = _utcnow()
    gate = session_gate(args.session, now, DURATION_SECONDS)
    if gate == "UNSUPPORTED_CAPTURE_SESSION":
        return _stop(gate, requested_session=args.session, allowed=list(CAPTURE_REQUEST_SESSIONS))
    if gate is not None:
        return _stop("TARGET_SESSION_NOT_ACTIVE", requested_session=args.session, reason=gate,
                     now_utc=now.isoformat())
    lineage = _lineage()
    if lineage.endswith("+dirty"):
        return _stop("PARITY_CAPTURE_FAILED", reason="tracked worktree is dirty; lineage must be exact")
    if _is_stub(MetaTrader5):
        return _stop("VT_DEMO_CONNECTION_UNAVAILABLE", reason="MT5_REAL_PACKAGE_UNAVAILABLE")
    if not MetaTrader5.initialize():
        return _stop("VT_DEMO_CONNECTION_UNAVAILABLE", reason=f"MT5_INITIALIZE_FAILED:{MetaTrader5.last_error()[0]}")
    try:
        venue = _venue()
        if (venue.broker, venue.server, venue.environment) != (sc.EXPECTED_BROKER, sc.EXPECTED_SERVER,
                                                               sc.EXPECTED_ENVIRONMENT):
            return _stop("VT_DEMO_CONNECTION_UNAVAILABLE", venue=venue.__dict__, reason="VENUE_IDENTITY_MISMATCH")
        snap_start = {s: symbol_snapshot(MetaTrader5.symbol_info(s)) for s in SYMBOLS}
        missing = [s for s in SYMBOLS if not snap_start[s]["available"]]
        if missing:
            return _stop("PARITY_CAPTURE_FAILED", reason="SYMBOL_UNAVAILABLE", symbols=missing)
        try:
            offset = server_time_timeline("EURUSD", now, now).at_utc(now).utc_offset_hours
        except MarketDataError as exc:
            return _stop("PARITY_CAPTURE_FAILED", reason=exc.reason_code)

        capture_start = _utcnow()
        gate = session_gate(args.session, capture_start, DURATION_SECONDS)
        if gate is not None:
            return _stop("TARGET_SESSION_WINDOW_EXPIRED_DURING_SETUP", requested_session=args.session,
                         reason=gate, precheck_utc=now.isoformat(), capture_start_utc=capture_start.isoformat())
        capture_id = f"VT_VIP_PARITY_{args.session}_" + capture_start.strftime("%Y%m%dT%H%M%SZ") + "_" + lineage[:8]
        rows = {s: [] for s in SYMBOLS}
        rounds = int(DURATION_SECONDS // CADENCE_SECONDS)
        t0 = time.monotonic()
        seq = 0
        for k in range(rounds):
            delay = t0 + k * CADENCE_SECONDS - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -CADENCE_SECONDS:
                continue  # stall-safe: an overdue round is skipped, never burst (collector V3 rule)
            round_venue = _venue()
            for s in SYMBOLS:
                sampled = _utcnow()
                raw = MetaTrader5.symbol_info_tick(s)
                tick = None
                if raw is not None and int(getattr(raw, "time_msc", 0) or 0) > 0:
                    tick = sc.RawTick(bid=raw.bid, ask=raw.ask, time_msc=int(raw.time_msc),
                                      time_utc=_utc_from_broker_seconds(int(raw.time_msc) / 1000.0, offset))
                row = sc.observe(capture_id=capture_id, sequence=seq, sampled_at_utc=sampled, expected_symbol=s,
                                 observed_symbol=snap_start[s]["name"], venue=round_venue, tick=tick,
                                 pip_size=PIP_SIZE, git_lineage=lineage,
                                 session_classification=sc.classify_session(sampled))
                row["round"] = k
                row["tick_flags"] = int(getattr(raw, "flags", 0) or 0) if raw is not None else None
                row["symbol_role"] = ROLES[s]
                row["collector_version"] = COLLECTOR_VERSION
                rows[s].append(row)
                seq += 1
        end = _utcnow()
        snap_end = {s: symbol_snapshot(MetaTrader5.symbol_info(s)) for s in SYMBOLS}
        m1 = {s: _m1_bars(s, capture_start, end, offset) for s in SYMBOLS}
    finally:
        MetaTrader5.shutdown()

    out_dir = os.path.join(OUT_ROOT, capture_id)
    os.makedirs(out_dir, exist_ok=False)
    files = {}
    for s in SYMBOLS:
        rel = os.path.join(out_dir, f"{s}_raw.jsonl").replace(os.sep, "/")
        files[s] = {"path": rel, "sha256": _write_once(rel, sc.serialize_rows(rows[s]))}
    m1_path = os.path.join(out_dir, "m1_bars.json").replace(os.sep, "/")
    m1_bytes = (json.dumps(m1, indent=2, sort_keys=True) + "\n").encode("utf-8")
    files["m1_bars"] = {"path": m1_path, "sha256": _write_once(m1_path, m1_bytes)}
    sessions = sorted({r["session_classification"] for rs in rows.values() for r in rs})
    manifest = {
        "schema": "AG_VT_VIP_PARITY_CAPTURE_MANIFEST_V1",
        "capture_id": capture_id, "requested_session": args.session, "session_classification": sessions,
        "collector_version": COLLECTOR_VERSION, "git_lineage": lineage,
        "preregistration": "artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/PREREGISTRATION.yaml",
        "broker": venue.broker, "server": venue.server, "environment": venue.environment,
        "symbols": {s: ROLES[s] for s in SYMBOLS},
        "start_utc": capture_start.isoformat(), "end_utc": end.isoformat(),
        "sampling": {"cadence_seconds": CADENCE_SECONDS, "rounds_planned": rounds,
                     "rounds_sampled": len(rows["EURUSD"]), "order_per_round": list(SYMBOLS)},
        "server_utc_offset_hours": offset,
        "symbol_metadata": {"start": snap_start, "end": snap_end},
        "per_symbol": {s: sc.symbol_counts(rows[s]) for s in SYMBOLS},
        "files": files,
        "semantics": {"spread_pips": "(ask - bid) / 0.0001 from live ticks; bar spread recorded for parity only",
                      "zero_spread": "preserved and counted", "stale_tolerance_seconds": sc.STALE_TOLERANCE_SECONDS},
        "commission_status": "UNKNOWN", "slippage_status": "UNKNOWN/INSUFFICIENT_SAMPLE",
        "authority": {"proposal": "NONE", "demo_trade": "NONE", "live": "NONE", "trade_ticket": "NOT_CREATED"},
        "broker_mutation_calls": dict(_calls),
    }
    sc.assert_secret_free(manifest)
    data = (json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    manifest_path = os.path.join(out_dir, "manifest.json").replace(os.sep, "/")
    print(json.dumps({"capture_id": capture_id, "status": "VT_VIP_PARITY_CAPTURE_COMPLETE",
                      "manifest": manifest_path, "manifest_sha256": _write_once(manifest_path, data),
                      "per_symbol": manifest["per_symbol"], "broker_mutation_calls": dict(_calls)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
