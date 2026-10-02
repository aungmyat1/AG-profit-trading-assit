"""AG Read-Only Session Scanner V1 -- unit tests (no network, no MT5)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from session_scanner import checklist as ck
from session_scanner.proposal import build_ticket
from session_scanner.quality import (FRESH, GAPPED, INVALID, STALE, VALID, Bar, assess_quote, assess_series,
                                     fetch_with_sync)
from session_scanner.registry import (InstrumentRegistryError, load_specs, resolve_spec, verify_live)
from session_scanner.scanner import load_scanner_config
from session_scanner.sessions import classify, load_canonical_windows
from session_scanner.strategy_adapter import (ADAPTER_SIGNAL, AsianSweepAdapter, resolve_proposal_scope,
                                              strategy_catalog)
from session_scanner.terminal_client import READ_ONLY_TOOLS, TerminalMcpClient, TerminalToolBlocked
from session_scanner.timebase import TIME_GATE_FAIL, TIME_GATE_PASS, derive_time_authority, parse_server_wallclock

UTC = timezone.utc
PKG = Path(__file__).resolve().parents[1] / "src" / "session_scanner"


@pytest.fixture(scope="module")
def cfg():
    return load_scanner_config()


def _ta(utc="2026-10-02T13:31:32Z", server="2026-10-02T16:31:15"):
    return derive_time_authority({"utc_time": utc, "trade_server_last_known_time": server})


def _vip_info(symbol="EURUSD-VIP", digits=5, point=0.00001, mode="full"):
    return {"symbol": symbol, "digits": digits, "point": point, "trade_mode_name": mode, "contract_size": 100000.0,
            "currency_profit": "USD", "volume_min": 0.01, "volume_step": 0.01}


# ------------------------------------------------------------------ symbol mapping

def test_canonical_maps_to_vip_symbols(cfg):
    specs = load_specs(cfg)
    assert resolve_spec(specs, "EURUSD").broker_symbol == "EURUSD-VIP"
    assert resolve_spec(specs, "XAUUSD").broker_symbol == "XAUUSD-VIP"
    assert {s.broker_symbol for s in specs.values()} == {"EURUSD-VIP", "GBPUSD-VIP", "USDJPY-VIP", "XAUUSD-VIP"}


def test_unknown_mapping_fails_closed(cfg):
    with pytest.raises(InstrumentRegistryError):
        resolve_spec(load_specs(cfg), "AUDUSD")
    bad = dict(cfg, instruments={"NZDUSD": {"asset_class": "FX", "expected_digits": 5, "session_policy": "FX_24x5"}})
    with pytest.raises(InstrumentRegistryError):
        load_specs(bad)


def test_live_metadata_mismatch_fails_closed(cfg):
    spec = resolve_spec(load_specs(cfg), "EURUSD")
    assert verify_live(spec, _vip_info()).pip_size == pytest.approx(0.0001)
    with pytest.raises(InstrumentRegistryError):  # plain reference feed returned instead of -VIP
        verify_live(spec, _vip_info(symbol="EURUSD", mode="disabled"))
    with pytest.raises(InstrumentRegistryError):
        verify_live(spec, _vip_info(mode="disabled"))
    with pytest.raises(InstrumentRegistryError):
        verify_live(spec, None)


# ------------------------------------------------------------------ time normalization

def test_offset_derived_from_broker_clock():
    ta = derive_time_authority({"utc_time": "2026-10-02T13:31:32Z", "trade_server_last_known_time": "2026-10-02T16:31:15"},
                               latest_tick_server=datetime(2026, 10, 2, 16, 31, 30))
    assert ta.gate == TIME_GATE_PASS and ta.broker_utc_offset == timedelta(hours=3) and ta.offset_confidence == "HIGH"
    assert ta.server_to_utc(datetime(2026, 10, 2, 16, 0)) == datetime(2026, 10, 2, 13, 0, tzinfo=UTC)


def test_stale_or_conflicting_clock_fails():
    stale = derive_time_authority({"utc_time": "2026-10-02T13:31:32Z", "trade_server_last_known_time": "2026-10-02T14:10:00"})
    assert stale.gate == TIME_GATE_FAIL
    conflict = derive_time_authority({"utc_time": "2026-10-02T13:31:32Z", "trade_server_last_known_time": "2026-10-02T16:31:15"},
                                     latest_tick_server=datetime(2026, 10, 2, 15, 31, 20))
    assert conflict.gate == TIME_GATE_FAIL
    skew = derive_time_authority({"utc_time": "2026-10-02T13:31:32Z", "trade_server_last_known_time": "2026-10-02T16:31:15"},
                                 local_utc_now=datetime(2026, 10, 2, 13, 40, tzinfo=UTC))
    assert skew.gate == TIME_GATE_FAIL


def test_mislabeled_utc_suffix_cannot_shift_session():
    # mt5ReadOnly stamps server wall-clock 16:33 as "...Z"; trusting the label would say OFF_SESSION.
    ta = _ta()
    naive = parse_server_wallclock("2026-10-02T16:33:17Z")
    assert naive.tzinfo is None and naive == datetime(2026, 10, 2, 16, 33, 17)
    assert parse_server_wallclock("2026-10-02 16:33:17+00:00") == naive
    utc = ta.server_to_utc(naive)
    windows = load_canonical_windows()
    assert classify(utc, windows, {}).current_session == "NEW_YORK"
    assert classify(naive.replace(tzinfo=UTC), windows, {}).current_session == "OFF_SESSION"


# ------------------------------------------------------------------ candles / quality

def _bars(start, n, step_min=15, skip=(), price=1.1):
    out = []
    for i in range(n):
        t = start + timedelta(minutes=step_min * i)
        if t in skip:
            continue
        out.append(Bar(t, price, price + 0.0005, price - 0.0005, price + 0.0001))
    return out


NOW = datetime(2026, 10, 2, 13, 31, tzinfo=UTC)  # server 16:31


def _series_to(last_closed, n=40, **kw):
    return _bars(last_closed - timedelta(minutes=15 * (n - 1)), n + 1, **kw)  # +1 = forming bar


def test_valid_series_and_forming_bar_separated():
    bars = _series_to(datetime(2026, 10, 2, 13, 15, tzinfo=UTC))
    q = assess_series(bars, "M15", NOW, _ta(), None, 20)
    assert q.status == VALID
    assert q.last_closed_bar_utc == datetime(2026, 10, 2, 13, 15, tzinfo=UTC)
    assert q.current_forming_bar_utc == datetime(2026, 10, 2, 13, 30, tzinfo=UTC)
    assert q.closed_count == q.bar_count - 1


def test_duplicate_badohlc_missing_bars():
    ta = _ta()
    bars = _series_to(datetime(2026, 10, 2, 13, 15, tzinfo=UTC))
    assert assess_series(bars[:10] + [bars[9]] + bars[10:], "M15", NOW, ta, None, 20).status == INVALID
    broken = list(bars)
    b = broken[5]
    broken[5] = Bar(b.time_utc, b.open, b.open - 0.001, b.low, b.close)
    assert assess_series(broken, "M15", NOW, ta, None, 20).status == INVALID
    gapped = bars[:10] + bars[12:]
    q = assess_series(gapped, "M15", NOW, ta, None, 20)
    assert q.status == GAPPED and q.unexpected_gaps
    assert assess_series(bars[:-4], "M15", NOW, ta, None, 20).status == STALE


def test_xau_daily_break_and_weekend_are_not_gaps():
    ta = _ta()
    # Server 00:00-01:00 == UTC 21:00-22:00 at UTC+3: four M15 bars legitimately absent.
    skip = {datetime(2026, 10, 1, 21, m, tzinfo=UTC) for m in (0, 15, 30, 45)}
    bars = _bars(datetime(2026, 10, 1, 12, 0, tzinfo=UTC), 103, skip=skip)  # through 13:30 forming
    q = assess_series(bars, "M15", NOW, ta, ("00:00", "01:00"), 20)
    assert q.status == VALID and q.expected_closure_gaps == 4
    assert assess_series(bars, "M15", NOW, ta, None, 20).status == GAPPED  # FX policy has no break
    # Weekend: Friday 20:45 UTC (server 23:45) -> Sunday 21:00 UTC (server Monday 00:00).
    mon_now = datetime(2026, 10, 4, 22, 1, tzinfo=UTC)
    fri = _bars(datetime(2026, 10, 2, 12, 0, tzinfo=UTC), 36)
    mon = _bars(datetime(2026, 10, 4, 21, 0, tzinfo=UTC), 5)
    assert assess_series(fri + mon, "M15", mon_now, ta, None, 20).status == VALID


def test_sync_accepts_fresh_retry_and_rejects_double_stale():
    ta = _ta()
    stale = _series_to(datetime(2026, 10, 2, 12, 15, tzinfo=UTC))
    fresh = _series_to(datetime(2026, 10, 2, 13, 15, tzinfo=UTC))
    assess = lambda b: assess_series(b, "M15", NOW, ta, None, 20)  # noqa: E731
    reads = iter([stale, fresh])
    s = fetch_with_sync(lambda: next(reads), assess)
    assert (s.first_read_status, s.retry_performed, s.second_read_status, s.quality.status) == (STALE, True, VALID, VALID)
    calls, sleeps = [], []
    s2 = fetch_with_sync(lambda: calls.append(1) or stale, assess, retry_delay_s=2.0, sleep=sleeps.append)
    assert s2.quality.status == STALE and len(calls) == 2 and sleeps == [2.0]  # one bounded retry, never a loop


# ------------------------------------------------------------------ sessions

@pytest.mark.parametrize("hhmm,expected", [("00:00", "ASIAN"), ("05:59", "ASIAN"), ("06:00", "LONDON"),
                                           ("11:00", "OFF_SESSION"), ("12:00", "NEW_YORK"), ("15:00", "OFF_SESSION")])
def test_session_boundaries(hhmm, expected):
    now = datetime.combine(date(2026, 10, 2), time.fromisoformat(hhmm), tzinfo=UTC)
    assert classify(now, load_canonical_windows(), {}).current_session == expected


def test_active_cycle_comes_from_contract_trade_windows():
    adapter = AsianSweepAdapter("strategies/ST_ASIAN_SWEEP_5R_V1.yaml", {})
    w, cyc = load_canonical_windows(), adapter.cycles()
    at = lambda h, m=0: classify(datetime(2026, 10, 2, h, m, tzinfo=UTC), w, cyc)  # noqa: E731
    assert at(6, 59).active_cycle is None and at(6, 59).current_session == "LONDON"
    assert at(7).active_cycle == "ASIAN_LONDON"
    assert at(12).active_cycle == "LONDON_NEWYORK" and at(15).active_cycle is None


# ------------------------------------------------------------------ spread authority

def test_plain_reference_zero_spread_cannot_supply_cost(cfg):
    spec = resolve_spec(load_specs(cfg), "EURUSD")
    rec = verify_live(spec, _vip_info())
    ta = _ta()
    q = assess_quote(rec.broker_symbol, {"time_ms": "2026-10-02T16:31:00.100", "bid": 1.12511, "ask": 1.12526},
                     ta, NOW, rec.point, rec.pip_size, 120)
    assert q.broker_symbol == "EURUSD-VIP" and q.spread_points == 15 and q.status == FRESH
    assert ck.spread_gate(q, "FX", 2.0)["status"] == ck.PASS
    wide = assess_quote(rec.broker_symbol, {"time_ms": "2026-10-02T16:31:00.100", "bid": 1.12500, "ask": 1.12530},
                        ta, NOW, rec.point, rec.pip_size, 120)
    assert ck.spread_gate(wide, "FX", 2.0)["status"] == ck.FAIL
    assert ck.spread_gate(q, "METAL", 2.0)["status"] == ck.OBSERVED_ONLY  # no invented metal limit
    with pytest.raises(InstrumentRegistryError):  # the plain feed can never become the cost source
        verify_live(spec, _vip_info(symbol="EURUSD", mode="disabled"))


# ------------------------------------------------------------------ mutation protection

_FORBIDDEN = re.compile(r"\btrade_(send|modify|delete|close)|order_send|order_check|mt5_gateway|management_gateway"
                        r"|\bexecution\.(executor|coordinator|mt5_gateway)|^\s*(from|import)\s+execution\b", re.M)


def test_scanner_source_has_no_mutation_path():
    for path in list(PKG.glob("*.py")) + [PKG.parents[1] / "scripts" / "run_session_scan.py"]:
        assert not _FORBIDDEN.search(path.read_text(encoding="utf-8")), path.name
    assert not any(t.startswith("trade_") for t in READ_ONLY_TOOLS)


def test_client_blocks_non_allowlisted_tools_before_network(monkeypatch):
    monkeypatch.setenv("SCANNER_TEST_TOKEN", "x")
    client = TerminalMcpClient("http://127.0.0.1:9/never", "SCANNER_TEST_TOKEN")
    for name in ("trade_send_market_order", "chart_open", "write_file", "send_web_request", "unknown_tool"):
        with pytest.raises(TerminalToolBlocked):
            client.call(name, {})


# ------------------------------------------------------------------ strategy outputs

DAY = date(2026, 10, 2)


def _asian_range_bars():
    out = []
    for i in range(24):  # oscillating -> ER 0 -> RANGE
        t = datetime(2026, 10, 2, 0, 0, tzinfo=UTC) + timedelta(minutes=15 * i)
        o, c = (1.1000, 1.1010) if i % 2 == 0 else (1.1010, 1.1000)
        out.append(Bar(t, o, 1.1012, 1.0998, c))
    for i in range(4):  # 06:00-06:45 London pre-trade
        out.append(Bar(datetime(2026, 10, 2, 6, 15 * i, tzinfo=UTC), 1.1005, 1.1008, 1.1002, 1.1005))
    return out


def test_valid_sweep_is_ready_with_non_executable_ticket(cfg):
    adapter = AsianSweepAdapter(cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]["contract"],
                                cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]["proposal_scope"])
    bars = _asian_range_bars() + [Bar(datetime(2026, 10, 2, 7, 0, tzinfo=UTC), 1.1005, 1.1009, 1.1001, 1.1008),
                                  Bar(datetime(2026, 10, 2, 7, 15, tzinfo=UTC), 1.1008, 1.1020, 1.1003, 1.1005)]
    now = datetime(2026, 10, 2, 7, 31, tzinfo=UTC)
    res = adapter.evaluate_cycle("ASIAN_LONDON", "EURUSD", DAY, bars, now)
    assert res.status == ADAPTER_SIGNAL and res.signal.direction == "SHORT"
    scope = resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", "EURUSD", adapter.pilots)
    assert scope.authorized and scope.risk_per_trade_pct == 0.5
    from session_scanner.market_state import sweep_events
    events = sweep_events(res.post_bars, 1.1012, 1.0998, "ASIAN")
    q = assess_quote("EURUSD-VIP", {"time_ms": "2026-10-02T10:31:00.000", "bid": 1.10050, "ask": 1.10062},
                     _ta(), now.replace(minute=31, second=5), 0.00001, 0.0001, 120)
    entry = ck.signal_entry_status(res.signal, datetime(2026, 10, 2, 7, 15, tzinfo=UTC))
    assert entry == (True, None)
    common = dict(time_gate=ck.PASS, series_status=dict.fromkeys(ck.MANDATORY_TIMEFRAMES, VALID),
                  quote_status=q.status, cycle="ASIAN_LONDON", strategy_scan_allowed=True, adapter=res,
                  location_events=events, scope=scope, spread=ck.spread_gate(q, "FX", 2.0))
    c = ck.evaluate_checklist(signal_entry=entry, **common)
    assert c["result"] == ck.READY and set(c["checklist"].values()) == {ck.PASS}
    # Same engine SIGNAL observed one closed bar later: market entry has passed -> NO_TRADE, never READY.
    expired = ck.signal_entry_status(res.signal, datetime(2026, 10, 2, 7, 30, tzinfo=UTC))
    assert expired == (False, "SIGNAL_ENTRY_WINDOW_PASSED")
    late = ck.evaluate_checklist(signal_entry=expired, **common)
    assert late["result"] == ck.NO_TRADE and late["reason"].startswith("SIGNAL_ENTRY_WINDOW_PASSED")
    rec = verify_live(resolve_spec(load_specs(cfg), "EURUSD"), _vip_info())
    t = build_ticket(signal=res.signal, strategy=adapter.strategy, record=rec, quote=q, scope=scope,
                     account={"equity": 1000.0, "currency": "USD"}, session="ASIAN_LONDON", now_utc=now,
                     market_context={}, data_freshness={})
    assert t["execution_authorized"] is False
    assert t["take_profit_1"] == 1.0998 and t["stop_loss"] == 1.1020 and t["entry_price"] == 1.1008
    assert t["risk_amount"] == 5.0 and t["position_size"] == 0.04  # 5 / (0.0012 * 100000) = 0.0416 -> 0.04


def test_missing_trigger_stale_data_out_of_session_and_scope(cfg):
    adapter = AsianSweepAdapter(cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]["contract"],
                                cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]["proposal_scope"])
    bars = _asian_range_bars() + [Bar(datetime(2026, 10, 2, 7, 0, tzinfo=UTC), 1.1005, 1.1009, 1.1001, 1.1006)]
    now = datetime(2026, 10, 2, 7, 16, tzinfo=UTC)
    res = adapter.evaluate_cycle("ASIAN_LONDON", "EURUSD", DAY, bars, now)
    ok = dict.fromkeys(ck.MANDATORY_TIMEFRAMES, VALID)
    spread = {"status": ck.PASS}
    base = dict(time_gate=ck.PASS, quote_status=FRESH, strategy_scan_allowed=True, location_events=[],
                scope=resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", "EURUSD", adapter.pilots), spread=spread)
    no_trig = ck.evaluate_checklist(series_status=ok, cycle="ASIAN_LONDON", adapter=res, **base)
    assert no_trig["result"] == ck.NO_TRADE and no_trig["checklist"]["TRIGGER"] == ck.FAIL
    stale = ck.evaluate_checklist(series_status=dict(ok, M15=STALE), cycle="ASIAN_LONDON", adapter=res, **base)
    assert stale["result"] == ck.INSUFFICIENT_DATA
    oos = ck.evaluate_checklist(series_status=ok, cycle=None, adapter=None, **base)
    assert oos["result"] == ck.OUT_OF_SESSION
    assert not resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", "USDJPY", adapter.pilots).authorized
    assert not resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", "XAUUSD", adapter.pilots).authorized


def test_strategy_catalog_respects_registry(cfg):
    cat = {s["strategy_id"]: s for s in strategy_catalog(cfg)}
    assert cat["ST_ASIAN_SWEEP_5R_V1"]["opportunity_scan_allowed"] is True
    assert cat["ST_LARGE_SMC_V1"]["opportunity_scan_allowed"] is False
    assert cat["ST_LARGE_SMC_V1"]["ticket_proposal_allowed"] is False
    assert cat["ST_ASIAN_SWEEP_5R_V1"]["demo_execution_allowed"] is False
