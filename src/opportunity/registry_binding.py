"""StrategyBinding (P2.5, P7).

Resolves strategy identity WITHOUT fabricating capability. Registry presence
(`strategies/registry.yaml`) is never treated as proof of runtime dispatchability
-- as of this mission, `strategy_manager.manager.evaluate()` only has a real
adapter wired for SESSION_TRADE_V1; every other registered strategy_id returns
STRATEGY_ADAPTER_NOT_IMPLEMENTED (see src/strategy_manager/manager.py). A binding
must describe that truthfully rather than assume aliases/registration imply
dispatchability.

This module is READ-ONLY: it inspects strategies/registry.yaml and the small set
of facts already established in src/strategy_manager/manager.py's own docstring;
it does not run, import, or alter any strategy engine, and it never mutates
registry authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import yaml

_REGISTRY_PATH = "strategies/registry.yaml"

# Only strategy_id the manager actually dispatches, per
# src/strategy_manager/manager.py: "Only SESSION_TRADE_V1 has an adapter in this
# V1 -- any other strategy_id is reported STRATEGY_ADAPTER_NOT_IMPLEMENTED".
_DISPATCHABLE_STRATEGY_IDS = frozenset({"SESSION_TRADE_V1"})


@dataclass(frozen=True)
class StrategyBinding:
    strategy_id: str
    semantic_version: Optional[str]

    engine_id: Optional[str]
    engine_version: Optional[str]

    adapter_id: Optional[str]
    adapter_version: Optional[str]

    dispatchable: bool

    supported_symbols: Tuple[str, ...] = field(default_factory=tuple)
    supported_timeframes: Tuple[str, ...] = field(default_factory=tuple)

    lifecycle: Optional[str] = None

    opportunity_authority: bool = False
    proposal_authority: bool = False
    execution_authority: str = "NONE"  # NONE | DEMO_AUTHORIZED | LIVE_AUTHORIZED

    replay_supported: bool = False
    live_observation_supported: bool = False

    configuration_fingerprint: Optional[str] = None


class StrategyNotRegisteredError(KeyError):
    pass


def _load_registry(registry_path: str = _REGISTRY_PATH) -> dict:
    with open(registry_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return (data or {}).get("strategies", {})


def resolve_strategy_binding(strategy_id: str, registry_path: str = _REGISTRY_PATH) -> StrategyBinding:
    """Resolve a StrategyBinding for an already-registered strategy_id. Raises
    StrategyNotRegisteredError (fail closed) if the id is absent from the
    registry -- this function never invents a binding for an unregistered id."""
    entries = _load_registry(registry_path)
    if strategy_id not in entries:
        raise StrategyNotRegisteredError(strategy_id)
    entry = entries[strategy_id]

    demo = bool(entry.get("demo_authorized", False))
    live = bool(entry.get("live_authorized", False))
    execution_authority = "LIVE_AUTHORIZED" if live else ("DEMO_AUTHORIZED" if demo else "NONE")

    dispatchable = strategy_id in _DISPATCHABLE_STRATEGY_IDS

    return StrategyBinding(
        strategy_id=strategy_id,
        semantic_version=None,  # not tracked in registry.yaml for most entries; left unfabricated
        engine_id=entry.get("engine"),
        engine_version=None,
        adapter_id="strategy_manager.session_trade_adapter" if dispatchable else None,
        adapter_version=None,
        dispatchable=dispatchable,
        lifecycle="RESEARCH" if entry.get("research") else None,
        opportunity_authority=bool(entry.get("registered", False)),
        proposal_authority=dispatchable,  # only a dispatchable strategy can reach proposal formation
        execution_authority=execution_authority,
        replay_supported=False,
        live_observation_supported=bool(entry.get("active", False)),
        configuration_fingerprint=None,
    )
