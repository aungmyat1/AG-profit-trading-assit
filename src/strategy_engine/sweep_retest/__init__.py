"""ST_SESSION_SWEEP_RETEST_V1: Asian session liquidity sweep + H1 trend + M5 MSS + retest.

Orchestration only -- all trading intelligence is delegated to existing capability
modules (strategy_engine.session for the Asian reference box, market_structure for H1
trend / M5 swing detection, execution.risk for position sizing). See engine.py's
docstring for the full pipeline and models.py for the state machine.

Status: RESEARCH. Produces a SetupState (candidate signal, ENTRY_READY at most) -- never
sends an order. See ../../execution/ for what happens to an ENTRY_READY setup next.
"""
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
from .config import SweepRetestStrategyConfig, load_sweep_retest_strategy
from .engine import SweepRetestRuntime, evaluate_setup

__all__ = [
    "SetupState", "TERMINAL_STATES",
    "STATE_WAITING_REFERENCE", "STATE_WAITING_WINDOW", "STATE_WAITING_SWEEP",
    "STATE_SWEEP_DETECTED", "STATE_WAITING_MSS", "STATE_MSS_CONFIRMED",
    "STATE_WAITING_RETEST", "STATE_ENTRY_READY", "STATE_ORDER_SUBMITTED",
    "STATE_POSITION_OPEN", "STATE_TP1_HIT", "STATE_RUNNER_ACTIVE",
    "STATE_TP2_HIT", "STATE_STOPPED", "STATE_SETUP_EXPIRED", "STATE_SESSION_EXPIRED",
    "STATE_NO_TRADE_DIRECTION", "STATE_NO_TRADE_TARGET_GEOMETRY",
    "STATE_BLOCKED_DAILY_LOSS", "STATE_BLOCKED_OPEN_POSITION",
    "SweepRetestStrategyConfig", "load_sweep_retest_strategy",
    "evaluate_setup", "SweepRetestRuntime",
]
