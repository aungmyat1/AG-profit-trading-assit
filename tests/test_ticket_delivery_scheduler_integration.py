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
from ticket_delivery.policy import CatchUpPolicy, RetryPolicy
from ticket_delivery.scheduler_integration import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_DELIVERY_STATE_DIR,
    MODE_ARCHIVE_ONLY,
    MODE_DISABLED,
    MODE_MESSAGE_DELIVERY,
    REASON_POLICY_BLOCK_MISSING,
    REASON_POLICY_RETRY_DELAY_BOUNDS_INVALID,
    REASON_POLICY_UNKNOWN_FIELD,
    REASON_POLICY_VALUE_INVALID_TYPE,
    REASON_POLICY_VALUE_MISSING,
    REASON_POLICY_VALUE_NOT_POSITIVE,
    TicketDeliveryConfigError,
    TicketDeliveryIntegrationConfig,
    cycle_label_from_pilot_path,
    load_integration_config,
    process_cycle_result,
)

UTC = dt.timezone.utc

_SIGNED_POLICY_YAML = (
    "policy:\n"
    "  fx_max_catch_up_age_minutes: 60\n"
    "  delivery_max_attempts: 3\n"
    "  delivery_retry_base_delay_seconds: 30\n"
    "  delivery_retry_max_delay_seconds: 300\n"
)


def _write_yaml(tmp_path, body: str, name: str = "cfg.yaml") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- config loading (structural)

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


def test_valid_archive_only_config_with_signed_policy_loads_correctly(tmp_path):
    path = _write_yaml(tmp_path, f"mode: ARCHIVE_ONLY\narchive_root: custom/archive\ndelivery_state_dir: custom/state\n{_SIGNED_POLICY_YAML}")
    config = load_integration_config(path)
    assert config.mode == MODE_ARCHIVE_ONLY
    assert config.archive_root == "custom/archive"
    assert config.delivery_state_dir == "custom/state"
    assert config.catch_up_policy.max_catch_up_age == dt.timedelta(minutes=60)
    assert config.retry_policy.max_attempts == 3
    assert config.retry_policy.base_delay_seconds == 30
    assert config.retry_policy.max_delay_seconds == 300


def test_shipped_repository_default_config_is_archive_only():
    """The actual committed config/ticket_delivery.yaml -- proves the real shipped
    mode is ARCHIVE_ONLY (owner-authorized 2026-09-08) with a valid signed policy, not
    just a test fixture's assumption."""
    config = load_integration_config("config/ticket_delivery.yaml")
    assert config.mode == MODE_ARCHIVE_ONLY
    assert config.catch_up_policy.max_catch_up_age == dt.timedelta(minutes=60)
    assert config.retry_policy.max_attempts == 3
    assert config.retry_policy.base_delay_seconds == 30
    assert config.retry_policy.max_delay_seconds == 300


def test_defaults_used_when_optional_fields_absent(tmp_path):
    path = _write_yaml(tmp_path, f"mode: ARCHIVE_ONLY\n{_SIGNED_POLICY_YAML}")
    config = load_integration_config(path)
    assert config.archive_root == DEFAULT_ARCHIVE_ROOT
    assert config.delivery_state_dir == DEFAULT_DELIVERY_STATE_DIR


def test_disabled_mode_never_requires_a_policy_block(tmp_path):
    """DISABLED must remain the unconditional one-line rollback -- it must not raise
    even if the policy block is entirely absent or malformed."""
    path = _write_yaml(tmp_path, "mode: DISABLED\n")
    config = load_integration_config(path)
    assert config.mode == MODE_DISABLED


# --------------------------------------------------------------------------- signed policy validation (Gate 2)

def test_policy_block_entirely_missing_raises_when_mode_is_active(tmp_path):
    path = _write_yaml(tmp_path, "mode: ARCHIVE_ONLY\n")
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_BLOCK_MISSING


@pytest.mark.parametrize("missing_field", [
    "fx_max_catch_up_age_minutes", "delivery_max_attempts",
    "delivery_retry_base_delay_seconds", "delivery_retry_max_delay_seconds",
])
def test_each_required_policy_value_missing_raises(tmp_path, missing_field):
    fields = {
        "fx_max_catch_up_age_minutes": 60, "delivery_max_attempts": 3,
        "delivery_retry_base_delay_seconds": 30, "delivery_retry_max_delay_seconds": 300,
    }
    del fields[missing_field]
    body = "mode: ARCHIVE_ONLY\npolicy:\n" + "".join(f"  {k}: {v}\n" for k, v in fields.items())
    path = _write_yaml(tmp_path, body)
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_VALUE_MISSING


def test_invalid_type_string_instead_of_number_raises(tmp_path):
    path = _write_yaml(tmp_path, 'mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: "sixty"\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n')
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_VALUE_INVALID_TYPE


def test_boolean_value_does_not_silently_pass_as_numeric(tmp_path):
    """bool is a subclass of int in Python -- `true`/`false` must never silently pass
    validation as 1/0."""
    path = _write_yaml(tmp_path, "mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: true\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n")
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_VALUE_INVALID_TYPE


def test_float_rejected_for_integer_only_field(tmp_path):
    path = _write_yaml(tmp_path, "mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: 60.5\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n")
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_VALUE_INVALID_TYPE


@pytest.mark.parametrize("bad_value", [0, -1, -60])
def test_zero_or_negative_value_raises(tmp_path, bad_value):
    path = _write_yaml(tmp_path, f"mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: {bad_value}\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n")
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_VALUE_NOT_POSITIVE


def test_base_delay_greater_than_max_delay_raises(tmp_path):
    path = _write_yaml(tmp_path, "mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: 60\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 400\n  delivery_retry_max_delay_seconds: 300\n")
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_RETRY_DELAY_BOUNDS_INVALID


def test_base_delay_equal_to_max_delay_is_valid(tmp_path):
    path = _write_yaml(tmp_path, "mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: 60\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 300\n  delivery_retry_max_delay_seconds: 300\n")
    config = load_integration_config(path)
    assert config.retry_policy.base_delay_seconds == 300


def test_unsupported_extra_policy_field_raises_under_strict_parsing(tmp_path):
    path = _write_yaml(tmp_path, f"mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: 60\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n  extra_unsigned_field: 1\n")
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_POLICY_UNKNOWN_FIELD


def test_policy_validation_error_never_silently_substitutes_a_default(tmp_path):
    """A malformed value must raise, never fall back to some implicit numeric
    default -- there is no such default anywhere in this module."""
    path = _write_yaml(tmp_path, "mode: ARCHIVE_ONLY\npolicy:\n  fx_max_catch_up_age_minutes: -5\n  delivery_max_attempts: 3\n  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n")
    with pytest.raises(TicketDeliveryConfigError):
        load_integration_config(path)
    # No side effect: calling again with the same bad file still raises identically,
    # proving no cached/defaulted config was produced anywhere.
    with pytest.raises(TicketDeliveryConfigError):
        load_integration_config(path)


def test_message_delivery_mode_also_requires_the_signed_policy_block(tmp_path):
    path = _write_yaml(tmp_path, "mode: MESSAGE_DELIVERY\n")
    with pytest.raises(TicketDeliveryConfigError):
        load_integration_config(path)


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

def _decision(status, ready_at=None):
    return SimpleNamespace(status=status, reason_codes=("R1",),
                           evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC), ready_at=ready_at)


def _pair(symbol, status=STATUS_WATCH, proposal=None, ready_at=None):
    return SimpleNamespace(
        symbol=symbol, decision=_decision(status, ready_at=ready_at), portfolio_state=PORTFOLIO_SELECTED,
        portfolio_reason_code=None, proposal=proposal,
    )


def _result(pairs):
    strategy = SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1", version="1.1.1")
    return SimpleNamespace(strategy=strategy, release_id="AG_TRADE_ASSISTANT_V1_0_3", trading_date=dt.date(2026, 9, 8), pairs=pairs)


def _config(mode, tmp_path, catch_up_minutes=60):
    return TicketDeliveryIntegrationConfig(
        mode=mode, archive_root=str(tmp_path / "archive"), delivery_state_dir=str(tmp_path / "state"),
        catch_up_policy=CatchUpPolicy(max_catch_up_age=dt.timedelta(minutes=catch_up_minutes)),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300),
    )


def test_disabled_mode_returns_empty_and_touches_no_filesystem(tmp_path):
    config = _config(MODE_DISABLED, tmp_path)
    outcomes = process_cycle_result(_result([_pair("EURUSD")]), pilot_path=None, config=config)
    assert outcomes == []
    import os
    assert not os.path.exists(str(tmp_path / "archive"))
    assert not os.path.exists(str(tmp_path / "state"))


def test_archive_only_mode_archives_watch_and_makes_no_network_call(tmp_path):
    config = _config(MODE_ARCHIVE_ONLY, tmp_path)
    outcomes = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config)
    assert len(outcomes) == 1
    assert outcomes[0]["cycle_state"] == "WATCH"
    assert outcomes[0]["delivery_state"] == "NOT_APPLICABLE"


def test_message_delivery_mode_is_currently_identical_to_archive_only_zero_network(tmp_path, monkeypatch):
    """Explicit proof of this pass's deliberate non-activation: even a config
    requesting MESSAGE_DELIVERY makes zero network calls when no destination is
    authorized (the shipped, current state -- `telegram_destination.authorized_chat_ids`
    is empty in config/ticket_delivery.yaml). Env vars are explicitly cleared so this
    is deterministic regardless of what happens to be set in the actual process
    environment (WP7: TelegramDestinationConfig.from_env() must fail closed here)."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    config_msg = TicketDeliveryIntegrationConfig(
        mode=MODE_MESSAGE_DELIVERY, archive_root=str(tmp_path / "archive1"), delivery_state_dir=str(tmp_path / "state1"),
        catch_up_policy=CatchUpPolicy(max_catch_up_age=dt.timedelta(minutes=60)),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300),
    )
    config_archive = _config(MODE_ARCHIVE_ONLY, tmp_path)

    pair = _pair("EURUSD", status=STATUS_WATCH)
    outcomes_msg = process_cycle_result(_result([pair]), pilot_path=None, config=config_msg)
    outcomes_archive = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config_archive)

    assert [o["delivery_state"] for o in outcomes_msg] == [o["delivery_state"] for o in outcomes_archive]
    assert outcomes_msg[0]["delivery_state"] == "NOT_APPLICABLE"


def test_deliver_closure_only_ever_constructed_inside_the_message_delivery_branch_static_check():
    """WP7 superseded the pre-WP7 invariant ("no mode ever constructs a deliver()
    closure") with a narrower one: `deliver` still starts as an unconditional `None`
    for every mode (ARCHIVE_ONLY/DISABLED never reassign it), and the ONLY other
    assignment is gated behind an `if config.mode == MODE_MESSAGE_DELIVERY:` check --
    so ARCHIVE_ONLY remains provably unable to reach the network-adapter constructor."""
    import inspect

    import ticket_delivery.scheduler_integration as mod
    source = inspect.getsource(mod.process_cycle_result)
    assert "deliver = None" in source
    assert source.count("deliver =") == 2  # the unconditional None, plus one gated reassignment
    lines = source.splitlines()
    gate_idx = next(i for i, line in enumerate(lines) if "if config.mode == MODE_MESSAGE_DELIVERY:" in line)
    assert "_build_message_delivery_closure" in lines[gate_idx + 1]


def test_ready_pair_without_ledger_context_reports_render_blocked_not_delivered(tmp_path):
    """A READY pair processed without ledger/fingerprint context (the honest 'we don't
    have enough persisted context to render' case) must report RENDER_BLOCKED, never
    fabricate a ticket or silently skip archiving. ready_at set to "now" so the
    (already-signed) catch-up gate does not itself block this on-time case."""
    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = SimpleNamespace(setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-08", actionable=True)
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    config = _config(MODE_ARCHIVE_ONLY, tmp_path)
    outcomes = process_cycle_result(_result([pair]), pilot_path=None, config=config, now=now)
    assert outcomes[0]["cycle_state"] == "READY"
    assert outcomes[0]["archived"] is True
    assert outcomes[0]["delivery_state"] == "RENDER_BLOCKED"


def test_repeated_call_same_result_converges_on_same_logical_ticket(tmp_path):
    config = _config(MODE_ARCHIVE_ONLY, tmp_path)
    result = _result([_pair("EURUSD", status=STATUS_WATCH)])
    first = process_cycle_result(result, pilot_path=None, config=config)
    second = process_cycle_result(result, pilot_path=None, config=config)
    assert first[0]["logical_ticket_id"] == second[0]["logical_ticket_id"]


# --------------------------------------------------------------------------- catch-up gate, wired through process_cycle_result

def test_on_time_ready_registers_normally_through_process_cycle_result(tmp_path, monkeypatch):
    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = SimpleNamespace(setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-08", actionable=True)
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    config = _config(MODE_ARCHIVE_ONLY, tmp_path)

    def fake_render_entry_ticket(*a, **k):
        return {
            "application": {"release_id": "AG_TRADE_ASSISTANT_V1_0_3"},
            "strategy": {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1"},
            "identity": {"proposal_id": "P1", "setup_id": proposal.setup_id},
            "market": {"symbol": "EURUSD", "direction": "SHORT"},
            "entry": {"entry": 1.0822, "stop_loss": 1.0852, "tp1": 1.0792, "tp2_runner": 1.0762},
            "risk": {"risk_percent": 0.5, "normalized_volume": 0.05},
            "timing": {"created_at": now.isoformat(), "expires_at": "2026-09-08T11:00:00+00:00"},
            "evidence": {"reason_codes": ["UPPER_SWEEP"]},
        }

    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "render_entry_ticket", fake_render_entry_ticket)
    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "TRANSPORT_NOT_CONFIGURED"


def test_ready_more_than_60_minutes_late_is_rejected_not_registered(tmp_path):
    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(minutes=90)  # well outside the 60-minute signed bound
    proposal = SimpleNamespace(setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-08", actionable=True)
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=ready_at)
    config = _config(MODE_ARCHIVE_ONLY, tmp_path)

    outcomes = process_cycle_result(_result([pair]), pilot_path=None, config=config, now=now)
    assert outcomes[0]["archived"] is True  # archive still happens
    assert outcomes[0]["delivery_state"] == "CATCH_UP_REJECTED"

    from ticket_delivery.delivery_store import TicketDeliveryStore
    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    assert store.get(outcomes[0]["logical_ticket_id"]) is None  # no ticket ever registered
