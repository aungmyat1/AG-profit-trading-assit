"""Shared VT-day derivation is evidence-gated and never a host observation."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from demo_execution.server_day import derive_vt_server_day

REPO = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _evidence(root, changes=None, *, remove=None):
    record = json.loads((REPO / "config/symbol_metadata/host_captured/GBPUSD.json").read_text())
    record.update(changes or {})
    if remove:
        record.pop(remove, None)
    payload = {k: v for k, v in record.items() if k != "sha256"}
    record["sha256"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str,
    ).encode()).hexdigest()
    path = root / "config/symbol_metadata/host_captured/GBPUSD.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))
    return path


@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"])
@pytest.mark.parametrize("instant,day,offset", [
    (datetime(2026, 10, 31, 21, tzinfo=UTC), date(2026, 11, 1), 3),
    (datetime(2026, 11, 1, 21, 59, 59, tzinfo=UTC), date(2026, 11, 1), 2),
    (datetime(2026, 11, 1, 22, tzinfo=UTC), date(2026, 11, 2), 2),
])
def test_each_committed_symbol_uses_the_rule_not_a_fixed_captured_offset(symbol, instant, day, offset):
    result = derive_vt_server_day(instant, canonical_symbol=symbol)
    assert (result.status, result.reason_code, result.server_day, result.utc_offset_hours) == (
        "DERIVED_NOT_OBSERVED", "VT_SERVER_DAY_DERIVED", day, offset,
    )
    assert result.captured_at_utc is not None


@pytest.mark.parametrize("changes,remove,reason", [
    ({}, "server_utc_offset_rule", "VT_SERVER_DAY_RULE_NOT_EVIDENCED"),
    ({"server_utc_offset_rule": "FIXED_UTC_PLUS_3"}, None, "VT_SERVER_DAY_RULE_NOT_EVIDENCED"),
    ({"server": "Other-Demo"}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
    ({"schema": "AG_HOST_SYMBOL_METADATA_V1"}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
    ({"canonical_symbol": "EURUSD"}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
    ({"server_utc_offset_hours": 2}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
    ({"server_utc_offset_hours": True}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
    ({"captured_at_utc": "2026-09-30T08:37:26"}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
    ({"captured_at_utc": "invalid"}, None, "VT_SERVER_DAY_METADATA_NOT_EVIDENCED"),
])
def test_bad_evidence_blocks_without_a_day_or_offset(tmp_path, changes, remove, reason):
    _evidence(tmp_path, changes, remove=remove)
    result = derive_vt_server_day(datetime(2026, 11, 1, 22, tzinfo=UTC),
                                  canonical_symbol="GBPUSD", metadata_root=tmp_path)
    assert (result.status, result.reason_code) == ("BLOCKED", reason)
    assert result.server_day is None and result.utc_offset_hours is None


@pytest.mark.parametrize("contents", [None, "not json", "[]", "{}"])
def test_missing_or_malformed_metadata_is_blocked(tmp_path, contents):
    if contents is not None:
        path = _evidence(tmp_path)
        path.write_text(contents)
    result = derive_vt_server_day(datetime(2026, 11, 1, 22, tzinfo=UTC),
                                  canonical_symbol="GBPUSD", metadata_root=tmp_path)
    assert (result.status, result.reason_code, result.server_day) == (
        "BLOCKED", "VT_SERVER_DAY_METADATA_NOT_EVIDENCED", None,
    )


def test_tampered_metadata_does_not_supply_a_rule(tmp_path):
    path = _evidence(tmp_path)
    record = json.loads(path.read_text())
    record["server_utc_offset_hours"] = 2  # Deliberately do not re-sign.
    path.write_text(json.dumps(record))
    result = derive_vt_server_day(datetime(2026, 11, 1, 22, tzinfo=UTC),
                                  canonical_symbol="GBPUSD", metadata_root=tmp_path)
    assert result.status == "BLOCKED" and result.server_day is None


@pytest.mark.parametrize("instant", [None, datetime(2026, 11, 1, 22)])
def test_unaware_or_missing_instant_is_blocked(instant):
    result = derive_vt_server_day(instant, canonical_symbol="GBPUSD")
    assert (result.status, result.reason_code) == ("BLOCKED", "VT_SERVER_DAY_TIME_INVALID")


def test_default_evidence_is_independent_of_cwd_and_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path))
    result = derive_vt_server_day(datetime(2026, 11, 1, 22, tzinfo=UTC), canonical_symbol="GBPUSD")
    assert result.server_day == date(2026, 11, 2)
    assert result.utc_offset_hours == 2 and result.status == "DERIVED_NOT_OBSERVED"
