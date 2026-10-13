"""AGP-C18-R2: exact per-scope verification fields on the canonical ticket (additive to
AG_CANONICAL_TICKET_V1). Scope status comes from the exact strategy version, symbol, session and
(CCFD) direction -- never from family-level status -- and every route is REPORT_ONLY."""
from __future__ import annotations

import datetime as dt

import pytest
from test_actionability_and_canonical_ticket import (
    SIGNED_POLICY,
    _build_asian_london_sweep,
)

from telegram_delivery.adapter import footer
from v1_tickets import fx as v1_fx
from v1_tickets.canonical_ticket import CANONICAL_VERSION, build_canonical_ticket
from v1_tickets.scope_status import resolve_ticket_scope

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
S1_IDENTITY = "d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5"
ASW, CCFD, LSMC = "ST_ASIAN_SWEEP_5R_V1", "ST_CRYPTO_CFD_SWEEP_RETEST_V1", "ST_LARGE_SMC_V1"


def raw(strategy_id, version, symbol, cycle, decision="NO_TRADE", **extra):
    return {"strategy_id": strategy_id, "strategy_version": version, "symbol": symbol, "cycle": cycle,
            "session_date": NOW.date().isoformat(), "decision": decision, "reason_code": "TEST",
            "evaluated_at": NOW.isoformat(), **extra}


def canon(ticket):
    return build_canonical_ticket(ticket, now=NOW, policy=SIGNED_POLICY)


def test_schema_id_is_unchanged_and_execution_flags_stay_false():
    c = canon(raw(ASW, "1.1.2", "GBPUSD", "ASIAN_LONDON"))
    assert c["schema"] == CANONICAL_VERSION == "AG_CANONICAL_TICKET_V1"
    assert (c["execution_authorization"], c["demo_authorized"], c["live_authorized"]) == (False, False, False)
    assert c["scope_route"] == "REPORT_ONLY"


def test_s1_scope_is_verified_but_report_only():
    c = canon(raw(ASW, "1.1.2", "GBPUSD", "ASIAN_LONDON"))
    assert (c["scope_verification_status"], c["scope_reason"]) == ("LOGIC_VERIFIED", "DEMO_AUTHORIZATION_ABSENT")
    assert c["verification_identity"] == S1_IDENTITY
    assert c["report_class"] == "NO_OPPORTUNITY" and c["candidate_signal_id"] is None


def test_other_version_never_borrows_the_scope_status():
    c = canon(raw(ASW, "1.1.1", "GBPUSD", "ASIAN_LONDON"))
    assert (c["scope_verification_status"], c["scope_reason"]) == ("UNVERIFIED", "VERSION_NOT_IN_SCOPE:1.1.1")
    assert c["verification_identity"] is None
    c = canon(raw(ASW, "1.1.3", "EURUSD", "ASIAN_LONDON"))
    assert c["scope_reason"] == "VERSION_NOT_IN_SCOPE:1.1.3"


@pytest.mark.parametrize("symbol,cycle,status", [
    ("EURUSD", "ASIAN_LONDON", "SUSPENDED"), ("EURUSD", "LONDON_NEWYORK", "UNVERIFIED"),   # OD1014-FAST D5
    ("GBPUSD", "LONDON_NEWYORK", "UNVERIFIED"), ("USDJPY", "ASIAN_LONDON", "UNVERIFIED"),
    ("XAUUSD", "LONDON_NEWYORK", "UNVERIFIED"), ("AUDUSD", "ASIAN_LONDON", "UNVERIFIED"),
])
def test_asw_scope_labels(symbol, cycle, status):
    assert canon(raw(ASW, "1.1.2", symbol, cycle))["scope_verification_status"] == status


def test_blocked_and_data_error_classes():
    assert canon(raw(ASW, "1.1.2", "USDJPY", "ASIAN_LONDON", decision="BLOCKED"))["report_class"] == "BLOCKED"
    assert canon(raw(ASW, "1.1.2", "USDJPY", "ASIAN_LONDON", decision="DATA_ERROR"))["report_class"] == "DATA_ERROR"


def test_suspended_scope_priced_candidate_stays_non_executable(monkeypatch):
    """A real v1.1.2 engine signal on a scope without READY authority is a priced CANDIDATE only."""
    ref, n, post = _build_asian_london_sweep(NOW, age_minutes=5)
    ticket = v1_fx.build_fx_ticket("EURUSD", "ASIAN_LONDON", NOW.date(), ref, n, post, data_source="TEST",
                                   evaluated_at=NOW, data_close=post[-1].time + dt.timedelta(minutes=15),
                                   spread=0.0001, strategy_path=v1_fx.SCOPED_CANDIDATE_PATH)
    c = build_canonical_ticket(ticket, now=NOW, current_price=1.1636, policy=SIGNED_POLICY)
    assert c["decision"] != "WATCH_READY"
    assert c["report_class"] == "CANDIDATE" and c["scope_verification_status"] == "SUSPENDED"
    assert c["prices"]["entry_reference_raw"] is not None and c["prices"]["sl_raw"] is not None
    assert c["candidate_signal_id"].startswith(f"{ASW}@1.1.2|EURUSD|ASIAN_LONDON|LONG|")
    assert c["execution_authorization"] is False


@pytest.mark.parametrize("direction,status,reason", [
    ("SHORT", "STALE_IDENTITY", "STALE_IDENTITY"),
    ("LONG", "UNVERIFIED", "DIRECTION_NOT_IN_SCOPE"),
])
def test_ccfd_scope_is_per_direction(direction, status, reason):
    scope = resolve_ticket_scope(CCFD, "1.0.0", "BTCUSD", "WEEKDAY", direction)
    assert (scope["scope_verification_status"], scope["scope_reason"]) == (status, reason)


def test_ccfd_verified_status_requires_a_recorded_window():
    import copy

    from v1_tickets.authority import load_registry, logic_identity
    reg = copy.deepcopy(load_registry())
    cand = reg[CCFD]["candidate_versions"]["1.0.0"]
    digest = logic_identity(CCFD, "1.0.0")["digest"]
    cand["logic_status"], cand["logic_verified_identity"] = "LOGIC_VERIFIED", digest
    for item in cand["logic_verified_symbols"]:
        item["logic_identity"] = digest
    scope = resolve_ticket_scope(CCFD, "1.0.0", "BTCUSD", "WEEKDAY", "SHORT", registry=reg)
    assert (scope["scope_verification_status"], scope["scope_reason"]) == ("UNVERIFIED", "WINDOW_NOT_IN_SCOPE")


def test_lsmc_watch_cycle_maps_to_entry_unverified():
    scope = resolve_ticket_scope(LSMC, "1.1.0", "EURUSD", "LSMC_WATCH-abc123")
    assert (scope["scope_verification_status"], scope["scope_reason"]) == ("UNVERIFIED", "ENTRY_LOGIC_NOT_VERIFIED")


def test_unknown_strategy_or_broken_registry_fails_closed():
    assert resolve_ticket_scope("NOPE", "1", "EURUSD", "ASIAN_LONDON")["scope_reason"] == "SCOPE_NOT_DECLARED"
    scope = resolve_ticket_scope(ASW, "1.1.2", "GBPUSD", "ASIAN_LONDON", registry={})
    assert (scope["scope_verification_status"], scope["scope_reason"]) == ("UNVERIFIED", "REGISTRY_ENTRY_MISSING")


def test_footer_shows_scope_in_ascii_and_rejects_a_routable_scope():
    c = canon(raw(ASW, "1.1.2", "USDJPY", "ASIAN_LONDON"))
    lines = footer(c)
    assert lines[0] == "scope: UNVERIFIED | REPORT_ONLY (LOGIC_NOT_VERIFIED)"
    assert all(line.isascii() for line in lines[:2])
    with pytest.raises(ValueError):
        footer({**c, "scope_route": "DEMO_ORDER"})
    legacy = {k: v for k, v in c.items() if not k.startswith(("scope_", "report_", "candidate_", "verification_"))}
    assert footer(legacy)[0].startswith("logic_status:")          # older tickets render unchanged
