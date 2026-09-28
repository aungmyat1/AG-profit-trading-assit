"""P6-R1: server-time authority vs the legacy largest-gap offset inference.

Series are synthetic broker-clock M15 sessions shaped like the live VTMarkets-Demo
evidence of 2026-09-28 (weekly Mon 00:00 -> Fri 23:45 broker time, NY-close server,
+3 in summer). The USDJPY series lacks exactly one bar -- Monday 2026-09-14 00:00 --
so its first post-weekend bar that week is 00:15, as observed live. Offsets are never
asserted from a table: every expectation below is also derivable from the reopen rule.
"""
from __future__ import annotations

import calendar
import datetime as dt

import pytest

import mt5.broker_time as bt
from mt5.time_authority import (
    SOURCE_SERVER_CONSENSUS,
    SOURCE_SERVER_SHARED,
    SOURCE_SYMBOL_LOCAL,
    TimeAuthorityConflict,
    TimeAuthorityTimeline,
    TimeAuthorityUnavailable,
    merge_periods,
    observe_reopens,
    resolve_periods,
)

M15 = dt.timedelta(minutes=15)
UTC = dt.timezone.utc
SEP_MONDAYS = [dt.datetime(2026, 8, 31), dt.datetime(2026, 9, 7), dt.datetime(2026, 9, 14),
               dt.datetime(2026, 9, 21), dt.datetime(2026, 9, 28)]
USDJPY_MISSING = {dt.datetime(2026, 9, 14, 0, 0)}


def weeks(mondays, drop=(), last_until=dt.datetime(2026, 9, 28, 21, 0)):
    """Naive broker-clock M15 bar times, Mon 00:00 .. Fri 23:45, optionally dropping bars."""
    out = []
    for monday in mondays:
        t, end = monday, monday + dt.timedelta(days=5)
        while t < end and t <= last_until:
            if t not in drop:
                out.append(t)
            t += M15
    return out


EURUSD = weeks(SEP_MONDAYS)
GBPUSD = weeks(SEP_MONDAYS)
USDJPY = weeks(SEP_MONDAYS, drop=USDJPY_MISSING)


def utc(*a):
    return dt.datetime(*a, tzinfo=UTC)


# --- Part A: pinned failing baseline of the legacy algorithm -------------------------


def _legacy(monkeypatch, times):
    rates = [{"time": calendar.timegm(t.timetuple())} for t in times[-3000:]]
    monkeypatch.setattr(bt.mt5, "copy_rates_from_pos", lambda *a, **k: rates, raising=False)
    return bt.detect_broker_utc_offset_hours("X")


@pytest.mark.parametrize("series", [EURUSD, GBPUSD], ids=["EURUSD", "GBPUSD"])
def test_legacy_resolves_complete_history(monkeypatch, series):
    assert _legacy(monkeypatch, series) == 3


def test_legacy_fails_on_usdjpy_missing_monday_open(monkeypatch):
    # 2026-09-11 23:45 -> 2026-09-14 00:15 (2d 00:30) becomes the single largest gap.
    assert max(b - a for a, b in zip(USDJPY, USDJPY[1:])) == dt.timedelta(days=2, minutes=30)
    with pytest.raises(bt.BrokerTimeError, match="OFFSET_FROM_REOPEN_AMBIGUOUS"):
        _legacy(monkeypatch, USDJPY)


# --- incomplete history --------------------------------------------------------------


def test_incomplete_reopen_is_rejected_as_evidence_not_interpreted():
    before = tuple(USDJPY)
    obs = {o.broker_reading: o for o in observe_reopens("USDJPY", USDJPY)}
    bad = obs[dt.datetime(2026, 9, 14, 0, 15)]
    assert (bad.status, bad.utc_offset_hours, bad.reopen_utc) == ("REJECTED_NOT_WHOLE_HOUR", None, None)
    assert all(o.status == "VALID" and o.utc_offset_hours == 3 for r, o in obs.items() if r != bad.broker_reading)
    assert tuple(USDJPY) == before  # raw history untouched, nothing synthesized


def test_symbol_local_only_leaves_the_incomplete_week_uncovered():
    tl = TimeAuthorityTimeline(resolve_periods("VT_MARKETS", "VTMarkets-Demo", "USDJPY",
                                               observe_reopens("USDJPY", USDJPY)))
    with pytest.raises(TimeAuthorityUnavailable):
        tl.at_utc(utc(2026, 9, 15, 12))           # the 09-14 week: no valid local evidence
    p = tl.at_utc(utc(2026, 9, 28, 12))          # current week: its own complete reopen
    assert (p.utc_offset_hours, p.source) == (3, SOURCE_SYMBOL_LOCAL)


def test_same_server_authority_covers_usdjpy_incomplete_week():
    obs = observe_reopens("EURUSD", EURUSD) + observe_reopens("GBPUSD", GBPUSD) + observe_reopens("USDJPY", USDJPY)
    tl = TimeAuthorityTimeline(resolve_periods("VT_MARKETS", "VTMarkets-Demo", "USDJPY", obs))
    p = tl.at_utc(utc(2026, 9, 15, 12))
    assert (p.utc_offset_hours, p.source, p.evidence_symbols) == (3, SOURCE_SERVER_CONSENSUS, ("EURUSD", "GBPUSD"))
    assert p.effective_from_utc == utc(2026, 9, 13, 21)  # NY 17:00 EDT, not 00:15 broker
    assert p.provenance("USDJPY")["scope"] == "SERVER_SHARED"
    now = tl.at_utc(utc(2026, 9, 28, 12))
    assert now.evidence_symbols == ("EURUSD", "GBPUSD", "USDJPY")


def test_single_other_symbol_is_server_shared():
    tl = TimeAuthorityTimeline(resolve_periods("VT_MARKETS", "S", "USDJPY", observe_reopens("EURUSD", EURUSD)))
    assert tl.at_utc(utc(2026, 9, 15)).source == SOURCE_SERVER_SHARED


# --- DST / effective periods ---------------------------------------------------------


def test_winter_offset_is_derived_not_assumed():
    jan = weeks([dt.datetime(2026, 1, 5), dt.datetime(2026, 1, 12)], last_until=dt.datetime(2026, 1, 16, 23, 45))
    tl = TimeAuthorityTimeline(resolve_periods("B", "S", "EURUSD", observe_reopens("EURUSD", jan)))
    p = tl.at_utc(utc(2026, 1, 13, 12))
    assert (p.utc_offset_hours, p.effective_from_utc) == (2, utc(2026, 1, 11, 22))


@pytest.mark.parametrize("mondays,before,after,offsets", [
    # US DST end 2026-11-01: +3 week then +2 week (next reopen 7d+1h later in UTC)
    ([dt.datetime(2026, 10, 19), dt.datetime(2026, 10, 26), dt.datetime(2026, 11, 2)],
     utc(2026, 10, 30, 12), utc(2026, 11, 3, 12), (3, 2)),
    # US DST start 2026-03-08: +2 week then +3 week (next reopen 7d-1h later in UTC)
    ([dt.datetime(2026, 2, 23), dt.datetime(2026, 3, 2), dt.datetime(2026, 3, 9)],
     utc(2026, 3, 6, 12), utc(2026, 3, 10, 12), (2, 3)),
])
def test_offset_changes_across_dst_transition(mondays, before, after, offsets):
    series = weeks(mondays, last_until=mondays[-1] + dt.timedelta(days=4))
    tl = TimeAuthorityTimeline(resolve_periods("B", "S", "EURUSD", observe_reopens("EURUSD", series)))
    assert (tl.at_utc(before).utc_offset_hours, tl.at_utc(after).utc_offset_hours) == offsets
    # broker readings map through their own period
    fri_close = mondays[1] + dt.timedelta(days=4, hours=23, minutes=45)
    assert tl.at_broker(fri_close).utc_offset_hours == offsets[0]
    assert tl.at_broker(mondays[2]).utc_offset_hours == offsets[1]


# --- disagreement / no authority / cache ---------------------------------------------


def test_same_week_disagreement_fails_closed():
    shifted = weeks(SEP_MONDAYS, drop={dt.datetime(2026, 9, 28, 0, m) for m in (0, 15, 30, 45)})
    obs = observe_reopens("EURUSD", EURUSD) + observe_reopens("GBPUSD", shifted)  # GBPUSD reads 01:00 -> +4
    with pytest.raises(TimeAuthorityConflict):
        resolve_periods("B", "S", "EURUSD", obs)


def test_no_weekend_evidence_is_unavailable():
    always_on = [dt.datetime(2026, 9, 21) + i * M15 for i in range(800)]  # 24/7-shaped, no gap
    tl = TimeAuthorityTimeline(resolve_periods("B", "S", "BTCUSD", observe_reopens("BTCUSD", always_on)))
    with pytest.raises(TimeAuthorityUnavailable):
        tl.at_utc(utc(2026, 9, 25))


def test_period_never_spans_an_unobserved_week():
    a = resolve_periods("B", "S", "EURUSD", observe_reopens("EURUSD", weeks(SEP_MONDAYS[:1],
                        last_until=dt.datetime(2026, 9, 4, 23, 45))) + observe_reopens(
                        "EURUSD", weeks(SEP_MONDAYS[:2], last_until=dt.datetime(2026, 9, 11))))
    c = resolve_periods("B", "S", "EURUSD", observe_reopens("EURUSD", weeks(SEP_MONDAYS[3:])))
    tl = TimeAuthorityTimeline(list(merge_periods({p.effective_from_utc: p for p in a}, c).values()))
    assert tl.at_utc(utc(2026, 9, 10)).utc_offset_hours == 3
    with pytest.raises(TimeAuthorityUnavailable):
        tl.at_utc(utc(2026, 9, 16))                # the unobserved 09-14 week


def test_previously_validated_authority_conflict_fails_closed():
    known = {p.effective_from_utc: p for p in resolve_periods("B", "S", "EURUSD", observe_reopens("EURUSD", EURUSD))}
    bad = resolve_periods("B", "S", "GBPUSD", observe_reopens(
        "GBPUSD", weeks(SEP_MONDAYS, drop={dt.datetime(2026, 9, 28, 0, m) for m in (0, 15, 30, 45)})))
    with pytest.raises(TimeAuthorityConflict):
        merge_periods(known, bad)
