"""Deterministic performance metrics over normalized ResolvedTradeSample/FunnelCounts.
Pure functions only -- no I/O, no strategy-specific knowledge. See models.py for the
NOT_EVALUATED convention: missing data is never silently rendered as zero.
"""
from __future__ import annotations

from typing import List, Sequence

from .models import NOT_EVALUATED, FunnelCounts, ResolvedTradeSample, TradeMetrics

_WIN_R_EPSILON = 1e-9


def _classify(r: float) -> str:
    if r > _WIN_R_EPSILON:
        return "WIN"
    if r < -_WIN_R_EPSILON:
        return "LOSS"
    return "BREAKEVEN"


def _ordered(samples: Sequence[ResolvedTradeSample]) -> List[ResolvedTradeSample]:
    """Deterministic ordering for drawdown/consecutive-loss sequencing: primary key is
    resolved_at (None sorts first, treated as unknown-earliest -- flagged, never
    silently dropped), secondary stable key is source_record_id so ties never depend on
    input iteration order."""
    return sorted(samples, key=lambda s: (s.resolved_at is None, s.resolved_at or "", s.source_record_id))


def compute_trade_metrics(samples: Sequence[ResolvedTradeSample]) -> TradeMetrics:
    n = len(samples)
    if n == 0:
        return TradeMetrics(
            sample_size=0, wins=0, losses=0, breakevens=0,
            gross_total_R=0.0, gross_expectancy_R=NOT_EVALUATED,
            net_total_R=NOT_EVALUATED, net_expectancy_R=NOT_EVALUATED,
            win_rate=NOT_EVALUATED, average_win_R=NOT_EVALUATED, average_loss_R=NOT_EVALUATED,
            profit_factor=NOT_EVALUATED, max_drawdown_R=NOT_EVALUATED, max_consecutive_losses=0,
            cost_status=NOT_EVALUATED,
        )

    ordered = _ordered(samples)
    gross_values = [s.gross_R for s in ordered]
    classes = [_classify(r) for r in gross_values]
    wins = classes.count("WIN")
    losses = classes.count("LOSS")
    breakevens = classes.count("BREAKEVEN")

    gross_total_R = sum(gross_values)
    gross_expectancy_R = gross_total_R / n

    net_values = [s.net_R for s in ordered]
    if all(v is not None for v in net_values):
        net_total_R = sum(net_values)
        net_expectancy_R = net_total_R / n
    else:
        net_total_R = NOT_EVALUATED
        net_expectancy_R = NOT_EVALUATED

    win_values = [r for r in gross_values if _classify(r) == "WIN"]
    loss_values = [r for r in gross_values if _classify(r) == "LOSS"]
    average_win_R = (sum(win_values) / len(win_values)) if win_values else NOT_EVALUATED
    average_loss_R = (sum(loss_values) / len(loss_values)) if loss_values else NOT_EVALUATED

    positive_sum = sum(r for r in gross_values if r > 0)
    negative_sum = sum(r for r in gross_values if r < 0)
    if negative_sum == 0 and positive_sum == 0:
        profit_factor = NOT_EVALUATED
    elif negative_sum == 0:
        profit_factor = "UNDEFINED_NO_LOSSES"
    elif positive_sum == 0:
        profit_factor = "UNDEFINED_NO_WINS"
    else:
        profit_factor = positive_sum / abs(negative_sum)

    cum = 0.0
    running_peak = float("-inf")
    max_drawdown = 0.0
    max_consecutive_losses = 0
    current_streak = 0
    for r in gross_values:
        cum += r
        running_peak = max(running_peak, cum)
        max_drawdown = max(max_drawdown, running_peak - cum)
        if _classify(r) == "LOSS":
            current_streak += 1
            max_consecutive_losses = max(max_consecutive_losses, current_streak)
        else:
            current_streak = 0

    cost_statuses = {s.cost_status for s in samples}
    cost_status = cost_statuses.pop() if len(cost_statuses) == 1 else "MIXED"

    return TradeMetrics(
        sample_size=n, wins=wins, losses=losses, breakevens=breakevens,
        gross_total_R=gross_total_R, gross_expectancy_R=gross_expectancy_R,
        net_total_R=net_total_R, net_expectancy_R=net_expectancy_R,
        win_rate=wins / n, average_win_R=average_win_R, average_loss_R=average_loss_R,
        profit_factor=profit_factor, max_drawdown_R=max_drawdown,
        max_consecutive_losses=max_consecutive_losses, cost_status=cost_status,
    )


# Row-level Large-SMC final_state buckets -- see FunnelCounts docstring for why this is
# deliberately NOT the same metric as FunnelTracker's distinct-first-occurrence counts.
_M_ENGAGED_STATES = {
    "HTF_QUALIFIED", "WAITING_M5_CONFIRMATION", "WAITING_M5_ENTRY", "READY",
}
_ENTRY_ELIGIBLE_STATES = {"WAITING_M5_ENTRY", "READY"}
_TRADE_GEOMETRY_COMPLETE_STATES = {"READY"}


def compute_funnel_counts(rows: Sequence[dict]) -> FunnelCounts:
    """`rows` are the raw dict records a LargeSMCSetupLedger.all() returns (or
    equivalent SetupLedgerRow-shaped dicts in tests)."""
    by_entry_condition: dict = {}
    by_maneuver: dict = {}
    m_engaged = entry_eligible = trade_geometry_complete = resolved = invalidated = expired = 0

    for row in rows:
        entry_condition = row.get("entry_condition")
        if entry_condition:
            by_entry_condition[entry_condition] = by_entry_condition.get(entry_condition, 0) + 1
        maneuver = row.get("maneuver")
        if maneuver:
            by_maneuver[maneuver] = by_maneuver.get(maneuver, 0) + 1

        final_state = row.get("final_state")
        if final_state in _M_ENGAGED_STATES:
            m_engaged += 1
        if final_state in _ENTRY_ELIGIBLE_STATES:
            entry_eligible += 1
        if final_state in _TRADE_GEOMETRY_COMPLETE_STATES:
            trade_geometry_complete += 1
        if row.get("terminal") is True:
            resolved += 1
            if final_state == "INVALIDATED":
                invalidated += 1
            elif final_state == "EXPIRED":
                expired += 1

    return FunnelCounts(
        total_rows=len(rows), by_entry_condition=by_entry_condition, by_maneuver=by_maneuver,
        e_qualified=len(rows), m_engaged=m_engaged, entry_eligible=entry_eligible,
        trade_geometry_complete=trade_geometry_complete, resolved=resolved,
        invalidated=invalidated, expired=expired,
    )


def funnel_ratio(numerator: int, denominator: int):
    if denominator == 0:
        return NOT_EVALUATED
    return numerator / denominator
