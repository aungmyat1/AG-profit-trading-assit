"""Exit policies applied to an immutable occurrence population."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from .models import CanonicalOccurrence, CandleSnapshot, ExitDecision


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _hits_stop_or_target(occurrence: CanonicalOccurrence, candle: CandleSnapshot):
    if occurrence.side == "LONG":
        stop = candle.low <= occurrence.initial_sl
        target = candle.high >= occurrence.initial_tp
    elif occurrence.side == "SHORT":
        stop = candle.high >= occurrence.initial_sl
        target = candle.low <= occurrence.initial_tp
    else:
        raise ValueError(f"unsupported side: {occurrence.side!r}")
    if stop and target:
        raise ValueError("AMBIGUOUS_SAME_CANDLE_STOP_TARGET")
    if stop:
        return "SL_HIT", occurrence.initial_sl
    if target:
        return "TP_HIT", occurrence.initial_tp
    return None


class ExitPolicy(ABC):
    policy_id: str

    @abstractmethod
    def evaluate(self, occurrence: CanonicalOccurrence) -> ExitDecision:
        raise NotImplementedError


class ControlPolicy(ExitPolicy):
    policy_id = "CONTROL"

    def evaluate(self, occurrence: CanonicalOccurrence) -> ExitDecision:
        entry_time = _parse_timestamp(occurrence.entry_timestamp)
        for candle in occurrence.m1_path:
            if _parse_timestamp(candle.timestamp) <= entry_time:
                continue
            hit = _hits_stop_or_target(occurrence, candle)
            if hit:
                reason, price = hit
                return ExitDecision(self.policy_id, candle.timestamp, price, reason, _holding_minutes(occurrence, candle))
        return _close_at_path_end(self.policy_id, occurrence, "PATH_EXHAUSTED")


class TimeStopPolicy(ExitPolicy):
    def __init__(self, minutes: int):
        if minutes <= 0:
            raise ValueError("time stop must be positive")
        self.minutes = minutes
        self.policy_id = f"TS_{minutes}M"

    def evaluate(self, occurrence: CanonicalOccurrence) -> ExitDecision:
        entry_time = _parse_timestamp(occurrence.entry_timestamp)
        deadline = entry_time + timedelta(minutes=self.minutes)
        for candle in occurrence.m1_path:
            candle_time = _parse_timestamp(candle.timestamp)
            if candle_time <= entry_time:
                continue
            hit = _hits_stop_or_target(occurrence, candle)
            if hit:
                reason, price = hit
                return ExitDecision(self.policy_id, candle.timestamp, price, reason, _holding_minutes(occurrence, candle))
            if candle_time >= deadline:
                return ExitDecision(self.policy_id, candle.timestamp, candle.close, "TIME_EXPIRED", self.minutes)
        return _close_at_path_end(self.policy_id, occurrence, "PATH_EXHAUSTED")


def _holding_minutes(occurrence: CanonicalOccurrence, candle: CandleSnapshot) -> int:
    delta = _parse_timestamp(candle.timestamp) - _parse_timestamp(occurrence.entry_timestamp)
    return max(0, int(delta.total_seconds() // 60))


def _close_at_path_end(policy_id: str, occurrence: CanonicalOccurrence, reason: str) -> ExitDecision:
    if not occurrence.m1_path:
        raise ValueError("INCOMPLETE_M1_PATH")
    candle = occurrence.m1_path[-1]
    return ExitDecision(policy_id, candle.timestamp, candle.close, reason, _holding_minutes(occurrence, candle))