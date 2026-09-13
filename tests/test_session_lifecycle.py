from datetime import datetime, timedelta, timezone

import pytest

from research.session_lifecycle import apply_time_stop, control_reconcile, lifecycle_record

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def accepted():
    return {"direction":"LONG", "entry_time":T0.isoformat(), "entry_price":100.0, "stop_price":99.0,
            "outcome":{"event_sequence":[
                {"time":(T0+timedelta(minutes=20)).isoformat(),"event":"PARTIAL_TARGET","exit_price":101.0,"gross_R_delta":.5,"quantity_before":1.0,"quantity_after":.5},
                {"time":(T0+timedelta(minutes=100)).isoformat(),"event":"RUNNER_TARGET_HIT","exit_price":103.0,"gross_R_delta":1.5,"quantity_before":.5,"quantity_after":0.0}],
                "gross_R":2.0,"spread_cost_R":.1,"commission_cost_R":.05,"slippage_cost_R":.05,
                "net_R":1.8,"terminal_state":"RESOLVED_PARTIAL_RUNNER_TARGET"}}


def test_control_and_volume_reconcile():
    r=lifecycle_record(accepted(),trade_id="T1",strategy_id="S",strategy_version="1",symbol="EURUSD")
    c=control_reconcile([r])
    assert c["trade_count"] == 1 and c["gross_R"] == 2 and c["friction_R"] == pytest.approx(.2)
    assert c["net_R"] == pytest.approx(1.8) and c["volume_invariants"]
    assert [e["time"] for e in r["events"]] == sorted(e["time"] for e in r["events"])


def test_time_stop_keeps_partial_and_closes_only_runner():
    r=lifecycle_record(accepted(),trade_id="T1",strategy_id="S",strategy_version="1",symbol="EURUSD")
    stopped=apply_time_stop(r,cutoff=T0+timedelta(minutes=30),exit_price=102.0)
    assert [e["event"] for e in stopped["events"]] == ["ENTRY","PARTIAL_TARGET","TIME_STOP"]
    assert stopped["events"][-1]["quantity_before"] == .5
    assert stopped["gross_R"] == pytest.approx(1.5) and stopped["net_R"] == pytest.approx(1.3)
    assert apply_time_stop(r,cutoff=T0+timedelta(minutes=120),exit_price=0) is r
