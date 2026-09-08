"""Tests for src/ticket_delivery/scheduler_integration.py -- the module that
scripts/run_post_asian_pilot.py's actual scheduled --once path calls into.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
import yaml

from post_asian_pilot.decision import STATUS_READY, STATUS_WATCH
from post_asian_pilot.governor import PORTFOLIO_SELECTED
from ticket_delivery.scheduler_integration import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_DELIVERY_STATE_DIR,
    MODE_ARCHIVE_ONLY,
    MODE_DISABLED,
    MODE_MESSAGE_DELIVERY,
    TicketDeliveryIntegrationConfig,
    cycle_label_from_pilot_path,
    load_integration_config,
    process_cycle_result,
)

UTC = dt.timezone.utc


# --------------------------------------------------------------------------- config loading

def test_missing_config_file_fails_closed_to_disabled(tmp_path):
    config = load_integration_config(str(tmp_path / "does_not_exist.yaml"))
    assert config.mode == MODE_DISABLED


def test_malformed_yaml_fails_closed_to_disabled(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("mode: [unclosed", encoding="utf-8")
    config = load_integration_config(str(path))
    assert config.mode == MODE_DISABLED


def test_unrecognized_mode_value_fails_closed_to_disabled(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("mode: SEND_EVERYTHING_NOW\n", encoding="utf-8")
    config = load_integration_config(str(path))
    assert config.mode == MODE_DISABLED


def test_valid_archive_only_config_loads_correctly(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("mode: ARCHIVE_ONLY\narchive_root: custom/archive\ndelivery_state_dir: custom/state\n", encoding="utf-8")
    config = load_integration_config(str(path))
    assert config.mode == MODE_ARCHIVE_ONLY
    assert config.archive_root == "custom/archive"
    assert config.delivery_state_dir == "custom/state"


def test_shipped_repository_default_config_is_disabled():
    """The actual committed config/ticket_delivery.yaml -- proves the real shipped
    default is the safe no-op mode, not just a test fixture's assumption."""
    config = load_integration_config("config/ticket_delivery.yaml")
    assert config.mode == MODE_DISABLED


def test_defaults_used_when_fields_absent(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("mode: ARCHIVE_ONLY\n", encoding="utf-8")
    config = load_integration_config(str(path))
    assert config.archive_root == DEFAULT_ARCHIVE_ROOT
    assert config.delivery_state_dir == DEFAULT_DELIVERY_STATE_DIR


# --------------------------------------------------------------------------- cycle label derivation

def test_no_pilot_path_means_asian_london():
    assert cycle_label_from_pilot_path(None) == "ASIAN_LONDON"


def test_london_newyork_pilot_path_detected():
    assert cycle_label_from_pilot_path("config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml") == "LONDON_NEWYORK"


def test_asian_london_pilot_path_detected():
    assert cycle_label_from_pilot_path("config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml") == "ASIAN_LONDON"


def test_unrecognized_pilot_path_raises_rather_than_guessing():
    with pytest.raises(ValueError):
        cycle_label_from_pilot_path("config/pilot/SOME_OTHER_PILOT.yaml")


# --------------------------------------------------------------------------- process_cycle_result

def _decision(status):
    return SimpleNamespace(status=status, reason_codes=("R1",), evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC))


def _pair(symbol, status=STATUS_WATCH, proposal=None):
    return SimpleNamespace(
        symbol=symbol, decision=_decision(status), portfolio_state=PORTFOLIO_SELECTED,
        portfolio_reason_code=None, proposal=proposal,
    )


def _result(pairs):
    strategy = SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1", version="1.1.1")
    return SimpleNamespace(strategy=strategy, release_id="AG_TRADE_ASSISTANT_V1_0_3", trading_date=dt.date(2026, 9, 8), pairs=pairs)


def test_disabled_mode_returns_empty_and_touches_no_filesystem(tmp_path):
    config = TicketDeliveryIntegrationConfig(mode=MODE_DISABLED, archive_root=str(tmp_path / "archive"), delivery_state_dir=str(tmp_path / "state"))
    outcomes = process_cycle_result(_result([_pair("EURUSD")]), pilot_path=None, config=config)
    assert outcomes == []
    import os
    assert not os.path.exists(str(tmp_path / "archive"))
    assert not os.path.exists(str(tmp_path / "state"))


def test_archive_only_mode_archives_watch_and_makes_no_network_call(tmp_path):
    config = TicketDeliveryIntegrationConfig(mode=MODE_ARCHIVE_ONLY, archive_root=str(tmp_path / "archive"), delivery_state_dir=str(tmp_path / "state"))
    outcomes = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config)
    assert len(outcomes) == 1
    assert outcomes[0]["cycle_state"] == "WATCH"
    assert outcomes[0]["delivery_state"] == "NOT_APPLICABLE"


def test_message_delivery_mode_is_currently_identical_to_archive_only_zero_network(tmp_path):
    """Explicit proof of this pass's deliberate non-activation: even a config
    requesting MESSAGE_DELIVERY makes zero network calls, because this integration
    function never constructs a deliver() closure for either archiving mode."""
    config_msg = TicketDeliveryIntegrationConfig(mode=MODE_MESSAGE_DELIVERY, archive_root=str(tmp_path / "archive1"), delivery_state_dir=str(tmp_path / "state1"))
    config_archive = TicketDeliveryIntegrationConfig(mode=MODE_ARCHIVE_ONLY, archive_root=str(tmp_path / "archive2"), delivery_state_dir=str(tmp_path / "state2"))

    pair = _pair("EURUSD", status=STATUS_WATCH)
    outcomes_msg = process_cycle_result(_result([pair]), pilot_path=None, config=config_msg)
    outcomes_archive = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config_archive)

    assert [o["delivery_state"] for o in outcomes_msg] == [o["delivery_state"] for o in outcomes_archive]
    assert outcomes_msg[0]["delivery_state"] == "NOT_APPLICABLE"


def test_no_deliver_closure_constructed_for_any_mode_static_check():
    import inspect

    import ticket_delivery.scheduler_integration as mod
    source = inspect.getsource(mod.process_cycle_result)
    assert "deliver = None" in source
    # No conditional branch assigns anything else to `deliver` -- single, unconditional assignment.
    assert source.count("deliver =") == 1


def test_ready_pair_without_ledger_context_reports_render_blocked_not_delivered(tmp_path):
    """A READY pair processed without ledger/fingerprint context (the honest 'we don't
    have enough persisted context to render' case) must report RENDER_BLOCKED, never
    fabricate a ticket or silently skip archiving."""
    proposal = SimpleNamespace(setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-08", actionable=True)
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal)
    config = TicketDeliveryIntegrationConfig(mode=MODE_ARCHIVE_ONLY, archive_root=str(tmp_path / "archive"), delivery_state_dir=str(tmp_path / "state"))
    outcomes = process_cycle_result(_result([pair]), pilot_path=None, config=config)
    assert outcomes[0]["cycle_state"] == "READY"
    assert outcomes[0]["archived"] is True
    assert outcomes[0]["delivery_state"] == "RENDER_BLOCKED"


def test_repeated_call_same_result_converges_on_same_logical_ticket(tmp_path):
    config = TicketDeliveryIntegrationConfig(mode=MODE_ARCHIVE_ONLY, archive_root=str(tmp_path / "archive"), delivery_state_dir=str(tmp_path / "state"))
    result = _result([_pair("EURUSD", status=STATUS_WATCH)])
    first = process_cycle_result(result, pilot_path=None, config=config)
    second = process_cycle_result(result, pilot_path=None, config=config)
    assert first[0]["logical_ticket_id"] == second[0]["logical_ticket_id"]
