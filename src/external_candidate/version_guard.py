"""Immutable-candidate-versioning guard (mission section 12).

Pure function, no filesystem/registry coupling of its own -- same discipline as
`validation_framework/economic_gate.py` (a pure evaluator over caller-supplied
state, not a second governance store). Callers that already know a strategy's
recorded evidence-bearing (strategy_id, version) -> config_fingerprint bindings
(e.g. a future evidence ledger, or today simply "no such binding exists yet")
supply them via `known_version_fingerprints`; this module invents no persistent
store of its own -- doing so without owner authorization would create a second,
divergence-prone source of truth, exactly the failure WP0's proposal-identity
reconciliation already flagged once in this repository.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class VersionGuardResult:
    ok: bool
    reason: str


def check_version_mutation(
    strategy_id: str,
    candidate_version: str,
    candidate_config_hash: str,
    known_version_fingerprints: Optional[Mapping[Tuple[str, str], str]] = None,
) -> VersionGuardResult:
    """Rejects admission of a candidate that would mutate an already-evaluated
    strategy version in place (mission section 12). `known_version_fingerprints`
    maps (strategy_id, semantic_version) -> the config_fingerprint that version's
    existing evidence was produced under, for every version that already has
    evidence on file. A candidate whose (strategy_id, candidate_version) key
    already exists there with a DIFFERENT fingerprint is a version mutation and is
    rejected; an identical fingerprint is a harmless re-submission and is allowed
    (not a mutation -- nothing about the evaluated version would change)."""
    known = known_version_fingerprints or {}
    key = (strategy_id, candidate_version)
    if key not in known:
        return VersionGuardResult(True, "no existing evidence recorded under this (strategy_id, version)")

    existing_fingerprint = known[key]
    if existing_fingerprint == candidate_config_hash:
        return VersionGuardResult(
            True, "identical config fingerprint already recorded under this version -- re-submission, not mutation"
        )
    return VersionGuardResult(
        False,
        f"{strategy_id} v{candidate_version} already has evidence recorded under config_fingerprint "
        f"{existing_fingerprint!r}; incoming candidate has a different fingerprint "
        f"{candidate_config_hash!r} -- rules/parameters changed under an already-evaluated version. "
        "A rule/parameter/session/entry/stop/target change requires a NEW semantic version.",
    )
