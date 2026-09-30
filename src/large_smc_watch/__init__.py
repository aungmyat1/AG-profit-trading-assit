"""ST_LARGE_SMC_V1@1.1.0 watch/alerts (AG V1 Goal 2) -- ALERTS ONLY.

proposal_generation_authorized = False. There is no execution, order, position or
transport path: alert events are archived only (ARCHIVE_ONLY) through the existing
ticket_delivery journal. v1.0.7 (strategies/ST_LARGE_SMC_V1.yaml) is preserved unchanged.
"""
from .contract import STRATEGY_ID, STRATEGY_VERSION
from .watch import AlertEvent, Snapshot, WatchTracker, evaluate_snapshot

__all__ = ["STRATEGY_ID", "STRATEGY_VERSION", "AlertEvent", "Snapshot", "WatchTracker", "evaluate_snapshot"]
