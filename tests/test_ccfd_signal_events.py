"""AGP-LANE-B3 (owner ruling 2026-10-11, item 1): append-only signal event log (EMIT / WITHDRAWN / EXPIRE /
REISSUE) and the L3 event-log prefix-invariance check of the ST_CRYPTO_CFD_SWEEP_RETEST_V1 replay."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ccfd_sweep_retest_replay as R  # noqa: E402

UTC = dt.timezone.utc
D0 = dt.datetime(2026, 9, 9, tzinfo=UTC)


def at(h, m=0):
    return D0 + dt.timedelta(hours=h, minutes=m)


def entry(retest: dt.datetime, direction="SHORT", entry_price=100.0):
    return {"result": "ENTRY_VALID", "sweep": {"candle_time_utc": (retest - 3 * R.M5).isoformat()},
            "mss": {"confirmed_at_utc": (retest - R.M5).isoformat()},
            "retest": {"candle_time_utc": retest.isoformat()},
            "target_plan": {"direction": direction, "entry": entry_price}}


def wait(result="WAITING_SWEEP"):
    return {"result": result, "sweep": None, "mss": None, "retest": None, "target_plan": None}


def stream_between(start, end, sem):
    t, out = start, []
    while t < end:
        out.append((t, sem))
        t += R.M5
    return out


def eth_0909_like():
    """ENTRY_VALID from the 10:55 retest at 11:00, withdrawn at 13:00 (H1 flip), reinstated at 20:00."""
    sig = entry(at(10, 55))
    return (stream_between(at(10), at(11), wait()) + stream_between(at(11), at(13), sig)
            + stream_between(at(13), at(20), wait()) + stream_between(at(20), at(21), sig))


def test_stale_reissue_is_expired_and_events_are_append_only():
    ev = R.signal_events(eth_0909_like())
    assert [(e["type"], e["bar_close_utc"][11:16], e.get("freshness")) for e in ev] == [
        ("EMIT", "11:00", "FRESH"), ("EXPIRE", "11:20", None), ("REISSUE", "20:00", "EXPIRED")]
    assert ev[1]["reason"] == "SIGNAL_STALE"
    assert all(e["retest_candle_time_utc"] == at(10, 55).isoformat() for e in ev)
    assert len({e["signal_id"] for e in ev}) == 1 and [e["seq"] for e in ev] == [0, 1, 2]


def test_withdraw_inside_the_expiry_window_then_fresh_reissue():
    sig = entry(at(10, 55))
    s = [(at(11), sig), (at(11, 5), wait("NO_TRADE_DIRECTION")), (at(11, 10), sig), (at(11, 15), sig),
         (at(11, 20), sig), (at(11, 25), sig)]
    ev = R.signal_events(s)
    assert [(e["type"], e["bar_close_utc"][11:16], e["reason"], e.get("freshness")) for e in ev] == [
        ("EMIT", "11:00", "ENTRY_VALID", "FRESH"), ("WITHDRAWN", "11:05", "NO_TRADE_DIRECTION", None),
        ("REISSUE", "11:10", "ENTRY_VALID", "FRESH"), ("EXPIRE", "11:20", "SIGNAL_STALE", None)]


def test_superseded_signal_and_utc_day_rotation():
    a, b = entry(at(23, 50)), entry(at(23, 50), entry_price=101.0)
    s = [(at(23, 55), a), (at(24, 0), b)]
    ev = R.signal_events(s)
    assert [(e["type"], e["reason"]) for e in ev] == [("EMIT", "ENTRY_VALID"), ("EXPIRE", "UTC_DAY_ROTATION"),
                                                     ("EMIT", "ENTRY_VALID")]
    s2 = [(at(10, 0), entry(at(9, 55))), (at(10, 5), entry(at(9, 55), entry_price=99.0))]
    ev2 = R.signal_events(s2)
    assert [e["type"] for e in ev2] == ["EMIT", "WITHDRAWN", "EMIT"] and ev2[1]["reason"] == "SUPERSEDED"


def test_event_log_invariance_passes_for_a_causal_stream():
    s = eth_0909_like()
    out = R.event_log_invariance(s, list(s))
    assert out["verdict"] == "PASS" and out["event_log_mismatches"] == 0
    assert out["reissues"] == {"total": 1, "fresh": 0, "expired": 1}
    assert out["events_by_type"] == {"EMIT": 1, "EXPIRE": 1, "REISSUE": 1}


def test_event_log_invariance_flags_a_scan_that_changes_when_later_bars_are_added():
    s = eth_0909_like()
    leaked = [(t, entry(at(10, 55), entry_price=99.0) if t == at(11) else sem) for t, sem in s]
    out = R.event_log_invariance(s, leaked)
    assert out["verdict"] == "FAIL" and out["event_log_mismatches"] > 0
    assert any(k.startswith("FUTURE_BARS:") for k in out["mismatches_by_type"])


def test_event_log_duplicate_retry_is_idempotent_and_restart_replays_state():
    from research_external.oracles.crypto_signal_ledger import SignalEventLedger
    ledger = SignalEventLedger()
    first = ledger.append("EMIT", at(11), "signal-1", "ENTRY_VALID", freshness="FRESH")
    assert ledger.append("EMIT", at(11), "signal-1", "ENTRY_VALID", freshness="FRESH") == first
    assert len(ledger.snapshot()) == 1
    restarted = SignalEventLedger.replay(ledger.snapshot())
    assert restarted.state("signal-1") == "ACTIVE"
    restarted.append("WITHDRAWN", at(11, 5), "signal-1", "NO_TRADE_DIRECTION")
    assert [e["type"] for e in restarted.snapshot()] == ["EMIT", "WITHDRAWN"]


def test_event_log_rejects_out_of_order_events():
    from research_external.oracles.crypto_signal_ledger import EventOrderError, SignalEventLedger
    ledger = SignalEventLedger()
    ledger.append("EMIT", at(11), "signal-1", "ENTRY_VALID", freshness="FRESH")
    with pytest.raises(EventOrderError, match="out-of-order"):
        ledger.append("WITHDRAWN", at(10, 59), "signal-1", "NO_TRADE_DIRECTION")
    with pytest.raises(ValueError, match="out-of-order scan"):
        R.signal_events([(at(11), entry(at(10, 55))), (at(10, 59), wait())])


def test_fill_then_invalidate_never_appends_withdrawn():
    sig = entry(at(10, 55))
    stream = [(at(11), sig), (at(11, 5), wait("NO_TRADE_DIRECTION"))]
    events = R.signal_events(stream, fill_events=[(at(11, 2), sig)])
    assert [e["type"] for e in events] == ["EMIT", "FILL"]
    assert events[-1]["bar_close_utc"] == at(11, 2).isoformat()


def test_duplicate_scan_retry_is_idempotent_and_conflicting_duplicate_rejected():
    sig = entry(at(10, 55))
    assert R.signal_events([(at(11), sig), (at(11), sig)]) == R.signal_events([(at(11), sig)])
    with pytest.raises(ValueError, match="conflicting duplicate scan"):
        R.signal_events([(at(11), sig), (at(11), entry(at(10, 55), entry_price=99.0))])


def test_filled_signal_cannot_be_withdrawn_during_ledger_replay():
    from research_external.oracles.crypto_signal_ledger import EventOrderError, SignalEventLedger
    ledger = SignalEventLedger()
    ledger.append("EMIT", at(11), "signal-1", "ENTRY_VALID", freshness="FRESH")
    ledger.append("FILL", at(11, 2), "signal-1", "FILL_RECORDED")
    with pytest.raises(EventOrderError, match="filled signal cannot be withdrawn"):
        SignalEventLedger.replay(ledger.snapshot() + [{
            "seq": 2, "event_id": "bad-event", "type": "WITHDRAWN",
            "bar_close_utc": at(11, 5).isoformat(), "signal_id": "signal-1", "reason": "INVALIDATED",
        }])
