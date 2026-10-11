"""Bridges WP-4's proposal_envelope.models.CanonicalProposal onto the existing
assistant-side owner-confirmed execution pipeline (assistant.analysis_models.
TradeCandidate/TradeProposal, execution.models.TradeCommand).

    CanonicalProposal (proposal_state == PROPOSAL_READY)
            v
    TradeCandidate / TradeProposal      (existing shapes, unchanged)
            v
    TradeCommand template                (existing shape, unchanged; risk_percent/
                                           volume left None -- owner-supplied)
            v
    STOP -- execution remains a separate, explicitly-confirmed action through
    assistant.commands.execute_command() -> execution.executor.execute(). Nothing in
    this module calls that path, imports execution.executor, or touches MT5.

Never recomputes strategy eligibility (opportunity.proposal_eligibility, WP-3) or
strategy detection (strategy_engine/) -- a CanonicalProposal not already
PROPOSAL_READY fails closed here; it is never re-evaluated.

No MT5 dependency: the independent WP-5/6 preflight established that
TradeCandidate.equity/symbol_meta are read only by assistant.five_skill_runtime's own
advisory preview and by execution.executor's best-effort staleness tolerance -- never
required for proposal formation. This module leaves both None; live account/symbol
metadata stays resolved exactly where it already is, inside execution.executor at
confirmed-execution time.

risk_percent/volume are deliberately left None on the TradeCommand template this
module builds: nothing in strategies/ST_ASIAN_SWEEP_5R_V1.yaml (or CanonicalProposal
itself, which WP-4 never computes risk into) authoritatively specifies
risk_per_trade_pct -- see strategies/registry.yaml's own comment on that strategy's
open contract gaps. Hard-coding a default here would be inventing strategy policy this
module has no authority over; see REQUIRED_OWNER_INPUTS. order_type is left at
TradeCommand's own pre-existing "MARKET" default (execution.models, unmodified) --
using an existing contract default is not the same as inventing one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from execution.models import ExecutionSource, TradeCommand
from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY

from .analysis_models import TradeCandidate, TradeProposal

# Mirrors assistant.commands._PROPOSAL_TTL_MINUTES -- used only when
# envelope.plan_expires_at is absent, as the same operational fallback build_proposal()
# already applies to every other proposal. Never a strategy-owned expiry invented here.
_DEFAULT_TTL_MINUTES = 15

_DIRECTION_MAP = {"BUY": "LONG", "SELL": "SHORT"}

# Fields this bridge deliberately leaves unset on the TradeCommand template -- the
# caller/owner must supply them explicitly before execute_command() can size an order
# from them (see module docstring).
REQUIRED_OWNER_INPUTS: Tuple[str, ...] = ("risk_percent",)


class CanonicalProposalNotReady(ValueError):
    """envelope.proposal_state != PROPOSAL_READY. Fail closed -- WP-3/WP-4 eligibility
    is never re-evaluated here; a BLOCKED/INCOMPLETE/unknown-state envelope simply does
    not proceed."""


class CanonicalProposalMalformed(ValueError):
    """A PROPOSAL_READY envelope missing a field WP-3/WP-4 already guarantee non-None
    for READY (direction/entry/stop/proposal_envelope_id) or carrying an unrecognized
    direction. Defensive: mirrors opportunity.proposal_eligibility's own WP-3 R1
    fail-closed-on-broken-invariant precedent rather than trusting the upstream
    guarantee blindly at this boundary."""


def _iso_to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def canonical_proposal_to_trade_candidate(envelope: CanonicalProposal) -> TradeCandidate:
    """Pure. Raises CanonicalProposalNotReady / CanonicalProposalMalformed rather than
    returning a partially-populated candidate -- there is no "INCOMPLETE" TradeCandidate
    concept to degrade to."""
    if envelope.proposal_state != PROPOSAL_READY:
        raise CanonicalProposalNotReady(
            f"proposal_envelope_id={envelope.proposal_envelope_id!r} proposal_state="
            f"{envelope.proposal_state!r} -- only PROPOSAL_READY may be prepared."
        )
    if not envelope.proposal_envelope_id:
        raise CanonicalProposalMalformed("PROPOSAL_READY envelope carries no proposal_envelope_id.")
    if envelope.direction not in _DIRECTION_MAP:
        raise CanonicalProposalMalformed(
            f"proposal_envelope_id={envelope.proposal_envelope_id!r}: unsupported/missing "
            f"direction {envelope.direction!r} (expected one of {sorted(_DIRECTION_MAP)})."
        )
    if envelope.entry is None or envelope.stop is None:
        raise CanonicalProposalMalformed(
            f"proposal_envelope_id={envelope.proposal_envelope_id!r}: PROPOSAL_READY envelope "
            "missing entry/stop -- WP-3/WP-4 guarantee these non-None for READY; refusing to "
            "prepare a candidate from a broken invariant rather than trusting it blindly."
        )

    # TradeCandidate.take_profit is Optional[float]=None by its own existing contract --
    # absence is explicitly permitted, not a fail-closed condition (unlike entry/stop above).
    take_profit = envelope.targets[0] if envelope.targets else None

    return TradeCandidate(
        direction=_DIRECTION_MAP[envelope.direction],
        entry_price=envelope.entry,
        stop_loss=envelope.stop,
        take_profit=take_profit,
        # risk_percent/risk_amount/equity/symbol_meta/current_price/management_policy all
        # stay at TradeCandidate's own None defaults -- never fabricated here (see module
        # docstring: no MT5 dependency, no invented risk policy).
    )


def canonical_proposal_to_trade_proposal(
    envelope: CanonicalProposal, *, analysis_summary: str = "", evidence: Tuple[str, ...] = (),
) -> TradeProposal:
    """Pure (no store write -- assistant.commands.build_proposal_from_canonical() owns
    that, mirroring build_proposal()'s own split of "construct" vs. "persist"). Reuses
    envelope.proposal_envelope_id AS the TradeProposal's own proposal_id -- WP-4's
    already-deterministic identity, never re-derived with a second scheme (see
    proposal_envelope.adapters.opportunity_adapter's own identity discipline)."""
    candidate = canonical_proposal_to_trade_candidate(envelope)  # raises on non-READY/malformed

    now = datetime.now(timezone.utc)
    expires_at = _iso_to_datetime(envelope.plan_expires_at) or (
        now + timedelta(minutes=_DEFAULT_TTL_MINUTES)
    )

    return TradeProposal(
        proposal_id=envelope.proposal_envelope_id,
        created_at=now,
        expires_at=expires_at,
        symbol=envelope.symbol,
        timeframe="",  # CanonicalProposal carries no timeframe field -- never invented
        candidate=candidate,
        analysis_summary=analysis_summary,
        evidence=evidence,
    )


def _direction_to_side(direction: str) -> str:
    return "BUY" if direction == "LONG" else "SELL"


def trade_command_template(
    trade_proposal: TradeProposal, *, command_id: Optional[str] = None,
) -> TradeCommand:
    """A PREPARED, unconfirmed TradeCommand -- constructing this object performs no I/O
    and never executes anything (execution.models.TradeCommand's own docstring: "Never
    executed by constructing one"). risk_percent/volume are left None
    (REQUIRED_OWNER_INPUTS) -- the caller must supply them explicitly, or accept
    execute()'s own fail-closed VOLUME_UNAVAILABLE rejection; this module never invents
    a risk percentage or a default volume."""
    candidate = trade_proposal.candidate
    return TradeCommand(
        command_id=command_id or str(uuid.uuid4()),
        action="OPEN",
        symbol=trade_proposal.symbol,
        source=ExecutionSource.ASSISTANT_PROPOSAL,
        side=_direction_to_side(candidate.direction),
        entry=candidate.entry_price,
        sl=candidate.stop_loss,
        tp=candidate.take_profit,
        proposal_id=trade_proposal.proposal_id,
    )
