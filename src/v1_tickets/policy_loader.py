"""Actionability policy loader (injected; no hardcoded production threshold).

Implements the versioned operational-policy schema. Paths:

    REPO_POLICY_SCHEMA        = config/policy/actionability_policy.yaml
                                (committed schema/default; signed_by = null,
                                 min_remaining_r = null; NEVER authorizes WATCH_READY)
    OWNER_RUNTIME_OVERRIDE    = config/local/actionability_policy.yaml
                                (host-local, gitignored, owner-signed; wins when present
                                 and signed_by is non-null)

Policy precedence (highest to lowest):

    1. owner-signed local override (config/local/actionability_policy.yaml), signed_by != null
            ↓ usable policy → WATCH_READY path enabled
    2. unsigned repo policy (config/policy/actionability_policy.yaml), signed_by = null
            ↓ schema/default only → POLICY_MISSING → INFO_ONLY_POLICY_UNRESOLVED
    3. missing / malformed / conflicting policy
            ↓ POLICY_MISSING / POLICY_INVALID / POLICY_CONFLICT → INFO_ONLY_POLICY_UNRESOLVED

DI (dependency injection) for tests: ``override_dict`` and ``override_path`` parameters
accept a fixture policy dictionary/file without creating a signed on-disk policy.

The loader NEVER chooses a numeric threshold.  A missing/invalid/conflicting policy is
reported with an explicit status and actionability falls back to INFO_ONLY_POLICY_UNRESOLVED
for every would-be WATCH_READY decision.  Arena does not create or sign the owner policy.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml

POLICY_ID = "LSMC_ACTIONABILITY_POLICY_V1"
REPO_POLICY_PATH = os.path.join("config", "policy", "actionability_policy.yaml")
LOCAL_POLICY_PATH = os.path.join("config", "local", "actionability_policy.yaml")

# Resolver statuses
POLICY_OK = "POLICY_OK"
POLICY_MISSING = "ACTIONABILITY_POLICY_MISSING"
POLICY_INVALID = "ACTIONABILITY_POLICY_INVALID"
POLICY_CONFLICT = "ACTIONABILITY_POLICY_CONFLICT"


@dataclass(frozen=True)
class ActionabilityPolicy:
    status: str
    policy_id: Optional[str] = None
    version: Optional[int] = None
    min_remaining_r: Optional[float] = None
    signed_by: Optional[str] = None
    signed_at: Optional[str] = None
    source_path: Optional[str] = None
    reason: Optional[str] = None

    @property
    def usable(self) -> bool:
        return (self.status == POLICY_OK
                and self.min_remaining_r is not None
                and self.min_remaining_r >= 0.0
                and self.signed_by is not None
                and bool(self.signed_by))


def _policy_paths(root: str) -> list:
    """Load order: local (host-signed, gitignored) wins over repo default."""
    paths = []
    local = os.path.join(root, LOCAL_POLICY_PATH)
    if os.path.isfile(local):
        paths.append(local)
    repo = os.path.join(root, REPO_POLICY_PATH)
    if os.path.isfile(repo):
        paths.append(repo)
    return paths


def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return None


def _validate(raw: Any, source_path: str) -> ActionabilityPolicy:
    """Validate a single loaded policy document; returns either POLICY_OK with parsed
    values or POLICY_INVALID with a reason.  Note: `signed_by: null` makes the policy
    structurally valid but NOT usable (reported as POLICY_MISSING signature)."""
    if not isinstance(raw, dict):
        return ActionabilityPolicy(status=POLICY_INVALID, source_path=source_path,
                                   reason="not a mapping")
    pid = raw.get("policy_id")
    if pid != POLICY_ID:
        return ActionabilityPolicy(status=POLICY_CONFLICT, source_path=source_path,
                                   policy_id=str(pid) if pid is not None else None,
                                   reason=f"policy_id {pid!r} != {POLICY_ID!r}")
    version = raw.get("version")
    if not isinstance(version, int) or version < 1:
        return ActionabilityPolicy(status=POLICY_INVALID, source_path=source_path,
                                   policy_id=pid, reason=f"version {version!r} not a positive int")
    min_rr = raw.get("min_remaining_r")
    if min_rr is not None:
        try:
            min_rr = float(min_rr)
        except (TypeError, ValueError):
            return ActionabilityPolicy(status=POLICY_INVALID, source_path=source_path,
                                       policy_id=pid, version=version,
                                       reason=f"min_remaining_r {min_rr!r} not numeric")
        if min_rr < 0:
            return ActionabilityPolicy(status=POLICY_INVALID, source_path=source_path,
                                       policy_id=pid, version=version,
                                       reason="min_remaining_r negative")
    signed_by = raw.get("signed_by")
    signed_at = raw.get("signed_at")
    return ActionabilityPolicy(status=POLICY_OK, policy_id=pid, version=version,
                               min_remaining_r=min_rr, signed_by=signed_by,
                               signed_at=str(signed_at) if signed_at is not None else None,
                               source_path=source_path)


def load_policy(root: str = ".", *, override_path: Optional[str] = None,
                override_dict: Optional[Dict[str, Any]] = None) -> ActionabilityPolicy:
    """Load policy. Resolution order (highest to lowest):

      1. explicit `override_dict` (for tests/DI)
      2. explicit `override_path` (for tests/DI)
      3. config/local/actionability_policy.yaml (host-signed override; gitignored)
      4. config/policy/actionability_policy.yaml (repo default; unsigned)

    A policy that parses OK but has no signed_by is POLICY_MISSING (unsigned).
    A policy with conflicting policy_id is POLICY_CONFLICT.
    Malformed YAML/schema is POLICY_INVALID.
    When multiple candidate files exist with different usable values, that is POLICY_CONFLICT.
    """
    candidates: list = []
    if override_dict is not None:
        candidates.append(_validate(override_dict, "<override_dict>"))
    if override_path is not None:
        raw = _load_yaml(override_path)
        if raw is None:
            return ActionabilityPolicy(status=POLICY_INVALID, source_path=override_path,
                                       reason="file unreadable or malformed YAML")
        candidates.append(_validate(raw, override_path))
    for path in _policy_paths(root):
        raw = _load_yaml(path)
        if raw is None:
            candidates.append(ActionabilityPolicy(status=POLICY_INVALID, source_path=path,
                                                  reason="file unreadable or malformed YAML"))
        else:
            candidates.append(_validate(raw, path))

    if not candidates:
        return ActionabilityPolicy(status=POLICY_MISSING, reason="no policy file found")

    # A single candidate drives the result; but if two usable candidates disagree on
    # min_remaining_r, flag CONFLICT.
    usable = [c for c in candidates if c.status == POLICY_OK and c.usable]
    if len({c.min_remaining_r for c in usable}) > 1:
        return ActionabilityPolicy(status=POLICY_CONFLICT, reason=(
            f"multiple signed policies disagree on min_remaining_r: "
            f"{sorted({c.min_remaining_r for c in usable})}"))
    # Invalid / conflict in any candidate with highest precedence wins (fail closed).
    for c in candidates:
        if c.status in (POLICY_CONFLICT, POLICY_INVALID):
            return c
    # Usable policy (signed + numeric threshold) takes precedence.
    if usable:
        return usable[0]
    # Structurally OK but unsigned: MISSING signature.
    ok_unsigned = next((c for c in candidates if c.status == POLICY_OK), None)
    if ok_unsigned is not None:
        return ActionabilityPolicy(status=POLICY_MISSING, policy_id=ok_unsigned.policy_id,
                                   version=ok_unsigned.version, min_remaining_r=ok_unsigned.min_remaining_r,
                                   source_path=ok_unsigned.source_path,
                                   reason="policy is unsigned (signed_by is null)")
    return candidates[0]
