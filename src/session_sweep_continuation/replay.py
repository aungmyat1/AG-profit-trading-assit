"""Deterministic replay driver for ST_SESSION_SWEEP_CONTINUATION_V1.

Does NOT reuse src/historical_replay/orchestrator.py's ChronologicalReplay directly --
that orchestrator is tightly coupled to a different, pre-existing signal system
(daytrading_runtime.conditional_entry_snapshot / entry_confirmation E1/E2/E3-M1/M2/M3),
which this new session/regime/BOS/FVG/campaign engine does not share (different
concepts, different state shapes, different setup identity). Forcing this engine's
setups through that orchestrator's SetupLedger/FunnelTracker would either silently
misuse its E/M vocabulary or require rewriting the orchestrator itself, both out of
scope and riskier than an isolated, narrowly-scoped driver. This module instead
reimplements the SAME two structural guarantees that orchestrator provides -- (1) step
a clock through closed bars only, calling the same live entrypoint each step, never
re-detecting the past, and (2) restart-safety via pure functional state (no in-process
global mutation the caller does not own) -- against this engine's own live entrypoint
(`step_engine` below). This is a documented, narrowest-compatible addition, not a
parallel backtester; recorded as a known integration gap in the final report.

Determinism/restart-safety: `run_replay` takes only (candles, config, symbol,
session_pair, trading_date) and returns a plain, JSON-serializable result -- no
filesystem writes, no wall-clock reads, no random values. Calling it twice with
identical inputs is asserted, by test, to produce an identical result
(tests/test_session_sweep_continuation_replay_determinism.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Sequence

from strategy_engine.session.candles import Candle

from market_intelligence.models import MarketBiasResult

from . import STRATEGY_ID, STRATEGY_VERSION
from .bias_gate import allowed_directions, rejection_reason
from .campaign import Campaign, CampaignStatus, allocate_risk, apply_entry, new_campaign
from .friction import estimate_friction
from .outcome_resolution import resolve_campaign_entry
from .regime import Regime, RegimeResult, classify_regime, required_regime_warmup
from .sessions import build_reference_session, session_windows_from_config, trade_session_candles
from .setups import (
    SetupModel,
    compute_continuation_signals,
    evaluate_s1_sweep_reversal,
    evaluate_s2_breakout_continuation,
    evaluate_s3_pullback_continuation,
)
from .state_machine import Event, State, transition
from .stop_engine import compute_stop, resolve_anchor_s1, resolve_anchor_s2, resolve_anchor_s3
from .swing_structure import BOSDirection, compute_atr, detect_bos, detect_fractal_swings, detect_fvg, swings_confirmed_by


@dataclass
class ReplayStepRecord:
    time: object
    event: str
    detail: Dict[str, object] = field(default_factory=dict)


@dataclass
class ReplayResult:
    symbol: str
    session_pair: str
    trading_date: object
    regime: Optional[str]
    campaign: Optional[Campaign]
    accepted_setups: List[dict]
    rejected_setups: List[dict]
    steps: List[ReplayStepRecord]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "session_pair": self.session_pair,
            "trading_date": str(self.trading_date),
            "regime": self.regime,
            "campaign_id": self.campaign.campaign_id if self.campaign else None,
            "campaign_status": self.campaign.status.value if self.campaign else None,
            "entry_count": self.campaign.entry_count if self.campaign else 0,
            "open_risk_pct": round(self.campaign.open_risk_pct, 6) if self.campaign else 0.0,
            "accepted_setups": self.accepted_setups,
            "rejected_setups": self.rejected_setups,
            "steps": [{"time": str(s.time), "event": s.event, "detail": s.detail} for s in self.steps],
        }


def _m1_subsequent_candles(
    m1_candles: Sequence[Candle], entry_time, session_exit_time,
) -> List[Candle]:
    """M1 fill/outcome-resolution slice for one accepted entry: every M1 candle whose
    bar-open time is strictly after `entry_time` (the M15 trigger candle's own close is
    the fill price -- P15 invariant, nothing at-or-before entry_time is ever consulted,
    exactly like the pre-existing M15 slicing this replaces) and whose bar-CLOSE time
    (open + 1 minute) is <= `session_exit_time` -- the same no-future-contamination /
    session-exit-cutoff convention sessions.py's own `_closed_candles_in_window`
    already enforces for M15, applied here at M1 granularity. `entry_time >=
    activation_time` is trivially satisfied by construction: for this strategy,
    activation_time == entry_time (no separate resting-order phase -- see
    outcome_resolution.py's own module docstring), so the strict `>` bound below IS the
    activation boundary."""
    return sorted(
        (c for c in m1_candles if entry_time < c.time and c.time + timedelta(minutes=1) <= session_exit_time),
        key=lambda c: c.time,
    )


def run_replay(
    candles: Sequence[Candle],
    config: dict,
    symbol: str,
    session_pair_id: str,
    trading_date,
    pip_size: float,
    pip_value_per_lot: float = 10.0,
    bias_result: Optional[MarketBiasResult] = None,
    m1_candles: Optional[Sequence[Candle]] = None,
    regime_result: Optional[RegimeResult] = None,
) -> ReplayResult:
    """Single-pass, deterministic replay over one symbol / session_pair /
    trading_date. Steps the clock forward one M15 close at a time through the
    trade_session window; only ever consumes candles already closed as of the current
    step (see sessions.py no-future-contamination guard).

    bias_result: the ONE canonical MarketBiasResult (market_intelligence.models) for
    this exact (symbol, decision_time, session_pair) decision cycle, already resolved
    by the caller BEFORE this call -- run_replay does not fetch, compute, or cache one
    itself (no I/O, unchanged from this module's existing pure-function design). It is
    consumed as-is, frozen for the entire cycle (never recomputed mid-replay after
    seeing setup/fill/outcome data -- MarketBiasResult is itself a frozen dataclass, so
    this is also enforced at the language level for whatever single instance is
    passed). Omitting it (None) is equivalent to an UNAVAILABLE bias: every candidate
    this cycle is rejected BIAS_MISSING (fail-closed, AG_STRATEGY_DIRECTION_CONTRACT_V1
    invariant P32) -- this is a strict narrowing of this function's prior behavior
    (previously direction-agnostic); see bias_gate.py for the full rule table.
    Strategy-local regime (regime.py) is unchanged and still exclusively decides which
    setup branch (S1/S2/S3) is eligible -- bias_result decides direction only.

    m1_candles: optional M1 series for FILL_RESOLUTION_INPUT (AG_ST_SESSION_SWEEP_
    CONTINUATION_FIRST_CANONICAL_REPLAY wiring). When supplied, each accepted entry's
    outcome is resolved against `_m1_subsequent_candles(m1_candles, entry_time,
    trade_end)` instead of the M15 trade_session slice -- same resolve_campaign_entry
    function, same economics (stop/target/friction/partial/runner formulas are entirely
    unchanged; only the granularity of the candle series they scan against changes).
    Omitting it (None, the default) preserves the exact prior M15-based outcome
    resolution byte-for-byte -- fully backward compatible with every existing caller
    and test that does not pass this parameter.

    regime_result: AG_PLAN2_GOLDEN_CANONICAL_COMPLETION_V1 -- an already-computed
    RegimeResult (session_sweep_continuation.regime) for this exact decision cycle,
    mirroring bias_result's own dependency-injection pattern exactly. When supplied,
    it is used AS-IS instead of calling classify_regime() internally -- the caller
    (typically canonical_consumer.run_canonical_shadow_cycle, which computes it via
    M15RegimeSkill from the SAME reference_closes/range_pips/candle_count this
    function would otherwise derive itself) is responsible for having computed it from
    identical inputs; run_replay performs no comparison or reconciliation of its own.
    Omitting it (None, the default) preserves the exact prior classify_regime() call
    byte-for-byte -- fully backward compatible with every existing caller and test
    that does not pass this parameter."""
    windows = session_windows_from_config(config)[session_pair_id]
    ref_window, trade_window = windows["reference"], windows["trade"]

    permitted_directions = allowed_directions(bias_result, symbol)

    ref_end = ref_window.bounds_for_date(trading_date)[1]
    reference = build_reference_session(candles, ref_window, trading_date, ref_end, pip_size)

    steps: List[ReplayStepRecord] = [ReplayStepRecord(ref_end, "REFERENCE_SESSION_CLOSED", {
        "high": reference.high, "low": reference.low, "range_pips": reference.range_pips,
        "candle_count": reference.candle_count,
    })]
    steps.append(ReplayStepRecord(ref_end, "BIAS_RESOLVED", {
        "bias": bias_result.bias if bias_result is not None else None,
        "confidence": bias_result.confidence if bias_result is not None else None,
        "decision_cycle_id": bias_result.decision_cycle_id if bias_result is not None else None,
        "model_version": bias_result.model_version if bias_result is not None else None,
        "input_fingerprint": bias_result.input_fingerprint if bias_result is not None else None,
        "permitted_directions": sorted(permitted_directions),
    }))

    if reference.candle_count == 0 or reference.high is None:
        return ReplayResult(symbol, session_pair_id, trading_date, None, None, [], [], steps)

    # GAP_1_REGIME_LOOKBACK fix: classify_regime's EMA needs a trailing history of
    # ema_slow_period closes (config["regime"]["ema_slow_period"], default 50) to ever
    # return a non-None value. The single reference-session window (e.g. 6h == 24 M15
    # bars for ASIAN_LONDON) can never contain that many bars on its own -- that is the
    # root cause every real-data replay day previously classified UNKNOWN
    # (INSUFFICIENT_EMA_HISTORY) regardless of actual market condition. Fix: feed
    # classify_regime the full deterministic PRE-ROLL history of closes strictly BEFORE
    # ref_end (every candle already fully closed as of the decision point -- no
    # lookahead, see time-safety invariant below), not just the closes inside the
    # reference-session window. Pre-roll bars are used ONLY to warm up the EMA
    # calculation here; they are never passed to trade_session_candles/setup evaluators
    # and can therefore never themselves generate a campaign or count as an active
    # decision (PRE_ROLL_DATA_IS_CONTEXT_ONLY). If fewer than ema_slow_period closes
    # exist before ref_end (e.g. the very first days of a dataset), classify_regime's
    # own existing fail-closed behavior (ema() returns None -> UNKNOWN,
    # reason=INSUFFICIENT_EMA_HISTORY) is unchanged and still applies -- this is a
    # genuine INSUFFICIENT_CONTEXT case, not silently forced to a classification.
    required_warmup = required_regime_warmup(config)
    # Use the FULL deterministic pre-roll history available before ref_end (not just the
    # minimum required_warmup count) so the EMA is properly converged, exactly as a
    # continuously-running live engine's EMA state would be -- required_warmup is used
    # only as the documented, testable "is there enough context at all" threshold, never
    # to truncate the series ema() actually consumes. time safety: c.time < ref_end for a
    # bar-open timestamp means this bar's own close time (c.time + timeframe) is <=
    # ref_end, i.e. fully closed by the decision point -- consistent with sessions.py's
    # own no-future-contamination guard. This is pre-roll CONTEXT only: these bars are
    # never passed to trade_session_candles/the setup evaluators below, so they can never
    # themselves create a campaign (PRE_ROLL_DATA_IS_CONTEXT_ONLY).
    if regime_result is None:
        ref_closes = [c.close for c in candles if c.time < ref_end]
        regime_result = classify_regime(ref_closes, reference.range_pips, reference.candle_count, config)
    steps.append(ReplayStepRecord(ref_end, "REGIME_CLASSIFIED", {"regime": regime_result.regime.value, "reason": regime_result.reason}))

    if regime_result.regime == Regime.UNKNOWN:
        return ReplayResult(symbol, session_pair_id, trading_date, regime_result.regime.value, None, [], [], steps)

    trade_start, trade_end = trade_window.bounds_for_date(trading_date)
    trade_candles = trade_session_candles(candles, trade_window, trading_date, trade_end)

    accepted: List[dict] = []
    rejected: List[dict] = []
    campaign: Optional[Campaign] = None

    atr_cfg = config["atr"]
    atr_period = int(atr_cfg["period"])
    atr_buffer_mult = float(atr_cfg["stop_buffer_multiplier"])
    friction_cfg = config["friction"]
    min_stop_multiple = float(friction_cfg["minimum_stop_multiple"])

    candles_list = list(candles)
    time_to_index = {c.time: idx for idx, c in enumerate(candles_list)}  # perf: avoid an
    # O(n) list-copy + linear search per trade-session candle (candle timestamps are
    # unique in an M15 series) -- purely a replay-mechanics performance fix, identical
    # output to the previous list(candles).index(candle) lookup it replaces.
    swings = detect_fractal_swings(candles_list, bars_each_side=int(config["swing"]["fractal_bars_each_side"]))
    continuation_score_cfg = config["continuation_score"]
    minimum_continuation_score = int(continuation_score_cfg["minimum"])
    trade_mgmt_cfg = config["trade_management"]
    runner_target_r_cfg = float(trade_mgmt_cfg["runner_target_r"])
    partial_pct_cfg = float(trade_mgmt_cfg["partial_target_pct"])
    runner_pct_cfg = float(trade_mgmt_cfg["runner_pct"])

    for i, candle in enumerate(trade_candles):
        as_of = candle.time + timedelta(minutes=15)
        global_index = time_to_index[candle.time]

        confirmed_swings = swings_confirmed_by(swings, as_of)
        history = candles_list[: global_index + 1]
        atr_val = compute_atr(history, period=atr_period)
        bos_all = detect_bos(history, confirmed_swings, as_of)
        new_bos = [b for b in bos_all if b.break_candle_index == global_index]

        candidate = None
        s3_prior_bos = None
        # GAP_2_S3_REACHABILITY: branch policy per this strategy's own state machine
        # (state_machine.py) -- S1/S2 are only evaluated while no campaign yet exists at
        # this decision point (campaign is None); S3 is a SUBSEQUENT-STATE evaluation
        # that only ever applies once a campaign is already CAMPAIGN_ACTIVE (whether it
        # was opened by S1 or S2), and requires a BOS in the campaign's own direction to
        # have already occurred (its own required `prior_bos` parameter) -- this
        # mirrors S3's own documented anchor rule (stop_engine.resolve_anchor_s3:
        # "the most recent CONFIRMED swing formed AFTER the triggering BOS"). Campaign-
        # state gating (S1/S2 only when campaign is None, S3 only when campaign is
        # ACTIVE) makes S1/S2 and S3 branch-exclusive at every single candle by
        # construction -- no candle can ever produce two competing candidates.
        if regime_result.regime in (Regime.RANGE, Regime.TRANSITION) and campaign is None:
            candidate = evaluate_s1_sweep_reversal(candle, global_index, reference.high, reference.low, regime_result.regime)
        elif regime_result.regime in (Regime.TREND_UP, Regime.TREND_DOWN) and new_bos and campaign is None:
            candidate = evaluate_s2_breakout_continuation(new_bos[0], candle, regime_result.regime)
        elif campaign is not None and campaign.status == CampaignStatus.ACTIVE:
            wanted_bos_dir = BOSDirection.UP if campaign.direction == "LONG" else BOSDirection.DOWN
            matching_bos = [b for b in bos_all if b.direction == wanted_bos_dir and b.break_candle_index < global_index]
            if matching_bos:
                s3_prior_bos = max(matching_bos, key=lambda b: b.break_candle_index)
                signals = compute_continuation_signals(
                    history=history, candle=candle, candle_index=global_index,
                    direction=campaign.direction, prior_bos=s3_prior_bos,
                    confirmed_swings=confirmed_swings, config=config, pip_size=pip_size,
                )
                candidate = evaluate_s3_pullback_continuation(
                    s3_prior_bos, candle, global_index, campaign.direction, regime_result.regime,
                    signals, minimum_continuation_score,
                )

        if candidate is None:
            continue

        if candidate.direction not in permitted_directions:
            # MarketBiasResult is the ONE final directional authority (AG_STRATEGY_
            # DIRECTION_CONTRACT_V1) -- regime/setup logic above may have produced a
            # structurally valid candidate in the OPPOSITE direction to the resolved
            # bias (or bias may be NEUTRAL/UNAVAILABLE/missing); this strategy never
            # overrides that authority. Rejected, never silently dropped, so the
            # decision remains attributable (P4/P23 provenance).
            rejected.append({
                "setup_model": candidate.setup_model.value, "direction": candidate.direction,
                "reason": rejection_reason(bias_result, symbol), "time": str(candle.time),
            })
            continue

        if candidate.setup_model == SetupModel.S1:
            anchor = resolve_anchor_s1(candidate.direction, candidate.evidence["sweep_extreme_price"])
        elif candidate.setup_model == SetupModel.S2:
            anchor = resolve_anchor_s2(candidate.direction, new_bos[0])
        else:
            post_bos_swings = [s for s in confirmed_swings if s.index > s3_prior_bos.break_candle_index]
            fvg_cfg = config["fvg"]
            fvgs = detect_fvg(history, pip_size, float(fvg_cfg["min_pips"]), float(fvg_cfg["max_pips"]))
            eligible_fvgs = [f for f in fvgs if f.eligible and f.index > s3_prior_bos.break_candle_index]
            eligible_fvg = eligible_fvgs[-1] if eligible_fvgs else None
            anchor = resolve_anchor_s3(candidate.direction, post_bos_swings, eligible_fvg)

        friction = estimate_friction(symbol, config, pip_size, pip_value_per_lot)
        stop_result = compute_stop(
            candidate.direction, candidate.entry_price, anchor, atr_val, atr_buffer_mult, friction, min_stop_multiple,
        )

        if not stop_result.accepted:
            rejected.append({
                "setup_model": candidate.setup_model.value, "reason": stop_result.reason,
                "time": str(candle.time),
            })
            continue

        if campaign is None:
            campaign = new_campaign(symbol, session_pair_id, trading_date, candidate.direction, regime_result.regime.value, as_of)

        alloc = allocate_risk(campaign, candidate.setup_model, config)
        if not alloc.accepted:
            rejected.append({
                "setup_model": candidate.setup_model.value, "reason": alloc.reason, "time": str(candle.time),
            })
            continue

        apply_entry(campaign, candidate.setup_model, alloc.risk_pct, candle.time, candidate.entry_price, stop_result.stop_price)

        # GAP_3_OUTCOME_RESOLUTION: resolve this fill's terminal outcome now, against
        # every remaining trade-session candle (already bounded to this cycle's own
        # session_exit_time -- SESSION EXIT CUTOFF convention reused from
        # scripts/resolve_forward_shadow_outcomes.py: a cycle is never resolved using
        # bars from beyond its own trade_session end). friction is recomputed here WITH
        # this fill's own final_stop_distance so cost accounting is expressed in this
        # trade's own risk units (P19/P20).
        friction_for_costs = estimate_friction(
            symbol, config, pip_size, pip_value_per_lot, stop_distance_price=stop_result.final_stop_distance,
        )
        if m1_candles is not None:
            subsequent_candles = _m1_subsequent_candles(m1_candles, candle.time, trade_end)
        else:
            subsequent_candles = trade_candles[i + 1 :]
        entry_index = campaign.entry_count - 1  # apply_entry already appended this entry
        outcome = resolve_campaign_entry(
            campaign_id=campaign.campaign_id, setup_model=candidate.setup_model.value,
            direction=candidate.direction, entry_time=candle.time, entry_price=candidate.entry_price,
            stop_price=stop_result.stop_price, reference_high=reference.high, reference_low=reference.low,
            runner_target_r=runner_target_r_cfg, partial_pct=partial_pct_cfg, runner_pct=runner_pct_cfg,
            subsequent_candles=subsequent_candles, session_exit_time=trade_end, friction=friction_for_costs,
        )
        campaign.entries[entry_index].realized_r = outcome.net_R if outcome.net_R is not None else outcome.gross_R
        accepted.append({
            "setup_model": candidate.setup_model.value, "direction": candidate.direction,
            "entry_time": str(candle.time), "entry_price": candidate.entry_price,
            "stop_price": stop_result.stop_price, "risk_pct": alloc.risk_pct,
            "fill_precision": "M1_OHLC" if m1_candles is not None else "M15_OHLC",
            "outcome": outcome.to_dict(),
        })
        steps.append(ReplayStepRecord(candle.time, "ENTRY_ACCEPTED", {
            "setup_model": candidate.setup_model.value, "risk_pct": alloc.risk_pct,
            "terminal_state": outcome.terminal_state, "gross_R": outcome.gross_R, "net_R": outcome.net_R,
        }))

    if campaign is not None and campaign.status == CampaignStatus.ACTIVE:
        campaign.state = State.CAMPAIGN_ACTIVE  # already active; session window has now closed
        campaign.status = CampaignStatus.SESSION_EXPIRED
        campaign.state = transition(State.CAMPAIGN_ACTIVE, Event.SESSION_WINDOW_EXPIRED)
        steps.append(ReplayStepRecord(trade_end, "SESSION_WINDOW_EXPIRED", {}))

    return ReplayResult(symbol, session_pair_id, trading_date, regime_result.regime.value, campaign, accepted, rejected, steps)
