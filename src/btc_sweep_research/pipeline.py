"""One BTC research evaluation cycle: fetch candles from a CryptoCandleFeed (production:
execution_runtime.binance_usdtm_feed.BinanceUSDTMFeed; tests: a fixture feed), enumerate
EVERY qualifying sweep candidate for ST_LIQUIDITY_SWEEP_RETEST_V1's CRYPTO_PERP profile
(strategy_engine/sweep_retest/occurrence_enumerator.py), evaluate each one independently
via the EXISTING, untouched SweepRetestRuntime/evaluate_setup (strategy_engine/
sweep_retest/engine.py), and on strategy_qualified build + dedup-record a
BTCSweepResearchProposal per occurrence.

Remediation Gap 1 (multi-occurrence collection): the previous version used ONE setup_id
per symbol/day, so SweepRetestRuntime's terminal-state caching meant a later, genuinely
independent sweep the same day was never (re-)evaluated once the day's setup_id went
terminal. Fixed by giving each enumerated sweep candidate its OWN occurrence-scoped
setup_id (f"{symbol}:{trading_day}:{sweep.candle_time.isoformat()}") -- each one is then
independently tracked, restart-safe, and terminal-state-cached through the SAME
SweepRetestRuntime, unchanged.

Remediation Gap 2 (research vs tradability): engine.evaluate_setup() itself now checks
daily_loss_guard/open_position_guard only AFTER full qualification (see its own "Guard
ordering" docstring) -- a genuinely qualified-but-guard-blocked occurrence still reaches
strategy_qualified=True and still gets a proposal + ledger row here, with
tradability_allowed=False. This module's own job is simply: build a proposal whenever
strategy_qualified is True, regardless of tradability.

Deliberately does NOT reuse execution_runtime/cycle.py::evaluate_and_route: that module's
evaluate_and_route ultimately calls ctx.coordinator.submit(...), and
execution.coordinator imports execution.executor (a real, if demo/confirmation-gated,
order-submission path) -- importing that chain here would violate this task's hard
constraint that the BTC research runner must never import execution.executor /
mt5.management_gateway / any order_send path. This module therefore re-implements just the
orchestration (fetch -> enumerate -> evaluate -> record), calling SweepRetestRuntime
directly, with NO import of execution.coordinator/execution.executor/execution.adapter/
mt5.management_gateway anywhere in this package (see
tests/test_btc_proposal_execution_boundary.py).

Every capability this module calls already exists elsewhere and is reused unchanged:
strategy_engine.sweep_retest.{engine,profile,occurrence_enumerator,occurrence_identity},
execution.daily_loss_guard / execution.position_guard (the SAME shared, COMBINED-across-
Forex-and-Crypto guards ST_LIQUIDITY_SWEEP_RETEST_V1's Forex path already uses).

Remediation Gap 19 (exchange metadata consistency): symbol_meta is now built from THIS
adapter's own exchange-specific record (execution_runtime.binance_usdtm_feed.
default_symbol_meta() + to_symbol_meta()), not strategy_engine.sweep_retest.crypto_symbols.
crypto_symbol_meta()'s hardcoded synthetic defaults -- one authority for tick/step/min-qty,
not two. See binance_usdtm_feed.to_symbol_meta's own docstring for why this stays tagged
METADATA_SOURCE_SYNTHETIC_RESEARCH regardless (never EXCHANGE_VERIFIED -- that tag has a
distinct, FX/MT5-execution-eligibility meaning elsewhere in this repo).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Tuple

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from execution_runtime.binance_usdtm_feed import CANONICAL_SYMBOL, EXCHANGE_ID, default_symbol_meta, to_symbol_meta
from execution_runtime.crypto_feed import CryptoCandleFeed
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.sweep_retest.config import SweepRetestStrategyConfig, load_sweep_retest_strategy
from strategy_engine.sweep_retest.engine import SweepRetestRuntime, in_execution_windows, sweep_requirement_for_h1_direction
from strategy_engine.sweep_retest.models import (
    STATE_NO_TRADE_DIRECTION,
    STATE_WAITING_REFERENCE,
    STATE_WAITING_SWEEP,
    STATE_WAITING_WINDOW,
    SetupState,
)
from strategy_engine.sweep_retest.occurrence_enumerator import enumerate_sweep_candidates
from strategy_engine.sweep_retest.occurrence_identity import btc_occurrence_id
from strategy_engine.sweep_retest.profile import (
    build_profile_reference_box,
    filter_previous_day_candles,
    previous_utc_day_window,
)
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore
from strategy_engine.sweep_retest.trend import h1_trend_direction

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
    """One enumerated occurrence's evaluation result."""
    setup_state: SetupState
    proposal: Optional[BTCSweepResearchProposal]
    ledger_new_row: bool
    trading_day: date


@dataclass(frozen=True)
class ResearchCycleReport:
    """One evaluation cycle's full result -- 0..N occurrences (remediation Gap 1: no
    artificial cap). container_state is populated ONLY when no occurrence could even be
    enumerated this cycle (reference not yet complete, H1 direction neutral, or the
    execution window not yet reached) -- an ephemeral, non-persisted status, since there
    is no occurrence identity to key it by and nothing to resume (a fresh, cheap,
    deterministic recomputation next cycle is correct, same as the FX pilot's own WATCH
    decisions). Exactly one of container_state / occurrences is ever non-empty."""
    trading_day: date
    container_state: Optional[SetupState]
    occurrences: Tuple[ResearchCycleResult, ...]

    @property
    def qualified_occurrences(self) -> Tuple[ResearchCycleResult, ...]:
        return tuple(o for o in self.occurrences if o.setup_state.strategy_qualified)

    @property
    def tradable_occurrences(self) -> Tuple[ResearchCycleResult, ...]:
        return tuple(o for o in self.qualified_occurrences if not o.setup_state.tradability_blocked)


def _container(strategy_id: str, symbol: str, trading_day: date, now, state: str, reason_code: str,
               **evidence) -> SetupState:
    return SetupState(
        setup_id=f"{symbol}:{trading_day.isoformat()}", strategy_id=strategy_id, symbol=symbol,
        state=state, reason_code=reason_code, evaluated_at=now, **evidence,
    )


def _expiry_for(profile_config, trading_day: date) -> datetime:
    """Natural validity boundary for a research proposal: the strategy's own Strategy
    Activity execution window close on the trading day it was produced (same convention
    as the FX pilot's PROPOSAL_EXPIRY_MINUTES -- "a stale sweep signal is not re-
    validated", see post_asian_pilot/proposal.py), rather than an invented duration."""
    window_end_time = profile_config.profile.execution_windows[-1][1]
    return datetime.combine(trading_day, window_end_time, tzinfo=timezone.utc)


def _build_proposal(
    setup_state: SetupState, strategy_config: SweepRetestStrategyConfig, profile_config,
    reference_trading_day: date, symbol_meta, trading_day: date, now: datetime, exchange_id: str,
) -> BTCSweepResearchProposal:
    occurrence_id = btc_occurrence_id(
        strategy_config.strategy_id, strategy_config.version, exchange_id, CANONICAL_SYMBOL,
        reference_trading_day, setup_state.direction, setup_state.sweep_time, setup_state.mss_time,
    )
    # Worst-case exit leg (stop_loss) for the cost estimate -- conservative (higher-cost)
    # rather than optimistic (target hit) as the default evidentiary figure.
    cost_estimate = costs.estimate_costs(
        entry_time=setup_state.sweep_time or now, entry_price=setup_state.entry,
        exit_price=setup_state.stop_loss, volume=setup_state.volume or symbol_meta.volume_min,
        tick_size=symbol_meta.tick_size, contract_size=symbol_meta.contract_size,
    )
    return BTCSweepResearchProposal(
        strategy=strategy_config.strategy_id, strategy_version=strategy_config.version,
        authority=AUTHORITY_RESEARCH_ONLY, exchange=exchange_id, instrument=CANONICAL_SYMBOL,
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
        volume=setup_state.volume, risk_amount=setup_state.risk_amount, setup_id=setup_state.setup_id,
        evidence=dict(setup_state.evidence),
        tradability_allowed=not setup_state.tradability_blocked, tradability_block_reason=setup_state.tradability_reason,
    )


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
    exchange_id: str = EXCHANGE_ID,
    symbol_meta: Optional[SymbolMeta] = None,
) -> ResearchCycleReport:
    """`exchange_id`/`symbol_meta` are additive, backward-compatible overrides
    (AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3): every existing
    caller that omits them gets EXACTLY the previous behavior (Binance identity/
    metadata, unchanged) -- this lets a Bybit-fed cycle tag its proposals with the
    correct exchange identity and use Bybit's own verified tick/step-size metadata
    instead of silently mislabeling Bybit-sourced data as Binance's. No strategy/sweep/
    trend/retest/entry/risk rule is touched by this parametrization."""
    now = now or datetime.now(timezone.utc)
    strategy_config = strategy_config or load_sweep_retest_strategy(STRATEGY_YAML_PATH)
    profile_config = strategy_config.profile_config_for_symbol(CANONICAL_SYMBOL)
    if profile_config is None:
        raise ValueError(f"{STRATEGY_YAML_PATH} has no CRYPTO_PERP profile entry for {CANONICAL_SYMBOL!r}")

    runtime = runtime or SweepRetestRuntime(SweepRetestStateStore())
    ledger = ledger or BTCResearchLedger()
    daily_loss_guard = daily_loss_guard or DailyLossGuard.default(strategy_config.strategy_id)
    open_position_guard = open_position_guard or OpenPositionGuard.default()

    trading_day = now.date()
    symbol_meta = symbol_meta or to_symbol_meta(default_symbol_meta(CANONICAL_SYMBOL))
    stop_buffer_price = symbol_meta.tick_size * (profile_config.buffer_ticks or 10.0)

    h1_candles = list(feed.get_latest_candles(CANONICAL_SYMBOL, "H1", H1_LOOKBACK_COUNT))
    m5_candles_raw = list(feed.get_latest_candles(CANONICAL_SYMBOL, "M5", M5_LOOKBACK_COUNT))

    today_start = previous_utc_day_window(now)[1]
    m5_candles = [c for c in m5_candles_raw if c.time >= today_start]
    reference_candles = filter_previous_day_candles(h1_candles, now)
    reference_trading_day = previous_utc_day_window(now)[0].date()

    box = build_profile_reference_box(profile_config.profile, reference_candles, expected_bar_count=None)
    if box is None or not box.session_complete:
        container = _container(strategy_config.strategy_id, CANONICAL_SYMBOL, trading_day, now,
                               STATE_WAITING_REFERENCE, "REFERENCE_WINDOW_INCOMPLETE",
                               profile_id=profile_config.profile.profile_id)
        return ResearchCycleReport(trading_day, container, ())

    direction_gate = h1_trend_direction(h1_candles, market_structure_config)
    required_sweep_direction, trade_direction = sweep_requirement_for_h1_direction(direction_gate)
    if required_sweep_direction is None:
        container = _container(strategy_config.strategy_id, CANONICAL_SYMBOL, trading_day, now,
                               STATE_NO_TRADE_DIRECTION, STATE_NO_TRADE_DIRECTION,
                               profile_id=profile_config.profile.profile_id, ref_high=box.session_high,
                               ref_low=box.session_low, ref_mid=box.session_mid)
        return ResearchCycleReport(trading_day, container, ())

    window_candles = [c for c in m5_candles if in_execution_windows(c.time, profile_config.profile.execution_windows)]
    if not window_candles:
        container = _container(strategy_config.strategy_id, CANONICAL_SYMBOL, trading_day, now,
                               STATE_WAITING_WINDOW, "EXECUTION_WINDOW_NOT_REACHED",
                               profile_id=profile_config.profile.profile_id, ref_high=box.session_high,
                               ref_low=box.session_low, ref_mid=box.session_mid, direction=trade_direction)
        return ResearchCycleReport(trading_day, container, ())

    candidates = enumerate_sweep_candidates(
        m5_candles, profile_config.profile.execution_windows, box.session_high, box.session_low,
        required_sweep_direction,
    )
    if not candidates:
        container = _container(strategy_config.strategy_id, CANONICAL_SYMBOL, trading_day, now,
                               STATE_WAITING_SWEEP, "NO_QUALIFIED_SWEEP_YET",
                               profile_id=profile_config.profile.profile_id, ref_high=box.session_high,
                               ref_low=box.session_low, ref_mid=box.session_mid, direction=trade_direction)
        return ResearchCycleReport(trading_day, container, ())

    results = []
    for i, candidate in enumerate(candidates):
        sweep_search_after = candidates[i - 1].candle_time if i > 0 else None
        occurrence_setup_id = f"{CANONICAL_SYMBOL}:{trading_day.isoformat()}:{candidate.candle_time.isoformat()}"

        setup_state = runtime.evaluate(
            setup_id=occurrence_setup_id, strategy_id=strategy_config.strategy_id, symbol=CANONICAL_SYMBOL,
            trading_day=trading_day, profile=profile_config.profile,
            reference_candles=reference_candles, h1_candles=h1_candles, m5_candles=m5_candles,
            execution_windows=profile_config.profile.execution_windows, equity=equity,
            symbol_meta=symbol_meta, risk_percent=strategy_config.risk_percent,
            stop_buffer_price=stop_buffer_price, entry_ttl_m5_bars=strategy_config.entry_ttl_m5_bars,
            daily_loss_guard=daily_loss_guard, open_position_guard=open_position_guard,
            market_structure_config=market_structure_config, now=now, sweep_search_after=sweep_search_after,
        )

        proposal = None
        ledger_new_row = False
        if setup_state.strategy_qualified:
            proposal = _build_proposal(setup_state, strategy_config, profile_config, reference_trading_day,
                                       symbol_meta, trading_day, now, exchange_id)
            ledger_new_row = ledger.record(proposal)

        results.append(ResearchCycleResult(setup_state=setup_state, proposal=proposal,
                                           ledger_new_row=ledger_new_row, trading_day=trading_day))

    return ResearchCycleReport(trading_day, None, tuple(results))
