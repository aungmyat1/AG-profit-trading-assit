"""AG_OSS_FIRST_TRADETICKET_VERTICAL_SLICE_V1 (R2).

Two successful outcomes are proven:

  TEST PIPELINE  frozen EURUSD Opportunity fixture (reserved PIPELINE_TEST_ namespace)
                 -> qualify -> ProposalEligibility (existing) -> CanonicalProposal
                 (existing) -> TradeTicket PREPARED_TEST_ONLY -> owner view
  REAL RESEARCH  ST_ASIAN_SWEEP_5R_V1 Opportunity from the unchanged live runner
                 -> proposal authority check -> NO_PROPOSAL_AUTHORITY, no ticket

MarketState/provenance come from the real runner over fixture candles. The fixture
candidate is labelled REAL only so the UNMODIFIED eligibility firewall is exercised in
full; its non-authority is carried by the reserved namespace, PIPELINE_TEST_MODE and
status PREPARED_TEST_ONLY (market_authoritative=False).
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import hashlib
import inspect
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import MetaTrader5
import pytest
import yaml

from fx_opportunity.runner import strategy_incompatibility
from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta
from opportunity.contracts import CandidateGeometry, OpportunityCandidate
from opportunity.registry_binding import StrategyBinding
from trade_ticket import sizing as sizing_mod
from trade_ticket.qualification import (
    MODE_PIPELINE_TEST,
    MODE_REAL,
    ProposalAuthority,
    registry_fingerprint,
    resolve_proposal_authority,
)
from trade_ticket.sizing import AccountSnapshot, RiskPolicy, prepare_sizing, risk_policy_from_pilot, size_position
from trade_ticket.ticket import (
    DECLARED_TRANSITIONS,
    PREPARED_TEST_ONLY,
    TradeTicket,
    prepare_trade_ticket,
    verify_ticket_dict,
)
from test_fx_opportunity_market_state import BINDING, PILOTS, STRATEGY, Feed, at, ready_bars, run

REPO = Path(__file__).resolve().parents[1]
TEST_ID = "PIPELINE_TEST_SESSION_FIXTURE_V1"
NOW = at(7, 31)
# Frozen fixture geometry per symbol (entry, stop, 5R target) -- matches the fixture sweep bar.
GEOMETRY = {"EURUSD": ("LONG", 1.1001, 1.0988, 1.1066), "GBPUSD": ("LONG", 1.3001, 1.2988, 1.3066)}
ACCOUNT = AccountSnapshot(equity=10_000.0, currency="USD", server="VTMarkets-Demo", environment="DEMO",
                          open_risk_pct=0.0)


def meta(symbol="EURUSD", **kw):
    base = dict(symbol=symbol, tick_size=0.00001, tick_value=1.0, contract_size=100_000.0, volume_min=0.01,
                volume_max=100.0, volume_step=0.01, digits=5, point=0.00001)
    if symbol == "USDJPY":
        base.update(tick_size=0.001, tick_value=0.66667, digits=3, point=0.001)
    base.update(kw)
    return SymbolMeta(**base)


def fixture_binding(strategy_id=TEST_ID):
    return StrategyBinding(strategy_id=strategy_id, semantic_version="0.0.0", engine_id=None, engine_version=None,
                           adapter_id=None, adapter_version=None, dispatchable=False,
                           opportunity_authority=True, live_observation_supported=True)


def runner_result(symbol="EURUSD", cycle="POST_ASIAN", mode="REAL"):
    return run(symbol, Feed(ready_bars(symbol)), NOW, cycle=cycle, mode=mode)


def fixture_candidate(symbol="EURUSD", *, mode="REAL", geometry=None, strategy_id=TEST_ID, **kw):
    d, e, s, t = GEOMETRY.get(symbol, GEOMETRY["EURUSD"])
    g = geometry or CandidateGeometry(direction=d, entry=e, invalidation=s, targets=(t,), estimated_rr=5.0)
    fields = dict(candidate_id=f"CAND:{symbol}:fixture", occurrence_id=f"OCC:{symbol}:2026-09-21",
                  strategy_id=strategy_id, strategy_version="0.0.0", strategy_engine_version=None,
                  symbol=symbol, market="FX", venue=None, direction=g.direction,
                  detected_at=at(7, 30), last_evaluated_at=at(7, 30), expires_at=None,
                  stage="ENTRY_CONFIRMED", outcome="ACTIVE", revision=1,
                  setup_evidence={"sweep": "LOWER_SWEEP_STRICT_PENETRATION"}, geometry=g,
                  market_data_mode=mode, data_lineage="PIPELINE_TEST_FIXTURE")
    fields.update(kw)
    return OpportunityCandidate(**fields)


def prepare(symbol="EURUSD", cycle="POST_ASIAN", *, candidate=None, result=None, mode=MODE_PIPELINE_TEST,
            authority=None, binding=None, **kw):
    result = result or runner_result(symbol, cycle)
    candidate = candidate or fixture_candidate(symbol)
    args = dict(candidate=candidate, market_state=result.market_state, binding=binding or fixture_binding(candidate.strategy_id),
                cycle=cycle, mode=mode, authority=authority,
                provenance=result.provenance, broker_key="VTMARKETS", account=ACCOUNT, symbol_meta=meta(symbol),
                evaluated_at=NOW)
    if "risk_policy" not in kw:
        args["risk_policy"] = risk_policy_from_pilot(PILOTS[cycle])
    args.update(kw)
    return prepare_trade_ticket(**args)


# --- EURUSD test vertical slice ------------------------------------------------------


def test_eurusd_fixture_reaches_prepared_test_only_ticket():
    res = prepare()
    assert res.status == PREPARED_TEST_ONLY, res.reason_codes
    t = res.ticket
    assert (t.status, t.execution_authority, t.market_authoritative) == (PREPARED_TEST_ONLY, "NONE", False)
    assert res.qualification.status == "QUALIFIED" and res.eligibility.status == "ELIGIBLE"
    assert t.proposal.proposal_state == "PROPOSAL_READY" and t.proposal.execution_authority == "NONE"
    assert (t.symbol, t.direction, t.entry, t.stop_loss, t.targets) == ("EURUSD", "LONG", 1.1001, 1.0988, (1.1066,))
    assert (t.broker, t.server, t.environment, t.cycle) == ("VT_MARKETS", "VTMarkets-Demo", "DEMO", "POST_ASIAN")
    assert t.risk_pct == 0.5 and t.risk_policy_source == "pilot:" + PILOTS["POST_ASIAN"].pilot_id
    # 0.5% of 10k = 50; 13 pips x $10/pip/lot = $130/lot -> 0.38 lots, $49.40
    assert (t.position_size_lots, t.risk_amount) == (0.38, 49.4)
    assert t.expires_at == res.market_state.execution_window_utc[1] and t.expiry_source == "EXECUTION_WINDOW_END"
    assert t.market_state_fingerprint == res.market_state.fingerprint
    assert t.market_data_fingerprint == runner_result().provenance["lineage_fingerprint"]
    assert t.ticket_id == f"TKT-{t.semantic_fingerprint[:24]}"
    assert DECLARED_TRANSITIONS[t.status] == ()


def test_owner_view_minimum_shape_and_advisory_ai():
    view = prepare().owner_view()
    tk = view["ticket"]
    assert view["symbol"] == "EURUSD" and view["cycle"] == "POST_ASIAN"
    assert view["strategy"] == {"id": TEST_ID, "version": "0.0.0"}
    assert view["qualification"]["status"] == "QUALIFIED" and view["proposal_authority"] == "PIPELINE_TEST_ONLY"
    assert view["execution_authority"] == "NONE" and view["market_state"]["fingerprint"]
    for key in ("direction", "entry", "stop_loss", "targets", "risk", "expires_at", "provenance", "why"):
        assert key in tk
    assert tk["risk"]["position_size_lots"] == 0.38 and tk["market_authoritative"] is False
    assert view["ai_explanation"] == {"authority": "ADVISORY_ONLY", "text": None}
    json.dumps(view)  # API-serializable


def test_ai_explanation_cannot_change_ticket_semantics():
    res = prepare()
    view = res.owner_view()
    view["ai_explanation"]["text"] = "price looks great, raise risk"
    view["ticket"]["entry"] = 9.9
    assert res.ticket.entry == 1.1001 and verify_ticket_dict(res.ticket.to_dict())


# --- real research path --------------------------------------------------------------


@pytest.mark.parametrize("mode", ["REAL", "REPLAY"])
def test_real_research_opportunity_is_denied_proposal_authority(mode):
    result = runner_result(mode=mode)
    assert result.opportunity == "OPPORTUNITY" and result.candidate.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    if mode == "REAL":
        assert result.eligibility.status == "ELIGIBLE"  # existing gate alone would pass
    res = prepare(result=result, candidate=result.candidate, mode=MODE_REAL, binding=BINDING,
                  authority=resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1"),
                  expected_registry_fingerprint=registry_fingerprint())
    assert res.status == "NO_PROPOSAL_AUTHORITY"
    # R1: both representations deny, and both denials are reported
    assert res.reason_codes == ("BINDING_PROPOSAL_AUTHORITY_FALSE", "PROPOSAL_AUTHORITY_FIELD_ABSENT")
    assert res.ticket is None and res.eligibility is None and res.proposal is None
    assert res.owner_view()["proposal_authority"] == "NONE"


def test_no_registered_strategy_has_proposal_authority():
    ids = yaml.safe_load((REPO / "strategies/registry.yaml").read_text(encoding="utf-8"))["strategies"]
    assert ids and not any(resolve_proposal_authority(s).proposal_authorized for s in ids)


def test_mode_namespace_cannot_be_crossed():
    real = runner_result().candidate
    assert prepare(candidate=real, binding=BINDING).reason_codes == ("REAL_STRATEGY_IN_PIPELINE_TEST_MODE",)
    assert prepare(mode=MODE_REAL).reason_codes == ("PIPELINE_TEST_STRATEGY_IN_REAL_MODE",)


def test_fixture_path_accepts_no_strategy_authority():
    """R1: PREPARED_TEST_ONLY needs no (fake) authority and cannot be handed one."""
    real_auth = resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1")
    forged = dataclasses.replace(real_auth, strategy_id=TEST_ID, proposal_authorized=True)
    assert prepare(authority=forged).reason_codes == ("AUTHORITY_NOT_ALLOWED_IN_PIPELINE_TEST",)
    claiming = dataclasses.replace(fixture_binding(), proposal_authority=True)
    assert prepare(binding=claiming).reason_codes == ("FIXTURE_BINDING_CLAIMS_AUTHORITY",)
    src = prepare().ticket.proposal_authority_source
    assert src == {"source": "PIPELINE_TEST_FIXTURE", "strategy_authority": "NONE"}


# --- fail-closed matrix --------------------------------------------------------------


@pytest.mark.parametrize("geometry, status, reason", [
    (CandidateGeometry("LONG", math.nan, 1.0988, (1.1066,)), "RISK_GEOMETRY_INVALID", "NON_FINITE_GEOMETRY"),
    (CandidateGeometry("LONG", 1.1001, math.inf, (1.1066,)), "RISK_GEOMETRY_INVALID", "NON_FINITE_GEOMETRY"),
    (CandidateGeometry("LONG", 1.1001, 1.0988, (math.nan,)), "RISK_GEOMETRY_INVALID", "NON_FINITE_GEOMETRY"),
    (CandidateGeometry("LONG", 1.1001, 1.1010, (1.1066,)), "RISK_GEOMETRY_INVALID", "INVALID_STOP_GEOMETRY"),
    (CandidateGeometry("SHORT", 1.1001, 1.0988, (0.9,)), "RISK_GEOMETRY_INVALID", "INVALID_STOP_GEOMETRY"),
    (CandidateGeometry("LONG", 1.1001, 1.1001, (1.1066,)), "RISK_GEOMETRY_INVALID", "ENTRY_EQUALS_STOP"),
    (CandidateGeometry("LONG", 1.1001, 1.0988, (1.0990,)), "RISK_GEOMETRY_INVALID", "INVALID_TARGET_GEOMETRY"),
    (CandidateGeometry("LONG", 1.1001, 1.0988, ()), "INCOMPLETE_TRADE_PLAN", "TARGETS_NOT_STRATEGY_OWNED"),
    (CandidateGeometry("LONG", None, 1.0988, (1.1066,)), "NO_SETUP", "NO_STRATEGY_GEOMETRY"),
])
def test_geometry_fails_closed(geometry, status, reason):
    res = prepare(candidate=fixture_candidate(geometry=geometry))
    assert res.status == status and reason in res.reason_codes and res.ticket is None


def test_wrong_symbol_fails_closed():
    gbp_state = runner_result("GBPUSD")
    assert prepare(result=gbp_state).reason_codes == ("MARKET_STATE_SYMBOL_MISMATCH",)
    xau = fixture_candidate("XAUUSD")
    assert prepare(candidate=xau).reason_codes == ("SYMBOL_NOT_IN_INSTRUMENT_CONTRACT",)


def test_unsupported_cycle_fails_closed():
    assert prepare(cycle="POST_NEWYORK", result=runner_result(),
                   risk_policy=risk_policy_from_pilot(PILOTS["POST_ASIAN"])).reason_codes == ("UNSUPPORTED_CYCLE",)


def test_stale_and_expired_opportunity_fail_closed():
    assert prepare(evaluated_at=NOW + dt.timedelta(minutes=16)).reason_codes == ("MARKET_STATE_STALE",)
    expired = fixture_candidate(expires_at=at(7, 31))
    assert prepare(candidate=expired).reason_codes == ("OPPORTUNITY_EXPIRED",)


def test_lookahead_contamination_fails_closed():
    assert prepare(evaluated_at=NOW - dt.timedelta(minutes=1)).reason_codes == ("LOOKAHEAD_CONTAMINATION",)
    future = fixture_candidate(last_evaluated_at=at(7, 45))
    assert prepare(candidate=future).reason_codes == ("LOOKAHEAD_CONTAMINATION",)


def test_synthetic_and_mode_mismatch_fail_closed():
    assert prepare(candidate=fixture_candidate(mode="REPLAY")).reason_codes == ("MARKET_DATA_MODE_MISMATCH",)
    synthetic = runner_result(mode="SYNTHETIC")
    res = prepare(result=synthetic, candidate=fixture_candidate(mode="SYNTHETIC"))
    assert res.status == "ELIGIBILITY_NOT_ELIGIBLE" and "SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE" in res.reason_codes


def test_missing_provenance_fails_closed():
    result = runner_result()
    prov = {k: v for k, v in result.provenance.items() if k != "strategy_config_fingerprint"}
    assert prepare(result=result, provenance=prov).reason_codes == ("MISSING_STRATEGY_CONFIG_FINGERPRINT",)


def test_account_context_must_be_verified_vt_demo():
    bad_server = dataclasses.replace(ACCOUNT, server="Other-Live")
    assert prepare(account=bad_server).reason_codes == ("BROKER_SERVER_MISMATCH",)
    live = dataclasses.replace(ACCOUNT, environment="LIVE")
    assert prepare(account=live).reason_codes == ("ACCOUNT_ENVIRONMENT_NOT_VERIFIED_DEMO",)


def test_duplicate_is_idempotent_and_conflict_blocks():
    first = prepare().ticket
    dup = prepare(existing={first.proposal_envelope_id: first})
    assert dup.status == "DUPLICATE" and dup.ticket is first
    moved = fixture_candidate(geometry=CandidateGeometry("LONG", 1.1001, 1.0988, (1.1070,)))
    conflict = prepare(candidate=moved, existing={first.proposal_envelope_id: first})
    assert conflict.status == "DUPLICATE_CONFLICT" and conflict.ticket is None


# --- risk / sizing -------------------------------------------------------------------


def test_size_position_is_verbatim_restoration():
    src = inspect.getsource(sizing_mod)
    body = src[src.index("def size_position"):src.index("return volume, risk_amount, None")]
    assert hashlib.sha256(body.encode()).hexdigest() == \
        "87fb5b53407697da002d63899ce661ddb000824716bbd66adca7bdd81db9ea4e"  # 1a8e7c5:src/execution/risk.py


def test_risk_policy_is_the_cycle_pilot_never_demo_default():
    for cycle in ("POST_ASIAN", "POST_LONDON"):
        policy = risk_policy_from_pilot(PILOTS[cycle])
        assert (policy.risk_per_trade_pct, policy.max_aggregate_open_risk_pct) == (0.5, 1.0)
    demo = yaml.safe_load((REPO / "config/trading.demo.yaml").read_text(encoding="utf-8"))
    assert demo["risk"]["risk_per_trade_pct"] == 1.0  # the divergent generic default -- not consulted
    assert not hasattr(sizing_mod, "load_risk_policy") and "trading.demo.yaml" not in \
        inspect.getsource(sizing_mod).split('"""')[-1]
    assert risk_policy_from_pilot(dataclasses.replace(PILOTS["POST_ASIAN"], risk_per_trade_pct=math.nan)) is None


def test_risk_policy_failures_fail_closed():
    assert prepare(risk_policy=None).reason_codes == ("RISK_POLICY_UNAVAILABLE",)
    foreign = RiskPolicy(0.5, 1.0, "OTHER_PILOT", "pilot:OTHER_PILOT")
    assert prepare(risk_policy=foreign).reason_codes == ("RISK_POLICY_PROVENANCE_MISMATCH",)
    assert prepare(account=dataclasses.replace(ACCOUNT, open_risk_pct=0.6)).reason_codes == ("AGGREGATE_RISK_EXCEEDED",)
    assert prepare(account=dataclasses.replace(ACCOUNT, open_risk_pct=None)).reason_codes == ("AGGREGATE_RISK_UNKNOWN",)
    assert prepare(account=dataclasses.replace(ACCOUNT, equity=math.nan)).reason_codes == ("ACCOUNT_EQUITY_INVALID",)


def test_symbol_metadata_mismatch_fails_closed():
    assert prepare(symbol_meta=meta("GBPUSD")).reason_codes == ("SYMBOL_METADATA_MISMATCH",)
    assert prepare(symbol_meta=meta(digits=3)).reason_codes == ("INSTRUMENT_DIGITS_MISMATCH",)
    assert prepare(symbol_meta=meta(tick_value=math.inf)).reason_codes == ("SYMBOL_METADATA_INVALID",)
    assert prepare(symbol_meta=None).reason_codes == ("SYMBOL_METADATA_UNAVAILABLE",)
    policy = risk_policy_from_pilot(PILOTS["POST_ASIAN"])
    synthetic = meta(metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH)
    r = prepare_sizing(entry=1.1001, stop_loss=1.0988, account=ACCOUNT, risk_policy=policy, symbol_meta=synthetic,
                       expected_symbol="EURUSD", expected_digits=5, require_verified_metadata=True)
    assert r.reason_code == "SYMBOL_METADATA_NOT_BROKER_VERIFIED"


@pytest.mark.parametrize("symbol, entry, stop, lots", [
    ("EURUSD", 1.1001, 1.0988, 0.38), ("GBPUSD", 1.3001, 1.2988, 0.38), ("USDJPY", 150.00, 149.70, 0.24)])
def test_sizing_geometry_per_symbol(symbol, entry, stop, lots):
    volume, risk, reason = size_position(entry, stop, 10_000.0, 0.5, meta(symbol))
    assert reason is None and volume == lots and risk <= 50.0


# --- determinism / restart parity ----------------------------------------------------


def test_same_process_determinism_and_sensitivity():
    a, b = prepare().ticket, prepare().ticket
    assert a.to_dict() == b.to_dict()
    moved = prepare(candidate=fixture_candidate(geometry=CandidateGeometry("LONG", 1.1001, 1.0990, (1.1066,)))).ticket
    richer = prepare(account=dataclasses.replace(ACCOUNT, equity=20_000.0)).ticket
    assert len({a.semantic_fingerprint, moved.semantic_fingerprint, richer.semantic_fingerprint}) == 3


def test_restart_parity_via_serialization():
    d = json.loads(json.dumps(prepare().ticket.to_dict()))
    assert verify_ticket_dict(d)
    d["position_size_lots"] = 1.0
    assert not verify_ticket_dict(d)


def test_fresh_process_determinism():
    code = ("import sys; sys.path[:0]=['tests']; import test_trade_ticket_vertical_slice as t; "
            "print(t.prepare().ticket.semantic_fingerprint)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src"), str(REPO / "tests")]))
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == prepare().ticket.semantic_fingerprint


# --- GBPUSD / USDJPY -----------------------------------------------------------------


def test_gbpusd_uses_the_same_contracts():
    res = prepare("GBPUSD")
    assert res.status == PREPARED_TEST_ONLY and res.ticket.symbol == "GBPUSD"
    assert res.ticket.position_size_lots == 0.38


def test_usdjpy_has_no_strategy_binding():
    for cycle, pilot in PILOTS.items():
        assert strategy_incompatibility("USDJPY", pilot, STRATEGY), cycle


# --- containment ---------------------------------------------------------------------

PKG = REPO / "src" / "trade_ticket"
MUTATION_APIS = ("order_send", "order_check", "positions_get", "positions_total", "orders_get",
                 "orders_total", "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel")
FORBIDDEN_ROOTS = ("execution", "execution_runtime", "authorization", "ticket_delivery", "notifications",
                   "owner_decision", "strategy_manager", "trade_management", "scheduler", "backtesting",
                   "research_external", "smartmoneyconcepts", "vectorbt")


def test_static_no_execution_capability():
    for path in PKG.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                assert name not in MUTATION_APIS, (path, name)
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            for n in names:
                assert n.split(".")[0] not in FORBIDDEN_ROOTS and n != "MetaTrader5", (path, n)


def test_ticket_has_no_order_capable_method():
    members = [m for m in dir(TradeTicket) if not m.startswith("_")]
    assert not [m for m in members if any(w in m.lower() for w in ("send", "order", "execute", "submit"))]


def test_transitive_imports_are_capability_zero():
    code = ("import sys; import trade_ticket.ticket; "
            f"roots={FORBIDDEN_ROOTS!r}; "
            "bad=[m for m in sys.modules if m.split('.')[0] in roots or m in "
            "('mt5.connection','mt5.account','mt5.management_gateway','mt5.mt5_gateway')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_runtime_zero_broker_calls(monkeypatch):
    calls = []
    for api in MUTATION_APIS:
        monkeypatch.setattr(MetaTrader5, api, lambda *a, _n=api, **k: calls.append(_n), raising=False)
    prepare()
    prepare("GBPUSD")
    r = runner_result()
    prepare(result=r, candidate=r.candidate, mode=MODE_REAL, binding=BINDING,
            authority=resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1"))
    assert calls == []  # BROKER_ORDER_CHECK = BROKER_ORDER_SEND = OTHER_EXECUTION_MUTATIONS = 0


# --- OSS licence / authority boundaries ----------------------------------------------


def _product_import_roots():
    """Product runtime = the importable application package tree under src/ (research
    CLIs under scripts/ are not product runtime)."""
    for path in (REPO / "src").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    yield path, [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    yield path, [node.module.split(".")[0]]


def test_backtesting_py_agpl_not_reachable_from_product_runtime():
    offenders = [(p, r) for p, roots in _product_import_roots() for r in roots
                 if r in ("backtesting", "research_external")]
    assert offenders == []
    code = ("import sys; import fx_opportunity.scanner, opportunity.proposal_eligibility, "
            "proposal_envelope.adapters.opportunity_adapter, trade_ticket.ticket, api.crypto_opportunities; "
            "bad=[m for m in sys.modules if m.split('.')[0] in ('backtesting','research_external')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_reference_only_and_rejected_oss_not_imported_by_product_runtime():
    offenders = [(p, r) for p, roots in _product_import_roots() for r in roots
                 if r in ("smartmoneyconcepts", "vectorbt")]
    assert offenders == []



# --- R1: Arena BLOCKING-1 (authority cross-check) ------------------------------------
# A temporary registry stands in for a FUTURE owner-signed proposal_authorization block;
# the real strategies/registry.yaml is never modified and grants nothing.

from trade_ticket import qualification as qualification_mod  # noqa: E402
from trade_ticket.ticket import semantic_fingerprint  # noqa: E402

SCOPE = dict(authorized=True, strategy_version="1.1.1", symbols=["EURUSD"], cycles=["POST_ASIAN"],
             market_data_modes=["REAL"])


def authorized_registry(tmp_path, monkeypatch, **scope_overrides):
    data = yaml.safe_load((REPO / "strategies/registry.yaml").read_text(encoding="utf-8"))
    data["strategies"]["ST_ASIAN_SWEEP_5R_V1"]["proposal_authorization"] = dict(SCOPE, **scope_overrides)
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(qualification_mod, "REGISTRY_PATH", str(path))
    return resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1"), registry_fingerprint()


def real(authority, fp, *, binding_authority=True, with_test_target=False, **kw):
    r = runner_result(mode="REAL")
    candidate = r.candidate
    if with_test_target:
        # ST_ASIAN_SWEEP_5R_V1 emits no targets (never invented by the pipeline); a
        # TEST-supplied 5R target lets the authorized path be exercised to the ticket.
        candidate = dataclasses.replace(candidate, geometry=dataclasses.replace(candidate.geometry, targets=(1.1066,)))
    binding = dataclasses.replace(BINDING, proposal_authority=binding_authority)
    return prepare(result=r, candidate=candidate, mode=MODE_REAL, binding=binding, authority=authority,
                   expected_registry_fingerprint=fp, **kw)


def test_agreeing_authority_passes_gate_then_genuine_candidate_still_fails_closed(tmp_path, monkeypatch):
    auth, fp = authorized_registry(tmp_path, monkeypatch)
    res = real(auth, fp)
    assert res.qualification.authority_provenance["source"] == "REGISTRY"  # authority gate passed
    assert (res.status, res.reason_codes, res.ticket) == ("INCOMPLETE_TRADE_PLAN", ("TARGETS_NOT_STRATEGY_OWNED",), None)


def test_binding_true_and_matching_registry_authority_reaches_prepared_only(tmp_path, monkeypatch):
    auth, fp = authorized_registry(tmp_path, monkeypatch)
    res = real(auth, fp, with_test_target=True)
    assert res.status == "PREPARED_ONLY", res.reason_codes
    t = res.ticket
    assert t.market_authoritative is True and t.execution_authority == "NONE"
    src = t.proposal_authority_source
    assert (src["source"], src["resolution"], src["registry_fingerprint"], src["binding_proposal_authority"]) == \
        ("REGISTRY", "AUTHORIZED", fp, True)
    assert res.owner_view()["ticket"]["provenance"]["proposal_authority_source"] == src
    assert verify_ticket_dict(json.loads(json.dumps(t.to_dict())))


def test_arena_forged_authority_with_genuine_binding_is_blocked():
    """Arena BLOCKING-1 reproduction: forged in-memory authority + genuine binding (False)."""
    forged = ProposalAuthority("ST_ASIAN_SWEEP_5R_V1", True, "FORGED", "AUTHORIZED", "strategies/registry.yaml",
                               registry_fingerprint(), "1.1.1", ("EURUSD",), ("POST_ASIAN",), ("REAL",))
    r = runner_result(mode="REAL")
    res = prepare(result=r, candidate=r.candidate, mode=MODE_REAL, binding=BINDING, authority=forged,
                  expected_registry_fingerprint=registry_fingerprint())
    assert res.status == "NO_PROPOSAL_AUTHORITY" and res.ticket is None
    assert res.reason_codes == ("BINDING_PROPOSAL_AUTHORITY_FALSE", "AUTHORITY_SOURCE_NOT_REGISTRY")


def test_binding_false_with_forged_registry_shaped_authority_is_blocked(tmp_path, monkeypatch):
    auth, fp = authorized_registry(tmp_path, monkeypatch)
    res = real(auth, fp, binding_authority=False)
    assert res.reason_codes == ("BINDING_PROPOSAL_AUTHORITY_FALSE",) and res.ticket is None


def test_binding_true_with_registry_authority_false_is_blocked():
    res = real(resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1"), registry_fingerprint())
    assert res.reason_codes == ("PROPOSAL_AUTHORITY_FIELD_ABSENT",)


def test_both_false_is_blocked_with_both_reasons():
    res = real(resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1"), registry_fingerprint(), binding_authority=False)
    assert res.reason_codes == ("BINDING_PROPOSAL_AUTHORITY_FALSE", "PROPOSAL_AUTHORITY_FIELD_ABSENT")


def test_missing_authority_in_real_mode_is_blocked():
    assert real(None, registry_fingerprint()).reason_codes == ("AUTHORITY_MISSING",)


@pytest.mark.parametrize("override, reason", [
    ({"strategy_version": "9.9.9"}, "AUTHORITY_STRATEGY_VERSION_MISMATCH"),
    ({"symbols": ["GBPUSD"]}, "AUTHORITY_SYMBOL_NOT_PERMITTED"),
    ({"cycles": ["POST_LONDON"]}, "AUTHORITY_CYCLE_NOT_PERMITTED"),
    ({"market_data_modes": ["REPLAY"]}, "AUTHORITY_DATA_MODE_NOT_PERMITTED"),
    ({"authorized": False}, "PROPOSAL_AUTHORITY_NOT_AUTHORIZED"),
    ({"symbols": []}, "PROPOSAL_AUTHORITY_MALFORMED"),
])
def test_authority_scope_must_match_exactly(tmp_path, monkeypatch, override, reason):
    auth, fp = authorized_registry(tmp_path, monkeypatch, **override)
    assert real(auth, fp).reason_codes == (reason,)


def test_authority_strategy_id_mismatch_is_blocked(tmp_path, monkeypatch):
    auth, fp = authorized_registry(tmp_path, monkeypatch)
    assert real(dataclasses.replace(auth, strategy_id="SESSION_TRADE_V1"), fp).reason_codes == \
        ("AUTHORITY_STRATEGY_MISMATCH",)


def test_wrong_source_or_registry_lineage_is_blocked(tmp_path, monkeypatch):
    auth, fp = authorized_registry(tmp_path, monkeypatch)
    assert real(dataclasses.replace(auth, source="FORGED"), fp).reason_codes == ("AUTHORITY_SOURCE_NOT_REGISTRY",)
    assert real(auth, "0" * 64).reason_codes == ("AUTHORITY_REGISTRY_LINEAGE_MISMATCH",)
    assert real(auth, None).reason_codes == ("AUTHORITY_REGISTRY_LINEAGE_MISMATCH",)
    other = tmp_path / "forged.yaml"
    other.write_text((tmp_path / "registry.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    off_path = resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1", registry_path=str(other))
    assert real(off_path, fp).reason_codes == ("AUTHORITY_REGISTRY_PATH_NOT_CANONICAL",)


def test_ticket_constructor_rejects_authority_impersonation():
    t = prepare().ticket
    with pytest.raises(ValueError):  # a fixture ticket cannot be relabelled as authoritative
        dataclasses.replace(t, status="PREPARED_ONLY", market_authoritative=True)
    with pytest.raises(ValueError):  # nor carry registry-looking provenance
        dataclasses.replace(t, proposal_authority_source={"source": "REGISTRY", "strategy_authority": "NONE"})


# --- R1: Arena BLOCKING-2 (risk context + authority provenance on the ticket) ---------


def test_open_risk_and_aggregate_policy_are_recorded_and_hashed():
    zero = prepare().ticket
    some = prepare(account=dataclasses.replace(ACCOUNT, open_risk_pct=0.4)).ticket
    assert (zero.open_risk_pct, some.open_risk_pct) == (0.0, 0.4)
    assert zero.semantic_fingerprint != some.semantic_fingerprint
    assert (zero.risk_pct, zero.max_aggregate_open_risk_pct) == (0.5, 1.0)
    assert zero.risk_policy_fingerprint == risk_policy_from_pilot(PILOTS["POST_ASIAN"]).fingerprint()
    assert zero.open_risk_snapshot_fingerprint == "NOT_AVAILABLE"
    assert "aggregate_risk_policy" not in zero.to_dict()
    risk = prepare().owner_view()["ticket"]["risk"]
    assert (risk["open_risk_pct"], risk["max_aggregate_open_risk_pct"]) == (0.0, 1.0)


@pytest.mark.parametrize("field, value", [
    ("proposal_authority_source", {"source": "REGISTRY", "strategy_authority": "NONE"}),
    ("open_risk_pct", 0.4),
    ("max_aggregate_open_risk_pct", 2.0),
    ("risk_policy_fingerprint", "0" * 64),
    ("risk_policy_source", "pilot:OTHER"),
    ("open_risk_snapshot_fingerprint", "f" * 64),
])
def test_r1_field_mutation_breaks_verification(field, value):
    d = json.loads(json.dumps(prepare().ticket.to_dict()))
    before = d["semantic_fingerprint"]
    d[field] = value
    assert not verify_ticket_dict(d)
    assert semantic_fingerprint(d) != before


def _mutate(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "x"
    if isinstance(value, list):
        return value + ["x"]
    if isinstance(value, dict):
        return dict(value, __tamper__=1)
    return "x"


SEMANTIC_FIELDS = [f.name for f in dataclasses.fields(TradeTicket) if f.name not in ("ticket_id", "semantic_fingerprint")]


@pytest.mark.parametrize("field", SEMANTIC_FIELDS)
def test_full_mutation_matrix_every_semantic_field(field):
    d = json.loads(json.dumps(prepare().ticket.to_dict()))
    d[field] = _mutate(d[field])
    assert not verify_ticket_dict(d), field


def test_full_mutation_matrix_on_registry_authorized_ticket(tmp_path, monkeypatch):
    auth, fp = authorized_registry(tmp_path, monkeypatch)
    base = json.loads(json.dumps(real(auth, fp, with_test_target=True).ticket.to_dict()))
    assert verify_ticket_dict(base)
    for field in SEMANTIC_FIELDS:
        assert not verify_ticket_dict(dict(base, **{field: _mutate(base[field])})), field
    d = json.loads(json.dumps(base))
    d["proposal_authority_source"]["registry_fingerprint"] = "0" * 64
    assert not verify_ticket_dict(d)
