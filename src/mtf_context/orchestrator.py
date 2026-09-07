"""Thin multi-timeframe orchestrator: WRAPPER_ONLY, no new detection logic.

Calls existing, already-authoritative AG capabilities per role/timeframe --
market_structure.analyze_structure(), liquidity.liquidity_result(),
supply_demand.validated_order_blocks_for() / fair_value_gaps_for(), and, only when the
caller explicitly supplies a candidate direction and candle context,
entry_confirmation.evaluate_entry_confirmation() -- and normalizes the results into one
MTFContext. Introduces no new candle-fetching path: every closed-candle / no-lookahead
guarantee is inherited verbatim from those modules (see
.agents/skills/multi-timeframe-market-context/SKILL.md "No-lookahead / data quality").

Authority: ADVISORY_ONLY. This module must never import execution/, mt5.management_gateway,
or anything from strategy_engine's decision path -- see test_mtf_context_execution_guard.py.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

from entry_confirmation.engine import evaluate_entry_confirmation
from entry_confirmation.models import EntryConfirmationRequest
from liquidity import liquidity_result
from market_structure import analyze_structure
from supply_demand import fair_value_gaps_for, validated_order_blocks_for

from .models import (
    ALL_ROLES,
    AUTHORITY,
    CONTEXT_READY,
    DATA_ERROR,
    INSUFFICIENT_DATA,
    INVALID_PROFILE,
    PARTIAL_CONTEXT,
    ROLE_EXECUTION,
    ROLE_SETUP,
    SKILL_ID,
    SKILL_VERSION,
    STATUS_DATA_ERROR,
    STATUS_PARTIAL,
    STATUS_VALID,
    InvalidProfileError,
    LayerResult,
    MTFContext,
    MTFProfile,
)

_ZONE_ROLES = (ROLE_SETUP, ROLE_EXECUTION)

_STRUCTURE_VALID_STATUSES = {"VALID", "OK"}


def analyze(
    symbol: str,
    profile: MTFProfile,
    evaluation_time: Optional[dt.datetime] = None,
    candidate_direction: Optional[str] = None,
    candidate_candle: Any = None,
    candle_history: Any = None,
    requested_confirmations: Optional[tuple] = None,
) -> MTFContext:
    """Evaluate `profile`'s roles for `symbol` and return one normalized MTFContext.

    `evaluation_time` is metadata only (recorded on the result) -- it does not select
    which candles are fetched. Every underlying call already returns only CLOSED bars
    as of whenever it actually runs (mt5.market_data.get_latest_candles excludes the
    forming bar at every timeframe); this orchestrator adds no separate as-of filter.

    EXECUTION-role entry-confirmation is only attempted when the caller supplies
    `candidate_direction` + `candidate_candle` + `candle_history` (this orchestrator
    never invents a candidate) -- otherwise that layer reports structure/liquidity/zone
    context only, with confirmation left None.
    """
    role_timeframes = profile.role_timeframes()
    if not role_timeframes:
        raise InvalidProfileError("profile has no roles set -- at least one of macro/bias/working/setup/execution/management is required")
    for role in role_timeframes:
        if role not in ALL_ROLES:
            raise InvalidProfileError(f"unknown role {role!r}, expected one of {ALL_ROLES}")

    evaluation_time = evaluation_time or dt.datetime.now(dt.timezone.utc)

    layers: Dict[str, LayerResult] = {}
    for role, timeframe in role_timeframes.items():
        layers[role] = _evaluate_role(
            role, symbol, timeframe,
            candidate_direction if role == ROLE_EXECUTION else None,
            candidate_candle if role == ROLE_EXECUTION else None,
            candle_history if role == ROLE_EXECUTION else None,
            requested_confirmations if role == ROLE_EXECUTION else None,
        )

    alignment = _compute_alignment(layers)
    data_quality, status = _compute_data_quality(layers)

    return MTFContext(
        skill_id=SKILL_ID,
        skill_version=SKILL_VERSION,
        authority=AUTHORITY,
        symbol=symbol,
        evaluation_time=evaluation_time,
        profile=profile,
        layers=layers,
        alignment=alignment,
        data_quality=data_quality,
        status=status,
    )


def _evaluate_role(
    role: str, symbol: str, timeframe: str,
    candidate_direction: Optional[str], candidate_candle: Any, candle_history: Any,
    requested_confirmations: Optional[tuple],
) -> LayerResult:
    evidence = []
    reason_codes = []
    structure = None
    liq = None
    zones = None
    fvgs = None
    confirmation = None
    bar_close_time = None
    forming_bar_used = False

    try:
        structure = analyze_structure(symbol, timeframe)
        if structure.status in _STRUCTURE_VALID_STATUSES:
            evidence.append(f"structure:{structure.state}")
            bar_close_time = structure.data_end_utc
        else:
            reason_codes.append(f"STRUCTURE:{structure.status}")
    except Exception as exc:  # noqa: BLE001 -- surfaced as a reason_code, never a crash
        reason_codes.append(f"STRUCTURE_EXCEPTION:{type(exc).__name__}")

    try:
        liq = liquidity_result(symbol, timeframe)
        if getattr(liq, "status", "LIQUIDITY_OK") == "LIQUIDITY_OK" or liq is not None:
            if getattr(liq, "levels", None):
                evidence.append(f"liquidity_levels:{len(liq.levels)}")
    except Exception as exc:  # noqa: BLE001
        reason_codes.append(f"LIQUIDITY_EXCEPTION:{type(exc).__name__}")

    if role in _ZONE_ROLES:
        try:
            zones = validated_order_blocks_for(symbol, timeframe)
            if zones:
                evidence.append(f"order_blocks:{len(zones)}")
        except Exception as exc:  # noqa: BLE001
            reason_codes.append(f"ZONES_EXCEPTION:{type(exc).__name__}")

        try:
            fvg_result = fair_value_gaps_for(symbol, timeframe)
            fvgs = getattr(fvg_result, "zones", fvg_result)
            if fvgs:
                evidence.append(f"fvgs:{len(fvgs)}")
        except Exception as exc:  # noqa: BLE001
            reason_codes.append(f"FVG_EXCEPTION:{type(exc).__name__}")

    if role == ROLE_EXECUTION and candidate_direction and candidate_candle is not None:
        try:
            request = EntryConfirmationRequest(
                symbol=symbol, timeframe=timeframe,
                candidate_direction=candidate_direction,
                requested_confirmations=requested_confirmations or (),
                reference_time=candidate_candle.time if hasattr(candidate_candle, "time") else None,
                candidate_candle=candidate_candle,
                candle_history=candle_history or (),
                structure_result=structure,
                liquidity_result=liq,
            )
            confirmation = evaluate_entry_confirmation(request)
            evidence.append(f"confirmation:{getattr(confirmation, 'overall_state', 'UNKNOWN')}")
        except Exception as exc:  # noqa: BLE001
            reason_codes.append(f"CONFIRMATION_EXCEPTION:{type(exc).__name__}")

    if reason_codes and not evidence:
        layer_status = STATUS_DATA_ERROR
    elif reason_codes:
        layer_status = STATUS_PARTIAL
    else:
        layer_status = STATUS_VALID

    return LayerResult(
        role=role, timeframe=timeframe, status=layer_status,
        structure=structure, liquidity=liq, zones=zones, fvgs=fvgs, confirmation=confirmation,
        evidence=evidence, reason_codes=reason_codes,
        bar_close_time=bar_close_time, data_cutoff=None, forming_bar_used=forming_bar_used,
    )


def _compute_alignment(layers: Dict[str, LayerResult]) -> Dict[str, str]:
    pairs = [
        ("macro_to_bias", "MACRO", "BIAS"),
        ("bias_to_working", "BIAS", "WORKING"),
        ("working_to_setup", "WORKING", "SETUP"),
    ]
    alignment = {}
    for key, role_a, role_b in pairs:
        layer_a = layers.get(role_a)
        layer_b = layers.get(role_b)
        if layer_a is None or layer_b is None:
            alignment[key] = "NOT_APPLICABLE"
            continue
        state_a = getattr(layer_a.structure, "state", None)
        state_b = getattr(layer_b.structure, "state", None)
        if state_a is None or state_b is None:
            alignment[key] = "UNKNOWN"
        elif state_a == "STRUCTURE_STATE_UNDEFINED" or state_b == "STRUCTURE_STATE_UNDEFINED":
            alignment[key] = "UNKNOWN"
        elif state_a == state_b:
            alignment[key] = "ALIGNED"
        else:
            alignment[key] = "CONFLICTED"
    return alignment


def _compute_data_quality(layers: Dict[str, LayerResult]) -> tuple:
    statuses = [layer.status for layer in layers.values()]
    if all(s == STATUS_VALID for s in statuses):
        return {"status": STATUS_VALID, "closed_candle_only": True, "reason_codes": []}, CONTEXT_READY
    all_reason_codes = [rc for layer in layers.values() for rc in layer.reason_codes]
    if all(s == STATUS_DATA_ERROR for s in statuses):
        return {"status": STATUS_DATA_ERROR, "closed_candle_only": True, "reason_codes": all_reason_codes}, DATA_ERROR
    return {"status": STATUS_PARTIAL, "closed_candle_only": True, "reason_codes": all_reason_codes}, PARTIAL_CONTEXT
