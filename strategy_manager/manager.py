"""Strategy Manager: resolves a strategy from strategies/registry.yaml, enforces
cycle/execution authority independently of the strategy's own code, builds
MarketContext, and dispatches to the strategy's own adapter. Contains NO strategy
decision rules (Trend/Range/Sweep/entry/SL/TP) -- those only ever get copied in from an
adapter's StrategyResult (spec section 9/13).

Only SESSION_TRADE_V1 has an adapter in this V1 -- any other strategy_id is reported
STRATEGY_ADAPTER_NOT_IMPLEMENTED, never silently evaluated by a fallback path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import yaml

from assistant.models import (
    MODE_LIVE,
    STATUS_BLOCKED,
    STATUS_INVALID_CONTEXT,
    CONTEXT_READY,
    MarketContext,
    StrategyResult,
)
from strategy_manager.context_builder import build_context
from strategy_manager.session_trade_adapter import (
    AdapterRunResult,
    SessionTradeAdapterError,
    run_session_trade_v1,
    to_strategy_result,
)

REGISTRY_PATH = "strategies/registry.yaml"
SESSION_TRADE_CONTRACT_PATH = "strategies/session_trade/contract.yaml"

REASON_STRATEGY_NOT_REGISTERED = "STRATEGY_NOT_REGISTERED"
REASON_STRATEGY_NOT_ACTIVE = "STRATEGY_NOT_ACTIVE"
REASON_STRATEGY_ADAPTER_NOT_IMPLEMENTED = "STRATEGY_ADAPTER_NOT_IMPLEMENTED"
REASON_UNSIGNED_CYCLE = "UNSIGNED_CYCLE"
REASON_CYCLE_NOT_SUPPORTED = "CYCLE_NOT_SUPPORTED"
REASON_LIVE_HARD_BLOCKED = "LIVE_HARD_BLOCKED"
REASON_ADAPTER_INFRASTRUCTURE_FAILURE = "ADAPTER_INFRASTRUCTURE_FAILURE"


@dataclass(frozen=True)
class ManagerResult:
    context: MarketContext
    strategy_result: StrategyResult
    adapter_result: Optional[AdapterRunResult] = None


def _blocked(strategy_id: str, symbol: str, cycle: str, context: MarketContext, *reason_codes: str) -> ManagerResult:
    return ManagerResult(
        context=context,
        strategy_result=StrategyResult(
            strategy_id=strategy_id, strategy_version="unknown", symbol=symbol, cycle=cycle,
            session_date=context.session_date, status=STATUS_BLOCKED, reason_codes=tuple(reason_codes),
        ),
    )


def _load_registry(path: str = REGISTRY_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get("strategies", {})


def _load_session_trade_contract(path: str = SESSION_TRADE_CONTRACT_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate(strategy_id: str, symbol: str, cycle: str, mode: str) -> ManagerResult:
    context = build_context(symbol)
    if context.status != CONTEXT_READY:
        return ManagerResult(
            context=context,
            strategy_result=StrategyResult(
                strategy_id=strategy_id, strategy_version="unknown", symbol=symbol, cycle=cycle,
                session_date=context.session_date, status=STATUS_INVALID_CONTEXT,
                reason_codes=context.reason_codes,
            ),
        )

    registry = _load_registry()
    entry = registry.get(strategy_id)
    if entry is None:
        return _blocked(strategy_id, symbol, cycle, context, REASON_STRATEGY_NOT_REGISTERED)
    if not entry.get("registered"):
        return _blocked(strategy_id, symbol, cycle, context, REASON_STRATEGY_NOT_REGISTERED)
    if not entry.get("active"):
        return _blocked(strategy_id, symbol, cycle, context, REASON_STRATEGY_NOT_ACTIVE)

    if strategy_id != "SESSION_TRADE_V1":
        return _blocked(strategy_id, symbol, cycle, context, REASON_STRATEGY_ADAPTER_NOT_IMPLEMENTED)

    contract = _load_session_trade_contract()
    cycle_spec = (contract.get("supported_cycles") or {}).get(cycle)
    if cycle_spec is None:
        return _blocked(strategy_id, symbol, cycle, context, REASON_CYCLE_NOT_SUPPORTED)
    # Independent, absolute gate (spec section 10/39): an unsigned cycle is blocked for
    # EVERY mode, including ANALYZE_ONLY -- no environment/mode flag overrides this.
    if cycle_spec.get("status") != "ACTIVE" or cycle_spec.get("execution_authority") != "SIGNED":
        return _blocked(strategy_id, symbol, cycle, context, REASON_UNSIGNED_CYCLE)

    if mode == MODE_LIVE:
        return _blocked(strategy_id, symbol, cycle, context, REASON_LIVE_HARD_BLOCKED)

    try:
        adapter_result = run_session_trade_v1(symbol, cycle, mode)
    except SessionTradeAdapterError as exc:
        return _blocked(strategy_id, symbol, cycle, context, REASON_ADAPTER_INFRASTRUCTURE_FAILURE, str(exc))

    strategy_result = to_strategy_result(adapter_result, symbol, cycle)
    return ManagerResult(context=context, strategy_result=strategy_result, adapter_result=adapter_result)
