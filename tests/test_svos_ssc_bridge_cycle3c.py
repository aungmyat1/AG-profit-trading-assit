from datetime import datetime, timezone, timedelta

import pytest

from session_sweep_continuation.campaign import Campaign, CampaignStatus
from session_sweep_continuation.replay import ReplayResult
from svos.ssc_bridge import BridgeError, SSCToVirtualOrderBridge
from svos.virtual_exchange import OHLCM1, VirtualExchange, OrderState

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def result(accepted=True):
    campaign = Campaign("EURUSD-ASIAN_LONDON-20260101-LONG", "ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.1", "EURUSD", "ASIAN_LONDON", T0.date(), "LONG", "RANGE") if accepted else None
    setups = [{"setup_model": "S1", "direction": "LONG", "entry_time": str(T0), "entry_price": 1.1,
               "stop_price": 1.099, "risk_pct": 0.4, "outcome": {"partial_target_price": 1.101}}] if accepted else []
    return ReplayResult("EURUSD", "ASIAN_LONDON", T0.date(), "RANGE", campaign, setups, [], [])


def test_actionable_bridge_preserves_reference_and_causal_exchange_fill():
    bridged = SSCToVirtualOrderBridge().build(result(), dataset_id="DS1", decision_event_id="MI-E1", m1_lineage_id="M1-SERIES")
    intent = bridged.intents[0]
    assert intent.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert intent.strategy_version == "1.0.1"
    assert intent.proposal.reference_entry.reference_price == 1.1
    assert intent.proposal.decision_cutoff == T0 + timedelta(minutes=15)
    exchange = VirtualExchange(); order = exchange.submit(intent.proposal)
    order = exchange.process([OHLCM1("M1-E0", "DS1", "EURUSD", T0, 1.1, 1.11, 1.09, 1.1),
                              OHLCM1("M1-E1", "DS1", "EURUSD", T0 + timedelta(minutes=16), 1.1005, 1.101, 1.100, 1.1008)])
    assert order.state == OrderState.FILLED
    assert order.fill.at > intent.proposal.decision_cutoff
    assert order.fill.reference_price == 1.1
    assert order.fill.executable_price != order.fill.reference_price


def test_no_setup_rejected_and_incomplete_produce_no_order():
    bridge = SSCToVirtualOrderBridge()
    assert bridge.build(result(False), dataset_id="DS1", decision_event_id="E").status == "NO_SETUP"
    rejected = ReplayResult("EURUSD", "ASIAN_LONDON", T0.date(), "RANGE", None, [], [{"reason": "BIAS_MISSING"}], [])
    assert bridge.build(rejected, dataset_id="DS1", decision_event_id="E").status == "REJECTED"
    incomplete = ReplayResult("EURUSD", "ASIAN_LONDON", T0.date(), "RANGE", Campaign("C", "ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.1", "EURUSD", "ASIAN_LONDON", T0.date(), "LONG", "RANGE"), [{"direction": "LONG"}], [], [])
    with pytest.raises(BridgeError):
        bridge.build(incomplete, dataset_id="DS1", decision_event_id="E")


def test_identity_is_deterministic_and_lineage_preserved():
    bridge = SSCToVirtualOrderBridge()
    a = bridge.build(result(), dataset_id="DS1", decision_event_id="MI-E1", mi_event_id="MI-E1", m1_lineage_id="M1")
    b = bridge.build(result(), dataset_id="DS1", decision_event_id="MI-E1", mi_event_id="MI-E1", m1_lineage_id="M1")
    assert a.intents[0].proposal.proposal_id == b.intents[0].proposal.proposal_id
    assert a.intents[0].proposal.dataset_id == "DS1"
    assert a.intents[0].proposal.decision_event_id == "MI-E1"
    assert a.intents[0].m1_lineage_id == "M1"


def test_invalid_identity_and_unsupported_evidence_fail_closed():
    bridge = SSCToVirtualOrderBridge()
    with pytest.raises(BridgeError):
        bridge.build(result(), dataset_id="", decision_event_id="E")
    intent = bridge.build(result(), dataset_id="DS1", decision_event_id="E").intents[0]
    exchange = VirtualExchange()
    exchange.submit(intent.proposal)
    with pytest.raises(Exception):
        exchange.process([OHLCM1("E", "OTHER", "EURUSD", T0 + timedelta(minutes=16), 1.1, 1.11, 1.09, 1.1)])
