"""LSMC_ACTIONABILITY_POLICY_V1 (owner decisions D1-D4, 2026-10-07): post-signal actionability gate.

Fixtures replay the cases in docs/status/AG_V1_FIRST_NATURAL_READY_EVIDENCE_2026-10-07.md:
07:01 unclosed bar, XAUUSD 243.8-min late send, ETHUSDT R 0.18, GBPUSD duplicate after
suspend -> resume, and a reboot during a session. Prices are synthetic where the evidence did not
persist them; the timings and R_ref values match the evidence table.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "host"))

import live_candles_smoke as smoke  # noqa: E402
from host_delivery import lsmc_actionability as act  # noqa: E402
from host_delivery import telegram_message as tg  # noqa: E402
from host_delivery.lsmc_alert_dedup import AlertLedger  # noqa: E402
from large_smc_watch.watch import Snapshot, WatchTracker  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import fx as fx_tickets  # noqa: E402
from v1_tickets.scan_record import WATCH, classify_fx_ticket  # noqa: E402

UTC = dt.timezone.utc
POLICY = act.load_policy(str(ROOT))


def t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def opp(direction: str, choch: str, entry: float, extreme: float, target, expires: str, stop=None) -> dict:
    return {"direction": direction, "choch_time": choch + "+00:00", "entry_reference": entry,
            "sweep_extreme": extreme, "target_c11": target, "stop_c10": stop, "expires_at": expires + "+00:00"}


# ------------------------------------------------------------------------------- policy / config

def test_policy_is_versioned_operational_config_with_signed_values():
    assert (POLICY.policy_id, POLICY.policy_version) == ("LSMC_ACTIONABILITY_POLICY_V1", 1)
    assert (POLICY.min_remaining_r, POLICY.freshness_max_bars, POLICY.trigger_timeframe) == (1.5, 2, "M5")


def test_min_remaining_r_lives_only_in_the_policy_config():
    hits = [p for p in (ROOT / "strategies").rglob("*.y*ml") if "min_remaining_r" in p.read_text(encoding="utf-8")]
    assert hits == []


def test_missing_policy_fails_closed(tmp_path):
    with pytest.raises(act.PolicyError):
        act.load_policy(str(tmp_path))
    o = opp("LONG", "2026-10-06T17:50:00", 1.0, 0.9, 1.5, "2026-10-06T21:00:00")
    a = act.assess(o, send_ts=t("2026-10-06T17:56:00"), bid=1.0, ask=1.0, policy=None, last_heartbeat_ts=None)
    assert (a["outcome"], a["reason"]) == (act.INFO_ONLY, act.POLICY_UNAVAILABLE)


# ------------------------------------------------------------------------------- D1 freshness

def test_freshness_boundary_is_two_trigger_bars_inclusive():
    o = opp("LONG", "2026-10-06T10:00:00", 1.1000, 1.0990, 1.1030, "2026-10-06T12:00:00")
    hb = t("2026-10-06T09:58:00")
    edge = act.assess(o, send_ts=t("2026-10-06T10:15:00"), bid=1.0999, ask=1.1000, policy=POLICY, last_heartbeat_ts=hb)
    late = act.assess(o, send_ts=t("2026-10-06T10:15:01"), bid=1.0999, ask=1.1000, policy=POLICY,
                      last_heartbeat_ts=t("2026-10-06T10:08:00"))
    assert edge["trigger_bar_close_ts"] == "2026-10-06T10:05:00+00:00" and edge["freshness_age_seconds"] == 600
    assert (edge["state"], edge["outcome"]) == (act.FRESH, act.WATCH_READY)
    assert (late["state"], late["outcome"]) == (act.STALE, act.INFO_ONLY_STALE)


# ------------------------------------------------------------------------------- D2 remaining R

def test_watch_ready_requires_r_at_send_at_least_min_remaining_r():
    o = opp("LONG", "2026-10-06T10:00:00", 1.1000, 1.0990, 1.1030, "2026-10-06T12:00:00")   # R_AT_TRIGGER 3.0
    hb, send = t("2026-10-06T09:58:00"), t("2026-10-06T10:06:00")
    at = lambda ask: act.assess(o, send_ts=send, bid=ask - 0.0001, ask=ask, policy=POLICY, last_heartbeat_ts=hb)  # noqa: E731
    ready, short = at(1.1000), at(1.1005)
    assert ready["R_AT_TRIGGER"] == pytest.approx(3.0) and ready["outcome"] == act.WATCH_READY
    assert ready["send_price"] == 1.1000 and ready["send_price_side"] == "ASK" and ready["reference_price"] == 1.1
    assert short["R_AT_SEND"] == pytest.approx(25 / 15) and short["outcome"] == act.WATCH_READY
    worse = at(1.1010)
    assert worse["R_AT_SEND"] == pytest.approx(1.0)
    assert (worse["outcome"], worse["reason"]) == (act.INFO_ONLY, act.INSUFFICIENT_REMAINING_R)


def test_eth_low_r_case_is_info_only_with_both_r_values_shown():
    """ETHUSDT 2026-10-06 17:58:37: LONG, latency 3.6 min (fresh), R_ref 0.18."""
    o = opp("LONG", "2026-10-06T17:50:00", 4500.0, 4450.0, 4509.0, "2026-10-06T21:00:00")
    a = act.assess(o, send_ts=t("2026-10-06T17:58:37"), bid=4500.5, ask=4501.0, policy=POLICY,
                   last_heartbeat_ts=t("2026-10-06T17:53:30"))
    assert a["state"] == act.FRESH and a["R_AT_TRIGGER"] == pytest.approx(0.18)
    assert a["R_AT_SEND"] == pytest.approx(8 / 51)
    assert (a["outcome"], a["reason"]) == (act.INFO_ONLY, act.INSUFFICIENT_REMAINING_R)
    ev = {"symbol": "ETHUSDT", "to_state": "OPPORTUNITY", "alert_level": "OPPORTUNITY", "reference_id": "r",
          "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0", "payload": {"opportunity": o}}
    text = tg.format_alert(ev, price=4500.8, actionability=a)
    assert "ACTIONABILITY: INFO_ONLY (INSUFFICIENT_REMAINING_R) -- NOT ACTIONABLE" in text
    assert "R_AT_TRIGGER: 0.18  R_AT_SEND: 0.16" in text and "min 1.5" in text
    assert "send price (ASK): 4501" in text


def test_short_uses_bid_and_price_through_invalidation_is_info_only():
    o = opp("SHORT", "2026-10-06T10:00:00", 1.1000, 1.1010, 1.0970, "2026-10-06T12:00:00")
    hb, send = t("2026-10-06T09:58:00"), t("2026-10-06T10:06:00")
    ok = act.assess(o, send_ts=send, bid=1.1000, ask=1.1001, policy=POLICY, last_heartbeat_ts=hb)
    assert ok["send_price_side"] == "BID" and ok["R_AT_SEND"] == pytest.approx(3.0)
    through = act.assess(o, send_ts=send, bid=1.1011, ask=1.1012, policy=POLICY, last_heartbeat_ts=hb)
    assert (through["outcome"], through["reason"]) == (act.INFO_ONLY, act.PRICE_BEYOND_INVALIDATION)
    no_quote = act.assess(o, send_ts=send, bid=None, ask=None, policy=POLICY, last_heartbeat_ts=hb)
    assert (no_quote["outcome"], no_quote["reason"]) == (act.INFO_ONLY, act.SEND_PRICE_UNAVAILABLE)
    no_target = act.assess({**o, "target_c11": None}, send_ts=send, bid=1.1, ask=1.1, policy=POLICY,
                           last_heartbeat_ts=hb)
    assert (no_target["outcome"], no_target["reason"]) == (act.INFO_ONLY, act.GEOMETRY_INCOMPLETE)


def test_c10_stop_is_the_risk_anchor_when_present():
    o = opp("LONG", "2026-10-06T10:00:00", 1.1000, 1.0995, 1.1030, "2026-10-06T12:00:00", stop=1.0990)
    a = act.assess(o, send_ts=t("2026-10-06T10:06:00"), bid=1.0999, ask=1.1000, policy=POLICY,
                   last_heartbeat_ts=t("2026-10-06T09:58:00"))
    assert (a["risk_anchor"], a["risk_anchor_source"]) == (1.0990, "STOP_C10") and a["R_AT_SEND"] == pytest.approx(3.0)


# ------------------------------------------------------------------------------- D3 downtime

def test_xauusd_243_8_minute_late_send_after_downtime_is_missed_not_actionable():
    """XAUUSD 2026-10-07 04:33:50: SHORT, CHoCH bar closed 00:30:02 (243.8 min earlier), host powered
    off 23:06 -> 04:27, R_ref 2.39, price ~82% of the way to target at send."""
    send = t("2026-10-07T04:33:50")
    choch_close = send - dt.timedelta(minutes=243.8)
    o = opp("SHORT", (choch_close - dt.timedelta(minutes=5)).replace(tzinfo=None).isoformat(),
            2650.0, 2655.0, 2638.05, "2026-10-07T06:00:00")
    bid = 2650.0 - 0.82 * 11.95
    missed = act.assess(o, send_ts=send, bid=bid, ask=bid + 0.27, policy=POLICY,
                        last_heartbeat_ts=t("2026-10-06T23:05:00"))
    assert missed["R_AT_TRIGGER"] == pytest.approx(2.39)
    assert missed["freshness_age_seconds"] == pytest.approx(243.8 * 60)
    assert (missed["state"], missed["outcome"]) == (act.MISSED_DOWNTIME, act.MISSED_NOT_ACTIONABLE)
    assert missed["R_AT_SEND"] < POLICY.min_remaining_r                  # persisted, never a READY
    # Same lateness while the host WAS watching (heartbeat after the trigger close): plain STALE.
    watched = act.assess(o, send_ts=send, bid=bid, ask=bid + 0.27, policy=POLICY,
                         last_heartbeat_ts=t("2026-10-07T04:28:00"))
    assert (watched["state"], watched["outcome"]) == (act.STALE, act.INFO_ONLY_STALE)


def test_expired_opportunity_is_never_sent():
    o = opp("SHORT", "2026-10-06T20:50:00", 150.0, 150.2, 149.9, "2026-10-06T21:00:00")
    a = act.assess(o, send_ts=t("2026-10-06T21:00:00"), bid=150.0, ask=150.01, policy=POLICY,
                   last_heartbeat_ts=t("2026-10-06T20:58:00"))
    assert (a["state"], a["outcome"]) == (act.EXPIRED, act.EXPIRED) and a["outcome"] not in act.SENT_OUTCOMES


# ------------------------------------------------------------------------------- D4 pending bar

def test_unclosed_trigger_bar_is_pending_not_stale_then_reassessed():
    o = opp("LONG", "2026-10-06T10:00:00", 1.1000, 1.0990, 1.1030, "2026-10-06T12:00:00")
    hb = t("2026-10-06T09:58:00")
    pending = act.assess(o, send_ts=t("2026-10-06T10:01:00"), bid=1.0999, ask=1.1, policy=POLICY, last_heartbeat_ts=hb)
    assert (pending["state"], pending["outcome"]) == (act.PENDING_BAR_CLOSE, None)
    closed = act.assess(o, send_ts=t("2026-10-06T10:06:00"), bid=1.0999, ask=1.1, policy=POLICY, last_heartbeat_ts=hb)
    assert (closed["state"], closed["outcome"]) == (act.FRESH, act.WATCH_READY)


def test_fx_0701_unclosed_signal_bar_is_pending_bar_close_then_ready_at_0716(monkeypatch):
    """2026-10-07 07:01 EURUSD ASIAN_LONDON: engine SIGNAL (box-based entry_1, no signal_timestamp),
    first trade-session bar 07:00-07:15 not closed. Previously STALE/STALE_SIGNAL; D4 makes it
    PENDING_BAR_CLOSE, and the 07:16 run (bar closed) is READY with the same levels."""
    sig = types.SimpleNamespace(status="SIGNAL", reason_code="BOX_DIRECTION_V1", regime="RANGE", setup="entry_1",
                                signal_id="s1", box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                signal_timestamp=None, direction="LONG", entry=1.1665, stop_loss=1.16515,
                                risk_distance=0.00135)
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: sig)
    day = dt.date(2026, 10, 7)
    bar = Candle(t("2026-10-07T07:00:00"), 1.1665, 1.1670, 1.1660, 1.1666)

    def build(at, post):
        return fx_tickets.build_fx_ticket("EURUSD", "ASIAN_LONDON", day, [], 2, post, data_source="FIXTURE",
                                          evaluated_at=at, data_close=at, spread=0.00015)

    at0701 = build(t("2026-10-07T07:01:05"), [])
    assert (at0701["decision"], at0701["reason_code"], at0701["suppressed_decision"]) == (
        "PENDING_BAR_CLOSE", "SIGNAL_BAR_NOT_CLOSED", "READY")
    assert at0701["pending_bar_close_utc"] == "2026-10-07T07:15:00+00:00"
    state, stage, reason = classify_fx_ticket(at0701, now=t("2026-10-07T07:01:05"), window_end=t("2026-10-07T10:00:00"))
    assert (state, stage, reason) == (WATCH, "TICKET", "PENDING_BAR_CLOSE:SIGNAL_BAR_NOT_CLOSED")
    assert fx_tickets._STATE[at0701["decision"]] == fx_tickets.CYCLE_STATE_NO_TRADE
    at0716 = build(t("2026-10-07T07:16:08"), [bar])
    assert at0716["decision"] == "READY" and at0716["signal_close_utc"] == "2026-10-07T07:15:00+00:00"
    assert (at0716["entry"], at0716["stop_loss"]) == (at0701["entry"], at0701["stop_loss"])
    at0731 = build(t("2026-10-07T07:31:00"), [bar])                  # unchanged: past freshness -> STALE
    assert (at0731["decision"], at0731["reason_code"]) == ("STALE", "STALE_SIGNAL")


# ------------------------------------------------------------------------------- runner integration

POI = "GBPUSD:H1:FVG:LONG:2026-10-06T11:00:00+00:00"


def _gbp_opp(choch: str = "2026-10-06T17:40:00+00:00", expires: str = "2026-10-06T21:00:00+00:00") -> dict:
    return {"opp_id": f"{POI}|2026-10-06T17:20:00+00:00|{choch}", "poi_id": POI, "direction": "LONG",
            "sweep_time": "2026-10-06T17:20:00+00:00", "sweep_extreme": 1.3247, "choch_time": choch,
            "entry_reference": 1.3260, "target_c11": 1.32847, "expires_at": expires}


def _snap(at: str, state: str = "OPPORTUNITY", o: dict = None) -> Snapshot:
    return Snapshot(symbol="GBPUSD", evaluated_at=at, state=state, bias="LONG",
                    poi={"poi_id": POI, "direction": "LONG", "low": 1.3240, "high": 1.3250},
                    opportunity=(o or _gbp_opp()) if state == "OPPORTUNITY" else None)


@pytest.fixture
def host(tmp_path, monkeypatch):
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    monkeypatch.setattr(smoke, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(smoke, "POLICY_ROOT", str(ROOT))
    sent = []
    monkeypatch.setattr(tg, "send_message", sent.append)
    j = tmp_path / "journal"
    tracker = WatchTracker(str(j / "large_smc_watch" / "state.json"), str(j / "ticket_delivery" / "archive"))
    ledger = AlertLedger(str(j / "large_smc_watch" / "delivered_confirmations.json"))
    return types.SimpleNamespace(j=j, sent=sent, tracker=tracker, ledger=ledger)


def _run(h, snap: Snapshot, quote=(1.3259, 1.3260)) -> list:
    """One watch run: tracker poll -> actionability gate -> delivery, then digest + heartbeat."""
    now = dt.datetime.fromisoformat(snap.evaluated_at)
    lines: list = []
    gate = smoke._actionability_gate(now, str(h.j), lines)
    for e in h.tracker.poll(snap):
        if e.to_state == "OPPORTUNITY":
            lines += smoke._deliver_opportunity(e.__dict__, gate, h.ledger, lambda: quote, 1.3259)
    return lines + smoke._finish_actionability(gate, h.ledger)


def _records(h) -> list:
    out = []
    for p in sorted((h.j / "large_smc_watch" / "actionability").glob("*.jsonl")):
        out += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    return out


def test_gbpusd_duplicate_after_suspend_resume_is_sent_once(host):
    """GBPUSD 2026-10-06: sent 17:48:10; PC slept, 18:34 STALE (SUSPENDED); 18:38 the identical
    confirmation re-entered OPPORTUNITY and was sent again. Now: one send, re-entry suppressed."""
    _run(host, _snap("2026-10-06T17:43:00+00:00", state="IDLE"))                # host watching
    first = _run(host, _snap("2026-10-06T17:48:00+00:00"))
    assert len(host.sent) == 1 and any("outcome=WATCH_READY" in ln or "outcome=INFO_ONLY" in ln for ln in first)
    _run(host, Snapshot(symbol="GBPUSD", evaluated_at="2026-10-06T18:34:00+00:00", state="STALE"))
    again = _run(host, _snap("2026-10-06T18:38:00+00:00"))
    assert len(host.sent) == 1
    assert any("ALERT_SUPPRESSED_DUPLICATE_CONFIRMATION" in ln for ln in again)
    assert not any("MISSED_NOT_ACTIONABLE_DIGEST" in ln for ln in again)        # already delivered: no digest


def test_reboot_during_session_sends_one_digest_and_no_catch_up_ready(host):
    """Heartbeat 17:30; host down 17:30 -> 18:30 (reboot). The 17:40 CHoCH (closed 17:45) was missed:
    it is digested once as MISSED - NOT ACTIONABLE, never sent as an individual READY. A restart
    that re-surfaces the same confirmation does not send the digest again."""
    _run(host, _snap("2026-10-06T17:30:00+00:00", state="IDLE"))
    after_boot = _run(host, _snap("2026-10-06T18:30:00+00:00"))
    assert len(host.sent) == 1 and host.sent[0].startswith("LARGE-SMC MISSED - NOT ACTIONABLE")
    assert "GBPUSD LONG" in host.sent[0] and any("MISSED_NOT_ACTIONABLE_DIGEST" in ln for ln in after_boot)
    rec = _records(host)[-1]
    assert (rec["state"], rec["outcome"]) == (act.MISSED_DOWNTIME, act.MISSED_NOT_ACTIONABLE)
    for key in ("reference_price", "send_price", "send_price_side", "trigger_bar_close_ts", "send_ts",
                "R_AT_TRIGGER", "R_AT_SEND", "policy_version", "confirmation_key"):
        assert key in rec
    # second reboot: suspended, then the same confirmation re-enters -> no repeat digest, no READY
    _run(host, Snapshot(symbol="GBPUSD", evaluated_at="2026-10-06T18:35:00+00:00", state="STALE"))
    _run(host, _snap("2026-10-06T19:40:00+00:00"))
    assert len(host.sent) == 1


def test_fresh_opportunity_after_reboot_is_delivered_normally(host):
    _run(host, _snap("2026-10-06T17:30:00+00:00", state="IDLE"))
    o = _gbp_opp(choch="2026-10-06T18:25:00+00:00")                            # closed 18:30, after the reboot
    lines = _run(host, _snap("2026-10-06T18:33:00+00:00", o=o))
    assert len(host.sent) == 1 and host.sent[0].startswith("LARGE-SMC ALERT")
    assert "ACTIONABILITY:" in host.sent[0] and "R_AT_SEND:" in host.sent[0]
    assert any("state=FRESH" in ln for ln in lines)


def test_pending_bar_close_is_held_and_reassessed_on_the_next_run(host):
    _run(host, _snap("2026-10-06T17:30:00+00:00", state="IDLE"))
    o = _gbp_opp(choch="2026-10-06T17:40:00+00:00")                            # closes 17:45
    held = _run(host, _snap("2026-10-06T17:43:00+00:00", o=o))                 # defensive: clock before close
    assert host.sent == [] and any("state=PENDING_BAR_CLOSE" in ln for ln in held)
    later = _run(host, _snap("2026-10-06T17:48:00+00:00", o=o))                # no new transition; held one re-run
    assert len(host.sent) == 1 and any("state=FRESH" in ln for ln in later)
    assert json.loads((host.j / "large_smc_watch" / "pending_bar_close.json").read_text() or "{}") == {}
