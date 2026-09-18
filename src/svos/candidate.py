"""Candidate freeze + CANDIDATE_FINGERPRINT (P7).

A candidate entering robustness / forward validation must freeze its full semantic
identity. `compute_candidate_fingerprint` hashes every frozen field (canonical hasher,
post_asian_pilot.fingerprint) so ANY semantic change yields a new candidate/version.
`freeze_candidate` binds the fingerprint to the frozen record.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from post_asian_pilot.fingerprint import fingerprint


@dataclass(frozen=True)
class CandidateFreeze:
    strategy_id: str
    version: str
    code_config_hash: str
    dataset_role: str
    parameters: Mapping[str, object]
    friction_contract: str
    session_contract: str
    decision_tf: str
    execution_tf: str
    risk_contract: str


@dataclass(frozen=True)
class FrozenCandidate:
    freeze: CandidateFreeze
    fingerprint: str = ""

    @property
    def candidate_id(self) -> str:
        return f"{self.freeze.strategy_id}@{self.freeze.version}:{self.fingerprint[:12]}"

    def verify(self) -> bool:
        return self.fingerprint == compute_candidate_fingerprint(self.freeze)


def compute_candidate_fingerprint(freeze: CandidateFreeze) -> str:
    return fingerprint(
        {
            "strategy_id": freeze.strategy_id,
            "version": freeze.version,
            "code_config_hash": freeze.code_config_hash,
            "dataset_role": freeze.dataset_role,
            "parameters": dict(sorted(freeze.parameters.items())),
            "friction_contract": freeze.friction_contract,
            "session_contract": freeze.session_contract,
            "decision_tf": freeze.decision_tf,
            "execution_tf": freeze.execution_tf,
            "risk_contract": freeze.risk_contract,
        }
    )


def freeze_candidate(freeze: CandidateFreeze) -> FrozenCandidate:
    return FrozenCandidate(freeze=freeze, fingerprint=compute_candidate_fingerprint(freeze))
