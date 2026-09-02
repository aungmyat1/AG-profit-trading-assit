"""Tests for execution/crypto_models.py: CryptoTradeCommand shape/validation and the
proposal -> command boundary function build_crypto_trade_command()."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from btc_sweep_research.proposal import (
    AUTHORITY_RESEARCH_ONLY,
    BTCSweepResearchProposal,
)
from execution.crypto_models import (
    ACCOUNT_ENVIRONMENT_DEMO,
    BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED,
    BLOCKED_INVALID_QUANTITY,
    BLOCKED_NOT_AUTHORIZED,
    BLOCKED_PROPOSAL_NOT_RESEARCH_DOMAIN,
    EXECUTION_DOMAIN_BINANCE_USDTM,
    CryptoTradeCommand,
    InvalidCryptoTradeCommand,
    STATUS_BUILT,
    STATUS_REJECTED,
    build_crypto_trade_command,
    validate_account_environment,
)


def _make_command(**overrides):
    fields = dict(
        command_id="cmd-1", occurrence_id="occ-1", account_environment=ACCOUNT_ENVIRONMENT_DEMO,
        symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01,
        client_order_id="AGX-abc123", created_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    return CryptoTradeCommand(**fields)


def _make_proposal(**overrides) -> BTCSweepResearchProposal:
    fields = dict(
        strategy="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="2.0.0", authority=AUTHORITY_RESEARCH_ONLY,
        exchange="BINANCE_USDT_M_PERP", instrument="BTCUSDT", direction="LONG",
        reference_day=date(2026, 9, 1), reference_high=42000.0, reference_low=40700.0,
        sweep={}, confirmation={}, entry=41000.0, stop=40700.0, target={"tp1": 41500.0, "tp2": 42000.0},
        RR=1.6, estimated_fees=1.0, funding_assumption={}, data_timestamp=datetime.now(timezone.utc), expiry=None,
        occurrence_id="BTC-OCC-1",
    )
    fields.update(overrides)
    return BTCSweepResearchProposal(**fields)


# --- account_environment: two independent failure shapes -------------------------------

def test_omitting_account_environment_raises_type_error_from_constructor():
    with pytest.raises(TypeError):
        CryptoTradeCommand(
            command_id="cmd-1", occurrence_id="occ-1",  # account_environment omitted
            symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01,
            client_order_id="AGX-abc123", created_at=datetime.now(timezone.utc),
        )


def test_explicit_empty_account_environment_is_not_a_constructor_type_error():
    """An explicit empty string IS a valid str, so the constructor accepts it -- this is
    exactly the caller-from-external-input case the spec calls out. Validation must be
    the caller's separate, explicit step (validate_account_environment)."""
    command = _make_command(account_environment="")
    assert command.account_environment == ""


def test_validate_account_environment_rejects_empty_string():
    assert validate_account_environment("") == BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED


def test_validate_account_environment_rejects_unknown_value():
    assert validate_account_environment("PRODUCTION") == BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED


def test_validate_account_environment_accepts_demo_and_real():
    assert validate_account_environment("DEMO") is None
    assert validate_account_environment("REAL") is None


# --- CryptoTradeCommand structural validation -------------------------------------------

def test_execution_domain_defaults_correctly_and_rejects_override():
    assert _make_command().execution_domain == EXECUTION_DOMAIN_BINANCE_USDTM
    with pytest.raises(InvalidCryptoTradeCommand):
        _make_command(execution_domain="MT5_FX")


def test_invalid_side_rejected():
    with pytest.raises(InvalidCryptoTradeCommand):
        _make_command(side="LONG")


def test_invalid_order_type_rejected():
    with pytest.raises(InvalidCryptoTradeCommand):
        _make_command(order_type="STOP")


def test_limit_order_requires_price():
    with pytest.raises(InvalidCryptoTradeCommand):
        _make_command(order_type="LIMIT", price=None)
    command = _make_command(order_type="LIMIT", price=41000.0)
    assert command.price == 41000.0


def test_non_positive_quantity_rejected():
    with pytest.raises(InvalidCryptoTradeCommand):
        _make_command(quantity=0)
    with pytest.raises(InvalidCryptoTradeCommand):
        _make_command(quantity=-0.01)


def test_command_is_frozen():
    command = _make_command()
    with pytest.raises(Exception):
        command.quantity = 1.0  # type: ignore[misc]


# --- build_crypto_trade_command(): proposal -> command boundary ------------------------

def test_authorized_omitted_is_type_error():
    proposal = _make_proposal()
    with pytest.raises(TypeError):
        build_crypto_trade_command(  # type: ignore[call-arg]
            proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO,
            command_id="cmd-1", client_order_id="AGX-1", quantity=0.01,
        )


def test_authorized_false_is_rejected():
    proposal = _make_proposal()
    result = build_crypto_trade_command(
        proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO, authorized=False,
        command_id="cmd-1", client_order_id="AGX-1", quantity=0.01,
    )
    assert result.status == STATUS_REJECTED
    assert result.reason_code == BLOCKED_NOT_AUTHORIZED
    assert result.command is None


def test_qualified_proposal_alone_never_authorizes_a_command():
    """A proposal in ENTRY_READY / strategy_qualified=True shape (the fixture below IS
    that shape by construction) must never, by itself, be sufficient -- only an explicit,
    externally-supplied authorized=True does anything."""
    proposal = _make_proposal()
    unauthorized = build_crypto_trade_command(
        proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO, authorized=False,
        command_id="cmd-1", client_order_id="AGX-1", quantity=0.01,
    )
    assert unauthorized.status == STATUS_REJECTED
    authorized = build_crypto_trade_command(
        proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO, authorized=True,
        command_id="cmd-1", client_order_id="AGX-1", quantity=0.01,
    )
    assert authorized.status == STATUS_BUILT


def test_invalid_account_environment_is_rejected_even_when_authorized():
    proposal = _make_proposal()
    result = build_crypto_trade_command(
        proposal, account_environment="", authorized=True,
        command_id="cmd-1", client_order_id="AGX-1", quantity=0.01,
    )
    assert result.status == STATUS_REJECTED
    assert result.reason_code == BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED


def test_wrong_execution_domain_proposal_rejected():
    proposal = _make_proposal(execution_domain="SOMETHING_ELSE")
    result = build_crypto_trade_command(
        proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO, authorized=True,
        command_id="cmd-1", client_order_id="AGX-1", quantity=0.01,
    )
    assert result.status == STATUS_REJECTED
    assert result.reason_code == BLOCKED_PROPOSAL_NOT_RESEARCH_DOMAIN


def test_non_positive_quantity_rejected_at_boundary():
    proposal = _make_proposal()
    result = build_crypto_trade_command(
        proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO, authorized=True,
        command_id="cmd-1", client_order_id="AGX-1", quantity=0.0,
    )
    assert result.status == STATUS_REJECTED
    assert result.reason_code == BLOCKED_INVALID_QUANTITY


def test_successful_build_carries_proposal_fields_through():
    proposal = _make_proposal(direction="SHORT", stop=42151.0, target={"tp1": 41350.0, "tp2": 40700.0})
    result = build_crypto_trade_command(
        proposal, account_environment=ACCOUNT_ENVIRONMENT_DEMO, authorized=True,
        command_id="cmd-42", client_order_id="AGX-42", quantity=0.02,
    )
    assert result.status == STATUS_BUILT
    command = result.command
    assert command.command_id == "cmd-42"
    assert command.occurrence_id == proposal.occurrence_id
    assert command.symbol == "BTCUSDT"
    assert command.side == "SELL"
    assert command.stop_price == 42151.0
    assert command.take_profit_price == 41350.0
    assert command.quantity == 0.02
    assert command.execution_domain == EXECUTION_DOMAIN_BINANCE_USDTM
