"""OD1014-FAST D5: the EURUSD v1.1.2 suspension is session-scoped (ASIAN_LONDON only); S1 and identities unchanged."""
from __future__ import annotations

from v1_tickets.authority import load_registry, logic_identity
from v1_tickets.scope_status import resolve_ticket_scope

ASW, V = "ST_ASIAN_SWEEP_5R_V1", "1.1.2"


def test_registry_record_is_scoped_to_asian_london():
    suspended = load_registry()[ASW]["candidate_versions"][V]["logic_suspended_scopes"]
    assert [(s["symbol"], s.get("session"), s["status"]) for s in suspended] == [
        ("EURUSD", "ASIAN_LONDON", "SUSPENDED")]


def test_eurusd_asian_london_stays_suspended_and_london_newyork_is_not():
    for direction in ("LONG", "SHORT"):
        assert resolve_ticket_scope(ASW, V, "EURUSD", "ASIAN_LONDON", direction)["scope_verification_status"] == \
            "SUSPENDED"
        ln = resolve_ticket_scope(ASW, V, "EURUSD", "LONDON_NEWYORK", direction)
        assert ln["scope_verification_status"] == "UNVERIFIED" and ln["scope_reason"] != "SUSPENDED"


def test_s1_and_identities_are_unchanged():
    assert resolve_ticket_scope(ASW, V, "GBPUSD", "ASIAN_LONDON", "LONG")["scope_verification_status"] == \
        "LOGIC_VERIFIED"
    assert logic_identity(ASW, V)["digest"] == "d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5"
    assert all("registry.yaml" not in str(logic_identity(sid, v)) for sid, v in (
        (ASW, V), (ASW, "1.1.3"), ("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0")))
