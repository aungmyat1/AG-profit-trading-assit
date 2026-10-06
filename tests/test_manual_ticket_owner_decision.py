"""Manual Trade Ticket V1 Phase 6: append-only owner decisions on manual tickets."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from v1_tickets import manual_ticket as mt
from v1_tickets.owner_decision import (
    DecisionError, ManualTicketDecision, decision_path, decision_ticket, expire_undecided, load_decisions,
    record_decision,
)
from v1_tickets.scan_record import read_jsonl

from test_manual_ticket_build import META, OWNER, l2_pass, manual  # noqa: F401  (fixtures)

UTC = dt.timezone.utc
DAY = dt.date(2026, 6, 17)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import manual_ticket_decision as cli  # noqa: E402


@pytest.fixture
def ready(tmp_path, l2_pass):  # noqa: F811
    journal = str(tmp_path / "j")
    t = manual(owner=OWNER, balance=10000.0, meta=META)
    assert t["state"] == "TICKET_READY"
    mt.archive_manual_ticket(journal, t)
    later = manual(at="07:31", owner=OWNER, balance=10000.0, meta=META)          # same ticket, now expired
    mt.archive_manual_ticket(journal, later)
    return journal, decision_ticket(journal, t["ticket_id"], DAY)


def _d(tid, **kw):
    return ManualTicketDecision(ticket_id=tid, recorded_at="2026-06-17T08:00:00+00:00", **kw)


def test_taken_records_actual_fill_and_is_append_only(ready):
    journal, t = ready
    assert t["state"] == "TICKET_READY"                                  # the READY version the owner saw
    e = record_decision(journal, t, _d(t["ticket_id"], decision="TAKEN", fill_time="2026-06-17T07:22:00+00:00",
                                       actual_fill=1.16080, actual_sl=1.16061, deviation_note="slippage 0.5 pip"))
    assert e["decision"] == "TAKEN" and e["ticket_state"] == "TICKET_READY"
    with pytest.raises(DecisionError, match="ALREADY_RECORDED"):
        record_decision(journal, t, _d(t["ticket_id"], decision="SKIPPED", skip_reason="NEWS"))
    assert len(read_jsonl(decision_path(journal))) == 1


def test_taken_after_valid_until_is_refused(ready):
    journal, t = ready
    with pytest.raises(DecisionError, match="EXPIRED"):
        record_decision(journal, t, _d(t["ticket_id"], decision="TAKEN", fill_time="2026-06-17T07:30:00+00:00",
                                       actual_fill=1.1608, actual_sl=1.16061))


def test_taken_refused_for_blocked_ticket(tmp_path):
    journal = str(tmp_path / "j")
    t = manual()                                                          # real v1.1.1: L2 blocks
    mt.archive_manual_ticket(journal, t)
    with pytest.raises(DecisionError, match="not TICKET_READY"):
        record_decision(journal, t, _d(t["ticket_id"], decision="TAKEN", fill_time="2026-06-17T07:21:00+00:00",
                                       actual_fill=1.1608, actual_sl=1.16061))
    # A blocked ticket can still be recorded as skipped / missed (shadow evidence).
    record_decision(journal, t, _d(t["ticket_id"], decision="SKIPPED", skip_reason="DISAGREE_CONTEXT"))


@pytest.mark.parametrize("kw,msg", [
    (dict(decision="SKIPPED"), "skip_reason"), (dict(decision="SKIPPED", skip_reason="OTHER"), "note"),
    (dict(decision="TAKEN", actual_fill=1.1), "fill_time"), (dict(decision="MISSED", actual_fill=1.1), "fill prices"),
    (dict(decision="MAYBE"), "not in"),
])
def test_contract_validation(kw, msg):
    with pytest.raises(DecisionError, match=msg):
        _d("x", **kw)


def test_auto_expiry_only_after_valid_until_and_only_once(ready):
    journal, t = ready
    rows = read_jsonl(mt.ticket_path(journal, DAY))
    assert expire_undecided(journal, rows, dt.datetime(2026, 6, 17, 7, 29, tzinfo=UTC)) == []
    out = expire_undecided(journal, rows, dt.datetime(2026, 6, 17, 7, 30, tzinfo=UTC))
    assert [e["decision"] for e in out] == ["EXPIRED"] and out[0]["source"] == "AUTO_EXPIRY"
    assert expire_undecided(journal, rows, dt.datetime(2026, 6, 17, 9, 0, tzinfo=UTC)) == []
    assert load_decisions(journal)[t["ticket_id"]]["decision"] == "EXPIRED"


def test_cli_records_skip(ready, capsys):
    journal, t = ready
    rc = cli.main(["--date", "2026-06-17", "--journal", journal, "--ticket-id", t["ticket_id"],
                   "--decision", "SKIPPED", "--reason", "COST_TOO_HIGH"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["skip_reason"] == "COST_TOO_HIGH"
    assert cli.main(["--date", "2026-06-17", "--journal", journal, "--ticket-id", t["ticket_id"],
                     "--decision", "MISSED"]) == 2                          # append-only refusal
