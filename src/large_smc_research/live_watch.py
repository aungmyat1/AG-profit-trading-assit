"""Corrected incremental live-watch evaluation for ST_LARGE_SMC_V1
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1, P4). RESEARCH_ONLY.

TWO CONFIRMED DEFECTS IN `scripts/run_large_smc_live_watch.py`
--------------------------------------------------------------
DEFECT 1 -- WRONG BROKER-TIME BASE FOR D1/H4 (time-alignment).

    The watcher did:

        broker_times = [c.time for c in m5_candles]        # <-- c.time is TRUE UTC
        ... resample_broker_aligned(m5_candles, broker_times, "M5", tf)

    but `mt5.market_data.get_candles` already subtracts the broker offset, so `c.time`
    is true UTC. `resample_broker_aligned`'s contract (see its own docstring) requires
    the candle's BROKER WALL-CLOCK reading, and `mt5_export_loader` supplies exactly
    that (`IngestionReport.broker_times`, i.e. the raw un-normalized file timestamps).
    Feeding UTC in makes broker-anchored bucketing degenerate to UTC-midnight
    bucketing -- precisely the failure `resample_broker_aligned` was written to
    prevent ("a UTC-midnight-bucketed resample mismatched EVERY SINGLE bar of a native
    MT5 D1 export"). H4 was equally wrong (boundaries 00/04/08/12/16/20 UTC instead of
    broker-anchored), and D1 windows were offset by the broker offset (2-3h), so the
    60-D1 / 50-H1 warm-up and every D1/H4-anchored detection input were computed on the
    wrong calendar.

    FIX: `resolve_broker_times()` reconstructs the broker wall-clock reading per candle
    from the broker's own detected UTC offset, so the D1/H4 buckets are broker-anchored
    again. DST is handled by re-detecting the offset on every run (the same seasonal
    +2/+3 behaviour `mt5_export_loader._offset_segments` documents), and the offset used
    is recorded in the run report so a stale-offset run is visible rather than silent.

DEFECT 2 -- REPEATED FULL 150-DAY REPLAY EVERY INVOCATION (no incrementality).

    The watcher re-fetched 150 days of M5 and re-ran `run_replay` over the whole window
    on EVERY invocation, re-deriving warm-up from scratch and re-evaluating ~43,000
    already-evaluated M5 bars. That is O(full history) work per run forever: cost grows
    with the calendar, not with new information, and every re-run re-observes the same
    historical setups (only the ledger's idempotent upsert hid the redundancy).

    FIX: a persisted watermark (`next_start_utc`) means each run evaluates only bars
    closed since the previous run, while the WARM-UP LOOKBACK is still fetched in full
    and the store is still built over it -- so warm-up is preserved without
    re-evaluating history. `run_replay`'s own clock filter (`as_of >= start_utc`) is
    exact at M5 close boundaries, so consecutive windows neither overlap nor skip.

FAIL-CLOSED RULES
-----------------
  * INSUFFICIENT_WARMUP_DATA -- the fetched history cannot clear D1/H1/M5 warm-up.
    Previously this produced `valid_steps=0` and an empty setup ledger, which is
    indistinguishable from "no setups found" -- a silent false negative. Now it is a
    hard error.
  * STALE_DATA -- the newest closed M5 bar is implausibly old relative to now.
  * NO_M5_CANDLES_RETURNED -- the fetch returned nothing.
  * OUT_OF_ORDER_OR_DUPLICATE_CANDLES -- the fetched series is not strictly ascending.
  * Watermark never advances past data actually evaluated, and is only written AFTER a
    successful evaluation, so a crash re-evaluates (safe) rather than skipping (unsafe).

NO EXECUTION AUTHORITY: this module imports only market-data, replay, and research
ledger modules. It must never import `execution.executor`, `execution.coordinator`,
`execution.adapter`, `mt5.management_gateway`, or any order function -- enforced by
tests/test_large_smc_live_watch_hardening.py. No proposal, demo, or live order is
reachable from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from historical_replay import (
    HistoricalCandleStore,
    resample,
    resample_broker_aligned,
)
from historical_replay.candle_store import HistoricalDataError
from historical_replay.orchestrator import (
    D1_WARMUP_CANDLES,
    H1_WARMUP_CANDLES,
    M5_WARMUP_CANDLES,
    run_replay,
)
from strategy_engine.session import Candle

# Lookback fetched for warm-up. Must comfortably exceed the binding warm-up constraint
# (60 closed D1 bars), which is why it is expressed in days rather than bars.
DEFAULT_WARMUP_LOOKBACK_DAYS = 150

# The set of timeframes the Large SMC engine consumes. M5 is the base feed; everything
# else is derived from it exactly as the pre-existing watcher did.
DERIVED_UTC_TIMEFRAMES = ("M15", "H1")
DERIVED_BROKER_TIMEFRAMES = ("H4", "D1")

# A weekend closure is ~47h (Fri ~22:00 UTC -> Sun ~21:00 UTC). 72h tolerates a
# weekend plus slack while still catching a genuinely dead feed.
DEFAULT_MAX_STALENESS_HOURS = 72

M5_MINUTES = 5


class LiveWatchError(RuntimeError):
    """Fail-closed watcher error. Carries a machine-checkable reason code."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


# ---------------------------------------------------------------------------
# DEFECT 1 fix -- broker wall-clock reconstruction
# ---------------------------------------------------------------------------

def resolve_broker_times(m5_candles: Sequence[Candle], broker_utc_offset_hours: int
                         ) -> List[datetime]:
    """Reconstruct each candle's BROKER WALL-CLOCK reading from its true-UTC `.time`.

    `mt5.market_data.get_candles` returns `true_utc = broker_wall_clock - offset`, so
    the inverse is `broker_wall_clock = true_utc + offset`. These naive datetimes are
    exactly what `resample_broker_aligned` requires and exactly what
    `mt5_export_loader` passes as `IngestionReport.broker_times` for a CSV covering the
    same window -- so a live-derived D1/H4 bar and a CSV-derived one for the same
    period are built from the same time base.

    Naive by design: this value is a wall-clock READING, not an instant. Never compare
    it to an aware datetime (see mt5/time_contract.py).
    """
    if not isinstance(broker_utc_offset_hours, int):
        raise LiveWatchError(
            "INVALID_BROKER_OFFSET",
            f"broker UTC offset must be an int, got {broker_utc_offset_hours!r}")
    return [(c.time + timedelta(hours=broker_utc_offset_hours)).replace(tzinfo=None)
            for c in m5_candles]


def build_store(symbol: str, m5_candles: Sequence[Candle], broker_utc_offset_hours: int
                ) -> HistoricalCandleStore:
    """Build the replay store with BROKER-ALIGNED H4/D1 (defect 1 fix).

    M15/H1 stay UTC-bucketed, which is correct for whole-hour offsets and matches the
    existing `resampler` contract ("H1/M15 stay correct under plain UTC bucketing").

    Fails closed on an empty feed BEFORE touching the store: a derived series built
    from zero bars has no dataset identity, and letting that surface as a raw
    `ValueError` from the identity layer would obscure the actual cause.
    """
    if not m5_candles:
        raise LiveWatchError(
            "NO_M5_CANDLES_RETURNED", "cannot build a replay store from an empty M5 feed")

    store = HistoricalCandleStore()
    store.load_series(symbol, "M5", list(m5_candles))
    broker_times = resolve_broker_times(m5_candles, broker_utc_offset_hours)
    for tf in DERIVED_UTC_TIMEFRAMES:
        store.load_series(symbol, tf, resample(list(m5_candles), "M5", tf))
    for tf in DERIVED_BROKER_TIMEFRAMES:
        store.load_series(symbol, tf, resample_broker_aligned(
            list(m5_candles), broker_times, "M5", tf))
    return store


# ---------------------------------------------------------------------------
# DEFECT 2 fix -- exact warm-up floor, then incremental evaluation
# ---------------------------------------------------------------------------

def _has_enough_history(store: HistoricalCandleStore, symbol: str, timeframe: str,
                        count: int, as_of: datetime) -> bool:
    """Mirrors `orchestrator._has_enough_history` exactly -- the same predicate
    `run_replay` uses to decide warm-up is cleared, so this module can never disagree
    with the engine about when warm-up ended."""
    try:
        store.closed_candles(symbol, timeframe, as_of, count)
        return True
    except HistoricalDataError:
        return False


def warmup_cleared_at(store: HistoricalCandleStore, symbol: str, as_of: datetime) -> bool:
    return (_has_enough_history(store, symbol, "D1", D1_WARMUP_CANDLES, as_of)
            and _has_enough_history(store, symbol, "H1", H1_WARMUP_CANDLES, as_of)
            and _has_enough_history(store, symbol, "M5", M5_WARMUP_CANDLES, as_of))


def find_warmup_floor(store: HistoricalCandleStore, symbol: str,
                      m5_candles: Sequence[Candle]) -> Optional[datetime]:
    """The earliest M5 close time at which D1/H1/M5 warm-up is cleared, found by binary
    search over the M5 close boundaries.

    Warm-up clearance is monotonic in `as_of` (history only accumulates), so binary
    search is exact, not an approximation. Returns None when even the newest bar cannot
    clear warm-up -- the caller must then fail closed rather than run a replay that
    would silently evaluate zero valid steps.
    """
    if not m5_candles:
        return None

    closes = [c.time + timedelta(minutes=M5_MINUTES) for c in m5_candles]
    if not warmup_cleared_at(store, symbol, closes[-1]):
        return None

    lo, hi = 0, len(closes) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if warmup_cleared_at(store, symbol, closes[mid]):
            hi = mid
        else:
            lo = mid + 1
    return closes[lo]


@dataclass(frozen=True)
class EvaluationWindow:
    """The exact [start, end) the replay clock will step through this run."""

    start_utc: datetime
    end_utc: datetime
    warmup_floor_utc: datetime
    watermark_utc: Optional[datetime]
    steps: int

    @property
    def is_empty(self) -> bool:
        return self.steps <= 0


def determine_evaluation_window(
    store: HistoricalCandleStore, symbol: str, m5_candles: Sequence[Candle],
    watermark_utc: Optional[datetime],
) -> EvaluationWindow:
    """Incremental window: from max(watermark, warm-up floor) to just past the newest
    closed bar.

    `run_replay` treats its range as half-open on the close time (`as_of >= start_utc
    and as_of < end_utc`), and the clock lands exactly on M5 close boundaries, so
    passing the previous run's `next_start_utc` as `watermark_utc` yields a window that
    neither re-evaluates a bar nor skips one.
    """
    if not m5_candles:
        raise LiveWatchError("NO_M5_CANDLES_RETURNED", "no M5 candles to evaluate")

    floor = find_warmup_floor(store, symbol, m5_candles)
    if floor is None:
        raise LiveWatchError(
            "INSUFFICIENT_WARMUP_DATA",
            f"{len(m5_candles)} M5 candles is not enough to clear warm-up "
            f"(needs {D1_WARMUP_CANDLES} closed D1, {H1_WARMUP_CANDLES} H1, "
            f"{M5_WARMUP_CANDLES} M5). Refusing to run: a short window would evaluate "
            "zero valid steps and be indistinguishable from 'no setups found'.")

    last_close = m5_candles[-1].time + timedelta(minutes=M5_MINUTES)
    start = floor if watermark_utc is None else max(floor, watermark_utc)
    # Half-open end: include the newest closed bar's own close instant.
    end = last_close + timedelta(seconds=1)

    steps = sum(1 for c in m5_candles
                if start <= c.time + timedelta(minutes=M5_MINUTES) < end)
    return EvaluationWindow(start, end, floor, watermark_utc, steps)


def check_freshness(m5_candles: Sequence[Candle], now_utc: datetime,
                    max_staleness_hours: float = DEFAULT_MAX_STALENESS_HOURS) -> None:
    """Fail closed on a dead or stale feed."""
    if not m5_candles:
        raise LiveWatchError("NO_M5_CANDLES_RETURNED", "no M5 candles returned")
    last_close = m5_candles[-1].time + timedelta(minutes=M5_MINUTES)
    age = now_utc - last_close
    if age > timedelta(hours=max_staleness_hours):
        raise LiveWatchError(
            "STALE_DATA",
            f"newest closed M5 bar is {last_close.isoformat()} "
            f"({age.total_seconds() / 3600:.1f}h old, limit {max_staleness_hours}h)")


def check_ordering(m5_candles: Sequence[Candle]) -> None:
    """Fail closed on a non-ascending or duplicated series -- resampling and the replay
    clock both assume strictly increasing base bars."""
    for a, b in zip(m5_candles, m5_candles[1:]):
        if b.time <= a.time:
            raise LiveWatchError(
                "OUT_OF_ORDER_OR_DUPLICATE_CANDLES",
                f"{a.time.isoformat()} -> {b.time.isoformat()} is not strictly ascending")


# ---------------------------------------------------------------------------
# Watcher state
# ---------------------------------------------------------------------------

WATCH_STATE_PATH = "journal/large_smc_research/watch_state.json"


@dataclass(frozen=True)
class WatchState:
    strategy_id: str
    strategy_version: str
    symbol: str
    last_evaluated_as_of_utc: Optional[datetime]
    next_start_utc: Optional[datetime]
    runs: int
    last_run_utc: Optional[datetime]
    broker_utc_offset_hours: Optional[int]

    @property
    def has_watermark(self) -> bool:
        return self.next_start_utc is not None


class WatchStateStore:
    """Deterministic, restart-safe watcher watermark. Version-scoped: a strategy
    version bump must point at a new path, never silently inherit the prior version's
    watermark (same discipline as `large_smc_research.live_ledger`)."""

    def __init__(self, path: str = WATCH_STATE_PATH):
        from runtime_state.store import JsonKeyValueStore

        self._store = JsonKeyValueStore(path)

    def _key(self, strategy_id: str, strategy_version: str, symbol: str) -> str:
        return f"{strategy_id}:{strategy_version}:{symbol}"

    def load(self, strategy_id: str, strategy_version: str, symbol: str) -> WatchState:
        raw = self._store.get(self._key(strategy_id, strategy_version, symbol))
        if raw is None:
            return WatchState(strategy_id, strategy_version, symbol, None, None, 0, None, None)
        return WatchState(
            strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol,
            last_evaluated_as_of_utc=_parse(raw.get("last_evaluated_as_of_utc")),
            next_start_utc=_parse(raw.get("next_start_utc")),
            runs=int(raw.get("runs", 0)),
            last_run_utc=_parse(raw.get("last_run_utc")),
            broker_utc_offset_hours=raw.get("broker_utc_offset_hours"),
        )

    def save(self, state: WatchState) -> None:
        self._store.put(self._key(state.strategy_id, state.strategy_version, state.symbol), {
            "strategy_id": state.strategy_id,
            "strategy_version": state.strategy_version,
            "symbol": state.symbol,
            "last_evaluated_as_of_utc": _iso(state.last_evaluated_as_of_utc),
            "next_start_utc": _iso(state.next_start_utc),
            "runs": state.runs,
            "last_run_utc": _iso(state.last_run_utc),
            "broker_utc_offset_hours": state.broker_utc_offset_hours,
        })


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _parse(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Orchestration (pure of MT5 -- the caller supplies candles)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WatchRunResult:
    window: EvaluationWindow
    steps: int
    warmup_steps: int
    valid_steps: int
    setup_rows: int
    identity_collisions: int
    ledger_fold: object
    ledger_total_rows: int
    broker_utc_offset_hours: int
    skipped_no_new_bars: bool


def evaluate_increment(symbol: str, m5_candles: Sequence[Candle],
                       broker_utc_offset_hours: int, state: WatchState):
    """One incremental evaluation. Pure: no MT5, no clock, no I/O beyond the ledger
    fold the caller chooses to do with the result. This is the unit the tests drive."""
    check_ordering(m5_candles)
    store = build_store(symbol, m5_candles, broker_utc_offset_hours)
    window = determine_evaluation_window(store, symbol, m5_candles, state.next_start_utc)

    if window.is_empty:
        return WatchRunResult(
            window=window, steps=0, warmup_steps=0, valid_steps=0, setup_rows=0,
            identity_collisions=0, ledger_fold=None, ledger_total_rows=0,
            broker_utc_offset_hours=broker_utc_offset_hours, skipped_no_new_bars=True,
        )

    result = run_replay(store, symbol, list(m5_candles), window.start_utc, window.end_utc)

    if result.valid_steps == 0:
        # Warm-up was proven clear above, so zero valid steps here means the clock
        # range is degenerate -- surface it rather than report a clean empty result.
        raise LiveWatchError(
            "NO_VALID_STEPS",
            f"replay produced 0 valid steps over [{window.start_utc.isoformat()}, "
            f"{window.end_utc.isoformat()}) despite cleared warm-up")

    return WatchRunResult(
        window=window, steps=result.steps, warmup_steps=result.warmup_steps,
        valid_steps=result.valid_steps, setup_rows=len(result.setup_ledger),
        identity_collisions=result.identity_collisions, ledger_fold=None,
        ledger_total_rows=0, broker_utc_offset_hours=broker_utc_offset_hours,
        skipped_no_new_bars=False,
    )


def next_watermark(window: EvaluationWindow, m5_candles: Sequence[Candle]) -> Tuple[datetime, datetime]:
    """(last_evaluated_as_of, next_start) after a successful run.

    `next_start` is the first M5 close strictly after the last one evaluated, so the
    next run begins exactly where this one stopped -- no overlap, no gap."""
    evaluated = [c.time + timedelta(minutes=M5_MINUTES) for c in m5_candles
                 if window.start_utc <= c.time + timedelta(minutes=M5_MINUTES) < window.end_utc]
    if not evaluated:
        raise LiveWatchError("NO_VALID_STEPS", "no M5 close fell inside the evaluation window")
    last_as_of = evaluated[-1]
    return last_as_of, last_as_of + timedelta(minutes=M5_MINUTES)
