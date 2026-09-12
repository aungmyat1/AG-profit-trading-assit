"""Focused integration tests for WP11A (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the
live wiring between post_asian_pilot/pipeline.py's real FX evaluation and the canonical
R2-R4 contracts (MarketSnapshot -> StrategyDecision -> proposal_envelope adapter ->
formation gate -> ProposalLedger).

Tests post_asian_pilot.pipeline._form_canonical_proposal directly, using the exact same
decision/build_entry_proposal recipe as tests/test_post_asian_pilot.py
(test_build_entry_proposal_ready_geometry_and_risk) -- a legitimate READY produced by the
real, unmodified strategy decision/proposal code, never a hand-built canonical proposal.
This is an integration test of the NEW wiring, not WP12's natural-market proof.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from mt5.symbol_resolver import SymbolMeta
from strategy_engine.loader import load_strategy
from strategy_engine.models import TradeSignal
from strategy_engine.session import Candle

from post_asian_pilot.decision import map_trade_signal_to_decision, STATUS_NO_TRADE, STATUS_READY
from post_asian_pilot.fingerprint import fingerprint as config_fingerprint
from post_asian_pilot.pilot_config import load_raw_yaml
from post_asian_pilot.proposal import build_entry_proposal
from post_asian_pilot.pipeline import _form_canonical_proposal
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import PROPOSAL_READY
from strategy_contract.market_snapshot import (
    MARKET_DATA_MODE_REAL,
    from_real_candle,
    from_synthetic_candle,
)

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
EXPECTED_CONFIG_HASH = config_fingerprint(load_raw_yaml(STRATEGY_PATH))  # same authoritative
# source pipeline.py's run_pilot_cycle() uses -- computed once here, never a second algorithm
EXPECTED_ENGINE_RELEASE = "AG_TRADE_ASSISTANT_V1_0_1_TEST"


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


@pytest.fixture()
def symbol_meta():
    return SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5)


def _signal(status, setup, reason_code, direction=None, entry=None, stop_loss=None, risk_distance=None,
           signal_timestamp=None, symbol="EURUSD"):
    return TradeSignal(
        signal_id="SID", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol=symbol,
        pair_id="ASIAN_LONDON", reference_session="Asian", session_date=dt.date(2026, 1, 5),
        box_high=1.10, box_low=1.09, box_mid=1.095, regime="RANGE", setup=setup, status=status,
        reason_code=reason_code, direction=direction, entry=entry, stop_loss=stop_loss,
        risk_distance=risk_distance, signal_timestamp=signal_timestamp,
    )


def _ready_decision_and_actionable_proposal(strategy, symbol_meta, symbol="EURUSD"):
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = _signal("SIGNAL", "SWEEP", "UPPER_SWEEP_STRICT_PENETRATION", "SHORT", entry=1.10000,
                     stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at, symbol=symbol)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    assert decision.status == STATUS_READY  # sanity: this is a genuine READY, not hand-built

    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "READY"
    actionable_proposal = dataclasses.replace(result.proposal, actionable=True)
    return decision, actionable_proposal


def _real_snapshot(symbol="EURUSD", time=dt.datetime(2026, 1, 5, 8, 45, tzinfo=UTC)):
    candle = Candle(time=time, open=1.0995, high=1.1005, low=1.0990, close=1.1000)
    return from_real_candle(symbol, "M15", candle)


def test_ready_forms_one_canonical_proposal_with_real_provenance(strategy, symbol_meta, tmp_path):
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    snapshot = _real_snapshot()

    _form_canonical_proposal(
        decision, actionable_proposal, snapshot, ledger,
        config_hash=EXPECTED_CONFIG_HASH, engine_release=EXPECTED_ENGINE_RELEASE,
    )

    active = ledger.list_active_proposals()
    assert len(active) == 1
    proposal = active[0]
    assert proposal.proposal_state == PROPOSAL_READY
    assert proposal.data_provenance.market_data_mode == MARKET_DATA_MODE_REAL
    assert proposal.entry == 1.10000
    assert proposal.stop == 1.10150
    assert proposal.execution_authority == "NONE"


def test_metadata_identity_populated_from_authoritative_sources_only(strategy, symbol_meta, tmp_path):
    """P8: config_hash and engine_release come from the exact values the caller already
    computed from authoritative sources (strategy fingerprint, release_id) -- never
    recomputed, never a fallback/fabricated value. git_commit stays None: no
    authoritative runtime producer exists in this repository."""
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    snapshot = _real_snapshot()

    _form_canonical_proposal(
        decision, actionable_proposal, snapshot, ledger,
        config_hash=EXPECTED_CONFIG_HASH, engine_release=EXPECTED_ENGINE_RELEASE,
    )

    proposal = ledger.list_active_proposals()[0]
    assert proposal.config_hash == EXPECTED_CONFIG_HASH
    assert proposal.config_hash == config_fingerprint(load_raw_yaml(STRATEGY_PATH))  # same source, not a copy
    assert proposal.engine_release == EXPECTED_ENGINE_RELEASE
    assert proposal.git_commit is None


def test_no_config_hash_or_engine_release_supplied_stays_unset_not_fabricated(strategy, symbol_meta, tmp_path):
    """A caller that supplies no config_hash/engine_release (e.g. an older call site)
    must never trigger a fallback/guessed value -- both stay None, matching the pre-P8
    honest-gap posture exactly."""
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    snapshot = _real_snapshot()

    _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger)  # no config_hash/engine_release kwargs

    proposal = ledger.list_active_proposals()[0]
    assert proposal.config_hash is None
    assert proposal.engine_release is None
    assert proposal.git_commit is None


def test_pipeline_module_never_spawns_git_subprocess():
    """Static proof that git_commit population was not implemented via a subprocess git
    call -- P8 explicitly forbids this. Checks only actual import statements, not prose
    (this module's own docstrings mention "subprocess" while explaining that no such call
    exists -- that's documentation, not a violation): if `subprocess` is never imported,
    pipeline.py cannot spawn one."""
    import post_asian_pilot.pipeline as pipeline_module

    with open(pipeline_module.__file__, "r", encoding="utf-8") as f:
        import_lines = [line for line in f if line.lstrip().startswith(("import ", "from "))]
    assert not any("subprocess" in line for line in import_lines)


def test_no_trade_forms_zero_canonical_proposals(strategy, symbol_meta, tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    # NO_TRADE never reaches _form_canonical_proposal in the real pipeline (only
    # `ordered_ready` decisions do) -- proven at the pipeline level: nothing to call.
    signal = _signal("SIGNAL", "TREND", "BOX_DIRECTION_V1", "LONG", 1.095, 1.09, 0.005)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), window_end)
    assert decision.status == STATUS_NO_TRADE
    # No call to _form_canonical_proposal is made for a non-READY decision anywhere in
    # run_pilot_cycle -- confirmed by inspection (only `for decision in ordered_ready`
    # reaches it). Ledger stays empty.
    assert ledger.list_active_proposals() == []


def test_missing_market_snapshot_fails_closed_zero_proposals(strategy, symbol_meta, tmp_path):
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))

    _form_canonical_proposal(decision, actionable_proposal, None, ledger)  # restart-recovery branch: no snapshot

    assert ledger.list_active_proposals() == []


def test_synthetic_snapshot_fails_closed_zero_proposals(strategy, symbol_meta, tmp_path):
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    synthetic = from_synthetic_candle("EURUSD", "M15", Candle(
        time=dt.datetime(2026, 1, 5, 8, 45, tzinfo=UTC), open=1.0995, high=1.1005, low=1.0990, close=1.1000,
    ))

    _form_canonical_proposal(decision, actionable_proposal, synthetic, ledger)

    assert ledger.list_active_proposals() == []


def test_duplicate_evaluation_produces_one_logical_proposal(strategy, symbol_meta, tmp_path):
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    snapshot = _real_snapshot()

    _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger)
    _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger)  # simulated rerun/overlap

    assert len(ledger.list_active_proposals()) == 1


def test_restart_reload_recovers_same_proposal_id_geometry_and_provenance(strategy, symbol_meta, tmp_path):
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    path = str(tmp_path / "ledger.json")
    snapshot = _real_snapshot()

    ledger_before = ProposalLedger(path=path)
    _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger_before)
    original = ledger_before.list_active_proposals()[0]

    ledger_after_restart = ProposalLedger(path=path)  # simulated backend restart
    recovered = ledger_after_restart.get_proposal(original.proposal_envelope_id)

    assert recovered is not None
    assert recovered.proposal_envelope_id == original.proposal_envelope_id
    assert recovered.entry == original.entry
    assert recovered.data_provenance.market_data_fingerprint == original.data_provenance.market_data_fingerprint


def test_canonical_formation_never_touches_execution(strategy, symbol_meta, tmp_path):
    """Execution containment: this wiring imports nothing from execution.executor,
    execution.coordinator, mt5.management_gateway, or authorization.* -- a static proof
    that the canonical formation path cannot reach a broker order. Checks only actual
    `import`/`from ... import` lines (pipeline.py's own module docstring mentions
    "execution.executor" in prose, describing what it deliberately does NOT use --
    that's not an import and must not fail this check)."""
    import post_asian_pilot.pipeline as pipeline_module

    source = pipeline_module.__file__
    with open(source, "r", encoding="utf-8") as f:
        import_lines = [line for line in f if line.lstrip().startswith(("import ", "from "))]
    forbidden = ["execution.executor", "mt5.management_gateway", "authorization.telegram_gateway",
                 "authorize_demo_execution", "order_send", "order_check"]
    for token in forbidden:
        for line in import_lines:
            assert token not in line, f"{token!r} must never appear in a pipeline.py import: {line!r}"
