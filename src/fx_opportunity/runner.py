"""EURUSD FX Opportunity runner -- composition only, no new strategy semantics.

Reproduces the data -> strategy -> decision path of the historical
`post_asian_pilot.pipeline._evaluate_pair` (restoration source 2b75bbf) using only
its pure, byte-exact-restored pieces, and deliberately WITHOUT that module's
execution-coupled parts (proposal.py/store.py/governor.py import `execution.*`;
pipeline.py imports `execution_runtime.data_provider`). Those are not restored.

    fetch_candles (caller-injected; CLI passes mt5.market_data.get_candles)
      -> post_asian_pilot.snapshot.build_asian_session_snapshot   (completeness)
      -> strategy_engine.engine.evaluate                           (frozen strategy)
      -> post_asian_pilot.decision.*                               (canonical decision)
      -> opportunity.asian_sweep_adapter + opportunity.engine      (funnel)
      -> opportunity.candidate_store                               (optional persistence)
      -> opportunity.proposal_eligibility                          (existing, unchanged)
      -> STOP

PROPOSAL AUTHORITY: this module never forms a CanonicalProposal or TradeTicket.
`StrategyBinding.proposal_authority` (opportunity.registry_binding) is the gate:
when False the result is PROPOSAL_NO_AUTHORITY; when True it is still
PROPOSAL_FORMATION_NOT_WIRED, because formation is out of scope for this slice.
The existing eligibility decision is reported as evidence only.

LOOK-AHEAD: only candles whose close time is <= `now` (and inside the requested
window) are passed on; anything else is dropped and counted in provenance.

No MT5 order/position API, no execution import, no network, no Telegram.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import session_clock as sc
from mt5.market_data import MarketDataError
from opportunity.asian_sweep_adapter import STRATEGY_ID, STRATEGY_VERSION, AsianSweepFunnelAdapter
from opportunity.candidate_store import CandidateStore
from opportunity.contracts import MarketEvent, OpportunityCandidate, ProposalEligibilityDecision
from opportunity.engine import evaluate_funnel
from opportunity.proposal_eligibility import evaluate_proposal_eligibility
from opportunity.registry_binding import StrategyBinding
from opportunity.transitions import FunnelTransition
from post_asian_pilot.decision import (
    STATUS_READY,
    PostAsianDecision,
    data_error_decision,
    map_trade_signal_to_decision,
    watch_decision,
)
from post_asian_pilot.fingerprint import fingerprint
from post_asian_pilot.pilot_config import PilotConfig
from post_asian_pilot.snapshot import build_asian_session_snapshot
from strategy_engine.engine import evaluate as evaluate_strategy
from strategy_engine.models import StrategyConfig
from strategy_engine.session import Candle

# The two canonical daily cycles, bound to the existing pilot configs (which own
# pair_id, reference session name and execution window -- not redefined here).
CYCLES: Dict[str, str] = {
    "POST_ASIAN": "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml",
    "POST_LONDON": "config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml",
}

# Milestone scope: EURUSD only. Widening this is a separate, explicit change.
SLICE_SYMBOLS: Tuple[str, ...] = ("EURUSD",)

OPPORTUNITY = "OPPORTUNITY"
NO_OPPORTUNITY = "NO_OPPORTUNITY"
PROPOSAL_NO_AUTHORITY = "NO_PROPOSAL_AUTHORITY"
PROPOSAL_FORMATION_NOT_WIRED = "PROPOSAL_FORMATION_NOT_WIRED"
TRADE_TICKET_NOT_CREATED = "NOT_CREATED"

_M15 = dt.timedelta(minutes=15)

FetchCandles = Callable[[str, str, dt.datetime, dt.datetime], List[Candle]]


class FxOpportunityScopeError(ValueError):
    """Symbol/strategy/config outside this slice's scope -- fail closed."""


@dataclass(frozen=True)
class FxOpportunityResult:
    cycle: str
    symbol: str
    pair_id: str
    trading_date: dt.date
    evaluated_at: dt.datetime
    decision: PostAsianDecision
    opportunity: str  # OPPORTUNITY | NO_OPPORTUNITY
    candidate: OpportunityCandidate
    transition: Optional[FunnelTransition]
    eligibility: ProposalEligibilityDecision
    proposal: str  # PROPOSAL_NO_AUTHORITY | PROPOSAL_FORMATION_NOT_WIRED
    trade_ticket: str  # always TRADE_TICKET_NOT_CREATED
    provenance: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        c = self.candidate
        g = c.geometry
        return {
            "cycle": self.cycle,
            "symbol": self.symbol,
            "pair_id": self.pair_id,
            "trading_date": self.trading_date.isoformat(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "decision_status": self.decision.status,
            "decision_reason_codes": list(self.decision.reason_codes),
            "missing_condition": self.decision.missing_condition,
            "opportunity": self.opportunity,
            "candidate_id": c.candidate_id,
            "candidate_stage": c.stage,
            "candidate_outcome": c.outcome,
            "candidate_revision": c.revision,
            "direction": g.direction if g else None,
            "entry": g.entry if g else None,
            "invalidation": g.invalidation if g else None,
            "strategy_id": c.strategy_id,
            "strategy_version": c.strategy_version,
            "eligibility_status": self.eligibility.status,
            "eligibility_reasons": list(self.eligibility.reason_codes),
            "proposal": self.proposal,
            "trade_ticket": self.trade_ticket,
            "execution_authority": "NONE",
            "provenance": self.provenance,
        }


def _closed_only(
    candles: Sequence[Candle], start: dt.datetime, end: dt.datetime, now: dt.datetime,
) -> Tuple[List[Candle], int]:
    """Keep bars with open in [start, end) whose close is <= min(now, end)."""
    horizon = min(now, end)
    kept = [c for c in candles if start <= c.time < end and c.time + _M15 <= horizon]
    return kept, len(candles) - len(kept)


def _ordered_unique(candles: Sequence[Candle]) -> bool:
    times = [c.time for c in candles]
    return times == sorted(times) and len(set(times)) == len(times)


def _candles_fingerprint(candles: Sequence[Candle]) -> Optional[str]:
    if not candles:
        return None
    return fingerprint([[c.time.isoformat(), c.open, c.high, c.low, c.close] for c in candles])


def _event_id(symbol: str, pair_id: str, trading_date: dt.date) -> str:
    # Established occurrence-identity pattern (asian_sweep_adapter module docstring,
    # "INTENDED EVENT-IDENTITY PATTERN"): stable per (symbol, pair, trading_date).
    return f"ASIAN_SWEEP:{symbol}:{pair_id}:{trading_date.isoformat()}"


def _lineage(parts: Dict[str, Any]) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_scope(symbol: str, pilot: PilotConfig, strategy: StrategyConfig, binding: StrategyBinding) -> None:
    if symbol not in SLICE_SYMBOLS:
        raise FxOpportunityScopeError(f"{symbol!r} is outside this slice's symbols {SLICE_SYMBOLS}")
    if symbol not in pilot.universe:
        raise FxOpportunityScopeError(f"{symbol!r} is not in pilot {pilot.pilot_id} universe {pilot.universe}")
    for label, got in (
        ("pilot.strategy_id", pilot.strategy_id),
        ("strategy.strategy_id", strategy.strategy_id),
        ("binding.strategy_id", binding.strategy_id),
    ):
        if got != STRATEGY_ID:
            raise FxOpportunityScopeError(f"{label}={got!r} != {STRATEGY_ID!r}")
    for label, got in (("pilot.strategy_version", pilot.strategy_version), ("strategy.version", strategy.version)):
        if got != STRATEGY_VERSION:
            raise FxOpportunityScopeError(f"{label}={got!r} != {STRATEGY_VERSION!r}")


def evaluate_fx_opportunity(
    *,
    cycle: str,
    symbol: str,
    trading_date: dt.date,
    now: dt.datetime,
    pilot: PilotConfig,
    strategy: StrategyConfig,
    binding: StrategyBinding,
    fetch_candles: FetchCandles,
    market_data_mode: str,
    source: str,
    store: Optional[CandidateStore] = None,
) -> FxOpportunityResult:
    if now.tzinfo is None:
        raise FxOpportunityScopeError("now must be timezone-aware UTC")
    _check_scope(symbol, pilot, strategy, binding)

    sid, sver, ref_name = strategy.strategy_id, strategy.version, pilot.reference_session_name
    ref_start, ref_end = sc.get_session_bounds(trading_date, ref_name)
    expected_bars = sc.expected_bar_count(ref_name, "M15")
    window_start = dt.datetime.combine(trading_date, dt.time.fromisoformat(pilot.execution_window_start_utc),
                                       tzinfo=dt.timezone.utc)
    window_end = dt.datetime.combine(trading_date, dt.time.fromisoformat(pilot.execution_window_end_utc),
                                     tzinfo=dt.timezone.utc)

    provenance: Dict[str, Any] = {
        "source": source,
        "market_data_mode": market_data_mode,
        "timeframe": "M15",
        "reference_session": ref_name,
        "reference_window_utc": [ref_start.isoformat(), ref_end.isoformat()],
        "execution_window_utc": [window_start.isoformat(), window_end.isoformat()],
        "pilot_id": pilot.pilot_id,
        "strategy_source_path": pilot.strategy_source_path,
    }
    ref_candles: List[Candle] = []
    post_candles: List[Candle] = []

    def _finish(decision: PostAsianDecision) -> FxOpportunityResult:
        used = post_candles or ref_candles
        bar_open = used[-1].time if used else now
        bar_close = used[-1].time + _M15 if used else now
        provenance["reference_bar_count"] = len(ref_candles)
        provenance["reference_fingerprint"] = _candles_fingerprint(ref_candles)
        provenance["post_session_bar_count"] = len(post_candles)
        provenance["post_session_fingerprint"] = _candles_fingerprint(post_candles)
        provenance["last_closed_bar_close_utc"] = bar_close.isoformat() if used else None
        lineage = _lineage({k: provenance.get(k) for k in (
            "source", "market_data_mode", "reference_fingerprint", "post_session_fingerprint")})
        provenance["lineage_fingerprint"] = lineage

        event = MarketEvent(
            event_id=_event_id(symbol, pilot.pair_id, trading_date),
            event_type="SESSION_CYCLE_EVALUATED",
            symbol=symbol, market="FX", venue=None, timeframe="M15",
            bar_open_time=bar_open, bar_close_time=bar_close, market_data_asof=now,
            market_data_mode=market_data_mode, snapshot_fingerprint=lineage, source=source,
        )
        adapter = AsianSweepFunnelAdapter(decision=decision)
        # First pass is pure and only yields the deterministic candidate_id; the
        # second pass (if a persisted candidate exists) continues its history.
        candidate, transition = evaluate_funnel(event=event, binding=binding, adapter=adapter)
        previous = store.get(candidate.candidate_id) if store is not None else None
        if previous is not None:
            candidate, transition = evaluate_funnel(
                event=event, binding=binding, adapter=adapter, previous_candidate=previous)
        if store is not None and transition is not None:
            candidate = store.persist(candidate, transition)

        eligibility = evaluate_proposal_eligibility(candidate, binding, evaluated_at=now)
        proposal = PROPOSAL_FORMATION_NOT_WIRED if binding.proposal_authority else PROPOSAL_NO_AUTHORITY
        return FxOpportunityResult(
            cycle=cycle, symbol=symbol, pair_id=pilot.pair_id, trading_date=trading_date,
            evaluated_at=now, decision=decision,
            opportunity=OPPORTUNITY if decision.status == STATUS_READY else NO_OPPORTUNITY,
            candidate=candidate, transition=transition, eligibility=eligibility,
            proposal=proposal, trade_ticket=TRADE_TICKET_NOT_CREATED, provenance=provenance,
        )

    def _data_error(reasons: Tuple[str, ...]) -> FxOpportunityResult:
        return _finish(data_error_decision(sid, sver, symbol, trading_date, ref_name, now, reasons))

    if now < ref_end:
        return _finish(watch_decision(sid, sver, symbol, trading_date, ref_name, now,
                                      "WAITING_REFERENCE_SESSION_COMPLETION", valid_until=ref_end))

    try:
        raw_ref = fetch_candles(symbol, "M15", ref_start, ref_end)
    except MarketDataError as exc:
        return _data_error((exc.reason_code,))
    ref_candles, dropped_ref = _closed_only(raw_ref, ref_start, ref_end, now)
    provenance["reference_bars_dropped"] = dropped_ref

    snap = build_asian_session_snapshot(sid, symbol, trading_date, ref_name, ref_start, ref_end,
                                        ref_candles, expected_bars, as_of=now, created_at_utc=ref_end)
    if snap.status != "VALID":
        return _data_error(tuple(snap.reason_codes) or ("DATA_ERROR",))
    provenance["session_snapshot_id"] = snap.snapshot.snapshot_id
    provenance["reference_box"] = {"high": snap.snapshot.high, "low": snap.snapshot.low,
                                   "mid": snap.snapshot.midpoint, "range": snap.snapshot.range}

    if now < window_start:
        return _finish(watch_decision(sid, sver, symbol, trading_date, ref_name, now,
                                      "WAITING_EXECUTION_WINDOW_OPEN", valid_until=window_start))

    try:
        raw_post = fetch_candles(symbol, "M15", window_start, min(now, window_end))
    except MarketDataError as exc:
        # Empty is only legitimate before the first window bar could have closed.
        if exc.reason_code != "DATA_MISSING" or now >= window_start + _M15:
            return _data_error((exc.reason_code,))
        raw_post = []
    post_candles, dropped_post = _closed_only(raw_post, window_start, window_end, now)
    provenance["post_session_bars_dropped"] = dropped_post
    if not _ordered_unique(post_candles):
        post_candles = []
        return _data_error(("POST_SESSION_DUPLICATE_OR_UNORDERED_BARS",))
    if not post_candles:
        return _finish(watch_decision(sid, sver, symbol, trading_date, ref_name, now,
                                      "WAITING_CLOSED_M15_CONFIRMATION", valid_until=window_end))

    signal = evaluate_strategy(strategy, pilot.pair_id, symbol, trading_date, list(ref_candles), expected_bars,
                               post_session_candles=list(post_candles))
    return _finish(map_trade_signal_to_decision(signal, snap.snapshot.snapshot_id, now, window_end))
