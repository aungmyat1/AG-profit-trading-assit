"""Orchestrates TradeCommand -> gate -> geometry/sizing -> mt5_gateway/management_gateway
-> journal -> ExecutionReport. Implemented 2026-08-28 (Execution authority restructure).

Single public entrypoint: execute(command, user_confirmed=...). user_confirmed is a
required keyword argument with NO default -- there is no code path here that can reach
order_send without the caller (assistant.commands.execute_command / scripts/execute_trade.py)
having just received an explicit user instruction this turn and passed True. This is a
Python-level invariant, deliberately not a config toggle (see docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md
"Execution authority restructure" for why a YAML flag alone must never be able to
authorize a specific order).

Two sources, two validation paths (see execution/models.py::ExecutionSource):
  USER_EXPLICIT_ORDER  -- geometry/sizing only (trade_management.pretrade_engine),
                          no entry-confirmation/strategy-signal requirement.
  ASSISTANT_PROPOSAL   -- same geometry/sizing, but requires a stored, non-stale
                          TradeProposal; price is refreshed and re-validated, never
                          silently reused.

CLOSE actions are a thin router onto the existing, already-gated
mt5.management_gateway.close_position() -- no new close logic, no second MT5 gateway
(see mt5/management_gateway.py, which remains the only module allowed to touch an
existing position's order_check/order_send).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
from typing import Optional

from mt5.account import account as get_account
from mt5.account import positions as get_positions
from mt5.deals import deals_for_symbol
from mt5.market_data import get_tick
from mt5.management_gateway import close_position
from mt5.symbol_resolver import get_symbol_meta
from trade_management.models import (
    GEOMETRY_VALID,
    SIZING_NOT_REQUESTED,
    SIZING_READY,
    TradeManagementRequest,
)
from trade_management.pretrade_engine import evaluate_trade_management

from . import journal, mt5_gateway
from .models import ExecutionReport, ExecutionSource, OrderSendResult, TradeCommand

# Stale-proposal tolerance -- no existing project precedent for this number; an
# explicit, documented, easily-revised default rather than an invented config key.
# See docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md "Execution authority restructure" design notes.
_STALE_PROPOSAL_MAX_AGE_SECONDS = 300
_STALE_PROPOSAL_MIN_POINT_TOLERANCE = 10  # x symbol point
_STALE_PROPOSAL_SPREAD_MULTIPLIER = 5  # x current spread

# Final risk-revalidation tolerance immediately before order_check/order_send (section
# 18): evaluate_sizing()'s floor-only rounding already mathematically guarantees
# actual_risk_percent <= requested_risk_percent, so this is a defensive re-check, not
# the primary control -- a small epsilon absorbs float rounding noise, nothing more.
_RISK_REVALIDATION_TOLERANCE_PCT = 1e-6
_VOLUME_TOLERANCE = 1e-9


class ProposalStore:
    """In-memory TradeProposal store, keyed by proposal_id. A process-local cache is
    sufficient for this pass (one assistant session) -- not a persistence layer."""

    def __init__(self):
        self._proposals = {}

    def put(self, proposal) -> None:
        self._proposals[proposal.proposal_id] = proposal

    def get(self, proposal_id: str):
        return self._proposals.get(proposal_id)

    def all(self):
        return list(self._proposals.values())


_default_store = ProposalStore()


def _reject(command: TradeCommand, reason_code: str, *reasons: str) -> ExecutionReport:
    return ExecutionReport(
        command_id=command.command_id, source=command.source, status="REJECTED",
        gate_reason_code=reason_code, reasons=reasons or (reason_code,),
    )


def _resolve_entry_price(command: TradeCommand):
    """(price, error_reason_code) -- exactly one is None. Geometry/sizing must validate
    against the SAME price the order will actually fill near; previously defaulting to
    0.0 whenever --entry (a MARKET order) was omitted silently made every geometry check
    meaningless -- found live during AG_DEMO_EXECUTION_V1."""
    if command.entry is not None:
        return command.entry, None
    try:
        tick = get_tick(command.symbol)
    except Exception as exc:  # noqa: BLE001
        return None, "STALE_MARKET_DATA"
    price = tick.bid if command.side == "SELL" else tick.ask
    return price, None


def _resolve_equity_and_symbol_meta(symbol: str):
    """(equity, symbol_meta, error_reason_code) -- fetched fresh at execution time, never
    from a proposal's stale snapshot (section 11: "execution uses current broker
    state"). Only called when sizing must actually derive a volume from risk_percent --
    an explicit --volume order needs neither."""
    try:
        acct = get_account()
    except Exception as exc:  # noqa: BLE001
        return None, None, "ACCOUNT_STATE_UNAVAILABLE"
    try:
        meta = get_symbol_meta(symbol)
    except Exception as exc:  # noqa: BLE001
        return None, None, "SYMBOL_METADATA_UNAVAILABLE"
    return acct.equity, meta, None


def _validate_geometry_and_sizing(command: TradeCommand, entry_price: float,
                                   equity: Optional[float] = None, symbol_meta=None):
    direction = "BUY" if command.side == "BUY" else "SELL"
    tm_direction = "LONG" if direction == "BUY" else "SHORT"
    request = TradeManagementRequest(
        symbol=command.symbol,
        direction=tm_direction,
        entry_price=entry_price,
        stop_loss=command.sl if command.sl is not None else 0.0,
        take_profit=command.tp,
        risk_percent=command.risk_percent,
        equity=equity,
        symbol_meta=symbol_meta,
    )
    return evaluate_trade_management(request)


def _comment_tag(command_id: str) -> str:
    """A short, broker-comment-length-safe (<=31 char) identifier embedded in every
    order's comment so a later process (after a crash between order_send succeeding and
    the local journal write -- AG_DEMO_EXECUTION_SAFETY_V1 Test 8) can reconcile broker
    state back to this command_id without a second persistence system."""
    return f"AGT:{command_id}"[:31]


def _reconcile_via_broker(symbol: str, command_id: str) -> Optional[OrderSendResult]:
    """Checks open positions, then recent deal history, for a comment tag matching this
    command_id -- reusing mt5.account.positions()/mt5.deals.deals_for_symbol() (both
    already existed for other purposes) rather than a new persistence layer. Returns an
    OrderSendResult reconstructed from broker state if found, else None. This is the
    crash-window closer: journal.has_executed() alone only catches a crash AFTER the
    local journal write; this catches one that happened before it, by asking the broker
    what actually happened instead of trusting local state."""
    tag = _comment_tag(command_id)
    try:
        rows = get_positions(symbol=symbol)
    except Exception:  # noqa: BLE001 -- reconciliation is best-effort, never blocks the caller
        rows = []
    for row in rows:
        if tag in (row.comment or ""):
            return OrderSendResult(
                status="EXECUTED", reason_code="RECONCILED_FROM_BROKER_POSITION", symbol=symbol,
                side=("BUY" if row.type == 0 else "SELL"), filled_volume=float(row.volume),
                fill_price=float(row.price_open), sl=row.sl, tp=row.tp, ticket=int(row.ticket),
                timestamp=datetime.now(timezone.utc),
            )
    try:
        deals = deals_for_symbol(symbol)
    except Exception:  # noqa: BLE001
        deals = []
    for deal in deals:
        # entry == 0 -> DEAL_ENTRY_IN (an opening deal, not a close/partial of another position).
        if tag in (deal.comment or "") and getattr(deal, "entry", None) == 0:
            return OrderSendResult(
                status="EXECUTED", reason_code="RECONCILED_FROM_BROKER_HISTORY", symbol=symbol,
                side=("BUY" if deal.type == 0 else "SELL"), filled_volume=float(deal.volume),
                fill_price=float(deal.price), deal_id=int(deal.ticket),
                timestamp=datetime.now(timezone.utc),
            )
    return None


def _direction_to_side(direction: str) -> str:
    return "BUY" if direction == "LONG" else "SELL"


def _merge_proposal_fields(command: TradeCommand, proposal) -> TradeCommand:
    """TradeCommand carries execution identity (action/source/proposal_id/command_id);
    trade parameters not explicitly overridden on the command are resolved FROM the
    proposal's own TradeCandidate -- the caller of scripts/execute_trade.py open
    --proposal-id <id> --confirm should never have to retype SL/TP/risk_percent the
    assistant already proposed (section 2/20)."""
    candidate = proposal.candidate
    return replace(
        command,
        symbol=command.symbol if command.symbol else proposal.symbol,
        side=command.side if command.side is not None else _direction_to_side(candidate.direction),
        sl=command.sl if command.sl is not None else candidate.stop_loss,
        tp=command.tp if command.tp is not None else candidate.take_profit,
        risk_percent=command.risk_percent if command.risk_percent is not None else candidate.risk_percent,
    )


def _mark_proposal_status(store: "ProposalStore", proposal_id: Optional[str], status: str) -> None:
    if not proposal_id:
        return
    proposal = store.get(proposal_id)
    if proposal is not None:
        store.put(replace(proposal, status=status))


def _proposal_stale_reason(proposal, current_price: float, spread_points: float, point: float) -> Optional[str]:
    now = datetime.now(timezone.utc)
    age_seconds = (now - proposal.created_at).total_seconds()
    if age_seconds > _STALE_PROPOSAL_MAX_AGE_SECONDS:
        return "PROPOSAL_STALE_AGE"
    if now > proposal.expires_at:
        return "PROPOSAL_STALE_EXPIRED"
    tolerance = max(_STALE_PROPOSAL_SPREAD_MULTIPLIER * spread_points * point,
                     _STALE_PROPOSAL_MIN_POINT_TOLERANCE * point)
    deviation = abs(current_price - proposal.candidate.entry_price)
    if deviation > tolerance:
        return "PROPOSAL_STALE_PRICE_DEVIATION"
    return None


def execute(command: TradeCommand, *, user_confirmed: bool, proposal_store: Optional[ProposalStore] = None) -> ExecutionReport:
    store = proposal_store or _default_store

    if not user_confirmed:
        return _reject(command, "EXECUTION_NOT_AUTHORIZED",
                        "No explicit user execution command was supplied this turn.")

    if command.action not in ("OPEN", "CLOSE"):
        return _reject(command, "INVALID_ACTION")

    if journal.has_executed(command.command_id):
        return _reject(command, "DUPLICATE_COMMAND_BLOCKED",
                       f"command_id {command.command_id} has already resulted in ORDER_EXECUTED.")

    if command.action == "CLOSE":
        return _execute_close(command)

    # action == "OPEN"
    proposal = None
    if command.source == ExecutionSource.ASSISTANT_PROPOSAL:
        if not command.proposal_id:
            return _reject(command, "PROPOSAL_ID_MISSING")
        proposal = store.get(command.proposal_id)
        if proposal is None:
            return _reject(command, "PROPOSAL_NOT_FOUND")
        if proposal.status == "EXECUTED":
            # A fresh command_id (a new CLI invocation / a second "execute it") would
            # otherwise slip past the command_id-keyed journal check below and re-fetch
            # price for a genuine second real order on the SAME proposal -- section 25's
            # exact "Execute P123 again" scenario. Block on the proposal's own identity.
            return _reject(command, "DUPLICATE_COMMAND_BLOCKED",
                            f"proposal {command.proposal_id} was already executed.")
        # Resolve side/SL/TP/risk_percent FROM the proposal before anything else needs
        # them -- a caller executing a proposal should not have to retype what the
        # assistant already proposed (section 2/20).
        command = _merge_proposal_fields(command, proposal)

    if command.side not in ("BUY", "SELL"):
        return _reject(command, "INVALID_SIDE")

    if proposal is not None:
        try:
            tick = get_tick(command.symbol)
        except Exception as exc:  # noqa: BLE001
            return _reject(command, "STALE_MARKET_DATA", str(exc))
        current_price = tick.bid if command.side == "SELL" else tick.ask
        point = (proposal.candidate.symbol_meta.point
                 if proposal.candidate.symbol_meta else 0.0001)
        stale_reason = _proposal_stale_reason(proposal, current_price, tick.spread_points or 0, point)
        if stale_reason is not None:
            _mark_proposal_status(store, command.proposal_id, "STALE")
            # gate_reason_code is the SPECIFIC code (e.g. PROPOSAL_STALE_EXPIRED,
            # PROPOSAL_STALE_PRICE_DEVIATION) -- distinguishable per AG_DEMO_EXECUTION_
            # SAFETY_V1 Tests 1/2, not the generic "PROPOSAL_STALE" wrapper.
            return _reject(command, stale_reason, "PROPOSAL_STALE")

    journal.record_event(command.command_id, "ORDER_ATTEMPTED", symbol=command.symbol,
                          side=command.side, volume=command.volume, source=command.source.value,
                          proposal_id=command.proposal_id)

    entry_price, entry_error = _resolve_entry_price(command)
    if entry_error is not None:
        journal.record_event(command.command_id, "ORDER_REJECTED", reason_code=entry_error)
        return _reject(command, entry_error)

    equity, symbol_meta = None, None
    if command.volume is None:
        equity, symbol_meta, resolve_error = _resolve_equity_and_symbol_meta(command.symbol)
        if resolve_error is not None:
            journal.record_event(command.command_id, "ORDER_REJECTED", reason_code=resolve_error)
            _mark_proposal_status(store, command.proposal_id, "REJECTED")
            return _reject(command, resolve_error)

    tm_result = _validate_geometry_and_sizing(command, entry_price, equity, symbol_meta)
    if tm_result.geometry.status != GEOMETRY_VALID:
        journal.record_event(command.command_id, "ORDER_REJECTED", reason_code=tm_result.geometry.status)
        _mark_proposal_status(store, command.proposal_id, "REJECTED")
        return _reject(command, tm_result.geometry.status, *tm_result.reasons)

    volume = command.volume
    if volume is None:
        # Derived from risk_percent -- must go through evaluate_sizing()'s conservative
        # floor-only normalization (never rounds up past the risk budget) and its
        # fail-closed broker-min-volume rejection (never forces volume_min if that would
        # exceed the requested risk) -- see trade_management/sizing.py, already covered
        # by tests/test_trade_management_pretrade.py::test_normalization_rounds_down_never_up
        # and ::test_normalization_below_min_is_size_unavailable.
        if tm_result.sizing.status != SIZING_READY:
            reason = tm_result.sizing.status if tm_result.sizing.status != SIZING_NOT_REQUESTED else "VOLUME_UNAVAILABLE"
            journal.record_event(command.command_id, "ORDER_REJECTED", reason_code=reason)
            _mark_proposal_status(store, command.proposal_id, "REJECTED")
            return _reject(command, reason, *tm_result.reasons)
        volume = tm_result.sizing.normalized_volume

        # Final risk revalidation immediately before order_check (section 18) -- defense
        # in depth on top of evaluate_sizing()'s own guarantee, not the primary control.
        requested_pct = command.risk_percent
        actual_pct = tm_result.sizing.actual_risk_percent
        if requested_pct is not None and actual_pct is not None and \
                actual_pct > requested_pct + _RISK_REVALIDATION_TOLERANCE_PCT:
            journal.record_event(command.command_id, "ORDER_REJECTED", reason_code="RISK_LIMIT_EXCEEDED",
                                  requested_risk_percent=requested_pct, actual_risk_percent=actual_pct)
            _mark_proposal_status(store, command.proposal_id, "REJECTED")
            return _reject(command, "RISK_LIMIT_EXCEEDED",
                            f"actual_risk_percent {actual_pct} exceeds requested {requested_pct}.")

    if not journal.claim_command(command.command_id):
        return _reject(command, "DUPLICATE_COMMAND_BLOCKED",
                       f"command_id {command.command_id} is already claimed by another execution worker.")

    # Crash/restart reconciliation (AG_DEMO_EXECUTION_SAFETY_V1 Test 8): if a prior
    # attempt with this exact command_id already reached the broker but the process
    # crashed before journal.record_event(ORDER_EXECUTED) ran, journal.has_executed()
    # above would have missed it (the local file was never written). Ask the broker
    # directly via the comment tag before ever calling order_open again.
    reconciled = _reconcile_via_broker(command.symbol, command.command_id)
    if reconciled is not None:
        journal.record_event(command.command_id, "ORDER_EXECUTED", ticket=reconciled.ticket,
                              deal_id=reconciled.deal_id, fill_price=reconciled.fill_price,
                              filled_volume=reconciled.filled_volume, proposal_id=command.proposal_id,
                              reconciled=True, reason_code=reconciled.reason_code)
        _mark_proposal_status(store, command.proposal_id, "EXECUTED")
        return ExecutionReport(command_id=command.command_id, source=command.source,
                                status="EXECUTED", gate_reason_code=reconciled.reason_code,
                                result=reconciled)

    result: OrderSendResult = mt5_gateway.order_open(
        symbol=command.symbol,
        side=command.side,
        order_type=command.order_type,
        volume=volume,
        sl=command.sl,
        tp=command.tp,
        magic_number=command.magic_number,
        # MT5's deal/order comment field is length-limited (~31 chars) -- found live
        # during AG_RISK_PERCENT_SIZING_LIVE_V1 (the previous, longer default triggered
        # a real "(-2) Invalid comment argument" order_check rejection). The tag also
        # doubles as the crash-reconciliation key above -- a caller-supplied comment
        # opts out of both the length guarantee and reconciliation, by choice.
        comment=command.comment or _comment_tag(command.command_id),
        entry=command.entry,
    )

    if result.status == "EXECUTED":
        fill_evidence = _fill_evidence(command, result, entry_price, equity, symbol_meta)
        journal.record_event(command.command_id, "ORDER_EXECUTED", ticket=result.ticket,
                              deal_id=result.deal_id, fill_price=result.fill_price,
                              filled_volume=result.filled_volume, proposal_id=command.proposal_id,
                              symbol=command.symbol, direction=command.side,
                              risk_percent=command.risk_percent, **fill_evidence)
        _mark_proposal_status(store, command.proposal_id, "EXECUTED")
    else:
        journal.record_event(command.command_id, "ORDER_REJECTED", reason_code=result.reason_code,
                              broker_retcode=result.broker_retcode, broker_comment=result.broker_comment,
                              proposal_id=command.proposal_id)
        _mark_proposal_status(store, command.proposal_id, "REJECTED")

    return ExecutionReport(
        command_id=command.command_id, source=command.source,
        status=result.status, gate_reason_code=result.reason_code, result=result,
    )


def _fill_evidence(command: TradeCommand, result: OrderSendResult, requested_entry: float,
                    equity: Optional[float], symbol_meta) -> dict:
    """Post-fill reconciliation evidence (Test 7): a broker fill can legitimately differ
    from the pre-send estimate via slippage -- this reports the actual numbers rather
    than assuming pre-send risk compliance still holds after the fill. Journal-only
    (dict of extra fields), not added to OrderSendResult's frozen schema, per "don't
    force fields into every layer" -- this is evidence, not a decision any gate acts on."""
    evidence: dict = {}
    if result.fill_price is None:
        return evidence

    if symbol_meta is None:
        try:
            symbol_meta = get_symbol_meta(command.symbol)
        except Exception:  # noqa: BLE001 -- evidence is best-effort
            symbol_meta = None
    if equity is None:
        try:
            equity = get_account().equity
        except Exception:  # noqa: BLE001
            equity = None

    if symbol_meta is not None:
        evidence["slippage_points"] = round((result.fill_price - requested_entry) / symbol_meta.point, 2)

    sl = command.sl
    if sl is not None and symbol_meta is not None and result.filled_volume is not None:
        actual_stop_distance = abs(result.fill_price - sl)
        value_per_price_unit = symbol_meta.tick_value / symbol_meta.tick_size
        actual_risk_at_fill = result.filled_volume * actual_stop_distance * value_per_price_unit
        evidence["actual_stop_distance"] = actual_stop_distance
        evidence["actual_risk_at_fill"] = round(actual_risk_at_fill, 2)
        if equity:
            evidence["actual_risk_percent_at_fill"] = round(actual_risk_at_fill / equity * 100.0, 4)

    return evidence


def _execute_close(command: TradeCommand) -> ExecutionReport:
    if command.position_ticket is None:
        return _reject(command, "POSITION_TICKET_MISSING")

    rows = get_positions(ticket=command.position_ticket)
    if not rows:
        return _reject(command, "POSITION_NOT_FOUND")
    row = rows[0]
    symbol = row.symbol
    direction = "BUY" if row.type == 0 else "SELL"
    current_volume = float(row.volume)
    requested_volume = command.volume if command.volume is not None else current_volume
    try:
        symbol_meta = get_symbol_meta(symbol)
    except Exception as exc:  # noqa: BLE001 -- missing broker constraints must fail closed
        return _reject(command, "SYMBOL_METADATA_UNAVAILABLE", str(exc))

    volume, volume_error = _normalize_close_volume(requested_volume, current_volume, symbol_meta)
    if volume_error is not None:
        return _reject(command, volume_error)

    try:
        tick = get_tick(symbol)
    except Exception as exc:  # noqa: BLE001
        return _reject(command, "STALE_MARKET_DATA", str(exc))
    price = tick.bid if direction == "BUY" else tick.ask

    if not journal.claim_command(command.command_id):
        return _reject(command, "DUPLICATE_COMMAND_BLOCKED",
                       f"command_id {command.command_id} is already claimed by another execution worker.")

    journal.record_event(command.command_id, "CLOSE_ATTEMPTED", ticket=command.position_ticket, volume=volume)

    gateway_result = close_position(command.position_ticket, symbol, direction, volume, price)

    if gateway_result.dry_run:
        journal.record_event(command.command_id, "CLOSE_DRY_RUN", ticket=command.position_ticket)
        return ExecutionReport(command_id=command.command_id, source=command.source,
                                status="REJECTED", gate_reason_code="DRY_RUN")

    if gateway_result.executed:
        journal.record_event(command.command_id, "ORDER_EXECUTED", ticket=command.position_ticket,
                              retcode=gateway_result.retcode)
        status, reason_code = "EXECUTED", "ORDER_SEND_DONE"
    else:
        journal.record_event(command.command_id, "ORDER_REJECTED", ticket=command.position_ticket,
                              retcode=gateway_result.retcode, comment=gateway_result.comment)
        status, reason_code = "REJECTED", "BROKER_REJECTED"

    result = OrderSendResult(
        status=status, reason_code=reason_code, symbol=symbol, side=direction,
        requested_volume=volume, filled_volume=volume if gateway_result.executed else None,
        requested_price=price, fill_price=price if gateway_result.executed else None,
        ticket=command.position_ticket, broker_retcode=gateway_result.retcode,
        broker_comment=gateway_result.comment, timestamp=datetime.now(timezone.utc),
        request=gateway_result.request,
    )
    return ExecutionReport(command_id=command.command_id, source=command.source,
                            status=status, gate_reason_code=reason_code, result=result)


def _normalize_close_volume(requested_volume: float, current_volume: float, symbol_meta):
    """Return a conservative broker-valid close volume, or a fail-closed reason code."""
    if not math.isfinite(requested_volume) or requested_volume <= 0:
        return None, "INVALID_CLOSE_VOLUME"
    if not math.isfinite(current_volume) or current_volume <= 0:
        return None, "INVALID_POSITION_VOLUME"
    if requested_volume > current_volume + _VOLUME_TOLERANCE:
        return None, "CLOSE_VOLUME_EXCEEDS_POSITION"
    if (
        symbol_meta.volume_min <= 0
        or symbol_meta.volume_max < symbol_meta.volume_min
        or symbol_meta.volume_step <= 0
    ):
        return None, "SYMBOL_METADATA_UNAVAILABLE"

    steps = math.floor(requested_volume / symbol_meta.volume_step + _VOLUME_TOLERANCE)
    normalized = round(steps * symbol_meta.volume_step, 8)
    if normalized < symbol_meta.volume_min - _VOLUME_TOLERANCE:
        return None, "CLOSE_VOLUME_BELOW_MIN"
    if normalized > symbol_meta.volume_max + _VOLUME_TOLERANCE:
        return None, "CLOSE_VOLUME_ABOVE_MAX"
    if normalized > current_volume + _VOLUME_TOLERANCE:
        return None, "CLOSE_VOLUME_EXCEEDS_POSITION"

    remaining = current_volume - normalized
    if remaining > _VOLUME_TOLERANCE and remaining < symbol_meta.volume_min - _VOLUME_TOLERANCE:
        return None, "CLOSE_VOLUME_LEAVES_BELOW_MIN_REMAINDER"
    return normalized, None
