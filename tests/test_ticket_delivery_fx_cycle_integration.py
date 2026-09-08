"""WP4.1/WP4.2 tests (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md).
Uses lightweight SimpleNamespace fixtures shaped like post_asian_pilot's real
PairResult/PostAsianDecision/PostAsianEntryProposal (only the specific attributes
ticket_delivery.fx_cycle_integration actually reads) -- decoupled from the full
pipeline object graph so these tests exercise archive-ordering/orchestration logic in
isolation, not strategy evaluation itself (which is out of scope and already tested
elsewhere).
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from post_asian_pilot.decision import (
    STATUS_BLOCKED,
    STATUS_DATA_ERROR,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
)
from post_asian_pilot.governor import PORTFOLIO_BLOCKED, PORTFOLIO_SELECTED
from ticket_delivery.archive import (
    CYCLE_STATE_BLOCKED,
    CYCLE_STATE_DATA_ERROR,
    CYCLE_STATE_NO_TRADE,
    CYCLE_STATE_READY,
    CYCLE_STATE_WATCH,
    ArchiveFailedError,
)
from ticket_delivery.delivery_store import TicketDeliveryStore
from ticket_delivery.fx_cycle_integration import process_pair_result
from ticket_delivery.models import STATE_NOT_APPLICABLE, STATE_READY_TO_DELIVER
from ticket_delivery.policy import REASON_OUTSIDE_CATCH_UP_WINDOW, REASON_PREMATURE, CatchUpPolicy

UTC = dt.timezone.utc
TRADING_DATE = dt.date(2026, 9, 8)


def _decision(status, reason_codes=("R1",), ready_at=None):
    return SimpleNamespace(status=status, reason_codes=reason_codes, evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC), ready_at=ready_at)


def _proposal(setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-08", actionable=True):
    return SimpleNamespace(setup_id=setup_id, actionable=actionable)


def _pair(symbol="EURUSD", decision_status=STATUS_READY, portfolio_state=PORTFOLIO_SELECTED, proposal=None, portfolio_reason_code=None, ready_at=None):
    return SimpleNamespace(
        symbol=symbol, decision=_decision(decision_status, ready_at=ready_at), portfolio_state=portfolio_state,
        portfolio_reason_code=portfolio_reason_code,
        proposal=proposal if proposal is not None else (_proposal() if decision_status == STATUS_READY else None),
    )


def _full_render_dict():
    return {
        "application": {"release_id": "AG_TRADE_ASSISTANT_V1_0_3"},
        "strategy": {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1"},
        "identity": {"proposal_id": "P1", "setup_id": "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-08"},
        "market": {"symbol": "EURUSD", "direction": "SHORT"},
        "entry": {"entry": 1.0822, "stop_loss": 1.0852, "tp1": 1.0792, "tp2_runner": 1.0762},
        "risk": {"risk_percent": 0.5, "normalized_volume": 0.05},
        "timing": {"created_at": "2026-09-08T07:45:00+00:00", "expires_at": "2026-09-08T11:00:00+00:00"},
        "evidence": {"reason_codes": ["UPPER_SWEEP"]},
    }


def _common_kwargs(tmp_path, delivery_store, deliver=None, render=None):
    return dict(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", application_release="AG_TRADE_ASSISTANT_V1_0_3",
        cycle="ASIAN_LONDON", trading_date=TRADING_DATE, delivery_store=delivery_store,
        render_entry_ticket_dict=render, deliver=deliver, archive_root=str(tmp_path / "archive"),
    )


# --------------------------------------------------------------------------- archive ordering / non-READY

@pytest.mark.parametrize("status,expected_cycle_state", [
    (STATUS_WATCH, CYCLE_STATE_WATCH),
    (STATUS_NO_TRADE, CYCLE_STATE_NO_TRADE),
    (STATUS_DATA_ERROR, CYCLE_STATE_DATA_ERROR),
    (STATUS_BLOCKED, CYCLE_STATE_BLOCKED),
])
def test_non_ready_states_archive_and_never_call_transport(tmp_path, status, expected_cycle_state):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    calls = []
    outcome = process_pair_result(_pair(decision_status=status), deliver=lambda *a: calls.append(a), **{k: v for k, v in _common_kwargs(tmp_path, store).items() if k != "deliver"})
    assert outcome.cycle_state == expected_cycle_state
    assert outcome.archived is True
    assert outcome.delivery_state == "NOT_APPLICABLE"
    assert calls == []  # zero transport calls
    assert store.get(outcome.logical_ticket_id).state == STATE_NOT_APPLICABLE


def test_ready_but_not_actionable_maps_to_blocked_not_ready():
    """A READY decision.status that never became actionable (governor/ledger blocked
    it) must archive as BLOCKED, not READY -- it never reaches delivery."""
    pair = _pair(decision_status=STATUS_READY, portfolio_state=PORTFOLIO_BLOCKED, proposal=_proposal(actionable=False), portfolio_reason_code="DAILY_LOSS_LIMIT")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        import pathlib
        tmp_path = pathlib.Path(tmp)
        store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
        outcome = process_pair_result(pair, **_common_kwargs(tmp_path, store))
        assert outcome.cycle_state == CYCLE_STATE_BLOCKED
        assert outcome.delivery_state == "NOT_APPLICABLE"


def test_archive_completes_before_delivery_claim_or_transport(tmp_path):
    """Positive proof of ordering: a READY pair with no `deliver` injected still gets
    archived AND registered as READY_TO_DELIVER -- the archive/registration steps
    happened, only the network call was skipped."""
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(_pair(), **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()))
    assert outcome.archived is True
    assert outcome.archive_path is not None
    assert outcome.delivery_state == "TRANSPORT_NOT_CONFIGURED"
    assert store.get(outcome.logical_ticket_id).state == STATE_READY_TO_DELIVER  # registered, never claimed


def test_archive_failure_produces_zero_transport_calls(tmp_path, monkeypatch):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    calls = []

    def _raise(*a, **k):
        raise ArchiveFailedError("simulated disk failure")

    import ticket_delivery.fx_cycle_integration as mod
    monkeypatch.setattr(mod, "archive_cycle_decision", _raise)

    outcome = process_pair_result(_pair(), deliver=lambda *a: calls.append(a), **{k: v for k, v in _common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()).items() if k != "deliver"})
    assert outcome.delivery_state == "ARCHIVE_FAILED"
    assert outcome.archived is False
    assert calls == []


def test_render_blocked_still_preserves_archive_and_makes_no_transport_call(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    calls = []
    incomplete = _full_render_dict()
    incomplete["entry"]["stop_loss"] = None  # a mandatory field, missing
    outcome = process_pair_result(_pair(), deliver=lambda *a: calls.append(a), **{k: v for k, v in _common_kwargs(tmp_path, store, render=lambda pair: incomplete).items() if k != "deliver"})
    assert outcome.archived is True
    assert outcome.delivery_state == "RENDER_BLOCKED"
    assert calls == []


# --------------------------------------------------------------------------- identity / idempotency

def test_repeated_identical_invocation_reuses_the_same_logical_ticket(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    kwargs = _common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict())
    first = process_pair_result(_pair(), **kwargs)
    second = process_pair_result(_pair(), **kwargs)
    assert first.logical_ticket_id == second.logical_ticket_id
    assert len(store._records.all()) == 1


def test_correction_never_overwrites_the_original_archive(tmp_path):
    """The archived CycleDecisionRecord captures decision identity/status/reason codes
    -- NOT the rendered ticket payload (archive happens strictly BEFORE rendering, per
    WP4.1's required ordering, so it cannot know the render content yet). A genuinely
    changed decision outcome (here: a different portfolio_reason_code on a re-run,
    e.g. the governor's block reason changed between two evaluations of the same
    occurrence) must produce a correction; the original file must stay untouched."""
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    kwargs = _common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict())
    blocked_pair = _pair(decision_status=STATUS_BLOCKED, proposal=None, portfolio_state=PORTFOLIO_BLOCKED, portfolio_reason_code="DAILY_LOSS_LIMIT")
    first = process_pair_result(blocked_pair, **kwargs)

    reevaluated_pair = _pair(decision_status=STATUS_BLOCKED, proposal=None, portfolio_state=PORTFOLIO_BLOCKED, portfolio_reason_code="OPEN_POSITION_LIMIT")
    second = process_pair_result(reevaluated_pair, **kwargs)

    assert second.archive_path != first.archive_path
    import json
    with open(first.archive_path, encoding="utf-8") as f:
        original = json.load(f)
    assert original["payload"]["portfolio_reason_code"] == "DAILY_LOSS_LIMIT"  # original untouched
    with open(second.archive_path, encoding="utf-8") as f:
        correction = json.load(f)
    assert correction["new_record"]["payload"]["portfolio_reason_code"] == "OPEN_POSITION_LIMIT"


def test_successful_delivery_end_to_end_via_injected_deliver(tmp_path):
    """Genuine end-to-end proof: uses the REAL telegram_adapter.deliver_informational_ticket
    (which itself calls store.claim_for_delivery()/mark_delivered()) against a mocked
    HTTP session -- not a bare fake that bypasses the store transitions."""
    from notifications.telegram_client import TelegramClient
    from ticket_delivery.telegram_adapter import TelegramDestinationConfig, deliver_informational_ticket

    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True, "result": {"message_id": 42}}

    class _FakeSession:
        def post(self, url, json=None, timeout=None):
            return _FakeResponse()

    client = TelegramClient("FAKE:TOKEN", session=_FakeSession())
    destination = TelegramDestinationConfig.from_values(bot_token="FAKE:TOKEN", chat_id=999, authorized_chat_ids=[999])

    def real_deliver(ticket_id, message_text):
        assert "INFORMATIONAL PROPOSAL" in message_text
        return deliver_informational_ticket(store=store, logical_ticket_id=ticket_id, message_text=message_text, client=client, destination=destination)

    outcome = process_pair_result(_pair(), deliver=real_deliver, **{k: v for k, v in _common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()).items() if k != "deliver"})
    assert outcome.delivery_state == "DELIVERED"
    assert store.get(outcome.logical_ticket_id).state == "DELIVERED"
    assert store.get(outcome.logical_ticket_id).provider_response_id == "42"


# --------------------------------------------------------------------------- catch-up gate (OWNER_APPROVED 2026-09-08: 60-minute bound)

SIGNED_CATCH_UP_POLICY = CatchUpPolicy(max_catch_up_age=dt.timedelta(minutes=60))


def test_no_catch_up_policy_supplied_skips_the_gate_entirely(tmp_path):
    """Backward-compatible default: omitting catch_up_policy (every pre-existing test
    above does) must behave exactly as before this task -- a READY pair proceeds
    straight to render/register regardless of ready_at."""
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(_pair(ready_at=None), **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()))
    assert outcome.delivery_state == "TRANSPORT_NOT_CONFIGURED"


def test_on_time_ready_passes_the_catch_up_gate(tmp_path):
    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(
        _pair(ready_at=now), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now,
        **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()),
    )
    assert outcome.delivery_state == "TRANSPORT_NOT_CONFIGURED"
    assert store.get(outcome.logical_ticket_id).state == STATE_READY_TO_DELIVER


def test_exact_60_minute_boundary_is_still_permitted(tmp_path):
    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(minutes=60)
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(
        _pair(ready_at=ready_at), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now,
        **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()),
    )
    assert outcome.delivery_state == "TRANSPORT_NOT_CONFIGURED"  # allowed, not CATCH_UP_REJECTED


def test_one_minute_past_the_60_minute_boundary_is_rejected(tmp_path):
    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(minutes=61)
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(
        _pair(ready_at=ready_at), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now,
        **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()),
    )
    assert outcome.delivery_state == "CATCH_UP_REJECTED"
    assert outcome.reason_code == REASON_OUTSIDE_CATCH_UP_WINDOW


def test_rejected_catch_up_still_archives_but_creates_no_ticket(tmp_path):
    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(hours=2)
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(
        _pair(ready_at=ready_at), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now,
        **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()),
    )
    assert outcome.archived is True
    assert outcome.archive_path is not None
    assert store.get(outcome.logical_ticket_id) is None  # no ticket ever registered


def test_premature_now_before_ready_at_is_rejected(tmp_path):
    """A clock anomaly (now before the signal's own checkpoint) must never be treated
    as 'on time' -- fails closed via CatchUpPolicy's own premature check."""
    ready_at = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    now = ready_at - dt.timedelta(minutes=5)
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(
        _pair(ready_at=ready_at), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now,
        **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()),
    )
    assert outcome.delivery_state == "CATCH_UP_REJECTED"
    assert outcome.reason_code == REASON_PREMATURE


def test_ready_missing_ready_at_fails_closed_rather_than_assumed_on_time(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    outcome = process_pair_result(
        _pair(ready_at=None), catch_up_policy=SIGNED_CATCH_UP_POLICY,
        **_common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict()),
    )
    assert outcome.delivery_state == "CATCH_UP_REJECTED"
    assert outcome.reason_code == "READY_MISSING_READY_AT"


def test_catch_up_rejection_preserves_the_same_logical_ticket_identity(tmp_path):
    """Recovery preserves trading date and logical occurrence identity: the
    logical_ticket_id computed for a late (rejected) evaluation of an occurrence is
    identical to the one an on-time evaluation of the SAME occurrence would produce --
    identity depends only on strategy/version/symbol/cycle/trading_date, never on the
    catch-up outcome."""
    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    store_a = TicketDeliveryStore(state_dir=str(tmp_path / "a"))
    store_b = TicketDeliveryStore(state_dir=str(tmp_path / "b"))
    on_time = process_pair_result(
        _pair(ready_at=ready_at), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=ready_at,
        **_common_kwargs(tmp_path, store_a, render=lambda pair: _full_render_dict()),
    )
    late = process_pair_result(
        _pair(ready_at=ready_at), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=ready_at + dt.timedelta(hours=2),
        **_common_kwargs(tmp_path, store_b, render=lambda pair: _full_render_dict()),
    )
    assert on_time.logical_ticket_id == late.logical_ticket_id


def test_already_registered_occurrence_stays_idempotent_across_repeated_on_time_calls(tmp_path):
    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    kwargs = _common_kwargs(tmp_path, store, render=lambda pair: _full_render_dict())
    first = process_pair_result(_pair(ready_at=now), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now, **kwargs)
    second = process_pair_result(_pair(ready_at=now), catch_up_policy=SIGNED_CATCH_UP_POLICY, now=now, **kwargs)
    assert first.logical_ticket_id == second.logical_ticket_id
    assert len(store._records.all()) == 1
