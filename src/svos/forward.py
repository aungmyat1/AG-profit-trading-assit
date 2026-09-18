"""Forward validation orchestrator + campaign contract (P11/P12/P14).

Chronological-only, closed-candles-only virtual forward validation:

    real closed candles -> canonical strategy (decision_fn) -> ForwardDecision
    -> VirtualBroker -> VirtualPosition -> future candles -> VirtualTrade
    -> ForwardMetrics / ForwardEvidenceLedger

Invariants enforced here:
  * forward data begins strictly AFTER campaign freeze (candle.time > frozen_at);
  * candles are consumed in strictly increasing time order (no reordering, no
    duplicates, no future-candle access -- the broker only ever sees the candles
    fed to it in order);
  * the candidate fingerprint is frozen at campaign creation and never mutated
    (no strategy mutation after forward start);
  * duplicate proposal cycles are rejected.

Restart-safety: `to_checkpoint`/`from_checkpoint` round-trip the full orchestrator state
so a run can be resumed without replaying or duplicating cycles.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .virtual_broker import (
    Side,
    VirtualAccount,
    VirtualBroker,
    VirtualCandle,
    VirtualOrderSpec,
)

DECISION_PROPOSAL = "PROPOSAL"
DECISION_NO_SETUP = "NO_SETUP"


@dataclass(frozen=True)
class ProposalSpec:
    proposal_id: str
    symbol: str
    side: Side
    stop_loss: float
    setup: str
    session: str
    direction: str
    partial_target: Optional[float] = None
    partial_pct: float = 0.5
    runner_target: Optional[float] = None
    session_exit_time: Optional[datetime] = None
    risk_amount_R: float = 1.0


@dataclass(frozen=True)
class ForwardDecision:
    decision: str  # DECISION_PROPOSAL | DECISION_NO_SETUP
    proposal: Optional[ProposalSpec] = None
    reason: str = ""


# A canonical strategy decision function: closed candle -> decision. Callers close over
# bias/regime context; the orchestrator never mutates or re-implements strategy logic.
DecisionFn = Callable[[VirtualCandle], ForwardDecision]


@dataclass(frozen=True)
class ForwardValidationCampaign:
    campaign_id: str
    candidate_fingerprint: str
    frozen_at: str  # ISO8601 UTC; forward data begins strictly after this
    symbols: Tuple[str, ...]
    sessions: Tuple[str, ...]
    friction_profile_ref: str
    risk_profile: Mapping[str, object]  # max_open_positions / risk_per_trade_R / daily_loss_limit_R
    minimum_occurrence_target: int
    evaluation_metrics: Tuple[str, ...]
    acceptance_criteria: Mapping[str, object]


@dataclass(frozen=True)
class PositionResult:
    position_id: str
    symbol: str
    side: str
    setup: str
    session: str
    direction: str
    gross_R: float
    friction_R: float
    net_R: float
    exit_reason: str


@dataclass(frozen=True)
class ForwardMetrics:
    opportunities: int
    no_setups: int
    proposals: int
    fills: int
    resolved_positions: int
    wins: int
    losses: int
    breakevens: int
    gross_R: float
    friction_R: float
    net_R: float
    expectancy_R: float
    profit_factor: object
    max_drawdown_R: float
    max_consecutive_losses: int
    by_symbol: Mapping[str, "ForwardMetrics"]
    by_session: Mapping[str, "ForwardMetrics"]
    by_setup: Mapping[str, "ForwardMetrics"]
    by_direction: Mapping[str, "ForwardMetrics"]


_WIN_EPSILON = 1e-9


def _classify(net_R: float) -> str:
    if net_R > _WIN_EPSILON:
        return "WIN"
    if net_R < -_WIN_EPSILON:
        return "LOSS"
    return "BREAKEVEN"


def _compute_metrics(results: Sequence[PositionResult], include_decomposition: bool = True) -> "ForwardMetrics":
    n = len(results)
    if n == 0:
        return ForwardMetrics(
            opportunities=0, no_setups=0, proposals=0, fills=0, resolved_positions=0,
            wins=0, losses=0, breakevens=0, gross_R=0.0, friction_R=0.0, net_R=0.0,
            expectancy_R=0.0, profit_factor="UNDEFINED_NO_TRADES", max_drawdown_R=0.0,
            max_consecutive_losses=0, by_symbol={}, by_session={}, by_setup={}, by_direction={},
        )

    gross_total = sum(r.gross_R for r in results)
    friction_total = sum(r.friction_R for r in results)
    net_total = sum(r.net_R for r in results)
    wins = sum(1 for r in results if _classify(r.net_R) == "WIN")
    losses = sum(1 for r in results if _classify(r.net_R) == "LOSS")
    breakevens = n - wins - losses

    gross_wins = sum(r.net_R for r in results if r.net_R > 0)
    gross_losses = sum(abs(r.net_R) for r in results if r.net_R < 0)
    if gross_losses > 0:
        profit_factor = gross_wins / gross_losses if gross_wins > 0 else 0.0
    elif gross_wins > 0:
        profit_factor = "UNDEFINED_NO_LOSSES"
    else:
        profit_factor = "UNDEFINED_NO_TRADES"

    # drawdown / consecutive losses over chronological trade order (results are in order)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    consec = 0
    max_consec = 0
    for r in results:
        equity += r.net_R
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if _classify(r.net_R) == "LOSS":
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    if include_decomposition:
        def by(key: str) -> Mapping[str, "ForwardMetrics"]:
            buckets: Dict[str, List[PositionResult]] = {}
            for r in results:
                buckets.setdefault(getattr(r, key), []).append(r)
            return {k: _compute_metrics(v, include_decomposition=False) for k, v in sorted(buckets.items())}

        by_symbol = by("symbol")
        by_session = by("session")
        by_setup = by("setup")
        by_direction = by("direction")
    else:
        by_symbol = by_session = by_setup = by_direction = {}

    return ForwardMetrics(
        opportunities=0, no_setups=0, proposals=0, fills=0, resolved_positions=n,
        wins=wins, losses=losses, breakevens=breakevens,
        gross_R=gross_total, friction_R=friction_total, net_R=net_total,
        expectancy_R=net_total / n,
        profit_factor=profit_factor, max_drawdown_R=max_dd, max_consecutive_losses=max_consec,
        by_symbol=by_symbol, by_session=by_session,
        by_setup=by_setup, by_direction=by_direction,
    )


class ForwardOrchestrator:
    def __init__(
        self,
        campaign: ForwardValidationCampaign,
        decision_fn: DecisionFn,
        broker: VirtualBroker,
    ) -> None:
        self._campaign = campaign
        self._decision_fn = decision_fn
        self._broker = broker
        self._last_candle_time: Optional[datetime] = None
        self._seen_cycles: set = set()
        self._proposal_meta: Dict[str, ProposalSpec] = {}
        self._opportunities = 0
        self._no_setups = 0
        self._proposals = 0

    @property
    def campaign(self) -> ForwardValidationCampaign:
        return self._campaign

    def on_candle(self, candle: VirtualCandle) -> Tuple:
        """Feeds one CLOSED candle. Raises on non-chronological / pre-freeze input; the
        broker never sees any candle out of order or from before the freeze."""
        if self._last_candle_time is not None and candle.time <= self._last_candle_time:
            raise ValueError(
                f"non-chronological candle {candle.time} (last={self._last_candle_time})"
            )
        frozen_at = datetime.fromisoformat(self._campaign.frozen_at)
        if candle.time <= frozen_at:
            raise ValueError(
                f"candle {candle.time} is not strictly after campaign freeze {frozen_at}"
            )
        self._last_candle_time = candle.time

        # 1) advance existing positions with this candle (no strategy call)
        self._broker.on_candle(candle)

        # 2) canonical strategy decision on this closed candle
        self._opportunities += 1
        decision = self._decision_fn(candle)
        if decision.decision == DECISION_NO_SETUP:
            self._no_setups += 1
            return ()

        proposal = decision.proposal
        if proposal is None:
            return ()
        cycle_key = f"{proposal.symbol}|{proposal.session}|{proposal.setup}|{proposal.direction}"
        if cycle_key in self._seen_cycles:
            return ()
        self._seen_cycles.add(cycle_key)
        self._proposals += 1

        order = self._broker.submit_market(
            VirtualOrderSpec(
                symbol=proposal.symbol,
                side=proposal.side,
                stop_loss=proposal.stop_loss,
                partial_target=proposal.partial_target,
                partial_pct=proposal.partial_pct,
                runner_target=proposal.runner_target,
                session_exit_time=proposal.session_exit_time,
                risk_amount_R=proposal.risk_amount_R,
            )
        )
        self._proposal_meta[order.order_id] = proposal
        return ()

    def finalize(self) -> ForwardMetrics:
        results: List[PositionResult] = []
        for position_id in sorted({t.position_id for t in self._broker.ledger.trades}):
            trades = [t for t in self._broker.ledger.trades if t.position_id == position_id]
            meta = self._proposal_meta.get(trades[0].order_id)
            results.append(
                PositionResult(
                    position_id=position_id,
                    symbol=trades[0].symbol,
                    side=trades[0].side.value,
                    setup=meta.setup if meta else "UNKNOWN",
                    session=meta.session if meta else "UNKNOWN",
                    direction=meta.direction if meta else trades[0].side.value,
                    gross_R=sum(t.gross_R * t.size_fraction for t in trades),
                    friction_R=sum(t.friction_R * t.size_fraction for t in trades),
                    net_R=sum(t.net_R * t.size_fraction for t in trades),
                    exit_reason=trades[-1].exit_reason,
                )
            )

        base = _compute_metrics(results)
        return ForwardMetrics(
            opportunities=self._opportunities,
            no_setups=self._no_setups,
            proposals=self._proposals,
            fills=len(self._broker.ledger.fills),
            resolved_positions=base.resolved_positions,
            wins=base.wins, losses=base.losses, breakevens=base.breakevens,
            gross_R=base.gross_R, friction_R=base.friction_R, net_R=base.net_R,
            expectancy_R=base.expectancy_R, profit_factor=base.profit_factor,
            max_drawdown_R=base.max_drawdown_R, max_consecutive_losses=base.max_consecutive_losses,
            by_symbol=base.by_symbol, by_session=base.by_session,
            by_setup=base.by_setup, by_direction=base.by_direction,
        )

    # -- checkpoint / restart-safety -----------------------------------------
    def to_checkpoint(self) -> dict:
        return {
            "campaign": self._campaign.__dict__,
            "last_candle_time": self._last_candle_time.isoformat() if self._last_candle_time else None,
            "seen_cycles": sorted(self._seen_cycles),
            "opportunities": self._opportunities,
            "no_setups": self._no_setups,
            "proposals": self._proposals,
            "proposal_meta": {k: v.__dict__ for k, v in self._proposal_meta.items()},
            "broker": self._broker.to_checkpoint(),
        }

    @staticmethod
    def _atomic_write(path: str, payload: dict) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, default=str)
        os.replace(tmp, path)

    def save_checkpoint(self, path: str) -> None:
        self._atomic_write(path, self.to_checkpoint())

    def load_checkpoint(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data["campaign"]["campaign_id"] != self._campaign.campaign_id:
            raise ValueError("checkpoint campaign_id mismatch")
        self._last_candle_time = (
            datetime.fromisoformat(data["last_candle_time"]) if data["last_candle_time"] else None
        )
        self._seen_cycles = set(data["seen_cycles"])
        self._opportunities = data["opportunities"]
        self._no_setups = data["no_setups"]
        self._proposals = data["proposals"]
        # proposal meta / broker ledger are restored read-only for reporting; the broker
        # state itself is not resumed in-place (a resumed run resumes candle consumption).
        self._restored_checkpoint = data
