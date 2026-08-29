"""Deterministic dedup identities (spec section 5). Plain colon-joined strings, not
hashes -- readable in the persisted JSON and in logs, and equally deterministic.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence, Tuple


def session_event_id(strategy_id: str, symbol: str, trading_date: date, reference_session: str) -> str:
    return f"SESSION:{strategy_id}:{symbol}:{trading_date.isoformat()}:{reference_session}"


def smc_alert_id(strategy_id: str, symbol: str, triggered_condition_keys: Sequence[Tuple[str, str]]) -> str:
    """Order-independent dedup identity -- same (condition_id, source_key) pairs always
    produce the same id regardless of E1/E2/E3 evaluation order, matching the sorted
    dedup-key semantics smc_watcher.watcher.SMCConditionWatcher.evaluate already uses
    for its own in-memory `_seen` set (spec section 24: strategy_id, symbol, and each
    triggered condition's source identity)."""
    ordered = sorted(triggered_condition_keys)
    conditions = "+".join(cid for cid, _ in ordered)
    sources = "+".join(str(key) for _, key in ordered)
    return f"{strategy_id}:{symbol}:{conditions}:{sources}"


def bar_cursor_key(symbol: str, timeframe: str, watcher: str) -> str:
    return f"{symbol}:{timeframe}:{watcher}"
