"""Focused tests for the combined FX daily decision report + append-only archive
(post_asian_pilot.daily_fx_report / post_asian_pilot.report_archive). Uses tmp_path-
backed pilot configs/state dirs throughout -- never touches the real journal/ directory
or real release files beyond reading them (read-only).
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest
import yaml

from post_asian_pilot.decision import data_error_decision, watch_decision
from post_asian_pilot.store import PilotStores, save_decision
from strategy_engine.loader import load_strategy

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


def _write_pilot_yaml(tmp_path, pair_id: str, reference_session: str, start_utc: str, end_utc: str) -> str:
    raw = {
        "pilot_id": f"TEST_{pair_id}",
        "strategy_id": "ST_ASIAN_SWEEP_5R_V1",
        "strategy_version": "1.1.1",
        "strategy_source_path": STRATEGY_PATH,
        "pair_id": pair_id,
        "universe": ["EURUSD", "GBPUSD"],
        "tie_break_priority": ["EURUSD", "GBPUSD"],
        "reference_session": {"source": "config/canonical_sessions.yaml", "name": reference_session},
        "execution_window": {"id": pair_id, "start_utc": start_utc, "end_utc": end_utc},
        "state_dir": str(tmp_path / pair_id.lower()),
        "risk": {
            "risk_per_trade_pct": 0.5, "max_open_positions": 2, "max_new_trades_per_day": 2,
            "max_new_trades_per_symbol_per_day": 1, "max_aggregate_open_risk_pct": 1.0,
            "strategy_daily_loss_limit_r": -1.0,
        },
        "execution": {"mode": "PROPOSAL_ONLY", "automatic_execution": False,
                     "explicit_confirmation_required": True, "live_execution": False},
    }
    path = tmp_path / f"{pair_id.lower()}_pilot.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return str(path)


@pytest.fixture()
def two_pilot_paths(tmp_path):
    asian_london = _write_pilot_yaml(tmp_path, "ASIAN_LONDON", "asian", "07:00", "11:00")
    london_newyork = _write_pilot_yaml(tmp_path, "LONDON_NEWYORK", "london_am", "12:00", "15:00")
    return asian_london, london_newyork


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


def _seed_no_trade_day(pilot_path: str, strategy, trading_date: dt.date, reference_session: str) -> None:
    from post_asian_pilot.pilot_config import load_pilot_config
    pilot = load_pilot_config(pilot_path)
    stores = PilotStores.default(pilot.strategy_id, pilot.state_dir)
    for symbol in pilot.universe:
        decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                  reference_session, dt.datetime(trading_date.year, trading_date.month,
                                                                 trading_date.day, 11, 0, tzinfo=UTC),
                                  "NO_SETUP_BY_WINDOW_END")
        save_decision(stores.decision_store, dataclasses.replace(decision, status="NO_TRADE"))


def test_combined_report_zero_proposal_day_is_valid_shape(two_pilot_paths, strategy):
    from post_asian_pilot.daily_fx_report import build_fx_daily_report

    asian_london_path, london_newyork_path = two_pilot_paths
    trading_date = dt.date(2026, 1, 5)
    _seed_no_trade_day(asian_london_path, strategy, trading_date, "asian")
    _seed_no_trade_day(london_newyork_path, strategy, trading_date, "london_am")

    report = build_fx_daily_report(trading_date, asian_london_path, london_newyork_path)

    assert report["schema_version"] == "AG_FX_DAILY_REPORT_V1"
    assert report["report_type"] == "FX_DAILY"
    assert report["trading_date"] == "2026-01-05"
    assert report["daily_proposal_required"] is False
    assert report["daily_decision_required"] is True
    assert set(report["cycles"]) == {"ASIAN_LONDON", "LONDON_NEWYORK"}
    for cycle_name in ("ASIAN_LONDON", "LONDON_NEWYORK"):
        cycle = report["cycles"][cycle_name]
        assert cycle["result"] == "PASS"
        for symbol in ("EURUSD", "GBPUSD"):
            assert cycle["pairs"][symbol]["final_strategy_state"] == "NO_TRADE"
            assert cycle["pairs"][symbol]["proposal_id"] is None
    assert report["execution_authority"]["automatic_execution"] == "DISABLED"
    assert report["execution_authority"]["fx_live_execution"] == "DISABLED"


def test_combined_report_data_error_surfaces_per_cycle(two_pilot_paths, strategy):
    from post_asian_pilot.daily_fx_report import build_fx_daily_report
    from post_asian_pilot.pilot_config import load_pilot_config

    asian_london_path, london_newyork_path = two_pilot_paths
    trading_date = dt.date(2026, 1, 6)

    pilot = load_pilot_config(asian_london_path)
    stores = PilotStores.default(pilot.strategy_id, pilot.state_dir)
    stores.counters.increment(strategy.strategy_id, trading_date, "data_errors")
    for symbol in pilot.universe:
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       "asian", dt.datetime(2026, 1, 6, 8, 0, tzinfo=UTC), ("DATA_MISSING",))
        save_decision(stores.decision_store, decision)
    _seed_no_trade_day(london_newyork_path, strategy, trading_date, "london_am")

    report = build_fx_daily_report(trading_date, asian_london_path, london_newyork_path)
    assert report["cycles"]["ASIAN_LONDON"]["result"] == "PASS_WITH_OBSERVATIONS"
    assert report["cycles"]["LONDON_NEWYORK"]["result"] == "PASS"


def test_human_report_renders_without_fake_price_fields(two_pilot_paths, strategy):
    from post_asian_pilot.daily_fx_report import build_fx_daily_report, human_readable_fx_daily_report

    asian_london_path, london_newyork_path = two_pilot_paths
    trading_date = dt.date(2026, 1, 7)
    _seed_no_trade_day(asian_london_path, strategy, trading_date, "asian")
    _seed_no_trade_day(london_newyork_path, strategy, trading_date, "london_am")

    report = build_fx_daily_report(trading_date, asian_london_path, london_newyork_path)
    text = human_readable_fx_daily_report(report)
    assert "NO_TRADE" in text
    assert "entry" not in text.lower()
    assert "automatic_execution = DISABLED" in text


def test_report_archive_write_is_idempotent(tmp_path):
    from post_asian_pilot.report_archive import archive_path, write_report

    trading_date = dt.date(2026, 1, 5)
    report = {"schema_version": "AG_FX_DAILY_REPORT_V1", "trading_date": "2026-01-05",
             "generated_at_utc": "2026-01-05T15:05:00+00:00", "cycles": {"x": 1}}

    path1 = write_report("fx", trading_date, report, root=str(tmp_path))
    assert path1 == archive_path("fx", trading_date, root=str(tmp_path))

    report_again = dict(report, generated_at_utc="2026-01-05T15:06:00+00:00")  # different regen timestamp only
    path2 = write_report("fx", trading_date, report_again, root=str(tmp_path))
    assert path2 == path1  # idempotent no-op -- same file, not a duplicate/correction

    import os
    directory = os.path.dirname(path1)
    assert not any("correction" in name for name in os.listdir(directory))


def test_report_archive_preserves_original_and_writes_correction_on_real_change(tmp_path):
    from post_asian_pilot.report_archive import write_report

    trading_date = dt.date(2026, 1, 5)
    original = {"trading_date": "2026-01-05", "generated_at_utc": "t0", "cycles": {"x": 1}}
    changed = {"trading_date": "2026-01-05", "generated_at_utc": "t1", "cycles": {"x": 2}}

    original_path = write_report("fx", trading_date, original, root=str(tmp_path))
    correction_path = write_report("fx", trading_date, changed, root=str(tmp_path),
                                   correction_reason="TEST_CORRECTION")

    assert correction_path != original_path
    assert "correction-001" in correction_path

    import json
    with open(original_path, encoding="utf-8") as f:
        assert json.load(f)["cycles"] == {"x": 1}  # original untouched
    with open(correction_path, encoding="utf-8") as f:
        record = json.load(f)
    assert record["new_record"]["cycles"] == {"x": 2}
    assert record["correction_reason"] == "TEST_CORRECTION"
    assert record["supersedes"] == original_path


def test_reporting_modules_never_import_execution_send_path():
    import post_asian_pilot.daily_fx_report as daily_fx_report
    import post_asian_pilot.report_archive as report_archive

    for module in (daily_fx_report, report_archive):
        assert not hasattr(module, "order_send")
        assert "execution.executor" not in module.__dict__
        assert "mt5_gateway" not in module.__dict__
        assert not any(name.startswith("execution") for name in vars(module))
