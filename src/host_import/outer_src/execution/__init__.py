"""Execution engine: TradeSignal -> TradeIntent -> risk -> validation -> MT5 -> journal.

This package is the only one allowed to place orders (via mt5_gateway.py -> mt5/).
strategy_engine/ must never be imported alongside MT5 order functions in the same call
path -- see ../PROJECT_STATUS.md 'Authority order'.

Status: intent_builder.py, risk.py, validator.py are implemented (Phase B: SIGNAL ->
TradeIntent -> READY_FOR_ORDER_CHECK, no order_check/order_send). executor.py,
mt5_gateway.py, journal.py still raise NotImplementedError -- see each module's
docstring and PROJECT_STATUS.md's implementation sequence.
"""
from .intent_builder import build_intent
from .models import STATUS_READY, IntentResult, TradeIntent

__all__ = ["build_intent", "IntentResult", "TradeIntent", "STATUS_READY"]
