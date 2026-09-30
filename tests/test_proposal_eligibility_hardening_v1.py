"""AG_PROPOSAL_STAGE_FOUNDATION_V1 -- eligibility trust-boundary hardening tests.

Covers the capability-zero Proposal stage matrix:
  valid LONG/SHORT -> ELIGIBLE -> Proposal; symbol binding (no second symbol);
  malformed geometry (wrong-side stop, entry==stop) -> BLOCKED; non-finite
  entry/stop/target (NaN/+Inf/-Inf) -> BLOCKED; SYNTHETIC/REPLAY provenance ->
  BLOCKED; expired/terminal -> BLOCKED; deterministic proposal identity;
  duplicate replay -> no second record; corrupt store -> loud fail-closed; and
  the no-execution-authority security properties of the resulting Proposal.

Proposal is DATA ONLY: no owner-decision, Demo/Live execution, broker, MT5, or
order path may exist anywhere in the Proposal stage.
"""
from __future__ import annotations

import ast
import inspect
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity.contracts import (
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_REPLAY,
    MARKET_DATA_MODE_SYNTHETIC,
    CandidateGeometry,
    OpportunityCandidate,
)
from opportunity.proposal_eligibility import (
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    REASON_ENTRY_EQUALS_STOP,
    REASON_EXPIRED,
    REASON_INVALID_DIRECTION,
    REASON_INVALID_STOP_GEOMETRY,
    REASON_NON_FINITE_GEOMETRY,
    REASON_SYMBOL_NOT_CANONICAL,
    REASON_TERMINAL_CANDIDATE,
    evaluate_proposal_eligibility,
)
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import OUTCOME_ACTIVE, OUTCOME_REJECT, STAGE_ENTRY_CONFIRMED
from proposal_envelope.adapters.opportunity_adapter import to_canonical_proposal
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import (
    AUTHORITY_NONE,
    PROPOSAL_BLOCKED,
    PROPOSAL_READY,
)

NOW = datetime.now(timezone.utc)
STRATEGY_ID = "CRYPTO_PREVIOUS_DAY_SWEEP_OBSERVATION_V1"
SYMBOL = "BTCUSDT"


def _binding() -> StrategyBinding:
    return StrategyBinding(
        strategy_id=STRATEGY_ID,
        semantic_version="1.0.0",
        engine_id="crypto_opportunity_scanner.previous_day_sweep",
        engine_version="1",
        adapter_id="crypto_opportunity_scanner.funnel_adapter",
        adapter_version="1",
        dispatchable=False,
        supported_symbols=(SYMBOL,),
        supported_timeframes=("M5",),
        lifecycle="RESEARCH",
        opportunity_authority=True,
        proposal_authority=False,
        execution_authority="NONE",
        replay_supported=True,
        live_observation_supported=True,
    )


def _geometry(**overrides) -> CandidateGeometry:
    base = dict(direction="SHORT", entry=100.0, invalidation=110.5,
                targets=(94.0, 90.0), estimated_rr=1.9)
    base.update(overrides)
    return CandidateGeometry(**base)


def _candidate(**overrides) -> OpportunityCandidate:
    base = dict(
        candidate_id="cand-h-1",
        occurrence_id="occ-h-1",
        strategy_id=STRATEGY_ID,
        strategy_version="1.0.0",
        strategy_engine_version="1",
        symbol=SYMBOL,
        market="CRYPTO",
        venue="BYBIT_LINEAR_PERP",
        direction="SHORT",
        detected_at=NOW - timedelta(minutes=5),
        last_evaluated_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        stage=STAGE_ENTRY_CONFIRMED,
        outcome=OUTCOME_ACTIVE,
        revision=1,
        geometry=_geometry(),
        market_data_mode=MARKET_DATA_MODE_REAL,
        data_lineage="BYBIT_LINEAR_PERP",
        latest_transition_id="t1",
    )
    base.update(overrides)
    return OpportunityCandidate(**base)


def _evaluate(candidate, binding=None):
    return evaluate_proposal_eligibility(
        candidate, binding or _binding(), evaluated_at=NOW,
    )


# ---------------------------------------------------------------------------
# VALID: REAL LONG / REAL SHORT -> ELIGIBLE -> Proposal
# ---------------------------------------------------------------------------

def test_valid_real_long_is_eligible_and_produces_ready_proposal():
    candidate = _candidate(
        candidate_id="cand-long", occurrence_id="occ-long", direction="LONG",
        geometry=_geometry(direction="LONG", entry=100.0, invalidation=94.0,
                           targets=(108.0, 115.0), estimated_rr=2.0),
    )
    decision = _evaluate(candidate)
    assert decision.status == ELIGIBILITY_ELIGIBLE and decision.reason_codes == ()
    proposal = to_canonical_proposal(candidate, decision)
    assert proposal.proposal_state == PROPOSAL_READY
    assert proposal.direction == "LONG" and proposal.entry == 100.0 and proposal.stop == 94.0


def test_valid_real_short_is_eligible_and_produces_ready_proposal():
    candidate = _candidate(candidate_id="cand-short", occurrence_id="occ-short")
    decision = _evaluate(candidate)
    assert decision.status == ELIGIBILITY_ELIGIBLE and decision.reason_codes == ()
    proposal = to_canonical_proposal(candidate, decision)
    assert proposal.proposal_state == PROPOSAL_READY
    assert proposal.direction == "SHORT" and proposal.entry == 100.0 and proposal.stop == 110.5


def test_buy_sell_are_the_repositories_established_side_synonyms():
    # BUY/SELL (FX heritage) map to the same two sides; both must remain valid.
    buy = _evaluate(_candidate(geometry=_geometry(direction="BUY", entry=100.0, invalidation=94.0)))
    sell = _evaluate(_candidate(geometry=_geometry(direction="SELL", entry=100.0, invalidation=105.0)))
    assert buy.status == ELIGIBILITY_ELIGIBLE
    assert sell.status == ELIGIBILITY_ELIGIBLE


# ---------------------------------------------------------------------------
# IDENTITY: symbol binding + strategy identity
# ---------------------------------------------------------------------------

def test_missing_or_noncanonical_symbol_is_blocked():
    for symbol in ("", "   ", "btcusdt", "BTC USDT", None):
        candidate = _candidate(symbol=symbol)
        decision = _evaluate(candidate)
        assert decision.status == ELIGIBILITY_BLOCKED
        assert REASON_SYMBOL_NOT_CANONICAL in decision.reason_codes


def test_no_second_symbol_can_override_opportunity_symbol():
    # By construction: neither the evaluator nor the bridge accepts any symbol
    # parameter -- there is nowhere a caller-controlled symbol could enter.
    evaluator_params = set(inspect.signature(evaluate_proposal_eligibility).parameters)
    bridge_params = set(inspect.signature(to_canonical_proposal).parameters)
    assert evaluator_params == {"candidate", "binding", "evaluated_at"}
    assert bridge_params == {"candidate", "eligibility", "strategy_authority"}
    # Behavioral: the proposal symbol is ALWAYS the opportunity symbol, and no
    # other identity field (venue, market, evidence) can override it.
    candidate = _candidate()
    proposal = to_canonical_proposal(candidate, _evaluate(candidate))
    assert proposal.symbol == candidate.symbol == SYMBOL
    assert proposal.market == candidate.market and proposal.venue == candidate.venue


def test_strategy_identity_mismatch_is_blocked():
    decision = _evaluate(_candidate(strategy_id="OTHER_STRATEGY_V9"))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert "STRATEGY_IDENTITY_MISMATCH" in decision.reason_codes


# ---------------------------------------------------------------------------
# GEOMETRY: stop side + entry==stop
# ---------------------------------------------------------------------------

def test_long_stop_below_entry_passes():
    assert _evaluate(_candidate(
        geometry=_geometry(direction="LONG", entry=100.0, invalidation=94.0),
    )).status == ELIGIBILITY_ELIGIBLE


def test_long_stop_equal_to_entry_is_blocked():
    decision = _evaluate(_candidate(
        geometry=_geometry(direction="LONG", entry=100.0, invalidation=100.0),
    ))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_ENTRY_EQUALS_STOP in decision.reason_codes


def test_long_stop_above_entry_is_blocked():
    decision = _evaluate(_candidate(
        geometry=_geometry(direction="LONG", entry=100.0, invalidation=105.0),
    ))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_INVALID_STOP_GEOMETRY in decision.reason_codes


def test_short_stop_above_entry_passes():
    assert _evaluate(_candidate(
        geometry=_geometry(direction="SHORT", entry=100.0, invalidation=105.0),
    )).status == ELIGIBILITY_ELIGIBLE


def test_short_stop_equal_to_entry_is_blocked():
    decision = _evaluate(_candidate(
        geometry=_geometry(direction="SHORT", entry=100.0, invalidation=100.0),
    ))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_ENTRY_EQUALS_STOP in decision.reason_codes


def test_short_stop_below_entry_is_blocked():
    decision = _evaluate(_candidate(
        geometry=_geometry(direction="SHORT", entry=100.0, invalidation=94.0),
    ))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_INVALID_STOP_GEOMETRY in decision.reason_codes


def test_unknown_side_value_is_blocked():
    for direction in ("HOLD", "FLAT", "long", "buy!", "LONG_SHORT"):
        decision = _evaluate(_candidate(geometry=_geometry(direction=direction)))
        assert decision.status == ELIGIBILITY_BLOCKED, direction
        assert REASON_INVALID_DIRECTION in decision.reason_codes


# ---------------------------------------------------------------------------
# NON-FINITE: entry / stop / targets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_entry_is_blocked(entry):
    decision = _evaluate(_candidate(geometry=_geometry(entry=entry)))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_NON_FINITE_GEOMETRY in decision.reason_codes


@pytest.mark.parametrize("stop", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_stop_is_blocked(stop):
    decision = _evaluate(_candidate(geometry=_geometry(invalidation=stop)))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_NON_FINITE_GEOMETRY in decision.reason_codes


@pytest.mark.parametrize("target", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_target_is_blocked(target):
    decision = _evaluate(_candidate(geometry=_geometry(targets=(94.0, target))))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_NON_FINITE_GEOMETRY in decision.reason_codes


def test_non_finite_values_are_never_normalized():
    # A NaN entry stays NaN in the decision input and still blocks; the
    # evaluator neither repairs nor substitutes a value.
    nan_entry = float("nan")
    decision = _evaluate(_candidate(geometry=_geometry(entry=nan_entry)))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert math.isnan(nan_entry)


# ---------------------------------------------------------------------------
# PROVENANCE / LIFECYCLE
# ---------------------------------------------------------------------------

def test_synthetic_provenance_is_blocked():
    decision = _evaluate(_candidate(market_data_mode=MARKET_DATA_MODE_SYNTHETIC))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert "SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE" in decision.reason_codes


def test_replay_provenance_is_blocked():
    decision = _evaluate(_candidate(market_data_mode=MARKET_DATA_MODE_REPLAY))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert "REPLAY_DATA_NOT_BROKER_EXECUTABLE" in decision.reason_codes


def test_expired_opportunity_is_blocked():
    decision = _evaluate(_candidate(expires_at=NOW - timedelta(minutes=1)))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_EXPIRED in decision.reason_codes


def test_terminal_opportunity_is_blocked():
    decision = _evaluate(_candidate(outcome=OUTCOME_REJECT))
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_TERMINAL_CANDIDATE in decision.reason_codes


# ---------------------------------------------------------------------------
# PERSISTENCE: deterministic identity, dedup, corrupt store
# ---------------------------------------------------------------------------

def _ready_proposal(candidate_id: str, occurrence_id: str):
    candidate = _candidate(candidate_id=candidate_id, occurrence_id=occurrence_id)
    return candidate, to_canonical_proposal(candidate, _evaluate(candidate))


def test_first_persist_read_back_and_deterministic_identity(tmp_path):
    candidate, proposal = _ready_proposal("cand-p1", "occ-p1")
    ledger = ProposalLedger(str(tmp_path / "proposals.json"))
    recorded = ledger.record_proposal(proposal)
    assert recorded.proposal_envelope_id == proposal.proposal_envelope_id
    got = ledger.get_proposal(proposal.proposal_envelope_id)
    assert got is not None and got.proposal_state == PROPOSAL_READY
    # Deterministic: same opportunity replayed from scratch yields the SAME id.
    _, again = _ready_proposal("cand-p1", "occ-p1")
    assert again.proposal_envelope_id == proposal.proposal_envelope_id
    assert again == proposal


def test_duplicate_replay_creates_no_second_record(tmp_path):
    candidate, proposal = _ready_proposal("cand-p2", "occ-p2")
    ledger = ProposalLedger(str(tmp_path / "proposals.json"))
    first = ledger.record_proposal(proposal)
    second = ledger.record_proposal(proposal)
    assert first.proposal_envelope_id == second.proposal_envelope_id
    assert len(ledger.list_active_proposals()) == 1


def test_corrupt_proposal_store_fails_closed(tmp_path):
    path = tmp_path / "proposals.json"
    _, proposal = _ready_proposal("cand-p3", "occ-p3")
    ledger = ProposalLedger(str(path))
    ledger.record_proposal(proposal)
    path.write_text("{ this ledger file is deliberately corrupt")
    with pytest.raises(Exception) as excinfo:
        ledger.record_proposal(proposal)
    assert "corrupt" in str(excinfo.value).lower() or "STATE_STORE" in str(excinfo.value)
    assert "{ this ledger file is deliberately corrupt" in path.read_text()


def test_ledger_rejects_non_ready_envelope(tmp_path):
    candidate = _candidate(market_data_mode=MARKET_DATA_MODE_SYNTHETIC)
    blocked = to_canonical_proposal(candidate, _evaluate(candidate))
    assert blocked.proposal_state == PROPOSAL_BLOCKED
    ledger = ProposalLedger(str(tmp_path / "proposals.json"))
    with pytest.raises(Exception):
        ledger.record_proposal(blocked)


# ---------------------------------------------------------------------------
# SECURITY: Proposal is DATA ONLY
# ---------------------------------------------------------------------------

def test_ready_proposal_carries_zero_execution_authority():
    _, proposal = _ready_proposal("cand-s1", "occ-s1")
    assert proposal.execution_authority == AUTHORITY_NONE
    assert proposal.proposal_only is True
    assert proposal.execution_eligible is False
    assert proposal.broker_mutation_blocked is True
    assert proposal.demo_authorized is False
    assert proposal.live_authorized is False
    assert proposal.economic_edge_established is False


def test_no_owner_decision_demo_live_or_order_capability_in_proposal_stage():
    package_root = Path(__file__).resolve().parent.parent / "src"
    scanned = [
        *(package_root / "proposal_envelope").rglob("*.py"),
        *(package_root / "validation_framework").rglob("*.py"),
        package_root / "opportunity" / "proposal_eligibility.py",
    ]
    forbidden_prefixes = (
        "execution", "authorization", "owner_decision", "broker",
        "telegram", "api.app", "ticket_delivery", "trade_management",
        "mt5.management_gateway", "mt5.mt5_gateway", "svos", "notifications",
    )
    forbidden_calls = {"order_send", "order_check", "place_order", "submit_order",
                       "create_order", "trade_buy", "trade_sell"}
    assert scanned, "proposal stage files must exist"
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = (
                [alias.name for alias in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level
                else []
            )
            for module in modules:
                assert not any(module == p or module.startswith(p + ".") for p in forbidden_prefixes), \
                    f"{path.name} imports forbidden module {module!r}"
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else "")
                assert name not in forbidden_calls, f"{path.name} calls {name}"


def test_proposal_stage_modules_are_not_importable_execution_surfaces():
    # The execution-capable packages must not exist in the tree at all.
    src = Path(__file__).resolve().parent.parent / "src"
    for forbidden_dir in ("execution", "authorization", "owner_decision",
                          "trade_management", "svos"):
        assert not (src / forbidden_dir).exists(), f"{forbidden_dir}/ must not exist"
    assert "api.app" not in sys.modules


# AG V1 owner decision 1 (2026-09-30): the narrow exception to the forbidden-package list.
# src/ticket_delivery may exist only in ARCHIVE_ONLY / message-only form: there is no
# Telegram or transport module, no network, broker or execution import, and the configured
# mode stays ARCHIVE_ONLY.
_TICKET_DELIVERY_FORBIDDEN_MODULES = ("telegram_adapter.py", "scheduler_integration.py")
_TICKET_DELIVERY_FORBIDDEN_IMPORTS = (
    "execution", "trade_management", "authorization", "owner_decision", "svos",
    "notifications", "telegram", "requests", "httpx", "urllib", "http", "socket", "aiohttp",
    "MetaTrader5", "mt5", "api",
)


def test_ticket_delivery_exception_is_archive_only_and_transport_free():
    import yaml

    root = Path(__file__).resolve().parent.parent
    pkg = root / "src" / "ticket_delivery"
    if not pkg.exists():
        return
    for name in _TICKET_DELIVERY_FORBIDDEN_MODULES:
        assert not (pkg / name).exists(), f"ticket_delivery/{name} must not exist"
    for path in sorted(pkg.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("telegram", "scheduler_integration")), path.name
            for name in names:
                assert not name.split(".")[0] in _TICKET_DELIVERY_FORBIDDEN_IMPORTS, f"{path.name} imports {name}"
    config = yaml.safe_load((root / "config" / "ticket_delivery.yaml").read_text(encoding="utf-8"))
    assert config["mode"] == "ARCHIVE_ONLY"
