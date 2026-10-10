"""AGP-LANE-B: replay ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0 on the VT recorded BTCUSD/ETHUSD captures.

Inputs are the PR #128 / #131 recorded files (tests/fixtures/ccfd_v100/recorded, every sha256 in its
manifest is verified first). Nothing here adds time or pricing code; it only wires existing modules:

  engine     crypto_cfd_contract.evaluate (guard.evaluate: drops any bar with close_time > now on
             every timeframe, then the frozen rules.evaluate) -- the CFD contract's entry point
             (strategy_engine.session.Candle input, strategy_engine.sweep_retest primitives).
             strategy_engine.evaluate() is the FX session-box entry; it needs session_pairs, which
             this contract forbids (FX_SESSION_GATE_APPLIED=False), so it is not called.
  time       v1_tickets.crypto_cfd._closed (server-rule D1 close), ._config/._window (WEEKDAY and
             WEEKEND gates), crypto_cfd_contract.rules UTC-day windows, session_clock (display only).
  tickets    v1_tickets.crypto_cfd.build_crypto_cfd_cycle and
             v1_tickets.manual_ticket.build_crypto_cfd_manual_ticket -- unchanged v1_tickets schema;
             lot size via manual_ticket.lot_size -> sizing_math.risk.size_position.
  spread     manual_ticket.crypto_cfd_cost_gate with config/v1_tickets/crypto_cfd_ticket_policy.yaml
             (owner bands: <=10% of stop OK, 10-20% WARN, >20% BLOCK). Bands change ticket state
             only; no L1-L6 check reads them.

Scan: every M5 close of every UTC day in the capture, weekends included. Tickets: one live-cycle
ticket per manifest case (each M15 close inside a WEEKDAY/WEEKEND window), plus one research
ticket at each first ENTRY_VALID scan of a UTC day (stream EMISSION_RESEARCH, beside the live-cycle
decision for the same instant). The replay quote is the last closed M5 bar: bid = recorded close
(MT5 bars are bid bars), ask = bid + recorded spread_price. balance defaults to None: no account
equity is invented, so READY-capable tickets carry ACCOUNT_BALANCE_UNAVAILABLE.

Read-only and hermetic: no broker, network or MT5 call; registry untouched.

    python scripts/ccfd_sweep_retest_replay.py --date 2026-10-10 [--out-dir DIR] [--balance X]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

# Import-only Linux MetaTrader5 portability shim (raises on any real MT5 call).
if "MetaTrader5" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("ccfd_replay_test_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))

import yaml  # noqa: E402

from crypto_cfd_contract import guard, rules  # noqa: E402
from crypto_cfd_contract.contract import (  # noqa: E402
    CONTRACT_ID,
    CONTRACT_VERSION,
    CONTRACT_YAML,
    INSTRUMENTS,
    STOP_BUFFER_PRICE,
    TP1_VOLUME_PCT,
)
from market_structure.config import load_market_structure_config  # noqa: E402
from scripts.ccfd_recorded_cases import (  # noqa: E402
    RECORDED,
    RECORDED_60D,
    parse_ts,
    read_rows,
    shared_paths,
    verify,
)
from session_clock import local_time_diagnostics  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from strategy_engine.sweep_retest.retest import ENTRY_TTL_M5_BARS  # noqa: E402
from strategy_engine.sweep_retest.targets import MIN_TP2_R_MULTIPLE  # noqa: E402
from ticket_delivery.renderer import payload_hash  # noqa: E402
from v1_tickets import crypto_cfd, manual_ticket  # noqa: E402
from v1_tickets.authority import logic_identity  # noqa: E402
from v1_tickets.crypto_cfd_policy import load_ticket_policy  # noqa: E402
from v1_tickets.logic_gate import (  # noqa: E402
    FAIL,
    PASS,
    l1_determinism,
    l5_cost,
    l6_freshness,
)

UTC = dt.timezone.utc
INSUFFICIENT = "INSUFFICIENT"
STEP = {"D1": dt.timedelta(days=1), "H1": dt.timedelta(hours=1), "M15": dt.timedelta(minutes=15),
        "M5": dt.timedelta(minutes=5)}
M5 = STEP["M5"]
SIGNAL_TTL = M5 + dt.timedelta(minutes=15)   # manual_ticket.build_crypto_cfd_manual_ticket valid_until
MANIFEST = RECORDED / "manifest.json"
REGISTRY = ROOT / "strategies/registry.yaml"
ARTIFACTS = ROOT / "artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0_0"
OUT_DIR = ARTIFACTS / "vt_recorded_2026-09-26_2026-10-09"
DATASETS = {"recorded": (RECORDED, OUT_DIR),                                   # PR #128/#131, 14 days
            "recorded_60d": (RECORDED_60D, ARTIFACTS / "vt_recorded_60d_2026-08-11_2026-10-09")}   # PR #143
COVERAGE_ONLY = OUT_DIR / "coverage_only_binance.json"     # scripts/ccfd_coverage_binance.py (dataset-independent)


# ------------------------------------------------------------------------------- data / feed

def load_symbol(symbol: str, base: Path = RECORDED) -> Dict[str, Any]:
    """Recorded rows exactly as committed: a missing bar stays missing (never filled or interpolated),
    so an incomplete day reaches the contract's own REFERENCE_INCOMPLETE / data-incomplete path."""
    paths = shared_paths(symbol, base)
    bars = {tf: [Candle(parse_ts(r["timestamp_utc"]), float(r["open"]), float(r["high"]), float(r["low"]),
                        float(r["close"])) for r in read_rows(base / paths[tf.lower()])] for tf in STEP}
    spread = {parse_ts(r["timestamp_utc"]): float(r["spread_price"])
              for r in read_rows(base / f"{symbol}_m5_meta.csv")}
    return {"bars": bars, "times": {tf: [c.time for c in rows] for tf, rows in bars.items()}, "spread": spread}


class ReplayFeed:
    """ReadOnlyCryptoFeed over the recorded capture as of `now`: bars opened before `now` (the forming
    bar included, as a terminal returns it; crypto_cfd._closed drops it) and the last closed M5 quote."""

    def __init__(self, data: Dict[str, Any], now: dt.datetime):
        self.data, self.now, self.requests = data, now, []

    def fetch(self, broker_symbol: str, timeframe: str, count: int) -> List[Candle]:
        self.requests.append((timeframe, count))
        end = bisect.bisect_left(self.data["times"][timeframe], self.now)
        return self.data["bars"][timeframe][max(0, end - count):end]

    def quote(self, broker_symbol: str):
        bar_open = self.now - M5
        i = bisect.bisect_left(self.data["times"]["M5"], bar_open)
        if i == len(self.data["times"]["M5"]) or self.data["times"]["M5"][i] != bar_open:
            raise ValueError("QUOTE_UNAVAILABLE")      # never invented from a neighbouring bar
        bid = self.data["bars"]["M5"][i].close
        return bid, round(bid + self.data["spread"][bar_open], 2), bar_open


def closed_inputs(data, now, counts) -> Dict[str, List[Candle]]:
    feed = ReplayFeed(data, now)
    return {tf: crypto_cfd._closed(feed.fetch("", tf, counts[tf]), now, STEP[tf]) for tf in STEP}


def engine(symbol, now, x, cfg) -> dict:
    return guard.evaluate(symbol, now, x["D1"], x["H1"], x["M5"], x["M15"], structure_config=cfg)


def semantic(r: dict) -> dict:
    ev = r["evidence"]
    return {"result": r["result"], **{k: ev.get(k) for k in ("sweep", "mss", "retest", "target_plan")}}


def day_type(day: dt.date) -> str:
    return "WEEKEND" if day.isoweekday() in (6, 7) else "WEEKDAY"


# ------------------------------------------------------------------------------- L2 / L4 checks

def reconstruct(r: dict, x: Dict[str, List[Candle]], now: dt.datetime, spec: dict) -> List[str]:
    """Re-derive an ENTRY_VALID result from raw closed candles and the YAML predicates; return the ids
    of failed checks. MSS swing location is the shared full_swings primitive and is taken as given."""
    ev, plan, bad = r["evidence"], r["evidence"]["target_plan"], []
    start, end = rules.previous_utc_day_window(now)
    prev = [c for c in x["M5"] if start <= c.time < end]
    if [c.time for c in prev] != [start + i * M5 for i in range(288)]:
        return ["reference_grid"]
    pdh, pdl = max(c.high for c in prev), min(c.low for c in prev)
    long = plan["direction"] == "LONG"
    if ev["context"]["direction_permission"] != ("LONG_ALLOWED" if long else "SHORT_ALLOWED"):
        bad.append("permission_side")
    if (ev["reference"]["high"], ev["reference"]["low"], ev["reference"]["mid"]) != (pdh, pdl, (pdh + pdl) / 2):
        bad.append("reference_levels")
    day0, _ = rules.utc_day_window(now)
    today = [c for c in x["M5"] if c.time >= day0]

    def swept(c):   # YAML m5_trigger_contract.sweep; dual-side candle skipped
        hi, lo = c.high > pdh and c.close < pdh, c.low < pdl and c.close > pdl
        return (lo if long else hi) and not (hi and lo)
    sweep = next((c for c in today if swept(c)), None)
    if sweep is None or sweep.time.isoformat() != ev["sweep"]["candle_time_utc"]:
        return bad + ["first_sweep"]
    level = ev["mss"]["broken_swing_price"]
    mss = next((c for c in today if c.time > sweep.time and (c.close > level if long else c.close < level)), None)
    if mss is None or mss.time.isoformat() != ev["mss"]["confirmed_at_utc"]:
        return bad + ["mss_close_break"]
    window = [c for c in today if c.time > mss.time][:ENTRY_TTL_M5_BARS]
    touch = next((c for c in window if (c.low <= level if long else c.high >= level)), None)
    if touch is None or touch.time.isoformat() != ev["retest"]["candle_time_utc"]:
        bad.append("retest_first_touch_ttl")
    stop = (sweep.low - STOP_BUFFER_PRICE) if long else (sweep.high + STOP_BUFFER_PRICE)
    expected = {"entry": level, "stop_loss": stop, "tp1": (pdh + pdl) / 2, "tp2": pdh if long else pdl}
    bad += [f"plan_{k}" for k, v in expected.items() if plan[k] != v]
    if plan["tp1_volume_pct"] != spec["targets_contract"]["tp1_volume_pct"]:
        bad.append("tp1_split")
    return bad


def geometry_ok(plan: dict) -> bool:
    entry, sl, tp1, tp2, risk = (plan[k] for k in ("entry", "stop_loss", "tp1", "tp2", "risk_distance"))
    long = plan["direction"] == "LONG"
    ordered = sl < entry < tp1 < tp2 if long else sl > entry > tp1 > tp2
    rr = abs(tp2 - entry) / risk if risk and risk > 0 else None
    return (ordered and risk > 0 and math.isclose(risk, abs(entry - sl)) and rr is not None
            and rr >= MIN_TP2_R_MULTIPLE and math.isclose(rr, plan["tp2_r_multiple"]))


def geometry_reject_ok(plan: dict) -> bool:
    """NO_TRADE_TARGET_GEOMETRY must really violate the guard: wrong-side target or RR < 1.5."""
    entry, tp1, tp2 = plan["entry"], plan["tp1"], plan["tp2"]
    wrong_side = not (tp1 > entry and tp2 > entry) if plan["direction"] == "LONG" else not (tp1 < entry and tp2 < entry)
    return wrong_side or (plan["tp2_r_multiple"] is not None and plan["tp2_r_multiple"] < MIN_TP2_R_MULTIPLE)


# ------------------------------------------------------------------------------- rule coverage

# Spec rule ids = YAML paths of strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml. scope: ANY (direction-
# independent: both direction cells share one status), LONG/SHORT (other direction NOT_APPLICABLE), BOTH.
RULES = (
    ("liquidity_contract.levels", "ANY"),
    ("liquidity_contract.completeness_rule", "ANY"),
    ("context_contract.direction_permission.h1_unresolved", "ANY"),
    ("context_contract.direction_permission.d1_confirmed_and_opposes_h1", "BOTH"),
    ("context_contract.direction_permission.h1_bullish", "LONG"),
    ("context_contract.direction_permission.h1_bearish", "SHORT"),
    ("context_contract.direction_permission.d1_unresolved", "BOTH"),
    ("m5_trigger_contract.sweep.long_candidate", "LONG"),
    ("m5_trigger_contract.sweep.short_candidate", "SHORT"),
    ("m5_trigger_contract.sweep.dual_side_candle", "BOTH"),
    ("m5_trigger_contract.sweep.direction_gate", "BOTH"),
    ("m5_trigger_contract.mss.confirmation", "BOTH"),
    ("m5_trigger_contract.retest", "BOTH"),
    ("signal_expiry_contract.rule_1", "BOTH"),
    ("signal_expiry_contract.rule_2", "BOTH"),
    ("targets_contract.geometry_guard", "BOTH"),
    ("invalidation_contract.INVALID_STOP_DISTANCE", "BOTH"),
    ("stop_loss_contract.long", "LONG"),
    ("stop_loss_contract.short", "SHORT"),
    ("targets_contract.tp1_tp2_min_tp2_r_multiple", "BOTH"),
    ("entry_timing_contract.actionable_event", "BOTH"),
)
WINDOWS = ("IN_WINDOW", "OUT_OF_WINDOW")

# AGP-LANE-B3 (owner ruling 2026-10-11, item 3): rejection-only rules -- every outcome is a non-entry result --
# may be proven by synthetic unit cases (SYNTHETIC_PROVEN). rules.evaluate takes no window input (the window is a
# ticket-layer gate), so one synthetic case per direction covers both window cells. Entry-branch rules (the rest)
# need VT exercise; LOGIC_VERIFIED is per symbol x entry branch (OD1011-SCOPE).
SYNTHETIC_TESTS = "tests/test_ccfd_synthetic_rejections.py"
SYNTHETIC_PROOFS = {
    "liquidity_contract.completeness_rule": "test_incomplete_reference_fails_closed",
    "context_contract.direction_permission.h1_unresolved": "test_h1_unresolved_gives_no_direction",
    "context_contract.direction_permission.d1_confirmed_and_opposes_h1": "test_d1_conflict_vetoes_direction",
    "m5_trigger_contract.sweep.dual_side_candle": "test_dual_side_candle_only_blocks",
    "m5_trigger_contract.sweep.direction_gate": "test_wrong_side_sweep_is_ignored",
    "signal_expiry_contract.rule_1": "test_rule_1_no_retest_within_ttl_expires",
    "signal_expiry_contract.rule_2": "test_rule_2_utc_day_rotation_kills_the_sequence",
    "targets_contract.geometry_guard": "test_geometry_guard_rejects",
    "invalidation_contract.INVALID_STOP_DISTANCE": "test_invalid_stop_distance_rejects",
}
BRANCHES = ("LONG", "SHORT")


def rule_events(r: dict, x: Dict[str, List[Candle]], now: dt.datetime) -> set:
    """(rule_id, LONG|SHORT|ANY) exercised by one scan, read from the engine result and its closed input."""
    ev, res, out = r["evidence"], r["result"], set()
    if res == "REFERENCE_INCOMPLETE":
        return {("liquidity_contract.completeness_rule", "ANY")}
    out.add(("liquidity_contract.levels", "ANY"))
    ctx = ev.get("context", {})
    perm, h1 = ctx.get("direction_permission"), ctx.get("h1_structure")
    if h1 not in ("BULLISH", "BEARISH"):
        return out | {("context_contract.direction_permission.h1_unresolved", "ANY")}
    side = "LONG" if h1 == "BULLISH" else "SHORT"
    if perm == "NO_DIRECTION":
        return out | {("context_contract.direction_permission.d1_confirmed_and_opposes_h1", side)}
    out.add((f"context_contract.direction_permission.h1_{'bullish' if side == 'LONG' else 'bearish'}", side))
    if ctx.get("d1_structure") not in ("BULLISH", "BEARISH"):
        out.add(("context_contract.direction_permission.d1_unresolved", side))
    pdh, pdl = ev["reference"]["high"], ev["reference"]["low"]
    day0, _ = rules.utc_day_window(now)
    for c in (c for c in x["M5"] if c.time >= day0):
        hi, lo = c.high > pdh and c.close < pdh, c.low < pdl and c.close > pdl
        if hi and lo:
            out.add(("m5_trigger_contract.sweep.dual_side_candle", side))
        elif (hi and side == "LONG") or (lo and side == "SHORT"):
            out.add(("m5_trigger_contract.sweep.direction_gate", side))
    if "sweep" in ev:
        out.add((f"m5_trigger_contract.sweep.{side.lower()}_candidate", side))
    if "mss" in ev:
        out.add(("m5_trigger_contract.mss.confirmation", side))
    if res == "SIGNAL_ENTRY_WINDOW_PASSED":
        out.add(("signal_expiry_contract.rule_1", side))
    if "retest" in ev:
        out.add(("m5_trigger_contract.retest", side))
    if res == "NO_TRADE_TARGET_GEOMETRY":
        out.add(("targets_contract.geometry_guard", side))
    if res == "INVALID_STOP_DISTANCE":
        out.add(("invalidation_contract.INVALID_STOP_DISTANCE", side))
    if res == "ENTRY_VALID":
        out |= {(f"stop_loss_contract.{side.lower()}", side), ("targets_contract.tp1_tp2_min_tp2_r_multiple", side),
                ("entry_timing_contract.actionable_event", side)}
    return out


def coverage_matrix(hits: Counter) -> dict:
    """hits[(rule, LONG|SHORT|ANY, window)] = scans -> rule x direction x window: EXERCISED / NOT_EXERCISED
    (NOT_APPLICABLE for the other side of a one-sided rule)."""
    out = {}
    for rule, scope in RULES:
        row = {}
        for d in ("LONG", "SHORT"):
            for w in WINDOWS:
                if scope in ("LONG", "SHORT") and d != scope:
                    row[f"{d}|{w}"] = {"status": "NOT_APPLICABLE", "scans": 0}
                    continue
                n = hits[(rule, "ANY" if scope == "ANY" else d, w)]
                row[f"{d}|{w}"] = {"status": "EXERCISED" if n else "NOT_EXERCISED", "scans": n}
        out[rule] = {"scope": scope, "cells": row}
    return out


def coverage_gaps(matrix: dict) -> List[str]:
    return [f"{rule}|{cell}" for rule, m in matrix.items() for cell, v in m["cells"].items()
            if v["status"] == "NOT_EXERCISED"]


def proof_matrix(vt: dict, cov_only: Optional[dict]) -> Dict[str, Dict[str, str]]:
    """Per cell: EXERCISED (VT) / SYNTHETIC_PROVEN (VT gap, rejection-only rule with a synthetic unit case) /
    COVERAGE_ONLY_EXERCISED (VT gap hit only on Binance bars: non-authoritative, never counts) / NOT_EXERCISED."""
    binance_gaps = set(cov_only["not_exercised"]) if cov_only else None
    out: Dict[str, Dict[str, str]] = {}
    for rule, m in vt.items():
        row = {}
        for cell, c in m["cells"].items():
            st = c["status"]
            if st == "NOT_EXERCISED" and rule in SYNTHETIC_PROOFS:
                st = "SYNTHETIC_PROVEN"
            elif st == "NOT_EXERCISED" and binance_gaps is not None and f"{rule}|{cell}" not in binance_gaps:
                st = "COVERAGE_ONLY_EXERCISED"
            row[cell] = st
        out[rule] = row
    return out


def branch_verdict(r: dict, proof: Dict[str, Dict[str, str]], side: str) -> dict:
    """LOGIC_VERIFIED for symbol x branch only when the branch's L1-L4/L6 PASS, L5 PASS (OD1011-L5), the run is
    mismatch-free (0 event-log mismatches) and every rule cell of that direction -- both windows -- is VT
    EXERCISED or (rejection-only) SYNTHETIC_PROVEN. Entry-branch rules can only be VT EXERCISED."""
    b = r["branches"][side]
    blocking = [f"{g}={st}" for g, st in b["gates"].items() if st != PASS]
    if not mismatch_free(r):
        blocking.append("MISMATCHES")
    blocking += [f"COVERAGE:{rule}|{cell}={st}" for rule, row in proof.items() for cell, st in row.items()
                 if cell.startswith(side + "|") and st not in ("EXERCISED", "SYNTHETIC_PROVEN", "NOT_APPLICABLE")]
    return {"verified": not blocking, "blocking": blocking, **b}


# ------------------------------------------------------------------------------- signal event log

# Owner ruling 2026-10-11 (AGP-LANE-B3, option A): direction permission is re-checked on every scan (frozen
# rules 1.0.0). The replay records signal events append-only and L3 compares the event log, not the scan.
EVENT_TYPES = ("EMIT", "WITHDRAW", "EXPIRE", "REISSUE")
# Signal-expiry window of an emitted signal = the ticket freshness rule already in
# manual_ticket.build_crypto_cfd_manual_ticket: SIGNAL_STALE once now > retest open + M5 + 15 min
# (valid_until). SIGNAL_TTL above mirrors it; no new time arithmetic.
EXPIRY_RULE = "SIGNAL_STALE once now > retest candle open + 5 min + 15 min (manual_ticket valid_until)"


def _signal_key(sem: dict) -> str:
    return json.dumps(sem, sort_keys=True, default=str)


def _retest_at(sem: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(sem["retest"]["candle_time_utc"])


def signal_events(stream: Sequence[tuple]) -> List[dict]:
    """Append-only signal event log over the chronological scan stream [(now, semantic)].

    A signal is one ENTRY_VALID payload (sweep, MSS, retest, plan). EMIT = first appearance; WITHDRAW = an
    active signal is no longer returned (reason = the scan result, or SUPERSEDED); EXPIRE = an active signal
    passes its expiry window (SIGNAL_STALE) or the UTC day rotates (signal_expiry rule_2); REISSUE = a signal
    seen before is returned again after it stopped being active. EMIT/REISSUE carry freshness: FRESH when
    now <= retest open + SIGNAL_TTL, else EXPIRED (never actionable; it never becomes active). An expired
    signal the engine keeps returning on consecutive scans is a continuation, not a new event."""
    events: List[dict] = []
    state: Dict[str, str] = {}
    sems: Dict[str, dict] = {}
    active: Optional[str] = None
    last: Optional[str] = None

    def add(kind: str, now: dt.datetime, key: str, reason: str, freshness: Optional[str] = None) -> None:
        sem = sems[key]
        ev = {"seq": len(events), "type": kind, "bar_close_utc": now.isoformat(),
              "retest_candle_time_utc": sem["retest"]["candle_time_utc"],
              "direction": sem["target_plan"]["direction"],
              "signal_id": hashlib.sha256(key.encode()).hexdigest()[:16], "reason": reason}
        if freshness is not None:
            ev["freshness"] = freshness
        events.append(ev)

    for now, sem in stream:
        if active is not None:
            retest = _retest_at(sems[active])
            if now > retest + SIGNAL_TTL or now.date() != retest.date():
                add("EXPIRE", now, active, "SIGNAL_STALE" if now > retest + SIGNAL_TTL else "UTC_DAY_ROTATION")
                state[active], active = "EXPIRED", None
        key = _signal_key(sem) if sem["result"] == "ENTRY_VALID" else None
        if active is not None and key != active:
            add("WITHDRAW", now, active, sem["result"] if key is None else "SUPERSEDED")
            state[active], active = "WITHDRAWN", None
        if key is not None and active is None and not (key == last and state.get(key) == "EXPIRED"):
            sems.setdefault(key, sem)
            fresh = now <= _retest_at(sem) + SIGNAL_TTL
            add("REISSUE" if key in state else "EMIT", now, key, sem["result"], "FRESH" if fresh else "EXPIRED")
            state[key] = "ACTIVE" if fresh else "EXPIRED"
            active = key if fresh else None
        last = key
    return events


def _diff_events(expected: List[dict], got: List[dict], kind: str) -> List[dict]:
    out = []
    for i in range(max(len(expected), len(got))):
        a = expected[i] if i < len(expected) else None
        b = got[i] if i < len(got) else None
        if a != b:
            out.append({"check": kind, "seq": i,
                        "mismatch": "ADDED" if a is None else "REMOVED" if b is None else "CHANGED",
                        "event_type": (a or b)["type"], "bar_close_utc": (a or b)["bar_close_utc"]})
    return out


# TEMP(AGP-ORACLE): inline event-log prefix invariance. Replace with the AGP-ORACLE prefix_invariance
# import once that PR is merged; do not extend this function.
def event_log_invariance(stream: Sequence[tuple], future_stream: Sequence[tuple]) -> dict:
    """L3: no event at or before t may change when bars after t are added.

    (a) PREFIX: the log built from the scans up to every cut t equals the full log's events at or before t
        (cuts: every UTC-day end and each scan at/just after an event).
    (b) FUTURE_BARS: the log built from scans that were handed every later bar (guard.evaluate drops them)
        equals the log built from closed-only input."""
    full = signal_events(stream)
    times = [now for now, _ in stream]
    at = {now: k for k, now in enumerate(times)}
    cuts = {k + 1 for k in range(len(times)) if k + 1 == len(times) or times[k + 1].date() != times[k].date()}
    for e in full:
        k = at[dt.datetime.fromisoformat(e["bar_close_utc"])]
        cuts |= {k, k + 1, min(k + 2, len(times))}
    cuts.discard(0)
    mism: List[dict] = []
    for k in sorted(cuts):
        cut = times[k - 1]
        mism += _diff_events([e for e in full if dt.datetime.fromisoformat(e["bar_close_utc"]) <= cut],
                             signal_events(stream[:k]), "PREFIX")
    mism += _diff_events(full, signal_events(future_stream), "FUTURE_BARS")
    by_type = Counter(f"{m['check']}:{m['mismatch']}:{m['event_type']}" for m in mism)
    reissues = [e for e in full if e["type"] == "REISSUE"]
    return {"source": "TEMP_INLINE event-log check (AGP-ORACLE not merged)",
            "definition": "no signal event at or before t changes when bars after t are added",
            "expiry_rule": EXPIRY_RULE, "events": len(full),
            "events_by_type": dict(sorted(Counter(e["type"] for e in full).items())),
            "reissues": {"total": len(reissues), "fresh": sum(e["freshness"] == "FRESH" for e in reissues),
                         "expired": sum(e["freshness"] == "EXPIRED" for e in reissues)},
            "cuts_checked": len(cuts), "event_log_mismatches": len(mism),
            "mismatches_by_type": dict(sorted(by_type.items())), "mismatch_detail": mism[:50],
            "mismatches_by_day": dict(sorted(Counter(m["bar_close_utc"][:10] for m in mism).items())),
            "verdict": PASS if not mism else FAIL, "log": full}


# ------------------------------------------------------------------------------- L5 (OD1011)

# OD1011-COMMISSION (Aung, 2026-10-11; register row + config block in PR #149): commission = 0 is an owner-stated
# fact of the VT Markets demo Standard STP account, NOT a default. Mirrors the PR #149 `commission` block of
# config/v1_tickets/crypto_cfd_ticket_policy.yaml; read it from there once #149 merges. Applied only when the
# dataset provenance names that account's server / source; anything else stays INSUFFICIENT (never 0).
OD1011_COMMISSION = {"value": 0.0, "source": "OD1011-COMMISSION", "bound_server": "VTMarkets-Demo",
                     "bound_source": "MT5_VT_MARKETS_DEMO", "bound_account_type": "STANDARD_STP",
                     "asset_classes": ["CRYPTO_CFD"]}
COST_CODES = ("SPREAD_TOO_WIDE", "SPREAD_WARN", "COST_TOO_HIGH", "COST_WARN")


def commission_binding(provenance: dict) -> Optional[dict]:
    """OD1011-COMMISSION applies to data captured on the bound VT demo server; else None (INSUFFICIENT)."""
    server, source = provenance.get("server"), provenance.get("source")
    if server == OD1011_COMMISSION["bound_server"] or (server is None and source == OD1011_COMMISSION["bound_source"]):
        return OD1011_COMMISSION
    return None


def l5_od1011(spread: float, risk: Optional[float], ticket: dict, policy: dict, binding: Optional[dict]) -> dict:
    """OD1011-L5: PASS = spread + commission evidence exist from an accepted source and the cost gate applies
    them correctly (OD1009-D2 0.10R warn / 0.25R block; owner spread bands). A ticket blocked by cost is an
    actionability outcome, not a verification failure. Missing cost evidence stays INSUFFICIENT."""
    if binding is None:
        return {"status": INSUFFICIENT, "reason": "COMMISSION_EVIDENCE_MISSING"}
    if spread is None or not risk or risk <= 0:
        return {"status": INSUFFICIENT, "reason": "SPREAD_OR_STOP_DISTANCE_MISSING"}
    blocks, warns, _, _ = manual_ticket.crypto_cfd_cost_gate(risk, spread, binding["value"], policy)
    pct, cost = spread / risk * 100, spread / risk + binding["value"]      # independent re-derivation
    expected = ({"SPREAD_TOO_WIDE"} if pct > policy["spread_block_pct"] else
                {"SPREAD_WARN"} if pct > policy["spread_ok_pct"] else set())
    expected |= ({"COST_TOO_HIGH"} if cost >= policy["cost_block_R"] else
                 {"COST_WARN"} if cost >= policy["cost_warn_R"] else set())
    gate = set(blocks) | set(warns)
    on_ticket = {c for c in COST_CODES if c in ticket["reason_codes"] or c in ticket["warnings"]}
    return {"status": PASS if gate == expected == on_ticket else FAIL,
            "commission_R": binding["value"], "commission_source": binding["source"],
            "spread_R": round(spread / risk, 4), "cost_R": round(cost, 4),
            "thresholds": {k: policy[k] for k in ("spread_ok_pct", "spread_block_pct", "cost_warn_R", "cost_block_R")},
            "expected_codes": sorted(expected), "gate_codes": sorted(gate), "ticket_codes": sorted(on_ticket),
            "actionability": ("BLOCK" if expected & {"SPREAD_TOO_WIDE", "COST_TOO_HIGH"} else
                              "WARN" if expected else "OK")}


# ------------------------------------------------------------------------------- tickets

def spread_band(ticket: dict) -> str:
    """Read the band the ticket already carries (crypto_cfd_cost_gate); no recomputation."""
    if "SPREAD_TOO_WIDE" in ticket.get("reason_codes", []):
        return "BLOCK"
    if "SPREAD_WARN" in ticket.get("warnings", []):
        return "WARN"
    return "OK" if ticket.get("spread_pct_of_stop") is not None else "NOT_EVALUATED"


def envelope(stream: str, case_id: str, symbol: str, now: dt.datetime, ticket: dict, **extra) -> dict:
    return {"stream": stream, "case_id": case_id, "symbol": symbol, "now": now.isoformat(),
            "day_type": day_type(now.date()), "spread_band": spread_band(ticket), **extra,
            "content_hash": manual_ticket.content_hash(ticket), "ticket": ticket}


# ------------------------------------------------------------------------------- run

def run_symbol(symbol: str, data: dict, cases: List[dict], days: Sequence[dt.date], cfg, spec: dict,
               policy: dict, balance: Optional[float], commission_binding: Optional[dict] = None) -> dict:
    mism = Counter()
    dfail: Dict[str, Counter] = {}       # per UTC day: failed checks by gate (L1..L6)

    def bump(t: dt.datetime, gate: str, failed: bool = True) -> None:
        dfail.setdefault(t.date().isoformat(), Counter())[gate] += int(failed)
    tickets, cycle_l1 = [], []
    counts: Dict[str, int] = {}
    for case in cases:                                    # live-cycle tickets (manifest cases)
        now = dt.datetime.fromisoformat(case["now"])
        feed = ReplayFeed(data, now)
        build = lambda now=now: crypto_cfd.build_crypto_cfd_cycle(symbol, now, feed=ReplayFeed(data, now),
                                                                   balance=balance)
        ticket = crypto_cfd.build_crypto_cfd_cycle(symbol, now, feed=feed, balance=balance)
        counts = counts or dict(feed.requests)
        x = closed_inputs(data, now, dict(feed.requests)) if feed.requests else {"M5": []}
        cycle_l1.append(l1_determinism(build, x["M5"], now, bar=M5)["status"])
        bid, ask, quote_time = ReplayFeed(data, now).quote("")
        mism["manifest_parity"] += (ticket["cycle"] != case["window"] or quote_time.isoformat() != case["quote_time"]
                                    or round(ask - bid, 2) != case["spread"])
        tickets.append(envelope("CYCLE", case["id"], symbol, now, ticket))
    if not counts:
        raise SystemExit(f"{symbol}: no in-window case reached the feed; fetch counts unknown")

    _, windows = crypto_cfd._config()
    stream, future_stream, results, emissions, hits = [], [], Counter(), [], Counter()
    entry_at: Dict[dt.datetime, dict] = {}
    by_day: Dict[str, Counter] = {}
    l2_bad, l4_bad, l4_neg_bad, l2_neg_bad = [], [], [], []
    for day in days:
        day0 = dt.datetime.combine(day, dt.time(), tzinfo=UTC)
        emitted = False
        for k in range(288):
            now = day0 + k * M5
            x = closed_inputs(data, now, counts)
            r = engine(symbol, now, x, cfg)
            nondet = payload_hash(r) != payload_hash(engine(symbol, now, x, cfg))
            mism["determinism"] += nondet
            bump(now, "L1", nondet)
            future = {tf: x[tf] + data["bars"][tf][bisect.bisect_left(data["times"][tf], now):] for tf in STEP}
            fsem, sem = semantic(engine(symbol, now, future, cfg)), semantic(r)
            leaked = fsem != sem
            mism["truncation"] += leaked
            bump(now, "L3", leaked)
            stream.append((now, sem))
            future_stream.append((now, fsem))
            win = "IN_WINDOW" if crypto_cfd._window(now, windows) else "OUT_OF_WINDOW"
            events = rule_events(r, x, now)
            if k == 287 and r["result"] in ("WAITING_MSS", "WAITING_RETEST"):   # UTC-day rotation kills it
                events.add(("signal_expiry_contract.rule_2",
                            "LONG" if r["evidence"]["context"]["direction_permission"] == "LONG_ALLOWED" else "SHORT"))
            hits.update((rule, d, win) for rule, d in events)
            results[r["result"]] += 1
            by_day.setdefault(day.isoformat(), Counter())[r["result"]] += 1
            start, end = rules.previous_utc_day_window(now)
            exact = [c.time for c in x["M5"] if start <= c.time < end] == [start + i * M5 for i in range(288)]
            if exact == (r["result"] == "REFERENCE_INCOMPLETE"):
                l2_neg_bad.append(now.isoformat())
                bump(now, "L2")
            if r["result"] == "ENTRY_VALID":
                entry_at[now] = r
                side = r["evidence"]["target_plan"]["direction"]
                bad = reconstruct(r, x, now, spec)
                if bad:
                    l2_bad.append({"now": now.isoformat(), "direction": side, "failed": bad})
                    bump(now, "L2")
                if not geometry_ok(r["evidence"]["target_plan"]):
                    l4_bad.append({"now": now.isoformat(), "direction": side})
                    bump(now, "L4")
                if not emitted:
                    emitted = True
                    emissions.append((now, r, x))
            elif r["result"] == "NO_TRADE_TARGET_GEOMETRY" and not geometry_reject_ok(r["evidence"]["target_plan"]):
                l4_neg_bad.append({"now": now.isoformat(), "direction": r["evidence"]["target_plan"]["direction"]})
                bump(now, "L4")
    mism["l2_reconstruction"], mism["l4_geometry"] = len(l2_bad), len(l4_bad) + len(l4_neg_bad)
    mism["l2_reference_rule"] = len(l2_neg_bad)

    # ticket <-> scan parity: a cycle ticket's engine_result equals the scan result at the same instant
    scan_at = dict((now.isoformat(), sem) for now, sem in stream)
    for env in tickets:
        er = env["ticket"].get("engine_result")
        if er is not None and env["now"] in scan_at:
            mism["ticket_scan_parity"] += semantic(er) != scan_at[env["now"]]

    meta, commission = manual_ticket.symbol_meta_from_host(symbol), manual_ticket.crypto_cfd_commission(symbol)
    emission_rows, l3_seq_bad, l5, l5_adv, l6, quote_gaps = [], [], [], [], [], []
    for now, r, x in emissions:
        ev, plan = r["evidence"], r["evidence"]["target_plan"]
        sweep_at, mss_at, retest_at = (dt.datetime.fromisoformat(ev[k][f]) for k, f in
                                       (("sweep", "candle_time_utc"), ("mss", "confirmed_at_utc"),
                                        ("retest", "candle_time_utc")))
        before = engine(symbol, retest_at, closed_inputs(data, retest_at, counts), cfg)
        if not (sweep_at < mss_at < retest_at and retest_at + M5 <= now and before["result"] != "ENTRY_VALID"):
            l3_seq_bad.append(now.isoformat())
            bump(now, "L3")
        try:
            bid, ask, quote_time = ReplayFeed(data, now).quote("")
        except ValueError:                       # missing M5 quote bar: no ticket, no invented quote
            quote_gaps.append(now.isoformat())
            continue
        ticket = manual_ticket.build_crypto_cfd_manual_ticket(
            r, now=now, window=crypto_cfd._window(now, windows) or "OUTSIDE_WINDOW", spread=ask - bid,
            balance=balance, meta=meta, commission_r=commission, policy=policy, quote_time=quote_time)
        live = crypto_cfd.build_crypto_cfd_cycle(symbol, now, feed=ReplayFeed(data, now), balance=balance)
        tickets.append(envelope("EMISSION_RESEARCH", f"{symbol}_EMISSION_{now:%Y%m%dT%H%MZ}", symbol, now, ticket,
                                live_cycle_decision=live["decision"], live_cycle_reason_codes=live["reason_codes"],
                                local_time=local_time_diagnostics(now)))
        l5_adv.append(l5_cost(ask - bid, plan["risk_distance"], commission_r=commission, warn_r=policy["cost_warn_R"]))
        l5.append(l5_od1011(ask - bid, plan["risk_distance"], ticket, policy, commission_binding))
        expected_until = (retest_at + SIGNAL_TTL).isoformat()
        gate6 = l6_freshness(ticket["valid_until"], {"rule": "SIGNAL_STALE once now > retest close + 15 min",
                                                     "or_after": ticket["valid_until"]},
                             {"sl_touched_before_fill": plan["stop_loss"]})
        l6.append(PASS if gate6["status"] == PASS and ticket["valid_until"] == expected_until
                  and now < retest_at + SIGNAL_TTL else FAIL)
        bump(now, "L6", l6[-1] == FAIL)
        emission_rows.append({"now": now.isoformat(), "day_type": day_type(now.date()),
                              "direction": plan["direction"], "entry": plan["entry"], "stop_loss": plan["stop_loss"],
                              "tp1": plan["tp1"], "tp2": plan["tp2"], "risk_distance": plan["risk_distance"],
                              "tp2_r_multiple": plan["tp2_r_multiple"], "sweep_at": sweep_at.isoformat(),
                              "mss_at": mss_at.isoformat(), "retest_at": retest_at.isoformat(),
                              "spread": round(ask - bid, 2), "spread_pct_of_stop": ticket["spread_pct_of_stop"],
                              "spread_band": spread_band(ticket), "ticket_decision": ticket["decision"],
                              "ticket_reason_codes": ticket["reason_codes"], "ticket_warnings": ticket["warnings"],
                              "live_cycle_decision": live["decision"], "live_cycle_reason_codes": live["reason_codes"],
                              "l5": l5[-1]["status"], "cost_actionability": l5[-1].get("actionability")})

    # L3 (owner ruling 2026-10-11): append-only signal event log, prefix-invariant
    events = event_log_invariance(stream, future_stream)
    mism["event_log"], mism["l3_sequence"] = events["event_log_mismatches"], len(l3_seq_bad)
    for d, n in events["mismatches_by_day"].items():
        dfail.setdefault(d, Counter())["L3"] += n
    # REISSUE: a re-issue whose retest is older than the expiry window must be EXPIRED and never actionable
    reissue_rows = []
    for e in (e for e in events["log"] if e["type"] == "REISSUE"):
        now = dt.datetime.fromisoformat(e["bar_close_utc"])
        try:
            bid, ask, quote_time = ReplayFeed(data, now).quote("")
        except ValueError:
            quote_gaps.append(now.isoformat())
            continue
        ticket = manual_ticket.build_crypto_cfd_manual_ticket(
            entry_at[now], now=now, window=crypto_cfd._window(now, windows) or "OUTSIDE_WINDOW", spread=ask - bid,
            balance=balance, meta=meta, commission_r=commission, policy=policy, quote_time=quote_time)
        tickets.append(envelope("REISSUE_RESEARCH", f"{symbol}_REISSUE_{now:%Y%m%dT%H%MZ}", symbol, now, ticket,
                                signal_event=e))
        stale = "SIGNAL_STALE" in ticket["reason_codes"]
        actionable = ticket["decision"] == "READY" or bool(ticket["owner_accept_allowed"])
        expired = e["freshness"] == "EXPIRED"
        ok = expired == stale == (now >= dt.datetime.fromisoformat(ticket["valid_until"])) and not (expired and actionable)
        mism["reissue_expiry"] += not ok
        bump(now, "L6", not ok)
        reissue_rows.append({"now": now.isoformat(), "direction": e["direction"],
                             "retest_at": e["retest_candle_time_utc"], "freshness": e["freshness"],
                             "valid_until": ticket["valid_until"], "expiry_rule_fired": stale,
                             "ticket_decision": ticket["decision"], "actionable": actionable,
                             "ticket_reason_codes": ticket["reason_codes"], "check": PASS if ok else FAIL})
    mism["ticket_determinism"] = sum(s != PASS for s in cycle_l1)

    identity = logic_identity(CONTRACT_ID, CONTRACT_VERSION)
    spec_ok = (spec["strategy_id"] == CONTRACT_ID and str(spec["version"]) == CONTRACT_VERSION
               and spec["targets_contract"]["tp1_volume_pct"] == TP1_VOLUME_PCT
               and spec["targets_contract"]["min_tp2_r_multiple"] == MIN_TP2_R_MULTIPLE
               and str(spec["m5_trigger_contract"]["retest"]["max_bars_after_mss"]).startswith(f"{ENTRY_TTL_M5_BARS} ")
               and spec["stop_loss_contract"]["stop_buffer"].startswith("0.00") and STOP_BUFFER_PRICE == 0
               and spec["context_contract"]["structure_params"] == {"swing_length": cfg.swing_length,
                                                                     "close_break": cfg.close_break})
    entries = results["ENTRY_VALID"]

    def v(failed: bool, positive: bool) -> str:
        return FAIL if failed else (PASS if positive else INSUFFICIENT)

    def l5_of(rows: List[dict]) -> str:
        st = [g["status"] for g in rows]
        return FAIL if FAIL in st else INSUFFICIENT if not st or INSUFFICIENT in st else PASS
    gates = {
        "L1": v(identity is None or mism["determinism"] or mism["ticket_determinism"], True),
        "L2": v(not spec_ok or mism["l2_reconstruction"] or mism["l2_reference_rule"], entries > 0),
        "L3": v(mism["truncation"] or mism["event_log"] or mism["l3_sequence"], bool(emissions)),
        "L4": v(bool(mism["l4_geometry"]), entries > 0),
        "L5": l5_of(l5),                       # OD1011-L5 (commission per OD1011-COMMISSION); band NOT consulted
        "L6": v(FAIL in l6 or bool(mism["reissue_expiry"]), bool(l6)),
    }

    def branch(side: str) -> dict:           # OD1011-SCOPE: per symbol x entry branch (LONG / SHORT)
        n = sum(1 for r in entry_at.values() if r["evidence"]["target_plan"]["direction"] == side)
        em = [k for k, row in enumerate(emission_rows) if row["direction"] == side]
        mine = lambda rows: any(b.get("direction") == side for b in rows)   # noqa: E731
        return {"entry_valid_scans": n, "emissions": len(em), "gates": {
            "L1": gates["L1"],
            "L2": v(not spec_ok or mine(l2_bad) or bool(l2_neg_bad), n > 0),
            "L3": v(mism["truncation"] or mism["event_log"] or mism["l3_sequence"], bool(em)),
            "L4": v(mine(l4_bad) or mine(l4_neg_bad), n > 0),
            "L5": l5_of([l5[k] for k in em]),
            "L6": v(any(l6[k] == FAIL for k in em)
                    or any(x["check"] == FAIL and x["direction"] == side for x in reissue_rows), bool(em))}}
    emitted_days = {e["now"][:10]: e for e in emission_rows}
    l5_by_day = {e["now"][:10]: g["status"] for e, g in zip(emission_rows, l5)}
    per_day = {}
    for d, c in by_day.items():
        f, pos = dfail.get(d, Counter()), c["ENTRY_VALID"] > 0
        gd = {"L1": v(f["L1"] > 0, True), "L2": v(f["L2"] > 0, pos), "L3": v(f["L3"] > 0, True),
              "L4": v(f["L4"] > 0, pos), "L5": l5_by_day.get(d, INSUFFICIENT), "L6": v(f["L6"] > 0, d in emitted_days),
              "event_log_mismatches": events["mismatches_by_day"].get(d, 0)}
        only_events = (f["L3"] == events["mismatches_by_day"].get(d, 0) > 0
                       and [k for k in ("L1", "L2", "L3", "L4", "L6") if gd[k] == FAIL] == ["L3"])
        gd["failure_class"] = (None if FAIL not in (gd[k] for k in ("L1", "L2", "L3", "L4", "L5", "L6")) else
                               "LOGIC_DEFECT:EVENT_LOG_MISMATCH" if only_events else "UNCLASSIFIED_FAILURE")
        per_day[d] = {"day_type": day_type(dt.date.fromisoformat(d)), "results": dict(sorted(c.items())), **gd}
    return {
        "symbol": symbol, "fetch_counts": counts, "per_day": per_day, "days": len(days), "scans": len(stream),
        "scan_results": dict(sorted(results.items())), "scan_results_by_day": {d: dict(sorted(c.items()))
                                                                               for d, c in by_day.items()},
        "entry_valid_scans": entries, "emissions": emission_rows, "emission_quote_gaps": quote_gaps, "gates": gates,
        "branches": {side: branch(side) for side in ("LONG", "SHORT")},
        "reissues": reissue_rows,
        "gate_evidence": {"logic_identity": identity, "spec_constants_match": spec_ok,
                          "l2_failures": l2_bad[:20], "l2_reference_rule_failures": l2_neg_bad[:20],
                          "l4_failures": l4_bad[:20], "l4_reject_failures": l4_neg_bad[:20],
                          "l3_sequence_failures": l3_seq_bad,
                          "l5_od1011": l5, "l5_advisory_cost_gates": l5_adv, "l6": l6,
                          "cycle_ticket_l1": dict(Counter(cycle_l1))},
        "signal_events": events, "mismatches": dict(sorted(mism.items())),
        "rule_coverage": coverage_matrix(hits),
        "tickets": tickets,
    }


def mismatch_free(r: dict) -> bool:
    return (not any(r["mismatches"].values()) and r["signal_events"]["verdict"] == PASS
            and not any(d["failure_class"] for d in r["per_day"].values()))


def all_checks_pass(r: dict) -> bool:
    """AGP-LANE-B3 (OD1011-L5): L1-L4 and L6 PASS, L5 PASS (cost evidence incl. OD1011-COMMISSION applied
    correctly; a cost-blocked ticket is not a failure), zero mismatches incl. 0 event-log mismatches, and no
    recorded day with a FAIL. INSUFFICIENT on a no-signal day is not a failure."""
    g = r["gates"]
    return all(g[k] == PASS for k in ("L1", "L2", "L3", "L4", "L5", "L6")) and mismatch_free(r)


def build(date: str, symbols: Sequence[str] = INSTRUMENTS, days: Optional[Sequence[dt.date]] = None,
          balance: Optional[float] = None, dataset: str = "recorded") -> dict:
    base = DATASETS[dataset][0]
    manifest_path = base / "manifest.json"
    manifest = verify(manifest_path)         # every listed sha256, else SystemExit before any replay
    registry_before = REGISTRY.read_bytes()
    spec = yaml.safe_load((ROOT / CONTRACT_YAML).read_text(encoding="utf-8"))
    cfg, policy = load_market_structure_config(), load_ticket_policy()
    out: Dict[str, Any] = {}
    for symbol in symbols:
        data = load_symbol(symbol, base)
        all_days = sorted({c.time.date() for c in data["bars"]["M5"]})
        run_days = [d for d in all_days if days is None or d in days]
        cases = [c for c in manifest["cases"] if c["symbol"] == symbol
                 and (days is None or dt.datetime.fromisoformat(c["now"]).date() in days)]
        provenance = json.loads((base / f"{symbol}_provenance.json").read_text(encoding="utf-8"))
        out[symbol] = run_symbol(symbol, data, cases, run_days, cfg, spec, policy, balance,
                                 commission_binding(provenance))
    registry = yaml.safe_load(registry_before)["strategies"][CONTRACT_ID]
    tickets = [t for s in out.values() for t in s.pop("tickets")]
    identity = logic_identity(CONTRACT_ID, CONTRACT_VERSION)
    summary = Counter((t["stream"], t["symbol"], t["day_type"], t["ticket"]["decision"], t["spread_band"])
                      for t in tickets)
    first = out[symbols[0]]
    cov_path = COVERAGE_ONLY
    cov_only = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.exists() else None
    vt_cov = {sym: r.pop("rule_coverage") for sym, r in out.items()}
    vt_gaps = {sym: coverage_gaps(m) for sym, m in vt_cov.items()}
    proven = {sym: proof_matrix(m, cov_only) for sym, m in vt_cov.items()}
    verification = {sym: {"all_checks_pass": all_checks_pass(r), "logic_identity": identity,
                          "branches": {b: branch_verdict(r, proven[sym], b) for b in BRANCHES}}
                    for sym, r in out.items()}
    rule_coverage = {
        "rule_ids_source": CONTRACT_YAML, "dimensions": "rule_id x LONG/SHORT x IN_WINDOW/OUT_OF_WINDOW",
        "window_definition": "IN_WINDOW = scan instant inside a v1_tickets crypto window (crypto_cfd._window: "
                             "WEEKDAY 09:00-12:00 America/New_York Mon-Fri, WEEKEND 21:00-23:00 UTC Sat/Sun)",
        "vt": vt_cov, "vt_not_exercised": vt_gaps,
        # COVERAGE_ONLY is consulted only for the cells VT left NOT_EXERCISED; it never overrides a VT cell.
        "coverage_only_binance": None if cov_only is None else {
            "label": cov_only["label"], "authoritative": False, "artifact": str(cov_path.relative_to(ROOT)),
            "sha256": hashlib.sha256(cov_path.read_bytes()).hexdigest(),
            "vt_gap_cells": {sym: {cell: ("NOT_EXERCISED" if cell in cov_only["not_exercised"] else "EXERCISED")
                                   for cell in gaps} for sym, gaps in vt_gaps.items()}},
        "not_exercised_anywhere": {sym: sorted(set(gaps) & set(cov_only["not_exercised"]))
                                   for sym, gaps in vt_gaps.items()} if cov_only else None,
        "synthetic_proofs": {rule: f"{SYNTHETIC_TESTS}::{t}" for rule, t in SYNTHETIC_PROOFS.items()},
        # status per cell: EXERCISED (VT) > SYNTHETIC_PROVEN (rejection-only rule) > COVERAGE_ONLY_EXERCISED
        # (Binance, non-authoritative, never counts) > NOT_EXERCISED
        "proof": proven,
        "open_gaps": {sym: [f"{rule}|{cell}" for rule, row in m.items() for cell, st in row.items()
                            if st in ("NOT_EXERCISED", "COVERAGE_ONLY_EXERCISED")] for sym, m in proven.items()},
    }
    return {
        "schema": "AG_CCFD_V100_REPLAY_V1", "mission": "AGP-LANE-B3", "date": date,
        "owner_rulings": {"L3": "2026-10-11 option A: permission re-checked every scan (rules 1.0.0 frozen); L3 = "
                                "append-only signal event-log prefix invariance",
                          "L5": "OD1011-L5 with OD1011-COMMISSION (PR #149)", "scope": "OD1011-SCOPE per symbol x branch",
                          "guard": "open-bar guard stays a wrapper (crypto_cfd_contract.guard)"},
        "policy_conformance_changes": 1,
        "policy_conformance_note": "crypto spread band boundary: exactly 10% of stop is OK (owner bands 2026-10-09)",
        "engine_entry_point": "crypto_cfd_contract.evaluate (guard.evaluate: open-bar guard over frozen rules.evaluate)",
        "rule_coverage": rule_coverage,
        "strategy": f"{CONTRACT_ID}@{CONTRACT_VERSION}", "contract_path": CONTRACT_YAML,
        "contract_sha256": hashlib.sha256((ROOT / CONTRACT_YAML).read_bytes()).hexdigest(),
        "dataset": {"id": dataset, "manifest": str(manifest_path.relative_to(ROOT)),
                    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                    "file_hashes_verified": True, "source": manifest["source"], "gaps": manifest["gaps"]},
        "days_run": sorted(first["scan_results_by_day"]),
        "weekend_days": [d for d in first["scan_results_by_day"] if day_type(dt.date.fromisoformat(d)) == "WEEKEND"],
        "spread_policy": {k: policy[k] for k in ("spread_ok_pct", "spread_block_pct", "cost_warn_R", "cost_block_R")},
        "spread_band_scope": "ticket state only; no L1-L6 check reads the band",
        "l3_source": "TEMP_INLINE event-log check (AGP-ORACLE not merged)",
        "balance": balance, "symbols": out, "logic_verification": verification,
        "ticket_summary": [dict(zip(("stream", "symbol", "day_type", "decision", "spread_band"), k), count=n)
                           for k, n in sorted(summary.items())],
        "tickets_total": len(tickets),
        "registry": {"active": registry["active"], "research": registry["research"],
                     "modified": REGISTRY.read_bytes() != registry_before},
        "edge_verified": False, "logic_verified_claim": False, "demo_authorized": False, "live_authorized": False,
        "ORDER_API_CALLS": 0, "BROKER_MUTATION_COUNT": 0, "_tickets": tickets,
    }


def write(report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tickets = report.pop("_tickets")
    with (out_dir / "tickets.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for t in tickets:
            f.write(json.dumps(t, sort_keys=True, default=str) + "\n")
    events = {s: r["signal_events"] for s, r in report["symbols"].items()}
    (out_dir / "signal_events.json").write_text(json.dumps(events, indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8", newline="\n")
    stale = out_dir / "prefix_invariance.json"          # superseded by signal_events.json (AGP-LANE-B3)
    if stale.exists():
        stale.unlink()
    (out_dir / "replay_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                                                encoding="utf-8", newline="\n")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--date", required=True)
    p.add_argument("--dataset", choices=sorted(DATASETS), default="recorded")
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--balance", type=float, default=None)
    p.add_argument("--symbols", nargs="+", default=list(INSTRUMENTS), choices=list(INSTRUMENTS))
    args = p.parse_args(argv)
    report = build(args.date, symbols=tuple(args.symbols), balance=args.balance, dataset=args.dataset)
    write(report, args.out_dir or DATASETS[args.dataset][1])
    for s, r in report["symbols"].items():
        print(s, r["days"], "days", r["scans"], "scans", r["gates"], "mismatches", sum(r["mismatches"].values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
