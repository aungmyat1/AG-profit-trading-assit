import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from historical_replay import HistoricalCandleStore
from strategy_contract.replay_bridge import ReplayBridgeError, build_replay_market_snapshot
from strategy_engine.session import Candle

UTC = timezone.utc
START = datetime(2026, 9, 18, tzinfo=UTC)


def fixture_data():
    return [Candle(time=START + timedelta(minutes=15*i), open=1.1+i*.0001,
                   high=1.101+i*.0001, low=1.099+i*.0001,
                   close=1.1002+i*.0001, volume=10+i) for i in range(70)]


def make_store(data=None):
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M15", data or fixture_data())
    return store


T = START + timedelta(hours=16)


def test_same_snapshot_reaches_two_consumers_by_identity():
    bridge = build_replay_market_snapshot("EURUSD", "M15", make_store(), T)
    seen = bridge.deliver({"asian": lambda x: x, "ssc": lambda x: x})
    assert seen[0] is seen[1] is bridge
    assert all(f.as_of_time if False else f.session_date == T.date() for f in bridge.session_facts)
    assert bridge.snapshot.market_data_mode == "REPLAY"


def test_same_dataset_time_is_deterministic_and_future_change_is_invisible():
    data = fixture_data()
    bridge_a = build_replay_market_snapshot("EURUSD", "M15", make_store(data), T)
    changed = list(data)
    changed[-1] = replace(changed[-1], high=changed[-1].high + 100)
    bridge_b = build_replay_market_snapshot("EURUSD", "M15", make_store(changed), T)
    assert bridge_a.snapshot.symbol == bridge_b.snapshot.symbol
    assert bridge_a.snapshot.timeframe == bridge_b.snapshot.timeframe
    assert bridge_a.snapshot.bar_open_time == bridge_b.snapshot.bar_open_time
    assert bridge_a.snapshot.bar_close_time == bridge_b.snapshot.bar_close_time
    assert bridge_a.snapshot.market_data_asof == bridge_b.snapshot.market_data_asof
    assert bridge_a.snapshot.fingerprint == bridge_b.snapshot.fingerprint
    assert bridge_a.session_facts == bridge_b.session_facts
    assert bridge_a.identity != bridge_b.identity  # provenance remains dataset-distinct


def test_changed_visible_time_changes_identity():
    bridge_a = build_replay_market_snapshot("EURUSD", "M15", make_store(), T)
    bridge_b = build_replay_market_snapshot("EURUSD", "M15", make_store(), T + timedelta(minutes=15))
    assert bridge_a.identity != bridge_b.identity


def test_missing_dataset_and_naive_time_fail_closed():
    with pytest.raises(ReplayBridgeError):
        build_replay_market_snapshot("EURUSD", "M15", HistoricalCandleStore(), T)
    with pytest.raises(ReplayBridgeError):
        build_replay_market_snapshot("EURUSD", "M15", make_store(), datetime(2026, 9, 18, 16))


def test_bridge_import_firewall():
    tree = ast.parse(open("src/strategy_contract/replay_bridge.py", encoding="utf-8").read())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden = ("execution", "proposal", "risk", "telegram", "frontend", "market_intelligence")
    assert not any(any(name == p or name.startswith(p + ".") for p in forbidden) for name in imports)
