"""TradeAssistant: the single top-level runtime entry point.

evaluate(strategy_id, symbol, cycle, mode) -> AssistantDecision:
    request -> strategy_manager.manager.evaluate() (registry/cycle authority, context,
    dispatch, normalize) -> map into AssistantDecision status -> journal -> return.

Contains no strategy decision rules and no MT5 calls itself -- both stay owned by
strategy_manager/ and its adapters. This module only coordinates and reports.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from assistant import journal as assistant_journal
from assistant.models import (
    ALL_MODES,
    DECISION_CONTEXT_FAILED,
    DECISION_DUPLICATE_SIGNAL,
    DECISION_EXECUTED,
    DECISION_EXECUTION_BLOCKED,
    DECISION_EXECUTION_FAILED,
    DECISION_NO_SETUP,
    DECISION_ORDER_CHECK_REJECTED,
    DECISION_SHADOW_CHECKED,
    DECISION_TRADE_READY,
    DECISION_UNSIGNED_CYCLE,
    DECISION_UNSIGNED_STRATEGY,
    MODE_ANALYZE_ONLY,
    MODE_SHADOW_DEMO,
    STATUS_BLOCKED,
    STATUS_INVALID_CONTEXT,
    STATUS_NO_SETUP,
    STATUS_TRADE_READY,
    AssistantDecision,
)
from strategy_manager import manager
from strategy_manager.session_trade_adapter import SUCCESSFUL_SUBMIT_OUTCOMES

_UNSIGNED_STRATEGY_REASONS = frozenset({
    manager.REASON_STRATEGY_NOT_REGISTERED, manager.REASON_STRATEGY_NOT_ACTIVE,
    manager.REASON_STRATEGY_ADAPTER_NOT_IMPLEMENTED, manager.REASON_CYCLE_NOT_SUPPORTED,
})


class InvalidRuntimeMode(ValueError):
    pass


def evaluate(strategy_id: str, symbol: str, cycle: str, mode: str) -> AssistantDecision:
    if mode not in ALL_MODES:
        raise InvalidRuntimeMode(f"Unknown mode {mode!r}; must be one of {ALL_MODES}")

    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    result = manager.evaluate(strategy_id, symbol, cycle, mode)
    sr = result.strategy_result
    status, execution_report = _map_status(sr, result.adapter_result, mode)

    decision = AssistantDecision(
        run_id=run_id, strategy_id=strategy_id, strategy_version=sr.strategy_version,
        symbol=symbol, cycle=cycle, timestamp_utc=now, execution_mode=mode, status=status,
        context_status=result.context.status, strategy_status=sr.status,
        setup=sr.setup, direction=sr.direction, entry=sr.entry, stop_loss=sr.stop_loss,
        target=sr.target, signal_id=sr.signal_id, reason_codes=sr.reason_codes,
        execution_report=execution_report,
    )
    assistant_journal.record(decision)
    return decision


def _map_status(sr, adapter_result, mode: str):
    if sr.status == STATUS_INVALID_CONTEXT and adapter_result is None and not sr.reason_codes:
        return DECISION_CONTEXT_FAILED, None
    if sr.status == STATUS_INVALID_CONTEXT:
        # Either MarketContext itself failed, or the adapter reported an environment
        # error (wrong account/trading_mode) -- both are "can't safely proceed" facts.
        return (DECISION_CONTEXT_FAILED if adapter_result is None else DECISION_EXECUTION_BLOCKED), None

    if sr.status == STATUS_BLOCKED:
        reason = sr.reason_codes[0] if sr.reason_codes else None
        if reason == manager.REASON_UNSIGNED_CYCLE:
            return DECISION_UNSIGNED_CYCLE, None
        if reason in _UNSIGNED_STRATEGY_REASONS:
            return DECISION_UNSIGNED_STRATEGY, None
        return DECISION_EXECUTION_BLOCKED, None

    if sr.status == STATUS_NO_SETUP:
        return DECISION_NO_SETUP, None

    if sr.status == STATUS_TRADE_READY:
        return _map_trade_ready(adapter_result, mode)

    return DECISION_EXECUTION_BLOCKED, None


def _map_trade_ready(adapter_result, mode: str):
    if adapter_result is None:
        return DECISION_TRADE_READY, None

    outcome = adapter_result.execution_outcome
    payload = adapter_result.payload

    if outcome == "DUPLICATE_BLOCKED":
        return DECISION_DUPLICATE_SIGNAL, payload
    if outcome == "REFUSED":
        reason_text = str(payload.get("reason", ""))
        if "execution_authority" in reason_text or "unsigned" in reason_text.lower():
            return DECISION_UNSIGNED_CYCLE, payload
        return DECISION_EXECUTION_BLOCKED, payload
    if outcome == "DRY_RUN":
        broker_check = payload.get("broker_check")
        if mode == MODE_ANALYZE_ONLY:
            return DECISION_TRADE_READY, payload
        if mode == MODE_SHADOW_DEMO:
            if broker_check is None:
                return DECISION_TRADE_READY, payload  # defensive: --check somehow not reflected
            return (DECISION_SHADOW_CHECKED, payload) if broker_check.get("retcode") == 0 else (DECISION_ORDER_CHECK_REJECTED, payload)
        return DECISION_TRADE_READY, payload
    if outcome == "ATTEMPTED":
        submit_outcome = payload.get("outcome")
        return (DECISION_EXECUTED, payload) if submit_outcome in SUCCESSFUL_SUBMIT_OUTCOMES else (DECISION_EXECUTION_FAILED, payload)

    return DECISION_TRADE_READY, payload
