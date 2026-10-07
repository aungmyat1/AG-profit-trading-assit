"""Post-signal ACTIONABILITY gate for Large-SMC OPPORTUNITY alerts (LSMC_ACTIONABILITY_POLICY_V1).

Authority: docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md. Signal validity
(strategy) and actionability (delivery) are separate layers: an opportunity that was VALID at its
trigger bar may be NOT ACTIONABLE at send time, and both facts are persisted. This module only
decides how an already-detected opportunity is delivered. It never changes detection, watch state
transitions, archive records or any strategy threshold; `min_remaining_r` lives only in the
versioned operational policy config.

Pipeline: Strategy -> deterministic opportunity -> assess() -> WATCH_READY | INFO_ONLY_STALE |
INFO_ONLY(reason) | EXPIRED | MISSED_NOT_ACTIONABLE (digest only) | none (PENDING_BAR_CLOSE).
Gate order (D7): validity > freshness > geometry > remaining R.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from runtime_state.store import JsonKeyValueStore

POLICY_PATH = os.path.join("config", "lsmc_actionability_policy_v1.yaml")
POLICY_ID = "LSMC_ACTIONABILITY_POLICY_V1"
TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60}
UTC = dt.timezone.utc

# Opportunity states (D4)
PENDING_BAR_CLOSE = "PENDING_BAR_CLOSE"
FRESH = "FRESH"
STALE = "STALE"
EXPIRED = "EXPIRED"
MISSED_DOWNTIME = "MISSED_DOWNTIME"

# Delivery outcomes
WATCH_READY = "WATCH_READY"
INFO_ONLY_STALE = "INFO_ONLY_STALE"
INFO_ONLY = "INFO_ONLY"
MISSED_NOT_ACTIONABLE = "MISSED_NOT_ACTIONABLE"
SENT_OUTCOMES = (WATCH_READY, INFO_ONLY_STALE, INFO_ONLY)      # delivered as an individual alert

# INFO_ONLY reasons
INSUFFICIENT_REMAINING_R = "INSUFFICIENT_REMAINING_R"           # D2
GEOMETRY_INCOMPLETE = "GEOMETRY_INCOMPLETE"                     # no target / no risk anchor
SEND_PRICE_UNAVAILABLE = "SEND_PRICE_UNAVAILABLE"               # no live bid/ask: fail closed
PRICE_BEYOND_INVALIDATION = "PRICE_BEYOND_INVALIDATION"         # send price at/through the risk anchor
POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"                       # config missing/invalid: fail closed


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    policy_id: str
    policy_version: int
    freshness_max_bars: int
    trigger_timeframe: str
    min_remaining_r: float

    @property
    def trigger_minutes(self) -> int:
        return TIMEFRAME_MINUTES[self.trigger_timeframe]


def load_policy(root: str = ".") -> Policy:
    """Strict load: any missing or malformed field raises PolicyError (callers fail closed)."""
    try:
        with open(os.path.join(root, POLICY_PATH), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        policy = Policy(
            policy_id=str(raw["policy_id"]), policy_version=int(raw["policy_version"]),
            freshness_max_bars=int(raw["freshness_max_bars"]), trigger_timeframe=str(raw["trigger_timeframe"]),
            min_remaining_r=float(raw["min_remaining_r"]),
        )
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise PolicyError(f"{POLICY_PATH}: {type(exc).__name__}") from None
    if (policy.policy_id != POLICY_ID or policy.trigger_timeframe not in TIMEFRAME_MINUTES
            or policy.freshness_max_bars < 0 or not policy.min_remaining_r > 0):
        raise PolicyError(f"{POLICY_PATH}: invalid values")
    return policy


def _ts(v: Any) -> Optional[dt.datetime]:
    if v is None:
        return None
    t = v if isinstance(v, dt.datetime) else dt.datetime.fromisoformat(str(v))
    return t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)


def send_price(direction: Optional[str], bid: Optional[float], ask: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """Executable side of a market entry: LONG buys at ASK, SHORT sells at BID."""
    price, side = (ask, "ASK") if direction == "LONG" else (bid, "BID") if direction == "SHORT" else (None, None)
    if price is None or not float(price) > 0:
        return None, None
    return float(price), side


def r_multiple(direction: Optional[str], price: Optional[float], anchor: Optional[float],
               target: Optional[float]) -> Optional[float]:
    """Reward / risk measured from `price`. None when undefined (missing level, or price at or
    beyond the risk anchor). Negative when price has already passed the target."""
    if direction not in ("LONG", "SHORT") or price is None or anchor is None or target is None:
        return None
    sign = 1.0 if direction == "LONG" else -1.0
    risk = sign * (price - anchor)
    if not risk > 0:
        return None
    return sign * (target - price) / risk


def risk_anchor(opportunity: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    """The C10 stop when the strategy produced one, else the opportunity invalidation level
    (sweep extreme). The source is persisted with every assessment."""
    if opportunity.get("stop_c10") is not None:
        return float(opportunity["stop_c10"]), "STOP_C10"
    if opportunity.get("sweep_extreme") is not None:
        return float(opportunity["sweep_extreme"]), "INVALIDATION_SWEEP_EXTREME"
    return None, None


def assess(opportunity: Dict[str, Any], *, send_ts: dt.datetime, bid: Optional[float], ask: Optional[float],
           policy: Optional[Policy], last_heartbeat_ts: Optional[dt.datetime]) -> Dict[str, Any]:
    """Deterministic actionability of one opportunity at `send_ts`. Pure: no I/O.

    `last_heartbeat_ts` is the evaluation time of the previous watch run (None = no earlier run
    on record). A trigger bar that closed after it, and is no longer fresh, was missed because the
    host was not watching (D3): it is MISSED_DOWNTIME and only ever reported in the digest."""
    send = _ts(send_ts)
    direction = opportunity.get("direction")
    reference = opportunity.get("entry_reference")
    anchor, anchor_source = risk_anchor(opportunity)
    target = opportunity.get("target_c11")
    price, side = send_price(direction, bid, ask)
    rec: Dict[str, Any] = {
        "policy_id": policy.policy_id if policy else POLICY_ID,
        "policy_version": policy.policy_version if policy else None,
        "min_remaining_r": policy.min_remaining_r if policy else None,
        "freshness_max_bars": policy.freshness_max_bars if policy else None,
        "trigger_timeframe": policy.trigger_timeframe if policy else None,
        "direction": direction, "send_ts": send.isoformat(),
        "reference_price": reference, "send_price": price, "send_price_side": side, "bid": bid, "ask": ask,
        "risk_anchor": anchor, "risk_anchor_source": anchor_source, "target": target,
        "R_AT_TRIGGER": r_multiple(direction, reference, anchor, target),
        "R_AT_SEND": r_multiple(direction, price, anchor, target),
        "expires_at": opportunity.get("expires_at"),
        "last_heartbeat_ts": last_heartbeat_ts.isoformat() if last_heartbeat_ts else None,
        "trigger_bar_close_ts": None, "freshness_age_seconds": None, "completed_bars_since_trigger": None,
        "state": None, "outcome": None, "reason": None,
    }
    if policy is None:
        return {**rec, "outcome": INFO_ONLY, "reason": POLICY_UNAVAILABLE}

    tf = dt.timedelta(minutes=policy.trigger_minutes)
    trigger_open = _ts(opportunity.get("choch_time"))
    trigger_close = trigger_open + tf if trigger_open is not None else None
    rec["trigger_bar_close_ts"] = trigger_close.isoformat() if trigger_close else None
    # D4: a required bar that has not closed is PENDING_BAR_CLOSE (never STALE); nothing is sent.
    if trigger_close is None or send < trigger_close:
        return {**rec, "state": PENDING_BAR_CLOSE}
    age = send - trigger_close
    rec.update(freshness_age_seconds=age.total_seconds(), completed_bars_since_trigger=int(age // tf))
    missed = last_heartbeat_ts is None or trigger_close > _ts(last_heartbeat_ts)
    expires = _ts(opportunity.get("expires_at"))
    if expires is not None and send >= expires:
        state = MISSED_DOWNTIME if missed else EXPIRED
    elif age <= policy.freshness_max_bars * tf:                 # D1
        state = FRESH
    else:
        state = MISSED_DOWNTIME if missed else STALE
    if state == MISSED_DOWNTIME:
        return {**rec, "state": state, "outcome": MISSED_NOT_ACTIONABLE}    # D3: digest only
    if state == EXPIRED:
        return {**rec, "state": state, "outcome": EXPIRED}
    if state == STALE:
        return {**rec, "state": state, "outcome": INFO_ONLY_STALE}
    if anchor is None or target is None or rec["R_AT_TRIGGER"] is None:
        return {**rec, "state": state, "outcome": INFO_ONLY, "reason": GEOMETRY_INCOMPLETE}
    if price is None:
        return {**rec, "state": state, "outcome": INFO_ONLY, "reason": SEND_PRICE_UNAVAILABLE}
    if rec["R_AT_SEND"] is None:
        return {**rec, "state": state, "outcome": INFO_ONLY, "reason": PRICE_BEYOND_INVALIDATION}
    if rec["R_AT_SEND"] < policy.min_remaining_r:              # D2
        return {**rec, "state": state, "outcome": INFO_ONLY, "reason": INSUFFICIENT_REMAINING_R}
    return {**rec, "state": state, "outcome": WATCH_READY}


class Heartbeat:
    """Evaluation time of the last completed watch run (any run means the host was watching)."""

    KEY = "LSMC"

    def __init__(self, path: str):
        self.store = JsonKeyValueStore(path)

    def last(self) -> Optional[dt.datetime]:
        v = self.store.get(self.KEY)
        return _ts(v.get("evaluated_at")) if isinstance(v, dict) else None

    def beat(self, at: dt.datetime) -> None:
        self.store.put(self.KEY, {"evaluated_at": _ts(at).isoformat()})


class MissedDigestLedger:
    """Confirmation keys already reported in a SENT missed digest (D3 dedup)."""

    def __init__(self, path: str):
        self.store = JsonKeyValueStore(path)

    def reported(self, key: str) -> bool:
        return self.store.get(key) is not None

    def pending(self, items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Items not yet reported, de-duplicated by key, in a stable order."""
        seen, out = set(), []
        for it in sorted(items, key=lambda i: (i["trigger_bar_close_ts"] or "", i["key"])):
            if it["key"] in seen or self.store.get(it["key"]) is not None:
                continue
            seen.add(it["key"])
            out.append(it)
        return out

    def mark(self, items: Iterable[Dict[str, Any]], digest_id: str) -> None:
        for it in items:
            self.store.put(it["key"], {"digest_id": digest_id})


def digest_id(items: Iterable[Dict[str, Any]]) -> str:
    return hashlib.sha256("|".join(sorted(i["key"] for i in items)).encode()).hexdigest()[:16]
