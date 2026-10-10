"""Manual Trade Ticket V1 Phase 2 (owner decision C3): DST is display/verification only.

Signed session windows stay fixed UTC on every date; local London/New York time is only a
diagnostic. Dates cover UK-BST/US-EDT, the 2026 autumn gap (UK GMT, US still EDT), both on
standard time, and the 2026 spring gap (US EDT, UK still GMT)."""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from session_clock import get_session_bounds, local_time_diagnostics
from strategy_engine.session import Candle
from v1_tickets.fx import build_fx_ticket, session_windows_utc

UTC = dt.timezone.utc
# date -> (London DST, New York DST)
DATES = {
    dt.date(2026, 10, 23): (True, True),     # both summer time
    dt.date(2026, 10, 27): (False, True),    # UK on GMT, US still EDT
    dt.date(2026, 11, 3): (False, False),    # both standard
    dt.date(2026, 3, 10): (False, True),     # spring: US EDT, UK still GMT
    dt.date(2026, 4, 14): (True, True),      # spring, both summer time
}
FIXED = {"ASIAN_LONDON": (("00:00", "06:00"), ("07:00", "11:00")),
         "LONDON_NEWYORK": (("06:00", "11:00"), ("12:00", "15:00"))}


def _hm(t: dt.datetime) -> str:
    return t.strftime("%H:%M")


@pytest.mark.parametrize("day", DATES)
def test_strategy_windows_are_fixed_utc_on_every_dst_state(day):
    w = session_windows_utc(day)
    for pair, (ref, trade) in FIXED.items():
        assert (_hm(w[pair]["ref"][0]), _hm(w[pair]["ref"][1])) == ref
        assert (_hm(w[pair]["trade"][0]), _hm(w[pair]["trade"][1])) == trade
        assert all(t.tzinfo == UTC and t.date() == day for t in (*w[pair]["ref"], *w[pair]["trade"]))
    assert get_session_bounds(day, "asian") == (dt.datetime.combine(day, dt.time(0), UTC),
                                                dt.datetime.combine(day, dt.time(6), UTC))


@pytest.mark.parametrize("day,dst", DATES.items())
def test_local_time_diagnostics_expose_dst_state(day, dst):
    trade_open = session_windows_utc(day)["ASIAN_LONDON"]["trade"][0]
    d = local_time_diagnostics(trade_open)
    assert (d["london"]["dst"], d["new_york"]["dst"]) == dst
    assert d["london"]["utc_offset"] == ("+01:00" if dst[0] else "+00:00")
    assert d["new_york"]["utc_offset"] == ("-04:00" if dst[1] else "-05:00")
    assert d["mmt"]["utc_offset"] == "+06:30" and d["mmt"]["dst"] is False
    assert d["london"]["local"].endswith("08:00" if dst[0] else "07:00")


@pytest.mark.parametrize("day", DATES)
def test_asian_range_never_includes_bars_after_london_open(day):
    w = session_windows_utc(day)["ASIAN_LONDON"]
    london_local_open_utc = dt.datetime.combine(day, dt.time(8), tzinfo=ZoneInfo("Europe/London")).astimezone(UTC)
    bars = [dt.datetime.combine(day, dt.time(0), UTC) + dt.timedelta(minutes=15 * i) for i in range(96)]
    ref = [b for b in bars if w["ref"][0] <= b < w["ref"][1]]
    assert len(ref) == 24 and _hm(ref[0]) == "00:00" and _hm(ref[-1]) == "05:45"
    last_close = ref[-1] + dt.timedelta(minutes=15)
    assert last_close <= w["trade"][0] and last_close <= london_local_open_utc


@pytest.mark.parametrize("day", DATES)
def test_dst_diagnostics_do_not_change_fixed_utc_eligibility(stub_symbol_verified, day):
    def c(h, m, o, hi, lo, cl):
        return Candle(dt.datetime.combine(day, dt.time(h, m), UTC), o, hi, lo, cl)
    session = [c(0, 0, 1.1000, 1.1050, 1.0950, 1.1010), c(0, 15, 1.1010, 1.1040, 1.0960, 1.1005)]
    post = [c(7, 0, 1.1005, 1.1006, 1.1004, 1.1005), c(7, 15, 1.1005, 1.1060, 1.1000, 1.1048)]
    at = dt.datetime.combine(day, dt.time(7, 35), UTC)
    kwargs = dict(data_source="FIXTURE", evaluated_at=at, data_close=at, spread=0.0001)
    before = build_fx_ticket("EURUSD", "ASIAN_LONDON", day, session, 2, post, **kwargs)
    local_time_diagnostics(at)
    after = build_fx_ticket("EURUSD", "ASIAN_LONDON", day, session, 2, post, **kwargs)
    assert before == after and before["decision"] == "READY"


def test_eligibility_path_does_not_import_zoneinfo():
    for rel in ("src/v1_tickets/fx.py", "src/strategy_engine/engine.py", "src/strategy_engine/session/router.py"):
        tree = ast.parse((Path(__file__).resolve().parents[1] / rel).read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "zoneinfo" not in names | mods and "local_time_diagnostics" not in names, rel
