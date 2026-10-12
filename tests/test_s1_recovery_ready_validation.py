"""Temporary S1 owner records validate READY without activating committed authority."""
import hashlib
from pathlib import Path

import pytest
import yaml

from v1_tickets import ready_authority as ra

STRATEGY = "ST_ASIAN_SWEEP_5R_V1"
CONTRACT = "4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf"


@pytest.fixture
def authority_files(tmp_path):
    config = tmp_path / "ready.yaml"
    config.write_text(yaml.safe_dump({"strategies": {STRATEGY: {"ready": "ON"}}}))
    record = {
        "decision_id": "TEST_ONLY_S1", "strategy_id": STRATEGY, "version": "1.1.2",
        "contract_sha256": CONTRACT, "status": "APPROVED", "date": "2026-10-12",
        "symbol_scope": ["GBPUSD"], "session_scope": ["ASIAN_LONDON"],
    }
    register = tmp_path / "register.md"

    def write_record(value):
        register.write_text("<!-- READY_AUTHORITY_RECORDS_START -->\n```yaml\n"
                            + yaml.safe_dump({"ready_authority_records": [value]})
                            + "```\n<!-- READY_AUTHORITY_RECORDS_END -->\n")

    write_record(record)
    return config, register, record, write_record


def check(files, symbol="GBPUSD", session="ASIAN_LONDON", contract=CONTRACT):
    config, register, _, _ = files
    return ra.ready_authority(STRATEGY, str(config), strategy_version="1.1.2",
                              contract_sha256=contract, symbol=symbol, session=session,
                              owner_register_path=str(register))


@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"])
@pytest.mark.parametrize("session", ["ASIAN_LONDON", "LONDON_NEWYORK"])
def test_temporary_owner_record_allows_only_s1(authority_files, symbol, session):
    allowed, reason = check(authority_files, symbol, session)
    assert allowed is (symbol == "GBPUSD" and session == "ASIAN_LONDON")
    if allowed:
        assert reason == "READY_AUTHORITY_ON_OWNER_RECORD"
    else:
        assert reason == (ra.OWNER_DECISION_SESSION_OUT_OF_SCOPE if symbol == "GBPUSD"
                          else ra.OWNER_DECISION_SYMBOL_OUT_OF_SCOPE)


def test_wrong_raw_contract_fails_closed(authority_files):
    assert check(authority_files, contract="0" * 64) == (False, ra.OWNER_DECISION_CONTRACT_MISMATCH)


def test_missing_owner_record_fails_closed(authority_files):
    authority_files[1].write_text("# No READY approval\n")
    assert check(authority_files) == (False, ra.OWNER_DECISION_RECORD_MISSING)


def test_ready_off_fails_closed_even_with_matching_owner_record(authority_files):
    authority_files[0].write_text(yaml.safe_dump({"strategies": {STRATEGY: {"ready": "OFF"}}}))
    assert check(authority_files) == (False, ra.READY_AUTHORITY_OFF)


@pytest.mark.parametrize("status", [[], {}, None, True])
def test_malformed_owner_status_is_refused_without_exception(authority_files, status):
    _, _, record, write_record = authority_files
    write_record({**record, "status": status})
    assert check(authority_files) == (False, ra.OWNER_DECISION_RECORD_INVALID)


def test_raw_frozen_contract_identity():
    root = Path(__file__).resolve().parents[1]
    assert hashlib.sha256((root / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml").read_bytes()).hexdigest() == CONTRACT
