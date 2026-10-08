"""Deterministic SESSION_TRADE_V2 research/shadow engine.

This package has no broker imports and no execution authority.
"""
from .engine import evaluate
from .models import Candle, Decision
from .ticket import build_ticket

__all__ = ["Candle", "Decision", "evaluate", "build_ticket"]
