"""WP4.3 tests: process_pair_result's run-level overlap protection is proven by
composition of already-atomic primitives (archive_cycle_decision's idempotent/
correction write, ensure_ready_to_deliver's idempotent creation, claim_for_delivery's
O_EXCL atomic claim -- each already proven individually in
tests/test_ticket_delivery_identity_and_archive.py and
tests/test_ticket_delivery_concurrency_and_restart.py). This file proves the
COMPOSITION holds at the orchestration layer itself, not just at each primitive.
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from notifications.telegram_client import TelegramClient
from post_asian_pilot.decision import STATUS_READY
from post_asian_pilot.governor import PORTFOLIO_SELECTED
from ticket_delivery.delivery_store import TicketDeliveryStore
from ticket_delivery.fx_cycle_integration import process_pair_result
from ticket_delivery.telegram_adapter import TelegramDestinationConfig, deliver_informational_ticket

UTC = dt.timezone.utc
TRADING_DATE = dt.date(2026, 9, 8)


def _pair(symbol="EURUSD"):
    decision = SimpleNamespace(status=STATUS_READY, reason_codes=("R1",), evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC))
    proposal = SimpleNamespace(setup_id=f"ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:{symbol}:2026-09-08", actionable=True)
    return SimpleNamespace(symbol=symbol, decision=decision, portfolio_state=PORTFOLIO_SELECTED, portfolio_reason_code=None, proposal=proposal)


def _render(pair):
    return {
        "application": {"release_id": "AG_TRADE_ASSISTANT_V1_0_3"},
        "strategy": {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1"},
        "identity": {"proposal_id": "P1", "setup_id": pair.proposal.setup_id},
        "market": {"symbol": pair.symbol, "direction": "SHORT"},
        "entry": {"entry": 1.0822, "stop_loss": 1.0852, "tp1": 1.0792, "tp2_runner": 1.0762},
        "risk": {"risk_percent": 0.5, "normalized_volume": 0.05},
        "timing": {"created_at": "2026-09-08T07:45:00+00:00", "expires_at": "2026-09-08T11:00:00+00:00"},
        "evidence": {"reason_codes": ["UPPER_SWEEP"]},
    }


class _CountingFakeSession:
    """Counts real HTTP-boundary calls -- the metric that actually matters for
    'losing workers send nothing'."""

    def __init__(self):
        self.send_count = 0

    def post(self, url, json=None, timeout=None):
        self.send_count += 1

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True, "result": {"message_id": 42}}

        return _Resp()


def _kwargs(tmp_path, store, deliver):
    return dict(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", application_release="AG_TRADE_ASSISTANT_V1_0_3",
        cycle="ASIAN_LONDON", trading_date=TRADING_DATE, delivery_store=store,
        render_entry_ticket_dict=_render, deliver=deliver, archive_root=str(tmp_path / "archive"),
    )


def test_ten_concurrent_invocations_same_pair_exactly_one_delivery(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    session = _CountingFakeSession()
    client = TelegramClient("FAKE:TOKEN", session=session)
    destination = TelegramDestinationConfig.from_values(bot_token="FAKE:TOKEN", chat_id=999, authorized_chat_ids=[999])

    def deliver(ticket_id, message_text):
        return deliver_informational_ticket(store=store, logical_ticket_id=ticket_id, message_text=message_text, client=client, destination=destination)

    kwargs = _kwargs(tmp_path, store, deliver)

    with ThreadPoolExecutor(max_workers=10) as pool:
        outcomes = list(pool.map(lambda _: process_pair_result(_pair(), **kwargs), range(10)))

    # DELIVERED is the durable ticket state, not "who sent it": a losing caller can
    # legitimately observe delivery_state == "DELIVERED" (the winner already finished)
    # OR the transient "DELIVERY_CLAIMED" (the winner is still mid-send) depending on
    # scheduling -- both are correct, non-duplicate outcomes, so delivery_state itself
    # is not asserted per-outcome here (see DeliveryOutcome's docstring in
    # telegram_adapter.py). The exactly-once guarantee that actually matters is how
    # many callers performed the real transport call, tracked separately and
    # deterministic regardless of scheduling.
    performed_delivery = [o for o in outcomes if o.delivery_performed_by_this_invocation]
    assert len(performed_delivery) == 1
    assert session.send_count == 1  # exactly one real transport call among 10 workers
    assert len({o.logical_ticket_id for o in outcomes}) == 1  # all 10 converged on the same logical ticket
    assert len(store._records.all()) == 1  # exactly one delivery record, ever


def test_independent_symbols_do_not_block_each_other(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    session = _CountingFakeSession()
    client = TelegramClient("FAKE:TOKEN", session=session)
    destination = TelegramDestinationConfig.from_values(bot_token="FAKE:TOKEN", chat_id=999, authorized_chat_ids=[999])

    def deliver(ticket_id, message_text):
        return deliver_informational_ticket(store=store, logical_ticket_id=ticket_id, message_text=message_text, client=client, destination=destination)

    kwargs = _kwargs(tmp_path, store, deliver)
    pairs = [_pair("EURUSD"), _pair("GBPUSD")]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda p: process_pair_result(p, **kwargs), pairs))

    assert all(o.delivery_state == "DELIVERED" for o in outcomes)
    assert session.send_count == 2  # each symbol delivered independently
    assert len({o.logical_ticket_id for o in outcomes}) == 2


def test_restart_before_claim_resumes_safely(tmp_path):
    """Simulates a restart between archive-completion and claim: a fresh
    TicketDeliveryStore instance against the same state_dir picks up exactly where the
    first left off, with no duplicate archive/registration."""
    state_dir = str(tmp_path / "delivery")
    archive_root = str(tmp_path / "archive")
    first_store = TicketDeliveryStore(state_dir=state_dir)
    kwargs_no_deliver = dict(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", application_release="AG_TRADE_ASSISTANT_V1_0_3",
        cycle="ASIAN_LONDON", trading_date=TRADING_DATE, delivery_store=first_store,
        render_entry_ticket_dict=_render, deliver=None, archive_root=archive_root,
    )
    first_outcome = process_pair_result(_pair(), **kwargs_no_deliver)
    assert first_outcome.delivery_state == "TRANSPORT_NOT_CONFIGURED"  # archived + registered, not yet delivered

    # "restart": a fresh store instance against the same on-disk state_dir
    second_store = TicketDeliveryStore(state_dir=state_dir)
    session = _CountingFakeSession()
    client = TelegramClient("FAKE:TOKEN", session=session)
    destination = TelegramDestinationConfig.from_values(bot_token="FAKE:TOKEN", chat_id=999, authorized_chat_ids=[999])

    def deliver(ticket_id, message_text):
        return deliver_informational_ticket(store=second_store, logical_ticket_id=ticket_id, message_text=message_text, client=client, destination=destination)

    kwargs_with_deliver = dict(kwargs_no_deliver, delivery_store=second_store, deliver=deliver)
    second_outcome = process_pair_result(_pair(), **kwargs_with_deliver)

    assert second_outcome.logical_ticket_id == first_outcome.logical_ticket_id  # same occurrence, no duplicate
    assert second_outcome.archive_path == first_outcome.archive_path  # idempotent re-archive, same file
    assert second_outcome.delivery_state == "DELIVERED"
    assert session.send_count == 1
