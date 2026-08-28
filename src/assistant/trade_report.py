"""Formats a strategy_engine.TradeSignal (and, once implemented, an execution outcome)
into the human-readable report shown to the user -- e.g. the "EURUSD / Asian box
complete / Regime: RANGE / Decision: NO TRADE" style report. NOT YET IMPLEMENTED --
see PROJECT_STATUS.md implementation sequence (step 11)."""
from __future__ import annotations


def render(*args, **kwargs):
    raise NotImplementedError(
        "assistant.trade_report.render is not implemented yet. "
        "See PROJECT_STATUS.md 'Implementation sequence' step 11."
    )
