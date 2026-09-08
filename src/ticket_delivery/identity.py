"""WP1 (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md) -- canonical logical
ticket identity and delivery-attempt identity for informational FX ticket delivery.

Reuses the existing deterministic occurrence key rather than inventing a second one:
`post_asian_pilot.proposal.PostAsianEntryProposal.setup_id` is already
`f"{strategy_id}:{cycle}:{symbol}:{trading_date}"` (verified against
tests/test_authorization_core.py's own fixtures, e.g.
"ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-07"). `logical_ticket_id()` below
extends that exact shape by one field, `strategy_version` -- the existing setup_id has
no version component, so a strategy-version bump evaluated on the same calendar date
for the same cycle/symbol could otherwise collide with the prior version's occurrence.
This is not a second competing identity; it is the same deterministic key with one
field added to close that one demonstrated gap. `post_asian_pilot.decision._decision_id`
was deliberately NOT reused here -- it hashes in `evaluation_time`, which differs on
every retry, so it cannot serve as a stable logical-ticket key (a retry must produce a
new delivery ATTEMPT, never a new logical ticket).
"""
from __future__ import annotations

import datetime as dt
import re

_ID_FIELD_SEPARATOR = "|"
_SAFE_FIELD = re.compile(r"^[A-Za-z0-9_.\-]+$")


class InvalidIdentityFieldError(ValueError):
    """A field value contains the identity separator or is otherwise unsafe to embed
    in a composite identity string -- fail closed rather than silently truncate or
    produce an ambiguous/collidable key."""


def _validate_field(name: str, value: str) -> str:
    if not value:
        raise InvalidIdentityFieldError(f"{name} must be a non-empty string")
    if not _SAFE_FIELD.match(value):
        raise InvalidIdentityFieldError(
            f"{name}={value!r} contains characters unsafe for a composite identity key "
            f"(must match {_SAFE_FIELD.pattern})"
        )
    return value


def logical_ticket_id(
    *, strategy_id: str, strategy_version: str, symbol: str, cycle: str, trading_date: dt.date,
) -> str:
    """Deterministic, stable across retries and process restarts -- same inputs always
    produce the same identity, and nothing time-of-evaluation-dependent is ever mixed
    in. Same occurrence -> one logical ticket, by construction (this is a pure
    function, not a lookup): calling it twice for the same occurrence returns the
    identical string, so a caller never needs a separate "is this the same ticket"
    check beyond string equality."""
    fields = [
        _validate_field("strategy_id", strategy_id),
        _validate_field("strategy_version", strategy_version),
        _validate_field("symbol", symbol),
        _validate_field("cycle", cycle),
        _validate_field("trading_date", trading_date.isoformat()),
    ]
    return _ID_FIELD_SEPARATOR.join(fields)


def delivery_attempt_id(*, logical_ticket_id_: str, attempt_number: int) -> str:
    """One logical ticket -> many possible delivery attempts, never the reverse. Retrying
    a delivery increments attempt_number; it never touches logical_ticket_id_."""
    if attempt_number < 1:
        raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")
    return f"{logical_ticket_id_}{_ID_FIELD_SEPARATOR}attempt-{attempt_number:03d}"


def correction_id(*, logical_ticket_id_: str, correction_number: int) -> str:
    """A correction to an already-archived occurrence keeps the SAME logical_ticket_id_
    (this is not a new occurrence) and receives its own correction identity, mirroring
    post_asian_pilot.report_archive's existing correction-NNN numbering convention."""
    if correction_number < 1:
        raise ValueError(f"correction_number must be >= 1, got {correction_number}")
    return f"{logical_ticket_id_}{_ID_FIELD_SEPARATOR}correction-{correction_number:03d}"
