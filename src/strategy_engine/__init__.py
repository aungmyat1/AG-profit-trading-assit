"""Strategy Engine: the deterministic trading brain.

MarketData -> StrategyConfig -> session box -> classify -> setup -> TradeSignal.

This package decides what a strategy would signal. It never talks to a broker: no MT5
import, no order_send. See ../PROJECT_STATUS.md for the authority order
(Strategy YAML -> Strategy Engine -> Execution Engine -> MT5; agent skills are advisory
only) and for what layers of the target architecture are implemented vs. still stubs.
"""
from .engine import evaluate
from .loader import load_strategy
from .models import RiskConfig, SessionPair, StrategyConfig, TargetLeg, TradeSignal

__all__ = [
    "StrategyConfig", "SessionPair", "RiskConfig", "TargetLeg", "TradeSignal",
    "load_strategy", "evaluate",
]
