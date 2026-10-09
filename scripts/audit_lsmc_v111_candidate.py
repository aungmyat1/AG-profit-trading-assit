"""Per-symbol L1-L6 shadow audit for ST_LARGE_SMC_V1@1.1.1.

Run from any directory:
    python scripts/audit_lsmc_v111_candidate.py

This is a read-only candidate adapter. It consumes the explicit per-symbol fixtures under
`tests/fixtures/large_smc_v111/`, reuses the frozen 1.1.0 signal pipeline, and evaluates
only the candidate C10/C11/RR deltas. C11 calls the existing core primary target selector;
only an explicit PRIMARY_EXTERNAL_LIQUIDITY result is accepted, after which a confirmed
opposing H1 swing is the sole fallback. The selector's legacy M5 fallback is ignored.

No broker, order, live/demo authority, or alert transport is accessed or enabled.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["AG_EVIDENCE_ROOT"] = str(ROOT)

# Reuse the import-only Linux MetaTrader5 portability shim. No MT5 call is made.
if "MetaTrader5" not in sys.modules:
    _shim_spec = importlib.util.spec_from_file_location("audit_test_conftest", ROOT / "tests/conftest.py")
    if _shim_spec is not None and _shim_spec.loader is not None:
        _shim = importlib.util.module_from_spec(_shim_spec)
        _shim_spec.loader.exec_module(_shim)

import yaml  # noqa: E402

from _lsmc_v111_fixtures import fixture_manifest, fixture_symbols, load_fixture  # noqa: E402
from fx_discovery import features as F  # noqa: E402
from large_smc_core.c10_stop_policy import C10StopPolicyViolation, compute_c10_stop  # noqa: E402
from large_smc_core.target_model import TARGET_TIER_PRIMARY, select_target  # noqa: E402
from large_smc_watch import contract as C  # noqa: E402
from large_smc_watch import evaluate_snapshot  # noqa: E402
from large_smc_watch.watch import session_end  # noqa: E402
from market_structure.config import load_market_structure_config  # noqa: E402
from market_structure.smc_adapter import candles_to_dataframe  # noqa: E402
from market_structure.tiers import (  # noqa: E402
    EXTERNAL_SWING_LENGTH,
    _build_tier,
    _equal_level_tolerance_points,
)
from host_evidence.symbol_metadata import load_record as load_host_symbol_metadata  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from v1_tickets.logic_gate import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    NOT_EVALUABLE,
    PASS,
    WARN,
    l1_determinism,
    l5_cost,
    l6_freshness,
)

CANDIDATE_PATH = ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml"
CRYPTO_WINDOW_PATH = ROOT / "config/v1_tickets/crypto_ticket_v3.yaml"
SYMBOLS = fixture_symbols()
TF_DELTA = {"D1": dt.timedelta(days=1), "H1": dt.timedelta(hours=1), "M5": dt.timedelta(minutes=5)}
NO_TICKET = "NOT_APPLICABLE_NO_TICKET"
C11_PRIMARY = "PRIMARY_EXTERNAL_LIQUIDITY"
C11_H1_FALLBACK = "CONFIRMED_OPPOSING_H1_SWING"


def _broker_symbol_for(spec: dict, symbol: str) -> str:
    """Resolve the candidate's broker-to-canonical alias map without editing runtime code."""
    aliases = spec.get("broker_symbol_aliases") or {}
    return next((broker for broker, canonical in aliases.items() if canonical == symbol), symbol)


def _evaluate_with_captured_points(
    spec: dict,
    symbol: str,
    d1: Sequence[Candle],
    h1: Sequence[Candle],
    m5: Sequence[Candle],
    now: dt.datetime,
):
    """Run the frozen signal evaluator with host-captured point inputs, locally scoped.

    The resolver override exists only during this read-only audit call and is always restored;
    no production/runtime resolver behavior is changed.
    """
    original_resolver = C.resolve_point

    def captured_resolver(runtime_symbol: str):
        record = load_host_symbol_metadata(runtime_symbol)
        if record is None:
            return None, "MISSING"
        return float(record["fields"]["point"]), "HOST_CAPTURED"

    # The 1.1.0 runtime universe is VT broker names only (BTCUSD/ETHUSD); the candidate keeps
    # its canonical names, so the runtime is called with the broker alias and relabelled back.
    C.resolve_point = captured_resolver
    try:
        snap = evaluate_snapshot(_broker_symbol_for(spec, symbol), d1, h1, m5, now)
    finally:
        C.resolve_point = original_resolver
    return replace(snap, symbol=symbol)


def _parse_candidate_time(value: Any) -> Optional[dt.datetime]:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _crypto_session_end(at: dt.datetime, config: dict) -> dt.datetime:
    """Candidate-only expiry from the configured crypto ticket windows; no runtime wiring."""
    window = config.get("window") or {}
    if window.get("kind") == "MULTI":
        windows = list(window.get("windows") or [])
    elif window.get("kind") == "LOCAL_WEEKDAY":
        windows = [window]
    else:
        raise ValueError(f"unsupported crypto window kind {window.get('kind')!r}")
    windows = [w for w in windows if isinstance(w, dict) and w.get("enabled", True) is not False]
    if not windows:
        raise ValueError("no enabled crypto ticket windows")

    utc = at.astimezone(dt.timezone.utc)
    candidates: List[dt.datetime] = []
    for spec in windows:
        zone = ZoneInfo(spec["timezone"])
        start = dt.time(*map(int, str(spec["start"]).split(":")))
        end = dt.time(*map(int, str(spec["end"]).split(":")))
        weekdays = {int(day) for day in spec["weekdays"]}
        if not weekdays or not weekdays <= set(range(1, 8)) or start == end:
            raise ValueError("invalid crypto window weekdays or duration")
        local_date = utc.astimezone(zone).date()
        for day_offset in range(-1, 15):
            start_date = local_date + dt.timedelta(days=day_offset)
            if start_date.isoweekday() not in weekdays:
                continue
            end_date = start_date + dt.timedelta(days=1 if end <= start else 0)
            start_at = dt.datetime.combine(start_date, start, tzinfo=zone)
            end_at = dt.datetime.combine(end_date, end, tzinfo=zone)
            if start_at <= utc < end_at:
                return end_at.astimezone(dt.timezone.utc)
            if end_at > utc:
                candidates.append(end_at.astimezone(dt.timezone.utc))
    if not candidates:
        raise ValueError("no future crypto ticket-window end")
    return min(candidates)


def _candidate_ticket(
    opportunity: dict,
    *,
    symbol: str,
    evaluated_at: Any,
    trading_date: str,
    metadata_source: Optional[str],
    strategy_version: str,
) -> Dict[str, Any]:
    """Candidate-only ticket projection for the shadow audit; never enters runtime paths."""
    signal_open = _parse_candidate_time(opportunity.get("choch_time"))
    signal_close = signal_open + dt.timedelta(minutes=5) if signal_open is not None else None
    direction = opportunity.get("direction")
    gaps = []
    if direction not in ("LONG", "SHORT"):
        gaps.append("DIRECTION_UNAVAILABLE")
    if opportunity.get("entry_reference") is None:
        gaps.append("ENTRY_UNAVAILABLE")
    if opportunity.get("stop_c10") is None:
        gaps.append("STOP_UNAVAILABLE")
    if opportunity.get("target_c11") is None:
        gaps.append("TP_UNAVAILABLE")
    if signal_close is None:
        gaps.append("TRIGGER_TIME_UNAVAILABLE")
    if not opportunity.get("expires_at"):
        gaps.append("EXPIRY_UNAVAILABLE")
    complete = not gaps
    return {
        "schema": "LSMC_V111_CANDIDATE_TICKET_V1",
        "schema_status": "COMPLETE" if complete else "SCHEMA_GAP",
        "schema_gaps": gaps,
        "strategy_id": "ST_LARGE_SMC_V1",
        "strategy_version": strategy_version,
        "symbol": symbol,
        "cycle": "LSMC_V111_CANDIDATE_AUDIT",
        "session_date": trading_date,
        "decision": "READY" if complete else "BLOCKED",
        "reason_code": "SETUP_CONFIRMED" if complete else (gaps[0] if gaps else None),
        "direction": direction,
        "entry": opportunity.get("entry_reference"),
        "stop_loss": opportunity.get("stop_c10"),
        "tp1": opportunity.get("target_c11"),
        "tp2": None,
        "signal_timestamp": opportunity.get("choch_time"),
        "signal_close_utc": signal_close.isoformat() if signal_close is not None else None,
        "evaluated_at": evaluated_at,
        "expires_at": opportunity.get("expires_at"),
        "valid_until": opportunity.get("expires_at"),
        "stale_if": {
            "no_closed_m5_bar_for_more_than_minutes": C.STALE_AFTER_MINUTES,
            "action": "SUSPEND_THEN_EXPIRE",
        },
        "invalid_if": {
            "after_choch_close_beyond_sweep_extreme": {
                "direction": direction,
                "operator": {"LONG": "<", "SHORT": ">"}.get(direction),
                "price": opportunity.get("sweep_extreme"),
            }
        },
        "metadata_source": metadata_source,
        "stop_source": "C10" if opportunity.get("stop_c10") is not None else None,
        "target_source": "C11" if opportunity.get("target_c11") is not None else None,
        "c11_source": opportunity.get("target_c11_source"),
        "delivery_mode": "AUDIT_ONLY",
        "proposal_eligibility": "NONE",
        "execution_authorized": False,
        "demo_authorized": False,
        "live_authorized": False,
    }


def _check(
    cid: str,
    verdict: str,
    value: Any = None,
    expected: Any = None,
    note: str = "",
) -> Dict[str, Any]:
    return {"id": cid, "verdict": verdict, "value": value, "expected": expected, "note": note}


def _gate(name: str, checks: List[Dict[str, Any]], *, advisory: bool = False) -> Dict[str, Any]:
    verdicts = [check["verdict"] for check in checks]
    if advisory:
        status = WARN if any(v in (FAIL, NOT_EVALUABLE, WARN) for v in verdicts) else PASS
    else:
        status = FAIL if any(v in (FAIL, NOT_EVALUABLE) for v in verdicts) else (WARN if WARN in verdicts else PASS)
    return {"gate": name, "status": status, "checks": checks}


def _candidate_stop(
    spec: dict,
    symbol: str,
    opportunity: dict,
    m5: Sequence[Candle],
) -> Tuple[Optional[float], str]:
    """Require captured point provenance, then a separately owner-confirmed pip size.

    Captured points are provenance only: this function never converts a point, digit
    count, asset class, or broker convention into a pip size.
    """
    unit = (spec.get("symbol_metadata") or {}).get(symbol) or {}
    broker_symbol = _broker_symbol_for(spec, symbol)
    record = load_host_symbol_metadata(broker_symbol)
    if record is None:
        return None, "C10_PIP_SIZE_NOT_EVIDENCED"
    captured_point = record.get("fields", {}).get("point")
    configured_point = unit.get("point") if unit.get("point_status") == "HOST_CAPTURED" else None
    if unit.get("broker_metadata_status") == "HOST_CAPTURED":
        configured_point = unit.get("broker_point")
    if (
        not isinstance(captured_point, (int, float))
        or isinstance(captured_point, bool)
        or not math.isfinite(float(captured_point))
        or float(captured_point) <= 0
        or not isinstance(configured_point, (int, float))
        or isinstance(configured_point, bool)
        or not math.isclose(float(configured_point), float(captured_point), rel_tol=0.0, abs_tol=1e-15)
    ):
        return None, "C10_PIP_SIZE_NOT_EVIDENCED"

    pip_size = unit.get("pip_size")
    if (
        unit.get("pip_size_status") != "CONFIRMED"
        or not isinstance(pip_size, (int, float))
        or isinstance(pip_size, bool)
        or pip_size <= 0
    ):
        return None, "PIP_SIZE_UNCONFIRMED"

    index = opportunity.get("choch_index")
    if not isinstance(index, int) or index < 0 or index >= len(m5):
        return None, "MISSING_ATR_DATA"
    try:
        result = compute_c10_stop(
            direction=opportunity.get("direction"),
            invalidation_price=opportunity.get("sweep_extreme"),
            bid=None,
            ask=None,
            m5_candles=m5[: index + 1],
            pip_size=float(pip_size),  # always explicit; never allow the core EURUSD default
        )
    except C10StopPolicyViolation as exc:
        return None, exc.reason_code
    return result.stop_price, ""


def _external_tier(spec: dict, symbol: str, m5: Sequence[Candle]):
    """Build the existing EXTERNAL tier from closed candles and the spec's broker alias."""
    if len(m5) < 2 * EXTERNAL_SWING_LENGTH + 1:
        return None, "INSUFFICIENT_EXTERNAL_STRUCTURE_HISTORY"
    broker_symbol = _broker_symbol_for(spec, symbol)
    host_meta = load_host_symbol_metadata(broker_symbol)
    if host_meta is None:
        return None, "C11_TICK_SIZE_METADATA_UNAVAILABLE"
    # The core structure tier's HH/HL tie tolerance is defined in captured tick-size
    # units. This value is C11 structure metadata only; it is never converted to pip_size.
    tick_size = float(host_meta["fields"]["trade_tick_size"])
    tolerance_price = _equal_level_tolerance_points() * tick_size
    config = load_market_structure_config()
    try:
        tier = _build_tier(
            candles_to_dataframe(m5),
            "EXTERNAL",
            EXTERNAL_SWING_LENGTH,
            config.close_break,
            tolerance_price,
        )
    except Exception as exc:  # candidate audit reports structure failure; no invented target
        return None, f"EXTERNAL_STRUCTURE_ERROR:{type(exc).__name__}"
    return tier, ""


def _h1_fallback_target(
    direction: Optional[str],
    anchor: Any,
    h1: Sequence[Candle],
) -> Dict[str, Any]:
    if direction not in ("LONG", "SHORT") or not isinstance(anchor, (int, float)) or not h1:
        return {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": None,
            "reason": "TARGET_INPUT_UNAVAILABLE",
        }

    last_closed_index = len(h1) - 1
    swings = F.swings(h1, C.SWING_K)
    candidates = []
    for swing in swings:
        if swing.known_at > last_closed_index:
            continue
        opposing = swing.kind == ("high" if direction == "LONG" else "low")
        beyond = swing.price > anchor if direction == "LONG" else swing.price < anchor
        if opposing and beyond:
            candidates.append(swing)
    if not candidates:
        return {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": None,
            "reason": "TARGET_UNAVAILABLE",
        }

    distances = [abs(swing.price - anchor) for swing in candidates]
    nearest_distance = min(distances)
    nearest = [
        swing
        for swing, distance in zip(candidates, distances)
        if math.isclose(distance, nearest_distance, rel_tol=0.0, abs_tol=1e-12)
    ]
    if len(nearest) != 1:
        return {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": None,
            "reason": "AMBIGUOUS_TARGET",
        }
    chosen = nearest[0]
    return {
        "price": float(chosen.price),
        "tier": "FALLBACK_H1_SWING",
        "source": "fx_discovery.features.swings",
        "c11_source": C11_H1_FALLBACK,
        "reason": "CONFIRMED_OPPOSING_H1_SWING",
        "swing_index": chosen.index,
        "known_at_index": chosen.known_at,
        "kind": chosen.kind,
    }


def _candidate_target(
    spec: dict,
    opportunity: dict,
    h1: Sequence[Candle],
    m5: Sequence[Candle],
) -> Dict[str, Any]:
    """Call core C11; accept only its primary external tier, then use causal H1 SW-A."""
    direction = opportunity.get("direction")
    anchor = opportunity.get("entry_reference")
    external, structure_note = _external_tier(spec, opportunity.get("symbol", ""), m5)
    core = select_target(
        direction=direction,
        anchor_price=float(anchor) if isinstance(anchor, (int, float)) else float("nan"),
        symbol=opportunity.get("symbol", ""),
        timeframe="M5",
        external_tier=external,
        m5_candles=m5,
    )
    core_details = {
        "core_selector_tier": core.target_tier,
        "core_selector_reason": core.reason,
        "core_selector_source": core.target_source,
        "core_selector_source_id": core.target_source_id,
        "structure_note": structure_note or None,
    }
    if (
        core.found
        and core.target_tier == TARGET_TIER_PRIMARY
        and isinstance(core.target_price, (int, float))
    ):
        return {
            "price": float(core.target_price),
            "tier": TARGET_TIER_PRIMARY,
            "source": core.target_source or "large_smc_core.target_model.select_target",
            "c11_source": C11_PRIMARY,
            "reason": core.reason,
            "source_id": core.target_source_id,
            "status_at_selection": core.target_status_at_selection,
            "evidence_timestamp": core.target_evidence_timestamp.isoformat()
            if core.target_evidence_timestamp
            else None,
            **core_details,
        }

    # The target model's FALLBACK_M5_SWING is deliberately ignored here. Candidate C11
    # requires the nearest confirmed opposing H1 swing when the primary is unavailable.
    fallback = _h1_fallback_target(direction, anchor, h1)
    fallback["core_selector_tier"] = core.target_tier
    fallback["core_selector_reason"] = core.reason
    fallback["core_selector_source"] = core.target_source
    fallback["core_selector_source_id"] = core.target_source_id
    fallback["structure_note"] = structure_note or None
    if fallback.get("price") is not None:
        fallback["reason"] = "PRIMARY_UNAVAILABLE_H1_FALLBACK"
        fallback["core_m5_fallback_ignored"] = core.target_tier == "FALLBACK_M5_SWING"
    return fallback


def _candidate_evaluation(spec: dict, bars: Dict[str, Any], crypto_config: dict) -> Dict[str, Any]:
    symbol = bars["symbol"]
    d1, h1, m5 = bars["D1"], bars["H1"], bars["M5"]
    now = bars["evaluated_at"]
    base = _evaluate_with_captured_points(spec, symbol, d1, h1, m5, now)
    has_opportunity = isinstance(base.opportunity, dict) and bool(base.opportunity)
    opportunity = dict(base.opportunity or {})

    if has_opportunity:
        opportunity["symbol"] = symbol
        signal_open = _parse_candidate_time(opportunity.get("choch_time"))
        signal_close = signal_open + dt.timedelta(minutes=5) if signal_open is not None else None
        if signal_close is not None:
            expiry = (
                _crypto_session_end(signal_close, crypto_config)
                if _broker_symbol_for(spec, symbol) in C.CRYPTO_SYMBOLS
                else session_end(signal_close)
            )
            opportunity["expires_at"] = expiry.isoformat()
        stop, stop_reason = _candidate_stop(spec, symbol, opportunity, m5)
        target = _candidate_target(spec, opportunity, h1, m5)
        opportunity["stop_c10"] = stop
        opportunity["stop_reason"] = stop_reason or None
        opportunity["target_c11"] = target.get("price")
        opportunity["target_c11_source"] = target.get("c11_source")
        opportunity["target_c11_source_id"] = target.get("source_id")
        opportunity["target_reason"] = target.get("reason") if target.get("price") is None else None
    else:
        stop, stop_reason = None, "NO_TICKET"
        target = {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": "NO_TICKET",
            "reason": "NO_OPPORTUNITY_TICKET",
            "core_selector_tier": None,
        }

    entry = opportunity.get("entry_reference")
    stop_distance = abs(entry - stop) if entry is not None and stop is not None else None
    reward_distance = (
        abs(target["price"] - entry)
        if entry is not None and target.get("price") is not None
        else None
    )
    computed_rr = (
        reward_distance / stop_distance
        if reward_distance is not None and stop_distance not in (None, 0)
        else None
    )
    rr_rules = spec.get("rules", {}).get("reward_risk") or {}
    minimum_rr = rr_rules.get("minimum_rr")
    minimum_rr_status = rr_rules.get("minimum_rr_status")
    if not has_opportunity:
        rr_status = NO_TICKET
    elif not isinstance(minimum_rr, (int, float)) or isinstance(minimum_rr, bool):
        rr_status = "RR_MINIMUM_UNCONFIRMED"
    elif computed_rr is None:
        rr_status = "RR_UNDEFINED_C10_STOP_UNAVAILABLE" if stop is None else "RR_UNDEFINED"
    elif computed_rr < float(minimum_rr):
        rr_status = "RR_BELOW_SPEC_MINIMUM"
    elif minimum_rr_status != "CONFIRMED":
        rr_status = "RR_AT_OR_ABOVE_PENDING_MINIMUM"
    else:
        rr_status = "PASS"

    ticket = _candidate_ticket(
        opportunity,
        symbol=symbol,
        evaluated_at=base.evaluated_at,
        trading_date=now.date().isoformat(),
        metadata_source=base.metadata_source,
        strategy_version=str(spec["version"]),
    )
    ticket["candidate_status"] = spec["status"]
    ticket["c11_source"] = target.get("c11_source")
    ticket["c11_selector_tier"] = target.get("core_selector_tier")
    ticket["c11_selector_source"] = target.get("core_selector_source")
    return {
        "snapshot": base,
        "has_opportunity": has_opportunity,
        "opportunity": opportunity,
        "target": target,
        "stop": stop,
        "stop_reason": stop_reason,
        "computed_rr": computed_rr,
        "minimum_rr": minimum_rr,
        "minimum_rr_status": minimum_rr_status,
        "rr_status": rr_status,
        "ticket": ticket,
    }


def _l2(spec: dict, bars: Dict[str, Any], result: dict) -> Dict[str, Any]:
    if not result["has_opportunity"]:
        return {
            "gate": "L2",
            "status": NO_TICKET,
            "checks": [_check("L2.ticket_rules", NOT_APPLICABLE, None, None, "No OPPORTUNITY ticket in this fixture.")],
        }
    opportunity, target = result["opportunity"], result["target"]
    identity_ok = (
        spec.get("strategy_id") == "ST_LARGE_SMC_V1"
        and spec.get("version") == "1.1.1"
        and spec.get("status") == "CANDIDATE_PENDING_OWNER_CONFIRM"
    )
    required_tfs = ("D1", "H1", "M5")
    now = bars["evaluated_at"]
    tfs_ok = all(
        bars[tf] and all(bar.time + TF_DELTA[tf] <= now for bar in bars[tf])
        for tf in required_tfs
    )
    direction_ok = (
        opportunity.get("direction") in ("LONG", "SHORT")
        and opportunity.get("direction") == result["snapshot"].bias
    )
    index = opportunity.get("choch_index")
    entry_ok = (
        isinstance(index, int)
        and 0 <= index < len(bars["M5"])
        and opportunity.get("entry_reference") == bars["M5"][index].close
    )
    stop_ok = result["stop"] is not None
    target_ok = target.get("price") is not None
    return _gate(
        "L2",
        [
            _check(
                "L2.candidate_identity",
                PASS if identity_ok else FAIL,
                f"{spec.get('strategy_id')}@{spec.get('version')}",
                "ST_LARGE_SMC_V1@1.1.1",
            ),
            _check(
                "L2.closed_declared_timeframes",
                PASS if tfs_ok else FAIL,
                {tf: len(bars[tf]) for tf in required_tfs},
                "closed D1/H1/M5 inputs",
            ),
            _check(
                "L2.h1_bias_direction",
                PASS if direction_ok else FAIL,
                opportunity.get("direction"),
                result["snapshot"].bias,
            ),
            _check(
                "L2.entry_by_reference",
                PASS if entry_ok else FAIL,
                opportunity.get("entry_reference"),
                "CHoCH bar close",
            ),
            _check(
                "L2.c10_pip_size_and_stop",
                PASS if stop_ok else FAIL,
                result["stop"],
                "host-captured point provenance plus owner-confirmed pip_size",
                result["stop_reason"],
            ),
            _check(
                "L2.c11_target",
                PASS if target_ok else FAIL,
                target.get("price"),
                "core PRIMARY_EXTERNAL_LIQUIDITY or confirmed opposing H1 swing",
                target.get("c11_source", ""),
            ),
        ],
    )


def _l3(bars: Dict[str, Any], result: dict) -> Dict[str, Any]:
    if not result["has_opportunity"]:
        return {
            "gate": "L3",
            "status": NO_TICKET,
            "checks": [_check("L3.ticket_geometry", NOT_APPLICABLE, None, None, "No OPPORTUNITY ticket in this fixture.")],
        }
    opportunity, target, stop = result["opportunity"], result["target"], result["stop"]
    direction = opportunity.get("direction")
    entry = opportunity.get("entry_reference")
    index = opportunity.get("choch_index")
    signal = bars["M5"][index] if isinstance(index, int) and 0 <= index < len(bars["M5"]) else None
    long = direction == "LONG"
    stop_side = stop is not None and entry is not None and (stop < entry if long else stop > entry)
    stop_beyond_anchor = (
        stop is not None
        and opportunity.get("sweep_extreme") is not None
        and (stop <= opportunity["sweep_extreme"] if long else stop >= opportunity["sweep_extreme"])
    )
    entry_match = signal is not None and entry is not None and entry == signal.close
    target_side = target.get("price") is not None and entry is not None and (
        target["price"] > entry if long else target["price"] < entry
    )
    rr_verdict = PASS if result["rr_status"] == "PASS" else FAIL
    if result["rr_status"] == "RR_AT_OR_ABOVE_PENDING_MINIMUM":
        rr_verdict = WARN
    return _gate(
        "L3",
        [
            _check("L3.entry_matches_choch_close", PASS if entry_match else FAIL, entry, signal.close if signal else None),
            _check("L3.stop_loss_side", PASS if stop_side else FAIL, stop, "loss side of entry", result["stop_reason"]),
            _check("L3.stop_beyond_sweep_anchor", PASS if stop_beyond_anchor else FAIL, stop, opportunity.get("sweep_extreme")),
            _check("L3.target_direction", PASS if target_side else FAIL, target.get("price"), "strictly in trade direction"),
            _check(
                "L3.rr_minimum",
                rr_verdict,
                result["computed_rr"],
                {"minimum_rr": result["minimum_rr"], "status": result["minimum_rr_status"]},
                result["rr_status"],
            ),
        ],
    )


def _l4(snapshot, bars: Dict[str, Any], ticket: Dict[str, Any], config: dict, has_opportunity: bool) -> Dict[str, Any]:
    now = bars["evaluated_at"]
    closed = all(
        bars[tf] and all(bar.time + TF_DELTA[tf] <= now for bar in bars[tf])
        for tf in TF_DELTA
    )
    last_close = bars["M5"][-1].time + TF_DELTA["M5"] if bars["M5"] else None
    age_s = (now - last_close).total_seconds() if last_close else None
    fresh = age_s is not None and 0 <= age_s <= C.STALE_AFTER_MINUTES * 60
    checks = [
        _check("L4.closed_d1_h1_m5", PASS if closed else FAIL, {tf: len(bars[tf]) for tf in TF_DELTA}, "closed D1/H1/M5 bars"),
        _check("L4.m5_fresh", PASS if fresh else FAIL, age_s, C.STALE_AFTER_MINUTES * 60),
    ]
    if has_opportunity:
        try:
            signal_close = dt.datetime.fromisoformat(ticket["signal_close_utc"])
            expected_expiry = (
                _crypto_session_end(signal_close, config)
                if snapshot.symbol in C.CRYPTO_SYMBOLS + ("BTCUSDT", "ETHUSDT")  # candidate canonical names
                else session_end(signal_close)
            )
            actual_expiry = dt.datetime.fromisoformat(ticket["expires_at"])
            expiry_ok = actual_expiry == expected_expiry
            checks.append(
                _check("L4.ticket_window_expiry", PASS if expiry_ok else FAIL, actual_expiry.isoformat(), expected_expiry.isoformat())
            )
        except (KeyError, TypeError, ValueError):
            checks.append(_check("L4.ticket_window_expiry", FAIL, ticket.get("expires_at"), "configured session end", "Missing/invalid ticket expiry."))
    else:
        checks.append(_check("L4.ticket_window_expiry", NOT_APPLICABLE, None, None, "No OPPORTUNITY ticket."))
    return _gate("L4", checks)


def _l6(ticket: Dict[str, Any], has_opportunity: bool) -> Dict[str, Any]:
    if not has_opportunity:
        return {
            "gate": "L6",
            "status": NO_TICKET,
            "checks": [_check("L6.ticket_freshness", NOT_APPLICABLE, None, None, "No OPPORTUNITY ticket."),],
        }
    return l6_freshness(ticket.get("valid_until"), ticket.get("stale_if"), ticket.get("invalid_if"))


def _classification_by_symbol() -> Dict[str, dict]:
    return {item["symbol"]: item for item in fixture_manifest()["sources"]}


def run() -> List[Dict[str, Any]]:
    spec = yaml.safe_load(CANDIDATE_PATH.read_text(encoding="utf-8"))
    crypto_config = yaml.safe_load(CRYPTO_WINDOW_PATH.read_text(encoding="utf-8"))
    provenance = _classification_by_symbol()
    rows = []
    for symbol in SYMBOLS:
        bars = load_fixture(symbol)
        source = provenance[symbol]
        result = _candidate_evaluation(spec, bars, crypto_config)
        now = bars["evaluated_at"]

        def build() -> Dict[str, Any]:
            rebuilt = _candidate_evaluation(spec, bars, crypto_config)
            snap = rebuilt["snapshot"]
            return {
                "symbol": symbol,
                "state": snap.state,
                "direction": rebuilt["opportunity"].get("direction"),
                "entry": rebuilt["opportunity"].get("entry_reference"),
                "stop": rebuilt["stop"],
                "stop_reason": rebuilt["stop_reason"],
                "target": rebuilt["target"],
                "rr_status": rebuilt["rr_status"],
                "owner_confirmation": spec["owner_confirmation"],
            }

        l1 = l1_determinism(build, bars["M5"], now, dt.timedelta(minutes=5))
        l2 = _l2(spec, bars, result)
        l3 = _l3(bars, result)
        l4 = _l4(result["snapshot"], bars, result["ticket"], crypto_config, result["has_opportunity"])
        # Fixture sets contain no bid/ask, spread, or commission; L5 remains advisory WARN.
        l5 = l5_cost(None, None, commission_r=None, warn_r=None)
        l6 = _l6(result["ticket"], result["has_opportunity"])
        symbol_metadata = (spec.get("symbol_metadata", {}).get(symbol) or {})
        pip_status = symbol_metadata.get("pip_size_status")
        point_status = (
            "HOST_CAPTURED"
            if symbol_metadata.get("point_status") == "HOST_CAPTURED"
            or symbol_metadata.get("broker_metadata_status") == "HOST_CAPTURED"
            else symbol_metadata.get("point_status", "MISSING")
        )
        point_source = symbol_metadata.get("point_source") or symbol_metadata.get("broker_point_source")
        rows.append({
            "symbol": symbol,
            "broker_symbol": _broker_symbol_for(spec, symbol),
            "point_status": point_status,
            "point_source": point_source,
            "fixture_file": bars["fixture_file"],
            "fixture_classification": source["classification"],
            "timeframe_sources": source.get("timeframes", {}),
            "state": result["snapshot"].state,
            "opportunity_ticket": result["has_opportunity"],
            "direction": result["opportunity"].get("direction"),
            "entry": result["opportunity"].get("entry_reference"),
            "C10": result["stop_reason"] if result["has_opportunity"] else NO_TICKET,
            "pip_size_status": pip_status,
            "C11_source": result["target"].get("c11_source"),
            "C11_selector_tier": result["target"].get("core_selector_tier"),
            "C11_selector_reason": result["target"].get("core_selector_reason"),
            "C11_target_tier": result["target"].get("tier"),
            "C11_target_price": result["target"].get("price"),
            "C11_target_source_id": result["target"].get("source_id"),
            "C11_status_at_selection": result["target"].get("status_at_selection"),
            "C11_target_reason": result["target"].get("reason"),
            "C11_legacy_m5_fallback_ignored": result["target"].get("core_m5_fallback_ignored", False),
            "ticket_c11_source": result["ticket"].get("c11_source"),
            "ticket_signal_timestamp": result["ticket"].get("signal_timestamp"),
            "RR_minimum": result["minimum_rr"],
            "RR_minimum_status": result["minimum_rr_status"],
            "RR": result["rr_status"],
            "computed_RR": result["computed_rr"],
            "owner_confirmation": spec["owner_confirmation"],
            "L1": l1["status"], "L2": l2["status"], "L3": l3["status"],
            "L4": l4["status"], "L5": l5["status"], "L6": l6["status"],
            "gate_notes": {
                gate["gate"]: [
                    check["id"] + (":" + check["note"] if check.get("note") else "")
                    for check in gate["checks"]
                    if check["verdict"] not in (PASS, NOT_APPLICABLE)
                ]
                for gate in (l1, l2, l3, l4, l5, l6)
            },
            "gates": {gate["gate"]: gate for gate in (l1, l2, l3, l4, l5, l6)},
        })
    return rows


def main() -> None:
    rows = run()
    print("| Symbol | Fixture | State | Ticket | C10 | C11 source / selector tier | C11 target | RR | L1 | L2 | L3 | L4 | L5 | L6 |")
    print("|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        selector = f"{row['C11_source']} / {row['C11_selector_tier']}"
        target = (
            f"{row['C11_target_tier']}@{row['C11_target_price']}"
            if row["C11_target_price"] is not None
            else row["C11_target_reason"]
        )
        print(
            f"| {row['symbol']} | {row['fixture_classification']} | {row['state']} "
            f"| {'YES' if row['opportunity_ticket'] else 'NO'} | {row['C10']} | {selector} | {target} "
            f"| {row['RR']} (min {row['RR_minimum']} {row['RR_minimum_status']}) "
            f"| {row['L1']} | {row['L2']} | {row['L3']} | {row['L4']} | {row['L5']} | {row['L6']} |"
        )
    print("\nJSON:")
    print(json.dumps(rows, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
