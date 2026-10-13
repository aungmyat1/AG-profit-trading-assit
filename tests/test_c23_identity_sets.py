"""AGP-C23: applying D8/D9 to strategies/registry.yaml cannot move any logic identity (registry is outside every
identity set), and each re-recorded / registered identity equals the identity computed from the tree."""
from v1_tickets.authority import ADAPTERS, CANDIDATE_CONTRACTS, CANDIDATE_ENGINE_FILES, load_registry, logic_identity

REGISTRY = "strategies/registry.yaml"


def test_registry_outside_every_identity_set():
    files = {c for c, _ in ADAPTERS.values()} | {f for _, fs in ADAPTERS.values() for f in fs}
    files |= set(CANDIDATE_CONTRACTS.values()) | {f for fs in CANDIDATE_ENGINE_FILES.values() for f in fs}
    assert REGISTRY not in files


def test_recorded_identities_match_tree():
    reg = load_registry()
    asw = reg["ST_ASIAN_SWEEP_5R_V1"]["candidate_versions"]
    ccfd = reg["ST_CRYPTO_CFD_SWEEP_RETEST_V1"]["candidate_versions"]["1.0.0"]
    for version in ("1.1.2", "1.1.3"):        # D9 adds 1.1.3; the S1 1.1.2 record is unchanged
        assert asw[version]["logic_verified_identity"] == logic_identity("ST_ASIAN_SWEEP_5R_V1", version)["digest"]
    assert ccfd["logic_verified_identity"] == logic_identity("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0")["digest"]  # D8
    assert ccfd["previous_logic_verified_identity"] != ccfd["logic_verified_identity"]
