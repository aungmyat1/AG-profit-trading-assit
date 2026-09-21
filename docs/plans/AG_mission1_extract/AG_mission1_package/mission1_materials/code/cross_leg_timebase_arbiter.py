"""DRAFT — Mission 1 / P3: cross-leg timebase arbiter for one-year replay admission.

Promotes the 2026-09-19 R3 mission analysis into an executable, fail-closed admission
component. Design constraints encoded here:

  * Parity is ALWAYS cross-timeframe: a candidate H1/M15 leg is compared against
    buckets derived from the canonical M1 authority. Same-source parity
    (H1-vs-H1 from the same package) is exactly the tautology that let GEN_002's
    defect pass its own parity_diagnostic -- it is not expressible in this API.
  * Exact OHLC bucketing from M1 (the DERIVED_001 derivation contract):
    open = first M1 open by M1 timestamp, high = max, low = min,
    close = last M1 close, volume = sum of present members (None if none).
  * Whole-hour shift diagnostics are bounded (-3h..+3h) and judged per DST season
    as well as globally; a leg explained only by two different shifts is reported
    INTERNALLY_DST_INCONSISTENT -- never given a misleading single "best" shift.
  * Everything fails closed: any ambiguity returns an inadmissible verdict.

Integration: place under src/historical_replay/ (suggested name
`timebase_arbiter.py`) or scripts/-local; the one-year coverage audit
(scripts/audit_ssc_v1_0_1_one_year_data_coverage.py) should import it in the gate
extension rather than re-implementing. Uses only public repo types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from strategy_engine.session import Candle

SHIFT_RANGE_HOURS: Tuple[int, ...] = (-3, -2, -1, 0, 1, 2, 3)

# Verdict statuses (fail-closed: anything not ALIGNED is inadmissible)
ALIGNED = "ALIGNED"
MISALIGNED = "MISALIGNED"
INTERNALLY_DST_INCONSISTENT = "INTERNALLY_DST_INCONSISTENT"
INPUT_REJECTED = "INPUT_REJECTED"


class TimebaseArbiterError(ValueError):
    """Raised on inadmissible inputs (duplicate timestamps, non-monotonic series)."""


@dataclass(frozen=True)
class ArbiterVerdict:
    status: str                      # ALIGNED | MISALIGNED | INTERNALLY_DST_INCONSISTENT | INPUT_REJECTED
    best_shift_hours: Optional[int]  # only meaningful when a single shift explains the leg
    exact_match_rate: float          # over common buckets at best shift (0.0 when rejected)
    common_buckets: int
    per_shift_rates: Dict[int, float] = field(default_factory=dict)
    detail: str = ""

    @property
    def admissible(self) -> bool:
        return (
            self.status == ALIGNED
            and self.best_shift_hours == 0
            and self.exact_match_rate == 1.0
        )


def _validate_monotonic(candles: Sequence[Candle], label: str) -> None:
    for a, b in zip(candles, candles[1:]):
        if b.time <= a.time:
            raise TimebaseArbiterError(
                f"{label}: non-monotonic/duplicate timestamp at {b.time.isoformat()} -- fail closed"
            )


def bucket_open(t: datetime, tf_minutes: int) -> datetime:
    """Floor an instant to its containing bucket open time (UTC)."""
    minutes = t.hour * 60 + t.minute
    floored = (minutes // tf_minutes) * tf_minutes
    return t.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def derive_buckets(m1: Sequence[Candle], tf_minutes: int) -> Dict[datetime, Candle]:
    """Deterministic exact-bucket aggregation of M1 candles (DERIVED_001 contract).
    A bucket exists only where M1 bars exist -- a closed market produces no bucket
    (NATIVE_FAITHFUL_INCLUSIVE convention)."""
    buckets: Dict[datetime, List[Candle]] = {}
    for c in m1:
        buckets.setdefault(bucket_open(c.time, tf_minutes), []).append(c)
    out: Dict[datetime, Candle] = {}
    for key, members in buckets.items():
        members = sorted(members, key=lambda c: c.time)
        vols = [c.volume for c in members if c.volume is not None]
        out[key] = Candle(
            time=key,
            open=members[0].open,
            high=max(c.high for c in members),
            low=min(c.low for c in members),
            close=members[-1].close,
            volume=sum(vols) if vols else None,
        )
    return out


def _ohlc_equal(a: Candle, b: Candle) -> bool:
    # exact float equality is intentional: both sides come from the same raw M1
    # values through deterministic aggregation -- any difference is a real displacement
    return (a.open, a.high, a.low, a.close) == (b.open, b.high, b.low, b.close)


def exact_match_rate(candidate: Sequence[Candle], derived: Dict[datetime, Candle]) -> float:
    """Rate of OHLC-exact matches over buckets common to candidate and derived set."""
    common = 0
    exact = 0
    for c in candidate:
        d = derived.get(c.time)
        if d is None:
            continue
        common += 1
        if _ohlc_equal(c, d):
            exact += 1
    return (exact / common) if common else 0.0


def _season_of(t: datetime) -> str:
    """Coarse DST-season split for per-season judgement. Agent: replace with the
    broker-DST calendar convention used by market_data_readiness if the repo already
    defines one (it detects per-week reopen offsets) -- do not invent a second."""
    # FX broker DST (US convention): roughly second Sunday of March .. first Sunday of November
    year = t.year
    march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
    nov_first = datetime(year, 11, 1, tzinfo=timezone.utc)
    march_second_sun = march_first + timedelta(days=(6 - march_first.weekday()) % 7 + 7)
    nov_first_sun = nov_first + timedelta(days=(6 - nov_first.weekday()) % 7)
    return "SUMMER" if march_second_sun <= t < nov_first_sun else "WINTER"


def arbitrate(
    m1_authority: Sequence[Candle],
    candidate_leg: Sequence[Candle],
    tf_minutes: int,
    min_common_buckets: int = 100,
) -> ArbiterVerdict:
    """Admission arbitration for one candidate H1/M15 leg against the M1 authority.

    Fail-closed rules:
      * duplicate/non-monotonic inputs            -> INPUT_REJECTED (exception-free verdict)
      * fewer than min_common_buckets common      -> MISALIGNED (insufficient evidence)
      * single +0h shift explains 100% of buckets -> ALIGNED (admissible)
      * another single shift explains the leg     -> MISALIGNED with that shift reported
      * two different shifts each explain material parts -> INTERNALLY_DST_INCONSISTENT
    """
    try:
        _validate_monotonic(m1_authority, "m1_authority")
        _validate_monotonic(candidate_leg, "candidate_leg")
    except TimebaseArbiterError as exc:
        return ArbiterVerdict(INPUT_REJECTED, None, 0.0, 0, {}, str(exc))

    derived = derive_buckets(m1_authority, tf_minutes)

    # Global whole-hour shift scan (R3 diagnostic).
    per_shift: Dict[int, float] = {}
    common_at_shift: Dict[int, int] = {}
    for shift_h in SHIFT_RANGE_HOURS:
        shift = timedelta(hours=shift_h)
        shifted = [Candle(c.time - shift, c.open, c.high, c.low, c.close, c.volume)
                   for c in candidate_leg]
        per_shift[shift_h] = exact_match_rate(shifted, derived)
        common_at_shift[shift_h] = sum(1 for c in shifted if c.time in derived)

    # Per-bucket alignment census: for EACH candidate bucket, find the whole-hour shift
    # (if any) at which it matches the derived bucket exactly. Internal DST fracture is
    # detected as a BIMODAL census -- two different shifts each explaining a material
    # number of buckets -- independent of calendar-season heuristics. This is the
    # generalization of the DEV_002 finding (winter at -1h, summer at 0h).
    explaining_counts: Dict[int, int] = {}
    for c in candidate_leg:
        for shift_h in SHIFT_RANGE_HOURS:
            d = derived.get(c.time - timedelta(hours=shift_h))
            if d is not None and _ohlc_equal(c, d):
                explaining_counts[shift_h] = explaining_counts.get(shift_h, 0) + 1
                break  # a bucket matching at one shift is explained; census stays bimodal-safe

    explaining = sorted(h for h, n in explaining_counts.items() if n >= min_common_buckets)
    if len(explaining) >= 2:
        return ArbiterVerdict(
            INTERNALLY_DST_INCONSISTENT, None, max(per_shift.values()),
            common_at_shift.get(explaining[0], 0), per_shift,
            f"leg internally fractured: buckets explained at distinct shifts {explaining} "
            f"(counts { {h: explaining_counts[h] for h in explaining} }) -- no single time base",
        )

    best_shift = max(per_shift, key=lambda h: per_shift[h])
    best_rate = per_shift[best_shift]
    common_best = common_at_shift[best_shift]

    if common_best < min_common_buckets:
        return ArbiterVerdict(
            MISALIGNED, best_shift, best_rate, common_best, per_shift,
            f"only {common_best} common buckets < minimum {min_common_buckets}",
        )
    if best_rate >= 1.0 and best_shift == 0:
        # Diagnostic per-DST-season rates at +0h for the record (R3-style reporting).
        seasons: Dict[str, Tuple[int, int]] = {}
        for c in candidate_leg:
            d = derived.get(c.time)
            if d is None:
                continue
            s = _season_of(c.time)
            n_common, n_exact = seasons.get(s, (0, 0))
            seasons[s] = (n_common + 1, n_exact + (1 if _ohlc_equal(c, d) else 0))
        seasonal = {s: (n_ex / n_c) for s, (n_c, n_ex) in seasons.items() if n_c}
        if any(r < 1.0 for r in seasonal.values()):
            return ArbiterVerdict(MISALIGNED, 0, best_rate, common_best, per_shift,
                                  f"per-DST-season rates not all 1.0: {seasonal}")
        return ArbiterVerdict(ALIGNED, 0, 1.0, common_best, per_shift,
                              "best_shift=+0h, DST CONSISTENT, exact rate 1.0")
    return ArbiterVerdict(MISALIGNED, best_shift, best_rate, common_best, per_shift,
                          f"leg displaced: best whole-hour shift {best_shift:+d}h at rate {best_rate:.6f}")
