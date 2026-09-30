"""WP4.1/WP4.2 (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md) --
narrow orchestration connecting an ALREADY-PRODUCED, deterministic
post_asian_pilot.pipeline.PilotCycleResult to the tested ticket_delivery foundation.

This module never calls run_pilot_cycle() itself and never reinterprets a
PairResult/PostAsianDecision -- it is handed one, already computed by the frozen
strategy path, and only archives/renders/delivers what it's given. `cycle` (e.g.
"ASIAN_LONDON"/"LONDON_NEWYORK") is a caller-supplied label, not derived here -- the
caller (the future scheduler-facing CLI, WP4.5) already knows which pilot config it
invoked and is the correct place to own that mapping, not this module.

Sequence enforced by construction (WP4.1): archive_cycle_decision() is called before
anything else for every pair, including WATCH/NO_TRADE/DATA_ERROR/BLOCKED -- no
render/register/claim/transport call exists on any path that skips it. A raised
ArchiveFailedError stops that pair's processing immediately with zero further calls.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from post_asian_pilot.decision import (
    STATUS_BLOCKED,
    STATUS_DATA_ERROR,
    STATUS_EXPIRED,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
)
from post_asian_pilot.governor import PORTFOLIO_SELECTED

from .archive import (
    CYCLE_STATE_BLOCKED,
    CYCLE_STATE_DATA_ERROR,
    CYCLE_STATE_NO_TRADE,
    CYCLE_STATE_READY,
    CYCLE_STATE_WATCH,
    ArchiveFailedError,
    CycleDecisionRecord,
    archive_cycle_decision,
)
from .delivery_store import TicketDeliveryStore
from .identity import logical_ticket_id
from .policy import CatchUpPolicy
from .renderer import format_message_text, render_informational_ticket

REASON_ARCHIVE_FAILED = "ARCHIVE_FAILED"
REASON_RENDER_BLOCKED = "RENDER_BLOCKED"
REASON_TRANSPORT_NOT_CONFIGURED = "TELEGRAM_NOT_CONFIGURED"
REASON_READY_MISSING_READY_AT = "READY_MISSING_READY_AT"
DELIVERY_STATE_CATCH_UP_REJECTED = "CATCH_UP_REJECTED"


@dataclass(frozen=True)
class PairOutcome:
    symbol: str
    cycle_state: str
    logical_ticket_id: str
    archive_path: Optional[str]
    archived: bool
    delivery_state: str  # NOT_APPLICABLE / RENDER_BLOCKED / (delivery_store state) / TRANSPORT_NOT_CONFIGURED / ARCHIVE_FAILED
    reason_code: Optional[str] = None
    # True only when THIS call to process_pair_result() is the one that performed the
    # real Telegram send (mirrors DeliveryOutcome.delivery_performed_by_this_invocation
    # -- see telegram_adapter.py's docstring). `delivery_state == "DELIVERED"` alone is
    # NOT sufficient to answer "did I send it": a caller that lost a claim race, or
    # that re-invoked after a prior successful send, also observes "DELIVERED" (the
    # durable ticket state), but did not itself deliver anything. Defaults to False on
    # every non-delivery path (NOT_APPLICABLE, RENDER_BLOCKED, CATCH_UP_REJECTED,
    # TRANSPORT_NOT_CONFIGURED, ARCHIVE_FAILED) since none of those ever send.
    delivery_performed_by_this_invocation: bool = False


def _map_cycle_state(pair) -> str:
    """Deterministic, exhaustive mapping from the strategy's own decision.status /
    portfolio_state vocabulary to ticket_delivery's 5-state archive vocabulary. Every
    input value is explicitly accounted for -- an unrecognized status fails closed
    (raises) rather than silently defaulting, so a future new decision status can never
    slip through unmapped."""
    status = pair.decision.status
    if status == STATUS_READY:
        if pair.portfolio_state == PORTFOLIO_SELECTED and pair.proposal is not None and pair.proposal.actionable:
            return CYCLE_STATE_READY
        return CYCLE_STATE_BLOCKED  # a real READY signal existed but never became actionable
    if status == STATUS_WATCH:
        return CYCLE_STATE_WATCH
    if status == STATUS_NO_TRADE:
        return CYCLE_STATE_NO_TRADE
    if status == STATUS_DATA_ERROR:
        return CYCLE_STATE_DATA_ERROR
    if status in (STATUS_BLOCKED, STATUS_EXPIRED):
        return CYCLE_STATE_BLOCKED
    raise ValueError(f"unrecognized decision.status={status!r} -- no archive-state mapping defined")


def process_pair_result(
    pair, *, strategy_id: str, strategy_version: str, application_release: str,
    cycle: str, trading_date: dt.date, delivery_store: TicketDeliveryStore,
    render_entry_ticket_dict: Optional[Callable[[Any], Dict[str, Any]]] = None,
    deliver: Optional[Callable[[str, str], Any]] = None,
    archive_root: Optional[str] = None, now: Optional[dt.datetime] = None,
    catch_up_policy: Optional[CatchUpPolicy] = None,
) -> PairOutcome:
    """Processes ONE PairResult end-to-end: archive-before-send, then (READY only)
    catch-up gate -> render -> register -> claim -> deliver.

    `render_entry_ticket_dict`: caller-injected, maps a PairResult to the
    render_entry_ticket()-shaped dict renderer.render_informational_ticket() expects --
    this module deliberately does not know how to build strategy/release fingerprints
    or read the ledger itself (WP2's renderer already owns "wrap without re-deriving";
    this keeps that boundary intact and keeps this orchestration layer trivially
    testable with a plain injected callable).

    `deliver`: caller-injected `(logical_ticket_id, message_text) -> DeliveryOutcome`
    (typically a closure over telegram_adapter.deliver_informational_ticket() with a
    pre-built store/client/destination) -- absence means "transport not configured",
    which fails closed AFTER the archive has already happened (WP4.2: configuration
    absence must preserve the archived strategy result).

    `catch_up_policy`: caller-injected `CatchUpPolicy` (typically built from
    scheduler_integration's signed config), evaluated ONLY for a READY pair, using
    `pair.decision.ready_at` as the checkpoint (the real strategy-signal timestamp --
    frozen across restart/cache-reconstruction, never re-derived here) against `now`
    (the actual current time this invocation is running, injectable for tests, real
    wall-clock in production). `None` (the default) skips the gate entirely --
    preserves every pre-catch-up-integration caller/test unchanged. When supplied, a
    rejected catch-up NEVER creates a ticket (no render/register call below this
    point); the archive already happened above and is untouched -- only registration is
    withheld. A READY decision with no `ready_at` at all is itself an anomaly and fails
    closed the same way (never assumed to be "on time")."""
    cycle_state = _map_cycle_state(pair)
    symbol = pair.symbol
    evaluation_time = pair.decision.evaluation_time.isoformat() if getattr(pair.decision, "evaluation_time", None) else (now or dt.datetime.now(dt.timezone.utc)).isoformat()

    ticket_id = logical_ticket_id(
        strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol,
        cycle=cycle, trading_date=trading_date,
    )

    record = CycleDecisionRecord(
        strategy_id=strategy_id, strategy_version=strategy_version, application_release=application_release,
        symbol=symbol, cycle=cycle, trading_date=trading_date, cycle_state=cycle_state,
        evaluation_time_utc=evaluation_time,
        payload={"setup_id": getattr(pair.proposal, "setup_id", None), "portfolio_state": pair.portfolio_state,
                 "portfolio_reason_code": pair.portfolio_reason_code, "decision_status": pair.decision.status},
        reason_codes=tuple(pair.decision.reason_codes or ()),
    )

    archive_kwargs = {"root": archive_root} if archive_root else {}
    try:
        archive_path = archive_cycle_decision(record, **archive_kwargs)
    except ArchiveFailedError as exc:
        # Fail closed: zero further calls for this pair. This is the enforced ordering
        # guarantee -- there is no code path below this except-block for this pair.
        return PairOutcome(symbol, cycle_state, ticket_id, None, False, "ARCHIVE_FAILED", str(exc))

    if cycle_state != CYCLE_STATE_READY:
        delivery_store.record_not_applicable(
            logical_ticket_id=ticket_id, strategy_id=strategy_id, strategy_version=strategy_version,
            application_release=application_release, symbol=symbol, cycle=cycle,
            trading_date=trading_date.isoformat(), now=now,
        )
        return PairOutcome(symbol, cycle_state, ticket_id, archive_path, True, "NOT_APPLICABLE")

    # READY only, past this point.
    if catch_up_policy is not None:
        checkpoint = getattr(pair.decision, "ready_at", None)
        effective_now = now or dt.datetime.now(dt.timezone.utc)
        if checkpoint is None:
            return PairOutcome(symbol, cycle_state, ticket_id, archive_path, True,
                               DELIVERY_STATE_CATCH_UP_REJECTED, REASON_READY_MISSING_READY_AT)
        gate = catch_up_policy.evaluate(checkpoint=checkpoint, now=effective_now)
        if not gate.allowed:
            return PairOutcome(symbol, cycle_state, ticket_id, archive_path, True,
                               DELIVERY_STATE_CATCH_UP_REJECTED, gate.reason_code)

    if render_entry_ticket_dict is None:
        raise ValueError("render_entry_ticket_dict is required to process a READY pair")
    proposal_dict = render_entry_ticket_dict(pair)
    render_result = render_informational_ticket(
        logical_ticket_id=ticket_id, cycle=cycle, trading_date=trading_date.isoformat(),
        decision_status=cycle_state, proposal=proposal_dict,
    )
    if render_result.status != "RENDERED":
        return PairOutcome(symbol, cycle_state, ticket_id, archive_path, True, "RENDER_BLOCKED", render_result.reason_code)

    delivery_store.ensure_ready_to_deliver(
        logical_ticket_id=ticket_id, strategy_id=strategy_id, strategy_version=strategy_version,
        application_release=application_release, symbol=symbol, cycle=cycle,
        trading_date=trading_date.isoformat(), payload_hash=render_result.payload_hash, now=now,
    )

    if deliver is None:
        # Configuration absence: archived decision (and the READY_TO_DELIVER record)
        # already persisted above; only the network step is skipped.
        return PairOutcome(symbol, cycle_state, ticket_id, archive_path, True, "TRANSPORT_NOT_CONFIGURED", REASON_TRANSPORT_NOT_CONFIGURED)

    message_text = format_message_text(render_result.payload)
    outcome = deliver(ticket_id, message_text)
    return PairOutcome(
        symbol, cycle_state, ticket_id, archive_path, True, outcome.final_state, outcome.reason_code,
        delivery_performed_by_this_invocation=getattr(outcome, "delivery_performed_by_this_invocation", False),
    )
