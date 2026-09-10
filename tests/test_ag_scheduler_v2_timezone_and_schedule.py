import datetime as dt

import pytest

from ag_scheduler_v2 import timezone_util as tzu
from ag_scheduler_v2.schedule import (
    BTC_FINALIZE, BTC_OBSERVE, P1_RESEARCH, POST_LONDON, POST_NEW_YORK, PRE_FLIGHT,
    PRE_LONDON_READINESS, PRE_LONDON_REFERENCE, PRE_NEW_YORK, STANDBY, WINDOW_ASIAN_LONDON,
    WINDOW_LONDON_NEWYORK, next_boundary_utc, resolve_state, transitions_between,
)


def _utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


class TestTimezone:
    def test_mmt_is_fixed_offset_not_integer_hours(self):
        assert tzu.MMT.utcoffset(None) == dt.timedelta(hours=6, minutes=30)

    def test_utc_to_mmt_roundtrip(self):
        ts = _utc(2026, 9, 10, 6, 30)
        mmt = tzu.utc_to_mmt(ts)
        assert mmt.hour == 13 and mmt.minute == 0
        assert tzu.mmt_to_utc(mmt) == ts

    def test_day_boundary_handling(self):
        # 23:45 UTC -> 06:15 MMT the *next* calendar day.
        ts = _utc(2026, 9, 10, 23, 45)
        mmt = tzu.utc_to_mmt(ts)
        assert mmt.date() == dt.date(2026, 9, 11)
        assert (mmt.hour, mmt.minute) == (6, 15)

    def test_naive_timestamp_rejected(self):
        with pytest.raises(ValueError):
            tzu.ensure_utc(dt.datetime(2026, 9, 10, 6, 30))


class TestSchedule:
    @pytest.mark.parametrize("hm,expected", [
        ((6, 25), PRE_FLIGHT),
        ((6, 29), PRE_FLIGHT),
        ((6, 30), BTC_OBSERVE),
        ((6, 44), BTC_OBSERVE),
        ((6, 45), BTC_FINALIZE),
        ((6, 49), BTC_FINALIZE),
        ((6, 50), PRE_LONDON_REFERENCE),
        ((6, 54), PRE_LONDON_REFERENCE),
        ((6, 55), PRE_LONDON_READINESS),
        ((6, 59), PRE_LONDON_READINESS),
        ((7, 0), WINDOW_ASIAN_LONDON),
        ((10, 59), WINDOW_ASIAN_LONDON),
        ((11, 0), POST_LONDON),
        ((11, 4), POST_LONDON),
        ((11, 5), STANDBY),
        ((11, 54), STANDBY),
        ((11, 55), PRE_NEW_YORK),
        ((11, 59), PRE_NEW_YORK),
        ((12, 0), WINDOW_LONDON_NEWYORK),
        ((14, 59), WINDOW_LONDON_NEWYORK),
        ((15, 0), POST_NEW_YORK),
        ((15, 9), POST_NEW_YORK),
        ((15, 10), P1_RESEARCH),
        ((23, 59), P1_RESEARCH),
        ((0, 0), P1_RESEARCH),
        ((6, 24), P1_RESEARCH),
    ])
    def test_state_transitions(self, hm, expected):
        ts = _utc(2026, 9, 10, *hm)
        assert resolve_state(ts) == expected

    def test_next_boundary(self):
        ts = _utc(2026, 9, 10, 6, 32)
        assert next_boundary_utc(ts) == _utc(2026, 9, 10, 6, 45)

    def test_next_boundary_from_open_ended_p1_research_is_tomorrow_preflight(self):
        ts = _utc(2026, 9, 10, 20, 0)
        assert next_boundary_utc(ts) == _utc(2026, 9, 11, 6, 25)

    def test_btc_finalize_exists_between_observe_and_pre_london(self):
        # BTC_OBSERVE must never jump straight to PRE_LONDON_REFERENCE.
        assert resolve_state(_utc(2026, 9, 10, 6, 46)) == BTC_FINALIZE

    def test_transitions_between_is_deterministic_and_logged(self):
        start = _utc(2026, 9, 10, 6, 25)
        end = _utc(2026, 9, 10, 7, 5)
        transitions = transitions_between(start, end)
        states = [t.to_state for t in transitions]
        assert states == [PRE_FLIGHT, BTC_OBSERVE, BTC_FINALIZE, PRE_LONDON_REFERENCE, PRE_LONDON_READINESS, WINDOW_ASIAN_LONDON]
        assert transitions[0].from_state is None
        assert transitions[1].from_state == PRE_FLIGHT
