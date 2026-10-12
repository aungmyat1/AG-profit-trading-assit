"""The reserved S1 magic must never equal a magic already in use on the host.

The reserved magic is not a literal here either: it is read from the registered strategy
contract through the scope loader, exactly as the runtime reads it. What is pinned literally
is the host's own list of magics in use, so a future contract change that collides with one
of them fails closed instead of sharing a magic with another order source on the account.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from _demo_execution_boundary_fixtures import (  # noqa: E402
    BROKER_MAP,
    HOST_MAGIC_REGISTRY,
    NOW,
    TICKET_ID,
    boundary,
    fixture_scope,
)

from demo_execution.guarded_adapter import GuardedCanonicalAdapter
from demo_execution.host_magics import (
    HOST_MAGIC_REGISTRY_PATH,
    HostMagicRegistryError,
    load_host_magics,
    reserved_magic_conflict,
)
from demo_execution.scope import ScopePolicyError, load_scope_policy

REPO = Path(__file__).resolve().parents[1]

# Magics in use on the VT Markets DEMO host, owner-stated 2026-10-11:
#   0          unattributed manual / local MT5 API orders (reason EXPERT, source 127.0.0.1)
#   102233     ContinuationBreakout_EA (loaded now, PROGRAM_FILES terminal, EURUSD M15)
#   18152023   asian_session_ea
#   550055     SMC_Sniper_EA
#   20260713   SMC_LSS_v1_EA
#   1120250714 MT5_EA_1BullBear_ICT_SMC
#   112201     Crypto_VBO_EA (BTC/ETH stop orders, canceled 2026-10-11)
#   112202     Crypto_VBO_EA (BTC/ETH stop orders, canceled 2026-10-11)
HOST_MAGICS_IN_USE = (0, 102233, 18152023, 550055, 20260713, 1120250714, 112201, 112202)


def _registry(tmp_path: Path, magics, *, schema: str = "AGP_C14_HOST_MAGIC_REGISTRY_V1",
              observed_at: str = "2026-10-11", with_source: bool = True) -> Path:
    entries = [{"magic": magic, "source": "TEST ONLY"} if with_source else {"magic": magic}
               for magic in magics]
    path = tmp_path / "host_magics.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"schema": schema, "observed_at_utc": observed_at,
                                    "magics_in_use_on_host": entries}, sort_keys=False),
                    encoding="utf-8")
    return path


def test_the_committed_registry_lists_exactly_the_magics_in_use_on_the_host():
    assert load_host_magics() == HOST_MAGICS_IN_USE
    assert HOST_MAGIC_REGISTRY_PATH == HOST_MAGIC_REGISTRY
    committed = yaml.safe_load(HOST_MAGIC_REGISTRY.read_text(encoding="utf-8"))
    assert committed["schema"] == "AGP_C14_HOST_MAGIC_REGISTRY_V1"
    assert [entry["magic"] for entry in committed["magics_in_use_on_host"]] == list(HOST_MAGICS_IN_USE)
    # Every listed magic cites where it was observed; magic 0 is always listed.
    assert all(str(entry["source"]).strip() for entry in committed["magics_in_use_on_host"])
    assert 0 in HOST_MAGICS_IN_USE


def test_the_reserved_s1_magic_is_not_any_magic_in_use_on_the_host():
    scope = load_scope_policy()
    registry = yaml.safe_load((REPO / "strategies" / "registry.yaml").read_text(encoding="utf-8"))
    candidate = registry["strategies"][scope.strategy_id]["candidate_versions"][scope.strategy_version]
    contract = yaml.safe_load((REPO / candidate["config_source"]).read_text(encoding="utf-8"))
    assert scope.magic_number == contract["magic_number"]          # resolved, never a literal
    assert scope.magic_number not in HOST_MAGICS_IN_USE
    assert reserved_magic_conflict(scope.magic_number, HOST_MAGICS_IN_USE) is None
    assert scope.host_magic_registry_path == HOST_MAGIC_REGISTRY


def test_crypto_vbo_magics_are_inventory_only_and_do_not_authorize_execution(tmp_path):
    fixture = boundary(tmp_path, enabled=False)
    assert {112201, 112202}.issubset(load_host_magics())
    assert fixture["scope"].account_login_suffix == "999"
    assert fixture["scope"].magic_number not in (112201, 112202)
    decision = fixture["guard"].authorize_order_check(
        authority=fixture["authority"], ticket=fixture["ticket"], market=fixture["market"],
        risk_snapshot=fixture["risk_snapshot"], now_utc=NOW,
    )
    assert (decision.admitted, decision.reason_code) == (False, "EXECUTION_DISABLED")
    assert fixture["reader"].calls == 0


@pytest.mark.parametrize("magic", [magic for magic in HOST_MAGICS_IN_USE if magic != 0])
def test_reserved_magic_conflict_names_a_collision_with_any_host_magic(magic):
    assert reserved_magic_conflict(magic, HOST_MAGICS_IN_USE) == "STRATEGY_MAGIC_COLLIDES_WITH_HOST"


def test_magic_zero_is_refused_as_a_reserved_magic_before_any_collision_is_considered():
    # 0 is in use on the host (unattributed manual/API orders) and is also the MT5 "no magic"
    # default, so it is refused as unusable rather than merely reported as a collision.
    assert reserved_magic_conflict(0, HOST_MAGICS_IN_USE) == "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"


@pytest.mark.parametrize(("magic", "reason"), [
    (0, "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"),
    (-1, "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"),
    (None, "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"),
    (True, "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"),
    ("777001", "STRATEGY_MAGIC_NUMBER_UNAVAILABLE"),
    (777001, None),
])
def test_a_reserved_magic_must_be_a_positive_integer(magic, reason):
    assert reserved_magic_conflict(magic, HOST_MAGICS_IN_USE) == reason


def test_scope_loading_fails_closed_when_the_reserved_magic_collides_with_a_host_magic(tmp_path):
    clean = fixture_scope(tmp_path)
    colliding = _registry(tmp_path, [clean.magic_number, 0])
    with pytest.raises(ScopePolicyError) as raised:
        fixture_scope(tmp_path / "colliding", host_magic_registry_path=colliding)
    assert raised.value.reason_code == "STRATEGY_MAGIC_COLLIDES_WITH_HOST"

    zero = _registry(tmp_path / "zero", [0])
    scope_with_zero_only = fixture_scope(tmp_path / "zero-ok", host_magic_registry_path=zero)
    assert scope_with_zero_only.magic_number == clean.magic_number


def test_scope_loading_fails_closed_when_the_host_magic_registry_is_unusable(tmp_path):
    with pytest.raises(ScopePolicyError) as missing:
        fixture_scope(tmp_path / "missing", host_magic_registry_path=tmp_path / "absent.yaml")
    assert missing.value.reason_code == "HOST_MAGIC_REGISTRY_UNAVAILABLE"

    for index, (magics, kwargs, reason) in enumerate((
        ([], {}, "HOST_MAGIC_REGISTRY_INVALID"),
        ([777001], {"schema": "SOMETHING_ELSE"}, "HOST_MAGIC_REGISTRY_INVALID"),
        ([777001], {"observed_at": ""}, "HOST_MAGIC_REGISTRY_INVALID"),
        ([777001, 777001], {}, "HOST_MAGIC_REGISTRY_INVALID"),
        ([102233], {}, "HOST_MAGIC_REGISTRY_INVALID"),            # magic 0 must always be listed
        ([0, "102233"], {}, "HOST_MAGIC_REGISTRY_INVALID"),
        ([0, -5], {}, "HOST_MAGIC_REGISTRY_INVALID"),
        ([0, 102233], {"with_source": False}, "HOST_MAGIC_REGISTRY_INVALID"),
    )):
        path = _registry(tmp_path / f"case-{index}", magics, **kwargs)
        with pytest.raises(ScopePolicyError) as raised:
            fixture_scope(tmp_path / f"scope-{index}", host_magic_registry_path=path)
        assert raised.value.reason_code == reason


def test_a_malformed_registry_file_is_refused_by_the_loader(tmp_path):
    path = tmp_path / "not-yaml-mapping.yaml"
    path.write_text("- 0\n- 102233\n", encoding="utf-8")
    with pytest.raises(HostMagicRegistryError) as raised:
        load_host_magics(path)
    assert raised.value.reason_code == "HOST_MAGIC_REGISTRY_INVALID"


def test_the_guard_refuses_a_call_when_the_reserved_magic_collides_with_the_host(tmp_path):
    """The guard re-loads the scope itself, so a collision blocks the call even though the
    caller's own fixture scope resolved cleanly a moment earlier."""
    fixture = boundary(tmp_path / "clean")
    root = fixture["tmp_path"]
    collided = _registry(tmp_path / "collided", [fixture["scope"].magic_number, 0])
    guard = GuardedCanonicalAdapter(
        ticket_store=fixture["store"],
        live_account_reader=fixture["reader"],
        scope_config_path=str(root / "demo_execution_s1.yaml"),
        repo_root=REPO,
        registry_path=str(root / "registry.yaml"),
        broker_symbol_map_path=BROKER_MAP,
        ready_authority_config_path=str(root / "ready_authority.yaml"),
        owner_decision_register_path=str(root / "OWNER_DECISION_REGISTER.md"),
        host_magic_registry_path=collided,
        authorization_path=str(fixture["auth_path"]),
    )
    decision = guard.authorize_order_check(
        authority=fixture["authority"], ticket=fixture["ticket"], market=fixture["market"],
        risk_snapshot=fixture["risk_snapshot"], now_utc=NOW,
    )
    assert decision.admitted is False
    assert decision.reason_code == "STRATEGY_MAGIC_COLLIDES_WITH_HOST"
    assert fixture["reader"].calls == 0
    assert [row["outcome_kind"] for row in fixture["store"].outcomes(TICKET_ID)
            if row["outcome_kind"] != "S1_PRE_ORDER_TELEGRAM_NOTICE"] \
        == ["DEMO_OWNER_ORDER_CONFIRM"]          # no lifecycle evidence was written
