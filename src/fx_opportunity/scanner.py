"""Bounded three-pair FX Opportunity scan for one cycle -- capability zero.

For each requested symbol exactly one explicit state is returned:

    OPPORTUNITY                        research strategy decision READY
    NO_OPPORTUNITY                     WATCH / EXPIRED / NO_TRADE / BLOCKED
    NO_COMPATIBLE_OPPORTUNITY_STRATEGY no strategy binding for (cycle, symbol); a
                                       strategy-neutral MarketState is still observed
    DATA_UNAVAILABLE                   market data missing/invalid for the decision
    LIVE_MT5_AUTH_BLOCKED / MT5_REAL_PACKAGE_UNAVAILABLE / INSTRUMENT_SPEC_MISMATCH /
    CYCLE_NOT_ALLOWED / UNKNOWN_INSTRUMENT   fail-closed environment/contract states

No quotas, no ranking, no forced signal. An OPPORTUNITY is research evidence from a
RESEARCH_STRATEGY and never a recommendation: proposal is NO_PROPOSAL_AUTHORITY and
the trade ticket is NOT_CREATED for every state. Nothing here imports execution,
proposal formation, scheduling or broker-mutation code.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import session_clock as sc
from opportunity.candidate_store import CandidateStore
from opportunity.registry_binding import StrategyBinding, resolve_strategy_binding
from post_asian_pilot.decision import STATUS_DATA_ERROR, STATUS_READY
from post_asian_pilot.pilot_config import PilotConfig, load_pilot_config
from strategy_engine.loader import load_strategy
from strategy_engine.models import StrategyConfig

from .instruments import UnknownInstrumentError, get_instrument
from .market_state import MarketState, observe_market_state
from .runner import (
    CYCLES,
    PROPOSAL_NO_AUTHORITY,
    TRADE_TICKET_NOT_CREATED,
    FetchCandles,
    FxOpportunityResult,
    evaluate_fx_opportunity,
    strategy_incompatibility,
)

OPPORTUNITY = "OPPORTUNITY"
NO_OPPORTUNITY = "NO_OPPORTUNITY"
NO_COMPATIBLE_OPPORTUNITY_STRATEGY = "NO_COMPATIBLE_OPPORTUNITY_STRATEGY"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
LIVE_MT5_AUTH_BLOCKED = "LIVE_MT5_AUTH_BLOCKED"
MT5_REAL_PACKAGE_UNAVAILABLE = "MT5_REAL_PACKAGE_UNAVAILABLE"
INSTRUMENT_SPEC_MISMATCH = "INSTRUMENT_SPEC_MISMATCH"
CYCLE_NOT_ALLOWED = "CYCLE_NOT_ALLOWED"
UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"


@dataclass(frozen=True)
class CycleContext:
    cycle: str
    pilot: PilotConfig
    strategy: StrategyConfig
    binding: StrategyBinding


def load_cycle_context(cycle: str) -> CycleContext:
    if cycle not in CYCLES:
        raise ValueError(f"unknown cycle {cycle!r}; known {sorted(CYCLES)}")
    pilot = load_pilot_config(CYCLES[cycle])
    return CycleContext(cycle=cycle, pilot=pilot, strategy=load_strategy(pilot.strategy_source_path),
                        binding=resolve_strategy_binding(pilot.strategy_id))


@dataclass(frozen=True)
class SymbolScan:
    cycle: str
    symbol: str
    status: str
    reason_codes: Tuple[str, ...] = ()
    market_state: Optional[MarketState] = None
    result: Optional[FxOpportunityResult] = None

    @property
    def proposal(self) -> str:
        return self.result.proposal if self.result is not None else PROPOSAL_NO_AUTHORITY

    def summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "cycle": self.cycle,
            "symbol": self.symbol,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "proposal": self.proposal,
            "trade_ticket": TRADE_TICKET_NOT_CREATED,
            "execution_authority": "NONE",
        }
        if self.result is not None:
            out["opportunity"] = self.result.summary()
        elif self.market_state is not None:
            out["market_state"] = self.market_state.to_dict()
        return out


def blocked(cycle: str, symbols: Iterable[str], status: str, reasons: Tuple[str, ...] = ()) -> Tuple[SymbolScan, ...]:
    """Explicit fail-closed state for every symbol when the environment blocks the scan."""
    return tuple(SymbolScan(cycle=cycle, symbol=s, status=status, reason_codes=reasons) for s in symbols)


def scan_symbol(
    ctx: CycleContext,
    symbol: str,
    *,
    trading_date: dt.date,
    now: dt.datetime,
    fetch_candles: FetchCandles,
    market_data_mode: str,
    source: str,
    store: Optional[CandidateStore] = None,
    spread_price: Optional[float] = None,
    spread_source: Optional[str] = None,
    application_lineage: Optional[str] = None,
) -> SymbolScan:
    try:
        instrument = get_instrument(symbol)
    except UnknownInstrumentError:
        return SymbolScan(ctx.cycle, symbol, UNKNOWN_INSTRUMENT, ("SYMBOL_NOT_IN_INSTRUMENT_CONTRACT",))
    if ctx.cycle not in instrument.allowed_cycles:
        return SymbolScan(ctx.cycle, symbol, CYCLE_NOT_ALLOWED)

    incompatible = strategy_incompatibility(symbol, ctx.pilot, ctx.strategy)
    if incompatible:
        pilot = ctx.pilot
        ref_start, ref_end = sc.get_session_bounds(trading_date, pilot.reference_session_name)
        win = tuple(dt.datetime.combine(trading_date, dt.time.fromisoformat(t), tzinfo=dt.timezone.utc)
                    for t in (pilot.execution_window_start_utc, pilot.execution_window_end_utc))
        state, data_reasons = observe_market_state(
            instrument=instrument, cycle=ctx.cycle, trading_date=trading_date, now=now,
            reference_session=pilot.reference_session_name, reference_window=(ref_start, ref_end),
            execution_window=win, expected_reference_bars=sc.expected_bar_count(pilot.reference_session_name, "M15"),
            fetch_candles=fetch_candles, market_data_mode=market_data_mode, source=source,
            spread_price=spread_price, spread_source=spread_source,
        )
        return SymbolScan(ctx.cycle, symbol, NO_COMPATIBLE_OPPORTUNITY_STRATEGY,
                          incompatible + data_reasons, market_state=state)

    result = evaluate_fx_opportunity(
        cycle=ctx.cycle, symbol=symbol, trading_date=trading_date, now=now, pilot=ctx.pilot,
        strategy=ctx.strategy, binding=ctx.binding, fetch_candles=fetch_candles,
        market_data_mode=market_data_mode, source=source, store=store,
        spread_price=spread_price, spread_source=spread_source, application_lineage=application_lineage,
    )
    status = result.decision.status
    if status == STATUS_DATA_ERROR:
        scan_status = DATA_UNAVAILABLE
    elif status == STATUS_READY:
        scan_status = OPPORTUNITY
    else:
        scan_status = NO_OPPORTUNITY
    return SymbolScan(ctx.cycle, symbol, scan_status, tuple(result.decision.reason_codes),
                      market_state=result.market_state, result=result)


def scan_cycle(
    ctx: CycleContext,
    symbols: Iterable[str],
    *,
    spreads: Optional[Mapping[str, Tuple[float, str]]] = None,
    **kwargs: Any,
) -> Tuple[SymbolScan, ...]:
    """Scan each symbol independently, in the given order; one symbol never affects
    another. `spreads` maps symbol -> (observed spread price, source)."""
    spreads = spreads or {}
    out = []
    for symbol in symbols:
        price, src = spreads.get(symbol, (None, None))
        out.append(scan_symbol(ctx, symbol, spread_price=price, spread_source=src, **kwargs))
    return tuple(out)
