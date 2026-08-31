"""AG_GLOBAL_EXECUTION_LIFECYCLE_V1: closes the two gaps ExecutionCoordinator's own
module docstring already named -- "SUBMITTED does not automatically equal OPEN", and
DailyLossGuard.record_trade_result() was only ever called from tests.

    BROKER_FILL_CONFIRMED -> register_confirmed_fill() -> OpenPositionGuard.register_open
    (restart / periodic) -> reconcile_open_positions() -> broker truth wins -> CloseLedger
    (idempotent) -> DailyLossGuard.record_trade_result()

Reuses, does not duplicate:
  - "is this broker position still open" -- mt5.account.positions(ticket=...), the SAME
    broker-position-query capability execution/executor.py's own crash reconciliation
    (_reconcile_via_broker) and trade_management/position_monitor.py already use. No
    second broker-position-discovery mechanism is built here.
  - "what was the realized PnL" -- mt5.deals.deals_for_position(ticket), the SAME deal-
    history read execution/executor.py's crash reconciliation already uses (there via
    deals_for_symbol). A deal's own `profit` field (MT5 history_deals_get()) is the
    authoritative realized PnL for that leg; entry != 0 (DEAL_ENTRY_OUT / INOUT / OUT_BY)
    identifies a CLOSING deal, entry == 0 (DEAL_ENTRY_IN) the opening deal -- the exact
    convention execution/executor.py::_reconcile_via_broker already uses for the opening
    side, reused here for the closing side rather than inventing a second entry-code
    reading.
  - "how much volume/risk was this position for" -- read directly off the TradeProposal
    that reached ExecutionCoordinator.submit() (proposal.risk_amount, already computed
    upstream by execution.risk.size_position via intent_builder/from_setup_state -- never
    recomputed here), persisted onto the OpenPositionGuard record at fill time
    (position_guard.py's own new optional fields) so it survives a restart without a
    second parallel store.

Position identity: every function here keys a position by the broker ticket (as a
string) -- the one identity that is stable across a restart, distinguishes two
completed trades on the same symbol, and is what mt5.account.positions()/deals_for_position
themselves are keyed by. strategy_id/setup_id/symbol are carried as the STORED RECORD for
that ticket (see position_guard.py), never used as part of the key itself.

GENUINE GAP (documented, not faked): a broker position discovered ONLY via reconciliation
(no OpenPositionGuard record survived to describe it -- e.g. a crash between broker fill
and register_confirmed_fill) carries no stable stored risk_amount/strategy_id anywhere in
this repo (the executor's own journal never recorded proposal.risk_amount or strategy_id
either -- see journal.record_event calls in execution/executor.py/coordinator.py). Such a
restored record is registered OPEN (so the global guard still fails closed / correctly
blocks new submissions) with risk_amount=None; its eventual close is intentionally left
UNRECORDED in the realized-R ledger (status CLOSED_RISK_AMOUNT_MISSING) rather than
guessed from current market price (explicitly forbidden by spec).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from execution import journal
from execution.close_ledger import CloseLedger
from execution.daily_loss_guard import DailyLossGuard
from execution.models import ExecutionReport
from execution.position_guard import OpenPositionGuard

UNKNOWN_STRATEGY_ID = "UNKNOWN_RECONCILED"
_COMMENT_TAG_PREFIX = "AGT:"


def _trading_day(now: Optional[datetime]) -> date:
    return (now or datetime.now(timezone.utc)).date()


def register_confirmed_fill(open_position_guard: OpenPositionGuard, proposal, report: ExecutionReport) -> Optional[str]:
    """BROKER_FILL_CONFIRMED -> register_open. Only ever fires when execution/executor.py
    itself reports EXECUTED with a real broker ticket -- an ASSISTANT_PROPOSAL/order still
    awaiting confirmation, a rejection, or a duplicate short-circuit never reaches here
    (spec: "SUBMITTED does not automatically equal OPEN"). Returns the position_id
    (ticket, as a string) it registered under, or None if nothing was registered.

    AG_EXECUTION_RUNTIME_READINESS_V1 (GAP 2): also persists IMMUTABLE lifecycle metadata
    (ticket, strategy_id, setup_id, symbol, direction, effective fill entry, original
    stop_loss, initial executed volume, original risk_amount, requested risk_percent) into
    execution.journal, keyed by proposal.setup_id -- the SAME command_id the Forex
    TradeCommand already used (see coordinator._forex_command), and the SAME identity a
    restart-restored broker position's AGT:<command_id> comment tag already resolves to
    (see reconcile_open_positions below). This is what lets a later restart recover the
    ORIGINAL risk_amount for a position whose OpenPositionGuard record did not itself
    survive, instead of leaving it permanently unrecoverable."""
    if report.status != "EXECUTED" or report.result is None or report.result.ticket is None:
        return None
    position_id = str(report.result.ticket)
    open_position_guard.register_open(
        position_id, proposal.strategy_id, proposal.symbol,
        setup_id=proposal.setup_id, risk_amount=proposal.risk_amount, volume=proposal.volume,
    )
    result = report.result
    journal.record_lifecycle_metadata(
        proposal.setup_id,
        ticket=position_id,
        strategy_id=proposal.strategy_id,
        setup_id=proposal.setup_id,
        symbol=proposal.symbol,
        direction=proposal.direction,
        entry=result.fill_price if result.fill_price is not None else proposal.entry,
        stop_loss=proposal.stop_loss,
        volume=result.filled_volume if result.filled_volume is not None else proposal.volume,
        risk_amount=proposal.risk_amount,
        risk_percent=getattr(proposal, "risk_percent", None),
    )
    return position_id


def _closing_deals_profit(deals) -> float:
    # entry == 0 is the OPENING deal (DEAL_ENTRY_IN) -- excluded. Every other entry code
    # (OUT/INOUT/OUT_BY) is a closing leg, partial or final; summing all of them across a
    # ticket's full history gives the correct total realized PnL exactly once at full
    # close (e.g. TP1 partial + runner-close), same convention as
    # execution/executor.py::_reconcile_via_broker's own entry==0 check for the open side.
    return sum(float(getattr(deal, "profit", 0.0) or 0.0) for deal in deals if getattr(deal, "entry", None) != 0)


def reconcile_closed_position(
    open_position_guard: OpenPositionGuard,
    daily_loss_guard: DailyLossGuard,
    close_ledger: CloseLedger,
    position_id: str,
    record: Dict[str, Any],
    *,
    deals_lookup: Callable[[int], Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Idempotent close lifecycle (spec 'CLOSE RECONCILIATION'): called once a caller has
    already established the broker no longer reports this ticket as an open position.

    1. find the matching global position record (caller-supplied `record`, read from
       OpenPositionGuard BEFORE any removal -- callers must not mutate the guard first).
    2. register_closed.
    3. compute realized result from authoritative deal history (deals_lookup).
    4. record_trade_result exactly once (guarded by CloseLedger).
    5. persist completion identity (CloseLedger.mark_recorded) so a replayed/duplicate
       close observation for the SAME position_id has zero additional effect.
    """
    if close_ledger.is_recorded(position_id):
        # Duplicate close observation (failure case 5) / replayed reconciliation run --
        # the realized-R ledger was already updated for this position_id. Only ensure the
        # open guard reflects the same fact (defensive; register_closed is itself
        # idempotent), never touch daily_loss_guard again.
        open_position_guard.register_closed(position_id)
        return {"status": "ALREADY_RECORDED", "position_id": position_id}

    try:
        ticket = int(position_id)
    except (TypeError, ValueError):
        return {"status": "NON_TICKET_ID_SKIPPED", "position_id": position_id}

    try:
        deals = deals_lookup(ticket)
    except Exception as exc:  # noqa: BLE001 -- authoritative data unavailable, fail closed on recording
        return {"status": "DEALS_UNAVAILABLE", "position_id": position_id, "error": str(exc)}

    realized_pnl = _closing_deals_profit(deals)
    risk_amount = record.get("risk_amount")
    strategy_id = record.get("strategy_id")
    symbol = record.get("symbol")

    realized_r: Optional[float] = None
    if risk_amount:  # None or 0 -- cannot compute a meaningful R, document as a gap, never guess
        realized_r = realized_pnl / risk_amount
        daily_loss_guard.record_trade_result(_trading_day(now), realized_r)

    close_ledger.mark_recorded(position_id, realized_pnl=realized_pnl, realized_r=realized_r,
                                strategy_id=strategy_id, symbol=symbol)
    open_position_guard.register_closed(position_id)

    status = "CLOSED_RECORDED" if realized_r is not None else "CLOSED_RISK_AMOUNT_MISSING"
    return {"status": status, "position_id": position_id, "realized_pnl": realized_pnl,
            "realized_r": realized_r, "strategy_id": strategy_id, "symbol": symbol}


def _extract_command_id_from_comment(comment: Optional[str]) -> Optional[str]:
    if not comment or not comment.startswith(_COMMENT_TAG_PREFIX):
        return None
    return comment[len(_COMMENT_TAG_PREFIX):]


def reconcile_open_positions(
    open_position_guard: OpenPositionGuard,
    daily_loss_guard: DailyLossGuard,
    close_ledger: CloseLedger,
    *,
    positions_lookup: Callable[..., Any],
    deals_lookup: Callable[[int], Any],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Restart-safe reconciliation (spec 'On restart: reconcile persisted guard state
    against authoritative broker/account position state'): also safe to run periodically
    while the process stays up, not only at startup -- every branch is idempotent.

    positions_lookup/deals_lookup are injected (not imported directly from mt5.account /
    mt5.deals here) so this stays unit-testable without a live MT5 terminal, same idiom
    execution/executor.py itself uses for its own dependencies; production callers pass
    mt5.account.positions and mt5.deals.deals_for_position.

    Two passes:
      1. Every ticket the guard currently thinks is open: ask the broker. Still there
         (even at reduced/partial volume -- spec: "TP1 partial reduction must NOT clear
         the guard") -> leave it. Broker no longer reports it -> reconcile_closed_position.
      2. Every OTHER live broker position tagged as ours (AGT:<command_id> comment, the
         SAME tag execution/executor.py's own _comment_tag()/_reconcile_via_broker()
         convention already writes/reads) that the guard does NOT know about -> restore it
         (spec: "Missing persisted record but a real AG position exists -> restore/
         register it"). See this module's docstring GAP note on what cannot be restored.
    """
    results: List[Dict[str, Any]] = []
    tracked = open_position_guard.store.all()

    for position_id, record in list(tracked.items()):
        try:
            ticket = int(position_id)
        except (TypeError, ValueError):
            results.append({"status": "NON_TICKET_ID_SKIPPED", "position_id": position_id})
            continue
        try:
            rows = positions_lookup(ticket=ticket)
        except Exception as exc:  # noqa: BLE001 -- cannot verify; fail closed (leave state as-is)
            results.append({"status": "POSITION_QUERY_FAILED", "position_id": position_id, "error": str(exc)})
            continue
        if rows:
            results.append({"status": "STILL_OPEN", "position_id": position_id})
            continue
        results.append(reconcile_closed_position(
            open_position_guard, daily_loss_guard, close_ledger, position_id, record,
            deals_lookup=deals_lookup, now=now,
        ))

    try:
        all_rows = positions_lookup()
    except Exception as exc:  # noqa: BLE001 -- best-effort restore pass only
        results.append({"status": "GLOBAL_POSITION_QUERY_FAILED", "error": str(exc)})
        return results

    known_now = open_position_guard.store.all()
    for row in all_rows:
        ticket_str = str(row.ticket)
        if ticket_str in known_now:
            continue
        command_id = _extract_command_id_from_comment(getattr(row, "comment", None))
        if command_id is None:
            continue  # not one of ours (no AGT: tag) -- never adopt a foreign position

        # GAP 2: combine "live MT5 AG position exists" with "persisted lifecycle metadata
        # for that command_id" -- if register_confirmed_fill() ran for this ticket before
        # whatever crash/restart lost the OpenPositionGuard record, the ORIGINAL
        # risk_amount/strategy_id are recoverable from execution.journal instead of being
        # permanently None. If no metadata was ever persisted (predates this phase, or the
        # write itself failed), fail closed exactly as before -- never guess.
        metadata = journal.read_lifecycle_metadata(command_id)
        if metadata is not None and metadata.get("risk_amount") is not None:
            open_position_guard.register_open(
                ticket_str, metadata.get("strategy_id") or UNKNOWN_STRATEGY_ID, row.symbol,
                setup_id=command_id, risk_amount=metadata.get("risk_amount"),
                volume=float(row.volume),
            )
            results.append({
                "status": "MISSING_RECORD_RESTORED_FROM_METADATA", "position_id": ticket_str,
                "risk_metadata_status": "RECOVERED",
                "risk_amount": metadata.get("risk_amount"),
                "strategy_id": metadata.get("strategy_id"),
            })
            continue

        open_position_guard.register_open(
            ticket_str, UNKNOWN_STRATEGY_ID, row.symbol,
            setup_id=command_id, risk_amount=None, volume=float(row.volume),
        )
        results.append({
            "status": "MISSING_RECORD_RESTORED", "position_id": ticket_str,
            "risk_metadata_status": "OPEN_RISK_METADATA_MISSING",
            "gap": "strategy_id/risk_amount not recoverable from broker state or the "
                   "lifecycle-metadata journal alone; the position still counts toward "
                   "and blocks the one-open-position rule, but realized-R at close will "
                   "be skipped (CLOSED_RISK_AMOUNT_MISSING) -- never guessed.",
        })

    return results
