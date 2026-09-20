"""Minimal deterministic end-to-end VD orchestration over already-admitted decisions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

from .ssc_bridge import SSCToVirtualOrderBridge
from .virtual_account import VirtualAccount
from .virtual_ledger import VirtualLedger
from .virtual_time import VirtualMarketFeed
from .virtual_exchange import OHLCM1, VirtualExchange, OrderState
from historical_replay.evaluation_context import ReplayEvaluationContext
from historical_replay.candle_store import HistoricalDataError
from session_sweep_continuation.replay import ReplayResult
from session_sweep_continuation import STRATEGY_ID, STRATEGY_VERSION
from session_sweep_continuation.canonical_consumer import run_canonical_shadow_cycle
from session_sweep_continuation.canonical_observations import ObservationValidationError
from session_sweep_continuation.sessions import session_windows_from_config
from historical_replay.symbol_metadata_manifest import (
    HistoricalSymbolMetadataManifest, REQUIRED_AUTHORITY, validate_manifest_for_dataset)
import yaml


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
                 capacity_mode: bool = False,
                 capacity_manifest: Optional[HistoricalSymbolMetadataManifest] = None,
                 capacity_h1_dataset_path: Optional[str] = None,
                 capacity_session_pair: Optional[str] = None,
                 capacity_pip_size: Optional[float] = None,
                 capacity_pip_value_per_lot: Optional[float] = None):
        if identity.dataset_id != dataset_id or feed.symbol == "":
            raise RunnerError("RUN_IDENTITY_MISMATCH")
        if capacity_mode:
            if decisions or decision_source is not None:
                raise RunnerError("CAPACITY_REJECTS_CALLER_DECISION_AUTHORITY")
            if (identity.strategy_id, identity.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
                raise RunnerError("CAPACITY_STRATEGY_IDENTITY_MISMATCH")
            if (capacity_manifest is None or capacity_manifest.authority != REQUIRED_AUTHORITY
                    or capacity_manifest.symbol != feed.symbol or capacity_session_pair is None
                    or capacity_h1_dataset_path is None
                    or capacity_pip_size is None or capacity_pip_size <= 0
                    or capacity_pip_value_per_lot is None or capacity_pip_value_per_lot <= 0
                    or set(feed.timeframes) != {"H1", "M15", "M1"}):
                raise RunnerError("CAPACITY_CANONICAL_INPUTS_UNAVAILABLE")
            if capacity_manifest.dataset_id != feed.store.dataset_identity(feed.symbol, "H1").dataset_id:
                raise RunnerError("CAPACITY_H1_DATASET_IDENTITY_MISMATCH")
            validate_manifest_for_dataset(capacity_manifest, capacity_h1_dataset_path, feed.symbol)
            contract_path = Path(__file__).resolve().parents[2] / "strategies" / "ST_SESSION_SWEEP_CONTINUATION_V1.yaml"
            contract_bytes = contract_path.read_bytes()
            contract = yaml.safe_load(contract_bytes)
            if contract["strategy_id"] != STRATEGY_ID or str(contract["version"]) != STRATEGY_VERSION:
                raise RunnerError("CAPACITY_CONTRACT_IDENTITY_MISMATCH")
            if capacity_session_pair not in session_windows_from_config(contract):
                raise RunnerError("CAPACITY_SESSION_PAIR_UNAVAILABLE")
            self.capacity_contract = contract
            self.capacity_contract_hash = "sha256:" + hashlib.sha256(contract_bytes).hexdigest()
        else:
            self.capacity_contract = None
            self.capacity_contract_hash = None
        self.capacity_manifest = capacity_manifest
        self.capacity_session_pair = capacity_session_pair
        self.capacity_pip_size = capacity_pip_size
        self.capacity_pip_value_per_lot = capacity_pip_value_per_lot
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
        self._active_orders = {}
        self._seen_setups = set()
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
                    bar = OHLCM1(event.event_id, event.dataset_id, event.symbol,
                                 event.candle.time, event.candle.open, event.candle.high,
                                 event.candle.low, event.candle.close)
                    self._bars.append(bar)
                    self._advance_orders(bar)
            # Controlled decision fixtures are keyed by TD-8E replay event identity.
            for event in batch:
                if event.replay_event_id in self._processed_decisions:
                    continue
                if self.capacity_mode:
                    if event.timeframe != "M15":
                        continue
                    context = ReplayEvaluationContext.create(
                        self.feed.store, self.feed.symbol, self.feed.clock.T, self.feed.timeframes)
                    if context.event_id != event.replay_event_id:
                        raise RunnerError("REPLAY_EVENT_ID_MISMATCH")
                    decision = self._canonical_capacity_decision(context)
                elif self.decision_source is not None:
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
        if self.feed.status == "END_OF_DATA":
            self._finish_orders()
        return self

    def _advance_orders(self, bar):
        for order_id, (exchange, intent, parent) in tuple(self._active_orders.items()):
            before_fill = exchange.order.fill
            before_exit = exchange.order.exit
            order = exchange.advance(bar)
            if before_fill is None and order.fill is not None:
                fill_event = self.ledger.append_exchange_record(
                    order.fill, strategy_id=intent.strategy_id,
                    strategy_version=intent.strategy_version, side=intent.proposal.side,
                    stop_price=intent.proposal.stop_price,
                    target_price=intent.proposal.target_price,
                    parent_event_ids=[parent])
                self.account.apply_fill(order.fill, strategy_id=intent.strategy_id,
                    strategy_version=intent.strategy_version, symbol=intent.proposal.symbol,
                    side=intent.proposal.side, stop_price=intent.proposal.stop_price,
                    target_price=intent.proposal.target_price)
                self.funnel = self._replace(virtual_fills=self.funnel.virtual_fills + 1,
                                            open_positions=len(self.account.open_positions))
                self._active_orders[order_id] = (exchange, intent, fill_event.event_id)
                parent = fill_event.event_id
            if before_exit is None and order.exit is not None:
                self.ledger.append_exchange_record(order.exit, strategy_id=intent.strategy_id,
                    strategy_version=intent.strategy_version, side=intent.proposal.side,
                    parent_event_ids=[parent])
                self.account.apply_exit(order.exit)
                ambiguous = order.exit.observation_kind == "AMBIGUOUS_SEQUENCE"
                self.funnel = self._replace(
                    closed_outcomes=self.funnel.closed_outcomes + (0 if ambiguous else 1),
                    unresolved_outcomes=self.funnel.unresolved_outcomes + (1 if ambiguous else 0),
                    open_positions=len(self.account.open_positions))
                del self._active_orders[order_id]
            elif order.state == OrderState.EXPIRED:
                del self._active_orders[order_id]

    def _finish_orders(self):
        for order_id, (exchange, intent, parent) in tuple(self._active_orders.items()):
            order = exchange.end_of_data(at=self.feed.clock.T,
                                         event_id=f"END_OF_DATA:{self.identity.fingerprint}")
            reason = "END_OF_DATA_OPEN_POSITION" if order.fill is not None else "END_OF_DATA_PENDING"
            if order.fill is not None:
                self.account.mark_unresolved(order_id=order_id, at=self.feed.clock.T,
                    reason=reason, evidence_event_id=f"END_OF_DATA:{self.identity.fingerprint}")
            self.ledger.append(event_type="VirtualUnresolved", at=self.feed.clock.T,
                dataset_id=self.dataset_id, source_event_id=order_id,
                strategy_id=intent.strategy_id, strategy_version=intent.strategy_version,
                proposal_id=intent.proposal.proposal_id, order_id=order_id,
                parent_event_ids=[parent], payload={"reason": reason,
                    "evidence_event_id": f"END_OF_DATA:{self.identity.fingerprint}"})
            self.funnel = self._replace(unresolved_outcomes=self.funnel.unresolved_outcomes + 1)
            del self._active_orders[order_id]

    def _canonical_capacity_decision(self, context: ReplayEvaluationContext):
        day = context.as_of.date()
        reference_end = session_windows_from_config(self.capacity_contract)[self.capacity_session_pair]["reference"].bounds_for_date(day)[1]
        if context.as_of < reference_end:
            self.funnel = self._replace(incomplete=self.funnel.incomplete + 1)
            return None
        try:
            cycle = run_canonical_shadow_cycle(
                h1_store=context.provider.store_view(), manifest=self.capacity_manifest,
                m15_candles=context.candles("M15"), m1_candles=context.candles("M1"),
                config=self.capacity_contract, symbol=context.symbol,
                session_pair_id=self.capacity_session_pair, trading_date=day,
                decision_time=reference_end, pip_size=self.capacity_pip_size,
                pip_value_per_lot=self.capacity_pip_value_per_lot)
        except (HistoricalDataError, ObservationValidationError, ValueError, KeyError) as exc:
            self.ledger.append(event_type="CanonicalUnavailable", at=context.as_of,
                               dataset_id=self.dataset_id, source_event_id=context.event_id,
                               payload={"reason": type(exc).__name__})
            self.funnel = self._replace(incomplete=self.funnel.incomplete + 1)
            return None
        current = [s for s in cycle.replay_result.accepted_setups
                   if datetime.fromisoformat(str(s["entry_time"])).astimezone(timezone.utc)
                   + timedelta(minutes=15) == context.as_of]
        self._capacity_provenance = {
            tf: identity.as_composed_identity_token()
            for tf, identity in context.series_identities.items()}
        return replace(cycle.replay_result, accepted_setups=current)

    def _evaluate(self, decision, event_id, mode):
        canonical_event = None
        if self.capacity_mode:
            canonical_event = self.ledger.append(event_type="CanonicalDecision", at=self.feed.clock.T,
                               dataset_id=self.dataset_id, source_event_id=event_id,
                               strategy_id=self.identity.strategy_id,
                               strategy_version=self.identity.strategy_version,
                               decision_id=_hash(decision.to_dict()),
                               payload={"strategy_contract_hash": self.capacity_contract_hash,
                                        "evaluation_time": self.feed.clock.T.isoformat(),
                                        "replay_event_id": event_id,
                                        "dataset_series": self._capacity_provenance,
                                        "decision_hash": _hash(decision.to_dict())})
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
            setup_key = (intent.campaign_id, intent.setup_model,
                         str(intent.proposal.reference_entry.decision_cutoff),
                         intent.proposal.reference_entry.reference_price)
            if self.capacity_mode and setup_key in self._seen_setups:
                continue
            self._seen_setups.add(setup_key)
            if self._active_orders or len(self.account.open_positions) >= self.account.max_open_positions:
                self.ledger.append(event_type="VirtualOrderRejected", at=self.feed.clock.T,
                    dataset_id=self.dataset_id, source_event_id=intent.proposal.proposal_id,
                    strategy_id=intent.strategy_id, strategy_version=intent.strategy_version,
                    proposal_id=intent.proposal.proposal_id,
                    payload={"reason": "MAX_CONCURRENT_VIRTUAL_POSITIONS"})
                self.funnel = self._replace(rejected=self.funnel.rejected + 1)
                continue
            root = self.ledger.append(event_type="TradeProposal", at=intent.proposal.decision_cutoff,
                                      dataset_id=self.dataset_id, source_event_id=intent.proposal.proposal_id,
                                      payload={"proposal_id": intent.proposal.proposal_id},
                                      parent_event_ids=[canonical_event.event_id] if canonical_event else ())
            self.funnel = self._replace(actionable_intents=self.funnel.actionable_intents + 1)
            exchange = VirtualExchange()
            order = exchange.submit(intent.proposal)
            self.funnel = self._replace(virtual_orders=self.funnel.virtual_orders + 1)
            self._active_orders[order.order_id] = (exchange, intent, root.event_id)

    def _replace(self, **kwargs):
        data = self.funnel.__dict__.copy(); data.update(kwargs); return RunFunnel(**data)

    def checkpoint(self) -> dict:
        return {"identity": self.identity.fingerprint, "cursor": self._cursor,
                "processed": sorted(self._processed_decisions), "ledger_hash": self.ledger.terminal_hash,
                "funnel": self.funnel.__dict__, "clock": self.feed.clock.T.isoformat(),
                "feed_sequence": self.feed.sequence_id,
                "capacity_contract_hash": self.capacity_contract_hash,
                "pending_orders": sorted(self._active_orders),
                "open_positions": sorted(self.account.open_positions),
                "closed_positions": sorted(self.account.closed_positions),
                "account_snapshot": self.account.latest_snapshot.snapshot_id if self.account.latest_snapshot else None,
                "seen_setups": sorted(str(s) for s in self._seen_setups)}

    @classmethod
    def restore_from_checkpoint(cls, checkpoint: dict, **runner_inputs):
        """Rebuild exact state from the admitted immutable feed prefix and verify it."""
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("cursor"), int) or checkpoint["cursor"] < 0:
            raise RunnerError("INVALID_CHECKPOINT")
        runner = cls(**runner_inputs)
        if runner.identity.fingerprint != checkpoint.get("identity"):
            raise RunnerError("CHECKPOINT_IDENTITY_MISMATCH")
        if checkpoint["cursor"]:
            runner.run(stop_after_events=checkpoint["cursor"])
        if runner.checkpoint() != checkpoint:
            raise RunnerError("CHECKPOINT_REPLAY_MISMATCH")
        return runner
