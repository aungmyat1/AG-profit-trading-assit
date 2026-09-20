from datetime import datetime, timedelta, timezone

from historical_replay import HistoricalCandleStore
from strategy_engine.session import Candle
from session_sweep_continuation.replay import ReplayResult
from svos.virtual_demo_runner import VirtualDemoRunIdentity, VirtualDemoRunner
from svos.virtual_time import VirtualClock, VirtualMarketFeed

UTC = timezone.utc; T0 = datetime(2026, 1, 1, tzinfo=UTC)


def feed():
    s = HistoricalCandleStore(); bars = [Candle(T0 + timedelta(minutes=i), 1.1, 1.101, 1.099, 1.1005, 1) for i in range(20)]
    s.load_series("EURUSD", "M1", bars, dataset_id="DS1", source="FIXTURE")
    return VirtualMarketFeed(s, "EURUSD", ("M1",), VirtualClock(T0, T0 + timedelta(minutes=19)))


def no_setup():
    return ReplayResult("EURUSD", "ASIAN_LONDON", T0.date(), "RANGE", None, [], [], [])


def test_run_identity_and_no_setup_audit_without_order():
    f = feed(); i = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=T0 + timedelta(minutes=19))
    r = VirtualDemoRunner(feed=f, identity=i, decisions={"__DEFAULT__": no_setup()}, dataset_id="DS1")
    r.run(); assert r.funnel.no_setup > 0 and r.funnel.virtual_orders == 0 and r.funnel.market_events == 19


def test_speed_and_repeated_runs_have_same_terminal_semantics():
    def run(mode):
        f = feed(); i = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=T0 + timedelta(minutes=19))
        r = VirtualDemoRunner(feed=f, identity=i, decisions={}, dataset_id="DS1").run(mode=mode)
        return i.fingerprint, r.ledger.terminal_hash, r.funnel, r.checkpoint()
    assert run("step") == run("maximum")


def test_checkpoint_is_deterministic():
    f = feed(); i = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=T0 + timedelta(minutes=19))
    r = VirtualDemoRunner(feed=f, identity=i, decisions={}, dataset_id="DS1"); r.run(stop_after_events=3)
    assert r.checkpoint() == r.checkpoint()
