import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "acquire_ssc_one_year_m1_mt5.py"
SPEC = importlib.util.spec_from_file_location("ssc_acquire", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def base(**overrides):
    value = {
        "mt5_initialized": True,
        "server_matches_expected": True,
        "login_matches_expected": True,
        "environment": "DEMO",
        "symbol_available": True,
        "symbol_visible": True,
    }
    value.update(overrides)
    return value


def test_metaquotes_terminal_vendor_does_not_fail_vantage_data_identity():
    assert MODULE.development_data_source_identity(base(terminal_company="MetaQuotes Ltd."), history_available=True)


def test_wrong_server_rejected():
    assert not MODULE.development_data_source_identity(base(server_matches_expected=False), history_available=True)


def test_wrong_account_rejected():
    assert not MODULE.development_data_source_identity(base(login_matches_expected=False), history_available=True)


def test_non_demo_rejected():
    assert not MODULE.development_data_source_identity(base(environment="NON_DEMO"), history_available=True)


def test_symbol_unavailable_rejected():
    assert not MODULE.development_data_source_identity(base(symbol_available=False), history_available=True)


def test_history_unavailable_rejected():
    assert not MODULE.development_data_source_identity(base(), history_available=False)


def test_initialize_failure_rejected():
    assert not MODULE.development_data_source_identity(base(mt5_initialized=False), history_available=True)
