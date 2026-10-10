"""ST_LARGE_SMC_V1@1.1.0 watch -- operational snapshot, persistent tracker, ARCHIVE_ONLY alert journal.

evaluate_snapshot() uses closed candles, `now_utc` and the configured operational
remaining-reward threshold. Candles that close after `now_utc` are dropped before
anything is computed, so the result cannot use future data.

WatchTracker persists the last watch state per symbol and turns snapshot changes into
alert transitions. Each transition has a deterministic id. It is archived through the
existing ticket_delivery journal (archive_cycle_decision -> report_archive.write_report,
which is atomic and idempotent), one file per transition, so a restart or a duplicate
poll on the same data is a no-op. Nothing is ever sent: there is no transport in this
package or in ticket_delivery.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

import yaml

from fx_discovery import features as F
from host_delivery.lsmc_actionability_config import remaining_fraction
from large_smc_core.c10_stop_policy import C10StopPolicyViolation, compute_c10_stop
from post_asian_pilot.report_archive import archive_path
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle
from ticket_delivery.archive import (
    CYCLE_STATE_DATA_ERROR,
    CYCLE_STATE_NO_TRADE,
    CYCLE_STATE_WATCH,
    CycleDecisionRecord,
    _report_type,
    archive_cycle_decision,
)

from . import contract as C
from .detect import (
    POI,
    bias_at,
    c11_causal_target,
    close_time,
    h1_pois,
    m5_opportunities,
    tolerant_breaks,
)

NY = ZoneInfo(C.DAY_BOUNDARY_TZ)
UTC = dt.timezone.utc
ACTIVE_STATES = ("DEVELOPING", "NEAR_POI", "OPPORTUNITY")
DELIVERY_MODE = "ARCHIVE_ONLY"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _remaining_fraction(root: Path) -> Optional[float]:
    """Missing/malformed host thresholds have no fallback."""
    return remaining_fraction(root)


def opportunity_rejection(opportunity: dict, current_price: Optional[float], *,
                          root: Optional[Path] = None) -> Optional[str]:
    """Delivery eligibility only; levels and detection evidence are never repaired.

    No R:R minimum is authorized by the 1.1.0 contract. The remaining-reward
    fraction is a separate owner-set operational parameter, not an R:R rule.
    """
    entry, stop, target = (opportunity.get(k) for k in ("entry_reference", "stop_c10", "target_c11"))
    sign = {"LONG": 1, "SHORT": -1}.get(opportunity.get("direction"))
    if sign is None or not _finite(entry) or entry <= 0:
        return "REJECT_NO_STOP"
    if not _finite(stop) or stop <= 0 or opportunity.get("stop_reason") or sign * (entry - stop) <= 0:
        return "REJECT_NO_STOP"
    if not _finite(target) or target <= 0 or opportunity.get("target_reason") or sign * (target - entry) <= 0:
        return "REJECT_NO_TARGET"
    threshold = _remaining_fraction(REPO_ROOT if root is None else root)
    if threshold is None or not _finite(current_price) or current_price <= 0:
        return "REJECT_STALE"
    if sign * (current_price - stop) <= 0 or (target - current_price) / (target - entry) < threshold:
        return "REJECT_STALE"
    return None


def gate_opportunity(snap: "Snapshot", current_price: Optional[float]) -> "Snapshot":
    if snap.state != "OPPORTUNITY":
        return snap
    reason = opportunity_rejection(snap.opportunity or {}, current_price)
    return replace(snap, state="REJECTED", reason_codes=(reason,) + snap.reason_codes) if reason else snap


def trading_date(t: dt.datetime) -> dt.date:
    """NY 17:00 day boundary: 17:00 New York (DST-aware) starts the next trading date."""
    local = t.astimezone(NY)
    return (local + dt.timedelta(hours=24 - C.DAY_BOUNDARY_HOUR)).date()


def next_day_boundary(t: dt.datetime) -> dt.datetime:
    local = t.astimezone(NY)
    boundary = local.replace(hour=C.DAY_BOUNDARY_HOUR, minute=0, second=0, microsecond=0)
    if local >= boundary:
        boundary = (local + dt.timedelta(days=1)).replace(hour=C.DAY_BOUNDARY_HOUR, minute=0, second=0, microsecond=0)
    return boundary.astimezone(UTC)


def fx_market_closed(t: dt.datetime) -> bool:
    """FX weekend: Friday 17:00 New York until Sunday 17:00 New York."""
    local = t.astimezone(NY)
    wd, hour = local.weekday(), local.hour
    return (wd == 4 and hour >= C.DAY_BOUNDARY_HOUR) or wd == 5 or (wd == 6 and hour < C.DAY_BOUNDARY_HOUR)


def _canonical_sessions(path: str = "config/canonical_sessions.yaml"):
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    out = []
    for name, s in raw["sessions"].items():
        sh, sm = map(int, s["start"].split(":"))
        eh, em = map(int, s["end"].split(":"))
        out.append((name, sh * 60 + sm, eh * 60 + em))
    return out


def session_end(t: dt.datetime, sessions=None) -> dt.datetime:
    """Opportunity expiry = end of the canonical UTC session containing `t` (half-open).
    Outside every canonical session it is the next NY 17:00 trading-day boundary."""
    sessions = sessions or _canonical_sessions()
    u = t.astimezone(UTC)
    minute = u.hour * 60 + u.minute
    for _name, start, end in sessions:
        if start <= minute < end:
            return u.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(minutes=end)
    return next_day_boundary(u)


def _closed(bars: Sequence[Candle], minutes: int, now: dt.datetime) -> List[Candle]:
    return [b for b in bars if close_time(b, minutes) <= now]


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    evaluated_at: str
    state: str                      # MARKET_CLOSED | DATA_ERROR | STALE | IDLE | DEVELOPING | NEAR_POI | OPPORTUNITY
    reason_codes: tuple = ()
    bias: Optional[str] = None
    d1_context: Optional[str] = None
    point: Optional[float] = None
    metadata_source: str = "MISSING"
    poi: Optional[dict] = None
    opportunity: Optional[dict] = None
    invalidated_poi_ids: tuple = ()
    expired_poi_ids: tuple = ()
    invalidated_opportunity_ids: tuple = ()
    expired_opportunity_ids: tuple = ()


def _poi_age_days(poi: POI, h1: Sequence[Candle], now: dt.datetime) -> int:
    dates = {trading_date(b.time) for b in h1 if b.time >= poi.origin_time}
    dates.add(trading_date(now))
    return len(dates) - 1


def evaluate_snapshot(
    symbol: str, d1: Sequence[Candle], h1: Sequence[Candle], m5: Sequence[Candle], now_utc: dt.datetime,
    bid: Optional[float] = None, ask: Optional[float] = None,
) -> Snapshot:
    now = now_utc.astimezone(UTC)
    base = dict(symbol=symbol, evaluated_at=now.isoformat())
    if symbol not in C.V1_SYMBOLS:
        return Snapshot(state="DATA_ERROR", reason_codes=("SYMBOL_NOT_IN_V1_UNIVERSE",), **base)
    if symbol not in C.CRYPTO_SYMBOLS and fx_market_closed(now):
        return Snapshot(state="MARKET_CLOSED", reason_codes=("FX_WEEKEND",), **base)
    pt, src = C.resolve_point(symbol)
    if pt is None:
        return Snapshot(state="DATA_ERROR", reason_codes=("SYMBOL_METADATA_MISSING",), **base)
    base.update(point=pt, metadata_source=src)
    d1c = _closed(d1, C.TIMEFRAME_MINUTES["D1"], now)
    h1c = _closed(h1, C.TIMEFRAME_MINUTES["H1"], now)
    m5c = _closed(m5, C.TIMEFRAME_MINUTES["M5"], now)
    if len(h1c) < C.MIN_H1_BARS or len(m5c) < C.MIN_M5_BARS:
        return Snapshot(state="DATA_ERROR", reason_codes=("INSUFFICIENT_HISTORY",), **base)
    last_m5_close = close_time(m5c[-1], C.TIMEFRAME_MINUTES["M5"])
    if now - last_m5_close > dt.timedelta(minutes=C.STALE_AFTER_MINUTES):
        return Snapshot(state="STALE", reason_codes=("M5_DATA_STALE",), **base)

    tol = C.TIE_TOLERANCE_POINTS * pt
    h1_breaks = tolerant_breaks(h1c, F.swings(h1c, C.SWING_K), tol)
    bias = bias_at(h1_breaks, len(h1c) - 1)
    d1_context = bias_at(tolerant_breaks(d1c, F.swings(d1c, C.SWING_K), tol), len(d1c) - 1) if d1c else None
    atr = F.atr(h1c, C.ATR_H1_PERIOD)[-1]
    if atr is None:
        return Snapshot(state="DATA_ERROR", reason_codes=("ATR_NOT_READY",), **base)
    base.update(bias=bias, d1_context=d1_context)

    pois = h1_pois(symbol, h1c, h1_breaks)

    def expires_at(p: POI) -> dt.datetime:
        # valid while its age is <= POI_MAX_AGE trading days; expiry at the boundary after that
        t = p.origin_time
        for _ in range(C.POI_MAX_AGE_TRADING_DAYS + 1):
            t = next_day_boundary(t)
        return t

    def valid_at(p: POI, t: dt.datetime) -> bool:
        return p.known_time <= t and (p.invalidated_time is None or t < p.invalidated_time) and t < expires_at(p)

    known = [p for p in pois if p.known_time <= now]
    invalidated = tuple(p.poi_id for p in known if p.invalidated_time is not None and p.invalidated_time <= now)
    expired = tuple(p.poi_id for p in known if p.poi_id not in invalidated and now >= expires_at(p))

    opps = m5_opportunities(m5c, known, valid_at, tol)
    sessions = _canonical_sessions()
    active_opp, inv_opp, exp_opp = None, [], []
    for o in opps:
        expiry = session_end(o.choch_time + dt.timedelta(minutes=C.TIMEFRAME_MINUTES["M5"]), sessions)
        if o.invalidated_time is not None and o.invalidated_time <= now:
            inv_opp.append(o.opp_id)
        elif now >= expiry:
            exp_opp.append(o.opp_id)
        elif o.direction == bias:
            active_opp = (o, expiry)
    common = dict(invalidated_poi_ids=invalidated, expired_poi_ids=expired,
                  invalidated_opportunity_ids=tuple(inv_opp), expired_opportunity_ids=tuple(exp_opp))

    if active_opp is not None:
        o, expiry = active_opp
        stop, stop_reason = None, None
        if symbol in C.C10_PIP_SIZE:
            try:
                stop = compute_c10_stop(o.direction, o.sweep_extreme, bid, ask, m5c[: o.choch_index + 1],
                                        pip_size=C.C10_PIP_SIZE[symbol]).stop_price
            except C10StopPolicyViolation as exc:
                stop_reason = exc.reason_code
        else:
            stop_reason = "C10_PIP_SIZE_NOT_EVIDENCED"
        target = c11_causal_target(m5c, o.direction, o.entry_reference, len(m5c) - 1)
        poi = next(p for p in known if p.poi_id == o.poi_id)
        return gate_opportunity(Snapshot(
            state="OPPORTUNITY", reason_codes=("D30_BADGE_ECONOMICS_NOT_EVALUATED",), **base, **common,
            poi=_poi_dict(poi), opportunity={
                **{k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in asdict(o).items()},
                "expires_at": expiry.isoformat(), "stop_c10": stop, "stop_reason": stop_reason,
                "target_c11": target, "target_reason": None if target is not None else "REJECT_NO_TARGET",
                "target_tier": "C11_FALLBACK_M5_SWING_CAUSAL", "economic_status": C.ECONOMIC_STATUS,
            },
        ), m5c[-1].close)

    live = [p for p in known if p.direction == bias and valid_at(p, now)]
    if bias is None or not live:
        return Snapshot(state="IDLE", reason_codes=("NO_BIAS" if bias is None else "NO_VALID_POI",), **base, **common)
    price = m5c[-1].close
    band = C.NEAR_POI_BAND_ATR_MULT * atr

    def distance(p: POI) -> float:
        if p.low <= price <= p.high:
            return 0.0
        return price - p.high if bias == "LONG" else p.low - price

    candidates = [p for p in live if distance(p) >= 0]
    if not candidates:
        return Snapshot(state="IDLE", reason_codes=("NO_POI_AHEAD_OF_PRICE",), **base, **common)
    poi = min(candidates, key=lambda p: (distance(p), -p.known_time.timestamp()))
    state = "NEAR_POI" if distance(poi) <= band else "DEVELOPING"
    return Snapshot(state=state, **base, **common, poi={**_poi_dict(poi), "distance": distance(poi), "band": band})


def _poi_dict(p: POI) -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in asdict(p).items()}


@dataclass(frozen=True)
class AlertEvent:
    transition_id: str
    symbol: str
    from_state: Optional[str]
    to_state: str
    alert_level: str
    reference_id: Optional[str]
    evaluated_at: str
    trading_date: str
    delivery_mode: str = DELIVERY_MODE
    strategy_id: str = C.STRATEGY_ID
    strategy_version: str = C.STRATEGY_VERSION
    proposal_generation_authorized: bool = C.PROPOSAL_GENERATION_AUTHORIZED
    payload: dict = field(default_factory=dict)


_ARCHIVE_STATE = {"DEVELOPING": CYCLE_STATE_WATCH, "NEAR_POI": CYCLE_STATE_WATCH, "OPPORTUNITY": CYCLE_STATE_WATCH,
                  "INVALIDATED": CYCLE_STATE_NO_TRADE, "EXPIRED": CYCLE_STATE_NO_TRADE,
                  "REJECTED": CYCLE_STATE_NO_TRADE}


class WatchTracker:
    """Persistent per-symbol watch state. `poll()` never sends anything; it archives
    alert events (ARCHIVE_ONLY) and returns them."""

    def __init__(self, state_path: str, archive_root: str, application_release: str = "AG_V1_CLOUD"):
        self.store = JsonKeyValueStore(state_path)
        self.archive_root = archive_root
        self.release = application_release

    def poll(self, snap: Snapshot) -> List[AlertEvent]:
        prev: Dict = self.store.get(snap.symbol) or {"state": None}
        prev_state = prev.get("state")
        now = dt.datetime.fromisoformat(snap.evaluated_at)
        transitions: List[tuple] = []  # (to_state, reference_id, payload)

        if snap.state == "MARKET_CLOSED":
            return []
        if snap.state in ("STALE", "DATA_ERROR"):
            if prev_state in ACTIVE_STATES:
                self._save(snap.symbol, {**prev, "state": "SUSPENDED", "suspended_from": prev_state,
                                         "suspended_at": snap.evaluated_at, "reason_codes": list(snap.reason_codes)})
            elif prev_state == "SUSPENDED" and prev.get("expires_at") and now >= dt.datetime.fromisoformat(prev["expires_at"]):
                transitions.append(("EXPIRED", prev.get("reference_id"), {"cause": "STALE_PAST_EXPIRY"}))
            return self._emit(snap, prev, transitions)

        ref = prev.get("reference_id")
        if prev_state in ACTIVE_STATES + ("SUSPENDED",) and ref:
            if ref in snap.invalidated_opportunity_ids or ref in snap.invalidated_poi_ids:
                transitions.append(("INVALIDATED", ref, {}))
            elif ref in snap.expired_opportunity_ids or ref in snap.expired_poi_ids:
                transitions.append(("EXPIRED", ref, {}))

        new_ref = (snap.opportunity or {}).get("opp_id") or (snap.poi or {}).get("poi_id")
        current_state = transitions[-1][0] if transitions else prev_state
        current_ref = transitions[-1][1] if transitions else ref
        if snap.state in ACTIVE_STATES + ("REJECTED",) and (snap.state != current_state or new_ref != current_ref):
            payload = {"poi": snap.poi, "opportunity": snap.opportunity}
            if snap.state == "REJECTED":
                payload["reason_codes"] = list(snap.reason_codes)
            transitions.append((snap.state, new_ref, payload))
        elif snap.state == "IDLE" and current_state in ACTIVE_STATES + ("SUSPENDED",):
            self._save(snap.symbol, {**prev, "state": "IDLE", "reference_id": None})
        return self._emit(snap, prev, transitions)

    def _emit(self, snap: Snapshot, prev: Dict, transitions: List[tuple]) -> List[AlertEvent]:
        events: List[AlertEvent] = []
        from_state = prev.get("state")
        seq = int(prev.get("seq", 0))
        now = dt.datetime.fromisoformat(snap.evaluated_at)
        for to_state, ref, payload in transitions:
            seq += 1
            tid = hashlib.sha256(
                f"{C.STRATEGY_ID}|{C.STRATEGY_VERSION}|{snap.symbol}|{seq}|{from_state}|{to_state}|{ref}".encode()
            ).hexdigest()[:24]
            ev = AlertEvent(tid, snap.symbol, from_state, to_state,
                            "INFO" if to_state == "REJECTED" else C.ALERT_LEVEL[to_state], ref,
                            snap.evaluated_at, trading_date(now).isoformat(),
                            payload={**payload, "bias": snap.bias, "d1_context": snap.d1_context,
                                     "metadata_source": snap.metadata_source})
            record = CycleDecisionRecord(
                strategy_id=C.STRATEGY_ID, strategy_version=C.STRATEGY_VERSION, application_release=self.release,
                symbol=snap.symbol, cycle=f"LSMC_WATCH-{tid}", trading_date=trading_date(now),
                cycle_state=_ARCHIVE_STATE.get(to_state, CYCLE_STATE_DATA_ERROR),
                evaluation_time_utc=snap.evaluated_at, payload=asdict(ev), reason_codes=tuple(snap.reason_codes),
            )
            # Exactly-once: a transition already archived (restart / replay after a crash
            # between archive and state save) is never rewritten or duplicated.
            if not os.path.exists(archive_path(_report_type(record.strategy_id, record.symbol, record.cycle),
                                               record.trading_date, self.archive_root)):
                archive_cycle_decision(record, root=self.archive_root)
            events.append(ev)
            from_state = to_state
        if transitions:
            to_state, ref, _payload = transitions[-1]
            expires_at = (snap.opportunity or {}).get("expires_at") if to_state == "OPPORTUNITY" else (
                next_day_boundary(now).isoformat() if to_state in ACTIVE_STATES else None)
            self._save(snap.symbol, {"state": to_state, "reference_id": ref, "expires_at": expires_at,
                                     "last_transition_id": events[-1].transition_id, "seq": seq})
        return events

    def _save(self, symbol: str, value: Dict) -> None:
        self.store.put(symbol, value)
