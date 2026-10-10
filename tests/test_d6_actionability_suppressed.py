"""D6 port to main: a READY-suppressed Asian Sweep ticket is terminal INFO_ONLY_SUPPRESSED in
actionability -- never WATCH_READY, even under an owner-signed policy with ample remaining R.

Runs against the production config/v1_tickets/ready_authority.yaml (READY OFF). The scenario is
the one tests/test_actionability_and_canonical_ticket.py::test_fresh_actionable_signal_is_watch_ready
uses; with the switch OFF it must not reach WATCH_READY (before this guard it did)."""
from __future__ import annotations

import datetime as dt

import pytest

from test_actionability_and_canonical_ticket import SIGNED_POLICY, _build_asian_london_sweep
from v1_tickets import actionability as A
from v1_tickets import daily_evaluator as de
from v1_tickets import fx as v1_fx
from v1_tickets import ready_authority as ra
from v1_tickets.canonical_ticket import PRESENTATION_INFO, build_canonical_ticket

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)


def _ticket(now=NOW):
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    return v1_fx.build_fx_ticket("EURUSD", "ASIAN_LONDON", now.date(), ref, n, post, data_source="TEST",
                                 evaluated_at=now, data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001)


def test_production_switch_is_off(production_ready_authority):
    assert ra.ready_authority("ST_ASIAN_SWEEP_5R_V1") == (False, "READY_AUTHORITY_OFF_D6")


def test_signed_policy_cannot_turn_suppressed_ready_into_watch_ready(production_ready_authority):
    t = _ticket()
    assert (t["decision"], t["suppressed_decision"]) == (ra.SHADOW_INFO_ONLY, "READY")
    act = A.evaluate_actionability(t, now=NOW, current_price=1.1636, policy=SIGNED_POLICY)
    assert act["actionability_decision"] == A.INFO_ONLY_SUPPRESSED != A.WATCH_READY
    assert act["actionability_reason"] == "READY_AUTHORITY_OFF_D6"
    canon = build_canonical_ticket(t, now=NOW, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["decision"] == A.INFO_ONLY_SUPPRESSED and canon["presentation"] == PRESENTATION_INFO


@pytest.mark.parametrize("minutes_after", [0, 5, 25, 200])
def test_suppressed_is_terminal_at_any_time(production_ready_authority, minutes_after):
    t = _ticket()
    now = NOW + dt.timedelta(minutes=minutes_after)
    for policy in (SIGNED_POLICY, None):
        kw = {"policy": policy} if policy else {"policy_override_dict": {}}
        act = A.evaluate_actionability(t, now=now, current_price=1.1636, **kw)
        assert act["actionability_decision"] == A.INFO_ONLY_SUPPRESSED


def test_daily_evaluator_never_emits_watch_ready_while_off(production_ready_authority, tmp_path):
    ref, n, post = _build_asian_london_sweep(NOW, age_minutes=5)
    provider = de.fixture_candle_provider(ref, n, post, spread=0.0001, current_price=1.1636,
                                          data_close=post[-1].time + dt.timedelta(minutes=15))
    results = de.run_daily_evaluation(now=NOW, candle_provider=provider, archive_root=str(tmp_path),
                                      include_crypto=False, policy=SIGNED_POLICY)
    assert results and all(r.decision != A.WATCH_READY for r in results)
    eur = next(r for r in results if (r.instrument, r.session) == ("EURUSD", "ASIAN_LONDON"))
    assert eur.decision == A.INFO_ONLY_SUPPRESSED


def test_switch_on_restores_the_pre_d6_watch_ready(tmp_path, monkeypatch, stub_symbol_verified):
    on = tmp_path / "on.yaml"
    on.write_text("strategies:\n  ST_ASIAN_SWEEP_5R_V1:\n    ready: 'ON'\n")
    monkeypatch.setattr(ra, "CONFIG_PATH", str(on))
    canon = build_canonical_ticket(_ticket(), now=NOW, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["decision"] == A.WATCH_READY
