"""Canonical setup/proposal evidence record.

Reuses the project's existing evidence vocabulary where compatible:
  - config_hash          -- see config.compute_config_hash (sha256 over the strategy
                             YAML, same pattern AG-EGSVF's adapters expect for
                             DETERMINISM evidence).
  - cost_status/friction  -- src/performance style KNOWN/MODELED/UNAVAILABLE +
                             NOT_EVALUATED convention (performance/models.py).
  - git_commit            -- resolved via `git rev-parse HEAD`, same identity concept
                             ST_ASIAN_SWEEP_5R_V1's release-identity evidence already
                             uses (docs/status/..._RELEASE_IDENTITY_REMEDIATION...).

No pre-existing canonical trade/proposal dataclass in this repo was found to be
schema-compatible with a *campaign*-shaped record (campaign_id, setup_model, BOS/FVG/
confirmation-score evidence, friction, config/dataset/git identity all on one row) --
`proposals.models`/`validation_framework.models` model lifecycle/gate evidence, not a
per-setup trade proposal shape, and ST_ASIAN_SWEEP_5R_V1's own outcome-resolution
records (artifacts/outcome_resolution/records/*.json) are strategy-specific to that
engine's own fields. Rather than force this new engine's genuinely different shape
(campaign_id, setup_model, BOS/FVG/score evidence) into an incompatible schema, this
module defines the narrowest compatible ADDITION: a plain, JSON-serializable dataclass
carrying every field the spec requires, so it can be trivially consumed by
performance_attribution.py (which DOES reuse performance/calculator.py+models.py) or a
future validation_framework adapter without inventing a second parallel gate/lifecycle
model.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Sequence

from strategy_engine.session.candles import Candle

from . import STRATEGY_ID, STRATEGY_VERSION


def compute_dataset_hash(candles: Sequence[Candle]) -> str:
    """sha256 over the exact ordered candle series used to produce a setup -- so any
    future re-run against the same nominal date range but different underlying data
    (a corrected bar, a different provider) is detectable as a different dataset_hash."""
    payload = [
        {"t": c.time.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close}
        for c in candles
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_git_commit(repo_root: str = ".") -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "UNKNOWN"


@dataclass(frozen=True)
class CanonicalSetupRecord:
    strategy_id: str
    version: str
    application_release: str
    campaign_id: str
    setup_model: str
    symbol: str
    session_pair: str
    direction: str
    decision_timeframe: str
    entry_time: str
    entry_price: float
    stop_price: Optional[float]
    stop_distance: Optional[float]
    targets: Dict[str, Any]
    risk_pct: Optional[float]
    regime: str
    bos_evidence: Dict[str, Any]
    fvg_evidence: Dict[str, Any]
    confirmation_score: Optional[int]
    transaction_friction: Dict[str, Any]
    config_hash: str
    dataset_hash: str
    git_commit: str
    lifecycle_stage: str = "OFFLINE_RESEARCH"
    demo_eligible: bool = False
    demo_authorized: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def build_canonical_setup_record(
    *,
    application_release: str,
    campaign_id: str,
    setup_model: str,
    symbol: str,
    session_pair: str,
    direction: str,
    entry_time: str,
    entry_price: float,
    stop_result,  # stop_engine.StopResult
    targets: Dict[str, Any],
    risk_pct: Optional[float],
    regime: str,
    bos_evidence: Dict[str, Any],
    fvg_evidence: Dict[str, Any],
    confirmation_score: Optional[int],
    friction,  # friction.FrictionEstimate
    config_hash: str,
    dataset_hash: str,
    git_commit: str,
) -> CanonicalSetupRecord:
    return CanonicalSetupRecord(
        strategy_id=STRATEGY_ID,
        version=STRATEGY_VERSION,
        application_release=application_release,
        campaign_id=campaign_id,
        setup_model=setup_model,
        symbol=symbol,
        session_pair=session_pair,
        direction=direction,
        decision_timeframe="M15",
        entry_time=entry_time,
        entry_price=entry_price,
        stop_price=stop_result.stop_price if stop_result else None,
        stop_distance=stop_result.final_stop_distance if stop_result else None,
        targets=targets,
        risk_pct=risk_pct,
        regime=regime,
        bos_evidence=bos_evidence,
        fvg_evidence=fvg_evidence,
        confirmation_score=confirmation_score,
        transaction_friction={
            "spread_pips": friction.spread_pips if friction else None,
            "commission_pips": friction.commission_pips if friction else None,
            "slippage_pips": friction.slippage_pips if friction else None,
            "total_pips": friction.total_pips if friction else None,
            "cost_status": friction.cost_status if friction else "UNAVAILABLE",
        },
        config_hash=config_hash,
        dataset_hash=dataset_hash,
        git_commit=git_commit,
    )
