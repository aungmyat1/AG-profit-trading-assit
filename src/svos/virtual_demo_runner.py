"""Minimal deterministic end-to-end VD orchestration over already-admitted decisions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, Optional, Tuple

from .ssc_bridge import SSCToVirtualOrderBridge
from .virtual_account import VirtualAccount
from .virtual_ledger import VirtualLedger
from .virtual_time import VirtualMarketFeed
from .virtual_exchange import OHLCM1
from historical_replay.evaluation_context import ReplayEvaluationContext
from session_sweep_continuation.replay import ReplayResult


class RunnerError(ValueError):
    pass


def _hash(v):
    return "sha256:" + hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class VirtualDemoRunIdentity:
    engine_version: str
    mi_release: str
    strategy_id: str
    strategy_version: str
    dataset_id: str
    start: datetime
    end: datetime
    execution_profile: str
    account_profile: str
    contract_versions: Tuple[str, ...]
    fingerprint: str

    @classmethod
    def create(cls, *, dataset_id, start, end, execution_profile="VD_EXECUTION_PROFILE_V1_DRAFT",
               account_profile="VD_ACCOUNT_ENGINEERING_NORMALIZED_1", mi_release="MI_V1_FROZEN",
               strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version="1.0.1"):
        payload = ["VD_RUN_V1", mi_release, strategy_id, strategy_version, dataset_id,
                   str(start), str(end), execution_profile, account_profile,
                   ["TD8E_V1", "MI_V1", "SSC_V1.0.1", "VD_LEDGER_V1"]]
        return cls("VD_RUN_V1", mi_release, strategy_id, strategy_version, dataset_id,
                   start, end, execution_profile, account_profile,
                   ("TD8E_V1", "MI_V1", "SSC_V1.0.1", "VD_LEDGER_V1"), _hash(payload))


@dataclass(frozen=True)
class RunFunnel:
    market_events: int = 0
    ssc_evaluations: int = 0
    no_setup: int = 0
    rejected: int = 0
    incomplete: int = 0
    actionable_intents: int = 0
    virtual_orders: int = 0
    virtual_fills: int = 0
    open_positions: int = 0
    closed_outcomes: int = 0
    unresolved_outcomes: int = 0


class VirtualDemoRunner:
    """Coordinates existing components; decision results are injected as authority."""

    def __init__(self, *, feed: VirtualMarketFeed, identity: VirtualDemoRunIdentity,
                 decisions: Dict[str, object], dataset_id: str,
                 decision_source: Optional[Callable[[ReplayEvaluationContext], ReplayResult]] = None,
                 capacity_mode: bool = False):
        if identity.dataset_id != dataset_id or feed.symbol == "":
            raise RunnerError("RUN_IDENTITY_MISMATCH")
        if capacity_mode and (decision_source is None or decisions):
            raise RunnerError("CAPACITY_REQUIRES_CONTEXT_DECISION_SOURCE")
        self.feed, self.identity, self.decisions, self.dataset_id = feed, identity, decisions, dataset_id
        self.decision_source = decision_source
        self.capacity_mode = capacity_mode
        self.bridge = SSCToVirtualOrderBridge(strategy_id=identity.strategy_id, strategy_version=identity.strategy_version)
        self.ledger = VirtualLedger()
        self.account = VirtualAccount(max_open_positions=1)
        self.funnel = RunFunnel()
        self._processed_decisions = set()
        self._cursor = 0
        self._bars: list[OHLCM1] = []
        self._fatal: Optional[str] = None

    def run(self, *, mode="maximum", stop_after_events: Optional[int] = None):
        if self._fatal:
            raise RunnerError(self._fatal)
        while self.feed.status != "END_OF_DATA":
            batch = self.feed.step()
            self._cursor += 1
            self.funnel = RunFunnel(self.funnel.market_events + len(batch), self.funnel.ssc_evaluations,
                                    self.funnel.no_setup, self.funnel.rejected, self.funnel.incomplete,
                                    self.funnel.actionable_intents, self.funnel.virtual_orders,
                                    self.funnel.virtual_fills, len(self.account.open_positions),
                                    len(self.account.closed_positions), self.funnel.unresolved_outcomes)
            for event in batch:
                if event.timeframe == "M1":
                    self._bars.append(OHLCM1(event.event_id, event.dataset_id, event.symbol,
                                             event.candle.time, event.candle.open, event.candle.high,
                                             event.candle.low, event.candle.close))
            # Controlled decision fixtures are keyed by TD-8E replay event identity.
            for event in batch:
                if event.replay_event_id in self._processed_decisions:
                    continue
                if self.decision_source is not None:
                    context = ReplayEvaluationContext.create(
                        self.feed.store, self.feed.symbol, self.feed.clock.T, self.feed.timeframes)
                    if context.event_id != event.replay_event_id:
                        raise RunnerError("REPLAY_EVENT_ID_MISMATCH")
                    decision = self.decision_source(context)
                    if not isinstance(decision, ReplayResult):
                        raise RunnerError("CONTEXT_SOURCE_MUST_RETURN_REPLAY_RESULT")
                else:
                    decision = self.decisions.get(event.replay_event_id, self.decisions.get("__DEFAULT__"))
                if decision is None:
                    continue
                self._processed_decisions.add(event.replay_event_id)
                self._evaluate(decision, event.replay_event_id, mode)
            if stop_after_events is not None and self._cursor >= stop_after_events:
                break
        return self

    def _evaluate(self, decision, event_id, mode):
        self.funnel = RunFunnel(self.funnel.market_events, self.funnel.ssc_evaluations + 1,
                                self.funnel.no_setup, self.funnel.rejected, self.funnel.incomplete,
                                self.funnel.actionable_intents, self.funnel.virtual_orders,
                                self.funnel.virtual_fills, len(self.account.open_positions),
                                len(self.account.closed_positions), self.funnel.unresolved_outcomes)
        bridged = self.bridge.build(decision, dataset_id=self.dataset_id,
                                    decision_event_id=event_id, m1_lineage_id=self.dataset_id)
        if bridged.status == "NO_SETUP":
            self.ledger.append(event_type="StrategyDecision", at=self.feed.clock.T,
                               dataset_id=self.dataset_id, source_event_id=event_id,
                               payload={"status": "NO_SETUP"})
            self.funnel = self._replace(no_setup=self.funnel.no_setup + 1)
            return
        if bridged.status == "REJECTED":
            self.funnel = self._replace(rejected=self.funnel.rejected + 1)
            return
        for intent in bridged.intents:
            root = self.ledger.append(event_type="TradeProposal", at=intent.proposal.decision_cutoff,
                                      dataset_id=self.dataset_id, source_event_id=event_id,
                                      payload={"proposal_id": intent.proposal.proposal_id})
            self.funnel = self._replace(actionable_intents=self.funnel.actionable_intents + 1)
            exchange = __import__("svos.virtual_exchange", fromlist=["VirtualExchange"]).VirtualExchange()
            order = exchange.submit(intent.proposal)
            self.funnel = self._replace(virtual_orders=self.funnel.virtual_orders + 1)
            order = exchange.process(self._bars, mode=mode)
            if order.fill is None:
                continue
            fill_event = self.ledger.append_exchange_record(order.fill, strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version, side=intent.proposal.side,
                stop_price=intent.proposal.stop_price, target_price=intent.proposal.target_price,
                parent_event_ids=[root.event_id])
            self.account.apply_fill(order.fill, strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version, symbol=intent.proposal.symbol,
                side=intent.proposal.side, stop_price=intent.proposal.stop_price,
                target_price=intent.proposal.target_price)
            self.funnel = self._replace(virtual_fills=self.funnel.virtual_fills + 1)
            if order.exit is not None:
                self.ledger.append_exchange_record(order.exit, strategy_id=intent.strategy_id,
                    strategy_version=intent.strategy_version, side=intent.proposal.side,
                    parent_event_ids=[fill_event.event_id])
                if order.exit.observation_kind == "AMBIGUOUS_SEQUENCE":
                    self.account.apply_exit(order.exit)
                    self.funnel = self._replace(unresolved_outcomes=self.funnel.unresolved_outcomes + 1)
                else:
                    self.account.apply_exit(order.exit)
                    self.funnel = self._replace(closed_outcomes=self.funnel.closed_outcomes + 1)

    def _replace(self, **kwargs):
        data = self.funnel.__dict__.copy(); data.update(kwargs); return RunFunnel(**data)

    def checkpoint(self) -> dict:
        return {"identity": self.identity.fingerprint, "cursor": self._cursor,
                "processed": sorted(self._processed_decisions), "ledger_hash": self.ledger.terminal_hash,
                "funnel": self.funnel.__dict__}
