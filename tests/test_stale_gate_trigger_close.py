"""AGP-TTU-02: stale-data gate must not erase the trigger close (RC1), a stale engine NO_TRADE
is restored only after the trade window closes (RC2), and TRIGGER_TF stays consistent with
the strategy YAML declarations (RC3).  Pure: no broker, no network, no candles provider."""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from v1_tickets import actionability as A  # noqa: E402
from v1_tickets import fx as v1_fx  # noqa: E402
from v1_tickets.canonical_ticket import build_canonical_ticket  # noqa: E402
from v1_tickets.guards import STALE, gate_ready  # noqa: E402
from v1_tickets.policy_loader import POLICY_ID, POLICY_OK, ActionabilityPolicy  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 7)
M15 = dt.timedelta(minutes=15)
STRATEGY = "ST_ASIAN_SWEEP_5R_V1"

SIGNED_POLICY = ActionabilityPolicy(
    status=POLICY_OK, policy_id=POLICY_ID, version=1, min_remaining_r=0.1,
    signed_by="test-fixture", signed_at="2026-10-07", source_path="<fixture>", reason=None,
)


def _t(hhmm: str) -> dt.datetime:
    h, m = map(int, hhmm.split(":"))
    return dt.datetime(2026, 10, 7, h, m, tzinfo=UTC)


def _ready(*, setup="TREND", signal_ts=None, direction="SHORT", entry=1.12403, sl=1.12539,
           tp1=1.12268, tp2=1.11726, strategy_id=STRATEGY, cycle="ASIAN_LONDON"):
    """Pre-gate READY ticket shaped like v1_tickets.fx.build_fx_ticket output."""
    return {"strategy_id": strategy_id, "strategy_version": "1.1.1", "symbol": "EURUSD",
            "cycle": cycle, "session_date": DAY.isoformat(), "data_source": "MT5_VT_MARKETS_DEMO",
            "decision": "READY", "reason_code": "ENGINE_REASON", "setup": setup,
            "signal_timestamp": signal_ts.isoformat() if signal_ts else None,
            "direction": direction, "entry_order_type": "MARKET", "entry": entry, "stop_loss": sl,
            "risk_distance": abs(entry - sl),
            "targets": [{"leg": 1, "price": tp1}, {"leg": 2, "price": tp2}]}


def _no_trade(engine_reason="NO_QUALIFIED_SWEEP_IN_WINDOW", cycle="LONDON_NEWYORK"):
    return {"strategy_id": STRATEGY, "strategy_version": "1.1.1", "symbol": "USDJPY",
            "cycle": cycle, "session_date": DAY.isoformat(), "data_source": "MT5_VT_MARKETS_DEMO",
            "decision": "NO_TRADE", "reason_code": engine_reason, "setup": "NONE",
            "signal_timestamp": None}


def _gate(ticket, *, now, data_close, signal_close):
    return gate_ready(ticket, now=now, data_close=data_close, signal_close=signal_close,
                      spread=0.00005, risk=ticket.get("risk_distance"))


def _act(ticket, *, now, window_end, current_price=None, policy=None):
    return A.evaluate_actionability(ticket, now=now, current_price=current_price,
                                    window_end=window_end, policy=policy,
                                    policy_root="/nonexistent")


# ---- RC1 -------------------------------------------------------------------------------

def test_stale_data_gate_preserves_trigger_close_on_ready():
    gated = _gate(_ready(), now=_t("17:56"), data_close=_t("11:00"), signal_close=_t("07:15"))
    assert gated["decision"] == STALE and gated["reason_code"] == "STALE_DATA"
    assert gated["suppressed_decision"] == "READY"
    assert gated["signal_close_utc"] == _t("07:15").isoformat()


def test_stale_data_gate_adds_no_trigger_close_to_no_trade():
    gated = _gate(_no_trade(), now=_t("17:56"), data_close=_t("15:00"), signal_close=None)
    assert gated["decision"] == STALE and "signal_close_utc" not in gated


def test_a_post_window_trend_stale_is_expired():
    gated = _gate(_ready(), now=_t("17:56"), data_close=_t("11:00"), signal_close=_t("07:15"))
    out = _act(gated, now=_t("17:56"), window_end=_t("11:00"), current_price=1.11959)
    assert (out["actionability_decision"], out["actionability_reason"]) == (A.EXPIRED, "TRADE_WINDOW_CLOSED")
    assert out["trigger_bar_close_utc"] == _t("07:15").isoformat()


# ---- RC2 -------------------------------------------------------------------------------

def test_b_post_window_engine_no_trade_stale_restores_engine_reason():
    gated = _gate(_no_trade("NO_QUALIFIED_SWEEP_IN_WINDOW"), now=_t("17:56"),
                  data_close=_t("15:00"), signal_close=None)
    out = _act(gated, now=_t("17:56"), window_end=_t("15:00"), current_price=157.97)
    assert (out["actionability_decision"], out["actionability_reason"]) == (
        A.NO_TRADE, "NO_QUALIFIED_SWEEP_IN_WINDOW")


@pytest.mark.parametrize("current", [1.1200, 1.1230, 1.1236, 1.1240, 1.1250, 1.1260])
def test_c_open_window_ready_stale_never_watch_ready(current):
    # Signal bar 07:15-07:30; last data bar closed 07:30; now 07:50 -> data 20 min old (stale)
    # while the trigger is still within the 2-bar freshness window.  Signed policy on purpose.
    gated = _gate(_ready(direction="LONG", entry=1.1236, sl=1.1226, tp1=1.1256, tp2=1.1286),
                  now=_t("07:50"), data_close=_t("07:30"), signal_close=_t("07:30"))
    out = _act(gated, now=_t("07:50"), window_end=_t("11:00"), current_price=current,
               policy=SIGNED_POLICY)
    assert out["actionability_decision"] != A.WATCH_READY
    assert out["actionability_reason"] != "TRIGGER_TIMEFRAME_UNKNOWN"


def test_c_open_window_ready_stale_is_info_only_stale_data():
    gated = _gate(_ready(direction="LONG", entry=1.1236, sl=1.1226, tp1=1.1256, tp2=1.1286),
                  now=_t("07:50"), data_close=_t("07:30"), signal_close=_t("07:30"))
    out = _act(gated, now=_t("07:50"), window_end=_t("11:00"), current_price=1.1238,
               policy=SIGNED_POLICY)
    assert (out["actionability_decision"], out["actionability_reason"]) == (A.INFO_ONLY_STALE, "STALE_DATA")


def test_d_open_window_no_trade_stale_stays_fail_closed():
    gated = _gate(_no_trade(cycle="ASIAN_LONDON"), now=_t("08:00"), data_close=_t("07:30"),
                  signal_close=None)
    out = _act(gated, now=_t("08:00"), window_end=_t("11:00"), current_price=157.97,
               policy=SIGNED_POLICY)
    assert (out["actionability_decision"], out["actionability_reason"]) == (A.INFO_ONLY_STALE, "STALE_DATA")


# ---- unchanged fail-closed / SWEEP behavior -----------------------------------------------

@pytest.mark.parametrize("stale", [False, True])
def test_e_unknown_strategy_timeframe_still_fails_closed(stale):
    now = _t("07:35")
    gated = _gate(_ready(strategy_id="ST_UNDECLARED_TF_V1"), now=now,
                  data_close=_t("06:00") if stale else _t("07:30"), signal_close=_t("07:30"))
    out = _act(gated, now=now, window_end=_t("11:00"), current_price=1.1235)
    assert (out["actionability_decision"], out["actionability_reason"]) == (
        A.INSUFFICIENT_DATA, "TRIGGER_TIMEFRAME_UNKNOWN")


def test_f_sweep_post_window_stale_unchanged():
    sig = _t("07:30")
    gated = _gate(_ready(setup="SWEEP", signal_ts=sig, direction="LONG", entry=158.298, sl=158.259,
                         tp1=158.502, tp2=158.493),
                  now=_t("17:56"), data_close=_t("11:00"), signal_close=sig + M15)
    out = _act(gated, now=_t("17:56"), window_end=_t("11:00"), current_price=157.9735)
    assert (out["actionability_decision"], out["actionability_reason"]) == (A.EXPIRED, "TRADE_WINDOW_CLOSED")
    assert out["trigger_bar_close_utc"] == (sig + M15).isoformat()


def test_f_fresh_ready_gate_output_unchanged():
    gated = _gate(_ready(), now=_t("07:40"), data_close=_t("07:30"), signal_close=_t("07:30"))
    assert gated["decision"] == "READY" and gated["signal_close_utc"] == _t("07:30").isoformat()
    assert "suppressed_decision" not in gated


# ---- RC3 -------------------------------------------------------------------------------

def _declared_trigger_tf(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if "timeframe" in spec:
        return spec["strategy_id"], str(spec["timeframe"]).upper()
    roles = spec["timeframe_responsibilities"]
    trigger = [tf for tf, role in roles.items() if role == "SWEEP_MSS_RETEST"]
    assert len(trigger) == 1, f"{path}: trigger timeframe not uniquely declared"
    return spec["strategy_id"], trigger[0].upper()


_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}


def test_g_trigger_tf_matches_strategy_yaml():
    declared = dict(_declared_trigger_tf(p) for p in (
        "strategies/ST_ASIAN_SWEEP_5R_V1.yaml", "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"))
    assert set(declared) == set(A.TRIGGER_TF)
    for strategy_id, tf in declared.items():
        assert A.TRIGGER_TF[strategy_id] == dt.timedelta(minutes=_TF_MINUTES[tf]), strategy_id


# ---- frozen replay of the 2026-10-07T17:56:02Z live smoke (8 evaluations) ------------------
# Reconstructed from the archived canonical journal: setup, direction, levels, current quote
# and SWEEP trigger bar are as recorded.  Engine NO_TRADE reason codes were not archived, so
# those two records carry reason_code=None.  data_close = trade-window end, as the MT5 provider
# reports once the window has closed.

REPLAY_NOW = dt.datetime(2026, 10, 7, 17, 56, 2, 375217, tzinfo=UTC)
REPLAY = [
    # symbol, cycle, setup, direction, entry, sl, tp1, tp2, current, sweep_signal_open
    ("EURUSD", "ASIAN_LONDON", "TREND", "SHORT", 1.12403, 1.12539, 1.12268, 1.11726, 1.11959, None),
    ("GBPUSD", "ASIAN_LONDON", "TREND", "SHORT", 1.32561, 1.32676, 1.32446, 1.31986, 1.321245, None),
    ("USDJPY", "ASIAN_LONDON", "SWEEP", "LONG", 158.298, 158.259, 158.502, 158.493, 157.9735, "07:30"),
    ("XAUUSD", "ASIAN_LONDON", "TREND", "SHORT", 4149.11, 4169.6, 4128.62, 4046.66, 4109.385, None),
    ("EURUSD", "LONDON_NEWYORK", "TREND", "SHORT", 1.1205, 1.12312, 1.11787, 1.10737, 1.11959, None),
    ("GBPUSD", "LONDON_NEWYORK", "TREND", "SHORT", 1.32347, 1.32538, 1.32156, 1.31392, 1.321245, None),
    ("USDJPY", "LONDON_NEWYORK", "NONE", None, None, None, None, None, 157.9735, None),
    ("XAUUSD", "LONDON_NEWYORK", "NONE", None, None, None, None, None, 4109.385, None),
]


def _replay_records(policy_root):
    out = []
    for sym, cycle, setup, direction, entry, sl, tp1, tp2, current, sweep_open in REPLAY:
        trade_start, trade_end = v1_fx.session_windows_utc(DAY)[cycle]["trade"]
        if setup == "NONE":
            ticket = {**_no_trade(engine_reason=None, cycle=cycle), "symbol": sym}
            signal_close = None
        else:
            sig_ts = _t(sweep_open) if sweep_open else None
            ticket = {**_ready(setup=setup, signal_ts=sig_ts, direction=direction, entry=entry, sl=sl,
                               tp1=tp1, tp2=tp2, cycle=cycle), "symbol": sym}
            # fx.build_fx_ticket: signal bar open, else the first trade-session bar; +1 M15.
            signal_close = (sig_ts or trade_start) + M15
        gated = _gate(ticket, now=REPLAY_NOW, data_close=trade_end, signal_close=signal_close)
        canon = build_canonical_ticket(gated, now=REPLAY_NOW, current_price=current,
                                       window_end=trade_end, policy_root=policy_root)
        out.append((sym, cycle, setup, canon["decision"], canon["reason_code"]))
    return out


def test_frozen_replay_2026_10_07(tmp_path):
    records = _replay_records(str(tmp_path))
    assert len(records) == 8 and all(r[3] for r in records)
    counts = {}
    for _, _, _, decision, _ in records:
        counts[decision] = counts.get(decision, 0) + 1
    assert counts == {A.EXPIRED: 6, A.NO_TRADE: 2}
    assert not [r for r in records if r[4] == "TRIGGER_TIMEFRAME_UNKNOWN"]
    for sym, cycle, setup, decision, reason in records:
        expected = (A.NO_TRADE, "NO_TRADE") if setup == "NONE" else (A.EXPIRED, "TRADE_WINDOW_CLOSED")
        assert (decision, reason) == expected, (sym, cycle)
