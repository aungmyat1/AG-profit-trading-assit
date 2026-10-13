"""Logic Gate L1-L6 for ST_LARGE_SMC_V1@1.1.3 (watch/alerts), v1_tickets.logic_gate pattern.

LOGIC_VERIFIED is a statement about rule conformance and internal consistency of the frozen
1.1.3 engine (src/large_smc_v113/) against its contract (strategies/ST_LARGE_SMC_V1_1_1_3.yaml).
It is never a statement about profitability, and it grants no proposal, demo or live authority.
The gate reads the contract and the engine output; it never changes a rule. A contract value
the engine does not implement FAILS (fail closed) instead of being interpreted.

L1-L4 block; L5 (cost) and L6 (freshness fields) are advisory, as in v1_tickets.logic_gate.
Checks that need an OPPORTUNITY are NOT_APPLICABLE on a non-opportunity snapshot.

Detection is verified on the PRE-delivery-gate snapshot (`signal_snapshot`). Since the
2026-10-10 actionability gates, `watch.gate_opportunity` turns every OPPORTUNITY into the
delivery state REJECTED whenever the host-only owner threshold
(`config/local/actionability_policy.yaml`) or a stop/target is absent -- off-host that is
always. Keying the opportunity checks on the shipped state therefore made L2's six
opportunity rules, all of L3 geometry and L6 freshness NOT_APPLICABLE while the gates still
printed PASS (156 check verdicts silently degraded between the 2026-10-09 LOGIC_VERIFIED
report and 2026-10-13). Delivery is a separate layer from detection, so the gate inverts it
exactly instead of losing the checks; the shipped state stays in the case record.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from large_smc_v113 import contract as C
from large_smc_v113 import evaluate_snapshot
from large_smc_v113.detect import close_time
from large_smc_v113.watch import opportunity_expiry
from strategy_engine.session import Candle
from v1_tickets.logic_gate import (
    BLOCKING,
    FAIL,
    NOT_APPLICABLE,
    NOT_EVALUABLE,
    PASS,
    WARN,
    _check,
    _gate,
    blocking_failures,
    l1_determinism,
    l5_cost,
    l6_freshness,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "strategies" / "ST_LARGE_SMC_V1_1_1_3.yaml"
ENGINE_FILES = tuple(f"src/large_smc_v113/{n}.py" for n in ("__init__", "contract", "detect", "watch", "metadata", "targets", "windows"))
DEPENDENCY_FILES = ("src/large_smc_core/c10_stop_policy.py", "src/fx_discovery/features.py",
                    "src/large_smc_v112/targets.py", "src/large_smc_v112/metadata.py",
                    "src/large_smc_v112/windows.py", "src/large_smc_v112/contract.py")
REPORT_SCHEMA = "LOGIC_VERIFICATION_REPORT"
LOGIC_VERIFIED, LOGIC_NOT_VERIFIED = "LOGIC_VERIFIED", "LOGIC_NOT_VERIFIED"
TF = {"D1": dt.timedelta(days=1), "H1": dt.timedelta(hours=1), "M5": dt.timedelta(minutes=5)}
OPPORTUNITY, REJECTED = "OPPORTUNITY", "REJECTED"
# Snapshot states that return BEFORE watch.evaluate_snapshot resolves the point size, so a
# MISSING metadata_source there is the short circuit, not a point-source failure.
PRE_METADATA_REASONS = ("FX_WEEKEND", "SYMBOL_NOT_IN_V1_UNIVERSE")


def signal_snapshot(snap):
    """The pre-delivery-gate (detection) snapshot for a shipped snapshot.

    `watch.gate_opportunity` is `replace(snap, state="REJECTED", reason_codes=(reason,) +
    snap.reason_codes)`: it changes the state and prepends exactly one delivery reason, and
    never touches `opportunity`, `poi` or any id. Inverting it is therefore exact, needs no
    engine change and no monkeypatching, and leaves every other state untouched.
    """
    if snap.state == REJECTED and snap.opportunity and snap.reason_codes:
        return dataclasses.replace(snap, state=OPPORTUNITY, reason_codes=tuple(snap.reason_codes[1:]))
    return snap


def short_circuited_before_metadata(snap) -> bool:
    """True when the snapshot returned before the point-size rule could be evaluated."""
    return snap.point is None and any(code in PRE_METADATA_REASONS for code in snap.reason_codes)


def file_sha256(rel: str) -> Optional[str]:
    path = REPO_ROOT / rel
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def engine_sha256() -> str:
    """sha256 over (path, sha256(bytes)) of every engine file, in fixed order."""
    h = hashlib.sha256()
    for rel in ENGINE_FILES:
        h.update(f"{rel}\0{file_sha256(rel)}\n".encode("utf-8"))
    return h.hexdigest()


def registry_identity(registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """This tree's identity against the pins in strategies/registry.yaml.

    Recorded, never gated: re-recording a registry identity is an owner decision
    (C16 defect register D-LSMC-3/D-LSMC-4), so a mismatch is reported with its exact
    values and left for the owner. A missing registry or entry fails closed to False.
    """
    path = registry_path or (REPO_ROOT / "strategies" / "registry.yaml")
    contract = file_sha256(str(CONTRACT_PATH.relative_to(REPO_ROOT)))
    engine = engine_sha256()
    try:
        entry = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("strategies", {}).get(C.STRATEGY_ID) or {}
    except (OSError, yaml.YAMLError):
        entry = {}
    return {
        "registry_path": str(path.relative_to(REPO_ROOT)) if path.is_absolute() else str(path),
        "registry_version": entry.get("version"),
        "contract_sha256": contract, "registry_contract_sha256": entry.get("contract_sha256"),
        "contract_matches_registry": contract is not None and contract == entry.get("contract_sha256"),
        "engine_sha256": engine, "registry_engine_sha256": entry.get("engine_sha256"),
        "engine_matches_registry": engine == entry.get("engine_sha256"),
        "registry_detection_logic_verification": (entry.get("detection_logic_verification") or {}).get("identity"),
    }


def _na(cid: str, note: str = "no OPPORTUNITY in this case") -> Dict[str, Any]:
    return _check(cid, "opportunity rule", None, None, NOT_APPLICABLE, note)


def _closed(bars: Sequence[Candle], tf: str, now: dt.datetime) -> List[Candle]:
    return [b for b in bars if b.time + TF[tf] <= now]


def _payload(snap) -> Dict[str, Any]:
    return dataclasses.asdict(snap)


# ---------------------------------------------------------------------------------- L1

def l1(case: Dict[str, Any]) -> Dict[str, Any]:
    sym, d1, h1, m5, now = case["symbol"], case["D1"], case["H1"], case["M5"], case["now"]
    gate = l1_determinism(lambda: _payload(evaluate_snapshot(sym, d1, h1, m5, now, target_history=case.get("target_history"))),
                          _closed(m5, "M5", now), now, TF["M5"])
    full = _payload(evaluate_snapshot(sym, d1, h1, m5, now, target_history=case.get("target_history")))
    cut = _payload(evaluate_snapshot(sym, _closed(d1, "D1", now), _closed(h1, "H1", now), _closed(m5, "M5", now), now, target_history=case.get("target_history")))
    gate["checks"].append(_check("L1.truncation_invariance", "unclosed/future bars do not change the snapshot",
                                 full == cut, True, PASS if full == cut else FAIL))
    return _gate("L1", gate["checks"])


# ---------------------------------------------------------------------------------- L2

def l2(spec: Dict[str, Any], case: Dict[str, Any], snap) -> Dict[str, Any]:
    """Contract-vs-engine rule conformance. `snap` is the DETECTION (pre-delivery-gate)
    snapshot -- see `signal_snapshot`; passing the shipped snapshot instead silently
    NOT_APPLICABLEs every opportunity rule whenever delivery rejects it."""
    rules = spec.get("rules") or {}
    checks = [
        _check("L2.identity", "strategy_id@version, alerts-only status",
               f"{spec.get('strategy_id')}@{spec.get('version')} {spec.get('status')}",
               f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION} CANDIDATE_PENDING_OWNER_CONFIRM",
               PASS if (spec.get("strategy_id"), spec.get("version"), spec.get("status")) ==
               (C.STRATEGY_ID, C.STRATEGY_VERSION, "CANDIDATE_PENDING_OWNER_CONFIRM") else FAIL),
        _check("L2.no_authority", "proposal/demo/live authorization all false",
               [spec.get(k) for k in ("proposal_generation_authorized", "demo_authorized", "live_authorized")],
               [False, False, False],
               PASS if [spec.get(k) for k in ("proposal_generation_authorized", "demo_authorized",
                                              "live_authorized")] == [False] * 3
               and C.PROPOSAL_GENERATION_AUTHORIZED is False else FAIL),
        _check("L2.instruments_vt_only", "contract instruments == engine universe (VT MT5 symbols)",
               spec.get("instruments"), list(C.V1_SYMBOLS),
               PASS if [spec.get("runtime_symbols", {}).get(s, s) for s in spec.get("instruments", [])] == list(C.V1_SYMBOLS)
               and not any(s.endswith("USDT") for s in C.V1_SYMBOLS) else FAIL),
        _check("L2.timeframes", "D1/H1/M5", sorted((spec.get("timeframes") or {}).keys()),
               sorted(C.TIMEFRAME_MINUTES), PASS if set(spec.get("timeframes") or {}) == set(C.TIMEFRAME_MINUTES)
               else FAIL),
        _check("L2.swing_k", "SW-A fractal k", (rules.get("swings") or {}).get("k"), C.SWING_K,
               PASS if (rules.get("swings") or {}).get("k") == C.SWING_K else FAIL),
        _check("L2.poi_max_age", "POI max age (trading days)", (rules.get("poi") or {}).get("max_age_trading_days"),
               C.POI_MAX_AGE_TRADING_DAYS,
               PASS if (rules.get("poi") or {}).get("max_age_trading_days") == C.POI_MAX_AGE_TRADING_DAYS else FAIL),
        _check("L2.tie_tolerance", "break tie tolerance (points)",
               (rules.get("break") or {}).get("tie_tolerance_points"), C.TIE_TOLERANCE_POINTS,
               PASS if (rules.get("break") or {}).get("tie_tolerance_points") == C.TIE_TOLERANCE_POINTS else FAIL),
        _check("L2.sweep_choch_window", "sweep -> CHoCH window (M5 bars)",
               rules.get("sweep_to_choch_window_m5_bars"), C.SWEEP_TO_CHOCH_WINDOW_M5,
               PASS if rules.get("sweep_to_choch_window_m5_bars") == C.SWEEP_TO_CHOCH_WINDOW_M5 else FAIL),
        _check("L2.near_poi_band", "ATR(H1,14) x 0.5", rules.get("near_poi_band"),
               {"atr_timeframe": "H1", "atr_period": C.ATR_H1_PERIOD, "multiplier": C.NEAR_POI_BAND_ATR_MULT},
               PASS if rules.get("near_poi_band") == {"atr_timeframe": "H1", "atr_period": C.ATR_H1_PERIOD,
                                                      "multiplier": C.NEAR_POI_BAND_ATR_MULT} else FAIL),
        _check("L2.day_boundary", "trading day boundary", rules.get("day_boundary"),
               {"time": f"{C.DAY_BOUNDARY_HOUR}:00", "tz": C.DAY_BOUNDARY_TZ},
               PASS if (rules.get("day_boundary") or {}).get("time") == f"{C.DAY_BOUNDARY_HOUR}:00"
               and (rules.get("day_boundary") or {}).get("timezone") == C.DAY_BOUNDARY_TZ else FAIL),
        _check("L2.alert_mapping", "alert level mapping", (spec.get("alerts") or {}).get("mapping"), C.ALERT_LEVEL,
               PASS if (spec.get("alerts") or {}).get("mapping") == C.ALERT_LEVEL else FAIL),
        _check("L2.point_source_declared", "contract declares the host capture as the only point source and "
                                            "DATA_ERROR on missing",
               [(rules.get("stop") or {}).get("pip_size", {}).get("point_evidence_path"), (rules.get("stop") or {}).get("pip_size", {}).get("on_missing_or_invalid")],
               ["config/symbol_metadata/host_captured/<SYMBOL>.json", "C10_PIP_SIZE_NOT_EVIDENCED"],
               PASS if (rules.get("stop") or {}).get("pip_size", {}).get("point_evidence_path") == "config/symbol_metadata/host_captured/<SYMBOL>.json"
               and (rules.get("stop") or {}).get("pip_size", {}).get("on_missing_or_invalid") == "C10_PIP_SIZE_NOT_EVIDENCED" else FAIL),
        # Attributed, not assumed: a snapshot that returned before the point rule ran (MARKET_CLOSED,
        # symbol outside the V1 universe) has metadata_source MISSING by construction. Reporting that
        # as a point-source FAIL names the wrong cause; L4.evaluated still fails the case closed.
        _check("L2.point_source", "point from verified host MT5 capture; missing -> DATA_ERROR",
               snap.metadata_source, "HOST_CAPTURED",
               NOT_APPLICABLE if short_circuited_before_metadata(snap)
               else (PASS if snap.metadata_source == "HOST_CAPTURED" and snap.point is not None else FAIL),
               "snapshot returned before point resolution: " + ",".join(snap.reason_codes)
               if short_circuited_before_metadata(snap) else ""),
    ]
    o = snap.opportunity
    if snap.state != "OPPORTUNITY" or not o:
        checks += [_na("L2.direction_matches_bias"), _na("L2.entry_by_reference"), _na("L2.sweep_window_measured"),
                   _na("L2.expiry_session_end"), _na("L2.c10_stop"), _na("L2.c11_target"),
                   _na("L2.c11_creation_anchor")]
        return _gate("L2", checks)
    m5 = _closed(case["M5"], "M5", case["now"])
    idx = o["choch_index"]
    sweep_idx = next((i for i, b in enumerate(m5) if b.time.isoformat() == o["sweep_time"]), None)
    choch_close = close_time(m5[idx], C.TIMEFRAME_MINUTES["M5"])
    want_expiry = opportunity_expiry(case["symbol"], choch_close)
    if C.resolve_pip(case["symbol"])[0] is not None:
        c10 = _check("L2.c10_stop", "C10 stop computed (pip evidenced)", o["stop_c10"], "price",
                     PASS if o["stop_c10"] is not None or o["stop_reason"] else FAIL, o["stop_reason"] or "")
    else:
        c10 = _check("L2.c10_stop", "C10 only where a pip is evidenced; else C10_PIP_SIZE_NOT_EVIDENCED",
                     o["stop_reason"], "C10_PIP_SIZE_NOT_EVIDENCED",
                     PASS if o["stop_c10"] is None and o["stop_reason"] == "C10_PIP_SIZE_NOT_EVIDENCED" else FAIL)
    checks += [
        _check("L2.direction_matches_bias", "OPPORTUNITY direction == H1 bias", o["direction"], snap.bias,
               PASS if o["direction"] == snap.bias and o["direction"] in ("LONG", "SHORT") else FAIL),
        _check("L2.entry_by_reference", "entry = CHoCH bar close", o["entry_reference"], m5[idx].close,
               PASS if o["entry_reference"] == m5[idx].close else FAIL),
        _check("L2.sweep_window_measured", "CHoCH within window of the sweep bar",
               idx - sweep_idx if sweep_idx is not None else None, f"1..{C.SWEEP_TO_CHOCH_WINDOW_M5}",
               PASS if sweep_idx is not None and 0 < idx - sweep_idx <= C.SWEEP_TO_CHOCH_WINDOW_M5 else FAIL),
        _check("L2.expiry_session_end", "expiry = canonical session end after CHoCH close", o["expires_at"],
               want_expiry.isoformat(), PASS if o["expires_at"] == want_expiry.isoformat() else FAIL),
        c10,
        _check("L2.c11_target", "C11 causal fallback target or REJECT_NO_TARGET", o["target_c11"],
               o["target_reason"] or "price",
               PASS if ((o["target_c11"] is None and bool(o["target_reason"]))
                        or (o["target_c11"] is not None and o.get("c11_source") in
                            ("PRIMARY_EXTERNAL_LIQUIDITY", "CONFIRMED_OPPOSING_H1_SWING")
                            and o["target_reason"] is None)) else FAIL),
    ]
    pip, source = C.resolve_pip(case["symbol"])
    selection = o.get('target_selection') or {}
    anchored = (selection.get('creation_bar_close_utc') == choch_close.isoformat()
                and (o['target_c11'] is None or selection.get('selection_mode') == 'STATELESS_CREATION_ANCHORED'))
    checks.append(_check('L2.c11_creation_anchor', 'C11 selection uses the immutable creation cutoff',
                         selection.get('creation_bar_close_utc'), choch_close.isoformat(),
                         PASS if anchored else FAIL))
    checks.append(_check("L2.pip_source", "OD1014 D2 validated host source on every stop",
                         [o.get("pip_size"), o.get("pip_source")], [pip, source],
                         PASS if [o.get("pip_size"), o.get("pip_source")] == [pip, source] else FAIL))
    return _gate("L2", checks)


# ---------------------------------------------------------------------------------- L3

def l3(case: Dict[str, Any], snap) -> Dict[str, Any]:
    """Level geometry. `snap` is the DETECTION (pre-delivery-gate) snapshot."""
    o = snap.opportunity
    if snap.state != "OPPORTUNITY" or not o:
        return _gate("L3", [_na("L3.geometry")])
    m5 = _closed(case["M5"], "M5", case["now"])
    bar = m5[o["choch_index"]]
    long = o["direction"] == "LONG"
    entry, stop, target = o["entry_reference"], o["stop_c10"], o["target_c11"]
    checks = [_check("L3.entry_in_choch_bar", "entry inside the CHoCH bar range", entry, [bar.low, bar.high],
                     PASS if bar.low <= entry <= bar.high else FAIL),
              _check("L3.sweep_extreme_side", "sweep extreme on the loss side of entry", o["sweep_extreme"], entry,
                     PASS if (o["sweep_extreme"] < entry if long else o["sweep_extreme"] > entry) else FAIL)]
    if stop is None:
        checks.append(_check("L3.stop_geometry", "stop geometry", None, None, NOT_APPLICABLE,
                             f"no stop by contract: {o['stop_reason']}"))
    else:
        checks += [
            _check("L3.stop_side", "stop on the loss side of entry", stop, entry,
                   PASS if (stop < entry if long else stop > entry) else FAIL),
            _check("L3.stop_beyond_sweep", "stop at or beyond the sweep extreme", stop, o["sweep_extreme"],
                   PASS if (stop <= o["sweep_extreme"] if long else stop >= o["sweep_extreme"]) else FAIL),
        ]
    if target is None:
        checks.append(_check("L3.target_direction", "target direction", None, None, NOT_APPLICABLE, "REJECT_NO_TARGET"))
    else:
        checks.append(_check("L3.target_direction", "target strictly in trade direction", target, entry,
                             PASS if (target > entry if long else target < entry) else FAIL))
    return _gate("L3", checks)


# ---------------------------------------------------------------------------------- L4

def l4(case: Dict[str, Any], snap) -> Dict[str, Any]:
    now = case["now"]
    m5 = _closed(case["M5"], "M5", now)
    age = (now - (m5[-1].time + TF["M5"])).total_seconds() if m5 else None
    stale_s = C.STALE_AFTER_MINUTES * 60
    evaluated = snap.state not in ("C10_PIP_SIZE_NOT_EVIDENCED", "MARKET_CLOSED")
    return _gate("L4", [
        _check("L4.evaluated", "snapshot evaluated (no DATA_ERROR / MARKET_CLOSED)", snap.state,
               "evaluated state", PASS if evaluated else FAIL, ",".join(snap.reason_codes)),
        _check("L4.history", "H1/M5 minimum history", [len(_closed(case["H1"], "H1", now)), len(m5)],
               [C.MIN_H1_BARS, C.MIN_M5_BARS],
               PASS if len(_closed(case["H1"], "H1", now)) >= C.MIN_H1_BARS and len(m5) >= C.MIN_M5_BARS else FAIL),
        _check("L4.m5_fresh", f"latest M5 closed within {stale_s} s", age, stale_s,
               PASS if age is not None and 0 <= age <= stale_s else FAIL),
        _check("L4.stale_state_consistent", "STALE iff M5 age exceeds the stale limit", snap.state == "STALE",
               age is not None and age > stale_s,
               PASS if (snap.state == "STALE") == (age is not None and age > stale_s) else FAIL),
    ])


# ---------------------------------------------------------------------------------- run

def evaluate_case(spec: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    """One case, both lanes: `state` is the shipped (delivery-gated) snapshot state and
    `signal_state` is the detection state the rule checks are evaluated on."""
    snap = evaluate_snapshot(case["symbol"], case["D1"], case["H1"], case["M5"], case["now"], target_history=case.get("target_history"))
    sig = signal_snapshot(snap)
    o = sig.opportunity or {}
    l2_gate = l2(spec, case, sig)
    if sig is not snap:
        # The delivery gate must change ONLY the state and prepend exactly one reason: if it ever
        # touched detection output, the two lanes would disagree and this fails closed.
        l2_gate = _gate("L2", l2_gate["checks"] + [_check(
            "L2.delivery_gate_preserves_detection",
            "watch.gate_opportunity changes only state + one prepended reason (detection output identical)",
            [snap.opportunity == sig.opportunity, snap.poi == sig.poi, len(snap.reason_codes)],
            [True, True, len(sig.reason_codes) + 1],
            PASS if (snap.opportunity == sig.opportunity and snap.poi == sig.poi
                     and len(snap.reason_codes) == len(sig.reason_codes) + 1) else FAIL,
            f"{sig.state} -> {snap.state}: {snap.reason_codes[0]}")])
    gates = {
        "L1": l1(case), "L2": l2_gate, "L3": l3(case, sig), "L4": l4(case, snap),
        # Fixtures carry no bid/ask or commission: L5 stays advisory WARN (never blocks).
        "L5": l5_cost(None, None, commission_r=None, warn_r=None),
        "L6": (l6_freshness(o.get("expires_at"), f"no closed M5 bar for > {C.STALE_AFTER_MINUTES} min",
                            "POI invalidated / opportunity invalidated or expired")
               if sig.state == OPPORTUNITY else _gate("L6", [_na("L6.freshness")])),
    }
    failures = blocking_failures(gates)
    return {"case_id": case["case_id"], "symbol": case["symbol"], "fixture": case["fixture"],
            "fixture_classification": case["classification"], "evaluated_at": case["now"].isoformat(),
            "state": snap.state, "signal_state": sig.state,
            "delivery_rejection": snap.reason_codes[0] if sig is not snap else None,
            "reason_codes": list(snap.reason_codes), "point": snap.point,
            "metadata_source": snap.metadata_source, "direction": o.get("direction"),
            "entry_reference": o.get("entry_reference"), "stop_c10": o.get("stop_c10"),
            "stop_reason": o.get("stop_reason"), "target_c11": o.get("target_c11"),
            "gate_status": {k: g["status"] for k, g in gates.items()},
            "blocking_failures": failures, "gates": gates}


#: Check ids that exist ONLY as the NOT_APPLICABLE marker of a whole branch: L3 on a
#: non-opportunity snapshot, L3's stop geometry when the contract yields no stop, and L6 on a
#: non-opportunity snapshot. They can never take a PASS/FAIL/WARN verdict, so listing them
#: among the never-exercised checks would bury real coverage gaps next to structural ones.
STRUCTURAL_NA_MARKERS: Tuple[str, ...] = ("L3.geometry", "L3.stop_geometry", "L6.freshness")


def check_coverage(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """How much of the gate was actually exercised: per-check verdict counts across cases.

    A gate status of PASS says nothing about coverage -- a check that never ran is
    NOT_APPLICABLE and still leaves its gate PASS. This makes the vacuous-PASS failure mode
    (every opportunity rule NOT_APPLICABLE while L2/L3/L6 print PASS) visible in the report.
    """
    per_gate: Dict[str, Counter] = {}
    per_check: Dict[str, Counter] = {}
    for r in results:
        for name, gate in (r.get("gates") or {}).items():
            per_gate.setdefault(name, Counter())[gate["status"]] += 1
            for check in gate["checks"]:
                per_check.setdefault(check["id"], Counter())[check["verdict"]] += 1
    evaluated = sum(c[v] for c in per_check.values() for v in (PASS, FAIL, WARN, NOT_EVALUABLE))
    not_applicable = sum(c[NOT_APPLICABLE] for c in per_check.values())
    return {
        "cases": len(results),
        "gate_status_counts": {g: dict(sorted(c.items())) for g, c in sorted(per_gate.items())},
        "check_verdict_counts": {k: dict(sorted(c.items())) for k, c in sorted(per_check.items())},
        "checks_evaluated": evaluated,
        "checks_not_applicable": not_applicable,
        "never_exercised_checks": sorted(
            k for k, c in per_check.items()
            if k not in STRUCTURAL_NA_MARKERS
            and not any(c[v] for v in (PASS, FAIL, WARN, NOT_EVALUABLE))),
        "structural_na_markers": sorted(k for k in per_check if k in STRUCTURAL_NA_MARKERS),
    }


def build_report(cases: Sequence[Dict[str, Any]], *, code_sha: str, generated_at: str) -> Dict[str, Any]:
    spec = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    results = [evaluate_case(spec, c) for c in cases]
    verified = bool(results) and all(not r["blocking_failures"] for r in results)
    covered = sorted({r["symbol"] for r in results if r["signal_state"] == OPPORTUNITY})
    return {
        "schema": REPORT_SCHEMA,
        "strategy": f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION}",
        "verdict": LOGIC_VERIFIED if verified else LOGIC_NOT_VERIFIED,
        "verdict_scope": "rule conformance and internal consistency only; not economic edge, "
                         "not proposal/demo/live authority (all remain false)",
        "lane_semantics": "state = shipped snapshot (delivery-gated); signal_state = detection lane the "
                          "opportunity rules are checked on; opportunity_symbols_covered counts signal_state",
        "contract_path": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "engine_files": list(ENGINE_FILES),
        "engine_sha256": engine_sha256(),
        "engine_file_sha256": {f: file_sha256(f) for f in ENGINE_FILES},
        "dependency_sha256": {f: file_sha256(f) for f in DEPENDENCY_FILES},
        "registry_identity": registry_identity(),
        "code_sha": code_sha,
        "generated_at_utc": generated_at,
        "blocking_gates": list(BLOCKING),
        "opportunity_symbols_covered": covered,
        "operational_opportunity_symbols": sorted(
            {r["symbol"] for r in results if r["state"] == OPPORTUNITY}),
        "c10_stop_geometry_symbols": sorted(
            {r["symbol"] for r in results if r["signal_state"] == OPPORTUNITY} & set(C.C10_PIP_SIZE)),
        "c10_stop_price_symbols": sorted(
            {r["symbol"] for r in results if r["signal_state"] == OPPORTUNITY and r.get("stop_c10") is not None}),
        "check_coverage": check_coverage(results),
        "cases": results,
    }
