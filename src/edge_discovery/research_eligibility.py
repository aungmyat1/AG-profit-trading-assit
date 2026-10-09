"""Strategy-blind clean-window eligibility for immutable Crypto-CFD M5 evidence.

This module deliberately separates two facts:

* raw source quality remains blocked when unexplained gaps exist; and
* a bounded reference/observation interval may still be usable only when each required
  M5 bar can be independently proven present and valid.

It never repairs, fills, sorts, aggregates through, or reclassifies an unknown gap.  It
also has no import of strategy/replay/metrics code: eligibility depends only on source
identity, timestamps, schema-level source flags, OHLC validity, duplicates, and M5
contiguity.  The immutable manifest can be handed to the R2 partition layer later, but
this module never creates partitions or runs C001.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .ingestion import DerivedDataset, OhlcBar, RawDataset, build_derived_dataset
from .quality import BARS_PER_UTC_DAY, M5_DELTA, _resample_complete, utc_iso

ELIGIBILITY_POLICY_ID = "CRYPTO_CFD_RESEARCH_WINDOW_ELIGIBILITY_V1"
ELIGIBILITY_SCHEMA_VERSION = "AG_CRYPTO_CFD_RESEARCH_ELIGIBILITY_MANIFEST_V1"
ELIGIBLE_M5_TRANSFORM_ID = "RESEARCH_ELIGIBLE_M5_V1"
RAW_DATA_QUALITY_BLOCKED_UNKNOWN_GAPS = "BLOCKED_UNKNOWN_GAPS"

# Authority supplied for the immutable source files in this mission.  The eligibility
# engine accepts an explicit test mapping, but production callers should retain these
# exact source bytes; a mismatch must not be treated as the same dataset.
AUTHORITATIVE_RAW_SHA256: Mapping[str, str] = {
    "BTCUSD": "ea0216b3431c8043537fd0a4cba9d57a7cf721f8d21656c2d90bb8a22468d3be",
    "ETHUSD": "1a2bd9429e14d0815210ae7913e130213d7c3b00c1608ec3025c333f06f5f713",
}


class EligibilityReason(str, Enum):
    """Stable, typed reason vocabulary. Multiple ordered reasons may be attached to
    one quarantine record; the first is its primary reason."""

    ELIGIBLE = "ELIGIBLE"
    SOURCE_HISTORY_LIMIT = "SOURCE_HISTORY_LIMIT"
    INCOMPLETE_REFERENCE_DAY = "INCOMPLETE_REFERENCE_DAY"
    UNKNOWN_GAP_REFERENCE_DAY = "UNKNOWN_GAP_REFERENCE_DAY"
    UNKNOWN_GAP_OBSERVATION_WINDOW = "UNKNOWN_GAP_OBSERVATION_WINDOW"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    INVALID_OHLC = "INVALID_OHLC"
    NON_CONTIGUOUS_M5 = "NON_CONTIGUOUS_M5"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    SYNTHETIC_OR_FILLED_BAR = "SYNTHETIC_OR_FILLED_BAR"
    RAW_HASH_MISMATCH = "RAW_HASH_MISMATCH"


class EligibilityError(ValueError):
    def __init__(self, reason: EligibilityReason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}{': ' + detail if detail else ''}")


@dataclass(frozen=True)
class ReferenceDayEligibility:
    symbol: str
    utc_date: str
    eligible: bool
    reasons: Tuple[EligibilityReason, ...]
    bar_count: int
    first_timestamp_utc: Optional[str]
    last_timestamp_utc: Optional[str]
    gap_dependency: bool
    source_dataset_id: str
    source_sha256: str

    @property
    def primary_reason(self) -> EligibilityReason:
        return self.reasons[0]


@dataclass(frozen=True)
class ObservationWindowEligibility:
    symbol: str
    observation_start_utc: str
    observation_end_utc: str
    end_inclusive: bool
    eligible: bool
    reasons: Tuple[EligibilityReason, ...]
    required_bar_count: int
    present_bar_count: int
    gap_dependency: bool
    source_dataset_id: str
    source_sha256: str

    @property
    def primary_reason(self) -> EligibilityReason:
        return self.reasons[0]


@dataclass(frozen=True)
class ObservationDayEligibility:
    """A conservative, strategy-blind population record for a whole UTC observation
    day. It requires a clean current day and a clean previous UTC reference day, but
    never asks whether a strategy signal would occur."""

    symbol: str
    utc_date: str
    reference_utc_date: str
    eligible: bool
    reasons: Tuple[EligibilityReason, ...]
    source_dataset_id: str
    source_sha256: str


@dataclass(frozen=True)
class ResearchEligibilityManifest:
    schema_version: str
    policy_id: str
    symbol: str
    source_dataset_id: str
    source_sha256: str
    raw_data_quality: str
    reference_days: Tuple[ReferenceDayEligibility, ...]
    observation_days: Tuple[ObservationDayEligibility, ...]
    manifest_sha256: str
    path: Optional[Path] = None

    def as_dict(self) -> Mapping[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _utc_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _parse_day(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "naive UTC day")
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _is_valid_ohlc(bar: OhlcBar) -> bool:
    return bar.high >= bar.low and bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high


def _dates_in_source(dataset: RawDataset) -> Tuple[date, ...]:
    if not dataset.bars:
        return ()
    start, end = min(bar.time for bar in dataset.bars).date(), max(bar.time for bar in dataset.bars).date()
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return tuple(days)


class ResearchWindowEligibility:
    """Read-only index over one already provenance-verified R2 ``RawDataset``.

    The constructor preserves input ordering and builds only timestamp/date lookup
    structures. It does not calculate performance outcomes, targets, or strategy state.
    """

    def __init__(
        self,
        dataset: RawDataset,
        expected_sha256: Optional[Mapping[str, str]] = None,
    ) -> None:
        if dataset.symbol not in AUTHORITATIVE_RAW_SHA256:
            raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, f"unsupported symbol {dataset.symbol}")
        if dataset.asset_class != "CRYPTO_CFD" or dataset.timeframe != "M5":
            raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "requires CRYPTO_CFD M5")
        expected = dict(AUTHORITATIVE_RAW_SHA256 if expected_sha256 is None else expected_sha256)
        if dataset.symbol in expected and dataset.sha256 != expected[dataset.symbol]:
            raise EligibilityError(EligibilityReason.RAW_HASH_MISMATCH, dataset.symbol)
        self.dataset = dataset
        self._bars_by_day: Dict[date, Tuple[OhlcBar, ...]] = {}
        grouped: Dict[date, list[OhlcBar]] = {}
        for bar in dataset.bars:
            grouped.setdefault(bar.time.astimezone(timezone.utc).date(), []).append(bar)
        self._bars_by_day = {day: tuple(bars) for day, bars in grouped.items()}
        self._source_dates = _dates_in_source(dataset)
        self._source_first = min((bar.time for bar in dataset.bars), default=None)
        self._source_last = max((bar.time for bar in dataset.bars), default=None)

    def reference_day(self, utc_date: str | date | datetime) -> ReferenceDayEligibility:
        """Prove whether this UTC day alone is safe as a C001 reference day. The
        expected sequence is exactly [00:00, 24:00) UTC in five-minute steps.
        """
        day = _parse_day(utc_date)
        bars = self._bars_by_day.get(day, ())
        # Sorting is used only to compare the expected calendar grid. The original
        # source sequence is separately checked: a reordered source cannot become
        # eligible merely because it can be sorted in memory.
        source_monotonic = all(before.time < after.time for before, after in zip(bars, bars[1:]))
        ordered = tuple(sorted(bars, key=lambda item: item.time))
        expected_start = _utc_midnight(day)
        expected_times = tuple(expected_start + index * M5_DELTA for index in range(BARS_PER_UTC_DAY))
        actual_times = tuple(bar.time for bar in ordered)
        reasons: list[EligibilityReason] = []

        duplicate = len(actual_times) != len(set(actual_times))
        invalid = any(not _is_valid_ohlc(bar) for bar in ordered)
        synthetic = any(bar.synthetic for bar in ordered)
        if duplicate:
            reasons.append(EligibilityReason.DUPLICATE_TIMESTAMP)
        if invalid:
            reasons.append(EligibilityReason.INVALID_OHLC)
        if synthetic:
            reasons.append(EligibilityReason.SYNTHETIC_OR_FILLED_BAR)

        source_limit = self._day_outside_source(day)
        missing_times = set(expected_times) - set(actual_times)
        extra_or_misaligned = set(actual_times) - set(expected_times)
        contiguous = actual_times == expected_times
        gap_dependency = bool(missing_times or extra_or_misaligned or not contiguous or not source_monotonic)

        if source_limit:
            reasons.append(EligibilityReason.SOURCE_HISTORY_LIMIT)
        if len(ordered) != BARS_PER_UTC_DAY:
            reasons.append(EligibilityReason.INCOMPLETE_REFERENCE_DAY)
        if gap_dependency:
            # A source-edge partial day is a history limit; an interior missing point is
            # an unknown dependency. Both remain quarantined, never reclassified.
            if not source_limit or self._has_interior_missing(day, missing_times):
                reasons.append(EligibilityReason.UNKNOWN_GAP_REFERENCE_DAY)
            reasons.append(EligibilityReason.NON_CONTIGUOUS_M5)
        if not ordered:
            reasons.append(EligibilityReason.INSUFFICIENT_DATA)

        reasons = list(dict.fromkeys(reasons))
        eligible = not reasons
        return ReferenceDayEligibility(
            symbol=self.dataset.symbol, utc_date=day.isoformat(), eligible=eligible,
            reasons=(EligibilityReason.ELIGIBLE,) if eligible else tuple(reasons),
            bar_count=len(ordered), first_timestamp_utc=utc_iso(ordered[0].time) if ordered else None,
            last_timestamp_utc=utc_iso(ordered[-1].time) if ordered else None,
            gap_dependency=gap_dependency, source_dataset_id=self.dataset.dataset_id,
            source_sha256=self.dataset.sha256,
        )

    def observation_window(
        self,
        observation_start: datetime,
        observation_end: datetime,
        *,
        end_inclusive: bool = True,
    ) -> ObservationWindowEligibility:
        """Prove an explicitly supplied observation interval. Both endpoints must be
        timezone-aware UTC-aligned M5 opens. By default ``end`` is included, matching
        a closed-bar observation request; callers can request half-open semantics.
        """
        start = _as_utc_m5(observation_start)
        end = _as_utc_m5(observation_end)
        if end < start or (not end_inclusive and end == start):
            return self._window_result(start, end, end_inclusive, (), 0,
                                       (EligibilityReason.INSUFFICIENT_DATA,), False)
        last_required = end if end_inclusive else end - M5_DELTA
        required_times = tuple(_timestamps(start, last_required))
        if not required_times:
            return self._window_result(start, end, end_inclusive, (), 0,
                                       (EligibilityReason.INSUFFICIENT_DATA,), False)
        interval_bars = tuple(bar for bar in self.dataset.bars if start <= bar.time <= last_required)
        source_monotonic = all(before.time < after.time for before, after in zip(interval_bars, interval_bars[1:]))
        present = {bar.time: bar for bar in interval_bars}
        selected = tuple(present[stamp] for stamp in required_times if stamp in present)
        reasons: list[EligibilityReason] = []
        source_limit = (self._source_first is None or self._source_last is None
                        or start < self._source_first or last_required > self._source_last)
        missing = [stamp for stamp in required_times if stamp not in present]
        duplicate_times = _duplicate_times_in_interval(self.dataset.bars, start, last_required)
        if duplicate_times:
            reasons.append(EligibilityReason.DUPLICATE_TIMESTAMP)
        if not source_monotonic:
            reasons.append(EligibilityReason.NON_CONTIGUOUS_M5)
        if any(not _is_valid_ohlc(bar) for bar in selected):
            reasons.append(EligibilityReason.INVALID_OHLC)
        if any(bar.synthetic for bar in selected):
            reasons.append(EligibilityReason.SYNTHETIC_OR_FILLED_BAR)
        if source_limit:
            reasons.append(EligibilityReason.SOURCE_HISTORY_LIMIT)
        if missing:
            reasons.append(EligibilityReason.UNKNOWN_GAP_OBSERVATION_WINDOW)
            reasons.append(EligibilityReason.NON_CONTIGUOUS_M5)
        if len(selected) != len(required_times) and not missing:
            reasons.append(EligibilityReason.INSUFFICIENT_DATA)
        reasons = tuple(dict.fromkeys(reasons))
        return self._window_result(start, end, end_inclusive, selected, len(required_times),
                                   (EligibilityReason.ELIGIBLE,) if not reasons else reasons,
                                   bool(missing or not source_monotonic))

    def observation_day(self, utc_date: str | date | datetime) -> ObservationDayEligibility:
        """Conservative whole-day candidate population: clean current-day M5 interval
        and a clean prior-day reference. This is a data dependency decision, not a C001
        signal/outcome decision.
        """
        day = _parse_day(utc_date)
        reference = self.reference_day(day - timedelta(days=1))
        current = self.observation_window(_utc_midnight(day), _utc_midnight(day) + timedelta(days=1) - M5_DELTA)
        reasons = []
        if not reference.eligible:
            reasons.extend(reference.reasons)
        if not current.eligible:
            reasons.extend(current.reasons)
        reasons = tuple(dict.fromkeys(reasons))
        return ObservationDayEligibility(
            symbol=self.dataset.symbol, utc_date=day.isoformat(),
            reference_utc_date=(day - timedelta(days=1)).isoformat(), eligible=not reasons,
            reasons=(EligibilityReason.ELIGIBLE,) if not reasons else reasons,
            source_dataset_id=self.dataset.dataset_id, source_sha256=self.dataset.sha256,
        )

    def build_manifest(
        self,
        raw_data_quality: str = RAW_DATA_QUALITY_BLOCKED_UNKNOWN_GAPS,
    ) -> ResearchEligibilityManifest:
        """Build a reproducible quarantine manifest without reclassifying raw gaps.
        The raw quality label is deliberately fixed by this contract, not inferred from
        the subset of clean windows that happens to be eligible.
        """
        if raw_data_quality != RAW_DATA_QUALITY_BLOCKED_UNKNOWN_GAPS:
            raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "raw quality may not be reclassified")
        days = self._source_dates
        reference_days = tuple(self.reference_day(day) for day in days)
        observation_days = tuple(self.observation_day(day) for day in days)
        payload = {
            "schema_version": ELIGIBILITY_SCHEMA_VERSION, "policy_id": ELIGIBILITY_POLICY_ID,
            "symbol": self.dataset.symbol, "source_dataset_id": self.dataset.dataset_id,
            "source_sha256": self.dataset.sha256, "raw_data_quality": raw_data_quality,
            "reference_days": reference_days, "observation_days": observation_days,
        }
        return ResearchEligibilityManifest(
            schema_version=ELIGIBILITY_SCHEMA_VERSION, policy_id=ELIGIBILITY_POLICY_ID,
            symbol=self.dataset.symbol, source_dataset_id=self.dataset.dataset_id,
            source_sha256=self.dataset.sha256, raw_data_quality=raw_data_quality,
            reference_days=reference_days, observation_days=observation_days,
            manifest_sha256=hashlib.sha256(_canonical(payload)).hexdigest(), path=None,
        )

    def eligible_observation_m5(
        self,
        manifest: ResearchEligibilityManifest,
        artifact_root: Optional[Path] = None,
    ) -> DerivedDataset:
        """Expose the conservative eligible observation-day population in the R2
        ``DerivedDataset`` shape. It contains only original raw bars from manifest-
        eligible days and can later be supplied to the existing partition freezer.
        """
        if manifest.symbol != self.dataset.symbol or manifest.source_sha256 != self.dataset.sha256:
            raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "manifest/source mismatch")
        eligible_days = {date.fromisoformat(record.utc_date) for record in manifest.observation_days if record.eligible}
        bars = tuple(bar for bar in self.dataset.bars if bar.time.date() in eligible_days)
        return build_derived_dataset(
            self.dataset, ELIGIBLE_M5_TRANSFORM_ID, "M5", bars, artifact_root,
        )

    def _day_outside_source(self, day: date) -> bool:
        if self._source_first is None or self._source_last is None:
            return True
        start, end = _utc_midnight(day), _utc_midnight(day) + timedelta(days=1) - M5_DELTA
        # A partial first/last source date is a source-history boundary, not a claimed
        # closure. Interior dates are handled as unknown gaps.
        return start < self._source_first or end > self._source_last

    @staticmethod
    def _has_interior_missing(day: date, missing: set[datetime]) -> bool:
        start, end = _utc_midnight(day), _utc_midnight(day) + timedelta(days=1) - M5_DELTA
        return any(start < stamp < end for stamp in missing)

    def _window_result(
        self, start: datetime, end: datetime, end_inclusive: bool,
        selected: Sequence[OhlcBar], required_count: int,
        reasons: Tuple[EligibilityReason, ...], gap_dependency: bool,
    ) -> ObservationWindowEligibility:
        return ObservationWindowEligibility(
            symbol=self.dataset.symbol, observation_start_utc=utc_iso(start),
            observation_end_utc=utc_iso(end), end_inclusive=end_inclusive,
            eligible=reasons == (EligibilityReason.ELIGIBLE,), reasons=reasons,
            required_bar_count=required_count, present_bar_count=len(selected),
            gap_dependency=gap_dependency, source_dataset_id=self.dataset.dataset_id,
            source_sha256=self.dataset.sha256,
        )


def _as_utc_m5(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "naive observation timestamp")
    utc = value.astimezone(timezone.utc)
    if utc.second or utc.microsecond or utc.minute % 5:
        raise EligibilityError(EligibilityReason.NON_CONTIGUOUS_M5, "observation bounds must be M5 opens")
    return utc


def _timestamps(start: datetime, end: datetime) -> Iterable[datetime]:
    point = start
    while point <= end:
        yield point
        point += M5_DELTA


def _duplicate_times_in_interval(bars: Sequence[OhlcBar], start: datetime, end: datetime) -> bool:
    timestamps = [bar.time for bar in bars if start <= bar.time <= end]
    return len(timestamps) != len(set(timestamps))


def freeze_eligibility_manifest(manifest: ResearchEligibilityManifest, path: Path) -> ResearchEligibilityManifest:
    """Write the canonical manifest once. Existing bytes must exactly match—quarantine
    facts are not silently replaced when a later run sees a different source view."""
    path = Path(path)
    document = manifest.as_dict()
    document = {key: value for key, value in document.items() if key not in {"manifest_sha256", "path"}}
    encoded = _canonical(document)
    expected = hashlib.sha256(encoded).hexdigest()
    if expected != manifest.manifest_sha256:
        raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "manifest hash mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != encoded:
        raise EligibilityError(EligibilityReason.INSUFFICIENT_DATA, "eligibility manifest immutability violation")
    if not path.exists():
        path.write_bytes(encoded)
    return replace(manifest, path=path)


def derive_complete_timeframe(bars: Sequence[OhlcBar], timeframe: str) -> Tuple[OhlcBar, ...]:
    """Authoritative M15/H1/D1 derivation from already eligible source bars only.

    M15 needs exactly 3 consecutive bars, H1 12, D1 288. Incomplete buckets disappear;
    they are never interpolated or emitted as an authoritative aggregate.
    """
    minutes = {"M15": 15, "H1": 60, "D1": 1440}.get(timeframe)
    if minutes is None:
        raise ValueError(f"unsupported timeframe {timeframe!r}")
    if any(not _is_valid_ohlc(bar) or bar.synthetic for bar in bars):
        return ()
    ordered = tuple(sorted(bars, key=lambda bar: bar.time))
    if len({bar.time for bar in ordered}) != len(ordered):
        return ()
    return tuple(_resample_complete(ordered, minutes))


__all__ = [
    "AUTHORITATIVE_RAW_SHA256", "ELIGIBILITY_POLICY_ID", "ELIGIBILITY_SCHEMA_VERSION",
    "ELIGIBLE_M5_TRANSFORM_ID", "RAW_DATA_QUALITY_BLOCKED_UNKNOWN_GAPS", "EligibilityError", "EligibilityReason",
    "ObservationDayEligibility", "ObservationWindowEligibility", "ReferenceDayEligibility",
    "ResearchEligibilityManifest", "ResearchWindowEligibility", "derive_complete_timeframe",
    "freeze_eligibility_manifest",
]
