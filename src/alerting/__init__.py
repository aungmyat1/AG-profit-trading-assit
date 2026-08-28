"""Minimal alert delivery (spec sections 27, 43). No third-party integrations --
console/log and an append-only JSONL journal only, following this repo's existing
journal convention (assistant/idea_journal.py, execution/journal.py,
trade_management/journal.py) rather than inventing a new persistence format.
"""
from .sink import AlertSink, JsonlAlertSink, LogAlertSink

__all__ = ["AlertSink", "JsonlAlertSink", "LogAlertSink"]
