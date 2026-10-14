"""A': N-scope admission/authorization with S1 byte-identical. No broker, no order path."""
from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from demo_execution.authorization import load_standing_authorization
from demo_execution.scope import (
    ScopePolicyError,
    load_scope_policies,
    load_scope_policy,
    resolve_ticket_scope_policy,
    select_scope,
)

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)


def _root(tmp_path: Path) -> Path:
    """Isolated copy of the inputs the loader reads (paths must stay under the root)."""
    for rel in ("config", "strategies"):
        shutil.copytree(REPO / rel, tmp_path / rel)
    (tmp_path / "docs/governance").mkdir(parents=True)
    shutil.copy(REPO / "docs/governance/OWNER_DECISION_REGISTER.md", tmp_path / "docs/governance")
    return tmp_path


def _second_scope(root: Path, *, session="LONDON_NEWYORK", suffix=None) -> str:
    raw = yaml.safe_load((root / "config/demo_execution_s1.yaml").read_text())
    raw["scope"]["session"] = session
    if suffix:
        raw["account_login_suffix"] = suffix
    (root / "config/demo_execution_ln.yaml").write_text(yaml.safe_dump(raw))
    return "config/demo_execution_ln.yaml"


def _manifest(root: Path, configs) -> Path:
    path = root / "config/demo_execution_scopes.yaml"
    path.write_text(yaml.safe_dump({"schema": "AGP_C14_DEMO_SCOPES_V1", "scope_configs": list(configs)}))
    return path


def test_committed_manifest_is_exactly_s1_and_byte_identical():
    policies = load_scope_policies()
    assert policies == (load_scope_policy(),)
    s1 = load_scope_policy()
    ticket = {"strategy_id": s1.strategy_id, "strategy_version": s1.strategy_version, "symbol": "GBPUSD",
              "cycle": "ASIAN_LONDON"}
    assert resolve_ticket_scope_policy(ticket) == s1
    # A ticket outside every scope resolves to the first (S1) scope, whose checks report the mismatch.
    assert resolve_ticket_scope_policy({"symbol": "EURUSD", "cycle": "LONDON_NEWYORK"}) == s1


def test_explicit_single_config_keeps_the_original_path():
    cfg = REPO / "config/demo_execution_s1.yaml"
    assert resolve_ticket_scope_policy({"symbol": "XAUUSD"}, config_path=cfg) == load_scope_policy(cfg)


def test_two_scopes_select_by_exact_identity(tmp_path):
    root = _root(tmp_path)
    _manifest(root, ["config/demo_execution_s1.yaml", _second_scope(root)])
    s1, ln = load_scope_policies(repo_root=root)
    assert (s1.session, ln.session) == ("ASIAN_LONDON", "LONDON_NEWYORK")
    pick = select_scope((s1, ln), strategy_id=ln.strategy_id, strategy_version=ln.strategy_version,
                        symbol="GBPUSD", session="LONDON_NEWYORK")
    assert pick is ln
    assert select_scope((s1, ln), strategy_id="X", strategy_version="0", symbol="GBPUSD",
                        session="LONDON_NEWYORK") is s1


def test_duplicate_scope_fails_closed(tmp_path):
    root = _root(tmp_path)
    _manifest(root, ["config/demo_execution_s1.yaml", _second_scope(root, session="ASIAN_LONDON")])
    with pytest.raises(ScopePolicyError) as exc:
        load_scope_policies(repo_root=root)
    assert exc.value.reason_code == "EXECUTION_SCOPE_DUPLICATE"


def test_scopes_on_different_accounts_fail_closed(tmp_path):
    root = _root(tmp_path)
    _manifest(root, ["config/demo_execution_s1.yaml", _second_scope(root, suffix="123")])
    with pytest.raises(ScopePolicyError) as exc:
        load_scope_policies(repo_root=root)
    assert exc.value.reason_code == "ACCOUNT_IDENTITY_CONFLICT"


@pytest.mark.parametrize("manifest", [{"schema": "X", "scope_configs": ["config/demo_execution_s1.yaml"]},
                                      {"schema": "AGP_C14_DEMO_SCOPES_V1", "scope_configs": []}])
def test_malformed_manifest_fails_closed(tmp_path, manifest):
    root = _root(tmp_path)
    (root / "config/demo_execution_scopes.yaml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(ScopePolicyError):
        load_scope_policies(repo_root=root)


def _record(scope, direction, **updates):
    record = {"schema": "AGP_STANDING_DEMO_AUTHORIZATION_V1", "strategy": scope.strategy_id,
              "version": scope.strategy_version, "symbol": scope.symbol, "session": scope.session,
              "branch": scope.setup_branch, "direction": direction, "logic_identity": scope.logic_identity,
              "granted_at": (NOW - timedelta(days=1)).isoformat(), "revoked_at": None,
              "decision_id": "TEST_ONLY_NOT_OWNER_AUTHORITY", "emergency_stop": False}
    record.update(updates)
    return record


def _auth(tmp_path, payload):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(payload))
    return path


def test_single_v1_record_unchanged_and_container_equivalent(tmp_path):
    s1 = load_scope_policy()
    ticket = {"direction": "LONG"}
    single = load_standing_authorization(s1, ticket, path=_auth(tmp_path, _record(s1, "LONG")), now_utc=NOW)
    container = load_standing_authorization(s1, ticket, now_utc=NOW, path=_auth(
        tmp_path, {"schema": "AGP_STANDING_DEMO_AUTHORIZATIONS_V1",
                   "records": [_record(s1, "SHORT"), _record(s1, "LONG")]}))
    assert single.authorized and container == single


def test_container_without_or_with_ambiguous_match_fails_closed(tmp_path):
    s1 = load_scope_policy()
    other = dataclasses.replace(s1, session="LONDON_NEWYORK")
    none = {"schema": "AGP_STANDING_DEMO_AUTHORIZATIONS_V1", "records": [_record(other, "LONG")]}
    dup = {"schema": "AGP_STANDING_DEMO_AUTHORIZATIONS_V1", "records": [_record(s1, "LONG")] * 2}
    extra = {"schema": "AGP_STANDING_DEMO_AUTHORIZATIONS_V1", "records": [], "grant": True}
    for payload, reason in ((none, "AUTHORIZATION_SCOPE_MISMATCH"), (dup, "AUTHORIZATION_INVALID"),
                            (extra, "AUTHORIZATION_INVALID")):
        result = load_standing_authorization(s1, {"direction": "LONG"}, path=_auth(tmp_path, payload), now_utc=NOW)
        assert (result.authorized, result.reason_code) == (False, reason)


def test_container_record_still_fully_validated(tmp_path):
    s1 = load_scope_policy()
    payload = {"schema": "AGP_STANDING_DEMO_AUTHORIZATIONS_V1",
               "records": [_record(s1, "LONG", emergency_stop=True)]}
    result = load_standing_authorization(s1, {"direction": "LONG"}, path=_auth(tmp_path, payload), now_utc=NOW)
    assert result.reason_code == "EMERGENCY_STOP_ENGAGED"
