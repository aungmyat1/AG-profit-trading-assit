"""One BTC research evaluation cycle: fetch candles from a CryptoCandleFeed (production:
execution_runtime.binance_usdtm_feed.BinanceUSDTMFeed; tests: a fixture feed), evaluate
ST_LIQUIDITY_SWEEP_RETEST_V1's CRYPTO_PERP profile via the EXISTING, untouched
SweepRetestRuntime/evaluate_setup (strategy_engine/sweep_retest/engine.py), and on
ENTRY_READY build + dedup-record a BTCSweepResearchProposal.

Deliberately does NOT reuse execution_runtime/cycle.py::evaluate_and_route: that module's
evaluate_and_route ultimately calls ctx.coordinator.submit(...), and
execution.coordinator imports execution.executor (a real, if demo/confirmation-gated,
order-submission path) -- importing that chain here would violate this task's hard
constraint that the BTC research runner must never import execution.executor /
mt5.management_gateway / any order_send path. This module therefore re-implements just the
orchestration (fetch -> evaluate -> record), calling SweepRetestRuntime directly, with NO
import of execution.coordinator/execution.executor/execution.adapter/mt5.management_gateway
anywhere in this package (see tests/test_btc_proposal_execution_boundary.py).

Every capability this module calls already exists elsewhere and is reused unchanged:
strategy_engine.sweep_retest.{engine,profile,crypto_symbols,occurrence_identity},
execution.daily_loss_guard / execution.position_guard (the SAME shared, COMBINED-across-
Forex-and-Crypto guards ST_LIQUIDITY_SWEEP_RETEST_V1's Forex path already uses).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from execution_runtime.binance_usdtm_feed import CANONICAL_SYMBOL, EXCHANGE_ID
from execution_runtime.crypto_feed import CryptoCandleFeed
from strategy_engine.sweep_retest.config import SweepRetestStrategyConfig, load_sweep_retest_strategy
from strategy_engine.sweep_retest.crypto_symbols import crypto_sl_buffer_price, crypto_symbol_meta
from strategy_engine.sweep_retest.engine import SweepRetestRuntime
from strategy_engine.sweep_retest.models import STATE_ENTRY_READY, SetupState
from strategy_engine.sweep_retest.occurrence_identity import btc_occurrence_id
from strategy_engine.sweep_retest.profile import filter_previous_day_candles, previous_utc_day_window
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore

from . import costs
from .ledger import BTCResearchLedger
from .proposal import AUTHORITY_RESEARCH_ONLY, BTCSweepResearchProposal

STRATEGY_YAML_PATH = "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"

# No crypto-exchange account/equity source exists anywhere in this repo (mt5.account is
# Forex/CFD-shaped; execution.adapter.CryptoExecutionAdapter is explicitly NOT_IMPLEMENTED,
# spec: "no exchange integration"). This is a documented RESEARCH-ONLY placeholder used
# solely to produce an evidentiary volume/risk_amount figure on the proposal -- never a
# live balance, never load-bearing for any real order (none can ever be sent from this
# package -- see module docstring).
DEFAULT_RESEARCH_EQUITY_USDT = 10000.0

# >24h of M5 bars -- covers "end of reference window (today's UTC midnight) up to now" per
# engine.evaluate_setup's own docstring ("m5_candles: ALL closed M5 candles from the end
# of the reference window ... up to now").
M5_LOOKBACK_COUNT = 300
# ~8 days of H1 -- enough history for market_structure.structural_breaks_for_candles to
# locate real swings for the H1 trend filter, while the same series also covers the
# previous UTC day used for the PREVIOUS_DAY reference box (spec section 2 / this
# package's task brief: "use ... with H1 candles fetched from the adapter").
H1_LOOKBACK_COUNT = 200


@dataclass(frozen=True)
class ResearchCycleResult:
    setup_state: SetupState
    proposal: Optional[BTCSweepResearchProposal]
    ledger_new_row: bool
    trading_day: date


def _expiry_for(profile_config, trading_day: date) -> datetime:
    """Natural validity boundary for a research proposal: the strategy's own Strategy
    Activity execution window close on the trading day it was produced (same convention
    as the FX pilot's PROPOSAL_EXPIRY_MINUTES -- "a stale sweep signal is not re-
    validated", see post_asian_pilot/proposal.py), rather than an invented duration."""
    window_end_time = profile_config.profile.execution_windows[-1][1]
    return datetime.combine(trading_day, window_end_time, tzinfo=timezone.utc)


def run_research_cycle(
    feed: CryptoCandleFeed,
    *,
    strategy_config: Optional[SweepRetestStrategyConfig] = None,
    runtime: Optional[SweepRetestRuntime] = None,
    ledger: Optional[BTCResearchLedger] = None,
    daily_loss_guard: Optional[DailyLossGuard] = None,
    open_position_guard: Optional[OpenPositionGuard] = None,
    equity: float = DEFAULT_RESEARCH_EQUITY_USDT,
    now: Optional[datetime] = None,
    market_structure_config=None,
) -> ResearchCycleResult:
    now = now or datetime.now(timezone.utc)
    strategy_config = strategy_config or load_sweep_retest_strategy(STRATEGY_YAML_PATH)
    profile_config = strategy_config.profile_config_for_symbol(CANONICAL_SYMBOL)
    if profile_config is None:
        raise ValueError(f"{STRATEGY_YAML_PATH} has no CRYPTO_PERP profile entry for {CANONICAL_SYMBOL!r}")

    runtime = runtime or SweepRetestRuntime(SweepRetestStateStore())
    ledger = ledger or BTCResearchLedger()
    daily_loss_guard = daily_loss_guard or DailyLossGuard.default(strategy_config.strategy_id)
    open_position_guard = open_position_guard or OpenPositionGuard.default()

    h1_candles = list(feed.get_latest_candles(CANONICAL_SYMBOL, "H1", H1_LOOKBACK_COUNT))
    m5_candles_raw = list(feed.get_latest_candles(CANONICAL_SYMBOL, "M5", M5_LOOKBACK_COUNT))

    today_start = previous_utc_day_window(now)[1]
    m5_candles = [c for c in m5_candles_raw if c.time >= today_start]
    reference_candles = filter_previous_day_candles(h1_candles, now)
    reference_trading_day = previous_utc_day_window(now)[0].date()

    trading_day = now.date()
    setup_id = f"{CANONICAL_SYMBOL}:{trading_day.isoformat()}"

    symbol_meta = crypto_symbol_meta(CANONICAL_SYMBOL)
    stop_buffer_price = crypto_sl_buffer_price(CANONICAL_SYMBOL, profile_config.buffer_ticks or 10.0)

    setup_state = runtime.evaluate(
        setup_id=setup_id, strategy_id=strategy_config.strategy_id, symbol=CANONICAL_SYMBOL,
        trading_day=trading_day, profile=profile_config.profile,
        reference_candles=reference_candles, h1_candles=h1_candles, m5_candles=m5_candles,
        execution_windows=profile_config.profile.execution_windows, equity=equity,
        symbol_meta=symbol_meta, risk_percent=strategy_config.risk_percent,
        stop_buffer_price=stop_buffer_price, entry_ttl_m5_bars=strategy_config.entry_ttl_m5_bars,
        daily_loss_guard=daily_loss_guard, open_position_guard=open_position_guard,
        market_structure_config=market_structure_config,
        now=now,
    )

    if setup_state.state != STATE_ENTRY_READY:
        return ResearchCycleResult(setup_state=setup_state, proposal=None, ledger_new_row=False,
                                    trading_day=trading_day)

    occurrence_id = btc_occurrence_id(
        strategy_config.strategy_id, strategy_config.version, EXCHANGE_ID, CANONICAL_SYMBOL,
        reference_trading_day, setup_state.direction, setup_state.sweep_time, setup_state.mss_time,
    )

    # Worst-case exit leg (stop_loss) for the cost estimate -- conservative (higher-cost)
    # rather than optimistic (target hit) as the default evidentiary figure.
    cost_estimate = costs.estimate_costs(
        entry_time=setup_state.sweep_time or now, entry_price=setup_state.entry,
        exit_price=setup_state.stop_loss, volume=setup_state.volume or symbol_meta.volume_min,
        tick_size=symbol_meta.tick_size, contract_size=symbol_meta.contract_size,
    )

    proposal = BTCSweepResearchProposal(
        strategy=strategy_config.strategy_id, strategy_version=strategy_config.version,
        authority=AUTHORITY_RESEARCH_ONLY, exchange=EXCHANGE_ID, instrument=CANONICAL_SYMBOL,
        direction=setup_state.direction, reference_day=reference_trading_day,
        reference_high=setup_state.ref_high, reference_low=setup_state.ref_low,
        sweep={"level": setup_state.sweep_level, "extreme": setup_state.sweep_extreme,
               "time": setup_state.sweep_time},
        confirmation={"broken_swing_price": setup_state.broken_swing_price, "mss_time": setup_state.mss_time},
        entry=setup_state.entry, stop=setup_state.stop_loss,
        target={"tp1": setup_state.tp1, "tp2": setup_state.tp2}, RR=setup_state.tp2_r_multiple,
        estimated_fees=cost_estimate.fees_estimate + cost_estimate.slippage_estimate,
        funding_assumption=dataclasses.asdict(cost_estimate),
        data_timestamp=now, expiry=_expiry_for(profile_config, trading_day), occurrence_id=occurrence_id,
        volume=setup_state.volume, risk_amount=setup_state.risk_amount, setup_id=setup_id,
        evidence=dict(setup_state.evidence),
    )

    ledger_new_row = ledger.record(proposal)
    return ResearchCycleResult(setup_state=setup_state, proposal=proposal, ledger_new_row=ledger_new_row,
                                trading_day=trading_day)
