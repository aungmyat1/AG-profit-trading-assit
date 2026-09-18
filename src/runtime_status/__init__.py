"""Runtime-status observation layer (AG_PROJECT_LIVE_CONTROL_PLANE_V2).

Separate and subordinate to the governance live-status snapshot. See `probe.py` for the
hard rules (read-only, bounded, never starts services, never imports execution order
paths, never feeds governance).
"""

from runtime_status.probe import (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    RuntimeProbe,
    RuntimeStatus,
    probe_runtime,
)

__all__ = [
    "STATUS_AVAILABLE",
    "STATUS_UNAVAILABLE",
    "RuntimeProbe",
    "RuntimeStatus",
    "probe_runtime",
]
