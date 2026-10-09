"""R6B default-deny permissions for the regeneration publisher (AG_REGEN_PERMISSIONS_V1).

Every side effect the publisher can have on GitHub is one ACTION below. An action runs only if
``config/governance/regen_permissions.json`` lists it in ``allow``. A missing, unreadable or
invalid config (wrong schema, non-list ``allow``, unknown action name) denies everything.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "AG_REGEN_PERMISSIONS_V1"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "governance" / "regen_permissions.json"
ACTIONS = frozenset({
    "bootstrap_push",        # push the empty bootstrap commit before the PR exists (REG-REGEN-BOOTSTRAP)
    "push_regen_branch",     # fast-forward push of generated content to regen/generated-files-<sha>
    "create_pr",             # open the draft regeneration PR
    "close_superseded_pr",   # comment on and close a superseded bot PR (REG-REGEN-STALE-CLOSE)
    "dispatch_ci",           # dispatch ci.yml for the bot branch head
})


class PermissionDenied(RuntimeError):
    pass


class Permissions:
    def __init__(self, allowed=frozenset(), error: str | None = None):
        self.allowed = frozenset(allowed)
        self.error = error

    def allows(self, action: str) -> bool:
        if action not in ACTIONS:
            return False
        return self.error is None and action in self.allowed

    def require(self, action: str) -> None:
        if not self.allows(action):
            why = self.error or ("unknown action" if action not in ACTIONS else "not in allowlist")
            raise PermissionDenied(f"REGEN_PERMISSION_DENIED:{action} ({why})")


def parse(raw) -> Permissions:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        return Permissions(error="config schema invalid")
    allow = raw.get("allow")
    if not isinstance(allow, list) or not all(isinstance(a, str) for a in allow):
        return Permissions(error="config allow is not a list of action names")
    unknown = sorted(set(allow) - ACTIONS)
    if unknown:
        return Permissions(error="config names unknown actions: " + ",".join(unknown))
    return Permissions(allow)


def load(path: Path | str | None = None) -> Permissions:
    try:
        raw = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Permissions(error=f"config unavailable: {type(exc).__name__}")
    return parse(raw)
