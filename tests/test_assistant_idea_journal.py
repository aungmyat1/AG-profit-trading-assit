"""decision_snapshot / realized_outcome separation (spec sections 26-28): WAIT and
TRADE_PROPOSAL_READY results both get journaled; a later realized_outcome is a new
appended line under the same idea_id, never a mutation of the original decision line."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from assistant import idea_journal
from daytrading.models import (
    AFFINITY_RESOLVED,
    BIAS_BULLISH,
    STATE_TRADE_READY_LONG,
    STATE_WAIT_AFFINITY,
    DayTradingLiquidityAffinityResult,
    DayTradingResult,
    NarrativeBiasResult,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _narrative():
    return NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH,
                                status="OK", evaluation_time=T0)


def _wait_result():
    return DayTradingResult(symbol="EURUSD", narrative_bias=_narrative(), trade_state=STATE_WAIT_AFFINITY)


def _trade_ready_result():
    affinity = DayTradingLiquidityAffinityResult(symbol="EURUSD", narrative_bias=BIAS_BULLISH, status=AFFINITY_RESOLVED)
    return DayTradingResult(symbol="EURUSD", narrative_bias=_narrative(), liquidity_affinity=affinity,
                             trade_state=STATE_TRADE_READY_LONG, direction="LONG")


def test_wait_result_is_journaled(tmp_path):
    path = str(tmp_path / "trade_ideas.jsonl")
    idea_journal.record_decision("DAYTRADING", "EURUSD", T0, _wait_result(), "WAIT_POI", "waiting.", path=path)

    entries = idea_journal.read_all(path)
    assert len(entries) == 1
    assert entries[0]["kind"] == idea_journal.KIND_DECISION_SNAPSHOT
    assert entries[0]["canonical_state"] == "WAIT_POI"
    assert entries[0]["symbol"] == "EURUSD"


def test_trade_proposal_ready_result_is_journaled(tmp_path):
    path = str(tmp_path / "trade_ideas.jsonl")
    idea_journal.record_decision("DAYTRADING", "EURUSD", T0, _trade_ready_result(), "TRADE_PROPOSAL_READY", path=path)

    entries = idea_journal.read_all(path)
    assert entries[0]["canonical_state"] == "TRADE_PROPOSAL_READY"
    assert entries[0]["direction"] == "LONG"


def test_realized_outcome_is_a_separate_line_never_a_mutation(tmp_path):
    path = str(tmp_path / "trade_ideas.jsonl")
    idea_id = idea_journal.record_decision("DAYTRADING", "EURUSD", T0, _wait_result(), "WAIT_POI", path=path)

    with open(path, "r", encoding="utf-8") as f:
        original_line = f.readline()

    idea_journal.record_realized_outcome(idea_id, executed=False, notes="never confirmed", path=path)

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 2
    assert lines[0] == original_line  # original decision_snapshot line untouched

    entries = idea_journal.read_all(path)
    decision, outcome = entries
    assert decision["kind"] == idea_journal.KIND_DECISION_SNAPSHOT
    assert outcome["kind"] == idea_journal.KIND_REALIZED_OUTCOME
    assert outcome["idea_id"] == decision["idea_id"] == idea_id
    assert outcome["executed"] is False
