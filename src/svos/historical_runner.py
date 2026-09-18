"""Canonical historical validation runner contract (P3).

REUSE: metric computation delegates to performance.calculator.compute_trade_metrics
(no competing metric definition); hashing delegates to post_asian_pilot.fingerprint.
The strategy implementation used for historical validation must be the SAME canonical
strategy authority used by forward operation -- the runner records which replay
entrypoint produced the occurrences (`HistoricalValidationRequest.replay_adapter`) and
refuses to fabricate occurrences itself. Adapters may change the DATA SOURCE, never the
strategy semantics (see adapters/ssc.py for the SSC proof).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence, Tuple

from performance.calculator import compute_trade_metrics
from performance.models import ResolvedTradeSample, TradeMetrics
from post_asian_pilot.fingerprint import fingerprint

_EMPTY_HASH_ERROR = "dataset/friction fingerprint must be present -- refuse to run on unadmitted data"


@dataclass(frozen=True)
class AdmittedDataset:
    dataset_id: str
    symbol: str
    timeframe: str
    utc_start: str
    utc_end: str
    fingerprint: str  # sha256 over the immutable dataset package
    hashes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FrictionContractRef:
    contract_id: str
    contract_hash: str  # sha256 over the admitted friction contract


@dataclass(frozen=True)
class HistoricalValidationRequest:
    strategy_id: str
    strategy_version: str
    dataset: AdmittedDataset
    friction_contract: FrictionContractRef
    replay_adapter: str  # fully-qualified canonical replay entrypoint used


@dataclass(frozen=True)
class HistoricalOccurrence:
    """One immutable historical outcome occurrence. `net_R`/`friction_R` are None when
    costs were not modeled -- never silently rendered as zero downstream."""

    occurrence_id: str
    symbol: str
    session: str
    direction: str
    setup: str
    exit_path: str
    outcome: str
    gross_R: float
    friction_R: float
    net_R: float
    cost_status: str
    evidence_hash: str = ""


@dataclass(frozen=True)
class HistoricalValidationResult:
    request: HistoricalValidationRequest
    occurrences: Tuple[HistoricalOccurrence, ...]
    metrics: TradeMetrics
    decomposition: Mapping[str, TradeMetrics]
    evidence_hashes: Mapping[str, str]


def _as_sample(o: HistoricalOccurrence, request: HistoricalValidationRequest) -> ResolvedTradeSample:
    return ResolvedTradeSample(
        source_record_id=o.occurrence_id,
        source_path=f"svos.historical_runner:{request.replay_adapter}",
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        symbol=o.symbol,
        cycle=o.session,
        resolved_at=None,
        gross_R=o.gross_R,
        net_R=o.net_R,
        cost_status=o.cost_status,
        outcome=o.outcome,
    )


def _decompose(
    occurrences: Sequence[HistoricalOccurrence], request: HistoricalValidationRequest, dimension: str
) -> Mapping[str, TradeMetrics]:
    buckets: dict[str, list[HistoricalOccurrence]] = {}
    for o in occurrences:
        key = getattr(o, dimension)
        buckets.setdefault(key, []).append(o)
    return {
        key: compute_trade_metrics([_as_sample(o, request) for o in group])
        for key, group in sorted(buckets.items())
    }


def _occurrence_hash(o: HistoricalOccurrence) -> str:
    return fingerprint(
        {
            "occurrence_id": o.occurrence_id,
            "symbol": o.symbol,
            "session": o.session,
            "direction": o.direction,
            "setup": o.setup,
            "exit_path": o.exit_path,
            "outcome": o.outcome,
            "gross_R": o.gross_R,
            "friction_R": o.friction_R,
            "net_R": o.net_R,
            "cost_status": o.cost_status,
        }
    )


def run_historical_validation(
    request: HistoricalValidationRequest,
    occurrences: Sequence[HistoricalOccurrence],
) -> HistoricalValidationResult:
    """Deterministic, pure. Validates dataset/friction identity (fail-closed), freezes
    occurrences (tuple, immutable), computes metrics + decomposition + evidence hashes.
    The caller supplies occurrences produced by the canonical replay adapter; this
    function performs no data loading and no strategy evaluation of its own."""
    if not request.dataset.fingerprint:
        raise ValueError(_EMPTY_HASH_ERROR)
    if not request.friction_contract.contract_hash:
        raise ValueError(_EMPTY_HASH_ERROR)

    frozen = tuple(occurrences)
    hashed = tuple(
        HistoricalOccurrence(
            occurrence_id=o.occurrence_id, symbol=o.symbol, session=o.session,
            direction=o.direction, setup=o.setup, exit_path=o.exit_path, outcome=o.outcome,
            gross_R=o.gross_R, friction_R=o.friction_R, net_R=o.net_R,
            cost_status=o.cost_status, evidence_hash=_occurrence_hash(o),
        )
        for o in frozen
    )

    metrics = compute_trade_metrics([_as_sample(o, request) for o in hashed])

    decomposition: dict[str, TradeMetrics] = {}
    for dimension in ("symbol", "session", "direction", "setup", "exit_path"):
        decomposition.update({f"by_{dimension}": _decompose(hashed, request, dimension)})

    evidence_hashes = {
        "dataset_fingerprint": request.dataset.fingerprint,
        "friction_contract_hash": request.friction_contract.contract_hash,
        "population_hash": fingerprint([o.evidence_hash for o in hashed]),
    }

    return HistoricalValidationResult(
        request=request,
        occurrences=hashed,
        metrics=metrics,
        decomposition=decomposition,
        evidence_hashes=evidence_hashes,
    )
