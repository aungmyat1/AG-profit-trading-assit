"""Phase 6 -- fast replay adapter for CRYPTO_CFD_C001 (ST_CRYPTO_CFD_SWEEP_RETEST_V1).

The adapter calls the FROZEN contract (crypto_cfd_contract.rules.evaluate) verbatim,
bar by bar, and adds ONLY the preregistered fill/outcome simulation below. It exposes
no strategy parameter of any kind: no alternative stop, no altered retest window, no
changed target, no session filter, no indicator, no post-result repair. (The optional
structure_config argument is the same test-injection seam the frozen contract's own
test suite uses -- it selects the shared market-structure authority config, it does not
create a tunable strategy surface; production default is the frozen shared config.)

PREREGISTERED FILL / OUTCOME MODEL (REPLAY_FILL_MODEL_V1, frozen before any BTCUSD/
ETHUSD CFD economic result exists in this repository):

  1. Entry fills at the broken swing price during the retest candle (the contract's
     limit level, known at MSS confirmation).
  2. Intrabar ambiguity is resolved PESSIMISTICALLY, always:
       - the entry (retest) candle itself may stop the trade out (same-candle stop
         touch counts); favorable same-candle touches (TP1/TP2) never count;
       - in any later candle that touches both the active stop and a target, the stop
         is assumed hit first.
  3. Position arithmetic follows the frozen targets contract exactly:
       - stop hit before TP1 -> gross_R = -1.0 (full position);
       - TP1 touch realizes 0.5 * R(TP1) and moves the remaining stop to entry;
       - afterwards: breakeven touch -> runner contributes 0.0; TP2 touch ->
         runner contributes 0.5 * R(TP2).
  4. One position per symbol; one setup per symbol per UTC day (the frozen contract
     emits at most one sequence per day). New signals while a position is open are not
     taken. Positions are managed across day boundaries until resolved.
  5. Dataset end with an open position -> mark-to-last-close exit, reason END_OF_DATA.
  6. Costs: net_R = gross_R - cost_R with cost_R from the preregistered friction
     scenarios (friction.py). Never FX pip math.

Asset isolation (fail closed): the dataset must carry EXACTLY the manifest's asset
class and one of its symbols. A USDT-perpetual (or any other near-miss) dataset is
refused with CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN -- perpetual data never silently
substitutes for CFD data. Every replay must pass through the dataset-access ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from market_structure.models import MarketStructureConfig
from strategy_engine.session import Candle

from crypto_cfd_contract import contract as c001_contract
from crypto_cfd_contract.rules import RESULT_ENTRY_VALID, evaluate

from .dataset_ledger import DatasetAccessDenied, DatasetAccessLedger
from .friction import SCENARIOS, cost_r, friction_for
from .models import CandidateManifest

REPLAY_FILL_MODEL_ID = "REPLAY_FILL_MODEL_V1"

CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN = "CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN"
ASSET_CLASS_MISMATCH = "ASSET_CLASS_MISMATCH"

EXIT_STOPPED = "STOPPED"
EXIT_BREAKEVEN_AFTER_TP1 = "BREAKEVEN_AFTER_TP1"
EXIT_TP2 = "TP2_HIT"
EXIT_END_OF_DATA = "END_OF_DATA"

_M5 = timedelta(minutes=5)


class InstrumentIsolationError(ValueError):
    """Dataset instrument/asset-class does not exactly match the candidate manifest."""


@dataclass(frozen=True)
class CandleDataset:
    """Replay input. h1/d1 candles are optional explicit series from the same
    provenance; when absent they are derived from M5 by deterministic resampling."""

    dataset_id: str
    symbol: str
    asset_class: str
    role: str
    m5_candles: Tuple[Candle, ...]
    provenance: str = ""
    h1_candles: Tuple[Candle, ...] = ()
    d1_candles: Tuple[Candle, ...] = ()


@dataclass(frozen=True)
class TradeRecord:
    candidate_id: str
    dataset_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    direction: str
    sweep_time_utc: str
    mss_time_utc: str
    retest_time_utc: str
    entry_time_utc: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    risk_distance: float
    gross_r: float
    cost_r: float
    net_r: float
    exit_time_utc: str
    exit_reason: str
    friction_scenario: str
    fill_model: str
    h1_regime_at_entry: str
    entry_hour_utc: int


def _resample(m5: Sequence[Candle], minutes: int, before: datetime) -> List[Candle]:
    """Deterministic OHLC resampling of closed M5 bars into `minutes` buckets whose
    bucket window ends at or before `before` (only fully elapsed buckets)."""
    buckets: dict = {}
    step = timedelta(minutes=minutes)
    for c in m5:
        epoch_min = int(c.time.timestamp() // 60)
        start_min = epoch_min - (epoch_min % minutes)
        start = datetime.fromtimestamp(start_min * 60, tz=timezone.utc)
        buckets.setdefault(start, []).append(c)
    out = []
    for start in sorted(buckets):
        if start + step > before:
            continue
        group = sorted(buckets[start], key=lambda c: c.time)
        out.append(Candle(time=start, open=group[0].open,
                          high=max(c.high for c in group),
                          low=min(c.low for c in group),
                          close=group[-1].close, volume=None))
    return out


def _check_isolation(manifest: CandidateManifest, dataset: CandleDataset) -> None:
    if dataset.symbol not in manifest.symbols:
        raise InstrumentIsolationError(
            f"{CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN}: dataset symbol "
            f"{dataset.symbol!r} is not a candidate symbol {list(manifest.symbols)}; "
            "perpetual/near-miss instruments never substitute for the CFD")
    if dataset.asset_class != manifest.asset_class:
        raise InstrumentIsolationError(
            f"{ASSET_CLASS_MISMATCH}: dataset {dataset.asset_class!r} != "
            f"candidate {manifest.asset_class!r}")
    if dataset.symbol not in c001_contract.INSTRUMENTS:
        raise InstrumentIsolationError(
            f"{CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN}: {dataset.symbol!r} is outside "
            f"the frozen contract scope {list(c001_contract.INSTRUMENTS)}")


@dataclass
class _OpenPosition:
    direction: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    risk: float
    realized_r: float = 0.0
    tp1_done: bool = False

    def r_to(self, price: float) -> float:
        move = (price - self.entry) if self.direction == "LONG" else (self.entry - price)
        return move / self.risk

    def manage(self, bar: Candle, entry_bar: bool = False) -> Optional[Tuple[float, str]]:
        """Apply the preregistered pessimistic rules to one closed M5 bar. Returns
        (gross_r, exit_reason) when the position fully closes, else None."""
        hit = (lambda level: bar.high >= level) if self.direction == "SHORT" else \
              (lambda level: bar.low <= level)        # adverse side touch
        fav = (lambda level: bar.low <= level) if self.direction == "SHORT" else \
              (lambda level: bar.high >= level)       # favorable side touch

        if not self.tp1_done:
            if hit(self.stop):                        # pessimistic: stop checked first
                return -1.0, EXIT_STOPPED
            if entry_bar:                             # favorable same-candle touches never count
                return None
            if fav(self.tp1):
                self.realized_r += 0.5 * self.r_to(self.tp1)
                self.tp1_done = True
                self.stop = self.entry                # breakeven
            return None
        if hit(self.stop):                            # breakeven exit, pessimistic first
            return self.realized_r, EXIT_BREAKEVEN_AFTER_TP1
        if fav(self.tp2):
            return self.realized_r + 0.5 * self.r_to(self.tp2), EXIT_TP2
        return None

    def mark_to_close(self, price: float) -> float:
        open_fraction = 0.5 if self.tp1_done else 1.0
        return self.realized_r + open_fraction * self.r_to(price)


def replay_c001(manifest: CandidateManifest, dataset: CandleDataset,
                ledger: DatasetAccessLedger, friction_scenario: str,
                access_reason: str = "FAST_SCREEN_DEV_REPLAY",
                structure_config: Optional[MarketStructureConfig] = None,
                governance_approval_id: Optional[str] = None) -> List[TradeRecord]:
    """Replay the frozen C001 contract over one dataset. Pure given its inputs."""
    if manifest.strategy_id != c001_contract.CONTRACT_ID:
        raise ValueError(f"this adapter only replays {c001_contract.CONTRACT_ID}")
    if friction_scenario not in SCENARIOS:
        raise KeyError(f"unknown friction scenario {friction_scenario!r}")
    _check_isolation(manifest, dataset)

    access = ledger.request_access(manifest, dataset.dataset_id, dataset.role,
                                   access_reason, result_visibility="METRICS_VISIBLE",
                                   governance_approval_id=governance_approval_id)
    if not access.granted:
        raise DatasetAccessDenied(access)

    m5 = sorted(dataset.m5_candles, key=lambda c: c.time)
    friction = friction_for(dataset.symbol, friction_scenario)
    trades: List[TradeRecord] = []
    pos: Optional[_OpenPosition] = None
    pending: Optional[dict] = None
    traded_days: set = set()

    def close_trade(info: dict, gross: float, reason: str, exit_time: datetime) -> None:
        cost = cost_r(dataset.symbol, friction_scenario, info["risk"])
        trades.append(TradeRecord(
            candidate_id=manifest.candidate_id, dataset_id=dataset.dataset_id,
            strategy_id=manifest.strategy_id, strategy_version=manifest.strategy_version,
            symbol=dataset.symbol, direction=info["direction"],
            sweep_time_utc=info["sweep_time"], mss_time_utc=info["mss_time"],
            retest_time_utc=info["retest_time"], entry_time_utc=info["retest_time"],
            entry=info["entry"], stop=info["stop"], tp1=info["tp1"], tp2=info["tp2"],
            risk_distance=info["risk"], gross_r=gross, cost_r=cost, net_r=gross - cost,
            exit_time_utc=exit_time.isoformat(), exit_reason=reason,
            friction_scenario=friction.scenario, fill_model=REPLAY_FILL_MODEL_ID,
            h1_regime_at_entry=info["h1_regime"], entry_hour_utc=info["entry_hour"]))

    for i, bar in enumerate(m5):
        bar_close = bar.time + _M5

        if pos is not None:
            done = pos.manage(bar)
            if done is not None:
                gross, reason = done
                close_trade(pending, gross, reason, bar_close)
                pos, pending = None, None
            continue

        day = bar.time.date()
        if day in traded_days:
            continue

        closed = m5[: i + 1]
        h1 = (sorted((c for c in dataset.h1_candles if c.time + timedelta(hours=1) <= bar_close),
                     key=lambda c: c.time)
              if dataset.h1_candles else _resample(closed, 60, bar_close))
        d1 = (sorted((c for c in dataset.d1_candles if c.time + timedelta(days=1) <= bar_close),
                     key=lambda c: c.time)
              if dataset.d1_candles else _resample(closed, 1440, bar_close))

        result = evaluate(dataset.symbol, bar_close, d1, h1, closed,
                          structure_config=structure_config)
        if result["result"] != RESULT_ENTRY_VALID:
            continue

        ev = result["evidence"]
        plan = ev["target_plan"]
        retest_time = datetime.fromisoformat(ev["retest"]["candle_time_utc"])
        pos = _OpenPosition(direction=plan["direction"], entry=plan["entry"],
                            stop=plan["stop_loss"], tp1=plan["tp1"], tp2=plan["tp2"],
                            risk=plan["risk_distance"])
        pending = {
            "direction": plan["direction"], "entry": plan["entry"],
            "stop": plan["stop_loss"], "tp1": plan["tp1"], "tp2": plan["tp2"],
            "risk": plan["risk_distance"],
            "sweep_time": ev["sweep"]["candle_time_utc"],
            "mss_time": ev["mss"]["confirmed_at_utc"],
            "retest_time": ev["retest"]["candle_time_utc"],
            "h1_regime": ev["context"]["h1_structure"],
            "entry_hour": retest_time.hour,
        }
        traded_days.add(day)

        done = pos.manage(bar, entry_bar=True)   # same-candle stop check, pessimistic
        if done is not None:
            gross, reason = done
            close_trade(pending, gross, reason, bar_close)
            pos, pending = None, None

    if pos is not None and m5:
        close_trade(pending, pos.mark_to_close(m5[-1].close), EXIT_END_OF_DATA,
                    m5[-1].time + _M5)

    return trades
