"""Normalized schemas the performance calculator consumes. Adapters map each
strategy's own native evidence into these -- nothing here is itself a source of truth;
each field must be traceable back to `source_path`/`source_record_id`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class ResolvedTradeSample:
    """One resolved (or resolved-enough-to-have-a-gross-R) trade, normalized from
    whatever shape the strategy's own outcome-resolution evidence uses. `gross_R` is
    required (a sample with no gross_R is not a resolved trade); `net_R` is `None` when
    costs have not been modeled for this sample -- callers must render that as
    NOT_EVALUATED, never silently as 0.0 or as gross_R."""

    source_record_id: str
    source_path: str
    strategy_id: str
    strategy_version: str
    symbol: str
    cycle: Optional[str]
    resolved_at: Optional[str]
    gross_R: float
    net_R: Optional[float]
    cost_status: str
    outcome: str  # e.g. RESOLVED_SL, RESOLVED_TP1, WIN, LOSS, BREAKEVEN -- source's own label, not renamed


@dataclass(frozen=True)
class FunnelCounts:
    """Row-level breakdown of a Large-SMC-style setup ledger. This is explicitly a
    DIFFERENT metric from historical_replay.orchestrator.FunnelTracker's own
    distinct-first-occurrence-per-stage counts (ReplayResult.per_e/per_m) -- those
    count a stage transition once no matter how many rows later share it; this counts
    CURRENT ROWS in the persisted ledger by their latest known stage. Do not treat the
    two as interchangeable; both are legitimate, differently-scoped views."""

    total_rows: int
    by_entry_condition: Dict[str, int] = field(default_factory=dict)  # E1/E2/E3 -> row count
    by_maneuver: Dict[str, int] = field(default_factory=dict)  # M1/M2/M3 -> row count
    e_qualified: int = 0  # every row in the ledger, by construction (see live_ledger docstring)
    m_engaged: int = 0  # final_state beyond WAITING_HTF_TOUCH/SCANNING_CONTEXT
    entry_eligible: int = 0  # final_state in (WAITING_M5_ENTRY, READY)
    trade_geometry_complete: int = 0  # final_state == READY (entry/stop/target all set)
    resolved: int = 0  # terminal is True (INVALIDATED/EXPIRED/READY-then-something-terminal)
    invalidated: int = 0
    expired: int = 0


@dataclass(frozen=True)
class TradeMetrics:
    sample_size: int
    wins: int
    losses: int
    breakevens: int
    gross_total_R: float
    gross_expectancy_R: float
    net_total_R: object  # float or NOT_EVALUATED
    net_expectancy_R: object  # float or NOT_EVALUATED
    win_rate: float
    average_win_R: object  # float or NOT_EVALUATED
    average_loss_R: object  # float or NOT_EVALUATED
    profit_factor: object  # float, "UNDEFINED_NO_LOSSES", "UNDEFINED_NO_WINS", or NOT_EVALUATED
    max_drawdown_R: object  # float or NOT_EVALUATED
    max_consecutive_losses: int
    cost_status: str


@dataclass(frozen=True)
class PerformanceSnapshot:
    generated_at: str
    application_release: str
    strategy_id: str
    strategy_version: str
    evidence_basis: str
    sample_size: int
    trade_metrics: Optional[TradeMetrics]
    funnel_counts: Optional[FunnelCounts]
    gross_classification: str
    net_classification: str
    source_paths: tuple
