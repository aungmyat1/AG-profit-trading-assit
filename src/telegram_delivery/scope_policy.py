"""Tracked immediate-send scope with a host-local narrowing-only override."""
from __future__ import annotations

from pathlib import Path
import yaml

POLICY_PATH = Path("config/ticket_delivery.yaml")
OVERRIDE_PATHS = {
    "legacy": Path("config/local/delivery_override.yaml"),
    "canonical": Path("config/local/canonical_ticket_delivery.yaml"),
}


def resolve(root=".", sender="legacy"):
    """Resolve one sender's scope against policy and only its own local override."""
    if sender not in OVERRIDE_PATHS:
        raise ValueError(f"unknown delivery sender: {sender}")
    root = Path(root)
    policy_path = root / POLICY_PATH
    if not policy_path.exists():
        # Unit/host probes may provide only a host-local overlay; policy remains the
        # tracked copy shipped beside this module.
        policy_path = Path(__file__).resolve().parents[2] / POLICY_PATH
    tracked = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    policy = tracked.get("immediate_send_scope") or {}
    allowed = tuple(policy.get("enabled", ()))
    disabled = tuple(policy.get("disabled", ()))
    effective = allowed
    error = None
    for override_path in (root / OVERRIDE_PATHS[sender],):
        if not override_path.exists():
            continue
        try:
            override = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
            if override.get("watch_info_scope") is True:
                effective, error = (), "SCOPE_WIDENING_REJECTED"
                break
            requested_value = override.get("immediate_send_scopes", override.get("scopes"))
            if requested_value is None:
                continue
            requested = tuple(requested_value)
            if not set(requested).issubset(allowed):
                effective, error = (), "SCOPE_WIDENING_REJECTED"
                break
            else:
                effective = tuple(scope for scope in effective if scope in requested)
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            effective, error = (), "SCOPE_OVERRIDE_INVALID"
            break
    return {"tracked": allowed, "disabled": disabled, "effective": effective, "error": error}
