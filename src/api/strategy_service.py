"""Read-only strategy/governance summaries for GET /api/strategies and
GET /api/validation/{id}. No new source of truth: registration/lifecycle facts are
read directly from strategies/registry.yaml and config/governance/
strategy_lifecycle.yaml (the same files and the same plain yaml.safe_load(...)
pattern already used by authorization.strategy_authority -- duplicated here rather
than imported, matching that module's own stated convention of not reaching across
modules for a three-line YAML read). Validation records are read via the existing
validation_framework adapters, never recomputed here.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Optional

import yaml

REGISTRY_PATH = "strategies/registry.yaml"
LIFECYCLE_PATH = os.path.join("config", "governance", "strategy_lifecycle.yaml")


def _load_yaml_strategies(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except OSError:
        return {}
    return (raw or {}).get("strategies") or {}


def _summarize(strategy_id: str, entry: dict, lifecycle_entry: Optional[dict]) -> dict:
    return {
        "strategy_id": strategy_id,
        "registered": bool(entry.get("registered")),
        "active": bool(entry.get("active")),
        "research": bool(entry.get("research")),
        "demo_authorized": bool(entry.get("demo_authorized")),
        "live_authorized": bool(entry.get("live_authorized")),
        "lifecycle_stage": (lifecycle_entry or {}).get("lifecycle_stage"),
        "semantic_version": (lifecycle_entry or {}).get("semantic_version"),
    }


def list_strategies(registry_path: str = REGISTRY_PATH, lifecycle_path: str = LIFECYCLE_PATH) -> list:
    registry = _load_yaml_strategies(registry_path)
    lifecycle = _load_yaml_strategies(lifecycle_path)
    return [_summarize(sid, entry, lifecycle.get(sid)) for sid, entry in registry.items()]


def get_strategy(
    strategy_id: str, registry_path: str = REGISTRY_PATH, lifecycle_path: str = LIFECYCLE_PATH,
) -> Optional[dict]:
    registry = _load_yaml_strategies(registry_path)
    entry = registry.get(strategy_id)
    if entry is None:
        return None
    lifecycle = _load_yaml_strategies(lifecycle_path)
    return _summarize(strategy_id, entry, lifecycle.get(strategy_id))


_adapter_builders: Dict[str, Callable] = {}


def _builders() -> Dict[str, Callable]:
    # Imported lazily so this module (and anything that merely lists strategies) never
    # pays for validation_framework's adapter imports unless /api/validation is hit.
    if not _adapter_builders:
        from validation_framework.adapters.btc_adapter import STRATEGY_ID as BTC_ID, build_btc_record
        from validation_framework.adapters.fx_adapter import STRATEGY_ID as FX_ID, build_fx_record
        from validation_framework.adapters.large_smc_adapter import (
            STRATEGY_ID as SMC_ID,
            build_large_smc_record,
        )
        from validation_framework.adapters.session_sweep_continuation_adapter import (
            STRATEGY_ID as SSC_ID,
            build_session_sweep_continuation_record,
        )

        _adapter_builders[FX_ID] = build_fx_record
        _adapter_builders[BTC_ID] = build_btc_record
        _adapter_builders[SMC_ID] = build_large_smc_record
        _adapter_builders[SSC_ID] = build_session_sweep_continuation_record
    return _adapter_builders


def has_validation_adapter(strategy_id: str) -> bool:
    return strategy_id in _builders()


def get_validation_record(strategy_id: str) -> Optional[dict]:
    """None means "no adapter for this strategy_id" (report 404, never fabricate).
    A build_*_record() call itself may still raise (missing/malformed evidence,
    lifecycle-registry mismatch) -- that propagates to the caller, which must turn it
    into a safe, non-leaking error response rather than a raw 500."""
    builder = _builders().get(strategy_id)
    if builder is None:
        return None
    record = builder()
    return {
        "strategy_id": record.identity.strategy_id,
        "semantic_version": record.identity.semantic_version,
        "lifecycle_stage": record.lifecycle_stage.value,
        "execution_capability": record.execution_capability,
        "execution_authority": record.execution_authority,
        "next_transition": record.next_transition.value if record.next_transition else None,
        "promotion_eligible": record.promotion_eligible,
        "promotion_blockers": list(record.promotion_blockers),
        "gates": [
            {"gate_name": g.gate_name, "status": g.status.value, "evidence_refs": list(g.evidence_refs)}
            for g in record.gates.values()
        ],
    }
