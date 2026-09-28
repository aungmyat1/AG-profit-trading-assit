"""AG_OUTCOME_RESOLUTION_CONTRACT_V2 resolver: post-fill invariant, positive controls,
same-bar policy, missing data, exclusions, friction, future mutation, determinism."""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import yaml

from outcome_resolution.v2 import (
    AMBIGUOUS_SAME_BAR,
    EXCLUDED_NO_POST_FILL_WINDOW,
    EXCLUDED_TP1_NOT_BEYOND_ENTRY,
    PIP_SIZE,
    RESOLVED_SESSION_EXIT,
    RESOLVED_SL,
    RESOLVED_TP1_BE,
    RESOLVED_TP1_TP2,
    UNRESOLVED_MISSING_M1,
    OpportunityInput,
    resolve_v2,
)
from strategy_engine.session import Candle

UTC = dt.timezone.utc
DAY = dt.date(2026, 7, 1)
M1 = dt.timedelta(minutes=1)
REPO = Path(__file__).resolve().parents[1]


def at(h, m=0):
    return dt.datetime.combine(DAY, dt.time(h, m), tzinfo=UTC)


# LONG: box 1.1000-1.1030, sweep bar 07:00-07:15 low 1.0990, close 1.1005 -> risk 15 pips,
# TP1 1.1030 (tp1_R 25/15), TP2 = 1.1005 + 5*0.0015 = 1.1080.
LONG = OpportunityInput(
    opportunity_id="cand_x", cycle="POST_ASIAN", trading_date=DAY, direction="LONG",
    sweep_open_time=at(7), sweep_close=1.1005, stop=1.0990, box_high=1.1030, box_low=1.1000,
    session_cutoff=at(11), engine_entry=1.1002,
)
SHORT = replace(LONG, direction="SHORT", sweep_close=1.1025, stop=1.1040)  # TP1 = box_low 1.1000


def flat(t, px=1.1010):
    return Candle(time=t, open=px, high=px + 0.0001, low=px - 0.0001, close=px)


def series(start, end, px=1.1010, overrides=None):
    overrides = overrides or {}
    out, t = [], start
    while t < end:
        out.append(overrides.get(t, flat(t, px)))
        t += M1
    return out


def bar(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c)


def sweep_candle_m1():
    """M1 bars INSIDE the sweep candle; one of them prints the wick low == stop."""
    ov = {at(7, 3): bar(at(7, 3), 1.1001, 1.1002, 1.0990, 1.0995)}
    return series(at(7), at(7, 15), px=1.1003, overrides=ov)


# --- the historical defect ------------------------------------------------------------


def test_prefill_sweep_wick_never_resolves_sl():
    """V1 resolved from the sweep bar's open and hit SL on the sweep wick itself. V2 must not."""
    bars = sweep_candle_m1() + series(at(7, 15), at(11))
    out = resolve_v2(LONG, bars)
    assert out.state != RESOLVED_SL
    assert out.state == RESOLVED_SESSION_EXIT
    assert all(e["time"] >= at(7, 15).isoformat() for e in out.events)
    assert out.entry_fill_time == at(7, 15).isoformat()


def test_prefill_bars_are_irrelevant_to_the_result():
    post = series(at(7, 15), at(11))
    assert asdict(resolve_v2(LONG, sweep_candle_m1() + post)) == asdict(resolve_v2(LONG, post))


# --- positive controls ----------------------------------------------------------------


def test_sl_after_entry_resolves_normally():
    ov = {at(8): bar(at(8), 1.1000, 1.1001, 1.0989, 1.0992)}
    out = resolve_v2(LONG, series(at(7, 15), at(11), overrides=ov))
    assert (out.state, out.gross_R) == (RESOLVED_SL, -1.0)
    assert out.exit_time == at(8, 1).isoformat()
    assert out.holding_minutes == 46.0


def test_sl_on_the_very_first_post_fill_bar_resolves():
    ov = {at(7, 15): bar(at(7, 15), 1.1005, 1.1006, 1.0990, 1.0991)}
    assert resolve_v2(LONG, series(at(7, 15), at(11), overrides=ov)).state == RESOLVED_SL


def test_tp1_then_runner_breakeven():
    ov = {at(8): bar(at(8), 1.1025, 1.1031, 1.1024, 1.1028),
          at(9): bar(at(9), 1.1010, 1.1011, 1.1004, 1.1006)}
    out = resolve_v2(LONG, series(at(7, 15), at(11), px=1.1020, overrides=ov))
    assert out.state == RESOLVED_TP1_BE
    assert out.gross_R == pytest.approx(0.75 * (0.0025 / 0.0015))


def test_tp1_then_tp2():
    ov = {at(8): bar(at(8), 1.1025, 1.1031, 1.1024, 1.1028),
          at(9): bar(at(9), 1.1070, 1.1081, 1.1069, 1.1080)}
    out = resolve_v2(LONG, series(at(7, 15), at(11), px=1.1040, overrides=ov))
    assert out.state == RESOLVED_TP1_TP2
    assert out.gross_R == pytest.approx(0.75 * (0.0025 / 0.0015) + 0.25 * 5.0)


def test_breakeven_not_armed_on_tp1_bar():
    ov = {at(8): bar(at(8), 1.1004, 1.1031, 1.1004, 1.1028)}  # TP1 bar also dips to entry
    out = resolve_v2(LONG, series(at(7, 15), at(11), px=1.1020, overrides=ov))
    assert out.state == RESOLVED_SESSION_EXIT  # runner survives, marked at cutoff


def test_session_exit_marks_full_position_at_last_close():
    out = resolve_v2(LONG, series(at(7, 15), at(11), px=1.1011))
    assert out.state == RESOLVED_SESSION_EXIT
    assert out.gross_R == pytest.approx((1.1011 - 1.1005) / 0.0015)
    assert out.exit_time == at(11).isoformat()


def test_short_is_symmetric():
    ov = {at(8): bar(at(8), 1.1030, 1.1041, 1.1029, 1.1035)}
    assert resolve_v2(SHORT, series(at(7, 15), at(11), px=1.1020, overrides=ov)).state == RESOLVED_SL


# --- same-bar ambiguity (signed conservative rule) -----------------------------------


def test_sl_and_tp1_same_bar_is_ambiguous_and_unscored():
    ov = {at(8): bar(at(8), 1.1010, 1.1031, 1.0989, 1.1010)}
    out = resolve_v2(LONG, series(at(7, 15), at(11), overrides=ov))
    assert out.state == AMBIGUOUS_SAME_BAR
    assert out.gross_R is None and out.net_R is None


def test_breakeven_and_tp2_same_bar_is_ambiguous():
    ov = {at(8): bar(at(8), 1.1025, 1.1031, 1.1024, 1.1028),
          at(9): bar(at(9), 1.1040, 1.1081, 1.1004, 1.1050)}
    out = resolve_v2(LONG, series(at(7, 15), at(11), px=1.1040, overrides=ov))
    assert out.state == AMBIGUOUS_SAME_BAR


# --- data policy / exclusions --------------------------------------------------------


def test_missing_post_fill_minute_is_unresolved():
    bars = [b for b in series(at(7, 15), at(11)) if b.time != at(9, 30)]
    assert resolve_v2(LONG, bars).state == UNRESOLVED_MISSING_M1


def test_fill_at_cutoff_is_excluded():
    opp = replace(LONG, sweep_open_time=at(10, 45))
    assert resolve_v2(opp, series(at(10, 45), at(11))).state == EXCLUDED_NO_POST_FILL_WINDOW


def test_tp1_not_beyond_entry_is_excluded():
    opp = replace(LONG, sweep_close=1.1035)
    assert resolve_v2(opp, series(at(7, 15), at(11))).state == EXCLUDED_TP1_NOT_BEYOND_ENTRY


def test_friction_is_three_pips_over_risk():
    ov = {at(8): bar(at(8), 1.1000, 1.1001, 1.0989, 1.0992)}
    out = resolve_v2(LONG, series(at(7, 15), at(11), overrides=ov))
    assert out.friction_R == pytest.approx(3 * PIP_SIZE / 0.0015)
    assert out.net_R == pytest.approx(-1.0 - 0.2)


# --- look-ahead / determinism --------------------------------------------------------


def test_bars_after_cutoff_or_resolution_cannot_change_outcome():
    ov = {at(8): bar(at(8), 1.1000, 1.1001, 1.0989, 1.0992)}
    base = series(at(7, 15), at(11), overrides=ov)
    future = [bar(at(11) + i * M1, 1.2, 1.3, 1.0, 1.25) for i in range(30)]
    mutated_after_sl = [bar(b.time, 1.3, 1.4, 1.2, 1.3) if b.time > at(8) else b for b in base]
    a = asdict(resolve_v2(LONG, base))
    assert asdict(resolve_v2(LONG, base + future)) == a
    b = asdict(resolve_v2(LONG, mutated_after_sl))
    assert (b["state"], b["gross_R"], b["exit_time"]) == (a["state"], a["gross_R"], a["exit_time"])


def test_deterministic():
    bars = sweep_candle_m1() + series(at(7, 15), at(11))
    assert asdict(resolve_v2(LONG, bars)) == asdict(resolve_v2(LONG, list(reversed(bars))))


# --- frozen contract consistency -----------------------------------------------------


def test_resolver_constants_match_frozen_contract():
    c = yaml.safe_load((REPO / "config/governance/AG_OUTCOME_RESOLUTION_CONTRACT_V2.yaml").read_text(encoding="utf-8"))
    assert c["resolution_start"]["semantics"] == "POST_FILL"
    assert c["stop_loss"]["mode"] == "SWEEP_WICK_EXTREME"
    assert c["entry"]["mode"] == "SWEEP_CONFIRMATION_CANDLE_CLOSE"
    assert {v["state"] for v in c["exits_disabled"].values() if isinstance(v, dict)} == {"OFF"}
    assert c["targets"]["tp1"]["volume_pct"] == 0.75 and c["targets"]["tp2"]["r_multiple"] == 5.0
    assert (c["friction"]["spread_pips"], c["friction"]["slippage_pips"]) == (2.0, 1.0)
    assert c["authority"]["proposal_authority"] == "NONE"


def test_v1_records_untouched():
    recs = sorted((REPO / "artifacts/outcome_resolution/records").glob("*.json"))
    assert len(recs) == 13
    digest = hashlib.sha256(b"".join(p.read_bytes().replace(b"\r\n", b"\n") for p in recs)).hexdigest()
    assert digest == V1_RECORDS_DIGEST


V1_RECORDS_DIGEST = "5fcbd6dcae207997713309e2351b9cbb8eaf1467ec771d3570e50210abe8e3b1"  # 13 files, last changed 335edb8
