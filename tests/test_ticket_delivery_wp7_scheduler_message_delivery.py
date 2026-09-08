"""WP7 tests for src/ticket_delivery/scheduler_integration.py's MESSAGE_DELIVERY
wiring: config parsing of the new `telegram_destination:` block, lazy/lawful
construction of the deliver() closure, execution-boundary isolation (a runtime spy, not
just the existing static AST scan), idempotency, the stale-ticket/catch-up gate
combined with MESSAGE_DELIVERY, rollback, and the synthetic ticket identity round-trip.

No real Telegram send anywhere: notifications.telegram_client.TelegramClient is always
replaced (monkeypatched at the scheduler_integration module level) with a fake whose
.send_message() never performs network I/O.
"""
from __future__ import annotations

import builtins
import datetime as dt
from types import SimpleNamespace

import pytest

from notifications.telegram_client import TelegramApiResult
from post_asian_pilot.decision import STATUS_READY, STATUS_WATCH
from post_asian_pilot.governor import PORTFOLIO_SELECTED
from ticket_delivery.delivery_store import TicketDeliveryStore
from ticket_delivery.identity import logical_ticket_id
from ticket_delivery.policy import CatchUpPolicy, RetryPolicy
from ticket_delivery.scheduler_integration import (
    MODE_ARCHIVE_ONLY,
    MODE_DISABLED,
    MODE_MESSAGE_DELIVERY,
    REASON_TELEGRAM_DESTINATION_BLOCK_INVALID,
    TicketDeliveryConfigError,
    TicketDeliveryIntegrationConfig,
    load_integration_config,
    process_cycle_result,
)

UTC = dt.timezone.utc
FAKE_TOKEN = "111222:CCFAKE-SCHEDULER-TEST-TOKEN-NEVER-REAL"
AUTHORIZED_CHAT = 424242424

_SIGNED_POLICY_YAML = (
    "policy:\n"
    "  fx_max_catch_up_age_minutes: 60\n"
    "  delivery_max_attempts: 3\n"
    "  delivery_retry_base_delay_seconds: 30\n"
    "  delivery_retry_max_delay_seconds: 300\n"
)


def _write_yaml(tmp_path, body: str, name: str = "cfg.yaml") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- telegram_destination: config parsing

def test_absent_telegram_destination_block_yields_empty_allow_list(tmp_path):
    path = _write_yaml(tmp_path, f"mode: ARCHIVE_ONLY\n{_SIGNED_POLICY_YAML}")
    config = load_integration_config(path)
    assert config.authorized_chat_ids == frozenset()


def test_populated_telegram_destination_block_parses_correctly(tmp_path):
    body = f"mode: ARCHIVE_ONLY\n{_SIGNED_POLICY_YAML}telegram_destination:\n  authorized_chat_ids: [111, 222]\n"
    path = _write_yaml(tmp_path, body)
    config = load_integration_config(path)
    assert config.authorized_chat_ids == frozenset({111, 222})


def test_non_mapping_telegram_destination_block_raises(tmp_path):
    body = f"mode: ARCHIVE_ONLY\n{_SIGNED_POLICY_YAML}telegram_destination: not_a_mapping\n"
    path = _write_yaml(tmp_path, body)
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_TELEGRAM_DESTINATION_BLOCK_INVALID


def test_non_integer_authorized_chat_ids_raises(tmp_path):
    body = f"mode: ARCHIVE_ONLY\n{_SIGNED_POLICY_YAML}telegram_destination:\n  authorized_chat_ids: [\"not-an-int\"]\n"
    path = _write_yaml(tmp_path, body)
    with pytest.raises(TicketDeliveryConfigError) as exc_info:
        load_integration_config(path)
    assert exc_info.value.reason_code == REASON_TELEGRAM_DESTINATION_BLOCK_INVALID


def test_disabled_mode_never_reads_telegram_destination_block(tmp_path):
    """DISABLED must remain the unconditional one-line rollback -- even a malformed
    telegram_destination block must not raise while mode: DISABLED."""
    body = "mode: DISABLED\ntelegram_destination: not_a_mapping\n"
    path = _write_yaml(tmp_path, body)
    config = load_integration_config(path)
    assert config.mode == MODE_DISABLED
    assert config.authorized_chat_ids == frozenset()


def test_shipped_repository_config_has_empty_authorized_chat_ids():
    """The actual committed config/ticket_delivery.yaml -- proves the shipped
    destination allow-list is empty (WP7 implementation, not activation)."""
    config = load_integration_config("config/ticket_delivery.yaml")
    assert config.mode == MODE_ARCHIVE_ONLY
    assert config.authorized_chat_ids == frozenset()


# --------------------------------------------------------------------------- process_cycle_result fixtures

def _decision(status, ready_at=None):
    return SimpleNamespace(status=status, reason_codes=("R1",),
                           evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC), ready_at=ready_at)


def _pair(symbol, status=STATUS_WATCH, proposal=None, ready_at=None):
    return SimpleNamespace(
        symbol=symbol, decision=_decision(status, ready_at=ready_at), portfolio_state=PORTFOLIO_SELECTED,
        portfolio_reason_code=None, proposal=proposal,
    )


def _result(pairs, trading_date=dt.date(2026, 9, 8)):
    strategy = SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1", version="1.1.1")
    return SimpleNamespace(strategy=strategy, release_id="AG_TRADE_ASSISTANT_V1_0_3", trading_date=trading_date, pairs=pairs)


def _config(mode, tmp_path, authorized_chat_ids=frozenset(), catch_up_minutes=60):
    return TicketDeliveryIntegrationConfig(
        mode=mode, archive_root=str(tmp_path / "archive"), delivery_state_dir=str(tmp_path / "state"),
        catch_up_policy=CatchUpPolicy(max_catch_up_age=dt.timedelta(minutes=catch_up_minutes)),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300),
        authorized_chat_ids=authorized_chat_ids,
    )


def _ready_proposal(symbol="EURUSD", trading_date="2026-09-08"):
    return SimpleNamespace(setup_id=f"ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:{symbol}:{trading_date}", actionable=True)


def _fake_render_entry_ticket(now, symbol="EURUSD"):
    def _render(*a, **k):
        return {
            "application": {"release_id": "AG_TRADE_ASSISTANT_V1_0_3"},
            "strategy": {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1"},
            "identity": {"proposal_id": "P1", "setup_id": f"ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:{symbol}:2026-09-08"},
            "market": {"symbol": symbol, "direction": "SHORT"},
            "entry": {"entry": 1.0822, "stop_loss": 1.0852, "tp1": 1.0792, "tp2_runner": 1.0762},
            "risk": {"risk_percent": 0.5, "normalized_volume": 0.05},
            "timing": {"created_at": now.isoformat(), "expires_at": "2026-09-08T11:00:00+00:00"},
            "evidence": {"reason_codes": ["UPPER_SWEEP"]},
        }
    return _render


class _FakeTelegramClient:
    """Replaces notifications.telegram_client.TelegramClient at the
    scheduler_integration module level -- constructed the same way
    (TelegramClient(bot_token)) but send_message() never touches the network."""

    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.calls = []

    def send_message(self, chat_id, text):
        self.calls.append((chat_id, text))
        return TelegramApiResult(ok=True, result={"message_id": 4242})


class _ExplodingTelegramClient:
    def __init__(self, bot_token):
        self.bot_token = bot_token

    def send_message(self, chat_id, text):
        raise AssertionError("no network call should ever be made on this path")


# --------------------------------------------------------------------------- lazy construction / rollback

def test_archive_only_never_constructs_deliver_even_with_full_authorization(tmp_path, monkeypatch):
    """Rollback guarantee: even with a fully authorized destination present in both env
    and config, ARCHIVE_ONLY must never construct a network adapter."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)

    config = _config(MODE_ARCHIVE_ONLY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    outcomes = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config)
    assert outcomes[0]["delivery_state"] == "NOT_APPLICABLE"


def test_disabled_mode_never_constructs_deliver_one_line_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)

    config = _config(MODE_DISABLED, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    outcomes = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config)
    assert outcomes == []


def test_message_delivery_without_env_vars_falls_back_to_transport_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)

    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))

    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "TRANSPORT_NOT_CONFIGURED"


def test_message_delivery_with_unauthorized_chat_id_falls_back_to_transport_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)

    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    # authorized_chat_ids does NOT include AUTHORIZED_CHAT -- unauthorized destination.
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({999}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))

    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "TRANSPORT_NOT_CONFIGURED"


# --------------------------------------------------------------------------- authorized, successful delivery

def test_message_delivery_fully_authorized_delivers_through_the_real_path(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _FakeTelegramClient)

    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))

    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "DELIVERED"

    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    record = store.get(outcomes[0]["logical_ticket_id"])
    assert record.state == "DELIVERED"
    assert record.provider_response_id == "4242"


def test_second_identical_invocation_is_idempotent_zero_provider_calls(tmp_path, monkeypatch):
    """DELIVERED is terminal and idempotent -- the next tick must be zero provider
    calls for the same occurrence."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _FakeTelegramClient)

    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = _ready_proposal()
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))

    def _pair_fresh():
        return _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)

    first = process_cycle_result(
        _result([_pair_fresh()]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert first[0]["delivery_state"] == "DELIVERED"

    # A fresh client that raises if send_message is ever called -- the second run must
    # not reach it (claim_for_delivery() refuses before any network call).
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)
    second = process_cycle_result(
        _result([_pair_fresh()]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert second[0]["logical_ticket_id"] == first[0]["logical_ticket_id"]
    # claim_for_delivery() refuses (record.state == DELIVERED is not claimable) before
    # any network call -- the reported state stays DELIVERED, unchanged, with a
    # not-retryable reason code, never a fabricated second delivery.
    assert second[0]["delivery_state"] == "DELIVERED"
    assert second[0]["reason_code"] == "DELIVERY_STATE_NOT_RETRYABLE"


# --------------------------------------------------------------------------- stale-ticket / catch-up gate combined with MESSAGE_DELIVERY

def test_stale_ready_ticket_rejected_before_any_delivery_attempt_even_when_authorized(tmp_path, monkeypatch):
    """Reuses fx_max_catch_up_age_minutes=60: an occurrence more than 60 minutes past
    ready_at must be rejected by the catch-up gate BEFORE any deliver() call, even when
    MESSAGE_DELIVERY is fully authorized and configured."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)

    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(minutes=90)  # outside the signed 60-minute bound
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=ready_at)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))

    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["archived"] is True
    assert outcomes[0]["delivery_state"] == "CATCH_UP_REJECTED"

    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    assert store.get(outcomes[0]["logical_ticket_id"]) is None  # never registered, never claimed


def test_on_time_ready_within_60_minutes_delivers_when_authorized(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _FakeTelegramClient)

    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(minutes=59)  # inside the 60-minute bound
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=ready_at)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))

    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "DELIVERED"


# --------------------------------------------------------------------------- synthetic ticket identity round-trip

def test_synthetic_ticket_identity_is_correctly_shaped_and_never_collides_with_real_ids():
    """Per the WP7 packet's 'Synthetic ticket identity and message contract' section:
    WP7 chooses the 'mint a fake but correctly-shaped identity' option, NOT a bypass of
    logical_ticket_id() -- this proves the exact literal shape
    SYNTHETIC_TEST|1.0.0|TESTPAIR|SYNTHETIC_CYCLE|2026-09-08 is produced by the SAME,
    unmodified identity.py constructor every real ticket uses, and cannot collide with
    a real ST_ASIAN_SWEEP_5R_V1|... identity (different strategy_id field entirely)."""
    synthetic_id = logical_ticket_id(
        strategy_id="SYNTHETIC_TEST", strategy_version="1.0.0", symbol="TESTPAIR",
        cycle="SYNTHETIC_CYCLE", trading_date=dt.date(2026, 9, 8),
    )
    assert synthetic_id == "SYNTHETIC_TEST|1.0.0|TESTPAIR|SYNTHETIC_CYCLE|2026-09-08"

    real_id = logical_ticket_id(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="EURUSD",
        cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 8),
    )
    assert synthetic_id != real_id


def test_synthetic_ticket_delivers_through_the_same_real_path_as_a_real_ticket(tmp_path):
    """The synthetic message must be sendable through the SAME
    deliver_informational_ticket() / TicketDeliveryStore path a real ticket uses -- no
    parallel, untested send path. This test exercises that path directly (bypassing
    process_cycle_result's strategy-shaped inputs, since the synthetic message is not a
    strategy occurrence) with a mocked Telegram client -- no real send."""
    from ticket_delivery.telegram_adapter import TelegramDestinationConfig, deliver_informational_ticket
    from notifications.telegram_client import TelegramClient

    synthetic_id = logical_ticket_id(
        strategy_id="SYNTHETIC_TEST", strategy_version="1.0.0", symbol="TESTPAIR",
        cycle="SYNTHETIC_CYCLE", trading_date=dt.date(2026, 9, 8),
    )
    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    store.ensure_ready_to_deliver(
        logical_ticket_id=synthetic_id, strategy_id="SYNTHETIC_TEST", strategy_version="1.0.0",
        application_release="AG_TRADE_ASSISTANT_TEST", symbol="TESTPAIR", cycle="SYNTHETIC_CYCLE",
        trading_date="2026-09-08", payload_hash="synthetic-hash",
    )

    message_text = (
        "AG DELIVERY SYSTEM TEST\n\n"
        "Environment: TEST\n"
        f"Ticket: {synthetic_id}\n"
        "Trading authority: NONE\n"
        "Broker execution: DISABLED\n\n"
        "This message verifies Stage-1 external\nticket-delivery infrastructure."
    )

    class _FakeSession:
        def post(self, url, json=None, timeout=None):
            class _Resp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"ok": True, "result": {"message_id": 1}}
            return _Resp()

    client = TelegramClient(FAKE_TOKEN, session=_FakeSession())
    destination = TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])

    outcome = deliver_informational_ticket(
        store=store, logical_ticket_id=synthetic_id, message_text=message_text,
        client=client, destination=destination,
    )
    assert outcome.final_state == "DELIVERED"
    assert store.get(synthetic_id).state == "DELIVERED"


# --------------------------------------------------------------------------- execution-boundary isolation (runtime spy, not just static AST scan)

FORBIDDEN_IMPORT_PREFIXES = (
    "execution",
    "mt5.management_gateway",
    "mt5.mt5_gateway",
    "authorization.mt5_execution_handler",
    "authorization.telegram_gateway",
    "notifications.trade_ticket_formatter",
)


@pytest.fixture()
def _block_execution_imports(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            if name == forbidden or name.startswith(forbidden + "."):
                raise AssertionError(f"forbidden import attempted during ticket-delivery runtime: {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    yield


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_success_path(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _FakeTelegramClient)
    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))
    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "DELIVERED"


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_retry_path(tmp_path):
    from notifications.telegram_client import TelegramClient
    from ticket_delivery.telegram_adapter import TelegramDestinationConfig, deliver_informational_ticket_with_retry

    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    tid = logical_ticket_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    store.ensure_ready_to_deliver(
        logical_ticket_id=tid, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="hash123",
    )

    class _Resp:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self._body

    class _Session:
        def __init__(self):
            self._responses = [
                {"ok": False, "error_code": 429, "description": "rate limited"},
                {"ok": True, "result": {"message_id": 1}},
            ]

        def post(self, url, json=None, timeout=None):
            return _Resp(self._responses.pop(0))

    client = TelegramClient(FAKE_TOKEN, session=_Session())
    destination = TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])
    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=destination, retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300),
        sleeper=lambda seconds: None,
    )
    assert outcome.final_state == "DELIVERED"


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_terminal_failure_path(tmp_path):
    from notifications.telegram_client import TelegramClient
    from ticket_delivery.telegram_adapter import TelegramDestinationConfig, deliver_informational_ticket

    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    tid = logical_ticket_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    store.ensure_ready_to_deliver(
        logical_ticket_id=tid, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="hash123",
    )

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": False, "error_code": 403, "description": "bot was blocked"}

    class _Session:
        def post(self, url, json=None, timeout=None):
            return _Resp()

    client = TelegramClient(FAKE_TOKEN, session=_Session())
    destination = TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=destination)
    assert outcome.final_state == "DELIVERY_FAILED_TERMINAL"


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_unauthorized_destination_path(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)
    now = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=now)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({999}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))
    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "TRANSPORT_NOT_CONFIGURED"


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_stale_ticket_path(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    import ticket_delivery.scheduler_integration as mod
    monkeypatch.setattr(mod, "TelegramClient", _ExplodingTelegramClient)
    ready_at = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    now = ready_at + dt.timedelta(minutes=90)
    proposal = _ready_proposal()
    pair = _pair("EURUSD", status=STATUS_READY, proposal=proposal, ready_at=ready_at)
    config = _config(MODE_MESSAGE_DELIVERY, tmp_path, authorized_chat_ids=frozenset({AUTHORIZED_CHAT}))
    monkeypatch.setattr(mod, "render_entry_ticket", _fake_render_entry_ticket(now))
    outcomes = process_cycle_result(
        _result([pair]), pilot_path=None, config=config, now=now,
        ledger=object(), release_fingerprint="fp1", strategy_fingerprint="fp2",
    )
    assert outcomes[0]["delivery_state"] == "CATCH_UP_REJECTED"


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_archive_only_path(tmp_path):
    config = _config(MODE_ARCHIVE_ONLY, tmp_path)
    outcomes = process_cycle_result(_result([_pair("EURUSD", status=STATUS_WATCH)]), pilot_path=None, config=config)
    assert outcomes[0]["delivery_state"] == "NOT_APPLICABLE"


@pytest.mark.usefixtures("_block_execution_imports")
def test_execution_boundary_synthetic_ticket_path(tmp_path):
    from notifications.telegram_client import TelegramClient
    from ticket_delivery.telegram_adapter import TelegramDestinationConfig, deliver_informational_ticket

    synthetic_id = logical_ticket_id(
        strategy_id="SYNTHETIC_TEST", strategy_version="1.0.0", symbol="TESTPAIR",
        cycle="SYNTHETIC_CYCLE", trading_date=dt.date(2026, 9, 8),
    )
    store = TicketDeliveryStore(state_dir=str(tmp_path / "state"))
    store.ensure_ready_to_deliver(
        logical_ticket_id=synthetic_id, strategy_id="SYNTHETIC_TEST", strategy_version="1.0.0",
        application_release="AG_TRADE_ASSISTANT_TEST", symbol="TESTPAIR", cycle="SYNTHETIC_CYCLE",
        trading_date="2026-09-08", payload_hash="synthetic-hash",
    )

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True, "result": {"message_id": 1}}

    class _Session:
        def post(self, url, json=None, timeout=None):
            return _Resp()

    client = TelegramClient(FAKE_TOKEN, session=_Session())
    destination = TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=synthetic_id, message_text="AG DELIVERY SYSTEM TEST", client=client, destination=destination)
    assert outcome.final_state == "DELIVERED"
