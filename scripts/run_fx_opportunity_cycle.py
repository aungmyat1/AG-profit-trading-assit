"""One-shot, capability-zero FX opportunity/proposal cycle runner.

AG_FX_OPPORTUNITY_PROPOSAL_SLICE_V1 (2026-09-28). Runs ONE bounded cycle for
one session pair and a list of symbols:

    read-only MT5 market data (mt5.market_data -- copy_rates_* ONLY)
      -> strategy evaluation          (strategy_engine.evaluate -- ST_ASIAN_SWEEP_5R_V1)
      -> PostAsianDecision            (post_asian_pilot.decision -- pure mapping)
      -> MarketEvent                  (opportunity.events -- deterministic BAR_CLOSE)
      -> OpportunityCandidate         (opportunity.engine.evaluate_funnel + asian_sweep_adapter)
      -> ProposalEligibility          (opportunity.proposal_eligibility -- HARDENED, audited)
      -> CanonicalProposal + ledger   (proposal_envelope -- audited, dedup, atomic)
      -> owner-readable ticket        (proposal_envelope.owner_report -- DATA ONLY)
    EXIT.

This script may invoke ONLY market-data read, analysis, opportunity,
proposal, and reporting. It has no execution path: no broker mutation, no
order submission, no Demo/Live execution, no authorization, no scheduler.
The historical pilot pipeline/governor/preflight and ag_scheduler_v2 are
deliberately NOT used (execution-coupled); daily automation, if ever wanted,
is an external cron/Task Scheduler entry invoking this script once per
cycle -- nothing more.

`previous_candidate` lookup imports opportunity.engine._candidate_id (the
deterministic candidate-id constructor) so a re-run of the SAME cycle dedups
through the funnel's semantic-equivalence path instead of creating revision 2
pollution -- see evaluate_funnel's own docstring (Safety Invariants #8/#9).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from mt5 import connection as mt5_connection  # noqa: E402
from mt5 import market_data as mt5_market_data  # noqa: E402
from mt5.market_data import MarketDataError  # noqa: E402
from mt5.connection import MT5ConnectionError  # noqa: E402
from opportunity import events as opportunity_events  # noqa: E402
from opportunity.asian_sweep_adapter import AsianSweepFunnelAdapter  # noqa: E402
from opportunity.candidate_store import CandidateStore  # noqa: E402
from opportunity.engine import _candidate_id, evaluate_funnel  # noqa: E402
from opportunity.proposal_eligibility import evaluate_proposal_eligibility  # noqa: E402
from opportunity.registry_binding import resolve_strategy_binding  # noqa: E402
from post_asian_pilot.decision import (  # noqa: E402
    data_error_decision,
    map_trade_signal_to_decision,
)
from proposal_envelope.adapters.opportunity_adapter import to_canonical_proposal  # noqa: E402
from proposal_envelope.ledger import ProposalLedger  # noqa: E402
from proposal_envelope.owner_report import (  # noqa: E402
    render_no_proposal_notice,
    render_owner_ticket,
)
from strategy_engine import evaluate as evaluate_strategy  # noqa: E402
from strategy_engine.loader import load_strategy  # noqa: E402
from strategy_engine.models import StrategyConfig  # noqa: E402
from strategy_engine.session.candles import Candle  # noqa: E402

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
MARKET = "FX"
VENUE = "MT5"
TIMEFRAME = "M15"
BAR_MINUTES = 15
DEFAULT_STRATEGY_CONFIG = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"

_EXIT_OK_STATUSES = {"PROPOSAL_RECORDED", "NO_PROPOSAL"}


@dataclass(frozen=True)
class _ClosedBarView:
    """Duck-typed closed-bar snapshot for opportunity.events.from_market_snapshot.

    Carries REAL market-data mode: this view is only ever constructed from
    bars returned by mt5.market_data (the connected MT5 terminal). The mode
    is never inferred from anything else and never mutated.
    """

    candle: Candle
    symbol: str
    timeframe: str = TIMEFRAME
    source: str = VENUE

    @property
    def is_closed(self) -> bool:
        return True  # mt5.market_data only ever returns closed bars (position 1+ / completed ranges)

    @property
    def bar_open_time(self) -> datetime:
        return self.candle.time

    @property
    def bar_close_time(self) -> datetime:
        return self.candle.time + timedelta(minutes=BAR_MINUTES)

    @property
    def market_data_asof(self) -> datetime:
        return self.bar_close_time

    @property
    def market_data_mode(self) -> str:
        return "REAL"

    @property
    def fingerprint(self) -> str:
        payload = "|".join(
            [
                self.symbol,
                self.timeframe,
                self.source,
                self.candle.time.astimezone(timezone.utc).isoformat(),
                repr(self.candle.open),
                repr(self.candle.high),
                repr(self.candle.low),
                repr(self.candle.close),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_window(day: date, hhmm: str) -> datetime:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return datetime.combine(day, dtime(hours, minutes), tzinfo=timezone.utc)


def _parse_as_of(raw: str) -> datetime:
    as_of = datetime.fromisoformat(raw)
    if as_of.tzinfo is None:
        raise SystemExit("--as-of must be timezone-aware ISO-8601 (e.g. 2026-09-23T11:00:00+00:00)")
    return as_of.astimezone(timezone.utc)


def _result(status: str, symbol: str, **extra: Any) -> Dict[str, Any]:
    return dict(symbol=symbol, status=status, **extra)


def run_cycle_for_symbol(
    *,
    strategy: StrategyConfig,
    pair_id: str,
    symbol: str,
    as_of: datetime,
    trading_date: date,
    candidate_store: CandidateStore,
    proposal_ledger: ProposalLedger,
    report_dir: Path,
) -> Dict[str, Any]:
    """Run one symbol's cycle. Returns the result record; raises nothing.

    Every non-PROPOSAL outcome is an explicit, deterministic status with
    reason codes -- a silent failure is not representable.
    """
    pair = next((p for p in strategy.session_pairs if p.pair_id == pair_id), None)
    if pair is None:
        known = [p.pair_id for p in strategy.session_pairs]
        return _result("DATA_ERROR", symbol, reason_codes=("UNKNOWN_PAIR",), detail=f"known pairs: {known}")

    ref_start = _utc_window(trading_date, pair.reference_session.start_time_gmt)
    ref_end = _utc_window(trading_date, pair.reference_session.end_time_gmt)
    trade_start = _utc_window(trading_date, pair.trade_session.start_time_gmt)
    trade_end = _utc_window(trading_date, pair.trade_session.end_time_gmt)
    window_minutes = (ref_end - ref_start).total_seconds() / 60.0
    expected_bars = int(window_minutes // BAR_MINUTES)

    if as_of < ref_end:
        return _result(
            "WATCH", symbol,
            reason_codes=("SESSION_NOT_CLOSED",),
            detail=f"reference session closes {ref_end.isoformat()}; as_of {as_of.isoformat()}",
        )

    post_end = min(as_of, trade_end)
    try:
        session_candles = mt5_market_data.get_candles(symbol, TIMEFRAME, ref_start, ref_end)
        post_candles: List[Candle] = []
        if post_end > trade_start:
            post_candles = mt5_market_data.get_candles(symbol, TIMEFRAME, trade_start, post_end)
    except MarketDataError as exc:
        decision = data_error_decision(
            strategy.strategy_id, strategy.version, symbol, trading_date,
            pair.reference_session.name, as_of, (str(exc),),
        )
        return _funnel_and_eligibility(
            decision=decision, symbol=symbol, as_of=as_of,
            candidate_store=candidate_store, proposal_ledger=proposal_ledger,
            report_dir=report_dir, strategy=strategy,
        )

    if len(session_candles) < expected_bars:
        decision = data_error_decision(
            strategy.strategy_id, strategy.version, symbol, trading_date,
            pair.reference_session.name, as_of,
            ("INSUFFICIENT_REFERENCE_CANDLES", f"expected={expected_bars} got={len(session_candles)}"),
        )
        return _funnel_and_eligibility(
            decision=decision, symbol=symbol, as_of=as_of,
            candidate_store=candidate_store, proposal_ledger=proposal_ledger,
            report_dir=report_dir, strategy=strategy,
        )

    signal = evaluate_strategy(
        strategy, pair.pair_id, symbol, trading_date, session_candles,
        expected_bars, post_session_candles=post_candles,
    )
    session_snapshot_id = (
        f"SESSION-BOX:{signal.strategy_id}:{signal.pair_id}:{symbol}:"
        f"{trading_date.isoformat()}"
    )
    decision = map_trade_signal_to_decision(
        signal, session_snapshot_id, evaluation_time=as_of, window_end_utc=trade_end,
    )
    return _funnel_and_eligibility(
        decision=decision, symbol=symbol, as_of=as_of,
        candidate_store=candidate_store, proposal_ledger=proposal_ledger,
        report_dir=report_dir, strategy=strategy,
        last_candle=(post_candles[-1] if post_candles else session_candles[-1]),
    )


def _funnel_and_eligibility(
    *,
    decision: Any,
    symbol: str,
    as_of: datetime,
    candidate_store: CandidateStore,
    proposal_ledger: ProposalLedger,
    report_dir: Path,
    strategy: StrategyConfig,
    last_candle: Optional[Candle] = None,
) -> Dict[str, Any]:
    """Project the decision through the funnel, then the eligibility authority."""
    if last_candle is None:
        # DATA_ERROR path: no bar available to key the event on -- the failure
        # is reported explicitly without inventing market data.
        return _result(
            "DATA_ERROR", symbol,
            reason_codes=tuple(decision.reason_codes),
            detail="market data unavailable; no candidate formed",
        )

    event = opportunity_events.from_market_snapshot(
        _ClosedBarView(candle=last_candle, symbol=symbol), market=MARKET, venue=VENUE,
    )
    binding = resolve_strategy_binding(strategy.strategy_id)
    adapter = AsianSweepFunnelAdapter(decision=decision)
    previous = candidate_store.get(_candidate_id(binding, event))
    candidate, transition = evaluate_funnel(
        event=event, binding=binding, adapter=adapter, previous_candidate=previous,
    )
    if transition is not None:
        candidate_store.persist(candidate, transition)

    eligibility = evaluate_proposal_eligibility(candidate, binding, evaluated_at=as_of)
    base = dict(
        candidate_id=candidate.candidate_id,
        stage=candidate.stage,
        outcome=candidate.outcome,
        eligibility_status=eligibility.status,
        reason_codes=tuple(eligibility.reason_codes),
    )

    if eligibility.status == "ELIGIBLE":
        proposal = to_canonical_proposal(candidate, eligibility)
        proposal_ledger.record_proposal(proposal)
        ticket = render_owner_ticket(proposal)
        (report_dir / f"{proposal.proposal_envelope_id.replace(':', '_')}.txt").write_text(
            ticket, encoding="utf-8"
        )
        return _result(
            "PROPOSAL_RECORDED", symbol,
            envelope_id=proposal.proposal_envelope_id,
            execution_authority=proposal.execution_authority,
            proposal_only=proposal.proposal_only,
            **base,
        )

    notice = render_no_proposal_notice(candidate, eligibility)
    (report_dir / f"NO_PROPOSAL_{candidate.candidate_id.replace(':', '_')}.txt").write_text(
        notice, encoding="utf-8"
    )
    return _result("NO_PROPOSAL", symbol, **base)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_fx_opportunity_cycle.py",
        description="One-shot capability-zero FX opportunity/proposal cycle (no execution path).",
    )
    parser.add_argument("--pair", required=True, choices=["ASIAN_LONDON", "LONDON_NEWYORK"])
    parser.add_argument("--symbols", default="EURUSD,GBPUSD", help="comma-separated canonical symbols")
    parser.add_argument("--as-of", required=True, help="timezone-aware ISO-8601 evaluation instant")
    parser.add_argument("--strategy-config", default=DEFAULT_STRATEGY_CONFIG)
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--report-dir", default="reports/fx_cycles")
    args = parser.parse_args(argv)

    as_of = _parse_as_of(args.as_of)
    trading_date = as_of.date()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("--symbols produced no symbols")

    strategy = load_strategy(args.strategy_config)
    state_dir = Path(args.state_dir)
    report_dir = Path(args.report_dir) / f"{args.pair}_{trading_date.isoformat()}"
    state_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    candidate_store = CandidateStore(str(state_dir / "fx_candidate_store.json"))
    proposal_ledger = ProposalLedger(str(state_dir / "proposal_ledger.json"))

    cycles: List[Dict[str, Any]] = []
    connected = False
    try:
        mt5_connection.connect()
        connected = True
        for symbol in symbols:
            cycles.append(
                run_cycle_for_symbol(
                    strategy=strategy, pair_id=args.pair, symbol=symbol, as_of=as_of,
                    trading_date=trading_date, candidate_store=candidate_store,
                    proposal_ledger=proposal_ledger, report_dir=report_dir,
                )
            )
    except MT5ConnectionError as exc:
        for symbol in symbols:
            cycles.append(_result("DATA_ERROR", symbol, reason_codes=("MT5_CONNECT_FAILED",), detail=str(exc)))
    finally:
        if connected:
            mt5_connection.shutdown()

    summary = dict(
        as_of=as_of.isoformat(),
        pair=args.pair,
        trading_date=trading_date.isoformat(),
        strategy_id=strategy.strategy_id,
        market=MARKET,
        venue=VENUE,
        execution_capability="NONE",
        cycles=cycles,
    )
    (report_dir / "cycle_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0 if all(c["status"] in _EXIT_OK_STATUSES for c in cycles) else 2


if __name__ == "__main__":
    raise SystemExit(main())
