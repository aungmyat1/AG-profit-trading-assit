"""Market Swing Structure -- advisory analytical composition layer (P4/P32).

Orchestrates existing canonical AG engines (market_structure, liquidity, supply_demand)
into one normalized, MTF-aware structure snapshot. Introduces exactly two genuinely new
pieces of logic, both pure derivations documented in their own modules:

  - confirmation.py  -- explicit swing pivot confirmation timestamps (derived from
                         already-known swing_length + timeframe duration, never a second
                         pivot detector)
  - alignment.py     -- an HTF/LTF structural-agreement LABEL over already-computed
                         structure_state values (never a bias/entry decision)

Everything else (swings, BOS/CHoCH, liquidity levels, FVGs, dealing-range arithmetic) is
read from the existing canonical modules unchanged -- see orchestrator.py.

Authority: ADVISORY_CONTEXT_ONLY (models.AUTHORITY). This package has no lifecycle,
strategy-configuration, risk, or execution authority -- see
tests/test_market_swing_structure.py's authority-boundary tests.
"""
from __future__ import annotations

from .models import AUTHORITY, SCHEMA_VERSION, MarketSwingStructureResult
from .orchestrator import analyze

__all__ = ["analyze", "MarketSwingStructureResult", "AUTHORITY", "SCHEMA_VERSION"]
