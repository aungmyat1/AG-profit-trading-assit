"""READY requires an owner decision record bound to this version, contract, symbol and session."""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from v1_tickets import ready_authority as ra

SID = "ST_ASIAN_SWEEP_5R_V1"
VERSION = "7.4.2"
SYMBOL = "EURUSD"
SESSION = "ASIAN_LONDON"


def _inputs(tmp_path: Path, *, version: str = VERSION, contract_hash: str | None = None,
            symbols: list[str] | None = None, sessions: list[str] | None = None):
    config = tmp_path / "ready.yaml"
    config.write_text(f"strategies:\n  {SID}:\n    ready: 'ON'\n", encoding="utf-8")
    contract = tmp_path / "contract.yaml"
    contract.write_text("strategy_id: fixture\nversion: 7.4.2\n", encoding="utf-8")
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    record = {"decision_id": "FIXTURE-OWNER-READY-1", "status": "APPROVED", "strategy_id": SID,
              "version": version, "contract_sha256": contract_hash or digest,
              "symbol_scope": symbols or [SYMBOL], "session_scope": sessions or [SESSION], "date": "2026-10-10"}
    register = tmp_path / "owner-register.md"
    register.write_text("# Fixture owner register\n\n<!-- READY_AUTHORITY_RECORDS_START -->\n"
                        + yaml.safe_dump({"ready_authority_records": [record]}, sort_keys=False)
                        + "<!-- READY_AUTHORITY_RECORDS_END -->\n", encoding="utf-8")
    return str(config), str(contract), str(register), digest


def _allowed(tmp_path: Path, **overrides):
    config, contract, register, digest = _inputs(tmp_path, **overrides)
    return ra.ready_authority(SID, config, strategy_version=VERSION, contract_sha256=digest,
                              symbol=SYMBOL, session=SESSION, owner_register_path=register)


def test_on_without_owner_record_is_off(tmp_path):
    config, contract, register, digest = _inputs(tmp_path)
    Path(register).write_text("# Register has no structured READY record\n", encoding="utf-8")
    assert ra.ready_authority(SID, config, strategy_version=VERSION, contract_sha256=digest,
                              symbol=SYMBOL, session=SESSION, owner_register_path=register) == (
                                  False, ra.OWNER_DECISION_RECORD_MISSING)


def test_owner_record_version_must_match_runtime_version(tmp_path):
    assert _allowed(tmp_path, version="7.4.1") == (False, ra.OWNER_DECISION_VERSION_MISMATCH)


def test_owner_record_contract_hash_must_match_loaded_contract(tmp_path):
    assert _allowed(tmp_path, contract_hash="0" * 64) == (False, ra.OWNER_DECISION_CONTRACT_MISMATCH)


def test_owner_record_symbol_scope_must_include_ticket_symbol(tmp_path):
    assert _allowed(tmp_path, symbols=["GBPUSD"]) == (False, ra.OWNER_DECISION_SYMBOL_OUT_OF_SCOPE)


def test_owner_record_session_scope_must_include_ticket_session(tmp_path):
    assert _allowed(tmp_path, sessions=["LONDON_NEWYORK"]) == (False, ra.OWNER_DECISION_SESSION_OUT_OF_SCOPE)


def test_valid_fixture_owner_record_plus_on_allows_ready(tmp_path):
    assert _allowed(tmp_path) == (True, "READY_AUTHORITY_ON_OWNER_RECORD")
