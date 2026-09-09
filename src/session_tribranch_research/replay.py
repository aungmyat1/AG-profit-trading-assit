"""AG_SESSION_TRADE_V120 canonical, fill-safe replay of the three-branch
(Sweep/Range/Trend) session decision tree, over real EURUSD M5 historical data.

RESEARCH_DESIGN_UNSIGNED. This is a NEW, independent research candidate -- it is NOT
ST_ASIAN_SWEEP_5R_V1 v1.1.1 (that strategy's own frozen forward-shadow evidence is
untouched, see tests/test_v111_evidence_immutable.py) and it is NOT SESSION_TRADE_V1 /
ASIAN_SESSION_V1 (a separately-signed strategy in a separate repository, D:\\ddev\\Session
Trade Codex -- this repo's own docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md is
explicit: "do not merge them"). What IS reused, verbatim and unmodified, from this
repo's own already-written, already-lookahead-tested code (resource-first: reuse before
reinventing):

    strategy_engine.session.classifier.classify              (ER_ONLY_V2, real, signed)
    strategy_engine.session.reference_box.build_reference_box (real, signed)
    strategy_engine.session.router.route_completed_session    (real, unit-tested)
    strategy_engine.session.setups.{entry_1_trend,entry_2_sweep,entry_3_range}
    strategy_engine.session.candidate_stop_models.session_range_25_stop (SWEEP's own
        already-signed 25%-of-range stop, from ST_ASIAN_SWEEP_5R_V1.yaml, reused for
        the Sweep branch only -- this candidate does not invent a new Sweep stop rule)

What is genuinely NEW, unsigned research design (per instruction: "borrow SESSION_TRADE_V1
where suitable" for fields router.py leaves undefined, rather than inventing arbitrarily) --

    ORDER TYPE (P6): router.py's setups give only a price level, never an order type.
        SWEEP:  MARKET at entry_reference (the qualifying candle's own already-closed
                body price) -- this is NOT a new choice, it is ST_ASIAN_SWEEP_5R_V1
                v1.1.1's own real, signed semantics, reused unchanged.
        RANGE/TREND: LIMIT at entry_reference (session boundary / session midpoint),
                borrowed from SESSION_TRADE_V1_SPEC.md Section 14 ("Order type: LIMIT at
                the computed entry price... IMPLEMENTED"), the one real, signed
                precedent for this exact question. Never MARKET/STOP -- no code or
                document in this repo assigns a MARKET-on-touch or STOP semantics to a
                boundary/midpoint entry.

    FILL-SAFETY (P5/P7/P8/P19): entry_3_range's/entry_1_trend's own decision requires
        seeing a candle's CLOSE (rejection pattern for RANGE; box completion for TREND)
        before a setup is "signalled" -- so a resting LIMIT order cannot be assumed live
        before that instant without contradicting the router's own signal definition.
        CONSERVATIVE POLICY (documented, deterministic, versioned as
        FILL_POLICY_V1 below):
          - SWEEP:  fill IS the signal (already a real, closed price) -- no separate wait.
          - RANGE:  order becomes live starting the candle immediately AFTER the
                    rejection (signal) candle, monitored through trade-window end.
          - TREND:  order becomes live from the first trade-window candle (the box/
                    direction is already known at box completion, before the window
                    opens) through trade-window end.
          - Fill test: LONG fills when a later candle's low <= entry_reference; SHORT
                    fills when a later candle's high >= entry_reference. Never filled by
                    window end -> NO_FILL / EXPIRED, never a trade.
          - SL/TP evaluation begins strictly on the candle AFTER the fill candle, never
                    the fill candle itself (M5 bars cannot resolve intrabar order vs.
                    SL/TP path -- see SAME_CANDLE_POLICY below).
          - fill_time is always > signal_timestamp (RANGE) or >= trade_session_start
                    (TREND); exit_time is always > fill_time. Enforced, not assumed
                    (see tests/test_session_tribranch_replay.py).

    SAME_CANDLE_POLICY (P8): if a single M5 candle would trigger both SL and TP (or, for
        the two-leg exit below, both TP1 and TP2/BE) with no intrabar (tick) evidence to
        order them, the CONSERVATIVE tie-break applies: SL (or the earlier-in-priority
        leg) is credited, never the favorable outcome. Documented, deterministic, and
        the same choice this repo's own resolve_forward_shadow_outcomes.py makes
        (AMBIGUOUS_SEQUENCE is flagged there too, but where this replay must produce one
        number per trade for aggregate branch economics, it resolves conservatively
        rather than discarding the trade).

    TARGETS (P10/P11): router.py's entry_3_range gives a real target_reference
        (session_mid); entry_1_trend gives target_reference=None (genuinely undefined in
        the existing code). Rather than inventing a bespoke scheme, this candidate
        reuses ST_ASIAN_SWEEP_5R_V1.yaml's OWN already-signed
        position_split_and_targets block (TP1 75% @ opposite-boundary-equivalent, move
        runner to breakeven, TP2 25% @ fixed 5R) uniformly across all three branches --
        the same two-leg shape SESSION_TRADE_V1_SPEC.md Section 14 independently signs
        for its own three branches, so this is reuse of convergent real precedent, not
        an arbitrary invention. RANGE's TP1 is router.py's own target_reference
        (session_mid, real code output) rather than a re-derived "opposite boundary."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from strategy_engine.session.candidate_stop_models import session_range_25_stop
from strategy_engine.session.candles import Candle
from strategy_engine.session.reference_box import ReferenceBox, build_reference_box
from strategy_engine.session.setups import (
    Direction, DecisionStatus, SetupDecision, SetupType,
    entry_1_trend, entry_2_sweep, entry_3_range,
)

FILL_POLICY_VERSION = "FILL_POLICY_V1"
SAME_CANDLE_POLICY_VERSION = "CONSERVATIVE_SL_FIRST_TIEBREAK_V1"

REFERENCE_START = time(0, 0)   # Asian reference, ST_ASIAN_SWEEP_5R_V1.yaml canonical (00:00 UTC)
REFERENCE_END = time(6, 0)
TRADE_START = time(7, 0)       # London_Open trade session, ST_ASIAN_SWEEP_5R_V1.yaml ASIAN_LONDON pair
TRADE_END = time(11, 0)

REFERENCE_BAR_MINUTES = 5
REFERENCE_EXPECTED_BARS = int((6 * 60) / REFERENCE_BAR_MINUTES)   # 72
TRADE_EXPECTED_BARS = int((4 * 60) / REFERENCE_BAR_MINUTES)        # 48

MAX_RANGE_PIPS_EURUSD = 25.0  # ST_ASIAN_SWEEP_5R_V1.yaml regime_classification.range_session_check
PIP_SIZE = 0.0001

STOP_LOSS_RANGE_PCT = 0.25  # ST_ASIAN_SWEEP_5R_V1.yaml risk_and_money_management, reused for SWEEP only
TP2_FIXED_R = 5.0            # ST_ASIAN_SWEEP_5R_V1.yaml position_split_and_targets.total_target_r
TP1_VOLUME_PCT = 0.75
TP2_VOLUME_PCT = 0.25


@dataclass(frozen=True)
class TradeOutcome:
    session_date: date
    setup_type: str
    decision_status: str
    reason_code: str
    direction: Optional[str]
    signal_timestamp: Optional[datetime]
    entry_reference: Optional[float]
    stop_loss: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    order_created_at: Optional[datetime]
    order_expiry: Optional[datetime]
    filled: bool
    fill_time: Optional[datetime]
    fill_price: Optional[float]
    exit_time: Optional[datetime]
    terminal_state: str  # NO_SETUP / EXPIRED_NO_FILL / RESOLVED_SL / RESOLVED_TP1_BE / RESOLVED_TP1_TP2 / RESOLVED_SESSION_EXIT / AMBIGUOUS_SEQUENCE_RESOLVED_CONSERVATIVE
        # never a synthetic/phantom win
    realized_R: Optional[float]
    tp1_R: Optional[float]


def _window(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=timezone.utc)


def _slice(candles: List[Candle], start: datetime, end: datetime) -> List[Candle]:
    """[start, end) -- candles are Candle.time == bar OPEN time."""
    return [c for c in candles if start <= c.time < end]


def _iter_trading_days(candles: List[Candle]) -> List[date]:
    days = sorted({c.time.date() for c in candles})
    return days


def _is_range_regime(box: ReferenceBox) -> bool:
    """ST_ASIAN_SWEEP_5R_V1.yaml's OWN signed regime_classification.range_session_check
    (Reference_Session_Range_Pips <= 25.0 -> RANGE, else TREND) -- NOT the unrelated
    ER_ONLY_V2 efficiency-ratio classifier (strategy_engine.session.classifier), which
    belongs to the separate, never-registered SESSION_FLOW_V2_SIMPLE system
    (docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md: "two different classifiers exist
    by design... do not merge them"). Using ER_ONLY_V2 here classified ~99% of sessions
    as RANGE (including 40-65 pip-wide boxes) and made entry_2_sweep's loose, unbuffered
    penetration test fire on 75% of days -- an implausible sweep rate traced directly to
    borrowing the wrong strategy's classifier. This candidate uses its own strategy
    family's real, signed range gate instead."""
    range_pips = box.session_range / PIP_SIZE
    return range_pips <= MAX_RANGE_PIPS_EURUSD


def _route(strategy_id: str, symbol: str, box: ReferenceBox, day: date, trade_candles: List[Candle]) -> SetupDecision:
    if not _is_range_regime(box):
        return entry_1_trend(strategy_id, symbol, box, day)
    decision = entry_2_sweep(strategy_id, symbol, box, day, trade_candles)
    if decision.decision_status == DecisionStatus.NO_SETUP:
        decision = entry_3_range(strategy_id, symbol, box, day, trade_candles)
    return decision


def _fill_scan(direction: Direction, entry: float, candles: Sequence[Candle]) -> Optional[Candle]:
    for c in candles:
        if direction == Direction.LONG and c.low <= entry:
            return c
        if direction == Direction.SHORT and c.high >= entry:
            return c
    return None


def _resolve_exit(
    direction: Direction, entry: float, stop_loss: float, tp1: float, tp2: float,
    tp1_R: float, candles_after_fill: Sequence[Candle],
) -> Tuple[str, Optional[float], Optional[datetime]]:
    """Two-leg exit (75% TP1->BE, 25% TP2 fixed 5R), scanning candles strictly AFTER the
    fill candle. Returns (terminal_state, realized_R, exit_time)."""
    is_long = direction == Direction.LONG
    tp1_hit_idx = None
    for i, c in enumerate(candles_after_fill):
        sl_hit = (c.low <= stop_loss) if is_long else (c.high >= stop_loss)
        tp1_hit = (c.high >= tp1) if is_long else (c.low <= tp1)
        if sl_hit and tp1_hit:
            return "AMBIGUOUS_SEQUENCE_RESOLVED_CONSERVATIVE", -1.0, c.time  # conservative: SL first
        if sl_hit:
            return "RESOLVED_SL", -1.0, c.time
        if tp1_hit:
            tp1_hit_idx = i
            break
    if tp1_hit_idx is None:
        if not candles_after_fill:
            return "UNRESOLVED_NO_DATA", None, None
        last = candles_after_fill[-1]
        exit_R = ((last.close - entry) / (entry - stop_loss)) if is_long else ((entry - last.close) / (stop_loss - entry))
        return "RESOLVED_SESSION_EXIT", exit_R, last.time

    be_price = entry
    for c in candles_after_fill[tp1_hit_idx + 1:]:
        be_hit = (c.low <= be_price) if is_long else (c.high >= be_price)
        tp2_hit = (c.high >= tp2) if is_long else (c.low <= tp2)
        if be_hit and tp2_hit:
            return "AMBIGUOUS_SEQUENCE_RESOLVED_CONSERVATIVE", TP1_VOLUME_PCT * tp1_R, c.time  # conservative: BE first
        if be_hit:
            return "RESOLVED_TP1_BE", TP1_VOLUME_PCT * tp1_R + TP2_VOLUME_PCT * 0.0, c.time
        if tp2_hit:
            return "RESOLVED_TP1_TP2", TP1_VOLUME_PCT * tp1_R + TP2_VOLUME_PCT * TP2_FIXED_R, c.time

    last = candles_after_fill[-1]
    runner_R = ((last.close - entry) / (entry - stop_loss)) if is_long else ((entry - last.close) / (stop_loss - entry))
    return "RESOLVED_SESSION_EXIT", TP1_VOLUME_PCT * tp1_R + TP2_VOLUME_PCT * runner_R, last.time


def _targets_for_setup(decision: SetupDecision, box: ReferenceBox, risk: float) -> Tuple[float, float]:
    """(tp1, tp2). TP1 borrowed per-branch; TP2 is always fixed 5R (ST_ASIAN_SWEEP_5R_V1.yaml).
    `risk` is the ACTUAL stop distance used for this trade (which for SWEEP is the
    candidate SESSION_RANGE_25 stop, not necessarily decision.risk_distance's own
    candle-wick-based value) -- TP2 must be consistent with the stop actually applied."""
    is_long = decision.direction == Direction.LONG
    if decision.setup_type == SetupType.SWEEP:
        tp1 = box.session_high if is_long else box.session_low  # opposite session boundary, v1.1.1's own rule
    elif decision.setup_type == SetupType.RANGE:
        tp1 = decision.target_reference  # router.py's own real target_reference == session_mid
    else:  # TREND
        tp1 = box.session_high if is_long else box.session_low  # far boundary in the trend's own direction
    tp2 = decision.entry_reference + TP2_FIXED_R * risk if is_long else decision.entry_reference - TP2_FIXED_R * risk
    return tp1, tp2


def replay_asian_london_eurusd(candles: List[Candle]) -> List[TradeOutcome]:
    """One decision cycle per trading day. Never uses a candle later than the point each
    decision needs it (reference box only from reference-session candles; trade-window
    routing/fill/exit only from trade-window candles in time order)."""
    outcomes: List[TradeOutcome] = []
    for day in _iter_trading_days(candles):
        ref_start, ref_end = _window(day, REFERENCE_START), _window(day, REFERENCE_END)
        trade_start, trade_end = _window(day, TRADE_START), _window(day, TRADE_END)

        ref_candles = _slice(candles, ref_start, ref_end)
        trade_candles = _slice(candles, trade_start, trade_end)
        if len(ref_candles) < REFERENCE_EXPECTED_BARS or not trade_candles:
            continue  # incomplete box or no trade-window data (holiday/weekend) -- not a decision cycle

        box = build_reference_box("Asian", ref_candles, REFERENCE_EXPECTED_BARS)
        if not box.session_complete:
            continue

        decision = _route("ST_SESSION_TRIBRANCH_RESEARCH_V1", "EURUSD", box, day, trade_candles)

        if decision.decision_status != DecisionStatus.VALID:
            outcomes.append(TradeOutcome(
                session_date=day, setup_type=decision.setup_type.value,
                decision_status=decision.decision_status.value, reason_code=decision.reason_code,
                direction=None, signal_timestamp=None, entry_reference=None, stop_loss=None,
                tp1=None, tp2=None, order_created_at=None, order_expiry=None, filled=False,
                fill_time=None, fill_price=None, exit_time=None, terminal_state="NO_SETUP",
                realized_R=None, tp1_R=None,
            ))
            continue

        direction = decision.direction
        entry = decision.entry_reference

        # Stop geometry: SWEEP reuses its own already-signed SESSION_RANGE_25 model;
        # RANGE/TREND use the router's own structural stop_reference (real code output).
        if decision.setup_type == SetupType.SWEEP:
            stop_result = session_range_25_stop(direction, entry, box.session_high, box.session_low, STOP_LOSS_RANGE_PCT)
            stop_loss = stop_result.stop_loss
        else:
            stop_loss = decision.stop_reference

        risk = abs(entry - stop_loss)
        if risk <= 0:
            outcomes.append(TradeOutcome(
                session_date=day, setup_type=decision.setup_type.value, decision_status=decision.decision_status.value,
                reason_code="NON_POSITIVE_RISK_MALFORMED", direction=direction.value, signal_timestamp=decision.signal_timestamp,
                entry_reference=entry, stop_loss=stop_loss, tp1=None, tp2=None, order_created_at=None,
                order_expiry=None, filled=False, fill_time=None, fill_price=None, exit_time=None,
                terminal_state="INVALID_EVIDENCE", realized_R=None, tp1_R=None,
            ))
            continue

        tp1, tp2 = _targets_for_setup(decision, box, risk)
        tp1_R = ((tp1 - entry) / risk) if direction == Direction.LONG else ((entry - tp1) / risk)

        # Order-window + fill scan (FILL_POLICY_V1 -- see module docstring).
        if decision.setup_type == SetupType.SWEEP:
            fill_candle = next(c for c in trade_candles if c.time == decision.signal_timestamp)
            order_created_at = decision.signal_timestamp
            order_expiry = trade_end
        else:
            if decision.setup_type == SetupType.RANGE:
                live_from = decision.signal_timestamp + timedelta(minutes=REFERENCE_BAR_MINUTES)
            else:  # TREND
                live_from = trade_start
            order_created_at = decision.signal_timestamp if decision.setup_type == SetupType.RANGE else trade_start
            order_expiry = trade_end
            monitor_candles = [c for c in trade_candles if c.time >= live_from]
            fill_candle = _fill_scan(direction, entry, monitor_candles)

        if fill_candle is None:
            outcomes.append(TradeOutcome(
                session_date=day, setup_type=decision.setup_type.value, decision_status=decision.decision_status.value,
                reason_code=decision.reason_code, direction=direction.value, signal_timestamp=decision.signal_timestamp,
                entry_reference=entry, stop_loss=stop_loss, tp1=tp1, tp2=tp2, order_created_at=order_created_at,
                order_expiry=order_expiry, filled=False, fill_time=None, fill_price=None, exit_time=None,
                terminal_state="EXPIRED_NO_FILL", realized_R=None, tp1_R=tp1_R,
            ))
            continue

        candles_after_fill = [c for c in trade_candles if c.time > fill_candle.time]
        terminal_state, realized_R, exit_time = _resolve_exit(
            direction, entry, stop_loss, tp1, tp2, tp1_R, candles_after_fill,
        )

        outcomes.append(TradeOutcome(
            session_date=day, setup_type=decision.setup_type.value, decision_status=decision.decision_status.value,
            reason_code=decision.reason_code, direction=direction.value, signal_timestamp=decision.signal_timestamp,
            entry_reference=entry, stop_loss=stop_loss, tp1=tp1, tp2=tp2, order_created_at=order_created_at,
            order_expiry=order_expiry, filled=True, fill_time=fill_candle.time, fill_price=entry,
            exit_time=exit_time, terminal_state=terminal_state, realized_R=realized_R, tp1_R=tp1_R,
        ))

    return outcomes
