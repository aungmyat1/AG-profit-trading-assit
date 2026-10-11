"""AGP-LANE-B2: ST_CRYPTO_CFD_SWEEP_RETEST_V1 evaluate() ignores every bar whose close_time > now.

A forming H1 or D1 bar (opened before `now`, closing after it) must not change any output,
however extreme it is; closed-only input stays byte-identical to the frozen rules.evaluate.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import crypto_cfd_contract  # noqa: E402
import scripts.ccfd_sweep_retest_replay as R  # noqa: E402
from crypto_cfd_contract import guard, rules  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from ticket_delivery.renderer import payload_hash  # noqa: E402
from v1_tickets import crypto_cfd  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 9, 18, 45, tzinfo=UTC)      # BTCUSD ENTRY_VALID instant on VT data
CFG = R.load_market_structure_config()


@pytest.fixture(scope="module")
def btc():
    data = R.load_symbol("BTCUSD")
    x = R.closed_inputs(data, NOW, {"D1": 50, "H1": 100, "M15": 96, "M5": 576})
    return data, x


def _spike(open_time: dt.datetime, ref: Candle, up: bool) -> Candle:
    p = ref.close * (3.0 if up else 0.2)      # far outside any real range
    return Candle(open_time, ref.close, max(p, ref.close), min(p, ref.close), p)


def _forming(tf: str, now: dt.datetime) -> dt.datetime:
    if tf == "H1":
        return now.replace(minute=0)           # opened 18:00, closes 19:00 > 18:45
    d1_open = max(t for t in R.load_symbol("BTCUSD")["times"]["D1"] if t < now)
    assert guard.bar_close_utc(Candle(d1_open, 1, 1, 1, 1), "d1") > now
    return d1_open                               # the recorded D1 bar still open at `now`


def _eval(x, entry=guard.evaluate):
    return entry("BTCUSD", NOW, x["D1"], x["H1"], x["M5"], x["M15"], structure_config=CFG)


def test_package_entry_point_is_the_guard():
    assert crypto_cfd_contract.evaluate is guard.evaluate
    assert crypto_cfd.evaluate is guard.evaluate


def test_closed_only_input_is_byte_identical_to_frozen_rules(btc):
    _, x = btc
    a, b = _eval(x), _eval(x, rules.evaluate)
    assert a["result"] == "ENTRY_VALID" and payload_hash(a) == payload_hash(b)
    assert "open_bar_guard" not in a["evidence"]["causal_filter"]


@pytest.mark.parametrize("tf", ["H1", "D1"])
@pytest.mark.parametrize("up", [True, False])
def test_open_htf_bar_cannot_affect_output(btc, tf, up):
    _, x = btc
    base = _eval(x)
    open_time = _forming(tf, NOW)
    rows = [c for c in x[tf] if c.time < open_time] + [_spike(open_time, x[tf][-1], up)]
    out = _eval({**x, tf: rows})
    assert R.semantic(out) == R.semantic(base)
    assert out["reason_codes"] == base["reason_codes"]
    assert {k: v for k, v in out["evidence"].items() if k != "causal_filter"} == \
        {k: v for k, v in base["evidence"].items() if k != "causal_filter"}
    guard_ev = out["evidence"]["causal_filter"]["open_bar_guard"]
    assert guard_ev["dropped_forming"][tf.lower()] == 1 and sum(guard_ev["dropped_forming"].values()) == 1


@pytest.mark.parametrize("tf", ["H1", "D1"])
def test_frozen_rules_alone_would_admit_the_forming_bar(btc, tf):
    """Shows the gap the guard closes: rules.evaluate keeps a bar timestamped before `now`."""
    _, x = btc
    open_time = _forming(tf, NOW)
    rows = [c for c in x[tf] if c.time < open_time] + [_spike(open_time, x[tf][-1], True)]
    raw = _eval({**x, tf: rows}, rules.evaluate)
    assert raw["evidence"]["causal_filter"]["closed_candles"][tf.lower()] == len(rows)


def test_vt_forming_h1_bar_flips_frozen_rules_but_not_the_guard(btc):
    """Non-vacuous on recorded VT data: an open H1 bar flips rules.evaluate (ENTRY_VALID ->
    WAITING_SWEEP via H1 BULLISH); the guarded entry point keeps ENTRY_VALID."""
    _, x = btc
    open_time = _forming("H1", NOW)
    rows = [c for c in x["H1"] if c.time < open_time] + [_spike(open_time, x["H1"][-1], True)]
    assert _eval({**x, "H1": rows}, rules.evaluate)["result"] != "ENTRY_VALID"
    assert _eval({**x, "H1": rows})["result"] == "ENTRY_VALID"


def test_synthetic_forming_d1_bar_flips_frozen_rules_but_not_the_guard():
    """Non-vacuous for D1: a forming server-day bar with a bullish break would veto the SHORT via
    HTF_DIRECTION_CONFLICT under rules.evaluate; the guard ignores it."""
    import test_crypto_cfd_strategy_contract_v1 as C

    def d1(i, o, h, lo, c):
        return Candle(dt.datetime(2025, 12, 30, 22, tzinfo=UTC) + dt.timedelta(days=i), o, h, lo, c, 1.0)
    closed = [d1(0, 95, 96, 94, 95), d1(1, 96, 100, 95, 97), d1(2, 96, 97, 90, 92), d1(3, 93, 97, 92, 95),
              d1(4, 94, 95, 93, 94), d1(5, 94, 95, 93, 94), d1(6, 94, 95, 93, 94)]
    forming = d1(7, 94, 130, 93, 125)
    assert forming.time < C.NOW < guard.bar_close_utc(forming, "d1")
    m5 = C._prev_day_m5(**C.BTC_REF_SHORT) + list(C.BTC_SHORT_DAY)

    def run(entry, d):
        return entry("BTCUSD", C.NOW, d, C.BTC_H1_BEARISH, m5, structure_config=C.CFG)
    assert run(rules.evaluate, closed + [forming])["reason_codes"] == ["HTF_DIRECTION_CONFLICT"]
    base, out = run(guard.evaluate, closed), run(guard.evaluate, closed + [forming])
    assert base["result"] == out["result"] == "ENTRY_VALID"
    assert {k: v for k, v in out["evidence"].items() if k != "causal_filter"} == \
        {k: v for k, v in base["evidence"].items() if k != "causal_filter"}


def test_open_m5_and_m15_bars_are_dropped_too(btc):
    _, x = btc
    m5_open, m15_open = NOW - dt.timedelta(minutes=2), NOW - dt.timedelta(minutes=10)
    extra = {"M5": x["M5"] + [_spike(m5_open, x["M5"][-1], True)],
             "M15": x["M15"] + [_spike(m15_open, x["M15"][-1], False)]}
    out = _eval({**x, **extra})
    assert R.semantic(out) == R.semantic(_eval(x))
    assert out["evidence"]["causal_filter"]["open_bar_guard"]["dropped_forming"] == {"d1": 0, "h1": 0, "m5": 1,
                                                                                   "m15": 1}


def test_bar_closing_exactly_at_now_is_kept(btc):
    _, x = btc
    last = x["H1"][-1]
    assert guard.bar_close_utc(last, "h1") <= NOW and guard.drop_open_bars([last], "h1", NOW) == [last]


def test_d1_close_uses_server_day_across_dst():
    # US DST ends 2026-11-01: the server D1 opening 2026-10-31T21:00Z spans 25h, not 24h.
    d1 = Candle(dt.datetime(2026, 10, 31, 21, tzinfo=UTC), 1, 1, 1, 1)
    close = guard.bar_close_utc(d1, "d1")
    assert close - d1.time == dt.timedelta(hours=25)
    assert guard.drop_open_bars([d1], "d1", d1.time + dt.timedelta(hours=24)) == []
    assert guard.drop_open_bars([d1], "d1", close) == [d1]
