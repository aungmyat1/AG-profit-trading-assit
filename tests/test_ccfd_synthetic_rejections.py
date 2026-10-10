"""AGP-LANE-B3 (owner ruling 2026-10-11, item 3): synthetic proofs for the rejection-only rules of
ST_CRYPTO_CFD_SWEEP_RETEST_V1 1.0.0 (SYNTHETIC_PROVEN cells of the rule-coverage matrix).

Every case runs through the production entry point crypto_cfd_contract.evaluate (the open-bar guard over the
frozen rules), for both symbols and both directions: the SHORT fixtures are the contract-test fixtures of
tests/test_crypto_cfd_strategy_contract_v1.py, and each LONG case is the exact price mirror (p -> K - p) of
its SHORT case. A rejection-only rule has no entry outcome; rules.evaluate takes no window input, so one case
per direction covers both window cells. Entry-branch rules are NOT proven here (they need VT exercise).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

from crypto_cfd_contract import evaluate, rules
from strategy_engine.session import Candle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_ccfd_contract_fixtures",
                                               ROOT / "tests/test_crypto_cfd_strategy_contract_v1.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

import scripts.ccfd_sweep_retest_replay as R  # noqa: E402

UTC = dt.timezone.utc
NOT_ENTRY = {r for r in vars(rules).values() if isinstance(r, str) and r.isupper()} - {rules.RESULT_ENTRY_VALID}
MIRROR_K = {"BTCUSD": 170000.0, "ETHUSD": 5400.0}

# SHORT base setups (contract-test fixtures) and per-rule variants
BASE = {
    "BTCUSD": dict(ref=F.BTC_REF_SHORT, day=F.BTC_SHORT_DAY, h1=F.BTC_H1_BEARISH, opp_h1=F.BTC_H1_BULLISH,
                   wrong_ref=F.BTC_REF_LONG, wrong_day=F.BTC_LONG_DAY,
                   geometry_refs=[dict(base=84000.0, hi=85000.0, lo=83900.0),    # TP1 on the wrong side
                                  dict(base=84000.0, hi=85000.0, lo=83000.0)],   # TP2 R < 1.5
                   invalid_stop_day=[F._m5(0, 85300, 85400, 85250, 85350), F._m5(1, 85350, 85360, 85200, 85250),
                                     F._m5(2, 85250, 85500, 85260, 85450), F._m5(3, 85150, 85180, 84800, 84900),
                                     F._m5(4, 84900, 84950, 84820, 84850), F._m5(5, 84850, 85210, 84840, 84900)],
                   no_touch=[(84100, 84140, 84060, 84120), (84120, 84150, 84080, 84100), (84100, 84130, 84050, 84090)],
                   dual=(84480, 85120, 82400, 84360), mss_bar=(84300, 84320, 84050, 84100)),
    "ETHUSD": dict(ref=F.ETH_REF_SHORT, day=F.ETH_SHORT_DAY, h1=F.ETH_H1_BEARISH, opp_h1=F.ETH_H1_BULLISH,
                   wrong_ref=F.ETH_REF_LONG, wrong_day=F.ETH_LONG_DAY,
                   geometry_refs=[dict(base=2650.0, hi=2700.0, lo=2530.0),
                                  dict(base=2650.0, hi=2700.0, lo=2480.0)],
                   invalid_stop_day=[F._m5(0, 2715, 2720, 2712, 2718), F._m5(1, 2718, 2719, 2710, 2712),
                                     F._m5(2, 2712, 2725, 2713, 2722), F._m5(3, 2708, 2709, 2690, 2695),
                                     F._m5(4, 2695, 2698, 2688, 2690), F._m5(5, 2690, 2711, 2689, 2692)],
                   no_touch=[(2600, 2608, 2595, 2602), (2602, 2609, 2596, 2600), (2600, 2607, 2594, 2599)],
                   dual=(2650, 2712, 2430, 2640), mss_bar=(2630, 2632, 2596, 2600)),
}
CASES = [(s, d) for s in BASE for d in ("SHORT", "LONG")]


def _flip(c: Candle, k: float) -> Candle:
    return Candle(time=c.time, open=k - c.open, high=k - c.low, low=k - c.high, close=k - c.close, volume=1.0)


def run(symbol, side, *, ref, day, h1, d1=None, now=F.NOW, prev=None):
    """Evaluate a SHORT-oriented synthetic case, mirrored to LONG when side == LONG."""
    prev = F._prev_day_m5(**ref) if prev is None else prev
    m5, d1 = prev + list(day), (F.D1_FLAT if d1 is None else d1)
    if side == "LONG":
        k = MIRROR_K[symbol]
        m5, h1, d1 = ([_flip(c, k) for c in rows] for rows in (m5, h1, d1))
    return evaluate(symbol, now, d1, h1, m5, structure_config=F.CFG)


def bar(idx, ohlc, **kw):
    return F._m5(idx, *ohlc, **kw)


@pytest.mark.parametrize("symbol,side", CASES)
def test_mirror_reproduces_the_entry_branch(symbol, side):
    """Sanity: the mirrored base setup is the opposite-direction ENTRY_VALID, so each LONG rejection below is a
    LONG-branch rejection (not an artefact of the mirror)."""
    b = BASE[symbol]
    r = run(symbol, side, ref=b["ref"], day=b["day"], h1=b["h1"])
    assert r["result"] == rules.RESULT_ENTRY_VALID and r["evidence"]["target_plan"]["direction"] == side


@pytest.mark.parametrize("symbol,side", CASES)
def test_incomplete_reference_fails_closed(symbol, side):
    b = BASE[symbol]
    r = run(symbol, side, ref=b["ref"], day=b["day"], h1=b["h1"], prev=F._prev_day_m5(**b["ref"])[:287])
    assert r["result"] == rules.RESULT_REFERENCE_INCOMPLETE


@pytest.mark.parametrize("symbol,side", CASES)
def test_h1_unresolved_gives_no_direction(symbol, side):
    b = BASE[symbol]
    r = run(symbol, side, ref=b["ref"], day=b["day"], h1=F.D1_FLAT)
    assert r["result"] == rules.RESULT_NO_DIRECTION and r["reason_codes"] == ["H1_STRUCTURE_UNRESOLVED"]


@pytest.mark.parametrize("symbol,side", CASES)
def test_d1_conflict_vetoes_direction(symbol, side):
    b = BASE[symbol]
    d1 = [Candle(time=c.time - dt.timedelta(days=200), open=c.open, high=c.high, low=c.low, close=c.close,
                 volume=1.0) for c in b["opp_h1"]]
    r = run(symbol, side, ref=b["ref"], day=b["day"], h1=b["h1"], d1=d1)
    assert r["result"] == rules.RESULT_NO_DIRECTION and r["reason_codes"] == ["HTF_DIRECTION_CONFLICT"]
    assert r["evidence"]["context"]["h1_structure"] == ("BEARISH" if side == "SHORT" else "BULLISH")


@pytest.mark.parametrize("symbol,side", CASES)
def test_dual_side_candle_only_blocks(symbol, side):
    """A candle piercing both levels and closing inside is skipped: alone it is no sweep (no entry), and a
    later single-side sweep in the same day is still taken -- the rule only blocks that candle."""
    b = BASE[symbol]
    alone = run(symbol, side, ref=b["ref"], day=list(b["day"][:3]) + [bar(3, b["dual"])], h1=b["h1"])
    assert alone["result"] == rules.RESULT_WAITING_SWEEP and "sweep" not in alone["evidence"]
    shifted = [bar(0, b["dual"])] + [bar(i + 1, (c.open, c.high, c.low, c.close)) for i, c in enumerate(b["day"])]
    later = run(symbol, side, ref=b["ref"], day=shifted, h1=b["h1"], now=F.NOW)
    assert later["result"] != rules.RESULT_ENTRY_VALID or \
        later["evidence"]["sweep"]["candle_time_utc"] != shifted[0].time.isoformat()
    assert "sweep" in later["evidence"] and later["evidence"]["sweep"]["candle_time_utc"] == shifted[4].time.isoformat()


@pytest.mark.parametrize("symbol,side", CASES)
def test_wrong_side_sweep_is_ignored(symbol, side):
    b = BASE[symbol]
    r = run(symbol, side, ref=b["wrong_ref"], day=b["wrong_day"], h1=b["h1"])
    assert r["result"] == rules.RESULT_WAITING_SWEEP and "sweep" not in r["evidence"]


@pytest.mark.parametrize("symbol,side", CASES)
def test_rule_1_no_retest_within_ttl_expires(symbol, side):
    b = BASE[symbol]
    day = list(b["day"][:6]) + [bar(6 + i, ohlc) for i, ohlc in enumerate(b["no_touch"])]
    r = run(symbol, side, ref=b["ref"], day=day, h1=b["h1"])
    assert r["result"] == rules.RESULT_ENTRY_WINDOW_PASSED and r["evidence"]["expiry"]["ttl_m5_bars"] == 3


@pytest.mark.parametrize("symbol,side", CASES)
def test_rule_2_utc_day_rotation_kills_the_sequence(symbol, side):
    """Sweep at the end of day D (WAITING_MSS); the bar that would confirm the MSS closes on D+1 -> the
    sequence is dead (reference maximum_age): no sweep/MSS carried, no entry."""
    b = BASE[symbol]
    base = b["ref"]["base"]
    d0 = dt.datetime(2026, 1, F.CUR_DAY, tzinfo=UTC)
    flat = [Candle(time=d0 + i * R.M5, open=base, high=base, low=base, close=base, volume=1.0) for i in range(282)]
    tail = [Candle(time=d0 + (282 + i) * R.M5, open=c.open, high=c.high, low=c.low, close=c.close, volume=1.0)
            for i, c in enumerate(list(b["day"][:5]) + [b["day"][4]])]
    day_d = flat + tail
    assert len(day_d) == 288
    control = run(symbol, side, ref=b["ref"], day=day_d, h1=b["h1"], now=d0 + 287 * R.M5)
    assert control["result"] == rules.RESULT_WAITING_MSS and "sweep" in control["evidence"]
    nxt = Candle(time=d0 + dt.timedelta(days=1), open=b["mss_bar"][0], high=b["mss_bar"][1], low=b["mss_bar"][2],
                 close=b["mss_bar"][3], volume=1.0)
    r = run(symbol, side, ref=b["ref"], day=day_d + [nxt], h1=b["h1"], now=nxt.time + R.M5)
    assert r["result"] != rules.RESULT_ENTRY_VALID and "sweep" not in r["evidence"] and "mss" not in r["evidence"]


@pytest.mark.parametrize("symbol,side", CASES)
def test_geometry_guard_rejects(symbol, side):
    b = BASE[symbol]
    for ref in b["geometry_refs"]:
        r = run(symbol, side, ref=ref, day=b["day"], h1=b["h1"])
        assert r["result"] == rules.RESULT_NO_TRADE_TARGET_GEOMETRY
        assert r["evidence"]["target_plan"]["direction"] == side and R.geometry_reject_ok(r["evidence"]["target_plan"])


@pytest.mark.parametrize("symbol,side", CASES)
def test_invalid_stop_distance_rejects(symbol, side):
    b = BASE[symbol]
    r = run(symbol, side, ref=b["ref"], day=b["invalid_stop_day"], h1=b["h1"])
    assert r["result"] == rules.RESULT_INVALID_STOP_DISTANCE and r["reason_codes"] == ["INVALID_STOP_DISTANCE"]
    assert r["evidence"]["target_plan"]["direction"] == side and r["evidence"]["target_plan"]["risk_distance"] is None


def test_every_synthetic_proof_names_a_test_here_and_only_rejection_rules():
    here = {n for n in globals() if n.startswith("test_")}
    assert set(R.SYNTHETIC_PROOFS.values()) <= here
    assert R.SYNTHETIC_TESTS == "tests/test_ccfd_synthetic_rejections.py"
    entry = {"stop_loss_contract.long", "stop_loss_contract.short", "targets_contract.tp1_tp2_min_tp2_r_multiple",
             "entry_timing_contract.actionable_event", "m5_trigger_contract.retest", "m5_trigger_contract.mss.confirmation",
             "m5_trigger_contract.sweep.long_candidate", "m5_trigger_contract.sweep.short_candidate"}
    assert not entry & set(R.SYNTHETIC_PROOFS)
    assert NOT_ENTRY  # sanity: result constants were discovered
