"""Tests for execution/crypto_journal.py: atomic composite-key claiming, append-only
event recording, and the critical isolation property -- the SAME command_id literal used
under a different execution_domain/account_environment must never collide."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execution.crypto_journal import claim_command, is_claimed, read_events, record_command, record_event
from execution.crypto_models import ACCOUNT_ENVIRONMENT_DEMO, EXECUTION_DOMAIN_BINANCE_USDTM, CryptoTradeCommand


def test_claim_succeeds_once(tmp_path):
    base_dir = str(tmp_path)
    assert claim_command("BINANCE_USDTM", "DEMO", "cmd-1", base_dir) is True
    assert claim_command("BINANCE_USDTM", "DEMO", "cmd-1", base_dir) is False
    assert is_claimed("BINANCE_USDTM", "DEMO", "cmd-1", base_dir) is True


def test_same_command_id_different_domain_is_not_confused(tmp_path):
    """The exact isolation property the spec requires: a command_id claimed under
    FX-DEMO must be independently claimable under BINANCE_USDTM-DEMO."""
    base_dir = str(tmp_path)
    assert claim_command("MT5_FX", "DEMO", "SAME-ID", base_dir) is True
    assert claim_command("BINANCE_USDTM", "DEMO", "SAME-ID", base_dir) is True
    # Both claims independently succeeded -- re-claiming either specific triple now fails.
    assert claim_command("MT5_FX", "DEMO", "SAME-ID", base_dir) is False
    assert claim_command("BINANCE_USDTM", "DEMO", "SAME-ID", base_dir) is False


def test_same_command_id_different_environment_is_not_confused(tmp_path):
    base_dir = str(tmp_path)
    assert claim_command("BINANCE_USDTM", "DEMO", "SAME-ID", base_dir) is True
    assert claim_command("BINANCE_USDTM", "REAL", "SAME-ID", base_dir) is True


def test_record_and_read_events_roundtrip(tmp_path):
    base_dir = str(tmp_path)
    record_event("BINANCE_USDTM", "DEMO", "cmd-1", "CRYPTO_COMMAND_CLAIMED", base_dir=base_dir, symbol="BTCUSDT")
    events = read_events("BINANCE_USDTM", "DEMO", "cmd-1", base_dir)
    assert len(events) == 1
    assert events[0]["event"] == "CRYPTO_COMMAND_CLAIMED"
    assert events[0]["execution_domain"] == "BINANCE_USDTM"
    assert events[0]["account_environment"] == "DEMO"
    assert events[0]["symbol"] == "BTCUSDT"


def test_events_for_same_command_id_different_domain_are_isolated(tmp_path):
    base_dir = str(tmp_path)
    record_event("MT5_FX", "DEMO", "SAME-ID", "ORDER_EXECUTED", base_dir=base_dir)
    record_event("BINANCE_USDTM", "DEMO", "SAME-ID", "CRYPTO_COMMAND_CLAIMED", base_dir=base_dir)
    fx_events = read_events("MT5_FX", "DEMO", "SAME-ID", base_dir)
    crypto_events = read_events("BINANCE_USDTM", "DEMO", "SAME-ID", base_dir)
    assert len(fx_events) == 1 and fx_events[0]["event"] == "ORDER_EXECUTED"
    assert len(crypto_events) == 1 and crypto_events[0]["event"] == "CRYPTO_COMMAND_CLAIMED"


def test_record_event_refuses_credential_shaped_fields(tmp_path):
    base_dir = str(tmp_path)
    with pytest.raises(ValueError):
        record_event("BINANCE_USDTM", "DEMO", "cmd-1", "SOME_EVENT", base_dir=base_dir, api_key="not-a-real-key")
    with pytest.raises(ValueError):
        record_event("BINANCE_USDTM", "DEMO", "cmd-1", "SOME_EVENT", base_dir=base_dir, secret="also-fake")


def test_record_command_writes_expected_fields(tmp_path):
    base_dir = str(tmp_path)
    command = CryptoTradeCommand(
        command_id="cmd-99", occurrence_id="occ-99", account_environment=ACCOUNT_ENVIRONMENT_DEMO,
        symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01,
        client_order_id="AGX-fixture", created_at=datetime.now(timezone.utc),
    )
    record_command(command, validation_state="CLAIMED", base_dir=base_dir)
    events = read_events(EXECUTION_DOMAIN_BINANCE_USDTM, ACCOUNT_ENVIRONMENT_DEMO, "cmd-99", base_dir)
    assert len(events) == 1
    row = events[0]
    assert row["symbol"] == "BTCUSDT"
    assert row["side"] == "BUY"
    assert row["quantity"] == 0.01
    assert row["order_type"] == "MARKET"
    assert row["validation_state"] == "CLAIMED"
    assert row["exchange_order_id"] is None
    assert "ts" in row
