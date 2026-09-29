"""P6-R2: A5-compatible raw spread observation semantics (evidence collector only)."""
from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

import pytest

from fx_friction_capture import spread_capture as sc
from fx_opportunity.instruments import get_instrument

UTC = dt.timezone.utc
T = dt.datetime(2026, 9, 28, 18, 50, 0, tzinfo=UTC)
VT = sc.VenueIdentity("VT_MARKETS", "VTMarkets-Demo", "DEMO")
REPO = Path(__file__).resolve().parents[1]


def tick(bid, ask, age=1.0):
    return sc.RawTick(bid=bid, ask=ask, time_utc=T - dt.timedelta(seconds=age), time_msc=1)


def row(symbol="EURUSD", t=None, venue=VT, observed=None, pip=None, sampled=T):
    return sc.observe(capture_id="C", sequence=0, sampled_at_utc=sampled, expected_symbol=symbol,
                      observed_symbol=symbol if observed is None else observed, venue=venue,
                      tick=tick(1.17001, 1.17013) if t is None else t,
                      pip_size=pip or get_instrument(symbol).pip_size, git_lineage="abc",
                      session_classification="OTHER")


def test_pip_sizes_match_contract():
    assert (get_instrument("EURUSD").pip_size, get_instrument("GBPUSD").pip_size) == (0.0001, 0.0001)


@pytest.mark.parametrize("symbol,bid,ask,pips", [
    ("EURUSD", 1.17001, 1.17013, 1.2),
    ("GBPUSD", 1.34120, 1.34129, 0.9),
])
def test_spread_arithmetic_and_pip_conversion(symbol, bid, ask, pips):
    r = row(symbol, t=tick(bid, ask))
    assert r["validity"] == "VALID"
    assert r["spread_price"] == round(ask - bid, 10) and r["spread_pips"] == pips
    assert (r["source"], r["collector_version"], r["zero_spread"]) == ("MT5_LIVE_TICK", sc.COLLECTOR_VERSION, False)


def test_zero_spread_is_preserved_and_flagged_as_valid():
    r = row(t=tick(1.17, 1.17))
    assert (r["validity"], r["spread_price"], r["spread_pips"], r["zero_spread"]) == ("VALID", 0.0, 0.0, True)
    assert sc.symbol_counts([r])["zero_spread_samples"] == 1


@pytest.mark.parametrize("kwargs,code", [
    ({"venue": sc.VenueIdentity("UNKNOWN", "VantageMarkets-Demo", "DEMO")}, "WRONG_BROKER"),
    ({"venue": sc.VenueIdentity("VT_MARKETS", "VTMarkets-Live", "DEMO")}, "WRONG_SERVER"),
    ({"venue": sc.VenueIdentity("VT_MARKETS", "VTMarkets-Demo", "NOT_DEMO")}, "WRONG_ENVIRONMENT"),
    ({"observed": "EURUSD-VIP"}, "WRONG_SYMBOL"),
    ({"t": tick(float("nan"), 1.17)}, "NONFINITE_QUOTE"),
    ({"t": tick(1.17, float("inf"))}, "NONFINITE_QUOTE"),
    ({"t": tick(0.0, 1.17)}, "NONPOSITIVE_BID"),
    ({"t": tick(1.17, -1.0)}, "NONPOSITIVE_ASK"),
    ({"t": tick(1.1702, 1.1701)}, "ASK_BELOW_BID"),
    ({"t": tick(1.17, 1.1701, age=sc.STALE_TOLERANCE_SECONDS + 0.001)}, "STALE_TICK"),
])
def test_invalid_observations_are_classified_not_dropped(kwargs, code):
    r = row(**kwargs)
    assert r["validity"] == code
    counts = sc.symbol_counts([r, row()])
    assert (counts["attempted"], counts["valid"], counts["invalid"]) == (2, 1, 1)


def test_boundary_age_is_not_stale():
    assert row(t=tick(1.17, 1.1701, age=sc.STALE_TOLERANCE_SECONDS))["validity"] == "VALID"


def test_missing_tick():
    r = sc.observe(capture_id="C", sequence=0, sampled_at_utc=T, expected_symbol="EURUSD", observed_symbol="EURUSD",
                   venue=VT, tick=None, pip_size=0.0001, git_lineage="abc", session_classification="OTHER")
    assert (r["validity"], r["bid"], r["spread_pips"]) == ("MISSING_TICK", None, None)
    assert sc.symbol_counts([r])["missing"] == 1


def test_nonfinite_rows_serialize_without_nan():
    data = sc.serialize_rows([row(t=tick(float("nan"), 1.17))])
    assert b"NaN" not in data and json.loads(data)["bid"] == "nan"


def test_hashing_is_deterministic_and_content_sensitive():
    a = sc.serialize_rows([row(), row("GBPUSD", t=tick(1.3412, 1.34129))])
    b = sc.serialize_rows([row(), row("GBPUSD", t=tick(1.3412, 1.34129))])
    c = sc.serialize_rows([row(), row("GBPUSD", t=tick(1.3412, 1.3413))])
    assert a == b and sc.sha256(a) == sc.sha256(b) != sc.sha256(c)


def test_serialization_is_secret_free():
    data = sc.serialize_rows([row()]).decode()
    for word in ("login", "password", "account", "investor"):
        assert word not in data.lower()
    with pytest.raises(ValueError):
        sc.assert_secret_free({"rows": [{"account_login": 123}]})


@pytest.mark.parametrize("t,label", [
    (dt.datetime(2026, 9, 28, 7, 0, tzinfo=UTC), "POST_ASIAN"),
    (dt.datetime(2026, 9, 28, 10, 59, tzinfo=UTC), "POST_ASIAN"),
    (dt.datetime(2026, 9, 28, 11, 0, tzinfo=UTC), "OTHER"),
    (dt.datetime(2026, 9, 28, 12, 0, tzinfo=UTC), "POST_LONDON"),
    (dt.datetime(2026, 9, 28, 15, 0, tzinfo=UTC), "OTHER"),
    (dt.datetime(2026, 9, 28, 18, 50, tzinfo=UTC), "OTHER"),
    (dt.datetime(2026, 9, 26, 8, 0, tzinfo=UTC), "OTHER"),  # Saturday
])
def test_session_classification_is_honest(t, label):
    assert sc.classify_session(t) == label


def test_mixed_or_wrong_venue_fails_the_whole_capture():
    good = {"EURUSD": [row()], "GBPUSD": [row("GBPUSD", t=tick(1.3412, 1.34129))]}
    assert sc.capture_status(good) == "VT_CAPTURE_OUTSIDE_TARGET_SESSION"
    vantage = sc.VenueIdentity("UNKNOWN", "VantageMarkets-Demo", "DEMO")
    mixed = {"EURUSD": [row(), row(venue=vantage)], "GBPUSD": good["GBPUSD"]}
    assert sc.capture_status(mixed) == "VT_CAPTURE_VALIDATION_FAILED"
    no_valid = {"EURUSD": [row(t=tick(0.0, 1.17))], "GBPUSD": good["GBPUSD"]}
    assert sc.capture_status(no_valid) == "VT_CAPTURE_VALIDATION_FAILED"


_FORBIDDEN_IMPORT_ROOTS = ("execution", "execution_runtime", "authorization", "ticket_delivery", "strategy_manager",
                           "proposal_envelope", "opportunity", "strategy_engine", "post_asian_pilot")
_MUTATION_APIS = ("order_send", "order_check", "positions_get", "orders_get", "trade_buy", "trade_sell",
                  "trade_close", "trade_modify", "trade_cancel")


@pytest.mark.parametrize("path", [REPO / "src" / "fx_friction_capture" / "spread_capture.py",
                                  REPO / "scripts" / "capture_vt_spread_evidence.py"], ids=lambda p: p.name)
def test_collector_has_no_execution_capability(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            assert name not in _MUTATION_APIS, (path.name, name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for n in names:
                assert n.split(".")[0] not in _FORBIDDEN_IMPORT_ROOTS, (path.name, n)


# --- P6-R3: quote-state metadata probe + session gate --------------------------------

import os  # noqa: E402
import runpy  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fx_friction_capture.quote_metadata import UNAVAILABLE, local_constant_tables, quote_metadata  # noqa: E402
from post_asian_pilot.pilot_config import load_pilot_config  # noqa: E402

CONSTANTS = {"TICK_FLAG_": {"ASK": 4, "BID": 2, "BUY": 32, "LAST": 8, "SELL": 64, "VOLUME": 16},
             "SYMBOL_TRADE_MODE_": {"CLOSEONLY": 3, "DISABLED": 0, "FULL": 4, "LONGONLY": 1, "SHORTONLY": 2},
             "SYMBOL_TRADE_EXECUTION_": {"EXCHANGE": 3, "INSTANT": 1, "MARKET": 2, "REQUEST": 0},
             "SYMBOL_FILLING_": {}}
RAW_TICK = SimpleNamespace(time=1790000000, bid=1.17, ask=1.17, last=0.0, volume=0, time_msc=1790000000123,
                           flags=6, volume_real=0.0)
SYMBOL = SimpleNamespace(trade_mode=0, trade_exemode=2, filling_mode=3, order_mode=127, spread=0, spread_float=True,
                         visible=True, select=True, bid=1.17, ask=float("nan"), name="EURUSD", login=999)


def test_metadata_copies_present_fields_and_decodes_only_with_local_constants():
    m = quote_metadata(RAW_TICK, SYMBOL, CONSTANTS, previous_time_msc=None)
    assert m["tick"]["flags"] == 6 and m["tick_flags_decoded"] == ["ASK", "BID"]
    assert (m["trade_mode_decoded"], m["execution_mode_decoded"]) == ("DISABLED", "MARKET")
    assert m["filling_mode_decoded"] == UNAVAILABLE and m["symbol"]["filling_mode"] == 3
    assert "trade_stops_level" not in m["symbol"]           # absent fields are not invented
    assert m["symbol"]["ask"] == "nan"                      # non-finite kept as raw token, JSON-safe
    assert m["same_tick_as_previous_sample"] is None
    assert quote_metadata(RAW_TICK, SYMBOL, CONSTANTS, 1790000000123)["same_tick_as_previous_sample"] is True
    assert "login" not in json.dumps(m)                     # symbol-only fields; nothing from the account


def test_metadata_is_deterministic_and_never_affects_validity():
    a = quote_metadata(RAW_TICK, SYMBOL, CONSTANTS, 1)
    assert a == quote_metadata(RAW_TICK, SYMBOL, CONSTANTS, 1)
    with_meta = sc.observe(capture_id="C", sequence=0, sampled_at_utc=T, expected_symbol="EURUSD",
                           observed_symbol="EURUSD", venue=VT, tick=tick(1.17, 1.17), pip_size=0.0001,
                           git_lineage="abc", session_classification="OTHER", quote_metadata=a)
    plain = row(t=tick(1.17, 1.17))
    assert {k: v for k, v in with_meta.items() if k != "quote_metadata"} == {k: v for k, v in plain.items() if k != "quote_metadata"}
    assert with_meta["validity"] == "VALID" and with_meta["zero_spread"] is True
    assert sc.serialize_rows([with_meta])  # canonical, NaN-free, secret-free


def test_local_constant_tables_reads_module_families():
    fake = SimpleNamespace(TICK_FLAG_BID=2, SYMBOL_TRADE_MODE_FULL=4, OTHER=1)
    t = local_constant_tables(fake)
    assert t["TICK_FLAG_"] == {"BID": 2} and t["SYMBOL_FILLING_"] == {}


def test_session_windows_match_canonical_pilot_execution_windows():
    for name, start, end in sc.SESSION_WINDOWS:
        path = {"POST_ASIAN": "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml",
                "POST_LONDON": "config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml"}[name]
        pilot = load_pilot_config(path)
        assert (start.strftime("%H:%M"), end.strftime("%H:%M")) == (
            pilot.execution_window_start_utc, pilot.execution_window_end_utc)


def _load_script(monkeypatch, calls):
    fake = types.ModuleType("MetaTrader5")
    fake.__file__ = os.path.join(os.sep, "site-packages", "MetaTrader5", "__init__.py")
    fake.initialize = lambda **k: calls.append("initialize") or False
    fake.last_error = lambda: (-6, "x")
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    cwd = os.getcwd()
    try:
        return runpy.run_path(str(REPO / "scripts" / "capture_vt_spread_evidence.py"), run_name="capture_under_test")
    finally:
        os.chdir(cwd)


@pytest.mark.parametrize("session,start,duration,expected", [
    ("POST_ASIAN", dt.datetime(2026, 9, 29, 7, 5, tzinfo=UTC), 720, None),
    ("POST_ASIAN", dt.datetime(2026, 9, 29, 10, 50, tzinfo=UTC), 720, "INSUFFICIENT_REMAINING_SESSION_WINDOW"),
    ("POST_ASIAN", dt.datetime(2026, 9, 28, 19, 44, tzinfo=UTC), 720, "TARGET_SESSION_NOT_ACTIVE"),
    ("POST_LONDON", dt.datetime(2026, 9, 29, 12, 0, tzinfo=UTC), 720, None),
    ("POST_LONDON", dt.datetime(2026, 9, 29, 8, 0, tzinfo=UTC), 720, "TARGET_SESSION_NOT_ACTIVE"),
    ("OTHER", dt.datetime(2026, 9, 29, 8, 0, tzinfo=UTC), 720, "TARGET_SESSION_NOT_ACTIVE"),
    ("OTHER", dt.datetime(2026, 9, 28, 19, 44, tzinfo=UTC), 720, None),
    ("POST_ASIAN", dt.datetime(2026, 10, 3, 8, 0, tzinfo=UTC), 720, "TARGET_SESSION_NOT_ACTIVE"),  # Saturday
])
def test_session_gate(monkeypatch, session, start, duration, expected):
    gate = _load_script(monkeypatch, [])["session_gate"]
    assert gate(session, start, duration) == expected


def test_out_of_session_run_stops_before_mt5_initialize(monkeypatch, capsys):
    calls = []
    ns = _load_script(monkeypatch, calls)
    monkeypatch.setattr(sys, "argv", ["capture", "--session", "POST_ASIAN"])
    monkeypatch.setitem(ns["main"].__globals__, "session_gate", lambda *a: "TARGET_SESSION_NOT_ACTIVE")
    cwd = os.getcwd()
    try:
        rc = ns["main"]()
    finally:
        os.chdir(cwd)
    out = json.loads(capsys.readouterr().out)
    assert rc == 2 and calls == [] and out["status"] == "TARGET_SESSION_NOT_ACTIVE"
    assert set(out["broker_mutation_calls"].values()) == {0}


# --- V3: stall-safe fixed cadence -----------------------------------------------------


def test_round_action_samples_on_time_and_early_rounds():
    assert sc.round_action(3, 100.0, 110.0, 5.0) == ("SAMPLE", 5.0)       # early: wait
    assert sc.round_action(3, 100.0, 115.0, 5.0) == ("SAMPLE", 0.0)       # due now
    assert sc.round_action(3, 100.0, 119.9, 5.0) == ("SAMPLE", 0.0)       # < one cadence late


def test_round_action_never_bursts_after_a_stall():
    """Reproduces the V2 defect: a ~10 min stall must skip the missed rounds, not sample
    83 of them at one instant."""
    t0, cadence, rounds, resume = 0.0, 5.0, 144, 300.0 + 598.0  # stall from round 60 to ~t=898s
    actions = [sc.round_action(k, t0, resume, cadence)[0] for k in range(60, rounds)]
    sampled_at_resume = actions.count("SAMPLE")
    assert sampled_at_resume <= 1 and actions.count("SKIP_LATE") >= 83 - 1
    skipped = actions.count("SKIP_LATE")
    assert skipped > sc.MAX_SKIPPED_ROUND_FRACTION * rounds   # such a capture is marked failed
