"""Host magic registry: the reserved S1 magic must never equal a magic in use on the host.

The reserved magic is resolved from the registered strategy contract by ``demo_execution.scope``;
it is never a runtime literal here. What this module owns is the other half of that check: the
committed list of magics already in use on the VT Markets DEMO host (other EAs, and the
unattributed manual/local-API orders that carry magic 0). A collision makes "own position" and
"foreign position" indistinguishable for the risk caps, so scope loading fails closed instead of
admitting an order under a shared magic.

Pure: no MT5 import, no broker read. Re-verification against the live terminal is a host step.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_MAGIC_REGISTRY_PATH = _REPO_ROOT / "config" / "demo_execution_host_magics.yaml"
SCHEMA = "AGP_C14_HOST_MAGIC_REGISTRY_V1"

HOST_MAGIC_COLLISION = "STRATEGY_MAGIC_COLLIDES_WITH_HOST"
HOST_MAGIC_REGISTRY_UNAVAILABLE = "HOST_MAGIC_REGISTRY_UNAVAILABLE"
HOST_MAGIC_REGISTRY_INVALID = "HOST_MAGIC_REGISTRY_INVALID"
STRATEGY_MAGIC_NUMBER_UNAVAILABLE = "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"


class HostMagicRegistryError(ValueError):
    """Missing, unreadable or malformed host magic registry; `reason_code` is safe to surface."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        super().__init__(f"{reason_code}{': ' + detail if detail else ''}")
        self.reason_code = reason_code


def load_host_magics(path: Optional[str | Path] = None) -> tuple[int, ...]:
    """Return the magics in use on the host, in committed order. Never returns an empty tuple.

    Every listed magic must be a non-negative integer and must cite its source; magic 0 must be
    present, because unattributed manual/local-API orders on this account carry it and because 0
    is the MT5 default for "no magic". Anything else fails closed.
    """
    selected = Path(path).expanduser().resolve() if path is not None else HOST_MAGIC_REGISTRY_PATH
    try:
        with selected.open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except FileNotFoundError:
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_UNAVAILABLE, str(selected)) from None
    except (OSError, yaml.YAMLError) as exc:
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_UNAVAILABLE, str(exc)) from None
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, f"schema must be {SCHEMA}")
    if not isinstance(raw.get("observed_at_utc"), str) or not raw["observed_at_utc"].strip():
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, "observed_at_utc is missing")
    entries = raw.get("magics_in_use_on_host")
    if not isinstance(entries, list) or not entries:
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, "magics_in_use_on_host is missing")

    magics: list[int] = []
    for entry in entries:
        value = entry.get("magic") if isinstance(entry, Mapping) else entry
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, f"magic {value!r} is not an integer >= 0")
        if isinstance(entry, Mapping) and not str(entry.get("source") or "").strip():
            raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, f"magic {value} cites no source")
        magics.append(value)
    if len(set(magics)) != len(magics):
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, "a magic is listed more than once")
    if 0 not in magics:
        raise HostMagicRegistryError(HOST_MAGIC_REGISTRY_INVALID, "magic 0 must always be listed")
    return tuple(magics)


def reserved_magic_conflict(magic_number: Any, host_magics: Sequence[int]) -> Optional[str]:
    """Return the blocking reason code for a reserved magic, or None when it is usable."""
    if isinstance(magic_number, bool) or not isinstance(magic_number, int) or magic_number <= 0:
        return STRATEGY_MAGIC_NUMBER_UNAVAILABLE
    if magic_number in tuple(host_magics):
        return HOST_MAGIC_COLLISION
    return None
