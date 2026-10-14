"""Append-only 1.1.3 candidate; REPORT_ONLY, NOT_VERIFIED."""
from .contract import STRATEGY_ID, STRATEGY_VERSION
from .watch import AlertEvent, Snapshot, WatchTracker, evaluate_snapshot

__all__ = ["STRATEGY_ID", "STRATEGY_VERSION", "AlertEvent", "Snapshot", "WatchTracker", "evaluate_snapshot"]
