"""C15-LSMC follow-up: independent L1-L6 logic audit of ST_LARGE_SMC_V1@1.1.0 (off-host, read-only).

Why this exists next to the two shipped harnesses
-------------------------------------------------
`scripts/lsmc_v110_logic_verification.py` (18 fixture cases) and
`scripts/lsmc_c15_symbol_replay.py` (60-day recorded crypto replay) both answer "does the
engine conform to its contract?". Neither one answers three questions this audit adds:

* **Was the rule actually exercised?** A gate status of PASS says nothing about coverage: a
  check that never ran is NOT_APPLICABLE and still leaves its gate PASS. Between the
  2026-10-09 LOGIC_VERIFIED report and 2026-10-13 the delivery gate added on 2026-10-10
  turned every OPPORTUNITY into REJECTED off-host, which made all six L2 opportunity rules,
  all of L3 geometry and L6 freshness NOT_APPLICABLE on 100% of cases while L2/L3/L6 kept
  printing PASS. Every lane here reports per-check verdict counts, not just gate statuses.
* **Is there FX evidence?** C15/C16 verified BTCUSD/ETHUSD only, where C10 stop geometry is
  NOT_APPLICABLE (`C10_PIP_SIZE_NOT_EVIDENCED`). Lane B replays the only HOST_CAPTURED FX
  fixture in the repository (EURUSD, pip evidenced), so C10 stop and L3 stop geometry are
  measured on recorded FX bars for the first time.
* **Are the declared rules implemented with the declared semantics?** Lane D checks rules the
  gate compares only numerically (POI age unit, tie tolerance, day boundary across DST,
  session expiry, weekend window, fail-closed metadata, ARCHIVE_ONLY exactly-once).

This script changes no rule, no contract, no registry authority and no delivery path. It
reads committed inputs only: no broker, no network, no MT5 call (the import-only Linux
MetaTrader5 shim is loaded exactly as the shipped harnesses load it).

The report is byte-reproducible: it carries no wall-clock field, no run id and no hostname.

    python scripts/lsmc_v110_logic_audit.py [--out PATH.json] [--crypto-scans N] [--skip-crypto]
"""
from __future__ import annotations

import argparse
import ast
import bisect
import csv
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "scripts")]
os.environ["AG_EVIDENCE_ROOT"] = str(ROOT)   # committed VT host captures only

if "MetaTrader5" not in sys.modules:   # import-only Linux shim (as scripts/lsmc_v110_logic_verification.py)
    _spec = importlib.util.spec_from_file_location("lsmc_audit_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))

import lsmc_v110_logic_verification as HARNESS  # noqa: E402  (the shipped 18-case harness, audited as-is)
import yaml  # noqa: E402
from _lsmc_v111_fixtures import (  # noqa: E402
    check_decision_time,
    decision_time_utc,
    fixture_manifest,
    load_fixture,
)

from fx_discovery import features as F  # noqa: E402
from large_smc_core.c10_stop_policy import MIN_BUFFER_PIPS  # noqa: E402
from large_smc_watch import contract as C  # noqa: E402
from large_smc_watch import detect as D  # noqa: E402
from large_smc_watch import watch as W  # noqa: E402
from post_asian_pilot.report_archive import archive_path  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from ticket_delivery.archive import _report_type  # noqa: E402
from ticket_delivery.renderer import payload_hash  # noqa: E402
from v1_tickets import lsmc_logic_gate as G  # noqa: E402
from v1_tickets.code_identity import code_sha  # noqa: E402
from v1_tickets.logic_gate import FAIL, NOT_APPLICABLE, PASS, WARN  # noqa: E402

SCHEMA = "AGP_C15_LSMC_V110_LOGIC_AUDIT_V1"
MISSION = ("AGP-C17-LSMC-LOGIC-COMPLETION-R1 Phase A/C, continuing the C15-LSMC follow-up "
           "(docs/governance/AGP_C15_THREE_STRATEGY_LOGIC_FIRST_2026-10-11.md); "
           "independent logic audit, 2026-10-13")
UTC = dt.timezone.utc
NY = ZoneInfo(C.DAY_BOUNDARY_TZ)
HOST_COUNTS = {"D1": 30, "H1": 200, "M5": 300}   # scripts/host/live_candles_smoke.py COUNTS
CRYPTO_DATASET = ROOT / "tests/fixtures/ccfd_v100/recorded_60d"
FX_H1_EXPORT = ROOT / "data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_001/raw/EURUSD_H1.csv"
C16_ARTIFACTS = ROOT / "artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c16_2026-10-12"
# Every declared rule of the frozen 1.1.0 contract, with the code that must implement it.
CONTRACT_RULES = {
    "swings": "src/fx_discovery/features.py::swings (SW-A strict fractal, known_at = index + k)",
    "poi": "src/large_smc_watch/detect.py::h1_pois (AG_ORDER_BLOCK_V1 + FVG on H1)",
    "sweep": "src/fx_discovery/features.py::sweeps (wick beyond a KNOWN swing, close back inside)",
    "break": "src/large_smc_watch/detect.py::tolerant_breaks (close beyond level +/- tie tolerance)",
    "displacement": "src/entry_confirmation/displacement.py::evaluate_displacement",
    "sweep_to_choch_window_m5_bars": "src/large_smc_watch/detect.py::m5_opportunities",
    "near_poi_band": "src/large_smc_watch/watch.py::evaluate_snapshot (band = 0.5 x ATR(H1,14))",
    "entry": "src/large_smc_watch/detect.py::Opportunity.entry_reference (CHoCH bar close)",
    "stop": "src/large_smc_core/c10_stop_policy.py::compute_c10_stop",
    "targets": "src/large_smc_watch/detect.py::c11_causal_target",
    "day_boundary": "src/large_smc_watch/watch.py::trading_date / next_day_boundary",
    "opportunity_expiry": "src/large_smc_watch/watch.py::session_end (config/canonical_sessions.yaml)",
    "stale": "src/large_smc_watch/watch.py::WatchTracker.poll (SUSPEND_THEN_EXPIRE)",
    "alerts.mapping": "src/large_smc_watch/contract.py::ALERT_LEVEL + watch.WatchTracker._emit",
    "symbol_metadata": "src/large_smc_watch/contract.py::resolve_point (host capture only)",
    "poi.max_age_trading_days": "src/large_smc_watch/watch.py::expires_at (POI_MAX_AGE_TRADING_DAYS)",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _counts(counter: Counter) -> dict:
    return {str(k): int(v) for k, v in sorted(counter.items())}


def check_coverage(results) -> dict:
    """Alias of the gate's own coverage function, so every lane reports identical semantics."""
    return G.check_coverage(results)


def window(bars, tf: str, now: dt.datetime, counts=HOST_COUNTS):
    """The host's rolling window: the last `counts[tf]` bars opened at or before `now`.

    The forming bar is deliberately included -- the engine must drop it (L1 truncation).
    """
    j = bisect.bisect_right([b.time for b in bars], now)
    return bars[max(0, j - counts[tf]):j]


# --------------------------------------------------------------------------- identity

def identity() -> dict:
    manifest = fixture_manifest()
    eurusd = ROOT / "tests/fixtures/large_smc_v111/EURUSD.json"
    out = {
        "strategy": f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION}",
        "code_sha": code_sha(),
        "contract_path": str(G.CONTRACT_PATH.relative_to(ROOT)),
        "contract_sha256": sha256(G.CONTRACT_PATH),
        "engine_sha256": G.engine_sha256(),
        "engine_file_sha256": {f: G.file_sha256(f) for f in G.ENGINE_FILES},
        "dependency_sha256": {f: G.file_sha256(f) for f in G.DEPENDENCY_FILES},
        "gate_file_sha256": {f: G.file_sha256(f) for f in (
            "src/v1_tickets/lsmc_logic_gate.py", "src/v1_tickets/logic_gate.py")},
        "registry_identity": G.registry_identity(),
        "fixture_set": {
            "manifest_decision_time_utc": decision_time_utc(),
            "eurusd_fixture_sha256": sha256(eurusd),
            "manifest_pins_match_files": all(
                sha256(ROOT / e["fixture_file"]) == e["fixture_sha256"] for e in manifest["fixtures"]),
            "every_fixture_evaluated_at_is_the_decision_time": all(
                json.loads((ROOT / e["fixture_file"]).read_text(encoding="utf-8"))["evaluated_at_utc"]
                == decision_time_utc() for e in manifest["fixtures"]),
        },
        "fx_h1_export": {
            "path": str(FX_H1_EXPORT.relative_to(ROOT)), "sha256": sha256(FX_H1_EXPORT),
            "provenance": "committed MT5 export; broker/server/account per its own dataset_manifest.json",
            "dataset_manifest_sha256": sha256(FX_H1_EXPORT.parent.parent / "dataset_manifest.json"),
        },
        "authority_flags": {
            "proposal_generation_authorized": C.PROPOSAL_GENERATION_AUTHORIZED,
            "economic_status": C.ECONOMIC_STATUS,
            "contract_proposal_generation_authorized": yaml.safe_load(
                G.CONTRACT_PATH.read_text(encoding="utf-8"))["proposal_generation_authorized"],
            "contract_demo_authorized": yaml.safe_load(
                G.CONTRACT_PATH.read_text(encoding="utf-8"))["demo_authorized"],
            "contract_live_authorized": yaml.safe_load(
                G.CONTRACT_PATH.read_text(encoding="utf-8"))["live_authorized"],
            "delivery_mode": W.DELIVERY_MODE,
        },
    }
    out["authority_flags"]["all_authority_false"] = not any([
        out["authority_flags"]["proposal_generation_authorized"],
        out["authority_flags"]["contract_proposal_generation_authorized"],
        out["authority_flags"]["contract_demo_authorized"],
        out["authority_flags"]["contract_live_authorized"]])
    return out


# --------------------------------------------------------------------------- lane A

def lane_a() -> dict:
    """The shipped 18-case fixture harness, run in-process and audited for coverage."""
    spec = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))
    cases = HARNESS.cases()
    results = [G.evaluate_case(spec, c) for c in cases]
    cov = check_coverage(results)
    return {
        "driver": "scripts/lsmc_v110_logic_verification.py::cases (unchanged case list)",
        "gate": "v1_tickets.lsmc_logic_gate.evaluate_case",
        "cases": len(results),
        "blocking_failures": {r["case_id"]: r["blocking_failures"] for r in results if r["blocking_failures"]},
        "verdict": G.LOGIC_VERIFIED if all(not r["blocking_failures"] for r in results) else G.LOGIC_NOT_VERIFIED,
        "states": {"shipped": _counts(Counter(r["state"] for r in results)),
                   "signal": _counts(Counter(r["signal_state"] for r in results))},
        "delivery_rejections": _counts(Counter(r["delivery_rejection"] for r in results if r["delivery_rejection"])),
        "opportunity_symbols_covered_signal_lane": sorted(
            {r["symbol"] for r in results if r["signal_state"] == "OPPORTUNITY"}),
        "opportunity_symbols_covered_shipped_state": sorted(
            {r["symbol"] for r in results if r["state"] == "OPPORTUNITY"}),
        "c10_stop_price_symbols": sorted(
            {r["symbol"] for r in results if r["signal_state"] == "OPPORTUNITY" and r["stop_c10"] is not None}),
        "per_symbol_cases": _counts(Counter(r["symbol"] for r in results)),
        "per_symbol_gates": {
            sym: {g: _counts(Counter(r["gate_status"][g] for r in results if r["symbol"] == sym))
                  for g in ("L1", "L2", "L3", "L4", "L5", "L6")}
            for sym in sorted({r["symbol"] for r in results})},
        "per_symbol_states": {
            sym: {"shipped": _counts(Counter(r["state"] for r in results if r["symbol"] == sym)),
                  "signal": _counts(Counter(r["signal_state"] for r in results if r["symbol"] == sym))}
            for sym in sorted({r["symbol"] for r in results})},
        "per_symbol_classifications": {
            sym: sorted({r["fixture_classification"] for r in results if r["symbol"] == sym})
            for sym in sorted({r["symbol"] for r in results})},
        "check_coverage": cov,
    }


# --------------------------------------------------------------------------- lane B

def lane_b(scans_every: int = 1) -> dict:
    """Rolling replay of the only HOST_CAPTURED FX fixture: EURUSD, every M5 close.

    This is the lane where C10 stop geometry is evaluable at all, because EURUSD is one of
    the two symbols with a repo-evidenced pip (`contract.C10_PIP_SIZE`).
    """
    spec = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))
    fx = load_fixture("EURUSD")
    d1, h1, m5 = fx["D1"], fx["H1"], fx["M5"]
    point, source = C.resolve_point("EURUSD")
    states = Counter()
    gate_status = {g: Counter() for g in ("L1", "L2", "L3", "L4", "L5", "L6")}
    results, opportunities, rejections = [], {}, Counter()
    scan_times = []
    for i, bar in enumerate(m5):
        now = bar.time + dt.timedelta(minutes=C.TIMEFRAME_MINUTES["M5"])
        closed_h1 = [b for b in h1 if D.close_time(b, C.TIMEFRAME_MINUTES["H1"]) <= now]
        closed_m5 = m5[:i + 1]
        if len(closed_h1) < C.MIN_H1_BARS or len(closed_m5) < C.MIN_M5_BARS:
            continue
        if scans_every > 1 and len(scan_times) % scans_every:
            scan_times.append(now)
            continue
        scan_times.append(now)
        case = {"case_id": f"EURUSD:host_captured:{now.isoformat()}", "symbol": "EURUSD", "now": now,
                "fixture": "tests/fixtures/large_smc_v111/EURUSD.json", "classification": "HOST_CAPTURED",
                "D1": window(d1, "D1", now), "H1": window(h1, "H1", now), "M5": window(m5, "M5", now)}
        shipped = W.evaluate_snapshot("EURUSD", case["D1"], case["H1"], case["M5"], now)
        res = G.evaluate_case(spec, case)
        results.append(res)
        states[shipped.state] += 1
        if shipped.state == "REJECTED":
            rejections[shipped.reason_codes[0]] += 1
        for g, status in res["gate_status"].items():
            gate_status[g][status] += 1
        if res["signal_state"] == "OPPORTUNITY":
            o = shipped.opportunity          # the DETECTED opportunity, pre-delivery-gate
            opportunities.setdefault(o["opp_id"], {
                "first_seen_utc": now.isoformat(), "direction": o["direction"], "poi_kind": o["poi_id"].split(":")[2],
                "entry_reference": o["entry_reference"], "sweep_extreme": o["sweep_extreme"],
                "choch_time": o["choch_time"], "stop_c10": o["stop_c10"], "stop_reason": o["stop_reason"],
                "target_c11": o["target_c11"], "target_reason": o["target_reason"],
                "target_tier": o["target_tier"], "expires_at": o["expires_at"],
                "shipped_state": shipped.state, "delivery_rejection": (shipped.reason_codes or [None])[0],
                "scans": 0})
            opportunities[o["opp_id"]]["scans"] += 1
    cov = check_coverage(results)
    blocking = {g: c for g, c in gate_status.items() if g in G.BLOCKING and (c[FAIL] or c[WARN])}
    # A weekend scan is legitimately MARKET_CLOSED, and L4 ("was this an evaluable trading
    # snapshot?") fails on exactly those. That relation is the check, not an exception to it:
    # any other blocking-gate failure means an evaluable scan broke a rule.
    market_closed = states.get("MARKET_CLOSED", 0)
    l4_fail = gate_status["L4"][FAIL]
    other_blocking = {g: c for g, c in blocking.items() if g != "L4"}
    verdict_reasons = []
    if l4_fail != market_closed:
        verdict_reasons.append(f"L4 FAIL on {l4_fail} scans but only {market_closed} were MARKET_CLOSED: "
                               "an evaluable scan failed a blocking gate")
    if other_blocking:
        verdict_reasons.append("blocking gates not PASS: " + ", ".join(sorted(other_blocking)))
    with_stop = sum(1 for o in opportunities.values() if o["stop_c10"] is not None)
    if not opportunities:
        verdict_reasons.append("no OPPORTUNITY scan in the window: the C10/C11 geometry was never reached")
    elif not with_stop:
        verdict_reasons.append("no opportunity carried a computed C10 stop price")
    return {
        "verdict": PASS if not verdict_reasons else FAIL,
        "verdict_reasons": verdict_reasons,
        "driver": "this script (rolling host windows D1 30 / H1 200 / M5 300, cadence = every M5 close)",
        "symbol": "EURUSD", "classification": "HOST_CAPTURED",
        "fixture_sha256": sha256(ROOT / "tests/fixtures/large_smc_v111/EURUSD.json"),
        "fixture_evaluated_at_utc": decision_time_utc(),
        "point": point, "point_source": source,
        "bars": {"D1": len(d1), "H1": len(h1), "M5": len(m5)},
        "window": {"first_scan_utc": scan_times[0].isoformat(), "last_scan_utc": scan_times[-1].isoformat(),
                   "scans": len(results)},
        "states_shipped": _counts(states),
        "market_closed_scans": market_closed,
        "l4_fail_equals_market_closed": l4_fail == market_closed,
        "delivery_rejection_reasons": _counts(rejections),
        "gate_status_counts": {g: _counts(c) for g, c in sorted(gate_status.items())},
        "blocking_gates_not_pass": {g: _counts(c) for g, c in sorted(blocking.items())},
        "check_coverage": cov,
        "opportunities": {"distinct": len(opportunities),
                          "by_direction": _counts(Counter(o["direction"] for o in opportunities.values())),
                          "with_c10_stop_price": with_stop,
                          "stop_reasons": _counts(Counter(o["stop_reason"] for o in opportunities.values()
                                                          if o["stop_reason"])),
                          "target_reasons": _counts(Counter(o["target_reason"] for o in opportunities.values()
                                                            if o["target_reason"])),
                          "items": opportunities},
        "note": ("state = the shipped snapshot (detection + the 2026-10-10 delivery gate); signal_state = "
                 "detection only. Off-host the delivery gate rejects every detected opportunity: "
                 "REJECT_NO_STOP / REJECT_NO_TARGET where C10 or C11 legitimately produced no level, and "
                 "REJECT_STALE for the fully-costed ones, because the owner remaining-reward threshold "
                 "config/local/actionability_policy.yaml is host-only and has no fallback "
                 "(watch._remaining_fraction). REJECT_STALE counts are therefore an environment fact, "
                 "not a rule failure."),
    }


# --------------------------------------------------------------------------- lane C

def _load_crypto(symbol: str):
    bars, spread = {}, {}
    for tf in ("D1", "H1", "M5"):
        rows = list(csv.DictReader((CRYPTO_DATASET / f"{symbol}_{tf.lower()}.csv").open(encoding="utf-8")))
        bars[tf] = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]), float(r["open"]), float(r["high"]),
                           float(r["low"]), float(r["close"]), None) for r in rows]
        meta = list(csv.DictReader((CRYPTO_DATASET / f"{symbol}_{tf.lower()}_meta.csv").open(encoding="utf-8")))
        spread[tf] = {dt.datetime.fromisoformat(r["timestamp_utc"]): float(r["spread_price"]) for r in meta
                      if r.get("spread_price")}
    return bars, spread


def verify_committed_c16(symbol: str) -> dict:
    """Re-derive every hash and count the committed C16 artifact asserts. No replay needed."""
    path = C16_ARTIFACTS / f"lsmc_{symbol.lower()}_vt_recorded_60d.json"
    art = json.loads(path.read_text(encoding="utf-8"))
    checks = {}
    checks["artifact_sha256"] = sha256(path)
    ident = art["identity"]
    checks["contract_sha256_matches_tree"] = ident["contract_sha256"] == sha256(G.CONTRACT_PATH)
    checks["engine_sha256_matches_tree"] = ident["engine_sha256"] == G.engine_sha256()
    checks["engine_file_sha256_matches_tree"] = all(
        ident["engine_file_sha256"][f] == G.file_sha256(f) for f in G.ENGINE_FILES)
    checks["registry_engine_pin_still_differs"] = (
        ident["registry_engine_sha256"] == G.registry_identity()["registry_engine_sha256"]
        and not ident["engine_matches_registry"])
    ds = art["dataset"]
    checks["dataset_sha256_matches_files"] = all(
        sha256(CRYPTO_DATASET / name) == value for name, value in ds["sha256"].items())
    checks["capture_report_sha256_matches_file"] = ds["capture_report_sha256"] == sha256(
        CRYPTO_DATASET / "capture_report.json")
    bars, _spread = _load_crypto(symbol)
    checks["dataset_bar_counts_match_files"] = ds["bars"] == {tf: len(v) for tf, v in bars.items()}
    # internal arithmetic of the committed report
    st = art["states"]
    checks["signal_states_sum_to_full_d1_scans"] = sum(st["signal"].values()) == art["replay"]["scans_full_d1_window"]
    checks["operational_states_sum_to_full_d1_scans"] = (
        sum(st["operational"].values()) == art["replay"]["scans_full_d1_window"])
    checks["opportunity_scans_equal_operational_rejections"] = (
        st["signal"]["OPPORTUNITY"] == sum(art["operational_rejection_reasons"].values()))
    checks["gate_counts_sum_to_full_d1_scans"] = all(
        sum(c.values()) == art["replay"]["scans_full_d1_window"] for c in art["gate_status_counts"].values())
    checks["opportunity_items_match_distinct"] = len(art["opportunities"]["items"]) == art["opportunities"]["distinct"]
    checks["opportunity_items_sum_matches_distinct"] = (
        sum(art["opportunities"]["items"][k]["scans"] for k in art["opportunities"]["items"])
        == st["signal"]["OPPORTUNITY"] + art["short_d1_window"]["states"]["signal"].get("OPPORTUNITY", 0))
    checks["by_direction_sums_to_distinct"] = sum(art["opportunities"]["by_direction"].values()) == \
        art["opportunities"]["distinct"]
    checks["scans_split_is_exhaustive"] = (art["replay"]["scans_full_d1_window"]
                                           + art["replay"]["scans_with_short_d1_window"] == art["replay"]["scans"])
    checks["verdict_is_not_verified"] = art["verdict"] == "NOT_VERIFIED"
    # What the artifact's own gate headline does NOT say: how many checks were evaluated.
    full, opp = art["replay"]["scans_full_d1_window"], st["signal"]["OPPORTUNITY"]
    with_stop = art["opportunities"]["with_c10_stop"]
    derived = {
        "headline_in_artifact": "gate_status_counts L1-L4 + L6 = PASS on every full-D1 scan",
        "full_d1_scans": full,
        "opportunity_scans_full_d1": opp,
        "scans_where_every_opportunity_rule_was_not_applicable": full - opp,
        "opportunities_with_c10_stop": with_stop,
        "l3_stop_geometry_assertions_evaluable": bool(with_stop),
        "reading": ("A gate status of PASS counts the gate, not the checks inside it. On this 60-day replay "
                    f"L2's six opportunity rules were evaluable on {opp} of {full} full-D1 scans, and "
                    "L3.stop_side / L3.stop_beyond_sweep on 0 of them (with_c10_stop = 0, "
                    "C10_PIP_SIZE_NOT_EVIDENCED). The committed NOT_VERIFIED verdict already says the second "
                    "half; this makes the first half explicit."),
    }
    return {"artifact": str(path.relative_to(ROOT)), "checks": checks,
            "coverage_derived_from_artifact": derived,
            "all_pass": all(v for k, v in checks.items() if k != "artifact_sha256"),
            "committed_verdict": art["verdict"], "committed_verdict_reasons": art["verdict_reasons"]}


def lane_c(scans: int) -> dict:
    """Bounded fresh reproduction of the committed C16 crypto lane on full-D1 scans."""
    spec = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))
    out = {}
    for symbol in C.CRYPTO_SYMBOLS:
        bars, _spread = _load_crypto(symbol)
        m5 = bars["M5"]
        first = next(i for i, b in enumerate(m5) if b.time + dt.timedelta(minutes=5) >= max(
            bars["H1"][HOST_COUNTS["H1"]].time, m5[HOST_COUNTS["M5"]].time))
        # Deterministic subset: the first `scans` scans whose D1 window is full (the C16 headline scope).
        chosen = []
        for i in range(first, len(m5)):
            now = m5[i].time + dt.timedelta(minutes=C.TIMEFRAME_MINUTES["M5"])
            if len(window(bars["D1"], "D1", now)) >= HOST_COUNTS["D1"]:
                chosen.append((i, now))
            if len(chosen) >= scans:
                break
        states, gate_status, rejections = Counter(), {g: Counter() for g in ("L1", "L2", "L3", "L4", "L5", "L6")}, Counter()
        results, stop_reasons, targets = [], Counter(), Counter()
        opportunity_scans = 0
        for i, now in chosen:
            case = {"case_id": f"{symbol}:{now.isoformat()}", "symbol": symbol, "now": now,
                    "fixture": str(CRYPTO_DATASET.relative_to(ROOT)), "classification": "VT_RECORDED",
                    "D1": window(bars["D1"], "D1", now), "H1": window(bars["H1"], "H1", now),
                    "M5": window(bars["M5"], "M5", now)}
            shipped = W.evaluate_snapshot(symbol, case["D1"], case["H1"], case["M5"], now)
            res = G.evaluate_case(spec, case)
            results.append(res)
            states[shipped.state] += 1
            if shipped.state == "REJECTED":
                rejections[shipped.reason_codes[0]] += 1
            for g, status in res["gate_status"].items():
                gate_status[g][status] += 1
            if res["signal_state"] == "OPPORTUNITY" and shipped.opportunity:
                opportunity_scans += 1
                stop_reasons[shipped.opportunity.get("stop_reason") or "STOP_COMPUTED"] += 1
                targets[shipped.opportunity.get("target_reason") or "TARGET_COMPUTED"] += 1
        cov = check_coverage(results)
        blocking_c = {g: c for g, c in gate_status.items() if g in G.BLOCKING and (c[FAIL] or c[WARN])}
        reasons_c = []
        if gate_status["L4"][FAIL] != states.get("MARKET_CLOSED", 0):
            reasons_c.append(f"L4 FAIL on {gate_status['L4'][FAIL]} scans but "
                             f"{states.get('MARKET_CLOSED', 0)} were MARKET_CLOSED")
        if {g: c for g, c in blocking_c.items() if g != "L4"}:
            reasons_c.append("blocking gates not PASS: "
                             + ", ".join(sorted(g for g in blocking_c if g != "L4")))
        # The crypto half of the book cannot evidence a pip (D-LSMC-1): every detected
        # opportunity must fail C10 closed with exactly that reason and must never invent a stop.
        pip_evidenced = symbol in C.C10_PIP_SIZE
        stop_reason_set = set(stop_reasons)
        if not pip_evidenced and stop_reasons and stop_reason_set != {"C10_PIP_SIZE_NOT_EVIDENCED"}:
            reasons_c.append(f"stop reasons {sorted(stop_reason_set)} are not the fail-closed "
                             "C10_PIP_SIZE_NOT_EVIDENCED the missing pip evidence requires")
        if pip_evidenced and "C10_PIP_SIZE_NOT_EVIDENCED" in stop_reason_set:
            reasons_c.append("a pip-evidenced symbol reported C10_PIP_SIZE_NOT_EVIDENCED")
        out[symbol] = {
            "verdict": PASS if not reasons_c else FAIL,
            "verdict_reasons": reasons_c,
            "scans": len(results), "scope": "first N full-D1-window scans (the C16 headline scope)",
            "first_scan_utc": chosen[0][1].isoformat(), "last_scan_utc": chosen[-1][1].isoformat(),
            "c10_pip_evidenced": pip_evidenced,
            "c10_stop_geometry_evaluable": pip_evidenced and bool(stop_reasons),
            "opportunity_scans_signal_lane": opportunity_scans,
            "scans_where_opportunity_rules_were_not_applicable": len(results) - opportunity_scans,
            "states_shipped": _counts(states), "delivery_rejection_reasons": _counts(rejections),
            "gate_status_counts": {g: _counts(c) for g, c in sorted(gate_status.items())},
            "opportunity_stop_reasons": _counts(stop_reasons), "opportunity_target_reasons": _counts(targets),
            "check_coverage": {k: v for k, v in cov.items() if k != "check_verdict_counts"},
            "opportunity_check_verdicts": {k: v for k, v in cov["check_verdict_counts"].items()
                                           if k.startswith(("L2.direction", "L2.entry", "L2.sweep_window",
                                                            "L2.expiry", "L2.c10", "L2.c11", "L3.", "L6."))},
        }
        out[f"{symbol}_committed_c16"] = verify_committed_c16(symbol)
    return out


# --------------------------------------------------------------------------- lane D: properties

def _synthetic_fx_calendar(weeks: int = 4) -> list:
    """Hourly FX trading instants built from the contract's own weekend rule (no invented calendar)."""
    start = dt.datetime(2026, 3, 2, 0, 0, tzinfo=UTC)   # spans the 2026-03-08 US DST start
    out, t = [], start
    while t < start + dt.timedelta(weeks=weeks):
        if not W.fx_market_closed(t):
            out.append(t)
        t += dt.timedelta(hours=1)
    return out


def _start_of_trading_date(d: dt.date) -> dt.datetime:
    """The instant a NY-17:00 trading date begins: 17:00 New York on the previous calendar day."""
    return dt.datetime.combine(d, dt.time(0, 0), tzinfo=NY) - dt.timedelta(hours=24 - C.DAY_BOUNDARY_HOUR)


def _declared_poi_expiry(origin: dt.datetime, calendar) -> tuple:
    """Expiry under the DECLARED rule: age = distinct trading dates since origin, valid while <= 5."""
    dates = sorted({W.trading_date(t) for t in calendar if W.trading_date(t) >= W.trading_date(origin)})
    if len(dates) <= C.POI_MAX_AGE_TRADING_DAYS + 1:
        return None, dates
    return _start_of_trading_date(dates[C.POI_MAX_AGE_TRADING_DAYS + 1]), dates


def _engine_poi_expiry(origin: dt.datetime) -> dt.datetime:
    """Expiry as implemented: POI_MAX_AGE_TRADING_DAYS + 1 calendar NY-17:00 boundaries."""
    t = origin
    for _ in range(C.POI_MAX_AGE_TRADING_DAYS + 1):
        t = W.next_day_boundary(t)
    return t


def poi_age_semantics() -> dict:
    """Contract/frozen-spec unit is TRADING days; the engine counts CALENDAR NY-17:00 dates."""
    out = {"declared_rule": "LSMC_SPEC_V2_FROZEN 4.2 / contract rules.poi.max_age_trading_days = 5 trading days",
           "implemented_rule": ("watch.expires_at: POI_MAX_AGE_TRADING_DAYS + 1 applications of next_day_boundary "
                                "= 6 consecutive CALENDAR NY-17:00 dates from the POI origin"),
           "dead_code": {"symbol": "large_smc_watch.watch._poi_age_days",
                         "line": 164,
                         "implements": "distinct NY-17:00 trading dates since the POI origin (the declared unit)",
                         "callers_in_repository": 0,
                         "note": "defined and never called; the declared semantics exist in the file but are unwired"}}
    calendars = {
        "SYNTHETIC_FX_4WEEKS": _synthetic_fx_calendar(),
        "EURUSD_H1_COMMITTED_EXPORT": [dt.datetime.strptime(r["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=UTC) for r in csv.DictReader(FX_H1_EXPORT.open(encoding="utf-8"))],
        "BTCUSD_H1_VT_RECORDED_60D": [b.time for b in _load_crypto("BTCUSD")[0]["H1"]],
    }
    for name, cal in calendars.items():
        origins = sorted({t for t in cal})
        divergent, lost_total, examples = 0, 0, []
        directions = Counter()
        for origin in origins:
            declared, dates = _declared_poi_expiry(origin, cal)
            if declared is None:
                continue
            engine = _engine_poi_expiry(origin)
            if declared == engine:
                continue
            divergent += 1
            direction = "ENGINE_EXPIRES_EARLIER" if engine < declared else "ENGINE_EXPIRES_LATER"
            directions[direction] += 1
            lost = [d for d in dates[:C.POI_MAX_AGE_TRADING_DAYS + 1] if _start_of_trading_date(d) >= engine]
            lost_total += len(lost)
            if len(examples) < 3:
                examples.append({"origin_utc": origin.isoformat(), "engine_expiry_utc": engine.isoformat(),
                                 "declared_expiry_utc": declared.isoformat(),
                                 "trading_dates_expired_early": [d.isoformat() for d in lost],
                                 "direction": direction})
        out[name] = {"calendar_instants": len(cal),
                     "distinct_trading_dates": len({W.trading_date(t) for t in cal}),
                     "origins_evaluated": len(origins), "origins_divergent": divergent,
                     "directions": _counts(directions),
                     "trading_dates_expired_early_total": lost_total, "examples": examples,
                     "verdict": FAIL if divergent else PASS}
    out["scope"] = ("FX instruments only: BTCUSD/ETHUSD trade every calendar date on this venue, so both "
                    "clocks coincide there (measured above). EURUSD/GBPUSD/USDJPY/XAUUSD lose trading-day "
                    "life whenever the FX weekend falls inside the 5-day window.")
    out["materiality"] = ("Conservative direction, MEASURED not assumed: every divergent origin on every "
                          "calendar is ENGINE_EXPIRES_EARLIER (see `directions`), because the trading-date "
                          "set is a subset of the calendar-date set, so six calendar boundaries land at or "
                          "before six trading dates. The engine therefore suppresses POI life -- it can drop "
                          "an opportunity or hold a state at NEAR_POI/DEVELOPING -- but it never keeps a POI "
                          "alive longer than the contract allows. No ENGINE_EXPIRES_LATER origin exists.")
    out["verdict"] = FAIL if any(v["verdict"] == FAIL for k, v in out.items() if isinstance(v, dict)
                                 and "verdict" in v and k not in ("dead_code",)) else PASS
    return out


def calendar_and_session_semantics() -> dict:
    """Day boundary across both 2026 US DST transitions, the weekend window, and session expiry."""
    dst = []
    for label, day in (("DST_START_2026-03-08", dt.date(2026, 3, 8)), ("DST_END_2026-11-01", dt.date(2026, 11, 1))):
        before = dt.datetime.combine(day - dt.timedelta(days=1), dt.time(21, 0), tzinfo=UTC)
        boundary = W.next_day_boundary(before)
        local = boundary.astimezone(NY)
        after = W.next_day_boundary(boundary)
        dst.append({"case": label, "boundary_utc": boundary.isoformat(),
                    "boundary_local": local.strftime("%H:%M %Z"),
                    "boundary_is_1700_local": local.hour == C.DAY_BOUNDARY_HOUR and local.minute == 0,
                    "next_boundary_utc": after.isoformat(),
                    "trading_day_length_hours": (after - boundary).total_seconds() / 3600,
                    "trading_date_before": W.trading_date(before).isoformat(),
                    "trading_date_at_boundary": W.trading_date(boundary).isoformat(),
                    "verdict": PASS if (local.hour == C.DAY_BOUNDARY_HOUR and local.minute == 0
                                        and W.trading_date(boundary) > W.trading_date(before)) else FAIL})
    weekend = []
    for label, t, want in (
            ("FRI_1659_NY_OPEN", dt.datetime(2026, 10, 9, 20, 59, tzinfo=UTC), False),
            ("FRI_1700_NY_CLOSED", dt.datetime(2026, 10, 9, 21, 0, tzinfo=UTC), True),
            ("SAT_NOON_CLOSED", dt.datetime(2026, 10, 10, 16, 0, tzinfo=UTC), True),
            ("SUN_1659_NY_CLOSED", dt.datetime(2026, 10, 11, 20, 59, tzinfo=UTC), True),
            ("SUN_1700_NY_OPEN", dt.datetime(2026, 10, 11, 21, 0, tzinfo=UTC), False)):
        got = W.fx_market_closed(t)
        weekend.append({"case": label, "utc": t.isoformat(), "local": t.astimezone(NY).strftime("%a %H:%M %Z"),
                        "closed_expected": want, "closed_measured": got, "verdict": PASS if got == want else FAIL})
    sessions = W._canonical_sessions()
    expiry = []
    for label, t, want_kind in (
            ("ASIAN_0300", dt.datetime(2026, 10, 13, 3, 0, tzinfo=UTC), "SESSION_END"),
            ("LONDON_AM_0930", dt.datetime(2026, 10, 13, 9, 30, tzinfo=UTC), "SESSION_END"),
            ("LONDON_AM_END_1100_HALF_OPEN", dt.datetime(2026, 10, 13, 11, 0, tzinfo=UTC), "NEXT_DAY_BOUNDARY"),
            ("GAP_1130", dt.datetime(2026, 10, 13, 11, 30, tzinfo=UTC), "NEXT_DAY_BOUNDARY"),
            ("NEW_YORK_AM_1300", dt.datetime(2026, 10, 13, 13, 0, tzinfo=UTC), "SESSION_END"),
            ("AFTER_1500_HALF_OPEN", dt.datetime(2026, 10, 13, 15, 0, tzinfo=UTC), "NEXT_DAY_BOUNDARY"),
            ("EVENING_2000", dt.datetime(2026, 10, 13, 20, 0, tzinfo=UTC), "NEXT_DAY_BOUNDARY")):
        got = W.session_end(t, sessions)
        want = (dt.datetime(2026, 10, 13, {  # canonical ends are fixed UTC clock times
            "ASIAN_0300": 6, "LONDON_AM_0930": 11, "NEW_YORK_AM_1300": 15}[label], 0, tzinfo=UTC)
            if want_kind == "SESSION_END" else W.next_day_boundary(t))
        expiry.append({"case": label, "utc": t.isoformat(), "expected_kind": want_kind,
                       "expected_utc": want.isoformat(), "measured_utc": got.isoformat(),
                       "verdict": PASS if got == want else FAIL})
    return {
        "canonical_sessions": [[n, f"{s // 60:02d}:{s % 60:02d}", f"{e // 60:02d}:{e % 60:02d}"]
                               for n, s, e in sessions],
        "session_gaps_utc": ["11:00-12:00", "15:00-24:00"],
        "gap_handling": "contract opportunity_expiry = SESSION_END; outside every session -> next NY 17:00 boundary",
        "day_boundary_dst": dst, "fx_weekend_window": weekend, "opportunity_expiry": expiry,
        "crypto_market_closed_bypass": {
            "rule": "watch.evaluate_snapshot skips the FX weekend check for contract.CRYPTO_SYMBOLS",
            "measured": {s: W.evaluate_snapshot(s, [], [], [], dt.datetime(2026, 10, 10, 16, 0, tzinfo=UTC)).state
                         for s in ("BTCUSD", "EURUSD")},
            "note": "a weekend crypto snapshot cannot be MARKET_CLOSED; it fails closed as STALE/DATA_ERROR instead",
            "verdict": PASS},
        "verdict": PASS if all(c["verdict"] == PASS for c in dst + weekend + expiry) else FAIL,
    }


def detection_semantics(lane_b_result: dict) -> dict:
    """Measured primitives on the host-captured FX fixture: tie tolerance, sweeps, windows, targets."""
    fx = load_fixture("EURUSD")
    h1, m5 = fx["H1"], fx["M5"]
    point, _src = C.resolve_point("EURUSD")
    tol = C.TIE_TOLERANCE_POINTS * point
    out = {"symbol": "EURUSD", "point": point, "tie_tolerance_price": tol,
           "tie_tolerance_rule": f"{C.TIE_TOLERANCE_POINTS} points x point size, per symbol"}

    # tie tolerance: a break must be strictly beyond the tolerance; a close inside it must not break
    h1_breaks = D.tolerant_breaks(h1, F.swings(h1, C.SWING_K), tol)
    strict_breaks = D.tolerant_breaks(h1, F.swings(h1, C.SWING_K), 0.0)
    near_misses = 0
    sw = F.swings(h1, C.SWING_K)
    for i, b in enumerate(h1):
        known = [s for s in sw if s.known_at <= i]
        for s in known[-4:]:
            if 0 < abs(b.close - s.price) <= tol:
                near_misses += 1
    out["h1_breaks"] = {"with_tolerance": len(h1_breaks), "without_tolerance": len(strict_breaks),
                        "suppressed_by_tolerance": len(strict_breaks) - len(h1_breaks),
                        "closes_within_tolerance_of_a_known_level": near_misses,
                        "every_break_strictly_beyond_tolerance": all(
                            abs(h1[i].close - br.level) > tol for br in h1_breaks for i in [br.index]),
                        "first_break_out_of_neutral_is_choch": (
                            h1_breaks[0].event == "CHoCH" if h1_breaks else None),
                        "event_counts": _counts(Counter(br.event for br in h1_breaks))}
    out["h1_breaks"]["verdict"] = PASS if (out["h1_breaks"]["every_break_strictly_beyond_tolerance"]
                                           and out["h1_breaks"]["first_break_out_of_neutral_is_choch"]) else FAIL

    # sweeps: wick beyond a swing KNOWN BEFORE the bar, close back inside (features.sweeps contract)
    m5_sw = F.swings(m5, C.SWING_K)
    sweeps = F.sweeps(m5, m5_sw)
    bad = []
    for s in sweeps:
        bar = m5[s.index]
        swing = next((x for x in m5_sw if x.index == s.swing_index), None)
        if swing is None or swing.known_at >= s.index:
            bad.append((s.index, "SWING_NOT_KNOWN_BEFORE_BAR"))
        elif s.direction == "bullish" and not (bar.low < swing.price < bar.close):
            bad.append((s.index, "BULLISH_GEOMETRY"))
        elif s.direction == "bearish" and not (bar.close < swing.price < bar.high):
            bad.append((s.index, "BEARISH_GEOMETRY"))
    out["m5_sweeps"] = {"count": len(sweeps), "violations": bad[:5], "violation_count": len(bad),
                        "directions": _counts(Counter(s.direction for s in sweeps)),
                        "swing_known_strictly_before_bar": not bad,
                        "verdict": PASS if not bad else FAIL}

    # opportunities: sweep -> CHoCH window, entry = CHoCH close, C11 target causality.
    # Recomputed from the primitives so the check is independent of the engine's own bookkeeping.
    windows, entries, targets = [], [], []
    closed_m5 = m5
    h1_pois = D.h1_pois("EURUSD", h1, h1_breaks)

    def valid_at(p, t):
        exp = _engine_poi_expiry(p.origin_time)
        return p.known_time <= t and (p.invalidated_time is None or t < p.invalidated_time) and t < exp

    recomputed = D.m5_opportunities(closed_m5, h1_pois, valid_at, tol)
    for op in recomputed:
        sweep_idx = next(i for i, b in enumerate(closed_m5) if b.time == op.sweep_time)
        windows.append(op.choch_index - sweep_idx)
        entries.append(op.entry_reference == closed_m5[op.choch_index].close)
        tgt = D.c11_causal_target(closed_m5, op.direction, op.entry_reference, len(closed_m5) - 1)
        targets.append({"opp": op.opp_id[:48], "engine_target_at_last_bar": tgt,
                        "beyond_entry": (tgt > op.entry_reference) if op.direction == "LONG"
                        else (tgt < op.entry_reference) if tgt is not None else None})
    out["opportunities_recomputed_from_primitives"] = {
        "count": len(recomputed),
        "sweep_to_choch_window_bars": _counts(Counter(windows)),
        "window_within_contract": all(0 < w <= C.SWEEP_TO_CHOCH_WINDOW_M5 for w in windows),
        "contract_window": C.SWEEP_TO_CHOCH_WINDOW_M5,
        "entry_equals_choch_bar_close_all": all(entries),
        "c11_targets_beyond_entry": all(t["beyond_entry"] for t in targets if t["beyond_entry"] is not None),
        "c11_target_examples": targets[:3],
        "verdict": PASS if (all(0 < w <= C.SWEEP_TO_CHOCH_WINDOW_M5 for w in windows) and all(entries)
                            and all(t["beyond_entry"] for t in targets if t["beyond_entry"] is not None)) else FAIL}
    out["verdict"] = PASS if all(out[k]["verdict"] == PASS for k in
                                ("h1_breaks", "m5_sweeps", "opportunities_recomputed_from_primitives")) else FAIL
    return out


def causality_properties(symbol: str = "EURUSD", samples: int = 12) -> dict:
    """Look-ahead tests stronger than the shipped L1 truncation check."""
    fx = load_fixture(symbol)
    d1, h1, m5 = fx["D1"], fx["H1"], fx["M5"]
    rng = random.Random(20261013)   # fixed seed: the perturbation is reproducible
    picked, i = [], 0
    while len(picked) < samples and i < len(m5):
        now = m5[i].time + dt.timedelta(minutes=C.TIMEFRAME_MINUTES["M5"])
        if (len([b for b in h1 if D.close_time(b, C.TIMEFRAME_MINUTES["H1"]) <= now]) >= C.MIN_H1_BARS
                and i + 1 >= C.MIN_M5_BARS):
            picked.append((i, now))
        i += max(1, len(m5) // samples)
    rows = []
    for i, now in picked:
        d1w, h1w, m5w = window(d1, "D1", now), window(h1, "H1", now), window(m5, "M5", now)
        base = G._payload(W.evaluate_snapshot(symbol, d1w, h1w, m5w, now))
        truncated = G._payload(W.evaluate_snapshot(
            symbol, [b for b in d1w if D.close_time(b, C.TIMEFRAME_MINUTES["D1"]) <= now],
            [b for b in h1w if D.close_time(b, C.TIMEFRAME_MINUTES["H1"]) <= now],
            [b for b in m5w if D.close_time(b, C.TIMEFRAME_MINUTES["M5"]) <= now], now))
        mutated = []
        for bars, minutes in ((d1w, C.TIMEFRAME_MINUTES["D1"]), (h1w, C.TIMEFRAME_MINUTES["H1"]),
                              (m5w, C.TIMEFRAME_MINUTES["M5"])):
            for b in bars:
                if D.close_time(b, minutes) > now:      # the forming bar and anything after it
                    mutated.append(Candle(b.time, b.close * 1.5, b.high * 2.0, b.low * 0.5,
                                          rng.uniform(b.low, b.high) * 1.1, b.volume))
                else:
                    mutated.append(b)
        # rebuild the three windows with mutated future bars, in the same order
        mut_d1, mut_h1, mut_m5 = mutated[:len(d1w)], mutated[len(d1w):len(d1w) + len(h1w)], \
            mutated[len(d1w) + len(h1w):]
        perturbed = G._payload(W.evaluate_snapshot(symbol, mut_d1, mut_h1, mut_m5, now))
        extended = G._payload(W.evaluate_snapshot(symbol, d1, h1, m5[:min(len(m5), i + 40)], now))
        rows.append({"scan_utc": now.isoformat(), "state": base["state"],
                     "replay_hash_stable": payload_hash(base) == payload_hash(
                         G._payload(W.evaluate_snapshot(symbol, d1w, h1w, m5w, now))),
                     "truncation_invariant": base == truncated,
                     "future_mutation_invariant": base == perturbed,
                     "future_bars_do_not_change_output": base == extended,
                     "forming_bars_present_in_input": sum(
                         1 for b in m5w if D.close_time(b, C.TIMEFRAME_MINUTES["M5"]) > now)})
    return {
        "symbol": symbol, "samples": len(rows),
        "tests": {"L1.replay_hash (determinism)": all(r["replay_hash_stable"] for r in rows),
                  "truncation_invariance (unclosed bars dropped)": all(r["truncation_invariant"] for r in rows),
                  "future_mutation_invariance (forming/future OHLC rewritten)": all(
                      r["future_mutation_invariant"] for r in rows),
                  "future_bars_appended_do_not_change_output": all(
                      r["future_bars_do_not_change_output"] for r in rows)},
        "forming_bars_in_input_range": [min(r["forming_bars_present_in_input"] for r in rows),
                                        max(r["forming_bars_present_in_input"] for r in rows)],
        "rows": rows,
        "verdict": PASS if all(all(v for v in r.values() if isinstance(v, bool)) for r in rows) else FAIL,
    }


def window_sensitivity(symbol: str = "EURUSD") -> dict:
    """Disclosure: the snapshot depends on the rolling window length the host supplies."""
    fx = load_fixture(symbol)
    d1, h1, m5 = fx["D1"], fx["H1"], fx["M5"]
    now = dt.datetime.fromisoformat(decision_time_utc().replace("Z", "+00:00"))
    rows = []
    for label, counts in (("host_D1_30_H1_200_M5_300", HOST_COUNTS),
                          ("half_D1_15_H1_100_M5_150", {"D1": 15, "H1": 100, "M5": 150}),
                          ("all_available_bars", {"D1": len(d1), "H1": len(h1), "M5": len(m5)})):
        snap = W.evaluate_snapshot(symbol, window(d1, "D1", now, counts), window(h1, "H1", now, counts),
                                   window(m5, "M5", now, counts), now)
        rows.append({"window": label, "bars": {tf: len(window(v, tf, now, counts)) for tf, v in
                                                (("D1", d1), ("H1", h1), ("M5", m5))},
                     "state": snap.state, "bias": snap.bias, "d1_context": snap.d1_context,
                     "poi_id": (snap.poi or {}).get("poi_id"),
                     "opportunity": (snap.opportunity or {}).get("opp_id")})
    same = len({(r["state"], r["bias"], r["poi_id"], r["opportunity"]) for r in rows}) == 1
    return {"symbol": symbol, "evaluated_at_utc": now.isoformat(), "rows": rows,
            "identical_across_windows": same,
            "verdict": PASS,
            "note": ("Recorded, not gated: bias/POI/opportunity are window-dependent by construction (the host "
                     "supplies fixed rolling counts). C15/C16 report the same effect as separate short_d1 and "
                     "full_d1 lanes; a shorter D1/H1 window can change which POI or opportunity is selected.")}


def fail_closed_metadata() -> dict:
    """resolve_point has no repo constant and no caller fallback: missing/malformed/mismatch -> DATA_ERROR."""
    rows = []
    good = json.loads((ROOT / "config/symbol_metadata/host_captured/EURUSD.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "config/symbol_metadata/host_captured/EURUSD.json"
        target.parent.mkdir(parents=True)
        cases = [("MISSING_FILE", None), ("MALFORMED_JSON", "{not json"),
                 ("HASH_MISMATCH", json.dumps({**good, "fields": {**good["fields"], "point": 0.0002}})),
                 ("WRONG_SCHEMA", json.dumps({**good, "schema": "SOMETHING_ELSE"}))]
        for label, content in cases:
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(content, encoding="utf-8")
            os.environ["AG_EVIDENCE_ROOT"] = str(root)
            try:
                point, source = C.resolve_point("EURUSD")
                snap = W.evaluate_snapshot("EURUSD", [], [], [], dt.datetime(2026, 10, 13, 9, 0, tzinfo=UTC))
                rows.append({"case": label, "point": point, "metadata_source": source,
                             "snapshot_state": snap.state, "snapshot_reasons": list(snap.reason_codes),
                             "verdict": PASS if point is None and source == C.METADATA_MISSING else FAIL})
            finally:
                os.environ["AG_EVIDENCE_ROOT"] = str(ROOT)
        # and the positive control: the committed capture resolves.  EURUSD is quoted to 5
        # decimals, so the broker *point* is 1e-05 while the evidenced C10 *pip* is 0.0001
        # (exactly 10 points).  Both relations are asserted: the first proves the capture is
        # read, the second proves the pip the C10 policy spends is the quoted pip.
        point, source = C.resolve_point("EURUSD")
        pip_ok = "EURUSD" in C.C10_PIP_SIZE and C.C10_PIP_SIZE["EURUSD"] == point * 10
        rows.append({"case": "COMMITTED_CAPTURE", "point": point, "metadata_source": source,
                     "c10_pip_size": C.C10_PIP_SIZE.get("EURUSD"),
                     "c10_pip_is_10_points": pip_ok,
                     "snapshot_state": None, "snapshot_reasons": [],
                     "verdict": PASS if point == 1e-05 and source == "HOST_CAPTURED" and pip_ok else FAIL})
    per_symbol = {}
    for s in C.V1_SYMBOLS:
        p, src = C.resolve_point(s)
        per_symbol[s] = {"point": p, "source": src, "c10_pip_evidenced": s in C.C10_PIP_SIZE}
    return {"rows": rows, "per_symbol_point_resolution": per_symbol,
            "c10_pip_evidenced_symbols": sorted(C.C10_PIP_SIZE),
            "c10_not_evaluable_symbols": sorted(set(C.V1_SYMBOLS) - set(C.C10_PIP_SIZE)),
            "verdict": PASS if all(r["verdict"] == PASS for r in rows) else FAIL}


def archive_only_exactly_once() -> dict:
    """ARCHIVE_ONLY: transitions archive once, a duplicate poll or a crash-between is a no-op."""
    fx = load_fixture("EURUSD")
    d1, h1, m5 = fx["D1"], fx["H1"], fx["M5"]
    now = dt.datetime.fromisoformat(decision_time_utc().replace("Z", "+00:00"))
    snap = W.evaluate_snapshot("EURUSD", window(d1, "D1", now), window(h1, "H1", now),
                               window(m5, "M5", now), now)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        state, archive = str(Path(tmp) / "state.json"), str(Path(tmp) / "archive")
        tracker = W.WatchTracker(state, archive)
        first = tracker.poll(snap)
        files1 = sorted(str(p.relative_to(archive)) for p in Path(archive).rglob("*.json"))
        second = tracker.poll(snap)                      # duplicate poll on identical data
        files2 = sorted(str(p.relative_to(archive)) for p in Path(archive).rglob("*.json"))
        rows.append({"step": "duplicate_poll_on_identical_snapshot", "events": len(second),
                     "archive_files_before": len(files1), "archive_files_after": len(files2),
                     "verdict": PASS if not second and files1 == files2 else FAIL})
        # watch._emit computes the exactly-once guard path itself
        # (`archive_path(_report_type(strategy, symbol, f"LSMC_WATCH-{tid}"), trading_date, root)`).
        # If that ever diverged from where archive_cycle_decision writes, the guard would never see
        # the file and every restart would re-archive the same transition. Check the two agree.
        expected = sorted(str(Path(archive_path(
            _report_type(C.STRATEGY_ID, e.symbol, f"LSMC_WATCH-{e.transition_id}"),
            dt.date.fromisoformat(e.trading_date), archive)).relative_to(archive)) for e in first)
        rows.append({"step": "archive_path_matches_the_exactly_once_guard", "events": len(first),
                     "guard_paths": expected, "archived_files": files1,
                     "verdict": (PASS if expected == files1 else FAIL) if first else NOT_APPLICABLE,
                     "note": None if first else "the decision-time snapshot emitted no transition"})
        # crash between archive and state save: the archive file exists, the tracker state does not
        if first:
            Path(state).unlink(missing_ok=True)
            replayed = W.WatchTracker(state, archive).poll(snap)
            files3 = sorted(str(p.relative_to(archive)) for p in Path(archive).rglob("*.json"))
            ids1 = [e.transition_id for e in first]
            ids3 = [e.transition_id for e in replayed]
            rows.append({"step": "restart_after_crash_between_archive_and_state_save",
                         "transition_ids_identical": ids1 == ids3,
                         "archive_files_before": len(files2), "archive_files_after": len(files3),
                         "archive_not_rewritten": files2 == files3,
                         "verdict": PASS if ids1 == ids3 and files2 == files3 else FAIL})
        else:
            rows.append({"step": "restart_after_crash_between_archive_and_state_save",
                         "note": "the decision-time snapshot emitted no transition, so this step is not "
                                 "exercisable on this fixture", "verdict": NOT_APPLICABLE})
        # stale -> suspend -> expire (contract rules.stale = SUSPEND_THEN_EXPIRE)
        stale = dataclasses.replace(snap, state="STALE", reason_codes=("M5_DATA_STALE",),
                                    evaluated_at=(now + dt.timedelta(minutes=20)).isoformat())
        events = tracker.poll(stale)
        saved = json.loads(Path(state).read_text(encoding="utf-8"))["EURUSD"]
        rows.append({"step": "stale_while_active_suspends_without_an_event", "events": len(events),
                     "saved_state": saved.get("state"), "suspended_from": saved.get("suspended_from"),
                     "verdict": PASS if not events and saved.get("state") == "SUSPENDED" else FAIL})
        expired = dataclasses.replace(stale, evaluated_at=(now + dt.timedelta(days=2)).isoformat())
        events = tracker.poll(expired)
        rows.append({"step": "suspended_past_expiry_emits_expired", "events": len(events),
                     "to_states": [e.to_state for e in events], "alert_levels": [e.alert_level for e in events],
                     "verdict": PASS if [e.to_state for e in events] == ["EXPIRED"]
                     and [e.alert_level for e in events] == [C.ALERT_LEVEL["EXPIRED"]] else FAIL})
        # MARKET_CLOSED emits nothing and does not disturb the saved state
        closed = dataclasses.replace(snap, state="MARKET_CLOSED", reason_codes=("FX_WEEKEND",))
        before = json.loads(Path(state).read_text(encoding="utf-8"))["EURUSD"]
        events = tracker.poll(closed)
        after = json.loads(Path(state).read_text(encoding="utf-8"))["EURUSD"]
        rows.append({"step": "market_closed_emits_nothing_and_preserves_state", "events": len(events),
                     "state_unchanged": before == after,
                     "verdict": PASS if not events and before == after else FAIL})
    evaluated = [r for r in rows if r["verdict"] != NOT_APPLICABLE]
    return {"decision_time_snapshot_state": snap.state, "rows": rows,
            "rows_evaluated": len(evaluated), "rows_not_applicable": len(rows) - len(evaluated),
            "alert_level_mapping_matches_contract": C.ALERT_LEVEL == yaml.safe_load(
                G.CONTRACT_PATH.read_text(encoding="utf-8"))["alerts"]["mapping"],
            "rejected_is_not_a_contract_alert_state": "REJECTED" not in C.ALERT_LEVEL,
            "rejected_alert_level_used": "INFO (watch.WatchTracker._emit special case)",
            "verdict": PASS if evaluated and all(r["verdict"] == PASS for r in evaluated) else FAIL}


TRANSPORT_DENY = ("telegram", "requests", "httpx", "aiohttp", "urllib", "smtplib", "socket", "fastapi",
                  "uvicorn", "execution", "trade_management", "authorization", "owner_decision", "svos",
                  "notifications", "api", "mt5.management_gateway")
BROKER_API_IMPORTS = ("MetaTrader5",)
# Modules whose file sha256 this report pins: the traversal MUST reach them, or the boundary
# check is vacuous (the exact defect class this audit was called for).
BOUNDARY_POSITIVE_CONTROL = ("large_smc_watch.contract", "large_smc_watch.detect", "large_smc_watch.watch",
                             "fx_discovery.features", "large_smc_core.c10_stop_policy")


def _repo_module_file(name: str):
    """`src/<dotted>.py` or `src/<dotted>/__init__.py`, else None (stdlib / third-party)."""
    if not name:
        return None
    rel = Path("src", *name.split("."))
    for cand in (ROOT / rel.with_suffix(".py"), ROOT / rel / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _resolve_from_import(current: str, is_init: bool, level: int, module: str) -> str:
    """Absolute name for an `ast.ImportFrom`, resolving relative imports against the package."""
    if level == 0:
        return module or ""
    base = current if is_init else current.rpartition(".")[0]
    for _ in range(level - 1):
        base = base.rpartition(".")[0]
    return f"{base}.{module}" if module else base


def _static_import_graph(roots=("large_smc_watch",)) -> dict:
    """Transitive import graph over REPO modules only.

    Third-party and stdlib imports are leaves: they are recorded, not traversed, because the
    boundary claim is about this repository's own code, not about what pandas does internally.
    Relative imports are resolved, so an eager `from .analyzer import ...` in a package
    `__init__.py` is followed exactly as the interpreter follows it.
    """
    seen: set = set()
    transport_hits, broker_hits, external, unresolved = [], [], set(), set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        path = _repo_module_file(name)
        if path is None:
            unresolved.add(name)
            continue
        is_init = path.name == "__init__.py"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, ValueError):
            unresolved.add(f"{name} (unparseable)")
            continue
        for node in ast.walk(tree):
            names, aliases = [], []
            if isinstance(node, ast.Import):
                names = [(a.name, node.lineno) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_from_import(name, is_init, node.level, node.module or "")
                names = [(base, node.lineno)]
                # `from pkg import submodule as X` -- the submodule is part of the closure too.
                aliases = [f"{base}.{a.name}" for a in node.names] if base else []
            for candidate in aliases:
                if _repo_module_file(candidate) is not None:
                    stack.append(candidate)
            for mod, lineno in names:
                if not mod:
                    continue
                top = mod.split(".")[0]
                record = {"module": name, "file": str(path.relative_to(ROOT)), "line": lineno, "import": mod}
                if any(mod == d or mod.startswith(d + ".") for d in TRANSPORT_DENY):
                    transport_hits.append(record)
                if any(mod == d or mod.startswith(d + ".") for d in BROKER_API_IMPORTS):
                    broker_hits.append(record)
                if _repo_module_file(mod) is not None:
                    stack.append(mod)
                elif _repo_module_file(top) is not None:
                    stack.append(top)
                    external.add(mod)      # a submodule reached through its package root
                else:
                    external.add(top)
    missing_control = sorted(m for m in BOUNDARY_POSITIVE_CONTROL if m not in seen)
    return {"repo_modules_reachable": len(seen),
            "repo_modules": sorted(seen),
            "positive_control_reached": not missing_control,
            "positive_control_missing": missing_control,
            "transport_deny_hits": transport_hits,
            "broker_api_imports": broker_hits,
            "external_roots": sorted(external),
            "unresolved": sorted(unresolved)}


def _runtime_import_probe() -> dict:
    """What `import large_smc_watch` actually loads, measured in a clean subprocess."""
    probe = (
        "import importlib.util, json, sys;"
        "sys.path[:0]=['.', 'src', 'tests'];"
        "_s=importlib.util.spec_from_file_location('ct','tests/conftest.py');"
        "_m=importlib.util.module_from_spec(_s); _s.loader.exec_module(_m);"
        "_shim='MetaTrader5' in sys.modules;"
        "_before=set(sys.modules);"
        "import large_smc_watch, large_smc_watch.contract, large_smc_watch.detect, large_smc_watch.watch;"
        "_loaded=sorted(set(sys.modules)-_before);"
        f"_deny={json.dumps(sorted(set(TRANSPORT_DENY)))};"
        "print(json.dumps({"
        "'modules_loaded_by_import': len(_loaded),"
        "'mt5_stub_installed_by_conftest': _shim,"
        "'mt5_modules_loaded': [m for m in _loaded if m == 'MetaTrader5' or m.split('.')[0] == 'mt5'],"
        "'transport_deny_loaded': [m for m in _loaded if m.split('.')[0] in _deny],"
        "'socket_loaded': 'socket' in sys.modules}))"
    )
    proc = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT), capture_output=True, text=True,
                          timeout=300, check=False)
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("{")), None)
    if line is None:
        return {"error": (proc.stderr or proc.stdout)[-800:], "verdict": FAIL}
    out = json.loads(line)
    # `socket` is pulled in by pandas/numba themselves, not by repo code (the same exemption
    # tests/test_v1_large_smc_import_boundary.py documents); it is checked statically above.
    out["transport_deny_loaded_excluding_stdlib_socket"] = [
        m for m in out["transport_deny_loaded"] if m.split(".")[0] != "socket"]
    return out


def no_transport_boundary() -> dict:
    """ARCHIVE_ONLY boundary: no transport, order, executor or notification path is reachable."""
    static = _static_import_graph()
    runtime = _runtime_import_probe()
    reasons = []
    if static["transport_deny_hits"]:
        reasons.append(f"{len(static['transport_deny_hits'])} repo module(s) in the closure import a "
                       "transport/executor/authorization module")
    if not static["positive_control_reached"]:
        reasons.append("the traversal did not reach " + ", ".join(static["positive_control_missing"])
                       + ": the boundary check would be vacuous")
    if runtime.get("transport_deny_loaded_excluding_stdlib_socket"):
        reasons.append("runtime import loads " + ", ".join(runtime["transport_deny_loaded_excluding_stdlib_socket"]))
    if W.DELIVERY_MODE != "ARCHIVE_ONLY":
        reasons.append(f"delivery_mode is {W.DELIVERY_MODE}")
    if C.PROPOSAL_GENERATION_AUTHORIZED is not False:
        reasons.append("proposal_generation_authorized is not False")
    return {
        "scope": ("static transitive import graph over REPO modules reachable from large_smc_watch "
                  "(third-party/stdlib are leaves) + a clean-subprocess runtime import probe"),
        "static": {k: v for k, v in static.items() if k != "repo_modules"},
        "runtime": runtime,
        "broker_api_observation": (
            "RECORDED, NOT GATED: the closure does reach the MT5 broker-API modules. "
            + " -> ".join(sorted({h["file"] for h in static["broker_api_imports"]}))
            + " import MetaTrader5 unconditionally, and they are pulled in by the eager re-exports in "
              "supply_demand/__init__.py and market_structure/__init__.py, which "
              "large_smc_watch.detect triggers via `from supply_demand.ob_config import ...`. No LSMC module "
              "calls MT5 (tests/test_v1_large_smc_import_boundary.py asserts no order_send/order_check/"
              "positions_get/position_close and exempts MetaTrader5 from its runtime check by design; "
              "tests/conftest.py documents the same chain and installs an import-only Linux stub). "
              "Consequence: the ARCHIVE_ONLY alert engine is not import-independent of the broker API "
              "package -- off-host it is importable only through that stub. See D-LSMC-10."),
        "delivery_mode": W.DELIVERY_MODE,
        "proposal_generation_authorized": C.PROPOSAL_GENERATION_AUTHORIZED,
        "verdict": PASS if not reasons else FAIL,
        "verdict_reasons": reasons,
    }


def harness_regression() -> dict:
    """Pin the two harness defects found 2026-10-13 so neither can return silently."""
    spec = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))
    case = HARNESS.cases()[0]                       # v110_synthetic:EURUSD:OPPORTUNITY
    res = G.evaluate_case(spec, case)
    verdicts = {c["id"]: c["verdict"] for g in res["gates"].values() for c in g["checks"]}
    opportunity_checks = ("L2.direction_matches_bias", "L2.entry_by_reference", "L2.sweep_window_measured",
                          "L2.expiry_session_end", "L2.c10_stop", "L2.c11_target", "L3.entry_in_choch_bar",
                          "L3.sweep_extreme_side", "L6.valid_until")
    gated = res["state"] == "REJECTED" and res["signal_state"] == "OPPORTUNITY"
    weekend = {"case_id": "weekend", "symbol": "EURUSD", "now": dt.datetime(2026, 10, 10, 16, 0, tzinfo=UTC),
               "fixture": "synthetic", "classification": "SYNTHETIC",
               "D1": case["D1"], "H1": case["H1"], "M5": case["M5"]}
    wk = G.evaluate_case(spec, weekend)
    wk_verdicts = {c["id"]: c["verdict"] for c in wk["gates"]["L2"]["checks"]}
    # The fixture guard is exercised, not asserted: a divergent evaluation time must raise,
    # and the message must name the manifest decision time so the failure is self-explaining.
    raised, message = False, ""
    try:
        check_decision_time("EURUSD", "2026-10-10T19:45:53.895829Z")   # the pre-correction value
    except ValueError as exc:
        raised, message = True, str(exc)
    guard_ok = raised and decision_time_utc() in message
    accepted = True
    try:
        check_decision_time("EURUSD", decision_time_utc())
    except ValueError as exc:                                    # pragma: no cover - would be a guard defect
        accepted, message = False, str(exc)
    out = {
        "delivery_gate_does_not_blank_the_opportunity_rules": {
            "shipped_state": res["state"], "signal_state": res["signal_state"],
            "opportunity_checks_evaluated": all(verdicts[c] != NOT_APPLICABLE for c in opportunity_checks),
            "opportunity_check_verdicts": {c: verdicts[c] for c in opportunity_checks},
            "verdict": PASS if gated and all(verdicts[c] != NOT_APPLICABLE for c in opportunity_checks) else FAIL},
        "short_circuit_is_not_reported_as_a_point_source_failure": {
            "state": wk["state"], "reason_codes": wk["reason_codes"],
            "L2.point_source": wk_verdicts["L2.point_source"],
            "L2.point_source_declared": wk_verdicts["L2.point_source_declared"],
            "L4.evaluated": sorted({c["verdict"] for c in wk["gates"]["L4"]["checks"]
                                    if c["id"] == "L4.evaluated"}),
            "blocking_failures": wk["blocking_failures"],
            "verdict": PASS if (wk_verdicts["L2.point_source"] == NOT_APPLICABLE
                                and wk_verdicts["L2.point_source_declared"] == PASS
                                and "L4" in wk["blocking_failures"] and "L2" not in wk["blocking_failures"]) else FAIL},
        "fixture_decision_time_guard": {
            "manifest_decision_time_utc": decision_time_utc(),
            "guard": "tests/_lsmc_v111_fixtures.check_decision_time, called from load_fixture",
            "divergent_time_raises": raised,
            "message_names_manifest_time": bool(raised) and decision_time_utc() in message,
            "conformant_time_accepted": accepted,
            "error_message": message if (raised or not accepted) else None,
            "verdict": PASS if guard_ok and accepted else FAIL},
    }
    out["verdict"] = PASS if all(v["verdict"] == PASS for v in out.values()
                                 if isinstance(v, dict) and "verdict" in v) else FAIL
    return out


# --------------------------------------------------------------------------- report

CANDIDATE_1_1_1_PATH = ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml"
# Preserve the pre-D2 candidate input for the legacy audit and its historical 15-path output.
# --version 1.1.2 dispatches to the current candidate contract instead.
CANDIDATE_1_1_2_PATH = ROOT / "tests/fixtures/c21/v112_pre_d2.yaml"


def _spec_diff(old, new, path: str = "") -> list:
    """Structural diff of two parsed contracts, as sorted dotted paths.

    A new or removed subtree is reported once at its own path (not expanded); a list is reported
    once at its path when its length or any element differs. Byte-level-only edits (a duplicated
    mapping key, comments, whitespace) do not appear, which is what makes the candidate's
    `parsed_structure_changed: false` claim checkable instead of asserted.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for key in sorted(set(old) | set(new)):
            child = f"{path}.{key}" if path else str(key)
            if key not in old or key not in new:
                out.append(child)
            else:
                out.extend(_spec_diff(old[key], new[key], child))
        return out
    if isinstance(old, list) and isinstance(new, list):
        return [] if old == new else [path]
    return [] if old == new else [path]


def candidate_rule_change_diff() -> dict:
    """AGP-C17 Phase B.5: the 1.1.2 candidate's rule-change diff, checked against its own claim.

    The frozen 1.1.0 contract and engine are not edited; the correction for a genuine strategy
    defect is prepared as a new candidate version with an explicit diff. This check proves the
    candidate contains exactly the diff it declares -- no undeclared rule drift, and no change to
    any authority surface.
    """
    v110 = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))
    v111 = yaml.safe_load(CANDIDATE_1_1_1_PATH.read_text(encoding="utf-8"))
    v112 = yaml.safe_load(CANDIDATE_1_1_2_PATH.read_text(encoding="utf-8"))
    block = v112["candidate_rule_changes"]
    declared = sorted(block["declared_diff_paths"])
    computed = sorted(_spec_diff(v111, v112))
    poi110, poi112 = v110["rules"]["poi"], v112["rules"]["poi"]
    checks = {
        "declared_diff_paths_match_the_computed_structural_diff": declared == computed,
        "candidate_is_bound_to_the_committed_1_1_1_bytes": (
            v112["based_on_sha256"] == sha256(CANDIDATE_1_1_1_PATH)
            and v112["based_on"] == "strategies/ST_LARGE_SMC_V1_1_1_1.yaml"),
        "frozen_1_1_0_contract_bytes_unchanged": (
            sha256(G.CONTRACT_PATH) == block["frozen_versions_untouched"][0]["sha256"]
            == identity()["contract_sha256"]),
        "frozen_1_1_0_engine_bytes_unchanged": G.engine_sha256() == identity()["engine_sha256"],
        "declared_number_is_unchanged": poi112["max_age_trading_days"] == poi110["max_age_trading_days"] == 5,
        "unit_is_now_explicit": poi112["max_age_unit"] == "DISTINCT_NY1700_TRADING_DATES"
                                and "max_age_unit" not in poi110 and "max_age_unit" not in v111["rules"]["poi"],
        "declared_unit_matches_the_dead_helper_semantics": (
            poi112["weekend_and_holiday_dates_excluded"] is True
            and _declared_poi_expiry_is_trading_date_based()),
        "duplicate_timeframes_key_was_byte_level_only": v111["timeframes"] == v112["timeframes"],
        "authority_surfaces_stay_false_in_the_candidate": all(
            v112[k] is False for k in ("registered", "active", "proposal_generation_authorized",
                                       "demo_authorized", "live_authorized"))
            and v112["implementation"] == "SPEC_ONLY_NOT_WIRED"
            and v112["economic_status"] == "NOT_EVALUATED"
            and v112["status"] == "CANDIDATE_PENDING_OWNER_CONFIRM",
        "candidate_is_not_registered_in_the_registry": (
            C.STRATEGY_VERSION in _registry_lsmc_versions()          # positive control, not vacuity
            and _registry_lsmc_entry()["config_source"] == "strategies/ST_LARGE_SMC_V1_1_1_0.yaml"
            and not {"1.1.1", "1.1.2"} & set(_registry_lsmc_versions())),
        "no_gate_is_weakened_and_no_emission_is_suppressed": (
            v112["alerts"] == v111["alerts"] == v110["alerts"]
            and v112["candidate_gates"] == v111["candidate_gates"]),
        "d_lsmc_1_carries_no_rule_change": next(
            c for c in block["changes"] if c["id"] == "C17-D-LSMC-1-NOT-A-RULE-CHANGE")["change"] == "none",
    }
    reasons = [k for k, ok in checks.items() if not ok]
    return {
        "verdict": PASS if not reasons else FAIL,
        "verdict_reasons": reasons,
        "candidate_contract": "strategies/ST_LARGE_SMC_V1_1_1_2.yaml",
        "candidate_contract_sha256": sha256(CANDIDATE_1_1_2_PATH),
        "based_on_candidate_sha256": v112["based_on_sha256"],
        "computed_structural_diff_1_1_1_to_1_1_2": computed,
        "declared_diff_paths": declared,
        "undeclared_rule_drift": sorted(set(computed) - set(declared)),
        "stale_declared_paths": sorted(set(declared) - set(computed)),
        "changes": [{k: c[k] for k in ("id", "defect", "defect_class", "gate", "number_changed",
                                       "unit_changed", "owner_decision_required")
                     if k in c} for c in block["changes"]],
        "checks": checks,
        "note": ("Phase B classification: D-LSMC-6 = implementation defect against a declared "
                 "contract rule (route: this candidate + owner confirmation + a fresh L1-L6 replay); "
                 "D-LSMC-1 = metadata defect, missing owner-confirmed broker pip evidence (route: "
                 "confirm 1.1.1's pip_size_rules proposals and capture the four missing symbols -- "
                 "never invent a pip size); D-LSMC-7/8 = verification-harness defects, already fixed "
                 "in this PR with the engine untouched; D-LSMC-3/5/9/10 = evidence/owner-decision "
                 "items, unfixable off-host."),
    }


def _declared_poi_expiry_is_trading_date_based() -> bool:
    """Positive control for the unit claim: the declared rule excludes weekend dates."""
    calendar = _synthetic_fx_calendar(weeks=2)
    origin = calendar[0]
    expiry, chain = _declared_poi_expiry(origin, calendar)
    engine = _engine_poi_expiry(origin)
    return bool(chain) and expiry is not None and all(d.weekday() < 5 for d in chain[:6]) and expiry > engine


PRE_FIX_HARNESS_BASELINE = {
    # Recorded from the pre-fix run of the same 18 cases inside this PR. It is not recomputable in
    # this checkout (the repository was delivered as a single squashed commit, so there is no
    # history to diff against); the numbers are the D-LSMC-7/D-LSMC-8 evidence.
    "checks_evaluated": 541, "checks_not_applicable": 79,
    "opportunity_rule_checks_exercised": 0, "check_verdicts_changed_by_the_fix": 156,
    "eurusd_fixture_sha256": "b5e1e524e1b912d15032650881edb000906d6d875657332be90fa3997a191c11",
}
OPPORTUNITY_RULE_PREFIXES = ("L2.direction", "L2.entry", "L2.sweep_window", "L2.expiry", "L2.c10", "L2.c11")
OPPORTUNITY_RULE_PREFIXES_CHECKS = ("L2.c10_stop", "L2.c11_target", "L2.direction_matches_bias",
                                    "L2.entry_by_reference", "L2.expiry_session_end", "L2.sweep_window_measured")
C17_DEFECT_CLASSES = ("IMPLEMENTATION", "STRATEGY_CONTRACT", "DATA", "METADATA", "VERIFICATION_HARNESS")


def gate_integrity(a: dict, b: dict, c: dict, props: dict, findings: list) -> dict:
    """Phase B.7: prove no fix in this PR hides a failure by suppressing an emission or weakening a gate.

    Every row is computed from this run, not asserted: the blocking gate set is read from the gate
    module, coverage is read from the lanes, emissions are counted, and the archive lane supplies
    the exactly-once evidence.
    """
    cov_a = a["check_coverage"]
    # Lanes A and B carry per-check verdict counts; lane C deliberately stores coverage without them.
    cov_full = {"A_fixture_harness": cov_a, "B_eurusd_host_captured_replay": b["check_coverage"]}
    lanes_cov = dict(cov_full)
    lanes_cov.update({f"C_{sym}": c[sym]["check_coverage"] for sym in C.CRYPTO_SYMBOLS if sym in c})
    l5_counts = {}
    for cov in cov_full.values():
        for key, statuses in cov["check_verdict_counts"].items():
            if key.startswith("L5."):
                agg = l5_counts.setdefault(key, Counter())
                for status, n in statuses.items():
                    agg[status] += n
    l5_warn = sum(v.get(WARN, 0) for v in l5_counts.values())
    counts = cov_a["check_verdict_counts"]
    opp_checks = sorted(k for k in counts if k.startswith(OPPORTUNITY_RULE_PREFIXES))
    opp_exercised = sum(1 for k in opp_checks if counts[k].get(PASS))
    archive = props["archive_only_exactly_once"]
    archive_rows = {r["step"]: r for r in archive["rows"]}
    emitted = archive_rows["archive_path_matches_the_exactly_once_guard"]["events"]
    shipped_nonempty = {
        "A": sum(a["states"]["shipped"].values()),
        "B": sum(b["states_shipped"].values()),
        **{f"C_{sym}": sum(c[sym]["states_shipped"].values()) for sym in C.CRYPTO_SYMBOLS if sym in c},
    }
    spec_alerts = yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))["alerts"]["mapping"]
    checks = {
        "blocking_gate_set_is_unchanged": G.BLOCKING == ("L1", "L2", "L3", "L4"),
        # L5 must keep being emitted as WARN: it may never block (that would be a stronger gate than
        # OD1011-L5 signed) and it may never PASS (that would be invented spread/commission evidence).
        "l5_stays_advisory_and_is_never_silently_dropped": (
            bool(l5_counts) and l5_warn > 0
            and not any(v.get(FAIL) or v.get(PASS) for v in l5_counts.values())),
        "no_declared_check_is_never_exercised_where_the_rules_are_reachable": all(
            not lanes_cov[k]["never_exercised_checks"] for k in ("A_fixture_harness",
                                                                 "B_eurusd_host_captured_replay",
                                                                 "C_ETHUSD") if k in lanes_cov),
        # Lane C on BTCUSD legitimately never reaches an opportunity in its bounded window, so six
        # opportunity checks are NOT_APPLICABLE there. That is a disclosed coverage gap (D-LSMC-9),
        # not a suppression: it must be counted, reported per lane and carried by a finding.
        "every_coverage_gap_is_disclosed_not_hidden": all(
            lanes_cov[k]["never_exercised_checks"] == list(OPPORTUNITY_RULE_PREFIXES_CHECKS)
            and c[sym]["opportunity_scans_signal_lane"] == 0
            and c[sym]["scans_where_opportunity_rules_were_not_applicable"] == c[sym]["scans"]
            and any(f["id"] == "D-LSMC-9" for f in findings)
            for k, sym in ((f"C_{sym}", sym) for sym in C.CRYPTO_SYMBOLS)
            if k in lanes_cov and lanes_cov[k]["never_exercised_checks"]),
        "coverage_did_not_shrink": cov_a["checks_evaluated"] >= PRE_FIX_HARNESS_BASELINE["checks_evaluated"],
        "opportunity_rules_are_now_exercised": (
            opp_exercised > PRE_FIX_HARNESS_BASELINE["opportunity_rule_checks_exercised"]
            and opp_exercised >= len(opp_checks) - 1),
        "emissions_are_still_produced_in_every_lane": all(v > 0 for v in shipped_nonempty.values()),
        "every_emitted_transition_is_archived_exactly_once": (
            archive["verdict"] == PASS and emitted >= 1
            and archive_rows["duplicate_poll_on_identical_snapshot"]["events"] == 0
            and archive_rows["archive_path_matches_the_exactly_once_guard"]["verdict"] == PASS),
        "alert_level_mapping_is_still_the_contract_mapping": (
            spec_alerts == C.ALERT_LEVEL and archive["alert_level_mapping_matches_contract"] is True),
        "fail_closed_metadata_paths_still_fail_closed": props["fail_closed_symbol_metadata"]["verdict"] == PASS,
        "no_engine_byte_was_edited_by_this_pr": (
            G.engine_sha256() == identity()["engine_sha256"]
            and sha256(G.CONTRACT_PATH) == identity()["contract_sha256"]
            == "78285f9fabcb20af14de327d010e48684dc12205f4435eff886fcc2373a357b4"),
    }
    reasons = [k for k, ok in checks.items() if not ok]
    return {
        "verdict": PASS if not reasons else FAIL,
        "verdict_reasons": reasons,
        "checks": checks,
        "opportunity_rule_checks": opp_checks,
        "opportunity_rule_checks_exercised": opp_exercised,
        "opportunity_rule_checks_with_a_pass": {k: counts[k].get(PASS, 0) for k in opp_checks},
        "shipped_state_counts_per_lane": shipped_nonempty,
        "l5_check_status_counts": {k: _counts(v) for k, v in sorted(l5_counts.items())},
        "pre_fix_baseline": PRE_FIX_HARNESS_BASELINE,
        "coverage_now": {"checks_evaluated": cov_a["checks_evaluated"],
                         "checks_not_applicable": cov_a["checks_not_applicable"],
                         "never_exercised_checks": cov_a["never_exercised_checks"]},
        "note": ("The harness fixes in this PR moved 156 check verdicts and turned six previously "
                 "blanked opportunity rules into evaluated checks. Nothing was suppressed: the "
                 "blocking gate set, the alert-level mapping and the fail-closed metadata paths are "
                 "byte-identical in behaviour, and the frozen 1.1.0 engine and contract were not "
                 "edited at all."),
    }


def phase_b_classification(findings: list, integrity: dict, candidate: dict) -> dict:
    """Phase B.2/B.3/B.5/B.7: one row per defect, classified against the mission's five classes."""
    by_id = {f["id"]: f for f in findings}
    rows = {
        "D-LSMC-6": {
            "class": "IMPLEMENTATION",
            "class_detail": "the frozen engine implements a different unit than its own contract declares "
                            "(calendar NY-17:00 boundaries instead of distinct trading dates)",
            "strategy_contract_also_involved": True,
            "route": "CANDIDATE_1_1_2_RULE_DIFF",
            "owner_decision_required": True,
            "fix_applied_in_this_pr": "none at runtime; the frozen 1.1.0 bytes and its historical verdict are preserved",
            "prepared_artifact": candidate["candidate_contract"],
            "prepared_artifact_sha256": candidate["candidate_contract_sha256"],
            "outcome_before": "declared 5 trading days, implemented 5 calendar days; 600 of 723 committed EURUSD H1 "
                              "POI origins expire early, always in the early direction",
            "outcome_after": "unchanged at runtime (frozen). The candidate pins max_age_unit "
                             "DISTINCT_NY1700_TRADING_DATES, keeps the number 5, and states the implementation "
                             "requirement; activation needs owner confirmation plus a fresh L1-L6 replay",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_poi_age_divergence_reproduces_and_is_conservative "
                               "+ ::test_declared_trading_day_rule_is_what_the_candidate_must_implement",
            "blocking": True,
        },
        "D-LSMC-1": {
            "class": "METADATA",
            "class_detail": "missing owner-confirmed broker pip evidence; the fail-closed gate is behaving correctly",
            "route": "OWNER_DECISION_REQUIRED_AND_HOST_CAPTURE",
            "owner_decision_required": True,
            "fix_applied_in_this_pr": "none; inventing a pip size would fabricate broker metadata",
            "prepared_artifact": None,
            "outcome_before": "USDJPY, XAUUSD, BTCUSD and ETHUSD have a HOST_CAPTURED point but no pip size, so C10 "
                              "returns C10_PIP_SIZE_NOT_EVIDENCED and every opportunity is rejected without a stop",
            "outcome_after": "unchanged. The route is 1.1.1's pip_size_rules proposals (FX 10 x point, XAUUSD 0.1, "
                             "BTCUSD 1.0, ETHUSD 0.1), all PENDING_OWNER_CONFIRM with apply_before_owner_confirmation "
                             "false; the audit's positive control measures exactly 10 x point for EURUSD",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_metadata_fails_closed_and_the_positive_control_still_resolves",
            "blocking": True,
        },
        "D-LSMC-7": {
            "class": "VERIFICATION_HARNESS",
            "class_detail": "the delivery gate blanked six opportunity rules, so a green verdict carried no coverage",
            "route": "FIX_APPLIED_IN_THIS_PR",
            "owner_decision_required": False,
            "fix_applied_in_this_pr": "src/v1_tickets/lsmc_logic_gate.py now evaluates the opportunity rules on the "
                                      "detection lane and records coverage; the engine was not touched",
            "prepared_artifact": None,
            "outcome_before": f"{PRE_FIX_HARNESS_BASELINE['checks_evaluated']} checks evaluated, "
                              f"{PRE_FIX_HARNESS_BASELINE['opportunity_rule_checks_exercised']} opportunity-rule checks "
                              "exercised: LOGIC_VERIFIED was vacuous",
            "outcome_after": f"{integrity['coverage_now']['checks_evaluated']} checks evaluated, all "
                             f"{integrity['opportunity_rule_checks_exercised']} distinct opportunity-rule checks "
                             f"exercised ({min(integrity['opportunity_rule_checks_with_a_pass'].values())} PASS cases "
                             "each), never_exercised_checks empty, 156 check verdicts moved, same LOGIC_VERIFIED "
                             "verdict but now with coverage; the undeclared REJECTED shipped state is recorded",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_harness_lane_evaluates_the_opportunity_rules_it_once_blanked "
                               "+ ::test_archive_only_stays_exactly_once",
            "blocking": False,
        },
        "D-LSMC-8": {
            "class": "VERIFICATION_HARNESS",
            "class_detail": "a fixture was evaluated at a time other than the manifest decision time",
            "route": "FIX_APPLIED_IN_THIS_PR",
            "owner_decision_required": False,
            "fix_applied_in_this_pr": "tests/fixtures/large_smc_v111/EURUSD.json re-pinned to the manifest decision "
                                      "time and a check_decision_time guard added to tests/_lsmc_v111_fixtures.py",
            "prepared_artifact": None,
            "outcome_before": f"EURUSD fixture sha256 {PRE_FIX_HARNESS_BASELINE['eurusd_fixture_sha256'][:16]}... with "
                              "an evaluated_at_utc that did not match the manifest decision time",
            "outcome_after": "all six fixtures are evaluated at 2026-08-03T00:00:00Z, every manifest pin recomputes "
                             "from the file, and the guard raises on any divergence",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_every_fixture_is_pinned_and_evaluated_at_the_manifest_decision_time",
            "blocking": False,
        },
        "D-LSMC-3": {
            "class": "METADATA",
            "class_detail": "repository identity metadata: strategies/registry.yaml pins an engine sha256 that the "
                            "working tree has not matched since the 2026-10-10 delivery-gate change to watch.py",
            "route": "OWNER_DECISION_REQUIRED",
            "owner_decision_required": True,
            "fix_applied_in_this_pr": "prose only (verification_basis); the stale pin was left stale on purpose so the "
                                      "divergence stays visible instead of being papered over",
            "prepared_artifact": None,
            "outcome_before": "registry engine_sha256 ec0b2f3d... vs tree 88dd9f1f..., drift isolated to watch.py",
            "outcome_after": "unchanged and still reported as engine_matches_registry=false; re-pinning is an owner "
                             "identity decision, not an audit action",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_frozen_strategy_and_data_identities_are_unchanged",
            "blocking": False,
        },
        "D-LSMC-5": {
            "class": "DATA",
            "class_detail": "no accepted spread/commission evidence exists off-host, so trading friction cannot be "
                            "verified in this environment",
            "route": "HOST_EVIDENCE_REQUIRED",
            "owner_decision_required": True,
            "fix_applied_in_this_pr": "none; L5 stays WARN in every lane rather than being forced to PASS",
            "prepared_artifact": None,
            "outcome_before": "L5 WARN on all 18 harness cases and all 575 EURUSD scans",
            "outcome_after": "unchanged: L5 WARN everywhere, recorded in the scope matrix as an advisory gate",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_verdict_is_not_verified_with_exactly_two_blocking_findings",
            "blocking": False,
        },
        "D-LSMC-9": {
            "class": "VERIFICATION_HARNESS",
            "class_detail": "the committed C16 60-day evidence records no check coverage and no C10 stop geometry, so "
                            "2040 + 848 full-D1 opportunities cannot be shown to have had their rules evaluated",
            "route": "RECORDED_NO_RERUN",
            "owner_decision_required": False,
            "fix_applied_in_this_pr": "the audit re-derives every committed C16 count from the artifacts' own bytes "
                                      "and measures the gap (6921/8961 BTCUSD scans had every opportunity rule "
                                      "NOT_APPLICABLE); the 60-day replays were not re-run (audit-only scope)",
            "prepared_artifact": None,
            "outcome_before": "committed headline PASS on 8961/8961 full-D1 scans with no coverage field",
            "outcome_after": "same committed bytes, now re-derived and qualified: with_c10_stop=0 for both crypto "
                             "symbols, and the coverage gap is explicit in lane C",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_committed_c16_artifacts_still_rederive_from_their_own_bytes",
            "blocking": False,
        },
        "D-LSMC-10": {
            "class": "VERIFICATION_HARNESS",
            "class_detail": "boundary evidence: the import closure reaches src/mt5 modules that import the MetaTrader5 "
                            "broker API, while no transport/order/authorization path exists",
            "route": "RECORDED_NO_ACTION",
            "owner_decision_required": False,
            "fix_applied_in_this_pr": "the boundary check was rewritten from a vacuous one-module scan into an ast "
                                      "graph over 48 repo modules plus a runtime probe with a positive control",
            "prepared_artifact": None,
            "outcome_before": "no_transport_boundary passed vacuously (it never traversed children)",
            "outcome_after": "48 modules reachable, 0 transport hits statically and at runtime (561 modules loaded), "
                             "positive control reaches all 5 pinned modules, MT5 import sites recorded",
            "regression_test": "tests/test_lsmc_v110_logic_audit.py::test_boundary_check_reaches_the_engine_and_finds_no_transport",
            "blocking": False,
        },
    }
    missing = sorted(set(by_id) - set(rows))
    counts = {}
    for r in rows.values():
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    checks = {
        "every_reported_finding_is_classified": not missing,
        "every_class_is_one_of_the_five_mission_classes": all(r["class"] in C17_DEFECT_CLASSES for r in rows.values()),
        "no_fix_weakened_a_gate_or_suppressed_an_emission": integrity["verdict"] == PASS,
        "frozen_v110_contract_and_engine_are_untouched": integrity["checks"]["no_engine_byte_was_edited_by_this_pr"],
        "genuine_strategy_defect_goes_to_a_candidate_not_to_1_1_0": (
            rows["D-LSMC-6"]["route"] == "CANDIDATE_1_1_2_RULE_DIFF" and candidate["verdict"] == PASS),
        "blocking_rows_are_owner_or_host_routes_not_agent_fixes": all(
            rows[fid]["owner_decision_required"] for fid in rows if rows[fid]["blocking"]),
    }
    reasons = [k for k, ok in checks.items() if not ok] + [f"unclassified findings: {missing}" if missing else ""]
    return {
        "verdict": PASS if not [r for r in reasons if r] else FAIL,
        "verdict_reasons": [r for r in reasons if r],
        "mission_classes": list(C17_DEFECT_CLASSES),
        "class_counts": dict(sorted(counts.items())),
        "rows": {k: rows[k] for k in sorted(rows, key=lambda x: (not rows[x]["blocking"], x))},
        "checks": checks,
        "severity_and_blocking_come_from": "findings[] in this same report",
    }


def _registry_lsmc_entry() -> dict:
    reg = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))
    return reg["strategies"][C.STRATEGY_ID]


def _registry_lsmc_versions() -> list:
    """Every LSMC version the registry knows: the registered one plus its historical entries."""
    entry = _registry_lsmc_entry()
    return [str(entry["version"])] + [str(v) for v in (entry.get("historical_versions") or {})]


def positive_risk_geometry(b: dict) -> dict:
    """Phase C: entry / stop / target geometry with a positive risk and reward distance.

    Only opportunities where C10 produced a stop *and* C11 produced a target are evaluable. The rest are
    recorded NOT_APPLICABLE carrying the engine's own reason -- no level is ever invented here, and the
    1.1.0 contract declares no reward/risk minimum, so the candidate's proposed `minimum_rr: 2.0`
    (PENDING_OWNER_CONFIRM) is measured and reported rather than gated.
    """
    pip = C.C10_PIP_SIZE[b["symbol"]]
    rows = []
    for key, o in sorted(b["opportunities"]["items"].items()):
        entry, stop, target = o["entry_reference"], o["stop_c10"], o["target_c11"]
        direction = o["direction"]
        if stop is None or target is None:
            rows.append({"opportunity": key, "direction": direction, "evaluable": False,
                         "reason": o["stop_reason"] or o["target_reason"] or "MISSING_STOP_OR_TARGET",
                         "stop_c10": stop, "target_c11": target,
                         "delivery_rejection": o["delivery_rejection"]})
            continue
        risk, reward = abs(entry - stop), abs(target - entry)
        side_ok = (stop < entry < target) if direction == "LONG" else (target < entry < stop)
        beyond = ((o["sweep_extreme"] - stop) if direction == "LONG" else (stop - o["sweep_extreme"]))
        rr = round(reward / risk, 6) if risk else None
        rows.append({
            "opportunity": key, "direction": direction, "evaluable": True, "reason": None,
            "entry_reference": entry, "stop_c10": stop, "target_c11": target,
            "target_tier": o["target_tier"], "sweep_extreme": o["sweep_extreme"],
            "risk_price_distance": round(risk, 10), "reward_price_distance": round(reward, 10),
            "risk_pips": round(risk / pip, 6), "reward_pips": round(reward / pip, 6),
            "reward_risk": rr, "positive_risk": risk > 0, "positive_reward": reward > 0,
            "geometry_side_consistent": side_ok,
            "stop_at_least_the_c10_floor_beyond_the_sweep": round(beyond / pip, 9) >= MIN_BUFFER_PIPS,
            "meets_candidate_minimum_rr_2_0": bool(rr is not None and rr >= 2.0),
            "delivery_rejection": o["delivery_rejection"],
        })
    ev = [r for r in rows if r["evaluable"]]
    checks = {
        "every_evaluable_opportunity_has_positive_risk_and_reward": all(
            r["positive_risk"] and r["positive_reward"] for r in ev),
        "stop_and_target_are_on_the_correct_side_of_entry": all(r["geometry_side_consistent"] for r in ev),
        "stop_respects_the_c10_hard_floor_beyond_the_sweep": all(
            r["stop_at_least_the_c10_floor_beyond_the_sweep"] for r in ev),
        "reward_risk_is_measured_for_every_evaluable_opportunity": all(r["reward_risk"] is not None for r in ev),
        "non_evaluable_opportunities_carry_the_engine_reason": all(
            r["reason"] for r in rows if not r["evaluable"]),
        "no_level_was_invented_for_a_non_evaluable_opportunity": all(
            (r["stop_c10"] is None or r["target_c11"] is None) for r in rows if not r["evaluable"]),
        "at_least_one_opportunity_was_evaluable": bool(ev),
    }
    reasons = [k for k, ok in checks.items() if not ok]
    return {
        "verdict": PASS if not reasons else FAIL,
        "verdict_reasons": reasons,
        "symbol": b["symbol"], "pip_size": pip, "pip_provenance": "contract.C10_PIP_SIZE (owner-evidenced)", "min_buffer_pips": MIN_BUFFER_PIPS,
        "opportunities": len(rows), "evaluable": len(ev),
        "not_evaluable": len(rows) - len(ev),
        "reward_risk_values": [r["reward_risk"] for r in ev],
        "opportunities_meeting_candidate_minimum_rr_2_0": sum(
            1 for r in ev if r["meets_candidate_minimum_rr_2_0"]),
        "candidate_rr_status": "rules.reward_risk.minimum_rr = 2.0, PENDING_OWNER_CONFIRM in 1.1.1/1.1.2; "
                               "the frozen 1.1.0 contract declares no RR minimum, so this is measured, not gated",
        "checks": checks,
        "rows": rows,
        "note": ("Off-host every evaluable opportunity is still rejected by the delivery gate "
                 "(REJECT_STALE: the owner remaining-reward threshold config is host-only), so this "
                 "geometry is evidence about detection, not a tradable signal."),
    }


GATES = ("L1", "L2", "L3", "L4", "L5", "L6")
REQUIRED_GATES = ("L1", "L2", "L3", "L4", "L6")     # L5 is advisory per OD1011-L5
FX_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
CANDIDATE_CONTRACT = "strategies/ST_LARGE_SMC_V1_1_1_2.yaml"


def _gate_verdict(counts: dict) -> str:
    """One gate's verdict from its status counts: any FAIL/WARN wins over PASS."""
    if counts.get(FAIL):
        return FAIL
    if counts.get(WARN):
        return WARN
    if counts.get(PASS):
        return PASS
    return NOT_APPLICABLE


def scope_matrix(a: dict, b: dict, c: dict, findings: list) -> dict:
    """AGP-C17 Phase C: per-symbol L1-L6 gate matrix, emissions and scope verdicts.

    A scope is `LOGIC_VERIFIED` only when every REQUIRED gate passes on evidence that actually
    covers the symbol and no blocking finding applies to it. `L4 FAIL` on a `MARKET_CLOSED` scan
    is the gate's declared semantics (that snapshot is not an evaluable trading instant), so it
    is accepted only when the two counts are equal and is reported explicitly either way.
    Evidence for 1.1.0 is never reused as evidence for a candidate version.
    """
    blocking = {f["id"]: f for f in findings if f["blocking"]}
    out = {}
    for symbol in C.V1_SYMBOLS:
        gates = {g: dict(a["per_symbol_gates"].get(symbol, {}).get(g, {})) for g in GATES}
        gate_verdicts = {g: _gate_verdict(gates[g]) for g in GATES}
        evidence = [{"lane": "A_fixture_harness",
                     "cases": a["per_symbol_cases"].get(symbol, 0),
                     "classifications": a["per_symbol_classifications"].get(symbol, []),
                     "states": a["per_symbol_states"].get(symbol, {})}]
        l4_note = None
        if symbol == "EURUSD" and b:
            evidence.append({"lane": "B_eurusd_host_captured_replay", "scans": b["window"]["scans"],
                             "classifications": [b["classification"]],
                             "window_utc": [b["window"]["first_scan_utc"], b["window"]["last_scan_utc"]],
                             "states": {"shipped": b["states_shipped"]},
                             "distinct_opportunities": b["opportunities"]["distinct"],
                             "opportunities_with_c10_stop": b["opportunities"]["with_c10_stop_price"],
                             "l4_fail_equals_market_closed": b["l4_fail_equals_market_closed"],
                             "positive_risk_geometry": {
                                 k: b["positive_risk_geometry"][k] for k in
                                 ("verdict", "opportunities", "evaluable", "not_evaluable",
                                  "reward_risk_values", "opportunities_meeting_candidate_minimum_rr_2_0",
                                  "candidate_rr_status")}})
            # merge the rolling replay into the symbol's gate picture
            for g in GATES:
                for status, n in b["gate_status_counts"].get(g, {}).items():
                    gates[g][status] = gates[g].get(status, 0) + n
            gate_verdicts = {g: _gate_verdict(gates[g]) for g in GATES}
            if gates["L4"].get(FAIL) and b["l4_fail_equals_market_closed"]:
                l4_note = (f"L4 FAIL on {b['market_closed_scans']} MARKET_CLOSED scan(s) only: a weekend "
                           "snapshot is not an evaluable trading instant, which is what L4 asserts")
        if symbol in C.CRYPTO_SYMBOLS and c:
            lane = c.get(symbol, {})
            evidence.append({"lane": "C_crypto_recorded_60d_bounded", "scans": lane.get("scans"),
                             "classifications": ["VT_RECORDED"],
                             "window_utc": [lane.get("first_scan_utc"), lane.get("last_scan_utc")],
                             "states": {"shipped": lane.get("states_shipped")},
                             "opportunity_scans_signal_lane": lane.get("opportunity_scans_signal_lane"),
                             "opportunity_stop_reasons": lane.get("opportunity_stop_reasons")})
            committed = c.get(f"{symbol}_committed_c16", {})
            evidence.append({"lane": "C_committed_c16_rederivation",
                             "artifact": committed.get("artifact"),
                             "all_counts_and_hashes_rederive": committed.get("all_pass"),
                             "committed_verdict": committed.get("committed_verdict"),
                             "note": "60-day replay evidence re-derived from its own bytes, not re-run"})
        applies = []
        if symbol in FX_SYMBOLS and "D-LSMC-6" in blocking:
            applies.append("D-LSMC-6")     # measured divergent on FX calendars, 0 divergences on crypto
        if symbol not in C.C10_PIP_SIZE and "D-LSMC-1" in blocking:
            applies.append("D-LSMC-1")     # no evidenced pip -> C10 stop geometry not evaluable
        required_ok = all(gate_verdicts[g] == PASS for g in REQUIRED_GATES)
        verdict = "LOGIC_VERIFIED" if required_ok and not applies else "NOT_VERIFIED"
        out[symbol] = {
            "strategy_version": C.STRATEGY_VERSION,
            "gates": gate_verdicts,
            "gate_status_counts": {g: gates[g] for g in GATES},
            "l4_note": l4_note,
            "required_gates": list(REQUIRED_GATES),
            "required_gate_note": ("stricter than the shipped gate on purpose: v1_tickets.logic_gate.BLOCKING is "
                                   "(L1, L2, L3, L4) and L5 + L6 are advisory there. This matrix additionally "
                                   "requires L6 to PASS, and keeps L5 advisory per OD1011-L5."),
            "required_gates_pass": required_ok,
            "advisory_gates": {"L5": "WARN in every lane: OD1011-L5, no accepted spread/commission "
                                     "evidence and no cost gate in the 1.1.0 alert path (D-LSMC-5)"},
            "blocking_findings_applying_to_this_scope": applies,
            "c10_pip_evidenced": symbol in C.C10_PIP_SIZE,
            "c10_stop_geometry_evaluable": symbol in C.C10_PIP_SIZE and (
                symbol != "EURUSD" or b["opportunities"]["with_c10_stop_price"] > 0),
            "poi_age_unit_divergent": symbol in FX_SYMBOLS,
            "evidence": evidence,
            "emissions": {
                "delivery_mode": W.DELIVERY_MODE,
                "alert_level_mapping_matches_contract": C.ALERT_LEVEL == yaml.safe_load(
                    G.CONTRACT_PATH.read_text(encoding="utf-8"))["alerts"]["mapping"],
                "undeclared_state_emitted": "REJECTED" if a["per_symbol_states"].get(
                    symbol, {}).get("shipped", {}).get("REJECTED") else None,
                "exactly_once_archive_verified": symbol == "EURUSD",
                "transport_or_order_path_reachable": False,
            },
            "scope_verdict": verdict,
            "scope_verdict_reasons": (
                [f"{fid}: {blocking[fid]['headline']}" for fid in applies]
                + ([] if required_ok else ["required gates not all PASS: "
                                           + ", ".join(g for g in REQUIRED_GATES if gate_verdicts[g] != PASS)])),
        }
    out["_candidate_1_1_2"] = {
        "strategy_version": "1.1.2",
        "contract": CANDIDATE_CONTRACT,
        "status": "CANDIDATE_PENDING_OWNER_CONFIRM",
        "implementation": "SPEC_ONLY_NOT_WIRED",
        "gates": {g: NOT_APPLICABLE for g in GATES},
        "scope_verdict": "NOT_VERIFIED",
        "scope_verdict_reasons": [
            "no runtime: the candidate is specification-only and is not wired into src/large_smc_watch",
            "1.1.0 evidence must not be reused as proof for a changed candidate (AGP-C17 Phase C)",
            "the D-LSMC-6 rule-change diff it carries needs owner confirmation before any engine change",
        ],
        "rule_change_diff": "see the candidate contract's candidate_rule_changes block",
        "authority": {"registered": False, "active": False, "proposal_generation_authorized": False,
                      "demo_authorized": False, "live_authorized": False,
                      "economic_status": "NOT_EVALUATED"},
    }
    verified = sorted(k for k, v in out.items() if not k.startswith("_")
                      and v["scope_verdict"] == "LOGIC_VERIFIED")
    return {"scopes": out,
            "logic_verified_scopes": verified,
            "not_verified_scopes": sorted(k for k, v in out.items() if not k.startswith("_")
                                          and v["scope_verdict"] == "NOT_VERIFIED"),
            "candidate_scopes": sorted(k for k in out if k.startswith("_")),
            "rule": ("LOGIC_VERIFIED requires every required gate (L1-L4, L6) to PASS on evidence "
                     "covering that symbol and no blocking finding to apply to it; L5 is advisory "
                     "(OD1011-L5). No scope qualifies today."),
            "economics": "no scope is EDGE_VERIFIED; economic_status stays NOT_EVALUATED everywhere"}


def build_report(crypto_scans: int, skip_crypto: bool, lane_b_every: int) -> dict:
    ident = identity()
    a = lane_a()
    b = lane_b(scans_every=lane_b_every)
    b["positive_risk_geometry"] = positive_risk_geometry(b)
    d_sem = detection_semantics(b)
    props = {
        "causality": causality_properties(),
        "window_sensitivity": window_sensitivity(),
        "calendar_and_sessions": calendar_and_session_semantics(),
        "poi_age_semantics": poi_age_semantics(),
        "fail_closed_symbol_metadata": fail_closed_metadata(),
        "archive_only_exactly_once": archive_only_exactly_once(),
        "no_transport_boundary": no_transport_boundary(),
        "harness_regressions": harness_regression(),
        "candidate_rule_change_diff": candidate_rule_change_diff(),
    }
    c = {} if skip_crypto else lane_c(crypto_scans)
    lanes = {"A_fixture_harness": a, "B_eurusd_host_captured_replay": b,
             "C_crypto_recorded_60d_bounded": c, "D_rule_semantics": d_sem}
    findings = build_findings(ident, a, b, c, d_sem, props)
    props["gate_integrity"] = gate_integrity(a, b, c, props, findings)
    props["phase_b_classification"] = phase_b_classification(
        findings, props["gate_integrity"], props["candidate_rule_change_diff"])
    matrix = scope_matrix(a, b, c, findings)
    property_verdicts = {k: v.get("verdict") for k, v in props.items() if isinstance(v, dict)}
    verdict_reasons = [f["id"] + ": " + f["headline"] for f in findings if f["blocking"]]
    lane_verdicts = {k: v.get("verdict") for k, v in lanes.items()
                     if isinstance(v, dict) and "verdict" in v}
    if c:
        fresh = [d["verdict"] for k, d in c.items() if not k.endswith("_committed_c16")]
        rederived = [PASS if d["all_pass"] else FAIL for k, d in c.items() if k.endswith("_committed_c16")]
        lane_verdicts["C_crypto_recorded_60d_bounded"] = (
            PASS if fresh + rederived and all(v == PASS for v in fresh + rederived) else FAIL)
    return {
        "schema": SCHEMA, "mission": MISSION, "strategy": ident["strategy"],
        "reproducibility": ("byte-reproducible: no wall-clock field, no run id, no hostname; fixed rng seed "
                            "20261013. The only run-dependent value is identity.code_sha = `git rev-parse HEAD` "
                            "resolved at import (v1_tickets.code_identity), so two runs on the same commit are "
                            "byte-identical; every other hash is over working-tree bytes actually exercised."),
        "environment": {"python": sys.version.split()[0], "platform": sys.platform,
                        "dependency_pins": "pyyaml 6.0.3 / numpy 2.2.6 / pandas 2.3.3 / smartmoneyconcepts 0.0.27"},
        "identity": ident,
        "lanes": lanes,
        "scope_matrix": matrix,
        "phase_b": props["phase_b_classification"],
        "property_checks": props,
        "property_verdicts": property_verdicts,
        "lane_verdicts": lane_verdicts,
        "findings": findings,
        "verdict": "NOT_VERIFIED",
        "verdict_semantics": ("LOGIC verification of rule conformance, causality and internal consistency only. "
                              "Not economic edge, not READY, not demo/live authority; all remain false."),
        "verdict_reasons": verdict_reasons,
        "harness_scope_verdict": {
            "value": a["verdict"],
            "scope": ("18 fixture cases, L1-L4 blocking; this is the shipped LOGIC_VERIFICATION_REPORT verdict "
                      "and it is necessary but not sufficient -- it cannot see the POI-age unit divergence "
                      "(its windows are shorter than six trading dates) or the missing crypto stop evidence."),
        },
        "authority": "none: logic evidence only; no registry status, READY, demo or live change",
    }


def build_findings(ident, a, b, c, d_sem, props) -> list:
    reg = ident["registry_identity"]
    poi = props["poi_age_semantics"]
    out = []
    out.append({
        "id": "D-LSMC-3", "status": "REPRODUCED (already registered by C16)", "severity": "MEDIUM",
        "class": "identity-record staleness", "blocking": False,
        "headline": "registry engine_sha256 pin does not match the tree",
        "evidence": {"tree_engine_sha256": reg["engine_sha256"], "registry_engine_sha256": reg["registry_engine_sha256"],
                     "drifted_file": "src/large_smc_watch/watch.py",
                     "drifted_file_sha256": ident["engine_file_sha256"]["src/large_smc_watch/watch.py"],
                     "contract_matches_registry": reg["contract_matches_registry"]},
        "cause": ("The 2026-10-10 delivery-gate change to watch.py moved the engine hash; the registry pin was "
                  "never re-recorded. Detection files (contract.py, detect.py) and both dependencies are unchanged."),
        "resolution": ("Owner choice, unchanged from C16: re-record the identity for the current engine, or move the "
                       "delivery gate out of the frozen engine. Not done here -- re-recording an identity on agent "
                       "authority would reattribute the 2026-10-09/11 LOGIC_VERIFIED record.")})
    divergent = {k: v for k, v in poi.items() if isinstance(v, dict) and v.get("verdict") == FAIL}
    out.append({
        "id": "D-LSMC-6", "status": "NEW (this audit)", "severity": "MEDIUM",
        "class": "declaration vs implementation (unit of a frozen rule)", "blocking": True,
        "headline": "POI max age is declared in TRADING days and implemented in CALENDAR NY-17:00 dates",
        "evidence": {"declared": poi["declared_rule"], "implemented": poi["implemented_rule"],
                     "dead_code": poi["dead_code"],
                     "measured": {k: {kk: vv for kk, vv in v.items() if kk != "examples"}
                                  for k, v in divergent.items()},
                     "examples": [e for k, v in divergent.items() for e in v.get("examples", [])][:4],
                     "scope": poi["scope"], "materiality": poi["materiality"]},
        "cause": ("watch.expires_at applies next_day_boundary POI_MAX_AGE_TRADING_DAYS + 1 times, which counts "
                  "Saturday and Sunday. The helper that implements the declared unit (_poi_age_days, distinct "
                  "NY-17:00 trading dates) exists in the same file and is never called."),
        "resolution": ("Owner decision, not an agent edit: either amend the contract/frozen-spec wording to the "
                       "implemented calendar-date unit, or ship a new strategy version that wires the trading-date "
                       "count. The frozen 1.1.0 engine must not be edited in place. Direction of the error is "
                       "conservative (POIs expire early), so no POI is ever kept alive longer than declared."),
        "why_not_gated_in_lsmc_logic_gate": ("A new blocking L2 check would also change the committed C15/C16 lane "
                                             "distributions on re-run, and the resolution is an owner decision; the "
                                             "measurement lives here until then. The 18-case harness cannot see it "
                                             "at all: its H1 windows span fewer than six trading dates.")})
    out.append({
        "id": "D-LSMC-7", "status": "NEW (this audit)", "severity": "MEDIUM",
        "class": "harness vacuity (fixed here) + contract state coverage", "blocking": False,
        "headline": "the delivery gate blanked every opportunity rule in the shipped fixture harness",
        "evidence": {"before_fix_check_verdict_changes": 156,
                     "before_fix": ("L2's six opportunity rules, all of L3 geometry and L6 freshness were "
                                    "NOT_APPLICABLE on 18/18 cases while L2/L3/L6 still printed PASS; "
                                    "opportunity_symbols_covered was [] and c10_stop_geometry_symbols was []"),
                     "after_fix": {"checks_evaluated": a["check_coverage"]["checks_evaluated"],
                                   "checks_not_applicable": a["check_coverage"]["checks_not_applicable"],
                                   "never_exercised_checks": a["check_coverage"]["never_exercised_checks"],
                                   "opportunity_symbols_covered_signal_lane":
                                       a["opportunity_symbols_covered_signal_lane"],
                                   "c10_stop_price_symbols": a["c10_stop_price_symbols"]},
                     "rejected_state_not_in_contract": ("watch emits REJECTED; the frozen contract's alerts.mapping "
                                                        "declares only DEVELOPING/NEAR_POI/OPPORTUNITY/INVALIDATED/"
                                                        "EXPIRED and says SUSPENDED/IDLE/DATA_ERROR/MARKET_CLOSED "
                                                        "emit nothing. REJECTED is undeclared (alert level INFO by a "
                                                        "code special case).")},
        "cause": ("watch.gate_opportunity (2026-10-10) renames the state to REJECTED off-host, where the owner "
                  "threshold config/local/actionability_policy.yaml is absent and fails closed; the gate keyed its "
                  "opportunity checks on state == OPPORTUNITY."),
        "resolution": ("Fixed in this PR for the harness: v1_tickets.lsmc_logic_gate.signal_snapshot inverts the "
                       "delivery gate exactly, the checks run on the detection lane, and check_coverage makes any "
                       "future vacuity visible. The undeclared REJECTED state needs a contract note or an owner "
                       "decision; no rule was changed.")})
    out.append({
        "id": "D-LSMC-8", "status": "NEW (this audit)", "severity": "MEDIUM",
        "class": "evidence fixture defect (fixed here)", "blocking": False,
        "headline": "the only HOST_CAPTURED FX fixture was evaluated 68 days after its own data, in the FX weekend",
        "evidence": {"fixture": "tests/fixtures/large_smc_v111/EURUSD.json",
                     "evaluated_at_utc_before": "2026-10-10T19:45:53.895829Z",
                     "evaluated_at_utc_before_local": "Saturday 15:45 America/New_York (FX weekend close)",
                     "manifest_decision_time_utc": ident["fixture_set"]["manifest_decision_time_utc"],
                     "sibling_fixtures_at_decision_time": 5,
                     "last_m5_bar_utc": "2026-08-02T23:55:00Z",
                     "staleness_before_days": 68.8,
                     "sha256_before": "b5e1e524e1b912d15032650881edb000906d6d875657332be90fa3997a191c11",
                     "sha256_after": ident["fixture_set"]["eurusd_fixture_sha256"],
                     "bars_changed": 0, "bars_total": 754,
                     "consequences": ["18-case harness verdict LOGIC_NOT_VERIFIED (L2 + L4 FAIL) since 2026-10-10",
                                      "v1.1.1 candidate audit's only HOST_CAPTURED row pinned to MARKET_CLOSED / "
                                      "L4 FAIL by tests/test_lsmc_v111_candidate_audit.py",
                                      "the AGP-4H-C oracle's L6 closed-ordered-input check had 68 days of slack and "
                                      "could not fail; it is boundary-exact after the correction"]},
        "cause": "the fixture was regenerated with its generation wall-clock instead of the manifest decision time",
        "resolution": ("Fixed in this PR: evaluated_at_utc = manifest decision_time_utc (all 754 bars byte-identical), "
                       "manifest pin updated, registry verification_basis annotated (the historical record stays "
                       "attributed to the bytes it ran on), and _lsmc_v111_fixtures.check_decision_time now fails "
                       "closed on any recurrence.")})
    rederived = {k: v["coverage_derived_from_artifact"] for k, v in c.items() if k.endswith("_committed_c16")}
    out.append({
        "id": "D-LSMC-9", "status": "NEW (this audit)", "severity": "LOW",
        "class": "reporting (gate status read as coverage)", "blocking": False,
        "headline": ("a gate PASS on every scan is not coverage: across the committed 60-day crypto replays no "
                     "stop-geometry check was ever evaluable"),
        "evidence": {"committed_c16_rederived_from_the_artifacts": rederived or "lane C skipped (--skip-crypto)",
                     "lane_c_bounded_window": {
                         sym: {"scans": d["scans"],
                               "window_utc": [d["first_scan_utc"], d["last_scan_utc"]],
                               "opportunity_scans_signal_lane": d["opportunity_scans_signal_lane"],
                               "scans_where_opportunity_rules_were_not_applicable":
                                   d["scans_where_opportunity_rules_were_not_applicable"],
                               "opportunity_stop_reasons": d["opportunity_stop_reasons"],
                               "never_exercised_checks": d["check_coverage"]["never_exercised_checks"]}
                         for sym, d in c.items() if not sym.endswith("_committed_c16")},
                     "same_defect_class_as": "D-LSMC-7 (the harness keyed its opportunity checks on a state "
                                             "the delivery gate had already renamed)"},
        "cause": ("Both committed C16 artifacts report gate_status_counts of PASS on 8,961/8,961 full-D1 scans for "
                  "L1-L4 and L6. That is true and it is not coverage: on 6,921 (BTCUSD) and 8,113 (ETHUSD) of those "
                  "scans the snapshot was not an OPPORTUNITY, so L2's six opportunity rules and all of L3/L6's "
                  "opportunity checks were NOT_APPLICABLE, and because opportunities.with_c10_stop = 0 the two "
                  "stop-geometry assertions (L3.stop_side, L3.stop_beyond_sweep) were NOT_APPLICABLE on every scan "
                  "of both 60-day replays. The committed NOT_VERIFIED verdicts already rest on the missing stop "
                  "evidence; what was missing is the explicit statement of how little of the gate those headlines "
                  "actually evaluated."),
        "resolution": ("Committed C16 artifacts are historical evidence and are NOT rewritten. Fresh reports now "
                       "carry check_coverage (checks_evaluated / checks_not_applicable / never_exercised_checks, "
                       "with the structural NOT_APPLICABLE markers listed separately), and lane C of this audit "
                       "re-derives the committed counts from the artifacts instead of trusting the headline. Any "
                       "future replay report that states a gate PASS count should state the evaluated-check count "
                       "next to it.")})
    boundary = props["no_transport_boundary"]
    out.append({
        "id": "D-LSMC-10", "status": "NEW (this audit); the import chain itself is already documented in "
                                     "tests/conftest.py", "severity": "LOW",
        "class": "import boundary / packaging", "blocking": False,
        "headline": ("the ARCHIVE_ONLY engine has no transport or order path, but importing it does load the "
                     "MT5 broker-API modules"),
        "evidence": {"static_transport_deny_hits": boundary["static"]["transport_deny_hits"],
                     "runtime_transport_deny_loaded":
                         boundary["runtime"].get("transport_deny_loaded_excluding_stdlib_socket"),
                     "runtime_mt5_modules_loaded": boundary["runtime"].get("mt5_modules_loaded"),
                     "modules_loaded_by_import": boundary["runtime"].get("modules_loaded_by_import"),
                     "repo_modules_in_closure": boundary["static"]["repo_modules_reachable"],
                     "broker_api_import_sites": boundary["static"]["broker_api_imports"],
                     "no_forbidden_calls": ("tests/test_v1_large_smc_import_boundary.py asserts no "
                                            "order_send/order_check/positions_get/position_close in "
                                            "large_smc_core, large_smc_watch or fx_discovery; 9 passed "
                                            "on this tree")},
        "cause": ("large_smc_watch.detect does `from supply_demand.ob_config import ...` and "
                  "`from supply_demand.ob_contract import ...`, which executes supply_demand/__init__.py; that "
                  "file eagerly re-exports .analyzer, and analyzer imports mt5.market_data, which imports "
                  "MetaTrader5 unconditionally. market_structure/__init__.py does the same. The engine itself "
                  "never calls MT5 -- it evaluates candles handed to it -- but its import closure is not "
                  "broker-independent."),
        "resolution": ("Packaging change, owner decision, not made here: lazy re-exports in "
                       "supply_demand/__init__.py and market_structure/__init__.py (or direct submodule imports "
                       "without package side effects) would make the alert engine importable without the MT5 "
                       "package. No rule, contract or gate changes. Off-host this costs nothing today because "
                       "tests/conftest.py installs an import-only stub whose every operation raises "
                       "MT5StubOperationAttempted, so a real broker call could not silently succeed.")})
    out.append({
        "id": "D-LSMC-1", "status": "REPRODUCED with FX-side evidence (already registered by C16)",
        "severity": "MEDIUM (by design)", "class": "missing host/broker evidence", "blocking": True,
        "headline": "C10 stop geometry is evaluable on 2 of 6 instruments; the other 4 fail closed",
        "evidence": {"c10_pip_evidenced_symbols": sorted(C.C10_PIP_SIZE),
                     "not_evaluable_symbols": sorted(set(C.V1_SYMBOLS) - set(C.C10_PIP_SIZE)),
                     "eurusd_lane_b": {"distinct_opportunities": b["opportunities"]["distinct"],
                                       "with_c10_stop_price": b["opportunities"]["with_c10_stop_price"],
                                       "stop_reasons": b["opportunities"]["stop_reasons"],
                                       "delivery_rejection_reasons": b["delivery_rejection_reasons"]},
                     "crypto_lane_c": {s: {k: v for k, v in d.items() if k in (
                         "opportunity_stop_reasons", "opportunity_target_reasons", "states_shipped")}
                         for s, d in c.items() if not s.endswith("_committed_c16")}},
        "cause": ("contract.C10_PIP_SIZE evidences a pip only for EURUSD/GBPUSD; C10's hard floor is expressed in "
                  "pips, so every other instrument takes stop_reason = C10_PIP_SIZE_NOT_EVIDENCED and the delivery "
                  "gate rejects with REJECT_NO_STOP."),
        "resolution": ("Owner input, unchanged from C16: evidenced pip/stop geometry for USDJPY, XAUUSD, BTCUSD and "
                       "ETHUSD. Lane B is new evidence that where a pip IS evidenced the C10 stop and the L3 stop "
                       "geometry do compute and do pass on recorded FX bars.")})
    out.append({
        "id": "D-LSMC-5", "status": "REPRODUCED (already registered by C16)", "severity": "MEDIUM",
        "class": "L5 cost evidence", "blocking": False,
        "headline": "L5 stays WARN in every lane: no accepted spread/commission evidence and no cost gate",
        "evidence": {"lane_a_L5": a["check_coverage"]["gate_status_counts"].get("L5"),
                     "lane_b_L5": b["gate_status_counts"].get("L5"),
                     "od1011_l5": "missing cost evidence stays WARN naming the missing source, never an invented value",
                     "note": ("OD1012-LSMC-RRF authorizes lsmc_min_remaining_reward_fraction = 0.5 in the host-local "
                              "policy only; it is an operational actionability parameter, not a contract rule and not "
                              "a cost gate, and off-host its absence fails closed as REJECT_STALE.")},
        "cause": "the 1.1.0 alert path has no cost gate and no bound commission/spread source off-host",
        "resolution": "Owner input, unchanged from C16."})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", choices=("1.1.0", "1.1.2"), default="1.1.0")
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--crypto-scans", type=int, default=120, help="full-D1 scans per crypto symbol (lane C)")
    ap.add_argument("--skip-crypto", action="store_true", help="skip lane C (the 60-day recorded crypto replay)")
    ap.add_argument("--lane-b-every", type=int, default=1, help="evaluate every Nth M5 close in lane B")
    args = ap.parse_args(argv)
    if args.version == "1.1.2":
        from lsmc_v112_logic_audit import main as candidate_main
        return candidate_main(args)
    report = build_report(args.crypto_scans, args.skip_crypto, args.lane_b_every)
    text = json.dumps(report, indent=1, sort_keys=True, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"{report['schema']} {report['strategy']} verdict={report['verdict']}")
    print(f"harness scope verdict = {report['harness_scope_verdict']['value']}")
    print(f"contract_sha256={report['identity']['contract_sha256']}")
    print(f"engine_sha256={report['identity']['engine_sha256']} "
          f"(registry match={report['identity']['registry_identity']['engine_matches_registry']})")
    for name in report["lanes"]:
        verdict = report["lane_verdicts"].get(name, "n/a (skipped)" if name.startswith("C_") else "n/a")
        print(f"  lane {name}: verdict={verdict}")
    for name, verdict in sorted(report["property_verdicts"].items()):
        print(f"  property {name}: {verdict}")
    for f in report["findings"]:
        print(f"  {f['id']:<10} {f['severity']:<24} blocking={f['blocking']!s:<5} {f['headline']}")
    print("scope matrix (AGP-C17 Phase C):")
    for sym, sc in sorted(report["scope_matrix"]["scopes"].items()):
        gates = " ".join(f"{g}={sc['gates'][g]}" for g in ("L1", "L2", "L3", "L4", "L5", "L6"))
        print(f"  {sym:<8} {sc['scope_verdict']:<14} {gates}")
        for r in sc["scope_verdict_reasons"]:
            print(f"           - {r}")
    cand = report["scope_matrix"]["scopes"]["_candidate_1_1_2"]
    print(f"  1.1.2    {cand['scope_verdict']:<14} candidate ({cand['implementation']}, {cand['status']})")
    phb = report["phase_b"]
    gi = report["property_checks"]["gate_integrity"]
    print(f"gate_integrity (Phase B.7): {gi['verdict']}"
          + ("" if gi["verdict"] == PASS else f" reasons={gi['verdict_reasons']}"))
    print(f"phase_b classification (Phase B.2): {phb['class_counts']} verdict={phb['verdict']}")
    diff = report["property_checks"]["candidate_rule_change_diff"]
    print(f"candidate rule-change diff (Phase B.5): {diff['candidate_contract']} "
          f"sha256={diff['candidate_contract_sha256'][:16]}... paths={len(diff['computed_structural_diff_1_1_1_to_1_1_2'])} "
          f"undeclared={diff['undeclared_rule_drift']}")
    print("verdict_reasons:")
    for r in report["verdict_reasons"]:
        print("   -", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
