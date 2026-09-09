"""Strategy-neutral adapter registry (P6). Maps a strategy_id to the diagnostic adapter
module that knows how to interpret ITS gates -- the core classifier/service code never
hardcodes a strategy_id or a strategy-specific gate name; see adapters/.

Reused, not duplicated: DEFAULT_APPLICATION_RELEASE mirrors src/api/app.py's own
DEFAULT_APPLICATION_RELEASE literal ("AG_TRADE_ASSISTANT_V1_0_3") -- this package has no
authority to invent a different release identity, so it is copied here rather than
importing api.app (which would pull in FastAPI as a hard dependency of this read-only
diagnostic package).
"""
from __future__ import annotations

from typing import Dict, FrozenSet

from validation_diagnostics.adapters import btc_sweep, large_smc, session_trade

DEFAULT_APPLICATION_RELEASE = "AG_TRADE_ASSISTANT_V1_0_3"

# Each adapter module exposes: SUPPORTED_GATES (frozenset of gate names it knows how to
# diagnose) and diagnose_gate(gate_name, record, repo_root) -> RawDiagnosis (see
# adapters/__init__.py). A strategy_id absent from this map, or a gate_name absent from
# its adapter's SUPPORTED_GATES, is a deliberate stop condition (P25) -- never routed to
# a generic guess.
ADAPTER_BY_STRATEGY: Dict[str, object] = {
    session_trade.STRATEGY_ID: session_trade,
    large_smc.STRATEGY_ID: large_smc,
    btc_sweep.STRATEGY_ID: btc_sweep,
}


class UnsupportedDiagnosticTargetError(Exception):
    """Raised when no adapter is registered for a strategy_id, or the registered
    adapter does not support the requested gate_name -- fail closed (P25), never a
    silent generic fallback that could fabricate a root cause for a gate this package
    has not been explicitly taught."""


def get_adapter(strategy_id: str):
    adapter = ADAPTER_BY_STRATEGY.get(strategy_id)
    if adapter is None:
        raise UnsupportedDiagnosticTargetError(
            f"no diagnostic adapter registered for strategy_id={strategy_id!r}"
        )
    return adapter


def supported_gates(strategy_id: str) -> FrozenSet[str]:
    return get_adapter(strategy_id).SUPPORTED_GATES
