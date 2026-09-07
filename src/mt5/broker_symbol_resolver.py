"""Canonical strategy symbol -> broker MT5 symbol name, config-driven
(config/mt5.yaml's symbol_map section) per broker. Strategy/research code never sees a
broker-specific name -- only this module (and mt5.config's broker identity) knows, e.g.,
Vantage calls the strategy's canonical BTCUSDT symbol "BTCUSD".

Deliberately separate from mt5.symbol_resolver, which looks up broker CONTRACT metadata
(tick size, volume step, ...) for an already-resolved broker symbol name -- this module's
only job is the name translation step that happens before that lookup.
"""
from __future__ import annotations

import os
from typing import Dict

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "mt5.yaml")


class BrokerSymbolMapError(RuntimeError):
    pass


def _load_symbol_map() -> Dict[str, Dict[str, str]]:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config.get("symbol_map", {}) or {}


def resolve_broker_symbol(canonical_symbol: str, broker: str) -> str:
    """Fails closed: raises BrokerSymbolMapError for an unmapped (broker,
    canonical_symbol) pair rather than assuming the broker symbol equals the canonical
    one."""
    symbol_map = _load_symbol_map()
    broker_map = symbol_map.get(broker)
    if broker_map is None:
        raise BrokerSymbolMapError(f"UNMAPPED_BROKER: no symbol_map entry for broker {broker!r}")
    broker_symbol = broker_map.get(canonical_symbol)
    if not broker_symbol:
        raise BrokerSymbolMapError(
            f"UNMAPPED_SYMBOL: no symbol_map entry for {canonical_symbol!r} under broker {broker!r}"
        )
    return broker_symbol
