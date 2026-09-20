from datetime import datetime, timedelta, timezone
import json
import hashlib
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from session_sweep_continuation.campaign import Campaign

from historical_replay import HistoricalCandleStore
from historical_replay.symbol_metadata_manifest import HistoricalSymbolMetadataManifest
from strategy_engine.session import Candle
from session_sweep_continuation.replay import ReplayResult
from svos.virtual_demo_runner import RunnerError, VirtualDemoRunIdentity, VirtualDemoRunner
from svos.virtual_time import VirtualClock, VirtualMarketFeed
from svos.ssc_bridge import SSCToVirtualOrderBridge
from svos.virtual_exchange import OHLCM1, VirtualExchange

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


def test_capacity_mode_rejects_caller_strategy_authority():
    identity = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=T0 + timedelta(minutes=19))
    with pytest.raises(RunnerError, match="CAPACITY_REJECTS_CALLER"):
        VirtualDemoRunner(feed=feed(), identity=identity, decisions={"__DEFAULT__": no_setup()},
                          dataset_id="DS1", capacity_mode=True)
    with pytest.raises(RunnerError, match="CAPACITY_REJECTS_CALLER"):
        VirtualDemoRunner(feed=feed(), identity=identity, decisions={}, dataset_id="DS1",
                          decision_source=lambda _: no_setup(), capacity_mode=True)
    with pytest.raises(RunnerError, match="CAPACITY_CANONICAL_INPUTS_UNAVAILABLE"):
        VirtualDemoRunner(feed=feed(), identity=identity, decisions={}, dataset_id="DS1",
                          capacity_mode=True)


def actionable():
    campaign = Campaign("C", "ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.1",
                        "EURUSD", "ASIAN_LONDON", T0.date(), "LONG", "RANGE")
    setup = {"setup_model": "S1", "direction": "LONG",
             "entry_time": str(T0 - timedelta(minutes=14)), "entry_price": 1.1,
             "stop_price": 1.098, "risk_pct": 0.4,
             "outcome": {"partial_target_price": 1.102}}
    return ReplayResult("EURUSD", "ASIAN_LONDON", T0.date(), "RANGE", campaign, [setup], [], [])


def test_runner_fills_only_on_later_event_then_updates_account_and_ledger():
    identity = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=T0 + timedelta(minutes=19))
    runner = VirtualDemoRunner(feed=feed(), identity=identity,
                               decisions={"__DEFAULT__": actionable()}, dataset_id="DS1")
    runner.run(stop_after_events=1)
    assert runner.funnel.virtual_orders == 1
    assert runner.funnel.virtual_fills == 0
    runner.run(stop_after_events=3)
    assert runner.funnel.virtual_fills == 1
    assert len(runner.account.open_positions) == 1
    assert any(e.event_type == "VirtualFill" for e in runner.ledger.events)
    runner.run()
    assert runner.funnel.unresolved_outcomes == 1
    assert any(e.event_type == "VirtualUnresolved" for e in runner.ledger.events)
    assert runner.ledger.replay_account().latest_snapshot == runner.account.latest_snapshot


@pytest.mark.parametrize("cursor", [1, 3])
def test_checkpoint_replay_restores_pending_or_open_position_and_terminal_identity(cursor):
    identity = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=T0 + timedelta(minutes=19))
    inputs = dict(identity=identity, decisions={"__DEFAULT__": actionable()}, dataset_id="DS1")
    continuous = VirtualDemoRunner(feed=feed(), **inputs).run()
    interrupted = VirtualDemoRunner(feed=feed(), **inputs).run(stop_after_events=cursor)
    saved = json.loads(json.dumps(interrupted.checkpoint()))
    restored = VirtualDemoRunner.restore_from_checkpoint(saved, feed=feed(), **inputs)
    assert restored.checkpoint() == saved
    restored.run()
    assert restored.checkpoint() == continuous.checkpoint()
    assert restored.ledger.terminal_hash == continuous.ledger.terminal_hash


def test_capacity_calls_fixed_canonical_entrypoint_with_closed_context(tmp_path):
    store = HistoricalCandleStore()
    for tf, step, count in (("H1", 60, 9), ("M15", 15, 33), ("M1", 1, 440)):
        bars = [Candle(T0 + timedelta(minutes=i * step), 1.1, 1.101, 1.099, 1.1005, 1)
                for i in range(count)]
        store.load_series("EURUSD", tf, bars, dataset_id="DS1", source="FIXTURE")
    start = T0 + timedelta(hours=7)
    end = start + timedelta(minutes=15)
    identity = VirtualDemoRunIdentity.create(dataset_id="DS1", start=start, end=end)
    h1_path = tmp_path / "H1.csv"
    h1_path.write_bytes(b"engineering fixture")
    file_hash = "sha256:" + hashlib.sha256(h1_path.read_bytes()).hexdigest()
    manifest = HistoricalSymbolMetadataManifest("DS1", "EURUSD", .00001,
        "HISTORICAL_ANALYSIS_ONLY", "OWNER_APPROVED_DATASET_MANIFEST", "2026-09-20", file_hash, str(h1_path))
    runner = VirtualDemoRunner(
        feed=VirtualMarketFeed(store, "EURUSD", ("H1", "M15", "M1"), VirtualClock(start, end)),
        identity=identity, decisions={}, dataset_id="DS1", capacity_mode=True,
        capacity_manifest=manifest, capacity_h1_dataset_path=str(h1_path), capacity_session_pair="ASIAN_LONDON",
        capacity_pip_size=.0001, capacity_pip_value_per_lot=10.0)
    with patch("svos.virtual_demo_runner.run_canonical_shadow_cycle",
               return_value=SimpleNamespace(replay_result=no_setup())) as canonical:
        runner.run()
    assert canonical.call_count == 2
    assert canonical.call_args.kwargs["m15_candles"][-1].time + timedelta(minutes=15) <= end
    assert runner.funnel.ssc_evaluations == 2
    assert any(e.event_type == "CanonicalDecision" and
               e.payload["strategy_contract_hash"] == runner.capacity_contract_hash
               for e in runner.ledger.events)
    unavailable = VirtualDemoRunner(
        feed=VirtualMarketFeed(store, "EURUSD", ("H1", "M15", "M1"), VirtualClock(start, end)),
        identity=identity, decisions={}, dataset_id="DS1", capacity_mode=True,
        capacity_manifest=manifest, capacity_h1_dataset_path=str(h1_path), capacity_session_pair="ASIAN_LONDON",
        capacity_pip_size=.0001, capacity_pip_value_per_lot=10.0)
    with patch("svos.virtual_demo_runner.run_canonical_shadow_cycle", side_effect=ValueError("no evidence")):
        unavailable.run()
    assert unavailable.funnel.virtual_orders == 0
    assert any(e.event_type == "CanonicalUnavailable" for e in unavailable.ledger.events)


@pytest.mark.parametrize("high,low,expected", [
    (1.103, 1.100, "FAVORABLE"),
    (1.101, 1.097, "ADVERSE"),
    (1.103, 1.097, "AMBIGUOUS_SEQUENCE"),
])
def test_exchange_stream_preserves_later_exit_and_ambiguity(high, low, expected):
    intent = SSCToVirtualOrderBridge().build(actionable(), dataset_id="DS1",
        decision_event_id="E1").intents[0]
    exchange = VirtualExchange()
    exchange.submit(intent.proposal)
    cutoff = intent.proposal.decision_cutoff
    same = OHLCM1("SAME", "DS1", "EURUSD", cutoff, 1.1, 1.103, 1.097, 1.1)
    assert exchange.advance(same).fill is None
    fill = OHLCM1("FILL", "DS1", "EURUSD", cutoff + timedelta(minutes=1), 1.1, 1.101, 1.099, 1.1)
    assert exchange.advance(fill).fill is not None
    assert exchange.order.exit is None
    exit_bar = OHLCM1("EXIT", "DS1", "EURUSD", cutoff + timedelta(minutes=2), 1.1, high, low, 1.1)
    assert exchange.advance(exit_bar).exit.observation_kind == expected


def test_pending_order_is_explicitly_expired_at_end_of_data():
    intent = SSCToVirtualOrderBridge().build(actionable(), dataset_id="DS1",
        decision_event_id="E1").intents[0]
    exchange = VirtualExchange()
    exchange.submit(intent.proposal)
    order = exchange.end_of_data(at=intent.proposal.decision_cutoff,
                                 event_id="END_OF_DATA:DS1")
    assert order.fill is None
    assert order.records[-1].reason == "END_OF_DATA_PENDING"


def test_runner_terminal_exit_reconciles_account_and_ledger():
    store = HistoricalCandleStore()
    bars = [Candle(T0 + timedelta(minutes=i), 1.1,
                   1.103 if i == 4 else 1.101, 1.099, 1.1005, 1)
            for i in range(8)]
    store.load_series("EURUSD", "M1", bars, dataset_id="DS1", source="FIXTURE")
    end = T0 + timedelta(minutes=7)
    first = VirtualMarketFeed(store, "EURUSD", ("M1",), VirtualClock(T0, end)).step()[0]
    identity = VirtualDemoRunIdentity.create(dataset_id="DS1", start=T0, end=end)
    runner = VirtualDemoRunner(
        feed=VirtualMarketFeed(store, "EURUSD", ("M1",), VirtualClock(T0, end)),
        identity=identity, decisions={first.replay_event_id: actionable()}, dataset_id="DS1").run()
    assert runner.funnel.virtual_fills == runner.funnel.closed_outcomes == 1
    assert not runner.account.open_positions
    assert runner.ledger.replay_account().latest_snapshot == runner.account.latest_snapshot
