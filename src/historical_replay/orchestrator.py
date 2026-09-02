"""Chronological replay orchestrator (historical-validation continuation spec sections
13-26): steps a replay clock through closed M5 bars, and at each step calls the SAME
live entrypoint (`daytrading_runtime.conditional_entry_snapshot.build_symbol_conditional_entry_analysis`)
inside `historical_data_context`, so E1/E2/E3, M1/M2/M3, and the composer are never
re-detected here -- only observed and recorded (spec section 13-14: "must NOT redetect
SMC concepts").

Two outputs, kept separate per spec section 46:
- `SetupLedger` -- every combination ever observed (READY or not), independent of the
  live proposal system's READY-only filtering, built directly from
  `analysis.combinations` using the SAME `setup_id`/`reference_key_for` identity
  functions `proposals.gate`/`lifecycle` use (reused, not reimplemented).
- `FunnelTracker` -- distinct-occurrence counts per funnel stage (spec section 22-26),
  using only the frozen `EntryModelState` enum's own state names, never invented ones.

Also runs `proposals.lifecycle.update_proposal_lifecycle` every step (cheap: `analysis`
is already computed) purely as an independent cross-check for setup-identity stability
(spec section 21) against an in-memory stand-in for `runtime_state.store.JsonKeyValueStore`
-- that store does a full file read+rewrite per `put`, which is fine for live polling
cadence but would be needless O(n) disk I/O per M5 step across a multi-month replay;
the in-memory store below implements the exact same get/put duck-type contract.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

from daytrading_runtime.conditional_entry_snapshot import build_symbol_conditional_entry_analysis
from entry_confirmation.entry_models_v1 import COMBINATIONS, ENTRY_CONDITIONS, MANEUVERS, EntryModelState, SMCConditionalEntryAnalysis
from proposals import reference_key_for, setup_id as _setup_id, update_proposal_lifecycle
from proposals.gate import _entry_range, _matching_m_result
from proposals.models import LIFECYCLE_CREATED
from strategy_engine.session import Candle

from .candle_store import HistoricalCandleStore, HistoricalDataError
from .data_source_patch import historical_data_context

D1_WARMUP_CANDLES = 60  # matches daytrading_runtime.conditional_entry_snapshot.D1_GAP_LOOKBACK_CANDLES
H1_WARMUP_CANDLES = 50  # matches ...H1_POI_LOOKBACK_CANDLES
M5_WARMUP_CANDLES = 200  # matches ...M5_LOOKBACK_CANDLES

_NOT_STARTED_STATES = (EntryModelState.NOT_APPLICABLE.value, EntryModelState.NO_VALID_COMBINATION.value,
                       EntryModelState.INSUFFICIENT_DATA.value)

# "M_CONFIRMED" (spec section 25/functionally "M's own confirmation event fired") --
# an ALLOWLIST of past-confirmation-or-terminal states, not a blacklist. M1/M3's own
# state vocabulary (m1_character_change_inducement.py, m3_sweep_drop_pump.py) includes
# several EARLY pre-confirmation states beyond WAITING_M5_CONFIRMATION --
# WAITING_HTF_TOUCH ("no inducement candidate identified yet", M1's very first gate)
# and WAITING_H1_REACTION ("inducement identified but not yet taken") -- and the
# composer copies combo.state = m.state directly (composer.py's compose()), so these
# early names DO appear as a combo's own state. An earlier blacklist-based version of
# this classifier only excluded WAITING_M5_CONFIRMATION, silently misclassifying
# WAITING_HTF_TOUCH/WAITING_H1_REACTION as "confirmed" -- found via the Aug-Sep 2025
# discovery run (M1 showed 18/18 "confirmed" with 0 arrays, which turned out to mean
# 18/18 never found an inducement candidate at all). See
# tests/test_setup_ledger_funnel_reconciliation.py for the regression test.
_CONFIRMED_OR_TERMINAL_STATES = (
    EntryModelState.WAITING_M5_ENTRY.value, EntryModelState.READY.value,
    EntryModelState.INVALIDATED.value, EntryModelState.EXPIRED.value,
)

_STAGES = ("REFERENCE_FOUND", "E_QUALIFIED", "M_STARTED", "M_CONFIRMED", "ENTRY_ARRAY_CREATED", "READY")


class InMemoryKeyValueStore:
    """Minimal in-memory get/put store matching runtime_state.store.JsonKeyValueStore's
    duck-typed interface -- used here instead of the disk-backed store purely for
    performance (see module docstring); not a competing persistence abstraction."""

    def __init__(self) -> None:
        self._data: Dict[str, object] = {}

    def get(self, key: str):
        return self._data.get(key)

    def put(self, key: str, value: object) -> None:
        self._data[key] = value


@dataclass
class SetupLedgerRow:
    setup_id: str
    symbol: str
    combination: str
    entry_condition: str
    maneuver: str
    direction: Optional[str]
    reference_key: Optional[str]
    first_seen_time: datetime
    last_seen_time: datetime
    ready_time: Optional[datetime] = None
    entry_type: Optional[str] = None
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    entry_reference: Optional[float] = None
    invalidation_price: Optional[float] = None
    invalidation_source_type: Optional[str] = None
    invalidation_trigger: Optional[str] = None
    final_state: str = EntryModelState.NOT_APPLICABLE.value
    final_time: Optional[datetime] = None
    terminal: bool = False


class SetupLedger:
    """Every combination ever observed in replay, keyed by the same `setup_id` the live
    proposal system uses -- freezes further updates once a setup reaches a terminal
    state (INVALIDATED/EXPIRED), mirroring proposals.lifecycle's own terminal discipline
    (spec section 21: a setup_id that keeps changing after termination would itself be
    an identity-instability bug)."""

    def __init__(self) -> None:
        self.rows: Dict[str, SetupLedgerRow] = {}
        self.identity_collisions: Set[str] = set()  # setup_ids observed with >1 distinct reference_key

    def observe(self, analysis: SMCConditionalEntryAnalysis, as_of: datetime) -> None:
        for combo in analysis.combinations:
            m_result = _matching_m_result(analysis, combo)
            if combo.state in _NOT_STARTED_STATES:
                continue  # composer never engaged this E/M/direction at all this step
            e_condition = analysis.e_conditions.get(combo.entry_condition)
            reference_key = reference_key_for(
                getattr(e_condition, "reference_type", None), getattr(e_condition, "reference_low", None),
                getattr(e_condition, "reference_high", None), getattr(e_condition, "reference_level", None),
            )
            setup_id = _setup_id(analysis.symbol, combo.combination, combo.direction, reference_key)

            row = self.rows.get(setup_id)
            if row is not None and row.terminal:
                if row.reference_key != reference_key:
                    self.identity_collisions.add(setup_id)
                continue  # frozen -- no further updates once terminal

            if row is None:
                row = SetupLedgerRow(
                    setup_id=setup_id, symbol=analysis.symbol, combination=combo.combination,
                    entry_condition=combo.entry_condition, maneuver=combo.maneuver, direction=combo.direction,
                    reference_key=reference_key, first_seen_time=as_of, last_seen_time=as_of,
                )
                self.rows[setup_id] = row
            elif row.reference_key != reference_key:
                self.identity_collisions.add(setup_id)

            row.last_seen_time = as_of
            row.final_state = combo.state
            row.final_time = as_of
            if combo.entry_array not in (None, "NONE"):
                # Record entry-array fields whenever one actually forms -- not only at
                # READY -- so the ledger agrees with FunnelTracker's own
                # ENTRY_ARRAY_CREATED definition (a setup can form an entry array and
                # still never reach READY; that is a valid, distinct funnel stage).
                entry_low, entry_high = _entry_range(m_result) if m_result is not None else (None, None)
                row.entry_type = combo.entry_array
                row.entry_low = entry_low
                row.entry_high = entry_high
                row.entry_reference = combo.entry_price
            if combo.state == EntryModelState.READY.value and row.ready_time is None:
                row.ready_time = as_of
            if combo.invalidation_price is not None:
                row.invalidation_price = combo.invalidation_price
                row.invalidation_source_type = combo.invalidation_source_type
                row.invalidation_trigger = combo.invalidation_trigger
            if combo.state in (EntryModelState.INVALIDATED.value, EntryModelState.EXPIRED.value):
                row.terminal = True


class FunnelTracker:
    """Distinct-FIRST-occurrence counters per funnel stage (spec sections 22-26) --
    counts a reference/setup once regardless of how many M5 polls it remains in that
    stage, so a long-lived setup does not inflate the numbers (spec section 18: "do not
    dump a complete identical analysis row every M5 candle")."""

    def __init__(self) -> None:
        self._e_stage_seen: Dict[str, Set[Tuple]] = defaultdict(set)  # stage -> {(entry_condition, ref_key, direction)}
        self._combo_stage_seen: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)  # stage -> {(combination, setup_id)}

    def observe(self, analysis: SMCConditionalEntryAnalysis) -> None:
        for name, econd in analysis.e_conditions.items():
            ref_key = reference_key_for(econd.reference_type, econd.reference_low, econd.reference_high, econd.reference_level)
            key = (name, ref_key, econd.direction)
            if econd.reference_type is not None:
                self._e_stage_seen["REFERENCE_FOUND"].add(key)
            if econd.eligible_for_confirmation:
                self._e_stage_seen["E_QUALIFIED"].add(key)

        for combo in analysis.combinations:
            if combo.state in _NOT_STARTED_STATES:
                continue
            e_condition = analysis.e_conditions.get(combo.entry_condition)
            reference_key = reference_key_for(
                getattr(e_condition, "reference_type", None), getattr(e_condition, "reference_low", None),
                getattr(e_condition, "reference_high", None), getattr(e_condition, "reference_level", None),
            )
            setup_id = _setup_id(analysis.symbol, combo.combination, combo.direction, reference_key)
            combo_key = (combo.combination, setup_id)

            self._combo_stage_seen["M_STARTED"].add(combo_key)
            if combo.state in _CONFIRMED_OR_TERMINAL_STATES:
                self._combo_stage_seen["M_CONFIRMED"].add(combo_key)
            if combo.entry_array not in (None, "NONE"):
                self._combo_stage_seen["ENTRY_ARRAY_CREATED"].add(combo_key)
            if combo.state == EntryModelState.READY.value:
                self._combo_stage_seen["READY"].add(combo_key)

    def per_combination(self) -> Dict[str, Dict[str, int]]:
        out = {c: {s: 0 for s in _STAGES} for c in COMBINATIONS}
        for stage, keys in self._combo_stage_seen.items():
            for combination, _setup in keys:
                out.setdefault(combination, {s: 0 for s in _STAGES})[stage] += 1
        return out

    def per_e(self) -> Dict[str, Dict[str, int]]:
        out = {e: {"REFERENCE_FOUND": 0, "E_QUALIFIED": 0} for e in ENTRY_CONDITIONS}
        for stage in ("REFERENCE_FOUND", "E_QUALIFIED"):
            for entry_condition, _ref, _direction in self._e_stage_seen.get(stage, ()):
                out.setdefault(entry_condition, {"REFERENCE_FOUND": 0, "E_QUALIFIED": 0})[stage] += 1
        return out

    def per_m(self) -> Dict[str, Dict[str, int]]:
        out = {m: {s: 0 for s in _STAGES if s not in ("REFERENCE_FOUND", "E_QUALIFIED")} for m in MANEUVERS}
        for stage, keys in self._combo_stage_seen.items():
            for combination, _setup in keys:
                maneuver = combination[2:]  # "E1M1" -> "M1"
                out.setdefault(maneuver, {})[stage] = out.setdefault(maneuver, {}).get(stage, 0) + 1
        return out


@dataclass(frozen=True)
class ReplayResult:
    symbol: str
    steps: int
    warmup_steps: int
    valid_steps: int
    setup_ledger: Tuple[SetupLedgerRow, ...]
    identity_collisions: int
    identity_instability_events: int
    ready_lifecycle_created_events: int
    per_combination: Dict[str, Dict[str, int]]
    per_e: Dict[str, Dict[str, int]]
    per_m: Dict[str, Dict[str, int]]


def _has_enough_history(store: HistoricalCandleStore, symbol: str, timeframe: str, count: int, as_of: datetime) -> bool:
    try:
        store.closed_candles(symbol, timeframe, as_of, count)
        return True
    except HistoricalDataError:
        return False


def run_replay(store: HistoricalCandleStore, symbol: str, m5_step_candles: Sequence[Candle],
               start_utc: datetime, end_utc: datetime, progress_callback=None,
               progress_every: int = 2000, symbol_metadata_manifest=None) -> ReplayResult:
    """`m5_step_candles` is the base M5 series already loaded into `store` -- the
    replay clock is exactly its closed-bar boundaries (spec section 15: M5
    closed-candle progression), filtered to [start_utc, end_utc).

    `progress_callback(valid_steps, steps, as_of)`, if given, is invoked every
    `progress_every` valid steps -- pure observability (e.g. writing a tiny checkpoint
    file for a long run), never affects replay semantics or results.

    `symbol_metadata_manifest` (REPLAY_METADATA_DECOUPLING_V1, optional, default None
    -- fully backward compatible) is threaded straight into `historical_data_context`;
    see that function and `historical_replay.symbol_metadata_manifest` for what it
    does (restores `market_structure.tiers.analyze_structure_tiers`'s tick_size lookup
    during replay, fixing M1 inducement-candidate detection's own use of it -- no
    detection semantics changed, only data availability)."""
    ledger = SetupLedger()
    funnel = FunnelTracker()
    lifecycle_store = InMemoryKeyValueStore()

    steps = warmup_steps = valid_steps = 0
    ready_created_events = 0
    warmup_cleared = False

    for candle in m5_step_candles:
        as_of = candle.time + timedelta(minutes=5)  # this M5 bar's close time
        if as_of < start_utc or as_of >= end_utc:
            continue
        steps += 1

        if not warmup_cleared:
            if (_has_enough_history(store, symbol, "D1", D1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, symbol, "H1", H1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, symbol, "M5", M5_WARMUP_CANDLES, as_of)):
                warmup_cleared = True
            else:
                warmup_steps += 1
                continue  # insufficient history -- WARMUP, not a valid "no setup" result

        valid_steps += 1
        with historical_data_context(store, as_of, symbol_metadata_manifest=symbol_metadata_manifest):
            analysis = build_symbol_conditional_entry_analysis(symbol)

        if progress_callback is not None and valid_steps % progress_every == 0:
            progress_callback(valid_steps, steps, as_of)

        ledger.observe(analysis, as_of)
        funnel.observe(analysis)
        updates = update_proposal_lifecycle(analysis, lifecycle_store)
        ready_created_events += sum(1 for u in updates if u.lifecycle == LIFECYCLE_CREATED)

    return ReplayResult(
        symbol=symbol, steps=steps, warmup_steps=warmup_steps, valid_steps=valid_steps,
        setup_ledger=tuple(ledger.rows.values()),
        identity_collisions=len(ledger.identity_collisions),
        identity_instability_events=0,  # see docs/status: not separately distinguished from collisions this phase
        ready_lifecycle_created_events=ready_created_events,
        per_combination=funnel.per_combination(), per_e=funnel.per_e(), per_m=funnel.per_m(),
    )


@dataclass(frozen=True)
class Stage1Event:
    """A qualified E-condition instance -- the seam between Stage 1 (context/E
    production) and Stage 2 (M1/M2/M3 entry confirmation). `qualification_time` is
    when this (entry_condition, reference_key, direction) tuple was first observed
    eligible_for_confirmation -- reconstructed here from an existing full-replay
    SetupLedger (min first_seen_time across its 3 combinations), NOT from a separately
    re-run Stage-1-only pass. A genuine standalone Stage-1 producer (one that runs E1/
    E2/E3 evaluation without ever touching M1/M2/M3) is future work; see status doc."""
    entry_condition: str
    reference_key: Optional[str]
    direction: Optional[str]
    qualification_time: datetime
    liquidity_reference: Optional[object] = None  # historical_replay.stage2.Stage1LiquidityReference,
    # for E3 events only -- untyped here to avoid a circular import (stage2.py imports Stage1Event
    # from this module)
    eligibility_intervals: Tuple[Tuple[datetime, datetime], ...] = ()  # [start, end) pairs; empty =
    # not yet reconstructed (migration-fixture default). See historical_replay.stage1.QualifiedEEvent
    # for the canonical, fully-specified contract this field is being promoted into.


def stage1_events_from_ledger(rows: Sequence[SetupLedgerRow]) -> Tuple[Stage1Event, ...]:
    groups: Dict[Tuple[str, Optional[str], Optional[str]], datetime] = {}
    for r in rows:
        key = (r.entry_condition, r.reference_key, r.direction)
        if key not in groups or r.first_seen_time < groups[key]:
            groups[key] = r.first_seen_time
    return tuple(Stage1Event(entry_condition=k[0], reference_key=k[1], direction=k[2], qualification_time=v)
                 for k, v in sorted(groups.items(), key=lambda kv: kv[1]))


# RESEARCH_ASSUMPTION / NOT_STRATEGY_CONTRACT (spec source, prior session's own rule on
# entry expiry, still true: "ENTRY_EXPIRY_RULE = UNDEFINED... do not invent one unless
# explicitly labeled"). No frozen entry-expiry contract exists anywhere in
# entry_confirmation. This window bounds how long Stage 2 keeps re-evaluating M5 for a
# given Stage-1 event before giving up -- picked generously (192h = 8 days) to exceed
# the longest observed real span in the Aug-Sep 2025 fixture (167.9h) with margin, NOT
# derived from any strategy rule. Never present ENTRY_ONLY_REPLAY results as canonical
# strategy behavior without this caveat attached.
STAGE2_WINDOW_HOURS_RESEARCH_ASSUMPTION = 192


def run_event_driven_replay(store: HistoricalCandleStore, symbol: str, m5_step_candles: Sequence[Candle],
                            events: Sequence[Stage1Event],
                            window_hours: int = STAGE2_WINDOW_HOURS_RESEARCH_ASSUMPTION) -> ReplayResult:
    """ENTRY_ONLY_REPLAY: identical per-step evaluation logic to run_replay (the SAME
    live entrypoint call, same ledger/funnel observation -- no duplicate strategy
    logic), but restricted to the UNION of [event.qualification_time,
    event.qualification_time + window_hours) across `events`, instead of one
    continuous [start, end) range. Does not skip warmup checking (still fails closed
    on insufficient D1/H1/M5 history at any given step)."""
    intervals = sorted(
        (e.qualification_time, e.qualification_time + timedelta(hours=window_hours)) for e in events
    )
    merged: List[Tuple[datetime, datetime]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    ledger = SetupLedger()
    funnel = FunnelTracker()
    lifecycle_store = InMemoryKeyValueStore()
    steps = warmup_steps = valid_steps = 0
    ready_created_events = 0
    warmup_cleared = False
    interval_idx = 0

    for candle in m5_step_candles:
        as_of = candle.time + timedelta(minutes=5)
        while interval_idx < len(merged) and as_of >= merged[interval_idx][1]:
            interval_idx += 1
        if interval_idx >= len(merged) or as_of < merged[interval_idx][0]:
            continue
        steps += 1

        if not warmup_cleared:
            if (_has_enough_history(store, symbol, "D1", D1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, symbol, "H1", H1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, symbol, "M5", M5_WARMUP_CANDLES, as_of)):
                warmup_cleared = True
            else:
                warmup_steps += 1
                continue

        valid_steps += 1
        with historical_data_context(store, as_of):
            analysis = build_symbol_conditional_entry_analysis(symbol)

        ledger.observe(analysis, as_of)
        funnel.observe(analysis)
        updates = update_proposal_lifecycle(analysis, lifecycle_store)
        ready_created_events += sum(1 for u in updates if u.lifecycle == LIFECYCLE_CREATED)

    return ReplayResult(
        symbol=symbol, steps=steps, warmup_steps=warmup_steps, valid_steps=valid_steps,
        setup_ledger=tuple(ledger.rows.values()),
        identity_collisions=len(ledger.identity_collisions),
        identity_instability_events=0,
        ready_lifecycle_created_events=ready_created_events,
        per_combination=funnel.per_combination(), per_e=funnel.per_e(), per_m=funnel.per_m(),
    )
