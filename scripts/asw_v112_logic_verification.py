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
        "GBPUSD": "NOT_EVIDENCED: no usable recorded GBPUSD M15 sessions on main (SSC_FRESH_DEV_GEN_002 package is "
                  "QUARANTINED, +3h misaligned; ticket_outcome_m1 is 5 synthetic bars); no external data fetched",
        "USDJPY": "PENDING_AGP-C2-SYMMAP",
        "XAUUSD": "PENDING_AGP-C2-SYMMAP",
    },
    "branches": {"SWEEP": "VERIFIED_RECORDED_FIXTURE", "TREND": "VERIFIED_RECORDED_FIXTURE (fails closed)",
                 "RANGE_REJECTION": "UNIT_ONLY (no recorded day yields Entry 3)"},
}
FIXTURE = "tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv"
L4_FAILURES = "tests/fixtures/asian_sweep_v1_1_2/l4_recorded_failures.json"
DAYS = ("2026-06-15", "2026-06-16", "2026-06-17", "2026-06-23", "2026-07-17")
CYCLES = {"ASIAN_LONDON": ("Asian", 24), "LONDON_NEWYORK": ("London", 20)}
TEST_SPREAD = 0.00002          # L2-closure test input (0.2 pip), not recorded data
SEMANTIC = ("decision", "reason_code", "regime", "setup", "signal_id", "box", "signal_timestamp", "direction",
            "entry", "stop_loss", "risk_distance", "targets")
SEED, MUTATIONS_PER_CASE, SYNTHETIC_SESSIONS = 112, 25, 400
DECLARED_FAIL_CLOSED = {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss", "R.target_leg2",
                        "R.max_spread", "R.max_spread_fraction", "R.target_order"}


def sha256_file(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def load_candles() -> List[Candle]:
    with (ROOT / FIXTURE).open() as fh:
        return [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC), float(r["open"]),
                       float(r["high"]), float(r["low"]), float(r["close"])) for r in csv.DictReader(fh)]


def split(candles: List[Candle], cycle: str, day: dt.date):
    w = fx.session_windows_utc(day)[cycle]
    now = w["trade"][1]
    session = [c for c in candles if w["ref"][0] <= c.time < w["ref"][1]]
    post = [c for c in candles if w["trade"][0] <= c.time < w["trade"][1] and c.time + M15 <= now]
    return w, now, session, post


def ticket(cycle: str, day: dt.date, session, post, now, spread: Optional[float] = TEST_SPREAD) -> Dict[str, Any]:
    return fx.build_fx_ticket("EURUSD", cycle, day, session, CYCLES[cycle][1], post, data_source="FIXTURE",
                              evaluated_at=now, data_close=now, spread=spread, strategy_path=CANDIDATE)


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


def ticket_gates(strategy, cycle, day, session, post, now, w, t, spread, warn_r) -> Optional[Dict[str, Any]]:
    if t.get("direction") is None:
        return None
    ref_name, bars = CYCLES[cycle]
    return {
        "L1": l1_determinism(lambda: ticket(cycle, day, session, post, now, spread), session + post, now),
        "L2": l2_rule_conformance(strategy, t, session, bars, post, digits=5, spread=spread),
        "L3": l3_geometry(t, post, digits=5, declared_rr=5.0),
        "L4": l4_data_session(t, ref_window=w["ref"], trade_window=w["trade"], reference_name=ref_name,
                              session=session, expected_bar_count=bars, post=post, data_close=now, now=now),
        "L5": l5_cost(spread, t.get("risk_distance"), commission_r=None, warn_r=warn_r),
        "L6": l6_freshness(t.get("valid_until") or "set", {"x": 1}, {"y": 1}),
    }


def manual_l6(cycle, day, session, post, now) -> Optional[Dict[str, Any]]:
    """L6 exactly as the owner ticket computes it (logic_gate.l6_freshness), candidate replayed test-locally."""
    from v1_tickets.manual_ticket import build_manual_ticket, load_owner_config
    saved = fx.STRATEGY_PATH, fx.build_fx_ticket
    fx.STRATEGY_PATH, fx.build_fx_ticket = CANDIDATE, functools.partial(saved[1], strategy_path=CANDIDATE)
    try:
        t = build_manual_ticket("EURUSD", cycle, day, session, CYCLES[cycle][1], post, now=now, data_close=now,
                                spread=TEST_SPREAD, owner=load_owner_config(ROOT),
                                data_source="FIXTURE")
    finally:
        fx.STRATEGY_PATH, fx.build_fx_ticket = saved
    return {"state": t["state"], "primary_block_reason": t.get("primary_block_reason"),
            "edge_verified": t["invariants"]["edge_verified"],
            "L6": (t.get("logic_gate") or {}).get("L6")}


# ------------------------------------------------------------------------------- L3 causality

def causality(cycle: str, day: dt.date, session, post, now, rng: random.Random) -> Dict[str, Any]:
    full = semantic(ticket(cycle, day, session, post, now))
    stream = [semantic(ticket(cycle, day, session, post[:k], now)) for k in range(len(post) + 1)]
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
            mismatch += semantic(ticket(cycle, day, session, post[:first] + fut, now)) != full
    return {"bars": len(post), "first_emission_prefix_len": first, "prefix_mismatches": prefix_mismatch,
            "pre_emission_signals": pre_emission, "streaming_hash_parity": stream_parity,
            "future_mutations": mutated, "future_mutation_mismatches": mismatch}


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
        t = ticket(cycle, day, session, post, now, spread=0.0)
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

def build_report(generated_at: str) -> Dict[str, Any]:
    strategy = load_strategy(CANDIDATE)
    from v1_tickets.manual_ticket import load_owner_config
    owner = load_owner_config(ROOT)
    registry = load_registry()[STRATEGY_ID]
    ident = logic_identity(STRATEGY_ID, VERSION)
    candles = load_candles()
    rng = random.Random(SEED)
    cases, causal, l6s = [], [], []
    for cycle in CYCLES:
        for ds in DAYS:
            day = dt.date.fromisoformat(ds)
            w, now, session, post = split(candles, cycle, day)
            t = ticket(cycle, day, session, post, now)
            gates = ticket_gates(strategy, cycle, day, session, post, now, w, t, TEST_SPREAD, owner["cost_warn_R"])
            l2_fail = sorted({c["id"] for c in gates["L2"]["checks"] if c["verdict"] in (FAIL, NOT_EVALUABLE)}) if gates else []
            c3 = causality(cycle, day, session, post, now, rng)
            m6 = manual_l6(cycle, day, session, post, now)
            causal.append(c3)
            l6s.append(m6)
            cases.append({
                "case_id": f"recorded:EURUSD:{cycle}:{ds}", "cycle": cycle, "session_date": ds,
                "fixture": FIXTURE, "fixture_classification": "RECORDED_DEVELOPMENT_FIXTURE",
                "setup": t.get("setup"), "direction": t.get("direction"), "entry": t.get("entry"),
                "stop_loss": t.get("stop_loss"), "decision": t["decision"],
                "ticket_gate_status": {k: v["status"] for k, v in gates.items()} if gates else None,
                "ticket_gate_blocking_failures": blocking_failures(gates) if gates else None,
                "l2_fail_ids": l2_fail, "l2_undeclared": sorted(set(l2_fail) - DECLARED_FAIL_CLOSED),
                "geometry": geometry_ok(t), "causality": c3,
                "owner_ticket_state": m6["state"], "owner_ticket_primary_block_reason": m6["primary_block_reason"],
                "edge_verified": m6["edge_verified"],
                "owner_ticket_L6": m6["L6"]["status"] if m6["L6"] else None,
            })

    # L1 identity
    l1_checks = {
        "candidate_contract_sha256": ident["contract_hash"] == _sha256_text((CANDIDATE,), ROOT),
        "registry_identity_matches": registry["candidate_versions"][VERSION]["logic_verified_identity"] == ident["digest"],
        "frozen_v1_1_1_contract_unchanged": _sha256_text((FROZEN,), ROOT) == FROZEN_CONTRACT_HASH,
        "runtime_binding_v1_1_1": registry["config_source"] == FROZEN and fx.STRATEGY_PATH == FROZEN,
        "replay_determinism": all(c["ticket_gate_status"] is None or c["ticket_gate_status"]["L1"] == PASS for c in cases),
    }
    # L2 (closure reused): no undeclared divergence, nothing NOT_EVALUABLE, conforming sweep per cycle passes.
    conforming = {c["cycle"] for c in cases if c["ticket_gate_blocking_failures"] == []}
    l2_ok = all(not c["l2_undeclared"] for c in cases) and conforming == set(CYCLES)
    # L3 causality
    l3 = {"cases": len(causal),
          "prefix_mismatches": sum(c["prefix_mismatches"] for c in causal),
          "pre_emission_signals": sum(c["pre_emission_signals"] for c in causal),
          "streaming_batch_mismatches": sum(not c["streaming_hash_parity"] for c in causal),
          "future_mutations": sum(c["future_mutations"] for c in causal),
          "future_mutation_mismatches": sum(c["future_mutation_mismatches"] for c in causal)}
    l3_ok = not (l3["prefix_mismatches"] or l3["pre_emission_signals"] or l3["streaming_batch_mismatches"]
                 or l3["future_mutation_mismatches"]) and l3["future_mutations"] > 0
    # L4 geometry: recorded failures reproduce in the engine output, and are never admitted by the gates.
    recorded_fail = json.loads((ROOT / L4_FAILURES).read_text())["cases"]
    by_id = {(c["cycle"], c["session_date"]): c for c in cases}
    rec = []
    for f in recorded_fail:
        c = by_id[(f["cycle"], f["session_date"])]
        reproduces = (not c["geometry"]["positive_stop"]) if f["kind"] == "ZERO_STOP" else (not c["geometry"]["target_order"])
        rec.append({**f, "reproduces_in_engine": reproduces,
                    "blocked_by_candidate": bool(c["ticket_gate_blocking_failures"]),
                    "fail_closed_rule": f["fail_closed_rule"] in c["l2_fail_ids"]})
    synth = l4_geometry(strategy, rng)
    admitted = [c for c in cases if c["ticket_gate_blocking_failures"] == []]
    l4_ok = (all(r["reproduces_in_engine"] and r["blocked_by_candidate"] and r["fail_closed_rule"] for r in rec)
             and all(c["geometry"]["positive_stop"] and c["geometry"]["target_order"] for c in admitted)
             and synth["admitted_zero_stop"] == 0 and synth["admitted_tp_inversion"] == 0
             and synth["undeclared_l2_failures"] == 0)
    # L5 risk and friction from the single D2 carrier; absent inputs are WARN with a reason, never 0.
    l5_warn = [
        "COMMISSION_NOT_AVAILABLE: no commission metadata for the FX ticket path; not assumed 0"]
    l5_warn.append("SPREAD_NOT_RECORDED: the recorded fixture has no bid/ask; cost_in_R not evaluable on recorded "
                   "data (L2 closure uses a 0.2-pip test input only)")
    pending = sorted(s for s, v in COVERAGE["instruments"].items() if v == "PENDING_AGP-C2-SYMMAP")
    l5_warn.append(f"SYMBOL_METADATA_PENDING: {', '.join(pending)} -> PENDING_AGP-C2-SYMMAP (not invented)")
    l5_block = []
    if owner["risk_status"] != "SET":
        l5_block.append("RISK_CONFIG_MISSING: owner_ticket risk_pct/cost_warn_R/cost_block_R incomplete")
    if not {"EURUSD"} <= set(EVIDENCED_PIP):
        l5_block.append("SYMBOL_EVIDENCE_MISSING: EURUSD pip size not evidenced")
    # L6 per logic_gate.l6_freshness on the owner ticket path.
    l6_status = [m["L6"]["status"] for m in l6s if m["L6"]]
    l6_ok = bool(l6_status) and all(s == PASS for s in l6_status)
    edge_false = all(m["edge_verified"] is False for m in l6s)

    checks = {
        "L1_identity_and_contract": {"verdict": PASS if all(l1_checks.values()) else FAIL, "evidence": l1_checks,
                                     "logic_identity": ident},
        "L2_specification_engine_equivalence": {
            "verdict": PASS if l2_ok else FAIL, "reused": "docs/status/AG_ST_ASIAN_SWEEP_5R_V1_1_1_2_L2_CLOSURE_2026-10-07.md",
            "evidence": "no undeclared or NOT_EVALUABLE L2 check on any recorded case; conforming sweep passes "
                        f"L1-L4 in {sorted(conforming)}"},
        "L3_temporal_causality": {"verdict": PASS if l3_ok else FAIL, "evidence": l3, "seed": SEED},
        "L4_price_geometry": {"verdict": PASS if l4_ok else FAIL, "recorded_failures": rec, "synthetic": synth,
                              "seed": SEED,
                              "fix": "no engine change (shared with frozen 1.1.1); 1.1.2 declared fail-closed rules "
                                     "R.stop_loss (risk_distance > 0) and R.target_order block every reproduced case"},
        "L5_risk_and_friction": {"verdict": "BLOCK" if l5_block else (WARN if l5_warn else PASS),
                                 "d2_source": OWNER_CONFIG, "risk_pct": owner["risk_pct"], "cost_warn_R": owner["cost_warn_R"],
                                 "cost_block_R": owner["cost_block_R"], "warn_reasons": l5_warn,
                                 "block_reasons": l5_block},
        "L6_freshness_fields": {"verdict": PASS if l6_ok else FAIL,
                                "evidence": f"owner-ticket L6 (logic_gate.l6_freshness) on {len(l6_status)} signal cases: "
                                            f"{sorted(set(l6_status))}"},
    }
    blocking_ok = all(checks[k]["verdict"] == PASS for k in list(checks)[:4])
    verdict = "LOGIC_VERIFIED" if blocking_ok and checks["L5_risk_and_friction"]["verdict"] != "BLOCK" \
        and checks["L6_freshness_fields"]["verdict"] == PASS and edge_false else "NOT_VERIFIED"
    return {
        "schema": "AG_LOGIC_VERIFICATION_REPORT_V1", "generated_at": generated_at,
        "strategy_id": STRATEGY_ID, "version": VERSION, "strategy": f"{STRATEGY_ID}@{VERSION}",
        "contract_path": CANDIDATE, "contract_hash": ident["contract_hash"], "engine_hash": ident["engine_identity"],
        "logic_identity": ident["digest"], "verification_code_sha": code_sha(),
        "dataset_identity": {"path": FIXTURE, "sha256": sha256_file(FIXTURE),
                             "classification": "RECORDED_DEVELOPMENT_FIXTURE"},
        "cycles": list(CYCLES), "coverage": COVERAGE, "checks": checks, "cases": cases, "verdict": verdict,
        "edge_status": "NOT_VERIFIED", "edge_verified": False, "economic_status": "NOT_EVALUATED",
        "admission": "NOT_ADMITTED (runtime loads v1.1.1; owner decision required)",
        "ready_authority": "OFF (D6; config/v1_tickets/ready_authority.yaml unchanged)",
        "demo_authorized": False, "live_authorized": False, "broker_calls": 0,
    }


def artifacts(report: Dict[str, Any]) -> Dict[str, Any]:
    c = report["checks"]
    return {
        "contract_identity.json": {"strategy_id": STRATEGY_ID, "strategy_version": VERSION,
                                   "canonicalization": "v1_tickets.authority._sha256_text (path + LF-normalized bytes)",
                                   "contract_path": CANDIDATE, "contract_hash": report["contract_hash"],
                                   "engine_identity": report["engine_hash"], "logic_identity": report["logic_identity"]},
        "prefix_invariance.json": {k: c["L3_temporal_causality"]["evidence"][k]
                                   for k in ("cases", "prefix_mismatches", "pre_emission_signals")}
                                  | {"verdict": PASS if not (c["L3_temporal_causality"]["evidence"]["prefix_mismatches"]
                                                             or c["L3_temporal_causality"]["evidence"]["pre_emission_signals"]) else FAIL},
        "future_mutation.json": {"seed": SEED, "iterations": c["L3_temporal_causality"]["evidence"]["future_mutations"],
                                 "semantic_mismatches": c["L3_temporal_causality"]["evidence"]["future_mutation_mismatches"],
                                 "verdict": PASS if not c["L3_temporal_causality"]["evidence"]["future_mutation_mismatches"] else FAIL},
        "streaming_parity.json": {"semantic_fields": list(SEMANTIC), "implementation_path": "src/v1_tickets/fx.py -> strategy_engine",
                                  "batch_stream_mismatches": c["L3_temporal_causality"]["evidence"]["streaming_batch_mismatches"],
                                  "verdict": PASS if not c["L3_temporal_causality"]["evidence"]["streaming_batch_mismatches"] else FAIL},
        "geometry_report.json": {"recorded_failures": c["L4_price_geometry"]["recorded_failures"],
                                 "synthetic": c["L4_price_geometry"]["synthetic"], "verdict": c["L4_price_geometry"]["verdict"]},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", help="write report JSON + artifact set here")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    report = build_report(f"{args.date}T00:00:00Z")
    if args.out_dir:
        out = ROOT / args.out_dir
        art = ROOT / "artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2"
        art.mkdir(parents=True, exist_ok=True)
        for name, body in artifacts(report).items():
            (art / name).write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        (out / f"AGP_C3_ASW_V112_LOGIC_VERIFICATION_{args.date}.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"{report['schema']} {report['strategy']} verdict={report['verdict']}")
    for k, v in report["checks"].items():
        print(f"  {k:<40} {v['verdict']}")
    return 0 if report["verdict"] == "LOGIC_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
