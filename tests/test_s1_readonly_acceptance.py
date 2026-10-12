"""Recorded positive preview through the frozen strategy, never a live-data claim."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
from pathlib import Path

import pytest
from test_actionability_and_canonical_ticket import SIGNED_POLICY

from demo_execution.admission import MarketEvidence
from scripts.host.s1_readonly_acceptance import evaluate_preview
from strategy_engine.session import Candle
from v1_tickets.daily_evaluator import CandleBundle
from v1_tickets.fx import session_windows_utc


def test_frozen_recorded_signal_preview_and_no_order_route():
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/fixtures/manual_ticket/GBPUSD_M15_recorded_spread_60d.csv"
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == "aeaf0ba504569f1fa8b9867f2ac8992e8b33fc143a247644e48a34be16cf2a33"
    day = dt.date(2026, 7, 23)
    windows = session_windows_utc(day)["ASIAN_LONDON"]
    with fixture.open() as stream:
        rows = [row for row in csv.DictReader(stream) if row["timestamp_utc"].startswith(day.isoformat())]
    bars = [Candle(dt.datetime.fromisoformat(row["timestamp_utc"]).replace(tzinfo=dt.timezone.utc),
                   *[float(row[key]) for key in ("open", "high", "low", "close")]) for row in rows]
    reference = [bar for bar in bars if windows["ref"][0] <= bar.time < windows["ref"][1]]
    post = [bar for bar in bars if windows["trade"][0] <= bar.time < windows["trade"][1]]
    before_first_close = windows["trade"][0] + dt.timedelta(seconds=1)
    empty_post = CandleBundle(reference, 24, [], windows["ref"][1], 0.00001, reference[-1].close)
    no_setup = evaluate_preview(empty_post, now=before_first_close,
                                market=MarketEvidence("GBPUSD", reference[-1].close, reference[-1].close + 0.00001,
                                                      before_first_close, empty_post.data_close),
                                policy=SIGNED_POLICY, data_source="RECORDED_FIXTURE")
    assert no_setup["outcome"] == "NO_OPPORTUNITY"
    reports = []
    for index, bar in enumerate(post):
        now = bar.time + dt.timedelta(minutes=15, seconds=1)
        recorded_row = next(row for row in rows if row["timestamp_utc"] == bar.time.strftime("%Y-%m-%d %H:%M:%S"))
        spread = int(recorded_row["spread_points"]) * 0.00001
        bundle = CandleBundle(reference, 24, post[:index + 1], bar.time + dt.timedelta(minutes=15), spread, bar.close)
        # Quote snapshot is explicitly a replay test input; no broker tick provenance is claimed.
        market = MarketEvidence("GBPUSD", bar.close - spread / 2, bar.close + spread / 2, now, bundle.data_close)
        report = evaluate_preview(bundle, now=now, market=market, policy=SIGNED_POLICY, data_source="RECORDED_FIXTURE")
        reports.append(report)
        if report["ticket"].get("decision") == "READY":
            assert report["outcome"] == "SIGNAL" and report["strategy_version"] == "1.1.2"
            assert report["gates"]["ready"]["allowed"]
            assert report["execution_reason"] == "EXECUTION_DISABLED"
            assert report["gates"]["risk"]["reason"] == "RISK_SNAPSHOT_MISSING"
            assert report["gates"]["notification"] == "PRE_ORDER_NOTIFICATION_MISSING"
            assert report["telegram_ascii_preview"].isascii()
            assert report["broker_mutations"] == report["order_api_calls"] == report["telegram_sends"] == 0
            with pytest.raises(ValueError, match="UNCLOSED_M15_BAR"):
                evaluate_preview(bundle, now=bar.time, market=market)
            break
    else:
        pytest.fail(f"Recorded qualifying GBPUSD prefix absent: {[r['ticket']['reason_code'] for r in reports]}")
