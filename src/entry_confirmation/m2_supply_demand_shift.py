"""M2 = SUPPLY_DEMAND_SHIFT -- one of three interchangeable M5 confirmation maneuvers in
SMC_CONDITIONAL_ENTRY_V2 (entry_models_v1.py). NOT a repackaged sweep model: M2 is never
`H1 POI -> sweep -> CHoCH -> FVG` (that pipeline is M3's, see m3_sweep_drop_pump.py).
M2's defining feature is that M5 order flow actually transitioned after the HTF
reaction -- the existing opposing-role M5 zone must be shown to have genuinely FAILED
(closed beyond, not merely wicked/mitigated) before any "shift" claim is made, and a new
opposing-direction zone must then form. No liquidity sweep is involved anywhere in this
model; that is precisely what keeps M2 distinct from M1 (inducement sweep) and M3 (HTF
liquidity sweep).

DECOUPLED FROM E2 (spec section 10): this maneuver used to require an `E2Result`
specifically. It now accepts ANY qualified `EConditionResult` (from E1, E2, or E3) -- a
Daily-gap reaction or an HTF-liquidity-sweep reclaim can trigger a supply/demand-shift
check on M5 just as validly as an H1-POI reaction. The composer decides which E's to
feed it; this module only checks `eligible_for_confirmation` and `direction`. M2 derives
its OWN direction independently from the caller-supplied opposing zone's role (a SUPPLY
zone failing implies a bullish shift, a DEMAND zone failing implies bearish) -- if that
contradicts the E-condition's direction, this reports `NO_VALID_COMBINATION`.

Bearish: qualified bearish E-condition -> existing M5 DEMAND zone -> demand FAILS
(closes beyond, ZoneStatus.INVALIDATED -- reused verbatim from supply_demand, never a
new invalidation rule) -> bearish displacement -> new M5 SUPPLY zone forms -> FVG/OB
entry array -> retracement -> SHORT READY. Bullish is the exact mirror (SUPPLY fails ->
new DEMAND).

ZONE_FAILURE reuses `supply_demand.ZoneStatus.INVALIDATED` exactly as
`supply_demand/ob_contract.py`/`native_zones.py` already compute it (a closed candle
beyond the zone boundary, with no reclaim). This module only locates WHEN that already-
computed status became true, by scanning the same caller-supplied M5 candles for the
first close-beyond-boundary bar after the zone's own origin_time -- the same mechanical
"find the causal timestamp for an already-signed status" technique
`e2_h1_poi_reaction.py` uses for POI-interaction time. Never a second invalidation rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence, Tuple

from market_structure import MarketStructureConfig, StructurePointKind, structural_breaks_for_candles
from strategy_engine.session import Candle
from supply_demand import ValidatedOrderBlock, ZoneResult
from supply_demand.models import ZoneRole, ZoneStatus

from .displacement import evaluate_displacement
from .entry_array import evaluate_entry_array
from .entry_models_v1 import EConditionResult, EntryModelState
from .gap import evaluate_gap_context
from .models import CandidateDirection

M2_SUPPLY_DEMAND_SHIFT_V1 = "M2_SUPPLY_DEMAND_SHIFT_V1"
MANEUVER = "M2"

_OPPOSING_ROLE_FOR_DIRECTION = {
    CandidateDirection.SHORT: ZoneRole.DEMAND,  # bearish shift fails EXISTING demand
    CandidateDirection.LONG: ZoneRole.SUPPLY,  # bullish shift fails EXISTING supply
}
_NEW_ROLE_FOR_DIRECTION = {
    CandidateDirection.SHORT: ZoneRole.SUPPLY,  # new supply forms after the shift
    CandidateDirection.LONG: ZoneRole.DEMAND,
}
_CHOCH_KIND_FOR_DIRECTION = {
    CandidateDirection.SHORT: StructurePointKind.BEARISH_CHOCH,
    CandidateDirection.LONG: StructurePointKind.BULLISH_CHOCH,
}
_DIRECTION_FOR_OPPOSING_ROLE = {
    ZoneRole.DEMAND: CandidateDirection.SHORT,  # a failing DEMAND zone implies a bearish shift
    ZoneRole.SUPPLY: CandidateDirection.LONG,  # a failing SUPPLY zone implies a bullish shift
}


@dataclass(frozen=True)
class M2Result:
    version: str = M2_SUPPLY_DEMAND_SHIFT_V1
    maneuver: str = MANEUVER
    symbol: str = ""
    entry_condition: Optional[str] = None  # which E fed this evaluation ("E1"/"E2"/"E3"), if any
    direction: Optional[str] = None
    state: str = EntryModelState.NOT_APPLICABLE.value

    pre_shift_flow: Optional[str] = None  # "DEMAND" / "SUPPLY" -- the role that must fail
    opposing_zone: Optional[ZoneResult] = None
    opposing_zone_status: Optional[str] = None
    zone_failure: bool = False
    zone_failure_time: Optional[datetime] = None

    structural_break: Optional[float] = None  # CHoCH price
    structural_break_time: Optional[datetime] = None
    displacement_confirmed: bool = False

    new_zone: Optional[ZoneResult] = None
    new_zone_type: Optional[str] = None

    entry_fvg: Optional[ZoneResult] = None
    entry_ob: Optional[ValidatedOrderBlock] = None
    retrace: bool = False

    evidence: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


def _zone_failure_time(zone: ZoneResult, direction: CandidateDirection, candles: Sequence[Candle]) -> Optional[datetime]:
    if zone.status != ZoneStatus.INVALIDATED or zone.low is None or zone.high is None:
        return None
    after = [c for c in candles if zone.origin_time is None or c.time > zone.origin_time]
    for candle in after:
        if direction == CandidateDirection.SHORT and candle.close is not None and candle.close < zone.low:
            return candle.time
        if direction == CandidateDirection.LONG and candle.close is not None and candle.close > zone.high:
            return candle.time
    return None


def _zone_in_window(zones: Sequence[ZoneResult], role: ZoneRole, start: datetime, end: datetime) -> Optional[ZoneResult]:
    matching = sorted(
        (z for z in zones if z.role == role and z.origin_time is not None and start <= z.origin_time <= end),
        key=lambda z: z.origin_time,
    )
    return matching[0] if matching else None


def _ob_for_event(order_blocks: Sequence[ValidatedOrderBlock], event_time: datetime) -> Optional[ValidatedOrderBlock]:
    return next(
        (ob for ob in order_blocks if ob.structure_event is not None and ob.structure_event.time_utc == event_time),
        None,
    )


def evaluate_m2_supply_demand_shift(
    symbol: str,
    e_condition: Optional[EConditionResult],
    opposing_zone: Optional[ZoneResult],
    m5_candles: Sequence[Candle] = (),
    m5_displacement_history: Sequence[Candle] = (),
    m5_candidate_zones: Sequence[ZoneResult] = (),  # candidate new-direction zones (generic supply_demand output)
    m5_fvg_zones: Sequence[ZoneResult] = (),
    m5_order_blocks: Sequence[ValidatedOrderBlock] = (),
    current_price: Optional[float] = None,
    evaluation_time: Optional[datetime] = None,
    structure_config: Optional[MarketStructureConfig] = None,
) -> M2Result:
    entry_condition = e_condition.entry_condition if e_condition is not None else None
    if e_condition is None or not e_condition.eligible_for_confirmation:
        return M2Result(symbol=symbol, entry_condition=entry_condition, state=EntryModelState.NOT_APPLICABLE.value,
                         reason="No qualified E-condition supplied -- M2 not applicable.")

    e_direction = CandidateDirection(e_condition.direction) if e_condition.direction in (
        CandidateDirection.LONG.value, CandidateDirection.SHORT.value,
    ) else CandidateDirection.NONE
    if e_direction == CandidateDirection.NONE:
        return M2Result(symbol=symbol, entry_condition=entry_condition, state=EntryModelState.NOT_APPLICABLE.value,
                         reason="E-condition direction unresolved -- cannot determine M2 candidate direction.")

    if opposing_zone is None:
        return M2Result(symbol=symbol, entry_condition=entry_condition, direction=e_direction.value,
                         state=EntryModelState.WAITING_H1_REACTION.value,
                         reason="No pre-existing opposing-role M5 zone supplied -- cannot evidence a shift "
                                "without knowing what order flow is being replaced.")

    m2_direction = _DIRECTION_FOR_OPPOSING_ROLE.get(opposing_zone.role)
    if m2_direction != e_direction:
        # Direction alignment (spec section 10): the opposing zone's own role implies a
        # different shift direction than the E-condition qualified -- not a valid combination.
        return M2Result(symbol=symbol, entry_condition=entry_condition,
                         direction=m2_direction.value if m2_direction else None,
                         state=EntryModelState.NO_VALID_COMBINATION.value,
                         opposing_zone=opposing_zone, opposing_zone_status=opposing_zone.status.value,
                         reason=f"Supplied opposing zone role {opposing_zone.role.value} implies "
                                f"{m2_direction.value if m2_direction else 'an unresolved direction'}, which does "
                                f"not match the E-condition's {e_direction.value} direction.")

    direction = e_direction
    expected_role = _OPPOSING_ROLE_FOR_DIRECTION[direction]
    pre_shift_flow = expected_role.value

    zone_failure_time = _zone_failure_time(opposing_zone, direction, m5_candles)
    zone_failure = zone_failure_time is not None
    if not zone_failure:
        return M2Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_M5_CONFIRMATION.value,
                         pre_shift_flow=pre_shift_flow, opposing_zone=opposing_zone,
                         opposing_zone_status=opposing_zone.status.value, zone_failure=False,
                         reason="Opposing zone not yet INVALIDATED (closed beyond) -- no confirmed order-flow "
                                "failure. A CHoCH alone never substitutes for this (SUPPLY_DEMAND_SHIFT != CHoCH).")

    wanted_kind = _CHOCH_KIND_FOR_DIRECTION[direction]
    breaks = structural_breaks_for_candles(m5_candles, structure_config)
    qualifying = [
        b for b in breaks if b.kind == wanted_kind and b.time_utc >= zone_failure_time
        and (evaluation_time is None or b.time_utc <= evaluation_time)
    ]
    if not qualifying:
        return M2Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_M5_CONFIRMATION.value,
                         pre_shift_flow=pre_shift_flow, opposing_zone=opposing_zone,
                         opposing_zone_status=opposing_zone.status.value, zone_failure=True,
                         zone_failure_time=zone_failure_time,
                         reason="Zone failed but no causally-ordered closed-candle structural break found yet.")
    choch_point = qualifying[0]

    displacement_candle = next((c for c in m5_candles if c.time == choch_point.time_utc), None)
    displacement = evaluate_displacement(displacement_candle, direction, m5_displacement_history)
    if displacement.status.value != "PASS":
        return M2Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_M5_CONFIRMATION.value,
                         pre_shift_flow=pre_shift_flow, opposing_zone=opposing_zone,
                         opposing_zone_status=opposing_zone.status.value, zone_failure=True,
                         zone_failure_time=zone_failure_time, structural_break=choch_point.price,
                         structural_break_time=choch_point.time_utc, displacement_confirmed=False,
                         reason="Structural break confirmed but displacement does not qualify under "
                                "AG_ENTRY_DISPLACEMENT_V1.")

    new_role = _NEW_ROLE_FOR_DIRECTION[direction]
    leg_start, leg_end = zone_failure_time, choch_point.time_utc
    new_zone = _zone_in_window(m5_candidate_zones, new_role, leg_start, leg_end)
    fvg_zone = next(
        (z for z in m5_fvg_zones if z.origin_time is not None and leg_start <= z.origin_time <= leg_end), None,
    )
    order_block = _ob_for_event(m5_order_blocks, choch_point.time_utc)
    gap_context = evaluate_gap_context(fvg_zone) if fvg_zone is not None else None
    fvg_associated = fvg_zone is not None
    ob_associated = order_block is not None

    entry_array = evaluate_entry_array(
        gap_context=gap_context, fvg_associated=fvg_associated, ob=order_block, ob_associated=ob_associated,
        candidate_direction=direction, current_price=current_price,
    )

    if entry_array.entry_array_type == "NONE":
        state = EntryModelState.WAITING_M5_CONFIRMATION.value
    elif entry_array.entry_status == "ENTRY_REFERENCE_AVAILABLE":
        state = EntryModelState.READY.value
    else:
        state = EntryModelState.WAITING_M5_ENTRY.value

    return M2Result(
        symbol=symbol, entry_condition=entry_condition, direction=direction.value, state=state,
        pre_shift_flow=pre_shift_flow, opposing_zone=opposing_zone,
        opposing_zone_status=opposing_zone.status.value, zone_failure=True, zone_failure_time=zone_failure_time,
        structural_break=choch_point.price, structural_break_time=choch_point.time_utc, displacement_confirmed=True,
        new_zone=new_zone, new_zone_type=new_zone.family.value if new_zone is not None else None,
        entry_fvg=fvg_zone, entry_ob=order_block, retrace=entry_array.entry_status == "ENTRY_REFERENCE_AVAILABLE",
        evidence=(
            f"opposing_zone_failed@{zone_failure_time}", f"structural_break@{choch_point.time_utc}",
            f"entry_array={entry_array.entry_array_type}",
        ),
        reason=entry_array.reason,
    )
