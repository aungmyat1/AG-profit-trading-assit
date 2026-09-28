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
