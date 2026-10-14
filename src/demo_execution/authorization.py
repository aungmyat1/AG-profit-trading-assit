"""Host-local standing DEMO authorization loader (no authorization is shipped).

The committed S1 scope is not authority. A matching, explicit, revocable record
must be supplied by the host. Missing, malformed, revoked, stopped, or mismatched
records block admission.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from demo_execution.scope import ScopePolicy

_DEFAULT_AUTH_PATH = Path.home() / ".config" / "ag-profit-trading" / "standing_demo_authorization.json"
_SCHEMA = "AGP_STANDING_DEMO_AUTHORIZATION_V1"
# A' (N scopes): one host-local file may hold several V1 records, one per exact scope/direction tuple.
_CONTAINER_SCHEMA = "AGP_STANDING_DEMO_AUTHORIZATIONS_V1"
_MATCH_KEYS = ("strategy", "version", "symbol", "session", "branch", "direction")
_REQUIRED_KEYS = frozenset({
    "schema", "strategy", "version", "symbol", "session", "branch", "direction",
    "logic_identity", "granted_at", "revoked_at", "decision_id", "emergency_stop",
})


@dataclass(frozen=True)
class AuthorizationResult:
    authorized: bool
    reason_code: str
    decision_id: Optional[str] = None
    granted_at: Optional[datetime] = None


def _parse_aware_utc(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def resolve_authorization_path(path: Optional[str | Path] = None, *, env_var: str) -> Path:
    """Explicit path, then named host env var, then a user-local path outside the repo."""
    if path is not None:
        selected = Path(path).expanduser()
    else:
        configured = os.environ.get(env_var)
        selected = Path(configured).expanduser() if configured else _DEFAULT_AUTH_PATH
    if not selected.is_absolute():
        raise ValueError("authorization path must be absolute and host-local")
    return selected.resolve()


def validate_standing_authorization(
    record: Mapping[str, Any],
    scope: ScopePolicy,
    ticket: Mapping[str, Any],
    *,
    now_utc: datetime,
) -> AuthorizationResult:
    """Validate the exact authority tuple; no wildcards or inherited permissions."""
    if not isinstance(record, Mapping) or set(record) != _REQUIRED_KEYS or record.get("schema") != _SCHEMA:
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    stop = record.get("emergency_stop")
    if type(stop) is not bool:
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    decision_id = record.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id.strip():
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    granted_at = _parse_aware_utc(record.get("granted_at"))
    if granted_at is None or now_utc.tzinfo is None or now_utc.utcoffset() is None:
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    revoked_at_raw = record.get("revoked_at")
    if revoked_at_raw is not None and _parse_aware_utc(revoked_at_raw) is None:
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    if stop:
        return AuthorizationResult(False, "EMERGENCY_STOP_ENGAGED", decision_id, granted_at)
    if revoked_at_raw is not None:
        return AuthorizationResult(False, "AUTHORIZATION_REVOKED", decision_id, granted_at)
    if granted_at > now_utc.astimezone(timezone.utc):
        return AuthorizationResult(False, "AUTHORIZATION_NOT_YET_VALID", decision_id, granted_at)

    expected = {
        "strategy": scope.strategy_id,
        "version": scope.strategy_version,
        "symbol": scope.symbol,
        "session": scope.session,
        "branch": scope.setup_branch,
        "direction": ticket.get("direction"),
        "logic_identity": scope.logic_identity,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        return AuthorizationResult(False, "AUTHORIZATION_SCOPE_MISMATCH", decision_id, granted_at)
    return AuthorizationResult(True, "STANDING_DEMO_AUTHORIZATION_MATCHED", decision_id, granted_at)


def load_standing_authorization(
    scope: ScopePolicy,
    ticket: Mapping[str, Any],
    *,
    path: Optional[str | Path] = None,
    now_utc: datetime,
) -> AuthorizationResult:
    """Read and validate a host-local JSON record. No sample/grant is committed."""
    try:
        selected = resolve_authorization_path(path, env_var=scope.authorization_path_env)
    except (TypeError, ValueError, OSError):
        return AuthorizationResult(False, "AUTHORIZATION_PATH_INVALID")
    try:
        with selected.open(encoding="utf-8") as stream:
            record = json.load(stream)
    except FileNotFoundError:
        return AuthorizationResult(False, "AUTHORIZATION_MISSING")
    except (OSError, json.JSONDecodeError):
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    if not isinstance(record, dict):
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    if record.get("schema") == _CONTAINER_SCHEMA:
        selected_record = select_container_record(record, scope, ticket)
        if isinstance(selected_record, AuthorizationResult):
            return selected_record
        record = selected_record
    return validate_standing_authorization(record, scope, ticket, now_utc=now_utc)


def select_container_record(container: Mapping[str, Any], scope: ScopePolicy,
                            ticket: Mapping[str, Any]) -> Any:
    """Exactly one record must match the scope tuple and the ticket's direction; none is a scope
    mismatch, several are ambiguous (fail closed). The selected record is then validated in full."""
    records = container.get("records")
    if set(container) != {"schema", "records"} or not isinstance(records, list) \
            or not all(isinstance(r, Mapping) for r in records):
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    want = (scope.strategy_id, scope.strategy_version, scope.symbol, scope.session, scope.setup_branch,
            ticket.get("direction") if isinstance(ticket, Mapping) else None)
    matches = [r for r in records if tuple(r.get(k) for k in _MATCH_KEYS) == want]
    if not matches:
        return AuthorizationResult(False, "AUTHORIZATION_SCOPE_MISMATCH")
    if len(matches) > 1:
        return AuthorizationResult(False, "AUTHORIZATION_INVALID")
    return matches[0]
