"""Narrow, non-mutating bridge from canonical SSC ReplayResult to VD order intent."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from session_sweep_continuation import STRATEGY_ID, STRATEGY_VERSION
from session_sweep_continuation.replay import ReplayResult

from .virtual_exchange import ProposalFixture, ResearchReferenceEntry


class BridgeError(ValueError):
    pass


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BridgeError("decision cutoff must be timezone-aware")
    return value.astimezone(timezone.utc)


def _id(payload):
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class SSCVirtualOrderIntent:
    proposal: ProposalFixture
    strategy_id: str
    strategy_version: str
    session_pair: str
    campaign_id: str
    setup_model: str
    risk_pct: Optional[float]
    target_price: Optional[float]
    m1_lineage_id: Optional[str]
    status: str = "ACTIONABLE"


@dataclass(frozen=True)
class BridgeResult:
    status: str
    reason: str
    intents: Tuple[SSCVirtualOrderIntent, ...] = ()


class SSCToVirtualOrderBridge:
    """Pure adapter. It never fills, sizes, mutates ReplayResult, or calls MT5."""

    def __init__(self, *, strategy_id: str = STRATEGY_ID, strategy_version: str = STRATEGY_VERSION):
        self.strategy_id, self.strategy_version = strategy_id, strategy_version

    def build(self, result: ReplayResult, *, dataset_id: str, decision_event_id: str,
              mi_event_id: Optional[str] = None, m1_lineage_id: Optional[str] = None,
              decision_cutoff: Optional[datetime] = None) -> BridgeResult:
        if not dataset_id or not decision_event_id:
            raise BridgeError("MISSING_DATASET_OR_EVENT_ID")
        if result.symbol == "" or result.regime is None and result.campaign is not None:
            raise BridgeError("INVALID_REPLAY_IDENTITY")
        if not result.accepted_setups:
            reason = "NO_SETUP" if not result.rejected_setups else "REJECTED"
            return BridgeResult(reason, reason)
        if result.campaign is None:
            raise BridgeError("ACTIONABLE_SETUP_WITHOUT_CAMPAIGN")
        campaign_id = result.campaign.campaign_id
        intents = []
        for index, setup in enumerate(result.accepted_setups):
            try:
                entry_time = _utc(datetime.fromisoformat(str(setup["entry_time"])))
                cutoff = _utc(decision_cutoff) if decision_cutoff is not None else entry_time + timedelta(minutes=15)
                direction = setup["direction"]
                entry_price = float(setup["entry_price"])
                stop_price = float(setup["stop_price"])
                outcome = setup.get("outcome") or {}
            except (KeyError, TypeError, ValueError) as exc:
                raise BridgeError("INCOMPLETE_ACTIONABLE_SETUP") from exc
            if direction not in {"LONG", "SHORT"} or stop_price <= 0 or entry_price <= 0:
                raise BridgeError("INVALID_ACTIONABLE_SETUP")
            reference = ResearchReferenceEntry(
                decision_id=decision_event_id, symbol=result.symbol,
                decision_cutoff=cutoff, reference_price=entry_price,
                source_event_id=f"{dataset_id}|{decision_event_id}",
            )
            target = outcome.get("partial_target_price")
            proposal_id = _id({"dataset": dataset_id, "event": decision_event_id,
                               "campaign": campaign_id, "setup_index": index,
                               "setup": setup})
            proposal = ProposalFixture(
                proposal_id, result.symbol, direction, cutoff, dataset_id,
                decision_event_id, reference, stop_price=stop_price,
                target_price=float(target) if target is not None else None,
            )
            intents.append(SSCVirtualOrderIntent(
                proposal, self.strategy_id, self.strategy_version,
                result.session_pair, campaign_id, setup.get("setup_model", "UNRESOLVED"),
                setup.get("risk_pct"), target, m1_lineage_id,
            ))
        return BridgeResult("ACTIONABLE", "ACTIONABLE_SETUP", tuple(intents))
