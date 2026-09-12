"""Minimum reusable OOS evaluator (mission section 19).

Takes a frozen candidate identity plus an explicit OOS dataset partition and a set
of already-resolved trade samples restricted to that partition, and produces
canonical evidence. It does not run a backtest and does not touch strategy code --
the resolved samples for the OOS window are supplied by whatever candidate-specific
replay/outcome-resolution pipeline already produced them (out of scope for this
infrastructure layer, same division of responsibility as
`performance.calculator.compute_trade_metrics` vs. the outcome resolvers that feed
it). No optimization occurs here: the same frozen samples are aggregated, not
searched over.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from performance.calculator import compute_trade_metrics
from performance.models import ResolvedTradeSample, TradeMetrics
from post_asian_pilot.fingerprint import fingerprint

from .models import DatasetPartition


@dataclass(frozen=True)
class OOSEvidence:
    dataset_identity: str
    strategy_id: str
    strategy_version: str
    candidate_id: str
    metrics: TradeMetrics
    evidence_fingerprint: str


def evaluate_oos(
    strategy_id: str,
    strategy_version: str,
    candidate_id: str,
    oos_dataset: DatasetPartition,
    resolved_samples: Sequence[ResolvedTradeSample],
) -> OOSEvidence:
    metrics = compute_trade_metrics(resolved_samples)
    evidence_fingerprint = fingerprint({
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "candidate_id": candidate_id,
        "dataset_fingerprint": oos_dataset.dataset_fingerprint,
        "sample_size": metrics.sample_size,
        "net_total_R": metrics.net_total_R,
        "gross_total_R": metrics.gross_total_R,
    })
    return OOSEvidence(
        dataset_identity=oos_dataset.dataset_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        candidate_id=candidate_id,
        metrics=metrics,
        evidence_fingerprint=evidence_fingerprint,
    )
