"""Phase D1: deterministic strategy demo-execution authorization check.

Reads strategies/registry.yaml directly -- the SAME file and the SAME
`yaml.safe_load(...).get("strategies", {})` access pattern already used by
strategy_manager.manager._load_registry() -- rather than importing that module (which
pulls in assistant.models / strategy_manager.context_builder / session_trade_adapter,
none of which are relevant to ST_ASIAN_SWEEP_5R_V1 or to this gateway). No independent
Telegram-side copy of `demo_authorized` is ever created or cached: every call re-reads
the registry file, so an owner edit to registry.yaml takes effect on the very next
Execute Demo click without restarting anything (spec section 13/14: "Recheck
authorization when Execute Demo is clicked... never assume the authorization state at
ticket creation is still valid").
"""
from __future__ import annotations

from typing import Optional

import yaml

from .models import REASON_STRATEGY_NOT_DEMO_AUTHORIZED, REASON_STRATEGY_NOT_REGISTERED, AuthorizationCheckResult

REGISTRY_PATH = "strategies/registry.yaml"


def _load_registry(path: str = REGISTRY_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return (raw or {}).get("strategies", {})


def check_strategy_demo_authorized(
    strategy_id: str, registry_path: str = REGISTRY_PATH,
) -> AuthorizationCheckResult:
    """True only when strategies/registry.yaml explicitly marks this exact strategy_id
    `demo_authorized: true`. An unknown/unregistered strategy_id fails closed to
    REASON_STRATEGY_NOT_REGISTERED, never treated as authorized-by-absence."""
    registry = _load_registry(registry_path)
    entry: Optional[dict] = registry.get(strategy_id)
    if entry is None:
        return AuthorizationCheckResult(False, REASON_STRATEGY_NOT_REGISTERED)
    if not entry.get("demo_authorized"):
        return AuthorizationCheckResult(False, REASON_STRATEGY_NOT_DEMO_AUTHORIZED)
    return AuthorizationCheckResult(True)
