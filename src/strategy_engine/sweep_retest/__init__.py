"""ST_LIQUIDITY_SWEEP_RETEST_V1: liquidity sweep + H1 trend + M5 MSS + retest, generalized
across a Forex profile (Asian High/Low/Mid reference) and a Crypto profile (Previous-Day
High/Low/Mid reference) via profile.py's MarketProfile -- one asset-independent
sweep/MSS/retest/state-machine engine, not a fork per asset class.

Package name kept as `sweep_retest` (not renamed to match the strategy_id) -- the
mechanism it implements (sweep + MSS + retest) is itself asset-independent and the name
describes that mechanism, not "session" or "asian" specifically; renaming the package
would touch every import across tests/config/execution for no behavioral gain. Only the
strategy_id and the strategies/*.yaml filename were renamed.

Orchestration only -- all trading intelligence is delegated to existing capability
modules (strategy_engine.session for the reference box math, market_structure for H1
trend / M5 swing detection, execution.risk for position sizing). See engine.py's
docstring for the full pipeline and models.py for the state machine.

Status: RESEARCH. Produces a SetupState (candidate signal, ENTRY_READY at most) -- never
sends an order. See ../../execution/adapter.py for the (interface-only) execution
boundary an ENTRY_READY setup would cross next.
"""
from .config import ProfileConfig, SweepRetestStrategyConfig, load_sweep_retest_strategy
from .crypto_symbols import CRYPTO_TICK_SIZE, crypto_sl_buffer_price, crypto_symbol_meta
from .engine import SweepRetestRuntime, evaluate_setup
from .models import (
    STATE_BLOCKED_DAILY_LOSS,
    STATE_BLOCKED_OPEN_POSITION,
    STATE_ENTRY_READY,
    STATE_MSS_CONFIRMED,
    STATE_NO_TRADE_DIRECTION,
    STATE_NO_TRADE_TARGET_GEOMETRY,
    STATE_ORDER_SUBMITTED,
    STATE_POSITION_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_SESSION_EXPIRED,
    STATE_SETUP_EXPIRED,
    STATE_STOPPED,
    STATE_SWEEP_DETECTED,
    STATE_TP1_HIT,
    STATE_TP2_HIT,
    STATE_WAITING_MSS,
    STATE_WAITING_REFERENCE,
    STATE_WAITING_RETEST,
    STATE_WAITING_SWEEP,
    STATE_WAITING_WINDOW,
    TERMINAL_STATES,
    SetupState,
)
from .profile import (
    PROFILE_CRYPTO_PERP,
    PROFILE_FOREX,
    MarketProfile,
    build_profile_reference_box,
    filter_previous_day_candles,
    previous_utc_day_window,
    profile_for_symbol,
)
from .targets import forex_sl_buffer_price

__all__ = [
    "SetupState", "TERMINAL_STATES",
    "STATE_WAITING_REFERENCE", "STATE_WAITING_WINDOW", "STATE_WAITING_SWEEP",
    "STATE_SWEEP_DETECTED", "STATE_WAITING_MSS", "STATE_MSS_CONFIRMED",
    "STATE_WAITING_RETEST", "STATE_ENTRY_READY", "STATE_ORDER_SUBMITTED",
    "STATE_POSITION_OPEN", "STATE_TP1_HIT", "STATE_RUNNER_ACTIVE",
    "STATE_TP2_HIT", "STATE_STOPPED", "STATE_SETUP_EXPIRED", "STATE_SESSION_EXPIRED",
    "STATE_NO_TRADE_DIRECTION", "STATE_NO_TRADE_TARGET_GEOMETRY",
    "STATE_BLOCKED_DAILY_LOSS", "STATE_BLOCKED_OPEN_POSITION",
    "SweepRetestStrategyConfig", "ProfileConfig", "load_sweep_retest_strategy",
    "evaluate_setup", "SweepRetestRuntime",
    "MarketProfile", "PROFILE_FOREX", "PROFILE_CRYPTO_PERP", "profile_for_symbol",
    "build_profile_reference_box", "previous_utc_day_window", "filter_previous_day_candles",
    "forex_sl_buffer_price", "CRYPTO_TICK_SIZE", "crypto_symbol_meta", "crypto_sl_buffer_price",
]
