"""Logic Gate L1-L6 for ST_LARGE_SMC_V1@1.1.0 (watch/alerts), v1_tickets.logic_gate pattern.

LOGIC_VERIFIED is a statement about rule conformance and internal consistency of the frozen
1.1.0 engine (src/large_smc_watch/) against its contract (strategies/ST_LARGE_SMC_V1_1_1_0.yaml).
It is never a statement about profitability, and it grants no proposal, demo or live authority.
The gate reads the contract and the engine output; it never changes a rule. A contract value
the engine does not implement FAILS (fail closed) instead of being interpreted.

L1-L4 block; L5 (cost) and L6 (freshness fields) are advisory, as in v1_tickets.logic_gate.
Checks that need an OPPORTUNITY are NOT_APPLICABLE on a non-opportunity snapshot.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from large_smc_watch import contract as C
from large_smc_watch import evaluate_snapshot
from large_smc_watch.detect import close_time
from large_smc_watch.watch import session_end
from strategy_engine.session import Candle
from v1_tickets.logic_gate import (
    BLOCKING,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    _check,
    _gate,
    blocking_failures,
    l1_determinism,
    l5_cost,
    l6_freshness,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "strategies" / "ST_LARGE_SMC_V1_1_1_0.yaml"
ENGINE_FILES = tuple(f"src/large_smc_watch/{n}.py" for n in ("__init__", "contract", "detect", "watch"))
DEPENDENCY_FILES = ("src/large_smc_core/c10_stop_policy.py", "src/fx_discovery/features.py")
REPORT_SCHEMA = "LOGIC_VERIFICATION_REPORT"
LOGIC_VERIFIED, LOGIC_NOT_VERIFIED = "LOGIC_VERIFIED", "LOGIC_NOT_VERIFIED"
TF = {"D1": dt.timedelta(days=1), "H1": dt.timedelta(hours=1), "M5": dt.timedelta(minutes=5)}


def file_sha256(rel: str) -> Optional[str]:
    path = REPO_ROOT / rel
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def engine_sha256() -> str:
    """sha256 over (path, sha256(bytes)) of every engine file, in fixed order."""
    h = hashlib.sha256()
    for rel in ENGINE_FILES:
        h.update(f"{rel}\0{file_sha256(rel)}\n".encode("utf-8"))
    return h.hexdigest()


def _na(cid: str, note: str = "no OPPORTUNITY in this case") -> Dict[str, Any]:
    return _check(cid, "opportunity rule", None, None, NOT_APPLICABLE, note)


def _closed(bars: Sequence[Candle], tf: str, now: dt.datetime) -> List[Candle]:
    return [b for b in bars if b.time + TF[tf] <= now]


def _payload(snap) -> Dict[str, Any]:
    return dataclasses.asdict(snap)


# ---------------------------------------------------------------------------------- L1

def l1(case: Dict[str, Any]) -> Dict[str, Any]:
    sym, d1, h1, m5, now = case["symbol"], case["D1"], case["H1"], case["M5"], case["now"]
    gate = l1_determinism(lambda: _payload(evaluate_snapshot(sym, d1, h1, m5, now)),
                          _closed(m5, "M5", now), now, TF["M5"])
    full = _payload(evaluate_snapshot(sym, d1, h1, m5, now))
    cut = _payload(evaluate_snapshot(sym, _closed(d1, "D1", now), _closed(h1, "H1", now), _closed(m5, "M5", now), now))
    gate["checks"].append(_check("L1.truncation_invariance", "unclosed/future bars do not change the snapshot",
                                 full == cut, True, PASS if full == cut else FAIL))
    return _gate("L1", gate["checks"])


# ---------------------------------------------------------------------------------- L2

def l2(spec: Dict[str, Any], case: Dict[str, Any], snap) -> Dict[str, Any]:
    rules = spec.get("rules") or {}
    meta = spec.get("symbol_metadata") or {}
    checks = [
        _check("L2.identity", "strategy_id@version, alerts-only status",
               f"{spec.get('strategy_id')}@{spec.get('version')} {spec.get('status')}",
               f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION} SHADOW_ALERTS_ONLY",
               PASS if (spec.get("strategy_id"), spec.get("version"), spec.get("status")) ==
               (C.STRATEGY_ID, C.STRATEGY_VERSION, "SHADOW_ALERTS_ONLY") else FAIL),
        _check("L2.no_authority", "proposal/demo/live authorization all false",
               [spec.get(k) for k in ("proposal_generation_authorized", "demo_authorized", "live_authorized")],
               [False, False, False],
               PASS if [spec.get(k) for k in ("proposal_generation_authorized", "demo_authorized",
                                              "live_authorized")] == [False] * 3
               and C.PROPOSAL_GENERATION_AUTHORIZED is False else FAIL),
        _check("L2.instruments_vt_only", "contract instruments == engine universe (VT MT5 symbols)",
               spec.get("instruments"), list(C.V1_SYMBOLS),
               PASS if list(spec.get("instruments") or []) == list(C.V1_SYMBOLS)
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
               and (rules.get("day_boundary") or {}).get("tz") == C.DAY_BOUNDARY_TZ else FAIL),
        _check("L2.alert_mapping", "alert level mapping", (spec.get("alerts") or {}).get("mapping"), C.ALERT_LEVEL,
               PASS if (spec.get("alerts") or {}).get("mapping") == C.ALERT_LEVEL else FAIL),
        _check("L2.point_source", "point from verified host MT5 capture; missing -> DATA_ERROR",
               snap.metadata_source, "HOST_CAPTURED",
               PASS if meta.get("on_missing") == "DATA_ERROR" and snap.metadata_source == "HOST_CAPTURED"
               and snap.point is not None else FAIL),
    ]
    o = snap.opportunity
    if snap.state != "OPPORTUNITY" or not o:
        checks += [_na("L2.direction_matches_bias"), _na("L2.entry_by_reference"), _na("L2.sweep_window_measured"),
                   _na("L2.expiry_session_end"), _na("L2.c10_stop"), _na("L2.c11_target")]
        return _gate("L2", checks)
    m5 = _closed(case["M5"], "M5", case["now"])
    idx = o["choch_index"]
    sweep_idx = next((i for i, b in enumerate(m5) if b.time.isoformat() == o["sweep_time"]), None)
    choch_close = close_time(m5[idx], C.TIMEFRAME_MINUTES["M5"])
    want_expiry = session_end(choch_close)
    if case["symbol"] in C.C10_PIP_SIZE:
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
               PASS if (o["target_c11"] is None) == (o["target_reason"] == "REJECT_NO_TARGET") else FAIL),
    ]
    return _gate("L2", checks)


# ---------------------------------------------------------------------------------- L3

def l3(case: Dict[str, Any], snap) -> Dict[str, Any]:
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
    evaluated = snap.state not in ("DATA_ERROR", "MARKET_CLOSED")
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
    snap = evaluate_snapshot(case["symbol"], case["D1"], case["H1"], case["M5"], case["now"])
    o = snap.opportunity or {}
    gates = {
        "L1": l1(case), "L2": l2(spec, case, snap), "L3": l3(case, snap), "L4": l4(case, snap),
        # Fixtures carry no bid/ask or commission: L5 stays advisory WARN (never blocks).
        "L5": l5_cost(None, None, commission_r=None, warn_r=None),
        "L6": (l6_freshness(o.get("expires_at"), f"no closed M5 bar for > {C.STALE_AFTER_MINUTES} min",
                            "POI invalidated / opportunity invalidated or expired")
               if snap.state == "OPPORTUNITY" else _gate("L6", [_na("L6.freshness")])),
    }
    failures = blocking_failures(gates)
    return {"case_id": case["case_id"], "symbol": case["symbol"], "fixture": case["fixture"],
            "fixture_classification": case["classification"], "evaluated_at": case["now"].isoformat(),
            "state": snap.state, "reason_codes": list(snap.reason_codes), "point": snap.point,
            "metadata_source": snap.metadata_source, "direction": o.get("direction"),
            "entry_reference": o.get("entry_reference"), "stop_c10": o.get("stop_c10"),
            "stop_reason": o.get("stop_reason"), "target_c11": o.get("target_c11"),
            "gate_status": {k: g["status"] for k, g in gates.items()},
            "blocking_failures": failures, "gates": gates}


def build_report(cases: Sequence[Dict[str, Any]], *, code_sha: str, generated_at: str) -> Dict[str, Any]:
    spec = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    results = [evaluate_case(spec, c) for c in cases]
    verified = bool(results) and all(not r["blocking_failures"] for r in results)
    covered = sorted({r["symbol"] for r in results if r["state"] == "OPPORTUNITY"})
    return {
        "schema": REPORT_SCHEMA,
        "strategy": f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION}",
        "verdict": LOGIC_VERIFIED if verified else LOGIC_NOT_VERIFIED,
        "verdict_scope": "rule conformance and internal consistency only; not economic edge, "
                         "not proposal/demo/live authority (all remain false)",
        "contract_path": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "engine_files": list(ENGINE_FILES),
        "engine_sha256": engine_sha256(),
        "engine_file_sha256": {f: file_sha256(f) for f in ENGINE_FILES},
        "dependency_sha256": {f: file_sha256(f) for f in DEPENDENCY_FILES},
        "code_sha": code_sha,
        "generated_at_utc": generated_at,
        "blocking_gates": list(BLOCKING),
        "opportunity_symbols_covered": covered,
        "c10_stop_geometry_symbols": sorted(s for s in covered if s in C.C10_PIP_SIZE),
        "cases": results,
    }
