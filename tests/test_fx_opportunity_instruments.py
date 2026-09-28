"""AG_FX_OPPORTUNITY_PLATFORM_V2 P1: per-instrument pip/point semantics."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from fx_opportunity.instruments import (
    InstrumentConfigError,
    UnknownInstrumentError,
    check_broker_spec,
    get_instrument,
    load_instruments,
)


def test_three_pairs_are_defined():
    assert sorted(load_instruments()) == ["EURUSD", "GBPUSD", "USDJPY"]


@pytest.mark.parametrize("symbol,digits,point,pip", [
    ("EURUSD", 5, 0.00001, 0.0001),
    ("GBPUSD", 5, 0.00001, 0.0001),
    ("USDJPY", 3, 0.001, 0.01),
])
def test_pip_semantics(symbol, digits, point, pip):
    inst = get_instrument(symbol)
    assert (inst.digits, inst.point, inst.pip_size, inst.points_per_pip) == (digits, point, pip, 10)
    assert inst.allowed_cycles == ("POST_ASIAN", "POST_LONDON")
    assert inst.time_semantics == "UTC"


def test_usdjpy_is_not_priced_in_eurusd_pips():
    assert get_instrument("EURUSD").price_to_pips(0.0025) == 25.0
    assert get_instrument("USDJPY").price_to_pips(0.25) == 25.0
    assert get_instrument("USDJPY").price_to_pips(0.0025) == 0.25


def test_broker_mapping_records_verification_state():
    assert get_instrument("EURUSD").broker_symbol("VANTAGE").verified is True
    assert get_instrument("USDJPY").broker_symbol("VANTAGE").verified is False
    with pytest.raises(UnknownInstrumentError):
        get_instrument("EURUSD").broker_symbol("UNKNOWN_BROKER")


def test_unknown_symbol_fails_closed():
    with pytest.raises(UnknownInstrumentError):
        get_instrument("AUDUSD")


def test_fingerprint_is_stable_and_symbol_specific():
    assert get_instrument("EURUSD").fingerprint() == get_instrument("EURUSD").fingerprint()
    assert get_instrument("EURUSD").fingerprint() != get_instrument("GBPUSD").fingerprint()


def _write(tmp_path, mutate):
    with open("config/instruments/fx_opportunity_instruments.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    mutate(data)
    path = tmp_path / "inst.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("mutate", [
    lambda d: d["instruments"]["USDJPY"].update(pip_size=0.0001),   # the universal-pip mistake
    lambda d: d["instruments"]["USDJPY"].update(point=0.00001),
    lambda d: d["instruments"]["EURUSD"].pop("digits"),
    lambda d: d["instruments"]["GBPUSD"].update(base_currency="EUR"),
    lambda d: d["instruments"]["EURUSD"].update(allowed_cycles=["POST_TOKYO"]),
    lambda d: d.update(timeframe="H1"),
])
def test_inconsistent_contract_fails_closed(tmp_path, mutate):
    with pytest.raises(InstrumentConfigError):
        load_instruments(_write(tmp_path, mutate))


def test_broker_spec_cross_check():
    jpy = get_instrument("USDJPY")
    assert check_broker_spec(jpy, SimpleNamespace(digits=3, point=0.001)) == ()
    assert check_broker_spec(jpy, SimpleNamespace(digits=5, point=0.00001)) == (
        "INSTRUMENT_DIGITS_MISMATCH", "INSTRUMENT_POINT_MISMATCH")
    assert check_broker_spec(jpy, None) == ("BROKER_SYMBOL_UNAVAILABLE",)


# --- P6-R1 broker identity -----------------------------------------------------------

from fx_opportunity.instruments import get_broker, load_brokers  # noqa: E402


def test_vtmarkets_is_the_canonical_verified_broker():
    vt = get_broker("VTMARKETS")
    assert (vt.canonical_name, vt.servers, vt.environment) == ("VT_MARKETS", ("VTMarkets-Demo",), "DEMO")
    for symbol in ("EURUSD", "GBPUSD", "USDJPY"):
        entry = get_instrument(symbol).broker_symbol("VTMARKETS")
        assert (entry.symbol, entry.verified) == (symbol, True)
    # the genuine historical Vantage origin is preserved, with no verified server
    assert get_broker("VANTAGE").servers == ()
    assert sorted(load_brokers()) == ["VANTAGE", "VTMARKETS"]


@pytest.mark.parametrize("mutate", [
    lambda d: d["instruments"]["EURUSD"]["broker_symbols"].update(UNKNOWNBROKER={"symbol": "EURUSD", "verified": True}),
    lambda d: d["brokers"]["VTMARKETS"].update(environment="LIVE"),
    lambda d: d.pop("brokers"),
])
def test_broker_contract_fails_closed(tmp_path, mutate):
    with pytest.raises(InstrumentConfigError):
        load_instruments(_write(tmp_path, mutate))
