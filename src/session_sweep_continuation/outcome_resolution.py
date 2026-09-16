"""GAP_3_OUTCOME_RESOLUTION remediation: deterministic trade-lifecycle outcome
resolution for ST_SESSION_SWEEP_CONTINUATION_V1 campaign entries.

Before this module, nothing in the package computed realized_R / win-loss outcomes --
CampaignEntry.realized_r/realized_cash were declared but never populated by any code
path (see the reconciliation milestone's own root-cause finding).

REUSE, NOT REINVENTION: this repository already has ONE established, owner-signed
outcome-resolution convention for a session-sweep strategy --
scripts/resolve_forward_shadow_outcomes.py (AG_TRADE_OUTCOME_RESOLVER_V1,
AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED, applied to ST_ASIAN_SWEEP_5R_V1). This module
reuses that convention's SAME_BAR_POLICY (a candle touching both a stop and a target in
the same bar is AMBIGUOUS_SEQUENCE -- never resolved by assumed intrabar ordering) and
its general lifecycle shape (phase 1: full position vs stop/first-target; phase 2:
runner at breakeven vs stop/second-target; unresolved-by-cutoff => resolved at last
candle close), adapted to THIS strategy's own, different trade-management config
(trade_management.partial_target_pct/runner_pct/runner_target_r in
strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml) rather than ST_ASIAN_SWEEP_5R_V1's
75/25 TP1/TP2 split. No new trade-management parameter is introduced here.

ENTRY/FILL SEMANTIC (per this strategy's own setups.py: S1/S2/S3 entry_price is always
the trigger candle's own CLOSE): exactly like ST_ASIAN_SWEEP_5R_V1's own resolver
documents for its strategy, there is no separate resting/pending-order phase for this
strategy either -- every accepted CampaignEntry is FILLED by construction, at the
trigger candle's own recorded close, at the moment the stop engine accepts it. There is
therefore no ORDER_PENDING/EXPIRED state to simulate for THIS strategy's entries (order
semantics are effectively MARKET-at-signal-close) -- order_state is always
"ORDER_FILLED" for an accepted CampaignEntry, and this is reported explicitly rather
than silently omitting the PENDING/EXPIRED states the lifecycle spec describes for a
resting-order strategy this one is not.

INTERPRETATION FLAGGED, NOT SILENTLY ASSUMED (P18): trade_management.partial_target_mode
= "NEXT_LIQUIDITY_TARGET" is not concretely defined anywhere else in the repository for
this strategy. This module interprets it as the OPPOSITE session-box boundary (the same
"OPPOSITE_SESSION_BOUNDARY" concept ST_ASIAN_SWEEP_5R_V1's own signed TP1 definition
already uses in this exact session-box architecture) -- the nearest liquidity level this
package's own evidence (the frozen reference session high/low) actually provides,
rather than inventing a new liquidity-detection mechanism. This is an explicit
INTERPRETATION requiring the same kind of owner sign-off
AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 P1A gave ST_ASIAN_SWEEP_5R_V1's own
ambiguity -- flagged in every resolved record's `partial_target_interpretation` field,
never silently assumed authoritative.

v1.0.1 SEMANTIC_BUGFIX (PARTIAL_TARGET_DIRECTION_INVERSION): from v1.0.0's introducing
commit through v1.0.0, the LONG/SHORT mapping below was implemented inverted relative to
the OPPOSITE_SESSION_BOUNDARY convention this docstring already claimed to reuse (LOW for
LONG / HIGH for SHORT, instead of HIGH for LONG / LOW for SHORT as in
src/execution/validator.py and scripts/resolve_forward_shadow_outcomes.py). Owner-adjudicated
in the SSC V1.0.1 EXIT CONTRACT SEMANTIC REMEDIATION mission (OPTION_A) on repository
semantic/provenance evidence only, not economic performance. This is now an owner-signed
convention for THIS strategy, not merely a borrowed interpretation. Pre-remediation
economic evidence generated under the inverted mapping remains classified
PRE_REMEDIATION_NON_COUNTING per existing governance and is not retroactively revised by
this fix.

Invariant (P15): TARGET_HIT_BEFORE_FILL != WIN, STOP_HIT_BEFORE_FILL != LOSS -- outcome
metrics are only ever computed from candles strictly AFTER entry_time (the fill has
already happened by construction at entry_time; nothing before it is consulted).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from strategy_engine.session.candles import Candle

SAME_BAR_POLICY = "AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER"
PARTIAL_TARGET_INTERPRETATION = (
    "NEXT_LIQUIDITY_TARGET interpreted as OPPOSITE_SESSION_BOUNDARY (reference session "
    "high/low) -- same interpretation concept as ST_ASIAN_SWEEP_5R_V1's own signed TP1 "
    "definition in this session-box architecture; owner-adjudicated OPTION_A as of "
    "v1.0.1 (SEMANTIC_BUGFIX: PARTIAL_TARGET_DIRECTION_INVERSION) -- LONG targets "
    "reference_high, SHORT targets reference_low."
)

TERMINAL_RESOLVED_STATES = {
    "RESOLVED_SL", "RESOLVED_PARTIAL_BE", "RESOLVED_PARTIAL_RUNNER_TARGET", "RESOLVED_SESSION_EXIT",
}


@dataclass
class ResolvedTradeOutcome:
    campaign_id: str
    setup_model: str
    direction: str
    entry_time: str
    entry_price: float
    stop_price: float
    partial_target_price: Optional[float]
    partial_target_interpretation: str
    runner_target_r: float
    order_state: str
    terminal_state: str
    event_sequence: List[dict] = field(default_factory=list)
    gross_R: Optional[float] = None
    spread_cost_R: Optional[float] = None
    commission_cost_R: Optional[float] = None
    slippage_cost_R: Optional[float] = None
    net_R: Optional[float] = None
    cost_status: str = "UNAVAILABLE"
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "campaign_id": self.campaign_id, "setup_model": self.setup_model, "direction": self.direction,
            "entry_time": self.entry_time, "entry_price": self.entry_price, "stop_price": self.stop_price,
            "partial_target_price": self.partial_target_price,
            "partial_target_interpretation": self.partial_target_interpretation,
            "runner_target_r": self.runner_target_r, "order_state": self.order_state,
            "terminal_state": self.terminal_state, "event_sequence": self.event_sequence,
            "gross_R": self.gross_R, "spread_cost_R": self.spread_cost_R,
            "commission_cost_R": self.commission_cost_R, "slippage_cost_R": self.slippage_cost_R,
            "net_R": self.net_R, "cost_status": self.cost_status, "note": self.note,
        }


def resolve_campaign_entry(
    *,
    campaign_id: str,
    setup_model: str,
    direction: str,
    entry_time,
    entry_price: float,
    stop_price: float,
    reference_high: float,
    reference_low: float,
    runner_target_r: float,
    partial_pct: float,
    runner_pct: float,
    subsequent_candles: Sequence[Candle],
    session_exit_time,
    friction,  # friction.FrictionEstimate, already computed with cost_status stamped
) -> ResolvedTradeOutcome:
    """`subsequent_candles` must be every candle strictly after entry_time, already
    filtered to those whose own close time is <= session_exit_time (the caller's
    responsibility, matching sessions.py's own no-future-contamination convention) --
    this function never looks beyond what it is given, and never consults anything at
    or before entry_time (fill invariant)."""
    is_long = direction == "LONG"
    risk = abs(entry_price - stop_price)

    partial_target_price = reference_high if is_long else reference_low
    # A NEXT_LIQUIDITY_TARGET on the wrong side of entry (already passed) is not a valid
    # forward target -- fail closed to "no partial target available" rather than
    # computing a nonsensical negative-R first leg.
    if is_long and partial_target_price <= entry_price:
        partial_target_price = None
    if not is_long and partial_target_price >= entry_price:
        partial_target_price = None

    base = dict(
        campaign_id=campaign_id, setup_model=setup_model, direction=direction,
        entry_time=str(entry_time), entry_price=entry_price, stop_price=stop_price,
        partial_target_price=partial_target_price,
        partial_target_interpretation=PARTIAL_TARGET_INTERPRETATION,
        runner_target_r=runner_target_r, order_state="ORDER_FILLED",
    )

    cost_status, total_friction_r, cost_fields = _friction_breakdown(friction, risk)

    if not subsequent_candles:
        return ResolvedTradeOutcome(
            **base, terminal_state="UNRESOLVED_NO_DATA", cost_status=cost_status,
            note="no candles available after entry_time before session_exit_time",
        )

    if partial_target_price is None:
        # No valid forward partial target -- resolve the FULL position against SL vs
        # session exit only (never silently substitute a synthetic target).
        return _resolve_full_position_only(base, is_long, entry_price, stop_price, risk,
                                            subsequent_candles, cost_status, total_friction_r, cost_fields)

    partial_R = (partial_target_price - entry_price) / risk if is_long else (entry_price - partial_target_price) / risk

    # --- Phase 1: full position, SL vs partial target ---
    partial_index = None
    for i, c in enumerate(subsequent_candles):
        sl_hit = (c.low <= stop_price) if is_long else (c.high >= stop_price)
        pt_hit = (c.high >= partial_target_price) if is_long else (c.low <= partial_target_price)
        if sl_hit and pt_hit:
            return ResolvedTradeOutcome(
                **base, terminal_state="AMBIGUOUS_SEQUENCE", cost_status=cost_status,
                event_sequence=[{"time": str(c.time), "event": "SL_AND_PARTIAL_TARGET_SAME_CANDLE"}],
                note=f"{SAME_BAR_POLICY}: candle at {c.time} touches both SL and partial target",
            )
        if sl_hit:
            gross_R = -1.0
            net_R = _apply_cost(gross_R, total_friction_r)
            return ResolvedTradeOutcome(
                **base, terminal_state="RESOLVED_SL",
                event_sequence=[{"time": str(c.time), "event": "SL"}],
                gross_R=gross_R, net_R=net_R, cost_status=cost_status,
                **cost_fields,
            )
        if pt_hit:
            partial_index = i
            break

    if partial_index is None:
        last = subsequent_candles[-1]
        exit_price = last.close
        gross_R = ((exit_price - entry_price) / risk) if is_long else ((entry_price - exit_price) / risk)
        net_R = _apply_cost(gross_R, total_friction_r)
        return ResolvedTradeOutcome(
            **base, terminal_state="RESOLVED_SESSION_EXIT",
            event_sequence=[{"time": str(last.time), "event": "SESSION_EXIT_FULL_POSITION", "exit_price": exit_price}],
            gross_R=gross_R, net_R=net_R, cost_status=cost_status,
            **cost_fields,
        )

    # --- Phase 2: runner, BE-stop vs fixed-R runner target ---
    partial_event = {
        "time": str(subsequent_candles[partial_index].time),
        "event": "PARTIAL_TARGET",
        "exit_price": partial_target_price,
        "gross_R_delta": partial_pct * partial_R,
        "quantity_before": 1.0,
        "quantity_after": runner_pct,
    }
    be_price = entry_price
    for c in subsequent_candles[partial_index:]:
        if c is subsequent_candles[partial_index]:
            continue  # BE stop not armed until the candle AFTER the partial-target candle
        be_hit = (c.low <= be_price) if is_long else (c.high >= be_price)
        runner_target_price = entry_price + runner_target_r * risk if is_long else entry_price - runner_target_r * risk
        rt_hit = (c.high >= runner_target_price) if is_long else (c.low <= runner_target_price)
        if be_hit and rt_hit:
            return ResolvedTradeOutcome(
                **base, terminal_state="AMBIGUOUS_SEQUENCE", cost_status=cost_status,
                event_sequence=[{"time": str(c.time), "event": "BE_AND_RUNNER_TARGET_SAME_CANDLE"}],
                note=f"{SAME_BAR_POLICY}: runner leg BE stop and target both touched in {c.time}",
            )
        if be_hit:
            gross_R = partial_pct * partial_R + runner_pct * 0.0
            net_R = _apply_cost(gross_R, total_friction_r)
            return ResolvedTradeOutcome(
                **base, terminal_state="RESOLVED_PARTIAL_BE",
                event_sequence=[partial_event, {"time": str(c.time), "event": "RUNNER_BE_STOP",
                                "exit_price": be_price, "gross_R_delta": 0.0,
                                "quantity_before": runner_pct, "quantity_after": 0.0}],
                gross_R=gross_R, net_R=net_R, cost_status=cost_status,
                **cost_fields,
            )
        if rt_hit:
            gross_R = partial_pct * partial_R + runner_pct * runner_target_r
            net_R = _apply_cost(gross_R, total_friction_r)
            return ResolvedTradeOutcome(
                **base, terminal_state="RESOLVED_PARTIAL_RUNNER_TARGET",
                event_sequence=[partial_event, {"time": str(c.time), "event": "RUNNER_TARGET_HIT",
                                "exit_price": runner_target_price, "gross_R_delta": runner_pct * runner_target_r,
                                "quantity_before": runner_pct, "quantity_after": 0.0}],
                gross_R=gross_R, net_R=net_R, cost_status=cost_status,
                **cost_fields,
            )

    last = subsequent_candles[-1]
    runner_R = ((last.close - entry_price) / risk) if is_long else ((entry_price - last.close) / risk)
    gross_R = partial_pct * partial_R + runner_pct * runner_R
    net_R = _apply_cost(gross_R, total_friction_r)
    return ResolvedTradeOutcome(
        **base, terminal_state="RESOLVED_SESSION_EXIT",
        event_sequence=[partial_event, {"time": str(last.time), "event": "SESSION_EXIT_RUNNER",
                        "exit_price": last.close, "gross_R_delta": runner_pct * runner_R,
                        "quantity_before": runner_pct, "quantity_after": 0.0}],
        gross_R=gross_R, net_R=net_R, cost_status=cost_status,
        **cost_fields,
    )


def _resolve_full_position_only(base, is_long, entry_price, stop_price, risk, candles, cost_status, total_friction_r, cost_fields):
    for c in candles:
        sl_hit = (c.low <= stop_price) if is_long else (c.high >= stop_price)
        if sl_hit:
            gross_R = -1.0
            net_R = _apply_cost(gross_R, total_friction_r)
            return ResolvedTradeOutcome(
                **base, terminal_state="RESOLVED_SL",
                event_sequence=[{"time": str(c.time), "event": "SL"}],
                gross_R=gross_R, net_R=net_R, cost_status=cost_status,
                **cost_fields,
            )
    last = candles[-1]
    gross_R = ((last.close - entry_price) / risk) if is_long else ((entry_price - last.close) / risk)
    net_R = _apply_cost(gross_R, total_friction_r)
    return ResolvedTradeOutcome(
        **base, terminal_state="RESOLVED_SESSION_EXIT",
        event_sequence=[{"time": str(last.time), "event": "SESSION_EXIT_FULL_POSITION", "exit_price": last.close}],
        gross_R=gross_R, net_R=net_R, cost_status=cost_status,
        **cost_fields,
    )


def _apply_cost(gross_R: float, total_friction_r: Optional[float]) -> Optional[float]:
    if total_friction_r is None:
        return None  # COST_STATUS=UNAVAILABLE -- never silently report gross as net
    return gross_R - total_friction_r


def _friction_breakdown(friction, risk: float):
    """Returns (cost_status, total_friction_r, cost_fields) where cost_fields is a dict
    of {spread_cost_R, commission_cost_R, slippage_cost_R} computed from THIS trade's
    own risk distance and friction.py's own per-component pip estimate (P19: report
    each component separately, never just an undifferentiated total; P20: uses this
    strategy's own configured pip_size via friction.total_price/total_pips, not an
    assumed universal EURUSD/GBPUSD pip constant)."""
    if friction is None or friction.cost_status == "UNAVAILABLE" or not risk or friction.total_pips in (None, 0):
        return "UNAVAILABLE", None, {"spread_cost_R": None, "commission_cost_R": None, "slippage_cost_R": None}
    pip_size = friction.total_price / friction.total_pips
    spread_r = (friction.spread_pips * pip_size) / risk
    commission_r = (friction.commission_pips * pip_size) / risk
    slippage_r = (friction.slippage_pips * pip_size) / risk
    total_friction_r = spread_r + commission_r + slippage_r
    return friction.cost_status, total_friction_r, {
        "spread_cost_R": spread_r, "commission_cost_R": commission_r, "slippage_cost_R": slippage_r,
    }
