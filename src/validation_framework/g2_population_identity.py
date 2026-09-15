"""G2 deterministic population identity (WP-SV3 / WORK PACKAGE D; hardened per Cycle-1
remediation V2 "G2 IDENTITY HARDENING").

Reuses the identity fields already hand-computed for
ST_SESSION_SWEEP_CONTINUATION_V1's HYP_002 population_manifest.json (strategy_id,
strategy_version, git_sha, dataset_fingerprint, symbol, timeframes, window,
config_hash) and formalizes them into one deterministic, pure hashing function. This
module does not generate populations, run replay, or touch any dataset -- it only
computes/verifies the identity hash over governed inputs a caller already has.

V2 hardening adds `preregistration_hash` and `validation_methodology_id` to the bound
identity fields (P1-05's HYP_001 GBPUSD lineage mismatch is exactly the failure mode
this closes: a population silently carrying a DIFFERENT preregistration's identity
while looking otherwise valid). A population computed under a superseded
preregistration hash, or under a different validation-methodology version, now
produces a provably different `population_hash` -- never the same one by coincidence.

No optimization, no search, no I/O.
"""
from __future__ import annotations

import hashlib
import json
from typing import Sequence

from .svos_contracts import PopulationFingerprint

_IDENTITY_FIELDS = (
    "strategy_id",
    "strategy_version",
    "hypothesis_id",
    "preregistration_hash",
    "validation_methodology_id",
    "git_sha",
    "dataset_fingerprint",
    "symbol",
    "timeframes",
    "window_start",
    "window_end",
    "timezone_session_contract_hash",
    "config_hash",
)


def compute_population_identity(
    strategy_id: str,
    strategy_version: str,
    hypothesis_id: str,
    preregistration_hash: str,
    validation_methodology_id: str,
    git_sha: str,
    dataset_fingerprint: str,
    symbol: str,
    timeframes: Sequence[str],
    window_start: str,
    window_end: str,
    timezone_session_contract_hash: str,
    config_hash: str,
) -> str:
    """Deterministic sha256 hex digest over exactly the governed-identity fields above
    (`_IDENTITY_FIELDS`), canonicalized as sorted-key JSON so field order never affects
    the hash. Same inputs -> same hash, always; any single differing input (including a
    single differing timeframe, a superseded `preregistration_hash`, or a bumped
    `validation_methodology_id`) -> a different hash -- verified directly by
    tests/test_g2_population_identity.py rather than merely asserted here."""
    payload = {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "hypothesis_id": hypothesis_id,
        "preregistration_hash": preregistration_hash,
        "validation_methodology_id": validation_methodology_id,
        "git_sha": git_sha,
        "dataset_fingerprint": dataset_fingerprint,
        "symbol": symbol,
        "timeframes": list(timeframes),
        "window_start": window_start,
        "window_end": window_end,
        "timezone_session_contract_hash": timezone_session_contract_hash,
        "config_hash": config_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_population_identity(fingerprint: PopulationFingerprint) -> bool:
    """True iff `fingerprint.population_hash` matches a fresh recomputation from its own
    other fields -- catches a manually-edited or corrupted manifest, a
    preregistration-hash swap, or a methodology-version drift, rather than trusting a
    stored hash at face value."""
    recomputed = compute_population_identity(
        fingerprint.strategy_id,
        fingerprint.strategy_version,
        fingerprint.hypothesis_id,
        fingerprint.preregistration_hash,
        fingerprint.validation_methodology_id,
        fingerprint.git_sha,
        fingerprint.dataset_fingerprint,
        fingerprint.symbol,
        fingerprint.timeframes,
        fingerprint.window_start,
        fingerprint.window_end,
        fingerprint.timezone_session_contract_hash,
        fingerprint.config_hash,
    )
    return recomputed == fingerprint.population_hash
