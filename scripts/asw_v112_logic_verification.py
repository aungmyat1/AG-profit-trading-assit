"""Emit LOGIC_VERIFICATION_REPORT for the candidate ST_ASIAN_SWEEP_5R_V1@1.1.2 (AGP-C3-ASW-RATIFY v2).

Read-only, hermetic: recorded EURUSD M15 fixture plus seeded synthetic sessions; no broker, no
network, no MT5. The candidate contract is replayed offline (build_fx_ticket(strategy_path=...));
the runtime keeps loading v1.1.1. Report L-numbering follows LOGIC_VERIFICATION_REPORT.json:
L1 identity, L2 contract/engine equivalence (L2 closure reused as-is), L3 temporal causality,
L4 price geometry, L5 risk and friction, L6 per src/v1_tickets/logic_gate.py (freshness fields).
Per-case ticket-gate results (logic_gate.py L1-L6) are recorded beside it.

    python scripts/asw_v112_logic_verification.py [--out-dir DIR] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import functools
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
os.environ.setdefault("AG_EVIDENCE_ROOT", str(ROOT / ".no_evidence"))

# Import-only Linux MetaTrader5 portability shim (raises on any real MT5 call).
if "MetaTrader5" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("asw_gate_test_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))


from host_evidence import symbol_metadata  # noqa: E402
from strategy_engine import load_strategy  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import fx  # noqa: E402
from v1_tickets.authority import _sha256_text, load_registry, logic_identity  # noqa: E402
from v1_tickets.code_identity import code_sha  # noqa: E402
from v1_tickets.logic_gate import (  # noqa: E402
    EVIDENCED_PIP, FAIL, NOT_EVALUABLE, PASS, WARN, blocking_failures, l1_determinism, l2_rule_conformance,
    l3_geometry, l4_data_session, l5_cost, l6_freshness,
)

UTC = dt.timezone.utc
M15 = dt.timedelta(minutes=15)
STRATEGY_ID, VERSION = "ST_ASIAN_SWEEP_5R_V1", "1.1.2"
CANDIDATE = "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
FROZEN = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
FROZEN_CONTRACT_HASH = "a1f331a23dd4494422aa9edde0f4a62985486f173561ca93e8c234d41730f550"  # LOGIC_VERIFICATION_REPORT.json
OWNER_CONFIG = "config/owner_ticket.yaml"       # single D2 carrier (OD1009-D2), read via manual_ticket.load_owner_config
# Verified instrument / branch coverage of this report (scoped truthfully; nothing is inferred).
COVERAGE = {
    "instruments": {
        "EURUSD": "VERIFIED_RECORDED_FIXTURE",
        "GBPUSD": "RECORDED_FIXTURE (status computed per run from its own gate results)",
        "USDJPY": "PENDING_AGP-C2-SYMMAP",
        "XAUUSD": "PENDING_AGP-C2-SYMMAP",
    },
    "branches": {"SWEEP": "VERIFIED_RECORDED_FIXTURE", "TREND": "VERIFIED_RECORDED_FIXTURE (fails closed)",
                 "RANGE_REJECTION": "UNIT_ONLY (no recorded day yields Entry 3)"},
}
# Data-driven symbol table. EURUSD runs first on the shared seed (byte-identical to the #108 report);
# every further symbol draws from its own seeded stream so adding one never perturbs another.
SYMBOLS = {
    "EURUSD": {"fixture": "tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv", "provenance": None,
               "l4_failures": "tests/fixtures/asian_sweep_v1_1_2/l4_recorded_failures.json", "seed": None},
    "GBPUSD": {"fixture": "tests/fixtures/manual_ticket/GBPUSD_M15_recorded.csv",
               "provenance": "tests/fixtures/manual_ticket/GBPUSD_M15_recorded.PROVENANCE.md",
               "l4_failures": None, "seed": "112:GBPUSD"},
}
# AGP-C3-ASW-R2 fixture routing only; select R2_SYMBOLS explicitly for replay.
R2_SYMBOLS = {
    "EURUSD": {"fixture": "tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv", "provenance": None,
               "l4_failures": "tests/fixtures/asian_sweep_v1_1_2/l4_recorded_failures.json", "seed": None},
    "GBPUSD": {"fixture": "tests/fixtures/manual_ticket/GBPUSD_M15_recorded_20d.csv",
               "provenance": "tests/fixtures/manual_ticket/GBPUSD_M15_recorded_20d.PROVENANCE.md",
               "l4_failures": None, "seed": "112:GBPUSD"},
    "USDJPY": {"fixture": "tests/fixtures/manual_ticket/USDJPY_M15_recorded.csv",
               "provenance": "tests/fixtures/manual_ticket/USDJPY_M15_recorded.PROVENANCE.md",
               "l4_failures": None, "seed": "112:USDJPY"},
    "XAUUSD": {"fixture": "tests/fixtures/manual_ticket/XAUUSD_M15_recorded.csv",
               "provenance": "tests/fixtures/manual_ticket/XAUUSD_M15_recorded.PROVENANCE.md",
               "l4_failures": None, "seed": "112:XAUUSD"},
}
# CCW-P1-REPLAY-01 fixture routing: the AGP-DATA-R3 60-weekday recorded files (verification basis).
# The 5-day EURUSD, 10-day and 20-day fixtures stay as historical evidence only. EURUSD has no
# historical L4 recorded-failure list here: those dates (June-July) are not in the 60-day window.
D60_SYMBOLS = {
    sym: {"fixture": f"tests/fixtures/manual_ticket/{sym}_M15_recorded_spread_60d.csv",
          "provenance": f"tests/fixtures/manual_ticket/{sym}_M15_recorded_spread_60d.PROVENANCE.md",
          "l4_failures": None, "seed": None if sym == "EURUSD" else f"112:{sym}"}
    for sym in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
}
FIXTURE = SYMBOLS["EURUSD"]["fixture"]
L4_FAILURES = SYMBOLS["EURUSD"]["l4_failures"]
DAY_TYPES = ("long-sweep", "short-sweep", "TREND", "no-setup")
NOT_EVIDENCED = "NOT_EVIDENCED"    # no recorded case exercises the rule; never reported as PASS
CYCLES = {"ASIAN_LONDON": ("Asian", 24), "LONDON_NEWYORK": ("London", 20)}
TEST_SPREAD = 0.00002          # L2-closure test input (0.2 pip), not recorded data
SEMANTIC = ("decision", "reason_code", "regime", "setup", "signal_id", "box", "signal_timestamp", "direction",
            "entry", "stop_loss", "risk_distance", "targets")
SEED, MUTATIONS_PER_CASE, SYNTHETIC_SESSIONS = 112, 25, 400
SYMBOLS["EURUSD"]["seed"] = SEED
DECLARED_FAIL_CLOSED = {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss", "R.target_leg2",
                        "R.max_spread", "R.max_spread_fraction", "R.target_order"}


def sha256_file(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def verify_provenance(symbol: str) -> Optional[Dict[str, Any]]:
    """Fail closed: a fixture with a provenance note is used only if its byte sha256 equals the note's
    `- sha256:` line (the note hashes the git blob; the file is `-text`, so disk bytes are the blob)."""
    note_path = SYMBOLS[symbol]["provenance"]
    if note_path is None:
        return None
    m = re.search(r"^- sha256: `([0-9a-f]{64})`", (ROOT / note_path).read_text(encoding="utf-8"), re.M)
    want = m.group(1) if m else None
    got = hashlib.sha256((ROOT / SYMBOLS[symbol]["fixture"]).read_bytes()).hexdigest()
    if want != got:
        raise RuntimeError(f"PROVENANCE_MISMATCH: {symbol} fixture sha256 {got} != note {want}")
    return {"note": note_path, "fixture_sha256": got}


def load_candles(symbol: str) -> List[Candle]:
    with (ROOT / SYMBOLS[symbol]["fixture"]).open() as fh:
        return [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC), float(r["open"]),
                       float(r["high"]), float(r["low"]), float(r["close"])) for r in csv.DictReader(fh)]


def fixture_days(candles: List[Candle]) -> List[str]:
    return sorted({c.time.date().isoformat() for c in candles})


@functools.lru_cache(maxsize=None)
def _spread_points(fixture: str) -> Dict[dt.datetime, int]:
    """Per-bar MqlRates spread (integer points) from a --with-spread fixture; {} when the column is absent."""
    with (ROOT / fixture).open() as fh:
        rows = csv.DictReader(fh)
        if "spread_points" not in (rows.fieldnames or []):
            return {}
        return {dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC): int(r["spread_points"])
                for r in rows}


def recorded_spread(symbol: str, t: Dict[str, Any]) -> Dict[str, Any]:
    """Conservative L5 spread at the signal bar: max(recorded bar spread, host-evidence spread), in points x the
    host_captured point. MqlRates spread is a per-bar lower bound, so a bar-only value is never used (-> None).
    Host evidence = the host_captured symbol_info snapshot spread (no tick-derived source exists for this path)."""
    record = symbol_metadata.load_record(symbol, root=str(ROOT))     # sha256-verified committed evidence
    fields = (record or {}).get("fields") or {}
    point, host = fields.get("point"), fields.get("spread")
    ts = t.get("signal_timestamp")
    bar = _spread_points(SYMBOLS[symbol]["fixture"]).get(dt.datetime.fromisoformat(ts)) if ts else None
    if bar is None or host is None or not point:
        pts, source = None, ("BAR_ONLY_LOWER_BOUND" if bar is not None else "NOT_AVAILABLE")
    else:
        pts, source = max(bar, host), ("HOST_SNAPSHOT" if host >= bar else "RECORDED_BAR")
    price = pts * point if pts is not None else None
    risk = t.get("risk_distance")
    return {"bar_spread_points": bar, "host_spread_points": host, "spread_points": pts, "point": point,
            "spread_price": price, "spread_R": round(price / risk, 4) if price is not None and risk else None,
            "source": source}


def split(candles: List[Candle], cycle: str, day: dt.date):
    w = fx.session_windows_utc(day)[cycle]
    now = w["trade"][1]
    session = [c for c in candles if w["ref"][0] <= c.time < w["ref"][1]]
    post = [c for c in candles if w["trade"][0] <= c.time < w["trade"][1] and c.time + M15 <= now]
    return w, now, session, post


def ticket(cycle: str, day: dt.date, session, post, now, spread: Optional[float] = TEST_SPREAD, *,
           symbol: str) -> Dict[str, Any]:
    return fx.build_fx_ticket(symbol, cycle, day, session, CYCLES[cycle][1], post, data_source="FIXTURE",
                              evaluated_at=now, data_close=now, spread=spread, strategy_path=CANDIDATE)


def day_type(t: Dict[str, Any]) -> str:
    """Harness classification only (engine ticket fields); no new market logic."""
    if t.get("setup") == "SWEEP" and t.get("direction") in ("LONG", "SHORT"):
        return "long-sweep" if t["direction"] == "LONG" else "short-sweep"
    if t.get("setup") == "TREND":
        return "TREND"
    if t.get("setup") == "RANGE":
        return "range-rejection"
    if t.get("direction") is None and t.get("decision") == "NO_TRADE":
        return "no-setup"
    return "insufficient-data"


def semantic(t: Dict[str, Any]) -> Dict[str, Any]:
    return {k: t.get(k) for k in SEMANTIC}


def geometry_ok(t: Dict[str, Any]) -> Dict[str, bool]:
    if t.get("direction") is None:
        return {"has_levels": False, "positive_stop": True, "target_order": True}
    long = t["direction"] == "LONG"
    entry, risk = t["entry"], t["risk_distance"]
    tp = {x["leg"]: x["price"] for x in t["targets"]}
    order = (entry < tp[1] <= tp[2]) if long else (entry > tp[1] >= tp[2])
    return {"has_levels": True, "positive_stop": risk is not None and risk > 0 and t["stop_loss"] != entry,
            "target_order": bool(order)}


def ticket_gates(strategy, cycle, day, session, post, now, w, t, spread, warn_r,
                 symbol: str, l5_spread: Optional[float] = None) -> Optional[Dict[str, Any]]:
    if t.get("direction") is None:
        return None
    ref_name, bars = CYCLES[cycle]
    return {
        "L1": l1_determinism(lambda: ticket(cycle, day, session, post, now, spread, symbol=symbol), session + post, now),
        "L2": l2_rule_conformance(strategy, t, session, bars, post, digits=5, spread=spread),
        "L3": l3_geometry(t, post, digits=5, declared_rr=5.0),
        "L4": l4_data_session(t, ref_window=w["ref"], trade_window=w["trade"], reference_name=ref_name,
                              session=session, expected_bar_count=bars, post=post, data_close=now, now=now),
        "L5": l5_cost(l5_spread, t.get("risk_distance"), commission_r=None, warn_r=warn_r),
        "L6": l6_freshness(t.get("valid_until") or "set", {"x": 1}, {"y": 1}),
    }


def manual_l6(cycle, day, session, post, now, symbol: str) -> Optional[Dict[str, Any]]:
    """L6 exactly as the owner ticket computes it (logic_gate.l6_freshness), candidate replayed test-locally."""
    from v1_tickets.manual_ticket import build_manual_ticket, load_owner_config
    saved = fx.STRATEGY_PATH, fx.build_fx_ticket
    fx.STRATEGY_PATH, fx.build_fx_ticket = CANDIDATE, functools.partial(saved[1], strategy_path=CANDIDATE)
    try:
        t = build_manual_ticket(symbol, cycle, day, session, CYCLES[cycle][1], post, now=now, data_close=now,
                                spread=TEST_SPREAD, owner=load_owner_config(ROOT),
                                data_source="FIXTURE")
    finally:
        fx.STRATEGY_PATH, fx.build_fx_ticket = saved
    return {"state": t["state"], "primary_block_reason": t.get("primary_block_reason"),
            "edge_verified": t["invariants"]["edge_verified"],
            "L6": (t.get("logic_gate") or {}).get("L6")}


# ------------------------------------------------------------------------------- L3 causality

def causality(cycle: str, day: dt.date, session, post, now, rng: random.Random,
              symbol: str) -> Dict[str, Any]:
    full = semantic(ticket(cycle, day, session, post, now, symbol=symbol))
    stream = [semantic(ticket(cycle, day, session, post[:k], now, symbol=symbol)) for k in range(len(post) + 1)]
    first = next((k for k, s in enumerate(stream) if s["direction"] is not None), None)
    # Prefix: once emitted, every longer prefix carries the identical decision; before it, none.
    prefix_mismatch = sum(1 for k, s in enumerate(stream) if first is not None and k >= first and s != full)
    pre_emission = sum(1 for k, s in enumerate(stream) if (first is None or k < first) and s["direction"] is not None)
    # Streaming: bar-by-bar final state equals the batch decision (canonical hash).
    stream_parity = canon(stream[-1]) == canon(full)
    # Future mutation: bars after the emission cut are replaced; the decision must not change.
    mutated, mismatch = 0, 0
    if first is not None and first < len(post):
        for _ in range(MUTATIONS_PER_CASE):
            fut = []
            for c in post[first:]:
                o, cl = (c.close + rng.uniform(-0.005, 0.005) for _ in range(2))
                fut.append(Candle(c.time, round(o, 5), round(max(o, cl) + rng.uniform(0, 0.003), 5),
                                  round(min(o, cl) - rng.uniform(0, 0.003), 5), round(cl, 5)))
            mutated += 1
            mismatch += semantic(ticket(cycle, day, session, post[:first] + fut, now, symbol=symbol)) != full
    return {"bars": len(post), "first_emission_prefix_len": first, "prefix_mismatches": prefix_mismatch,
            "pre_emission_signals": pre_emission, "streaming_hash_parity": stream_parity,
            "future_mutations": mutated, "future_mutation_mismatches": mismatch,
            "_first_setup": stream[first]["setup"] if first is not None else None}


# ------------------------------------------------------------------------------- L4 synthetic geometry

def synthetic_session(rng: random.Random, cycle: str, day: dt.date):
    w = fx.session_windows_utc(day)[cycle]
    bars, t, px = [], w["ref"][0], 1.10 + rng.uniform(-0.01, 0.01)
    while t < w["trade"][1]:
        o = px
        c = o + rng.gauss(0, 0.0006)
        hi, lo = max(o, c) + abs(rng.gauss(0, 0.0004)), min(o, c) - abs(rng.gauss(0, 0.0004))
        if rng.random() < 0.15:                      # degenerate bars exercise zero-stop/ordering edges
            hi, lo = max(o, c), min(o, c)
        bars.append(Candle(t, round(o, 5), round(hi, 5), round(lo, 5), round(c, 5)))
        px, t = c, t + M15
    return w, w["trade"][1], [b for b in bars if b.time < w["ref"][1]], [b for b in bars if b.time >= w["trade"][0]]


def l4_geometry(strategy, rng: random.Random) -> Dict[str, Any]:
    out = {"sessions": 0, "tickets_with_levels": 0, "raw_zero_stop": 0, "raw_tp_inversion": {"LONG": 0, "SHORT": 0},
           "admitted_by_gates": 0, "admitted_zero_stop": 0, "admitted_tp_inversion": 0,
           "undeclared_l2_failures": 0}
    day = dt.date(2026, 6, 15)
    for i in range(SYNTHETIC_SESSIONS):
        cycle = ("ASIAN_LONDON", "LONDON_NEWYORK")[i % 2]
        w, now, session, post = synthetic_session(rng, cycle, day)
        t = ticket(cycle, day, session, post, now, spread=0.0, symbol="EURUSD")   # synthetic, EURUSD-scaled
        out["sessions"] += 1
        g = geometry_ok(t)
        if not g["has_levels"]:
            continue
        out["tickets_with_levels"] += 1
        out["raw_zero_stop"] += not g["positive_stop"]
        if not g["target_order"]:
            out["raw_tp_inversion"][t["direction"]] += 1
        l2 = l2_rule_conformance(strategy, t, session, CYCLES[cycle][1], post, digits=5, spread=0.0)
        l3 = l3_geometry(t, post, digits=5, declared_rr=5.0)
        bad = {c["id"] for c in l2["checks"] if c["verdict"] in (FAIL, NOT_EVALUABLE)}
        out["undeclared_l2_failures"] += bool(bad - DECLARED_FAIL_CLOSED - {"R.max_spread"})
        if not bad and l3["status"] == PASS:
            out["admitted_by_gates"] += 1
            out["admitted_zero_stop"] += not g["positive_stop"]
            out["admitted_tp_inversion"] += not g["target_order"]
    return out


# ------------------------------------------------------------------------------- report

def _run_symbol(symbol: str, strategy, owner, rng: random.Random) -> List[Dict[str, Any]]:
    candles = load_candles(symbol)
    by_day: Dict[str, List[Candle]] = {}
    for c in candles:
        by_day.setdefault(c.time.date().isoformat(), []).append(c)
    cases = []
    for cycle in CYCLES:
        for ds in fixture_days(candles):
            day = dt.date.fromisoformat(ds)
            w, now, session, post = split(by_day[ds], cycle, day)
            t = ticket(cycle, day, session, post, now, symbol=symbol)
            l5 = recorded_spread(symbol, t) if t.get("direction") is not None else None
            gates = ticket_gates(strategy, cycle, day, session, post, now, w, t, TEST_SPREAD, owner["cost_warn_R"],
                                 symbol, l5_spread=(l5 or {}).get("spread_price"))
            l2_fail = sorted({c["id"] for c in gates["L2"]["checks"] if c["verdict"] in (FAIL, NOT_EVALUABLE)}) if gates else []
            c3 = causality(cycle, day, session, post, now, rng, symbol)
            m6 = manual_l6(cycle, day, session, post, now, symbol)
            cases.append({
                "case_id": f"recorded:{symbol}:{cycle}:{ds}", "cycle": cycle, "session_date": ds,
                "fixture": SYMBOLS[symbol]["fixture"], "fixture_classification": "RECORDED_DEVELOPMENT_FIXTURE",
                "setup": t.get("setup"), "direction": t.get("direction"), "entry": t.get("entry"),
                "stop_loss": t.get("stop_loss"), "decision": t["decision"],
                "ticket_gate_status": {k: v["status"] for k, v in gates.items()} if gates else None,
                "ticket_gate_blocking_failures": blocking_failures(gates) if gates else None,
                "l2_fail_ids": l2_fail, "l2_undeclared": sorted(set(l2_fail) - DECLARED_FAIL_CLOSED),
                "geometry": geometry_ok(t), "causality": c3, "l5_recorded_spread": l5,
                "owner_ticket_state": m6["state"], "owner_ticket_primary_block_reason": m6["primary_block_reason"],
                "edge_verified": m6["edge_verified"],
                "owner_ticket_L6": m6["L6"]["status"] if m6["L6"] else None,
            })
            cases[-1]["_day_type"] = day_type(t)
            cases[-1]["_first_setup"] = c3.pop("_first_setup")
            cases[-1]["_l6"] = m6
    return cases


def _cached_strategy_loads():
    """Verification-local memo of load_strategy (pure for an unchanged file); restored afterwards."""
    from v1_tickets import manual_ticket
    saved = fx.load_strategy, manual_ticket.load_strategy
    cached = functools.lru_cache(maxsize=None)(saved[0])
    fx.load_strategy = manual_ticket.load_strategy = cached
    return lambda: (setattr(fx, "load_strategy", saved[0]), setattr(manual_ticket, "load_strategy", saved[1]))


def _symbol_checks(symbol: str, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-symbol L2/L3/L4/L6 evidence over that symbol's recorded cases."""
    conforming = sorted({c["cycle"] for c in cases if c["ticket_gate_blocking_failures"] == []})
    causal = [c["causality"] for c in cases]
    l3 = {"cases": len(causal),
          "prefix_mismatches": sum(c["prefix_mismatches"] for c in causal),
          "pre_emission_signals": sum(c["pre_emission_signals"] for c in causal),
          "streaming_batch_mismatches": sum(not c["streaming_hash_parity"] for c in causal),
          "future_mutations": sum(c["future_mutations"] for c in causal),
          "future_mutation_mismatches": sum(c["future_mutation_mismatches"] for c in causal)}
    raw_zero = [c["case_id"] for c in cases if c["geometry"]["has_levels"] and not c["geometry"]["positive_stop"]]
    raw_inv = [c["case_id"] for c in cases if c["geometry"]["has_levels"] and not c["geometry"]["target_order"]]
    by_id = {c["case_id"]: c for c in cases}
    leaked = [i for i in raw_zero + raw_inv if not by_id[i]["ticket_gate_blocking_failures"]]
    admitted = [c for c in cases if c["ticket_gate_blocking_failures"] == []]
    l6 = [c["_l6"]["L6"]["status"] for c in cases if c["_l6"]["L6"]]
    counts = {k: 0 for k in DAY_TYPES + ("range-rejection", "insufficient-data")}
    per_cycle = {cy: dict(counts) for cy in CYCLES}
    for c in cases:
        counts[c["_day_type"]] += 1
        per_cycle[c["cycle"]][c["_day_type"]] += 1
    # Which branch was emitted first, and was that emission later revised (prefix or future-mutation)?
    revision = {}
    for c in cases:
        fs = c["_first_setup"]
        if fs is None:
            continue
        r = revision.setdefault(fs, {"cases": 0, "revised": 0, "revised_case_ids": []})
        r["cases"] += 1
        cz = c["causality"]
        if cz["prefix_mismatches"] or cz["future_mutation_mismatches"] or not cz["streaming_hash_parity"]:
            r["revised"] += 1
            r["revised_case_ids"].append(c["case_id"])
    return {
        "cases": len(cases), "days": len({c["session_date"] for c in cases}),
        "l3_by_first_emitted_setup": revision,
        "l2_undeclared_cases": [c["case_id"] for c in cases if c["l2_undeclared"]],
        "conforming_cycles": conforming,
        "l3": l3,
        "l4": {"raw_zero_stop": len(raw_zero), "raw_tp_inversion": len(raw_inv), "leaked_to_admitted": leaked,
               "admitted": len(admitted),
               "admitted_bad_geometry": sum(not (c["geometry"]["positive_stop"] and c["geometry"]["target_order"])
                                            for c in admitted)},
        "l6_statuses": sorted(set(l6)), "l6_cases": len(l6),
        "edge_verified_false": all(c["edge_verified"] is False for c in cases),
        "ticket_ready_cases": sum(c["owner_ticket_state"] == "TICKET_READY" for c in cases),
        "day_types": counts, "day_types_by_cycle": per_cycle,
    }


def build_report(generated_at: str) -> Dict[str, Any]:
    restore = _cached_strategy_loads()
    try:
        return _build_report(generated_at)
    finally:
        restore()


def _build_report(generated_at: str) -> Dict[str, Any]:
    strategy = load_strategy(CANDIDATE)
    from v1_tickets.manual_ticket import load_owner_config
    owner = load_owner_config(ROOT)
    registry = load_registry()[STRATEGY_ID]
    ident = logic_identity(STRATEGY_ID, VERSION)
    provenance = {sym: verify_provenance(sym) for sym in SYMBOLS}
    # EURUSD first on the shared stream, then the synthetic L4 sessions (unchanged order), then other symbols.
    rng = random.Random(SEED)
    by_symbol = {"EURUSD": _run_symbol("EURUSD", strategy, owner, rng)}
    l4_failures = SYMBOLS["EURUSD"]["l4_failures"]       # None: route has no historical failure list
    recorded_fail = json.loads((ROOT / l4_failures).read_text())["cases"] if l4_failures else []
    eur = {(c["cycle"], c["session_date"]): c for c in by_symbol["EURUSD"]}
    rec = []
    for f in recorded_fail:
        c = eur[(f["cycle"], f["session_date"])]
        reproduces = (not c["geometry"]["positive_stop"]) if f["kind"] == "ZERO_STOP" else (not c["geometry"]["target_order"])
        rec.append({**f, "reproduces_in_engine": reproduces,
                    "blocked_by_candidate": bool(c["ticket_gate_blocking_failures"]),
                    "fail_closed_rule": f["fail_closed_rule"] in c["l2_fail_ids"]})
    synth = l4_geometry(strategy, rng)
    for sym, spec in SYMBOLS.items():
        if sym != "EURUSD":
            by_symbol[sym] = _run_symbol(sym, strategy, owner, random.Random(spec["seed"]))
    per_symbol = {sym: _symbol_checks(sym, cases) for sym, cases in by_symbol.items()}
    cases = [c for sym in SYMBOLS for c in by_symbol[sym]]

    # L1 identity
    l1_checks = {
        "candidate_contract_sha256": ident["contract_hash"] == _sha256_text((CANDIDATE,), ROOT),
        "registry_identity_matches": registry["candidate_versions"][VERSION]["logic_verified_identity"] == ident["digest"],
        "frozen_v1_1_1_contract_unchanged": _sha256_text((FROZEN,), ROOT) == FROZEN_CONTRACT_HASH,
        "runtime_binding_v1_1_1": registry["config_source"] == FROZEN and fx.STRATEGY_PATH == FROZEN,
        "replay_determinism": all(c["ticket_gate_status"] is None or c["ticket_gate_status"]["L1"] == PASS for c in cases),
        "fixture_provenance_verified": all(provenance[s] is not None for s in SYMBOLS if SYMBOLS[s]["provenance"]),
    }
    l3 = {k: sum(p["l3"][k] for p in per_symbol.values()) for k in per_symbol["EURUSD"]["l3"]}
    # L5 risk and friction from the single D2 carrier; absent inputs are WARN with a reason, never 0.
    l5_warn = [
        "COMMISSION_NOT_AVAILABLE: no commission metadata for the FX ticket path; not assumed 0"]
    unrecorded = sorted({c["case_id"].split(":")[1] for c in cases if c["ticket_gate_blocking_failures"] == []
                         and c["l5_recorded_spread"]["spread_price"] is None})
    if unrecorded:
        l5_warn.append(f"SPREAD_NOT_RECORDED: no conservative spread (bar-only lower bound or missing) for "
                       f"{unrecorded}; cost_in_R not evaluable there (L2 closure uses a 0.2-pip test input only)")
    pending = sorted(s for s, v in COVERAGE["instruments"].items() if v == "PENDING_AGP-C2-SYMMAP")
    l5_warn.append(f"SYMBOL_METADATA_PENDING: {', '.join(pending)} -> PENDING_AGP-C2-SYMMAP (not invented)")
    l5_block = []
    if owner["risk_status"] != "SET":
        l5_block.append("RISK_CONFIG_MISSING: owner_ticket risk_pct/cost_warn_R/cost_block_R incomplete")
    missing_pip = sorted(set(SYMBOLS) - set(EVIDENCED_PIP))
    if missing_pip:
        l5_block.append(f"SYMBOL_EVIDENCE_MISSING: pip size not evidenced for {missing_pip}")
    for c in cases:
        c.pop("_l6")
        c.pop("_first_setup")
    day_types = {sym: {"counts": p["day_types"], "by_cycle": p["day_types_by_cycle"],
                       "by_case": {c["case_id"]: c.pop("_day_type") for c in by_symbol[sym]}}
                 for sym, p in per_symbol.items()}
    # Per-symbol gate table. L2 keeps the original rule: no undeclared divergence AND a conforming sweep
    # passing L1-L4 in BOTH windows. A window without a conforming ticket is NOT_EVIDENCED (never PASS).
    # No cross-symbol verdict is formed: each symbol stands on its own evidence.
    l1_global = all(v for k, v in l1_checks.items() if k not in ("replay_determinism", "fixture_provenance_verified"))
    l5_verdict = "BLOCK" if l5_block else (WARN if l5_warn else PASS)
    gates_by_symbol, verdicts, l2_evidence = {}, {}, {}
    for sym, p in per_symbol.items():
        sym_cases = by_symbol[sym]
        missing = [cy for cy in CYCLES if cy not in p["conforming_cycles"]]
        l2_evidence[sym] = {"undeclared_cases": p["l2_undeclared_cases"], "conforming_cycles": p["conforming_cycles"],
                            "conforming_not_evidenced": missing}
        l4_ok = not p["l4"]["leaked_to_admitted"] and p["l4"]["admitted_bad_geometry"] == 0
        if sym == "EURUSD":
            l4_ok = l4_ok and all(r["reproduces_in_engine"] and r["blocked_by_candidate"] and r["fail_closed_rule"]
                                  for r in rec) and synth["admitted_zero_stop"] == 0 \
                and synth["admitted_tp_inversion"] == 0 and synth["undeclared_l2_failures"] == 0
        g = {
            "L1": PASS if l1_global and all(c["ticket_gate_status"] is None or c["ticket_gate_status"]["L1"] == PASS
                                            for c in sym_cases)
            and (SYMBOLS[sym]["provenance"] is None or provenance[sym] is not None) else FAIL,
            "L2": FAIL if p["l2_undeclared_cases"] else (NOT_EVIDENCED if missing else PASS),
            "L3": PASS if not (p["l3"]["prefix_mismatches"] or p["l3"]["pre_emission_signals"]
                               or p["l3"]["streaming_batch_mismatches"] or p["l3"]["future_mutation_mismatches"])
            and p["l3"]["future_mutations"] > 0 else FAIL,
            "L4": PASS if l4_ok else FAIL,
            "L5": l5_verdict,
            "L6": PASS if p["l6_statuses"] == [PASS] else FAIL,
        }
        gates_by_symbol[sym] = g
        if any(g[k] == FAIL for k in ("L1", "L2", "L3", "L4", "L6")) or g["L5"] == "BLOCK" or not p["edge_verified_false"]:
            verdicts[sym] = "NOT_VERIFIED"
        elif NOT_EVIDENCED in g.values():
            verdicts[sym] = "PARTIAL"
        else:
            verdicts[sym] = "LOGIC_VERIFIED"
    coverage = json.loads(json.dumps(COVERAGE))
    for sym, p in per_symbol.items():
        missing = l2_evidence[sym]["conforming_not_evidenced"]
        coverage["instruments"][sym] = verdicts[sym] if not missing else \
            f"{verdicts[sym]}: {p['days']} recorded days; conforming ticket NOT_EVIDENCED in {', '.join(missing)}"
    range_seen = {sym: (d["counts"]["range-rejection"], p["l3_by_first_emitted_setup"].get("RANGE", {}).get("cases", 0))
                  for (sym, d), p in zip(day_types.items(), per_symbol.values())}
    if any(a or b for a, b in range_seen.values()):
        coverage["branches"]["RANGE_REJECTION"] = "RECORDED: " + "; ".join(
            f"{sym} {a} final / {b} first-emitted" for sym, (a, b) in range_seen.items() if a or b) + " (fails closed in L2)"
    coverage["day_types"] = {sym: {t: (f"EVIDENCED ({n})" if n else "NOT_EVIDENCED")
                                   for t, n in ((t, d["counts"][t]) for t in DAY_TYPES)}
                             for sym, d in day_types.items()}

    checks = {
        "L1_identity_and_contract": {"evidence": l1_checks, "logic_identity": ident},
        "L2_specification_engine_equivalence": {
            "reused": "docs/status/AG_ST_ASIAN_SWEEP_5R_V1_1_1_2_L2_CLOSURE_2026-10-07.md",
            "rule": "no undeclared/NOT_EVALUABLE check AND a conforming sweep passing L1-L4 in both windows",
            "evidence": l2_evidence},
        "L3_temporal_causality": {"evidence": l3, "by_symbol": {sym: p["l3"] for sym, p in per_symbol.items()},
                                  "seed": SEED},
        "L4_price_geometry": {"recorded_failures": rec, "synthetic": synth,
                              "by_symbol": {sym: p["l4"] for sym, p in per_symbol.items()},
                              "seed": SEED,
                              "fix": "no engine change (shared with frozen 1.1.1); 1.1.2 declared fail-closed rules "
                                     "R.stop_loss (risk_distance > 0) and R.target_order block every reproduced case"},
        "L5_risk_and_friction": {"verdict": l5_verdict,
                                 "d2_source": OWNER_CONFIG, "risk_pct": owner["risk_pct"], "cost_warn_R": owner["cost_warn_R"],
                                 "cost_block_R": owner["cost_block_R"], "warn_reasons": l5_warn,
                                 "block_reasons": l5_block},
        "L6_freshness_fields": {"evidence": {sym: {"cases": p["l6_cases"], "statuses": p["l6_statuses"]}
                                             for sym, p in per_symbol.items()}},
    }
    return {
        "schema": "AG_LOGIC_VERIFICATION_REPORT_V1", "generated_at": generated_at,
        "strategy_id": STRATEGY_ID, "version": VERSION, "strategy": f"{STRATEGY_ID}@{VERSION}",
        "contract_path": CANDIDATE, "contract_hash": ident["contract_hash"], "engine_hash": ident["engine_identity"],
        "logic_identity": ident["digest"], "verification_code_sha": code_sha(),
        "dataset_identity": {sym: {"path": spec["fixture"], "sha256": sha256_file(spec["fixture"]),
                                   "classification": "RECORDED_DEVELOPMENT_FIXTURE",
                                   "provenance": spec["provenance"],
                                   "provenance_sha256_verified": provenance[sym] is not None}
                             for sym, spec in SYMBOLS.items()},
        "cycles": list(CYCLES), "symbols": list(SYMBOLS), "coverage": coverage, "per_symbol": per_symbol,
        "day_types": day_types, "gates_by_symbol": gates_by_symbol, "verdicts": verdicts,
        "checks": checks, "cases": cases,
        "edge_status": "NOT_VERIFIED", "edge_verified": False, "economic_status": "NOT_EVALUATED",
        "admission": "NOT_ADMITTED (runtime loads v1.1.1; owner decision required)",
        "ready_authority": "OFF (D6; config/v1_tickets/ready_authority.yaml unchanged)",
        "demo_authorized": False, "live_authorized": False, "broker_calls": 0,
    }


def artifacts(report: Dict[str, Any]) -> Dict[str, Any]:
    c = report["checks"]
    l3 = c["L3_temporal_causality"]["by_symbol"]
    ok = lambda sym, *keys: PASS if not any(l3[sym][k] for k in keys) else FAIL  # noqa: E731
    return {
        "contract_identity.json": {"strategy_id": STRATEGY_ID, "strategy_version": VERSION,
                                   "canonicalization": "v1_tickets.authority._sha256_text (path + LF-normalized bytes)",
                                   "contract_path": CANDIDATE, "contract_hash": report["contract_hash"],
                                   "engine_identity": report["engine_hash"], "logic_identity": report["logic_identity"]},
        "prefix_invariance.json": {sym: {k: l3[sym][k] for k in ("cases", "prefix_mismatches", "pre_emission_signals")}
                                   | {"verdict": ok(sym, "prefix_mismatches", "pre_emission_signals")} for sym in l3},
        "future_mutation.json": {sym: {"seed": SEED, "iterations": l3[sym]["future_mutations"],
                                       "semantic_mismatches": l3[sym]["future_mutation_mismatches"],
                                       "verdict": ok(sym, "future_mutation_mismatches")} for sym in l3},
        "streaming_parity.json": {"semantic_fields": list(SEMANTIC), "implementation_path": "src/v1_tickets/fx.py -> strategy_engine",
                                  "by_symbol": {sym: {"batch_stream_mismatches": l3[sym]["streaming_batch_mismatches"],
                                                      "verdict": ok(sym, "streaming_batch_mismatches")} for sym in l3}},
        "geometry_report.json": {"recorded_failures": c["L4_price_geometry"]["recorded_failures"],
                                 "synthetic": c["L4_price_geometry"]["synthetic"],
                                 "by_symbol": c["L4_price_geometry"]["by_symbol"],
                                 "verdict_by_symbol": {sym: g["L4"] for sym, g in report["gates_by_symbol"].items()}},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", help="write report JSON + artifact set here")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--report-name", default="AGP_C3_ASW_V112_LOGIC_VERIFICATION",
                    help="report file stem; dated evidence from earlier runs is never overwritten")
    ap.add_argument("--artifact-dir", default="artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2")
    args = ap.parse_args(argv)
    report = build_report(f"{args.date}T00:00:00Z")
    if args.out_dir:
        out = ROOT / args.out_dir
        art = ROOT / args.artifact_dir
        art.mkdir(parents=True, exist_ok=True)
        for name, body in artifacts(report).items():
            (art / name).write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        (out / f"{args.report_name}_{args.date}.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"{report['schema']} {report['strategy']}")
    for sym, g in report["gates_by_symbol"].items():
        print(f"  {sym}: {report['verdicts'][sym]:<15} " + " ".join(f"{k}={v}" for k, v in g.items()))
    return 1 if "NOT_VERIFIED" in report["verdicts"].values() else 0


if __name__ == "__main__":
    raise SystemExit(main())
