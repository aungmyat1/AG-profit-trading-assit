"""AGP-C18-R2 PR C: governed REPORT_ONLY Telegram delivery (synthetic transport only).

ASCII rendering, tracked-scope gating (OD1013-C18-REPORT-SCOPE), ledger dedupe, failure without
automatic retry, INTENT/RESULT evidence with message ids, and the once-per-day strategy summary.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from reporting.deliver import deliver_observations
from telegram_delivery import scope_policy
from telegram_delivery.adapter import Config, Sender, render_report, report_identity

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
import canonical_fx_delivery as cfd  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
SCOPES = frozenset({"TICKET_READY", "LSMC_OPPORTUNITY", "REPORT_CANDIDATE", "REPORT_BLOCKED", "REPORT_WATCH"})


def sender(tmp_path, *, scopes=SCOPES, transport=None, calls=None):
    calls = [] if calls is None else calls

    def fake(token, chat_id, message):
        calls.append(message)
        return {"ok": True, "message_id": len(calls), "chat_id": chat_id}
    fake.returns_telegram_receipt = True
    cfg = Config(enabled=True, token="t", chat_id="1", owner_chat_ids=frozenset({"1"}), immediate_scopes=scopes)
    return Sender(tmp_path / "d.sqlite", cfg, transport or fake, sleep=lambda *_: None), calls


def obs(report_class="CANDIDATE", **extra):
    c = {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.2", "instrument": "USDJPY",
         "session": "ASIAN_LONDON", "direction": "LONG", "report_class": report_class, "scope_route": "REPORT_ONLY",
         "scope_verification_status": "UNVERIFIED", "scope_reason": "LOGIC_NOT_VERIFIED", "ticket_id": "tid",
         "reason_code": "REPORT_ONLY_OBSERVATION", "reason_codes": ["C10_PIP_SIZE_NOT_EVIDENCED"],
         "trigger": {"trigger_timestamp": "2026-10-13T07:45:00+00:00"},
         "prices": {"entry_reference": "150.100", "sl": "149.900", "tp1": "150.600", "tp2": None},
         "candidate_signal_id": "ST_ASIAN_SWEEP_5R_V1@1.1.2|USDJPY|ASIAN_LONDON|LONG|2026-10-13T07:45:00+00:00"}
    c.update(extra)
    return c


def test_tracked_policy_enables_report_scopes_and_local_override_only_narrows(tmp_path):
    tracked = scope_policy.resolve(ROOT)["tracked"]
    assert {"REPORT_CANDIDATE", "REPORT_BLOCKED", "REPORT_WATCH"} <= set(tracked)
    local = tmp_path / "config" / "local"
    local.mkdir(parents=True)
    (local / "delivery_override.yaml").write_text("immediate_send_scopes: [TICKET_READY]\n", encoding="utf-8")
    narrowed = scope_policy.resolve(tmp_path)
    assert "REPORT_CANDIDATE" not in narrowed["effective"] and narrowed["error"] is None


@pytest.mark.parametrize("cls,needle", [("CANDIDATE", "entry: 150.100  stop: 149.900"), ("BLOCKED", "blocked: C10_PIP_SIZE"),
                                        ("WATCH", "state: REPORT_ONLY_OBSERVATION")])
def test_render_report_is_ascii_and_report_only(cls, needle):
    text = render_report(obs(cls))
    assert text.isascii() and "REPORT ONLY -- NOT A BROKER ORDER" in text.splitlines()[0] and needle in text
    assert text.endswith("EXECUTION: DISABLED")
    with pytest.raises(ValueError):
        render_report(obs(cls, scope_route="DEMO_ORDER"))


def test_send_report_dedupes_and_gates_by_scope(tmp_path):
    s, calls = sender(tmp_path)
    assert s.send_report(obs()) == "sent"
    assert s.send_report(obs()) == "duplicate" and len(calls) == 1
    assert s.send_report(obs("NO_OPPORTUNITY")) == "summary_only"
    narrow, _ = sender(tmp_path / "n", scopes=frozenset({"TICKET_READY"}))
    (tmp_path / "n").mkdir(exist_ok=True)
    assert narrow.send_report(obs()) == "summary_only"
    empty, _ = sender(tmp_path / "e", scopes=frozenset())
    (tmp_path / "e").mkdir(exist_ok=True)
    assert empty.send_report(obs()) == "summary_only"                  # empty scope fails closed


def test_failed_transport_is_recorded_and_not_retried(tmp_path):
    def broken(*_):
        raise OSError("network down")
    s, _ = sender(tmp_path, transport=broken)
    first = deliver_observations([obs()], sender=s, journal=str(tmp_path), now=NOW, label="X")
    second = deliver_observations([obs()], sender=s, journal=str(tmp_path), now=NOW, label="X")
    rows = [json.loads(line) for line in
            (tmp_path / "ticket_delivery" / "report_lane" / "delivery_2026-10-13.jsonl").read_text().splitlines()]
    results = [r for r in rows if r["stage"] == "RESULT"]
    assert results[0]["delivery_state"] != "sent" and results[0]["telegram_message_id"] is None
    assert results[1]["delivery_state"] != "sent"                         # no silent resend after failure
    assert first[0].startswith("REPORT_DELIVERY X") and second[0].startswith("REPORT_DELIVERY X")


def test_delivery_evidence_has_intent_result_and_message_id(tmp_path):
    s, _ = sender(tmp_path)
    deliver_observations([obs(), obs("NO_OPPORTUNITY")], sender=s, journal=str(tmp_path), now=NOW)
    rows = [json.loads(line) for line in
            (tmp_path / "ticket_delivery" / "report_lane" / "delivery_2026-10-13.jsonl").read_text().splitlines()]
    assert [r["stage"] for r in rows] == ["INTENT", "RESULT"]           # NO_OPPORTUNITY is summary-only
    assert rows[1]["delivery_state"] == "sent" and rows[1]["telegram_message_id"] == "1"
    assert rows[1]["identity"] == report_identity(obs()) and rows[1]["execution_authorized"] is False


def test_daily_report_summary_counts_distinct_and_flags_no_opportunity(tmp_path):
    lane = tmp_path / "ticket_delivery" / "archive" / "report_lane"
    lane.mkdir(parents=True)
    rows = [obs("CANDIDATE"), obs("CANDIDATE"), obs("BLOCKED", candidate_signal_id=None)]
    (lane / "2026-10-13_session_fx_gold.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    s, calls = sender(tmp_path)
    summary = cfd.build_daily_report_summary(str(tmp_path), session_date=NOW.date(), sender=s)
    assert summary["families"]["session_fx_gold"]["counts"] == {"BLOCKED": 1, "CANDIDATE": 1}
    assert summary["families"]["crypto_cfd"]["counts"] == {}
    assert cfd.process_due_daily_report_summaries(NOW, journal=str(tmp_path), sender=s) == []   # start only
    due = dt.datetime(2026, 10, 14, 0, 31, tzinfo=UTC)
    assert cfd.process_due_daily_report_summaries(due, journal=str(tmp_path), sender=s) == [
        "DAILY_REPORT_SUMMARY 2026-10-13 DAILY_REPORT status=COMPLETE delivery=sent"]
    assert cfd.process_due_daily_report_summaries(due, journal=str(tmp_path), sender=s) == []    # once
    assert "crypto_cfd: NO OPPORTUNITY" in calls[-1].replace("- ", "") and calls[-1].isascii()


def test_candidate_layout_matches_owner_example():
    c = obs("CANDIDATE", risk={"risk_distance": 0.2, "initial_R_tp1": 2.5, "initial_R_tp2": None},
            expires_at="2026-10-13T08:15:00+00:00", created_at="2026-10-13T08:00:00+00:00",
            venue="MT5_VT_MARKETS_DEMO", trigger={"trigger_bar_close_utc": "2026-10-13T07:45:00+00:00"})
    lines = render_report(c).splitlines()
    assert lines[:3] == ["INFORMATIONAL REPORT -- REPORT ONLY -- NOT A BROKER ORDER", "USDJPY LONG (ASIAN_LONDON)",
                         "ST_ASIAN_SWEEP_5R_V1 v1.1.2  report=CANDIDATE  scope=UNVERIFIED (LOGIC_NOT_VERIFIED)"]
    assert "signal close: 14:15 MMT / 07:45 UTC (2026-10-13)" in lines
    assert "entry: 150.100  stop: 149.900  risk: 20.0 pips" in lines
    assert "target leg 1 (OPPOSITE_SESSION_BOUNDARY, 75%): 150.600  = +2.50R" in lines
    assert "VALID UNTIL 14:45 MMT / 08:15 UTC (2026-10-13) -- STALE after; re-check before acting." in lines
    assert lines[-1] == "REPORT ONLY - NOT AN ORDER | EXECUTION: DISABLED" and "decision=READY" not in "\n".join(lines)
