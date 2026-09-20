from datetime import datetime, timedelta, timezone

import pytest

from svos.virtual_exchange import (ExchangeError, OHLCM1, ObservationKind,
                                   ProposalFixture, ResearchReferenceEntry,
                                   VirtualExchange, OrderState,
                                   OHLC_AMBIGUITY_HASH, OHLC_AMBIGUITY_VERSION,
                                   SAME_BAR_POLICY, compute_ambiguity_contract_hash,
                                   validate_ambiguity_contract)

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def ref():
    return ResearchReferenceEntry("DEC-1", "EURUSD", T0, 1.1000, "DS1|DEC-EVENT")


def proposal(**kw):
    return ProposalFixture("PROP-1", "EURUSD", "LONG", T0, "DS1", "DEC-EVENT", ref(), **kw)


def bar(i, o, h, l, c, *, event=None, dataset="DS1", symbol="EURUSD"):
    return OHLCM1(event or f"E{i}", dataset, symbol, T0 + timedelta(minutes=i), o, h, l, c)


def run(target=True, ambiguous=False):
    e = VirtualExchange()
    e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    later = bar(2, 1.1002, 1.1020 if target else 1.1005, 1.0980 if ambiguous else 1.1001, 1.1003)
    return e.process([bar(1, 1.1001, 1.1003, 1.0999, 1.1002), later])


def test_reference_entry_is_preserved_but_not_used_as_fill():
    order = run(target=False)
    assert order.state == OrderState.FILLED
    assert order.fill.executable_price == 1.1001
    assert order.fill.reference_price == 1.1000
    assert order.fill.executable_price != order.fill.reference_price
    assert order.fill.reason == "OHLC_M1_ENGINEERING_OPEN"


def test_pre_cutoff_bar_cannot_fill_and_first_later_bar_is_eligible():
    e = VirtualExchange()
    e.submit(proposal())
    order = e.process([bar(0, 1.0990, 1.2, 1.0, 1.1), bar(1, 1.1005, 1.101, 1.100, 1.1008)])
    assert order.fill.at == T0 + timedelta(minutes=1)
    assert order.records[1].reason == "FIRST_ELIGIBLE_EVENT"


@pytest.mark.parametrize("kind, high, low", [(ObservationKind.ADVERSE, 1.1005, 1.0980),
                                              (ObservationKind.FAVORABLE, 1.1020, 1.1001),
                                              (ObservationKind.AMBIGUOUS_SEQUENCE, 1.1020, 1.0980)])
def test_exit_observation_is_explicit(kind, high, low):
    e = VirtualExchange()
    e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    order = e.process([bar(1, 1.1001, 1.1003, 1.1000, 1.1002), bar(2, 1.1002, high, low, 1.1003)])
    assert order.exit.observation_kind == kind.value


def test_ambiguity_contract_is_frozen_and_versioned():
    digest = validate_ambiguity_contract()
    assert OHLC_AMBIGUITY_VERSION == "VD_OHLC_AMBIGUITY_V1"
    assert SAME_BAR_POLICY == "AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER"
    assert OHLC_AMBIGUITY_HASH == digest
    assert digest.startswith("sha256:")
    assert compute_ambiguity_contract_hash() == digest


@pytest.mark.parametrize(
    "entry_bar, expected",
    [
        (bar(1, 1.1001, 1.1003, 1.0988, 1.1002), ObservationKind.AMBIGUOUS_SEQUENCE.value),
        (bar(1, 1.1001, 1.1015, 1.0998, 1.1004), ObservationKind.AMBIGUOUS_SEQUENCE.value),
    ],
)
def test_same_bar_fill_and_exit_is_fail_closed(entry_bar, expected):
    e = VirtualExchange()
    e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    order = e.process([entry_bar])
    assert order.exit is not None
    assert order.exit.observation_kind == expected
    assert order.exit.reason == expected


def test_entry_plus_target_same_bar_is_ambiguous():
    e = VirtualExchange()
    e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    order = e.process([bar(1, 1.1001, 1.1015, 1.1000, 1.1008)])
    assert order.exit is not None
    assert order.exit.observation_kind == ObservationKind.AMBIGUOUS_SEQUENCE.value
    assert order.exit.executable_price is None


def test_sl_plus_target_after_entry_is_ambiguous_same_bar():
    e = VirtualExchange(); e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    first_fill = bar(1, 1.1001, 1.1003, 1.1000, 1.1002)
    ambiguous_bar = bar(2, 1.1002, 1.1015, 1.0988, 1.1009)
    order = e.process([first_fill, ambiguous_bar])
    assert order.exit is not None
    assert order.exit.observation_kind == ObservationKind.AMBIGUOUS_SEQUENCE.value
    assert order.exit.reason == ObservationKind.AMBIGUOUS_SEQUENCE.value


def test_multiple_targets_in_one_bar_do_not_infer_favorable_sequence():
    e = VirtualExchange(); e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    order = e.process([bar(1, 1.1001, 1.1003, 1.1000, 1.1002), bar(2, 1.1002, 1.1020, 1.0988, 1.1013)])
    assert order.exit is not None
    assert order.exit.observation_kind == ObservationKind.AMBIGUOUS_SEQUENCE.value
    assert order.exit.executable_price is None


def test_gap_cross_bar_is_fail_closed_when_range_crosses_levels():
    e = VirtualExchange(); e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    order = e.process([bar(1, 1.1001, 1.1003, 1.1000, 1.1002), bar(2, 1.1002, 1.1015, 1.0988, 1.1004)])
    assert order.exit is not None
    assert order.exit.observation_kind == ObservationKind.AMBIGUOUS_SEQUENCE.value


def test_unknown_intrabar_chronology_never_favors_target_sequence():
    e = VirtualExchange()
    e.submit(proposal(stop_price=1.0990, target_price=1.1010))
    order = e.process([bar(1, 1.1001, 1.1015, 1.0988, 1.1002)])
    assert order.exit is not None
    assert order.exit.observation_kind == ObservationKind.AMBIGUOUS_SEQUENCE.value
    assert order.exit.executable_price is None


@pytest.mark.parametrize("mode", ["step", "accelerated", "maximum"])
def test_determinism_and_input_order_independence(mode):
    bars = [bar(2, 1.1002, 1.1010, 1.1001, 1.1004), bar(1, 1.1001, 1.1003, 1.1000, 1.1002)]
    a, b = VirtualExchange(), VirtualExchange()
    a.submit(proposal()); b.submit(proposal())
    oa, ob = a.process(bars, mode=mode), b.process(reversed(bars), mode=mode)
    assert [(r.record_id, r.reason) for r in oa.records] == [(r.record_id, r.reason) for r in ob.records]


def test_failure_closed_guards():
    with pytest.raises(ExchangeError):
        VirtualExchange(execution_quality="REAL_TICK")
    with pytest.raises(ExchangeError):
        VirtualExchange().process([])
    e = VirtualExchange(); e.submit(proposal())
    with pytest.raises(ExchangeError):
        e.process([bar(1, 1, 2, .5, 1, symbol="GBPUSD")])
    with pytest.raises(ExchangeError):
        OHLCM1("bad", "DS1", "EURUSD", T0, 1, .9, .8, .85)


def test_missing_lineage_and_expiry_are_deterministic():
    e = VirtualExchange(); e.submit(proposal(expires_at=T0 + timedelta(minutes=1)))
    order = e.process([bar(1, 1.1, 1.11, 1.09, 1.1), bar(2, 1.1, 1.11, 1.09, 1.1)])
    assert order.state == OrderState.EXPIRED
