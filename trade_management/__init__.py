"""Trade Management capability: two independent products sharing one package by logical
ownership (see TRADE_ASSISTANT_ARCHITECTURE.md's "Assistant skill taxonomy").

1. Manual-entry management (Phase 6, `claims`/`state`/`rules`/`position_monitor`):
   manages an already-open MT5 position a human opened by hand -- detects it, tracks R,
   takes a 75% partial at TP1, moves the runner to breakeven once broker-confirmed, and
   closes the runner at 5R. Never opens a position.

2. Pre-trade calculation (Phase 5 continuation, `TRADE_MANAGEMENT_V1`, added
   2026-08-28, `geometry`/`sizing`/`position_state`/`pretrade_engine`): deterministic
   geometry validation, broker-realistic position sizing, and R/reward geometry for a
   PROPOSED trade, before any position exists -- generic across strategy or manual use.
   See ENTRY_CONFIRMATION_V1_SPEC.md's sibling, TRADE_MANAGEMENT_V1_SPEC.md.

Both are independent of the (paused) entry-side execution/ package -- see
PROJECT_STATUS.md 'Phase 6' and trade_management/models.py's docstring for the Phase 6
authority chain, and pretrade_engine.py's docstring for TRADE_MANAGEMENT_V1's boundary.
"""
from __future__ import annotations

from .geometry import evaluate_geometry
from .models import (
    ManagementPolicy,
    PositionSizing,
    PositionStateAdvisory,
    TradeGeometry,
    TradeManagementRequest,
    TradeManagementResult,
)
from .position_state import evaluate_position_state
from .pretrade_engine import evaluate_trade_management
from .sizing import evaluate_sizing

__all__ = [
    "evaluate_trade_management", "evaluate_geometry", "evaluate_sizing", "evaluate_position_state",
    "TradeManagementRequest", "TradeManagementResult", "ManagementPolicy",
    "TradeGeometry", "PositionSizing", "PositionStateAdvisory",
]
