"""evaluate_m5_execution() -- orchestration only. Reuses the existing live
SMC_CONDITIONAL_ENTRY_V2 entrypoint (daytrading_runtime.conditional_entry_snapshot) for
sweep/structure-shift/displacement/entry-array/READY -- no new M5 detector (spec
section 7) -- then trade_management.pretrade_engine for risk. `strategy_id` is exposed
per spec section 7's adapter requirement but only SMC_CONDITIONAL_ENTRY_V2 is wired
today; a real multi-strategy dispatch through strategy_manager is future work.
"""
from __future__ import annotations

from daytrading_runtime.conditional_entry_snapshot import build_symbol_conditional_entry_analysis
from entry_confirmation.entry_models_v1 import EntryModelState
from mt5.market_data import MarketDataError, get_tick
from mt5.symbol_resolver import SymbolMetaError, get_symbol_meta
from proposals import generate_proposals
from trade_management import TradeManagementRequest, evaluate_trade_management

from .models import (
    H1_POI_IDENTIFIED,
    H1_POI_REACHED,
    M5_INDETERMINATE,
    M5_NO_TRADE,
    M5_READY_FOR_PROPOSAL,
    M5_RISK_REJECTED,
    M5_WAITING_CONFIRMATION,
    M5_WAITING_H1_LOCATION,
    M5_WAITING_SWEEP,
    H1SetupContext,
    M5ExecutionContext,
)

_DIRECTION_FOR_PERMISSION = {"LONG_ONLY": "LONG", "SHORT_ONLY": "SHORT"}


def evaluate_m5_execution(symbol: str, h1: H1SetupContext, strategy_id: str = "SMC_CONDITIONAL_ENTRY_V2",
                         risk_percent: float = 1.0, equity: float = None) -> M5ExecutionContext:
    if h1.status not in (H1_POI_IDENTIFIED, H1_POI_REACHED):
        return M5ExecutionContext(symbol=symbol, as_of=None, d1_permission=h1.d1_directional_permission,
                                  h1_location=h1.status, strategy_id=strategy_id, status=M5_WAITING_H1_LOCATION,
                                  reasoning_codes=("H1_LOCATION_NOT_READY",))

    wanted_direction = _DIRECTION_FOR_PERMISSION.get(h1.d1_directional_permission)
    if wanted_direction is None:
        return M5ExecutionContext(symbol=symbol, as_of=None, d1_permission=h1.d1_directional_permission,
                                  h1_location=h1.status, strategy_id=strategy_id, status=M5_INDETERMINATE,
                                  reasoning_codes=("D1_PERMISSION_NOT_DIRECTIONAL",))

    analysis = build_symbol_conditional_entry_analysis(symbol)
    matching = [c for c in analysis.combinations if c.direction == wanted_direction]

    ready = next((c for c in matching if c.state == EntryModelState.READY.value), None)
    started = bool(matching)
    confirmed = any(c.state not in (
        EntryModelState.NOT_APPLICABLE.value, EntryModelState.NO_VALID_COMBINATION.value,
        EntryModelState.WAITING_HTF_TOUCH.value, EntryModelState.WAITING_H1_REACTION.value,
        EntryModelState.WAITING_M5_CONFIRMATION.value,
    ) for c in matching)

    if ready is None:
        status = M5_WAITING_CONFIRMATION if confirmed else (M5_WAITING_SWEEP if started else M5_NO_TRADE)
        return M5ExecutionContext(
            symbol=symbol, as_of=analysis.snapshot_time, d1_permission=h1.d1_directional_permission,
            h1_location=h1.status, strategy_id=strategy_id, status=status,
            reasoning_codes=(f"NO_READY_COMBINATION_FOR_{wanted_direction}",),
            evidence={"combinations": matching},
        )

    proposals = generate_proposals(analysis)
    proposal = next((p for p in proposals if p.combination == ready.combination and p.direction == wanted_direction), None)
    if proposal is None or proposal.entry_reference is None or proposal.invalidation_price is None:
        return M5ExecutionContext(
            symbol=symbol, as_of=analysis.snapshot_time, d1_permission=h1.d1_directional_permission,
            h1_location=h1.status, strategy_id=strategy_id, status=M5_INDETERMINATE,
            confirmation_result=ready, reasoning_codes=("READY_BUT_NO_ENTRY_GEOMETRY",),
        )

    try:
        symbol_meta = get_symbol_meta(symbol)
    except SymbolMetaError as exc:
        return M5ExecutionContext(
            symbol=symbol, as_of=analysis.snapshot_time, d1_permission=h1.d1_directional_permission,
            h1_location=h1.status, strategy_id=strategy_id, status=M5_RISK_REJECTED,
            confirmation_result=ready, entry_array_result=proposal,
            reasoning_codes=(f"SYMBOL_META_UNAVAILABLE:{exc}",),
        )

    current_price = None
    try:
        current_price = get_tick(symbol).bid
    except MarketDataError:
        pass

    tm_request = TradeManagementRequest(
        symbol=symbol, direction=wanted_direction, entry_price=proposal.entry_reference,
        stop_loss=proposal.invalidation_price, take_profit=None,
        risk_percent=risk_percent, equity=equity, symbol_meta=symbol_meta, current_price=current_price,
    )
    risk_result = evaluate_trade_management(tm_request)
    status = M5_READY_FOR_PROPOSAL if risk_result.overall_status == "READY" else M5_RISK_REJECTED

    return M5ExecutionContext(
        symbol=symbol, as_of=analysis.snapshot_time, d1_permission=h1.d1_directional_permission,
        h1_location=h1.status, strategy_id=strategy_id,
        entry_array_result=proposal, confirmation_result=ready, risk_result=risk_result,
        tp1=None,  # pretrade_engine's geometry takes take_profit as an INPUT, not an output --
                   # no existing contract derives a TP1 price for pretrade proposals; GAP, not invented
        status=status,
        reasoning_codes=(f"RISK_{risk_result.overall_status}",),
    )
