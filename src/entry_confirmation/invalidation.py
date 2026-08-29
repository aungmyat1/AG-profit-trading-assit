"""Deterministic per-maneuver invalidation (task: "SMC operational completion" phase).
Each M model owns its own invalidation semantics -- this module does NOT define one
generic rule; it defines the SHARED PLUMBING two of the three models already computed
but never exposed, plus a distinct rule for the third:

    M1 (CHARACTER_CHANGE_WITH_INDUCEMENT) and M3 (SWEEP_DROP_PUMP) both already call
    `entry_array.py::evaluate_entry_array()`, which already computes
    `structural_invalidation_candidates` = [sweep/inducement price] + [entry Order
    Block's far boundary, if associated]. `engine_v2_1.py::evaluate_reversal_sweep_shift`
    (M3's own delegate) already applies the invalidation comparison
    (`current_price < min(...)` for LONG / `current_price > max(...)` for SHORT) --
    this module only factors that EXACT, already-frozen comparison out so M1 (which
    computes the same candidates but previously discarded them) can reuse it verbatim,
    never inventing a second rule.

    M2 (SUPPLY_DEMAND_SHIFT) has no sweep/inducement concept by design (see that
    module's own docstring) -- its natural invalidation source is the NEW controlling
    zone that IS the M2 thesis: reusing `supply_demand.ZoneStatus.INVALIDATED` exactly
    as `ob_contract.py` already computes it (closed-candle close-beyond-boundary), the
    same convention M2 already reuses for the OLD zone's failure. See
    `m2_invalidation()` below.

Trigger honesty (spec section 8): M1/M3's trigger is genuinely a LIVE-PRICE comparison
(`current_price`, i.e. the live tick bid used throughout this pipeline) -- that is
`engine_v2_1`'s existing, unmodified behavior, not a closed-candle check, and this
module labels it exactly that rather than mislabeling it CLOSE. M2's trigger IS a
closed-candle close-beyond check (`ZoneStatus.INVALIDATED`'s own frozen definition).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from supply_demand.models import ZoneResult, ZoneRole, ZoneStatus

from .models import CandidateDirection
from .models_v2_1 import EntryArrayContext

TRIGGER_LIVE_PRICE = "LIVE_PRICE"  # current tick vs. a structural price -- engine_v2_1's existing rule
TRIGGER_CLOSED_CANDLE_CLOSE = "CLOSED_CANDLE_CLOSE"  # supply_demand ZoneStatus.INVALIDATED's own rule

SOURCE_INDUCEMENT_LEVEL = "INDUCEMENT_LEVEL"
SOURCE_LIQUIDITY_SWEEP_LEVEL = "LIQUIDITY_SWEEP_LEVEL"
SOURCE_ENTRY_ORDER_BLOCK_BOUNDARY = "ENTRY_ORDER_BLOCK_BOUNDARY"
SOURCE_NEW_CONTROLLING_ZONE_BOUNDARY = "NEW_CONTROLLING_ZONE_BOUNDARY"


@dataclass(frozen=True)
class ManeuverInvalidation:
    """Attach this (or None -- see each function's docstring for when it is honestly
    undefined) to the maneuver result. `price`/`source_type`/`reason`/`trigger` are
    always populated together; `triggered` says whether the CURRENT snapshot has
    actually breached it yet (False = this is the invalidation LEVEL, not yet hit)."""

    price: float
    source_type: str
    reason: str
    trigger: str
    triggered: bool = False


def entry_array_invalidation(
    entry_array: EntryArrayContext,
    direction: CandidateDirection,
    current_price: Optional[float],
    primary_price: Optional[float],
    primary_source_type: str,
) -> Optional[ManeuverInvalidation]:
    """Shared by M1 and M3 -- both call `evaluate_entry_array()` with `sweep_price` set
    to their own model's sweep/inducement level, so `entry_array.
    structural_invalidation_candidates` already contains exactly [that level] plus
    ([entry-OB far boundary] if an entry Order Block is associated), per
    `entry_array.py`'s own frozen construction (never a second rule here). Returns None
    when no candidate exists at all (nothing to invalidate against yet -- honest
    absence, not UNDEFINED-as-a-permanent-gap: it becomes defined the moment an entry
    array forms, same as READY itself only becomes reachable then)."""
    candidates = entry_array.structural_invalidation_candidates
    if not candidates:
        return None

    if direction == CandidateDirection.LONG:
        trigger_price = min(candidates)
        triggered = current_price is not None and current_price < trigger_price
    elif direction == CandidateDirection.SHORT:
        trigger_price = max(candidates)
        triggered = current_price is not None and current_price > trigger_price
    else:
        return None

    source_type = primary_source_type if primary_price is not None and trigger_price == primary_price \
        else SOURCE_ENTRY_ORDER_BLOCK_BOUNDARY
    reason = (
        f"{'LONG' if direction == CandidateDirection.LONG else 'SHORT'} invalidated: "
        f"live price crossed {source_type} at {trigger_price}."
    ) if triggered else (
        f"Invalidation level ({source_type} at {trigger_price}) not yet breached by the current live price."
    )

    return ManeuverInvalidation(price=trigger_price, source_type=source_type, reason=reason,
                                 trigger=TRIGGER_LIVE_PRICE, triggered=triggered)


def m2_invalidation(new_zone: Optional[ZoneResult]) -> Optional[ManeuverInvalidation]:
    """M2 has no sweep/inducement concept (see module docstring) -- its invalidation
    source is the NEW controlling zone (the zone whose formation IS the M2 thesis)
    failing exactly the way `supply_demand`/`ob_contract.py` already define zone
    failure: a closed candle beyond the zone's own boundary
    (`ZoneStatus.INVALIDATED`), never a second rule invented here. Returns None when no
    new zone was identified yet -- honest absence, not a gap: M2 cannot have an
    invalidation reference before it has a controlling zone to invalidate."""
    if new_zone is None or new_zone.low is None or new_zone.high is None:
        return None

    if new_zone.role == ZoneRole.DEMAND:
        boundary = new_zone.low
    elif new_zone.role == ZoneRole.SUPPLY:
        boundary = new_zone.high
    else:
        return None

    triggered = new_zone.status == ZoneStatus.INVALIDATED
    reason = (
        f"New controlling {new_zone.role.value} zone closed beyond its own boundary at {boundary}."
        if triggered else
        f"Invalidation level (new controlling {new_zone.role.value} zone boundary at {boundary}) "
        f"not yet closed-beyond."
    )
    return ManeuverInvalidation(price=boundary, source_type=SOURCE_NEW_CONTROLLING_ZONE_BOUNDARY, reason=reason,
                                 trigger=TRIGGER_CLOSED_CANDLE_CLOSE, triggered=triggered)
