"""ASSISTANT_RUNTIME_V1: strategy-neutral orchestration (context building, registry/cycle
authority, dispatch to a strategy's own adapter). Owns no strategy decision rules -- see
strategy_manager/manager.py's module docstring.
"""
from __future__ import annotations
