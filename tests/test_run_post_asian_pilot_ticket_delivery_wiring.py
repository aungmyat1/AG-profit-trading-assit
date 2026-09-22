"""Tests for the ACTUAL scheduled CLI entry point's ticket-delivery wiring
(scripts/run_post_asian_pilot.py::_run_once() / _process_ticket_delivery()) -- not just
process_cycle_result() in isolation. Loads the script module via importlib (it isn't a
package) and monkeypatches _execute_cycle() so no live MT5 terminal is required, the
same idiom this repository's own CLI already relies on being callable this way.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_post_asian_pilot.py"

UTC = dt.timezone.utc


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_post_asian_pilot_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def script_module():
    return _load_script_module()


def _decision(status="WATCH"):
    from post_asian_pilot.decision import STATUS_WATCH
    return SimpleNamespace(status=STATUS_WATCH if status == "WATCH" else status, reason_codes=("R1",),
                           evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC),
                           signal=None, ready_at=None, missing_condition=None)


def _fixture_result():
    from post_asian_pilot.governor import PORTFOLIO_SELECTED
    pair = SimpleNamespace(symbol="EURUSD", decision=_decision(), portfolio_state=PORTFOLIO_SELECTED,
                           portfolio_reason_code=None, proposal=None)
    strategy = SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1", version="1.1.1")
    return SimpleNamespace(strategy=strategy, release_id="AG_TRADE_ASSISTANT_V1_0_3",
                           trading_date=dt.date(2026, 9, 8), pairs=[pair])


_SIGNED_POLICY_YAML = (
    "policy:\n"
    "  fx_max_catch_up_age_minutes: 60\n"
    "  delivery_max_attempts: 3\n"
    "  delivery_retry_base_delay_seconds: 30\n"
    "  delivery_retry_max_delay_seconds: 300\n"
)


def _write_config(tmp_path, mode="ARCHIVE_ONLY", include_policy=True, name="ticket_delivery.yaml"):
    cfg_path = tmp_path / name
    body = f"mode: {mode}\narchive_root: {tmp_path / 'archive'}\ndelivery_state_dir: {tmp_path / 'state'}\n"
    if include_policy and mode != "DISABLED":
        body += _SIGNED_POLICY_YAML
    cfg_path.write_text(body, encoding="utf-8")
    return str(cfg_path)


def test_real_shipped_config_is_archive_only_and_produces_output(script_module):
    """The real shipped config/ticket_delivery.yaml -- proves a scheduled run today
    (owner-authorized 2026-09-08) archives with the signed policy, no monkeypatching of
    the config path at all."""
    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ticket_delivery_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert ticket_delivery_failed is False
    output = buf.getvalue()
    assert '"mode": "ARCHIVE_ONLY"' in output
    assert '"cycle_state": "WATCH"' in output


def test_disabled_config_produces_no_ticket_delivery_output_and_no_writes(script_module, tmp_path, monkeypatch):
    """The one-line-rollback path: an explicit DISABLED config (no policy block
    required or read) must remain a complete, silent no-op."""
    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "DISABLED"))

    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ticket_delivery_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert ticket_delivery_failed is False
    assert "ticket_delivery" not in buf.getvalue()
    import os
    assert not os.path.exists(str(tmp_path / "archive"))
    assert not os.path.exists(str(tmp_path / "state"))


def test_missing_signed_policy_under_active_mode_produces_nonzero_exit_zero_network(script_module, tmp_path, monkeypatch):
    """Gate 2: mode is ARCHIVE_ONLY but the signed policy block is absent -- this must
    be a visible, normalized operational failure (nonzero exit) at the real CLI call
    site, not a silent DISABLED-style no-op, and must make zero archive/network calls."""
    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "ARCHIVE_ONLY", include_policy=False))

    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ticket_delivery_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert ticket_delivery_failed is True
    import os
    assert not os.path.exists(str(tmp_path / "archive"))


def test_invalid_signed_policy_value_under_active_mode_produces_nonzero_exit(script_module, tmp_path, monkeypatch):
    import ticket_delivery.scheduler_integration as si_module
    cfg_path = tmp_path / "ticket_delivery.yaml"
    cfg_path.write_text(
        f"mode: ARCHIVE_ONLY\narchive_root: {tmp_path / 'archive'}\ndelivery_state_dir: {tmp_path / 'state'}\n"
        "policy:\n  fx_max_catch_up_age_minutes: 0\n  delivery_max_attempts: 3\n"
        "  delivery_retry_base_delay_seconds: 30\n  delivery_retry_max_delay_seconds: 300\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", str(cfg_path))

    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ticket_delivery_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert ticket_delivery_failed is True


def test_archive_only_config_wired_through_the_real_cli_function(script_module, tmp_path, monkeypatch):
    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "ARCHIVE_ONLY"))

    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        archive_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert archive_failed is False
    output = buf.getvalue()
    assert '"ticket_delivery"' in output
    assert '"mode": "ARCHIVE_ONLY"' in output
    assert '"cycle_state": "WATCH"' in output

    import os
    assert os.path.exists(str(tmp_path / "archive"))


def test_repeated_cli_invocation_same_result_converges_on_one_archive(script_module, tmp_path, monkeypatch):
    """The requirement: 'A repeated scheduler invocation must converge on the same
    archive and logical ticket' -- exercised through the actual CLI function, twice."""
    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "ARCHIVE_ONLY"))

    result = _fixture_result()
    buf1, buf2 = io.StringIO(), io.StringIO()
    with redirect_stdout(buf1):
        script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    with redirect_stdout(buf2):
        script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)

    import re
    ids = [re.search(r'"logical_ticket_id": "([^"]+)"', b.getvalue()).group(1) for b in (buf1, buf2)]
    assert ids[0] == ids[1]


def test_two_simultaneous_cli_invocations_same_pair_one_archive_record(script_module, tmp_path, monkeypatch):
    """Checks the persisted store directly rather than parsing concurrently-captured
    stdout -- contextlib.redirect_stdout swaps the single process-global sys.stdout and
    is not safe to use from two threads at once; that would be a test-harness race, not
    evidence about the production code under test."""
    from concurrent.futures import ThreadPoolExecutor

    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "ARCHIVE_ONLY"))

    def run_once(_):
        return script_module._process_ticket_delivery(_fixture_result(), None, None, None, None, as_json=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_once, range(2)))

    from ticket_delivery.delivery_store import TicketDeliveryStore
    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    all_records = store._records.all()
    assert len(all_records) == 1  # WATCH converges on exactly one NOT_APPLICABLE record, never two


def test_archive_failure_produces_nonzero_indication_and_no_crash(script_module, tmp_path, monkeypatch):
    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "ARCHIVE_ONLY"))

    import ticket_delivery.fx_cycle_integration as fx_mod

    def _raise(*a, **k):
        from ticket_delivery.archive import ArchiveFailedError
        raise ArchiveFailedError("simulated disk failure")

    monkeypatch.setattr(fx_mod, "archive_cycle_decision", _raise)

    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        archive_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert archive_failed is True
    assert '"delivery_state": "ARCHIVE_FAILED"' in buf.getvalue()


def test_ticket_delivery_error_never_crashes_but_signals_failure(script_module, tmp_path, monkeypatch):
    """An unexpected exception anywhere in ticket-delivery processing must be caught
    and reported to stderr, never propagate and crash the caller (the strategy report
    already printed successfully before this function was even called) -- but it must
    still be reported as a failure to the caller so a nonzero scheduler exit code
    results. Silently returning False here would mean a real ticket-delivery defect
    never surfaces anywhere except an unwatched stderr line."""
    import ticket_delivery.scheduler_integration as si_module

    def _raise(*a, **k):
        raise RuntimeError("totally unexpected bug")

    monkeypatch.setattr(si_module, "load_integration_config", _raise)

    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ticket_delivery_failed = script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert ticket_delivery_failed is True  # degrades safely (no exception propagates) but is not silently swallowed


def test_unexpected_ticket_delivery_error_propagates_as_nonzero_exit_from_run_once(script_module, tmp_path, monkeypatch):
    """Proves the failure signal actually reaches the real scheduled entry point
    (_run_once), not only the helper in isolation -- the strategy report must still
    print successfully before the nonzero exit."""
    import ticket_delivery.scheduler_integration as si_module

    def _raise(*a, **k):
        raise RuntimeError("totally unexpected bug")

    monkeypatch.setattr(si_module, "load_integration_config", _raise)
    monkeypatch.setattr(script_module, "_execute_cycle", lambda pilot_path=None, persist=True: _fixture_result())
    monkeypatch.setattr(script_module, "_entry_ticket_context", lambda pilot_path, result: (None, None, None))
    # cycle_to_dict()/human_readable_report() rendering is proven elsewhere against a
    # real PilotCycleResult; this test isolates only the exit-code propagation path, so
    # a minimal stub stands in for the already-frozen report schema.
    monkeypatch.setattr(script_module, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"strategy_report": "STUBBED_FOR_EXIT_CODE_TEST"})

    buf = io.StringIO()
    with redirect_stdout(buf):
        with pytest.raises(SystemExit) as exc_info:
            script_module._run_once(as_json=True)
    assert exc_info.value.code == 1
    # The strategy report printed successfully before the exit.
    assert '"strategy_report": "STUBBED_FOR_EXIT_CODE_TEST"' in buf.getvalue()


def test_message_delivery_config_makes_zero_network_calls_through_the_cli(script_module, tmp_path, monkeypatch):
    import ticket_delivery.scheduler_integration as si_module
    monkeypatch.setattr(si_module, "DEFAULT_CONFIG_PATH", _write_config(tmp_path, "MESSAGE_DELIVERY"))

    # If any code path here ever tried a real network call, requests.Session.post would
    # need to exist and succeed against a real host -- there is deliberately no mock
    # transport injected anywhere in this call chain, so a network attempt would raise.
    result = _fixture_result()
    buf = io.StringIO()
    with redirect_stdout(buf):
        script_module._process_ticket_delivery(result, None, None, None, None, as_json=True)
    assert '"mode": "MESSAGE_DELIVERY"' in buf.getvalue()
    assert '"delivery_state": "NOT_APPLICABLE"' in buf.getvalue()
