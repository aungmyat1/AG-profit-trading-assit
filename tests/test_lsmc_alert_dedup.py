"""Large-SMC delivery exactly-once (audit 2026-10-07, LSMC-DUP). Detection/transitions unchanged."""
from __future__ import annotations

import datetime as dt

from host_delivery.lsmc_alert_dedup import (
    AlertLedger, DELIVERY_UNCERTAIN, DUPLICATE_UNCERTAIN, PENDING, confirmation_key, deliver_once,
)
from large_smc_watch.watch import Snapshot, WatchTracker

UTC = dt.timezone.utc
POI = "GBPUSD:H1:FVG:LONG:2026-10-06T11:00:00+00:00"
CHOCH = "2026-10-06T17:40:00+00:00"


def _opp(sweep: str = "2026-10-06T17:20:00+00:00", target: float = 1.32847, extreme: float = 1.3247,
         choch: str = CHOCH) -> dict:
    return {"opp_id": f"{POI}|{sweep}|{choch}", "poi_id": POI, "direction": "LONG", "sweep_time": sweep,
            "sweep_extreme": extreme, "choch_time": choch, "target_c11": target,
            "expires_at": "2026-10-06T21:00:00+00:00"}


def _snap(at: str, state: str = "OPPORTUNITY", opp: dict = None) -> Snapshot:
    opp = _opp() if opp is None and state == "OPPORTUNITY" else opp
    return Snapshot(symbol="GBPUSD", evaluated_at=at, state=state, bias="LONG",
                    poi={"poi_id": POI, "direction": "LONG", "low": 1.3240, "high": 1.3250}, opportunity=opp)


def _deliver(events, ledger, sent):
    out = []
    for e in events:
        out.append(deliver_once(e.__dict__, ledger, lambda e=e: sent.append(e.reference_id) or "SENT"))
    return out


def test_identical_ref_reentered_after_stale_is_transitioned_but_sent_once(tmp_path):
    tracker = WatchTracker(str(tmp_path / "state.json"), str(tmp_path / "archive"))
    ledger, sent = AlertLedger(str(tmp_path / "ledger.json")), []
    first = tracker.poll(_snap("2026-10-06T17:48:00+00:00"))
    assert tracker.poll(_snap("2026-10-06T18:34:00+00:00", state="STALE")) == []
    second = tracker.poll(_snap("2026-10-06T18:38:00+00:00"))
    # detection/transition layer unchanged: the re-entry is still a transition (and archived)
    assert [e.to_state for e in first] == ["OPPORTUNITY"] and [e.to_state for e in second] == ["OPPORTUNITY"]
    assert first[0].reference_id == second[0].reference_id
    assert _deliver(first, ledger, sent) == ["SENT"]
    assert _deliver(second, ledger, sent) == ["SUPPRESSED_DUPLICATE_CONFIRMATION"]
    assert len(sent) == 1


def test_restart_between_evaluations_does_not_resend(tmp_path):
    sent = []
    first = WatchTracker(str(tmp_path / "s.json"), str(tmp_path / "a")).poll(_snap("2026-10-06T17:48:00+00:00"))
    _deliver(first, AlertLedger(str(tmp_path / "ledger.json")), sent)
    # new process: fresh tracker state (lost) and a fresh ledger object over the same file
    again = WatchTracker(str(tmp_path / "s2.json"), str(tmp_path / "a2")).poll(_snap("2026-10-06T18:38:00+00:00"))
    assert [e.to_state for e in again] == ["OPPORTUNITY"]
    assert _deliver(again, AlertLedger(str(tmp_path / "ledger.json")), sent) == ["SUPPRESSED_DUPLICATE_CONFIRMATION"]
    assert len(sent) == 1


def test_parameter_only_change_under_same_confirmation_is_not_resent(tmp_path):
    """BTC 2026-10-06 shape: same POI + CHoCH, sweep anchor / invalidation / target changed -> new ref."""
    tracker = WatchTracker(str(tmp_path / "state.json"), str(tmp_path / "archive"))
    ledger, sent = AlertLedger(str(tmp_path / "ledger.json")), []
    a = tracker.poll(_snap("2026-10-06T17:58:00+00:00"))
    b = tracker.poll(_snap("2026-10-06T18:53:00+00:00", opp=_opp(sweep="2026-10-06T17:05:00+00:00",
                                                                 target=1.32798, extreme=1.3241)))
    assert a[-1].reference_id != b[-1].reference_id                    # new identity at detection level
    assert confirmation_key(a[-1].__dict__) == confirmation_key(b[-1].__dict__)
    _deliver(a, ledger, sent)
    assert _deliver(b, ledger, sent)[-1] == "SUPPRESSED_DUPLICATE_CONFIRMATION"
    assert len(sent) == 1


def test_new_choch_is_a_new_confirmation_and_failed_send_is_not_recorded(tmp_path):
    ledger = AlertLedger(str(tmp_path / "ledger.json"))
    e1 = {"to_state": "OPPORTUNITY", "symbol": "GBPUSD", "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0",
          "payload": {"opportunity": _opp()}}
    e2 = {**e1, "payload": {"opportunity": _opp(choch="2026-10-06T19:00:00+00:00")}}
    assert deliver_once(e1, ledger, lambda: "FAILED") == "FAILED"
    assert deliver_once(e1, ledger, lambda: "SENT") == "SENT"          # known rejection may be retried
    assert deliver_once(e2, ledger, lambda: "SENT") == "SENT"
    assert deliver_once({**e1, "to_state": "NEAR_POI"}, ledger, lambda: "NOT_SENT_POLICY") == "NOT_SENT_POLICY"
    assert deliver_once(e1, None, lambda: "SENT") == "SENT"            # no ledger -> legacy behaviour


def test_ambiguous_outcome_and_restart_left_pending_claim_never_resend(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger = AlertLedger(path)
    event = {"to_state": "OPPORTUNITY", "symbol": "GBPUSD", "strategy_id": "ST_LARGE_SMC_V1",
             "strategy_version": "1.1.0", "reference_id": "ref-1", "transition_id": "transition-1",
             "evaluated_at": "2026-10-06T17:48:00+00:00", "payload": {"opportunity": _opp()}}
    calls = []
    assert deliver_once(event, ledger, lambda: calls.append("request") or "DELIVERY_UNCERTAIN") == "DELIVERY_UNCERTAIN"
    assert deliver_once(event, AlertLedger(path), lambda: calls.append("retry") or "SENT") == DUPLICATE_UNCERTAIN
    assert calls == ["request"]
    assert len(AlertLedger(path).list_uncertain()) == 1

    key = confirmation_key(event)
    ledger.store.put(key, {"state": PENDING, "reference_id": "ref-pending"})
    assert deliver_once(event, AlertLedger(path), lambda: calls.append("crash-retry") or "SENT") == DELIVERY_UNCERTAIN
    assert calls == ["request"]
    recovered = AlertLedger(path).list_uncertain()
    assert {row["identity"] for row in recovered} == {key}


def test_opportunity_without_stable_confirmation_identity_fails_closed(tmp_path):
    event = {"to_state": "OPPORTUNITY", "symbol": "GBPUSD", "strategy_id": "ST_LARGE_SMC_V1",
             "strategy_version": "1.1.0", "payload": {"opportunity": {"direction": "LONG"}}}
    calls = []
    assert deliver_once(event, AlertLedger(str(tmp_path / "ledger.json")),
                        lambda: calls.append("request") or "SENT") == "IDENTITY_UNAVAILABLE"
    assert calls == []
