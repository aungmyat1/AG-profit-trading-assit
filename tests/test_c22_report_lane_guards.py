"""AGP-C22-R2: OD1014-FAST D4 guard-verdict CANDIDATEs on the report lane (one message per signal),
DATA_MISSING diagnostics incl. the last M15 bar returned, pin mismatches name the field. Thresholds
(STALE_AFTER, FRESHNESS_BARS, MAX_SPREAD_RISK_FRACTION) unchanged. Synthetic only: no MT5/broker/network."""
from __future__ import annotations

import ast
import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_actionability_and_canonical_ticket import SIGNED_POLICY, _c

from mt5 import mt5_candles_readonly as adapter
from reporting import asw_lane
from v1_tickets import actionability, guards
from v1_tickets.mt5_provider import MT5CandleProvider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 7)
CLOSE = dt.datetime(2026, 10, 7, 13, 0, tzinfo=UTC)          # the sweep bar (12:45 open) closes here
QUOTE_AT = CLOSE + dt.timedelta(seconds=30)
LANE_CLOCK = CLOSE + dt.timedelta(seconds=72)                   # host: EURUSD 13:00 bar seen at 72 s


def _bars():
    hi, lo, out = 1.3450, 1.3400, []
    t = dt.datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
    for i in range(20):
        o = h = l = c = (hi + lo) / 2
        if i == 0:
            o, h, l, c = lo + 0.002, hi, lo, lo + 0.001
        out.append(_c(t.isoformat(), o, h, l, c))
        t += dt.timedelta(minutes=15)
    t = dt.datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    while t < CLOSE - dt.timedelta(minutes=15):
        m = (hi + lo) / 2
        out.append(_c(t.isoformat(), m, m + 0.0002, m - 0.0002, m))
        t += dt.timedelta(minutes=15)
    out.append(_c(t.isoformat(), o=lo + 0.0003, h=lo + 0.0005, l=lo - 0.0008, c=lo + 0.0034))
    return out


class Reader:
    _symbol_map = {"GBPUSD": "GBPUSD-VIP"}

    def __init__(self, drop_last=False, fail=None, quote=(1.3433, 1.3434)):
        self.drop_last, self.fail, self._q = drop_last, fail, quote

    def fetch_range(self, symbol, tf, start, end):
        if self.fail:
            raise adapter.CandleAdapterError(adapter.DATA_MISSING, self.fail)
        rows = [SimpleNamespace(time=b.time, symbol=symbol, to_engine_candle=lambda b=b: b)
                for b in _bars() if start <= b.time <= end]
        return rows[:-1] if self.drop_last and rows and rows[-1].time.hour >= 12 else rows

    def quote(self, symbol):
        return (*self._q, QUOTE_AT)


def _lane(now, reader=None):
    provider = MT5CandleProvider(reader or Reader())
    return asw_lane.evaluate_scope("GBPUSD", "LONDON_NEWYORK", now=now, day=DAY, candle_provider=provider,
                                   policy=SIGNED_POLICY)


def test_thresholds_are_unchanged():
    assert guards.STALE_AFTER == dt.timedelta(minutes=15) and actionability.FRESHNESS_BARS == 2
    assert guards.MAX_SPREAD_RISK_FRACTION == 0.15


WIDE = (1.3430, 1.3440)            # 0.0010 spread on a 0.0011 stop distance -> 91% of risk


def test_fresh_signal_with_spread_too_wide_is_a_priced_candidate_with_the_verdict():
    from telegram_delivery.adapter import render_report
    c = _lane(LANE_CLOCK, Reader(quote=WIDE))
    assert c["report_class"] == "CANDIDATE" and c["scope_route"] == "REPORT_ONLY"
    assert c["decision"] not in ("READY", "WATCH_READY") and "SPREAD_TOO_WIDE" in c["reason_codes"]
    assert c["guard_verdicts"] == ["spread 91% of risk > 15% -- NOT ACTIONABLE"]
    text = render_report(c)
    assert text.splitlines()[0].startswith("OPPORTUNITY -- REPORT ONLY -- NON-ACTIONABLE")
    assert "guard: spread 91% of risk > 15% -- NOT ACTIONABLE" in text and "entry: " in text
    assert c["last_m15_bar_utc"] == "2026-10-07T12:45:00+00:00"


def test_same_signal_next_cycle_is_a_duplicate_not_a_second_send(tmp_path):
    from test_report_delivery import sender
    first = _lane(LANE_CLOCK, Reader(quote=WIDE))
    s, calls = sender(tmp_path)
    assert s.send_report(first) == "sent"
    later = dict(first, report_class="BLOCKED", reason_code="INFO_ONLY_STALE",
                 reason_codes=["INFO_ONLY_STALE"], guard_verdicts=None)
    assert later["candidate_signal_id"] == first["candidate_signal_id"]
    assert s.send_report(later) == "duplicate" and len(calls) == 1


def test_missing_spread_stays_blocked_without_prices():
    from telegram_delivery.adapter import render_report

    class NoQuote(Reader):
        def quote(self, symbol):
            raise adapter.CandleAdapterError(adapter.DATA_MISSING, "QUOTE_MISSING")
    c = _lane(LANE_CLOCK, NoQuote())
    assert c["report_class"] == "DATA_ERROR" and not c.get("guard_verdicts")
    assert c["prices"]["entry_reference_raw"] is None and "entry: " not in render_report(c)


@pytest.mark.parametrize("reader,expect", [
    (Reader(drop_last=True), {"requested_bars": 4, "returned_bars": 3, "broker_symbol": "GBPUSD-VIP",
                              "detail": "M15_WINDOW_INCOMPLETE"}),
    (Reader(fail="GBPUSD/M15 (GBPUSD-VIP): (-1, 'Terminal: Call failed')"),
     {"mt5_last_error": "GBPUSD/M15 (GBPUSD-VIP): (-1, 'Terminal: Call failed')", "broker_symbol": "GBPUSD-VIP"}),
])
def test_data_missing_rows_carry_acquisition_diagnostics(reader, expect):
    d = _lane(LANE_CLOCK, reader)["data_error_diagnostics"]
    assert d["code"] == "DATA_MISSING" and d["cycle"] == "LONDON_NEWYORK"
    assert d["cycle_time_utc"] == LANE_CLOCK.isoformat() and d["requested_range_utc"]
    assert {k: d[k] for k in expect} == expect


@pytest.mark.parametrize("status,field", [("ACCOUNT_PIN_MISMATCH SERVER", "SERVER"),
                                          ("ACCOUNT_PIN_MISMATCH LOGIN_SUFFIX", "LOGIN_SUFFIX"),
                                          ("ACCOUNT_PIN_MISMATCH TRADE_MODE", "TRADE_MODE"),
                                          ("ACCOUNT_PIN_MISMATCH TERMINAL_PATH", "TERMINAL_PATH"),
                                          ("ACCOUNT_PIN_VERIFIED", None)])
def test_pin_mismatch_names_the_field_only(status, field):
    import live_candles_smoke as lcs
    assert lcs.pin_mismatch_field(status) == field


def test_no_order_calls_and_guard_still_wraps_the_runner():
    for rel in ("scripts/host/live_candles_smoke.py", "src/reporting/asw_lane.py", "src/v1_tickets/mt5_provider.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        calls = {getattr(n.func, "attr", getattr(n.func, "id", None)) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not calls & {"order_send", "order_check"}, rel
    runner = (ROOT / "scripts" / "host" / "live_candles_smoke.py").read_text(encoding="utf-8")
    assert "mt5 = install_mt5_guard(mt5, run_id)" in runner


# --------------------------------------------------------------------------------- CCFD D4

def _ccfd(reasons, **extra):
    from reporting import ccfd_lane
    row = {"strategy_id": "ST_CRYPTO_CFD_SWEEP_RETEST_V1", "strategy_version": "1.0.0", "symbol": "ETHUSD",
           "cycle": "WEEKDAY", "decision": "BLOCKED", "evaluated_at": LANE_CLOCK.isoformat(),
           "session_date": DAY.isoformat(), "reason_codes": reasons, "direction": "SHORT", "entry": 3000.0,
           "stop_loss": 3020.0, "tp1": 2980.0, "tp2": 2940.0, "spread_pct_of_stop": 22.0, "cost_in_R": 0.31,
           **extra}
    return ccfd_lane.observe_row(row, now=LANE_CLOCK, policy=SIGNED_POLICY)


def test_ccfd_spread_and_cost_guards_are_candidates_with_verdicts():
    c = _ccfd(["SPREAD_TOO_WIDE", "COST_TOO_HIGH", "LOGIC_STATUS_NOT_VERIFIED"])
    assert c["report_class"] == "CANDIDATE" and c["opportunity_basis"] == "OD1014_FAST_D4_GUARD_VERDICT"
    assert c["guard_verdicts"] == ["spread 22% of risk > 20% -- NOT ACTIONABLE",
                                   "cost 0.31R >= 0.25R -- NOT ACTIONABLE"]


@pytest.mark.parametrize("reasons,extra", [
    (["SPREAD_TOO_WIDE", "QUOTE_STALE_OR_MISSING"], {}),                  # another reason -> BLOCKED
    (["SPREAD_TOO_WIDE"], {"spread_pct_of_stop": None}),                  # unmeasured guard -> BLOCKED
    (["COST_TOO_HIGH"], {"tp2": None}),                                   # incomplete plan -> BLOCKED
    (["SPREAD_NOT_EVALUATED"], {}),                                       # missing spread -> BLOCKED
])
def test_ccfd_guard_verdict_needs_a_complete_measured_plan(reasons, extra):
    c = _ccfd(reasons, **extra)
    assert c["report_class"] == "BLOCKED" and not c.get("guard_verdicts")


# ------------------------------------------------------------ E2: one fresh BLOCKED -> CANDIDATE upgrade

def _blocked_missing_spread(first):
    return dict(first, report_class="BLOCKED", reason_code="MISSING_SPREAD", reason_codes=["MISSING_SPREAD"],
                guard_verdicts=None)


def test_blocked_then_fresh_candidate_sends_exactly_once_more(tmp_path):
    from test_report_delivery import sender
    candidate = _lane(LANE_CLOCK, Reader(quote=WIDE))
    assert candidate["freshness"]["status"] == "PASS"
    s, calls = sender(tmp_path)
    assert s.send_report(_blocked_missing_spread(candidate)) == "sent"
    assert s.send_report(candidate) == "sent"                      # the one allowed upgrade
    assert s.send_report(candidate) == "duplicate"                 # same class again
    assert s.send_report(_blocked_missing_spread(candidate)) == "duplicate"   # back to BLOCKED
    assert len(calls) == 2


def test_blocked_then_stale_candidate_is_a_duplicate(tmp_path):
    from test_report_delivery import sender
    candidate = _lane(LANE_CLOCK, Reader(quote=WIDE))
    stale = dict(candidate, freshness={**candidate["freshness"], "status": "FAIL"}, decision="INFO_ONLY_STALE")
    s, calls = sender(tmp_path)
    assert s.send_report(_blocked_missing_spread(candidate)) == "sent"
    assert s.send_report(stale) == "duplicate" and len(calls) == 1


def test_candidate_then_blocked_is_a_duplicate(tmp_path):
    from test_report_delivery import sender
    candidate = _lane(LANE_CLOCK, Reader(quote=WIDE))
    s, calls = sender(tmp_path)
    assert s.send_report(candidate) == "sent"
    assert s.send_report(_blocked_missing_spread(candidate)) == "duplicate" and len(calls) == 1


def test_blocked_then_blocked_is_a_duplicate(tmp_path):
    from test_report_delivery import sender
    candidate = _lane(LANE_CLOCK, Reader(quote=WIDE))
    s, calls = sender(tmp_path)
    assert s.send_report(_blocked_missing_spread(candidate)) == "sent"
    other = dict(_blocked_missing_spread(candidate), reason_code="SIGNAL_STALE", reason_codes=["SIGNAL_STALE"])
    assert s.send_report(other) == "duplicate" and len(calls) == 1
