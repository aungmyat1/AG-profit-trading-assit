"""Campaign domain object and Campaign Risk Controller.

campaign_id format: {SYMBOL}-{SESSION_PAIR}-{YYYYMMDD}-{DIRECTION}
  e.g. EURUSD-ASIAN_LONDON-20260910-LONG
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from . import STRATEGY_ID, STRATEGY_VERSION
from .setups import SetupModel
from .state_machine import Event, State, entries_permitted, transition


class CampaignStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    RISK_EXHAUSTED = "RISK_EXHAUSTED"
    COMPLETE = "COMPLETE"


def build_campaign_id(symbol: str, session_pair: str, trading_date, direction: str) -> str:
    date_str = trading_date.strftime("%Y%m%d") if hasattr(trading_date, "strftime") else str(trading_date)
    return f"{symbol}-{session_pair}-{date_str}-{direction}"


@dataclass
class CampaignEntry:
    setup_model: SetupModel
    entry_time: object
    risk_pct: float
    entry_price: float
    stop_price: float
    realized_r: Optional[float] = None
    realized_cash: Optional[float] = None


@dataclass
class Campaign:
    campaign_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    session_pair: str
    trading_date: object
    direction: str
    regime: str
    status: CampaignStatus = CampaignStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    state: State = State.CAMPAIGN_ACTIVE
    entries: List[CampaignEntry] = field(default_factory=list)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def open_risk_pct(self) -> float:
        return sum(e.risk_pct for e in self.entries)

    @property
    def realized_r(self) -> float:
        return sum(e.realized_r for e in self.entries if e.realized_r is not None)

    @property
    def realized_cash(self) -> float:
        return sum(e.realized_cash for e in self.entries if e.realized_cash is not None)

    @property
    def setup_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self.entries:
            counts[e.setup_model.value] = counts.get(e.setup_model.value, 0) + 1
        return counts


def new_campaign(symbol: str, session_pair: str, trading_date, direction: str, regime: str, as_of: datetime) -> Campaign:
    return Campaign(
        campaign_id=build_campaign_id(symbol, session_pair, trading_date, direction),
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
        symbol=symbol, session_pair=session_pair, trading_date=trading_date, direction=direction,
        regime=regime, created_at=as_of, updated_at=as_of,
    )


@dataclass(frozen=True)
class RiskAllocationResult:
    accepted: bool
    reason: str
    risk_pct: Optional[float]


def allocate_risk(campaign: Campaign, setup_model: SetupModel, config: dict) -> RiskAllocationResult:
    """Campaign Risk Controller.

    Enforces, in order:
      1. entries_permitted(campaign.state) -- no add after invalidation/expiry/terminal.
      2. max_total_entries_per_campaign (authoritative hard cap -- NOT the sum of
         per-setup maxima; e.g. S1+S2+S3+S3 = 4 entries is rejected here even though
         each individual setup's own per-setup max (S1<=1, S2<=1, S3<=2) is respected,
         because the total (4) exceeds campaign.max_entries (3)).
      3. per-setup max occurrences (setup_limits.*_max_per_campaign).
      4. campaign_max_total_risk_pct hard cap (1.0% default), with remaining-risk
         clamping: the target allocation for this setup_model is clamped down to
         whatever room remains under the cap (never allocated above the target, and
         never allowed to push total risk over the cap).
      5. reject if the clamped remaining risk is below min_meaningful_risk_pct
         (campaign.min_meaningful_risk_pct) -- a trade sized at a dust-level risk is
         rejected outright rather than silently taken.
    """
    campaign_cfg = config["campaign"]
    max_entries = int(campaign_cfg["max_entries"])
    max_total_risk = float(campaign_cfg["maximum_total_risk_pct"])
    min_meaningful = float(campaign_cfg["min_meaningful_risk_pct"])
    setup_limits = config["setup_limits"]
    risk_allocation = config["risk_allocation"]

    if not entries_permitted(campaign.state):
        return RiskAllocationResult(False, "CAMPAIGN_NOT_ACCEPTING_ENTRIES", None)

    if campaign.entry_count >= max_entries:
        return RiskAllocationResult(False, "MAX_TOTAL_ENTRIES_PER_CAMPAIGN_REACHED", None)

    per_setup_max = int(setup_limits[f"{setup_model.value.split('_')[0]}_max_per_campaign"])
    current_setup_count = campaign.setup_counts.get(setup_model.value, 0)
    if current_setup_count >= per_setup_max:
        return RiskAllocationResult(False, "SETUP_MAX_OCCURRENCES_REACHED", None)

    if campaign_cfg.get("block_new_entries_after_realized_r_enabled", False):
        threshold = float(campaign_cfg["block_new_entries_after_realized_r_lte"])
        if campaign.realized_r <= threshold:
            return RiskAllocationResult(False, "REALIZED_R_LOSS_BLOCK", None)

    target_pct = float(risk_allocation[setup_model.value.split("_")[0]])
    remaining_room = max_total_risk - campaign.open_risk_pct
    if remaining_room <= 0:
        return RiskAllocationResult(False, "RISK_CAP_EXHAUSTED", None)

    clamped_pct = min(target_pct, remaining_room)
    if clamped_pct < min_meaningful:
        return RiskAllocationResult(False, "MIN_MEANINGFUL_RISK_UNAVAILABLE", None)

    return RiskAllocationResult(True, "OK", clamped_pct)


def apply_entry(campaign: Campaign, setup_model: SetupModel, risk_pct: float, entry_time, entry_price: float, stop_price: float) -> Campaign:
    campaign.entries.append(CampaignEntry(setup_model, entry_time, risk_pct, entry_price, stop_price))
    campaign.updated_at = entry_time
    if campaign.state == State.CAMPAIGN_ACTIVE and campaign.entry_count > 1:
        campaign.state = transition(campaign.state, Event.ADDITIONAL_ENTRY_ACCEPTED)
    return campaign


def invalidate_campaign(campaign: Campaign, reason_event: Event, as_of) -> Campaign:
    campaign.state = transition(campaign.state, reason_event)
    campaign.updated_at = as_of
    status_map = {
        Event.STRUCTURE_INVALIDATED: CampaignStatus.INVALIDATED,
        Event.SESSION_WINDOW_EXPIRED: CampaignStatus.SESSION_EXPIRED,
        Event.RISK_BUDGET_EXHAUSTED: CampaignStatus.RISK_EXHAUSTED,
        Event.HARD_LOSS_STOP: CampaignStatus.INVALIDATED,
        Event.BAD_DATA: CampaignStatus.INVALIDATED,
        Event.CAMPAIGN_CLOSED: CampaignStatus.COMPLETE,
    }
    campaign.status = status_map.get(reason_event, campaign.status)
    return campaign
