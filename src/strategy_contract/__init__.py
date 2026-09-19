"""AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_V1 additions.

This package is a small, ADDITIVE, read-only normalization layer over AG's existing,
independently-signed strategy decision shapes. It does not replace, wrap, or change the
behavior of any native strategy engine; see decision.py's module docstring for the exact
non-goals and field-provenance rules.
"""

from .replay_bridge import ReplayBridgeError, ReplayMarketSnapshot, build_replay_market_snapshot

__all__ = ["ReplayBridgeError", "ReplayMarketSnapshot", "build_replay_market_snapshot"]
