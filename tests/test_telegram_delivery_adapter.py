import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from telegram_delivery.adapter import (Config, Sender, STATUSES, render_session_summary,
                                       render_summary, render_ticket)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'telegram_delivery'
TICKETS = json.loads((FIXTURES / 'tickets.json').read_text())


@pytest.mark.parametrize('ticket', TICKETS, ids=lambda t: t['decision'])
def test_golden(ticket):
    assert render_ticket(ticket) + '\n' == (FIXTURES / (ticket['decision'] + '.txt')).read_text()


def test_fixture_status_coverage():
    assert {t['decision'] for t in TICKETS} == STATUSES


def test_adapter_taxonomy_matches_canonical_actionability():
    from v1_tickets import actionability as canonical
    expected = {canonical.WATCH_READY, canonical.INFO_ONLY_STALE,
                canonical.INFO_ONLY_INSUFFICIENT_REMAINING_R,
                canonical.INFO_ONLY_POLICY_UNRESOLVED, canonical.INFO_ONLY_SUPPRESSED,
                canonical.NO_TRADE, canonical.EXPIRED, canonical.MISSED,
                canonical.BLOCKED, canonical.INSUFFICIENT_DATA, canonical.OUT_OF_SESSION}
    assert STATUSES == expected
    suppressed = next(t for t in TICKETS if t['decision'] == canonical.INFO_ONLY_SUPPRESSED)
    assert render_ticket(suppressed).startswith('Ticket: fixture-INFO_ONLY_SUPPRESSED')


def test_summary():

    message = render_summary(TICKETS)
    assert message + '\n' == (FIXTURES / 'summary.txt').read_text()
    assert len([line for line in message.splitlines() if line[:1].isdigit()]) == len(TICKETS)
    for t in TICKETS:
        assert t['decision'] in message and t['reason_code'] in message


def session_digest():
    return {
        'schema': 'AGP_HOST_TICKET_DELIVERY_R1_SESSION_SUMMARY_V1',
        'session_date': '2026-10-08', 'session': 'ASIAN_LONDON',
        'status': 'INCOMPLETE_WITH_MISSED', 'expected_evaluations': 4,
        'recorded_evaluations': 3,
        'terminal_counts': {'INSUFFICIENT_DATA': 3},
        'missed_pairs': [{'symbol': 'XAUUSD', 'reason_code': 'SCHEDULED_EVALUATION_NOT_RECOVERED'}],
        'delivery_counts': {'succeeded': 1, 'failed': 0, 'uncertain': 1, 'disabled': 0,
                            'blocked': 0, 'summary_only': 1, 'persistence_failed': 0, 'not_attempted': 0},
        'uncertain_deliveries': [{'identity': 'ticket-1', 'status': 'WATCH_READY'}],
        'delivery_enabled': True,
    }


def test_deterministic_session_digest_reports_missing_and_uncertain_without_inventing_levels():
    first = render_session_summary(session_digest())
    assert first == render_session_summary(session_digest())
    assert 'Durable evaluations: 3/4' in first
    assert 'MISSED XAUUSD | SCHEDULED_EVALUATION_NOT_RECOVERED' in first
    assert 'Delivery enabled: true' in first
    assert 'Delivery UNCERTAIN: 1' in first
    assert 'Possibly undelivered (no automatic retry)' in first
    assert 'EXECUTION: DISABLED' in first
    assert '1.10000' not in first


def test_session_digest_sender_restart_uses_stable_session_key(tmp_path):
    calls = []
    path = tmp_path / 'delivery.sqlite'
    first = Sender(path, config(), lambda *args: calls.append(args))
    assert first.send_session_summary(session_digest()) == 'sent'
    assert len(calls) == 1 and 'MISSED XAUUSD' in calls[0][2]
    rows = first.delivery_attempts('session_summary')
    assert len(rows) == 1 and rows[0]['state'] == 'DELIVERED'
    restarted = Sender(path, config(), lambda *args: calls.append(args))
    assert restarted.send_session_summary(session_digest()) == 'duplicate'
    assert len(calls) == 1


def config(**overrides):
    # C16 scope flag is ON here so the pre-existing informational tests keep exercising the
    # enabled path; default-OFF behaviour is pinned separately below.
    return Config(**({'enabled': True, 'token': 'fake', 'chat_id': '123',
                      'owner_chat_ids': frozenset({'123'}), 'watch_info_scope': True} | overrides))


def watch():
    return next(t for t in TICKETS if t['decision'] == 'WATCH_READY')


def test_dedupe_restart(tmp_path):
    calls = []
    path = tmp_path / 'dedupe.sqlite'
    assert Sender(path, config(), transport=lambda *x: calls.append(x)).send_ticket(watch()) == 'sent'
    assert Sender(path, config(), transport=lambda *x: calls.append(x)).send_ticket(watch()) == 'duplicate'
    assert len(calls) == 1


@pytest.mark.parametrize('cfg', [Config(), config(enabled=False), config(token=''),
                               config(chat_id=''), config(owner_chat_ids=frozenset()), config(chat_id='999')])
def test_closed(tmp_path, cfg):
    calls = []
    sender = Sender(tmp_path / 'dedupe.sqlite', cfg, transport=lambda *x: calls.append(x))
    # 'summary_only' is also closed: with the C16 flag OFF (Config() default) informational
    # routing short-circuits before the enabled gate. Either way nothing is sent or created.
    assert sender.send_ticket(watch()) in {'disabled', 'blocked', 'summary_only'}
    assert calls == [] and not sender.path.exists()


def test_session_summary_disabled_is_closed_by_default(tmp_path):
    calls = []
    sender = Sender(tmp_path / 'dedupe.sqlite', Config(), lambda *x: calls.append(x))
    assert sender.send_session_summary(session_digest()) == 'disabled'
    assert calls == [] and not sender.path.exists()


def test_summary_once(tmp_path):
    calls = []
    path = tmp_path / 'dedupe.sqlite'
    assert Sender(path, config(), transport=lambda *x: calls.append(x)).send_summary(TICKETS) == 'sent'
    assert Sender(path, config(), transport=lambda *x: calls.append(x)).send_summary(TICKETS) == 'duplicate'
    assert len(calls) == 1


@pytest.mark.parametrize('ticket', TICKETS, ids=lambda t: t['decision'])
def test_per_ticket_selection(tmp_path, ticket):
    calls = []
    result = Sender(tmp_path / 'dedupe.sqlite', config(), transport=lambda *x: calls.append(x)).send_ticket(ticket)
    eligible = (ticket['decision'] == 'WATCH_READY'
                or ticket['decision'].startswith('INFO_ONLY_') and ticket['decision'] != 'INFO_ONLY_SUPPRESSED')
    assert result == ('sent' if eligible else 'summary_only')
    assert len(calls) == int(eligible)


def test_info_only_suppressed_is_persistable_but_never_immediately_sent(tmp_path):
    suppressed = next(t for t in TICKETS if t['decision'] == 'INFO_ONLY_SUPPRESSED')
    calls = []
    path = tmp_path / 'delivery.sqlite'
    sender = Sender(path, config(), transport=lambda *args: calls.append(args))
    assert sender.send_ticket(suppressed) == 'summary_only'
    assert calls == [] and not path.exists()


def test_unknown_decision_fails_closed_with_durable_compatibility_error(tmp_path):
    unknown = dict(watch(), decision='FUTURE_CANONICAL_STATE')
    calls = []
    path = tmp_path / 'delivery.sqlite'
    sender = Sender(path, config(), transport=lambda *args: calls.append(args))
    assert sender.send_ticket(unknown) == 'compatibility_error'
    assert calls == []
    diagnostics = sender.compatibility_errors()
    assert len(diagnostics) == 1
    assert diagnostics[0]['identity'] == unknown['ticket_id']
    assert diagnostics[0]['error_code'] == 'UNKNOWN_CANONICAL_DECISION'
    assert diagnostics[0]['observed_decision'] == 'FUTURE_CANONICAL_STATE'
    assert sender.send_ticket(unknown) == 'compatibility_error'
    assert len(sender.compatibility_errors()) == 1 and calls == []


def test_retry_backoff_and_redaction(tmp_path, caplog):
    calls, delays = [], []
    def transport(*args):
        calls.append(args)
        if len(calls) < 3:
            raise urllib.error.HTTPError('secret-token-url', 429, 'secret-token-url', {}, None)
    assert Sender(tmp_path / 'dedupe.sqlite', config(), transport, delays.append).send_ticket(watch()) == 'sent'
    assert delays == [1, 2] and len(calls) == 3
    assert 'secret-token-url' not in caplog.text


def test_ambiguous_restart(tmp_path, caplog):
    calls = []
    def transport(*args):
        calls.append(args)
        raise TimeoutError('secret-token-url')
    path = tmp_path / 'dedupe.sqlite'
    assert Sender(path, config(), transport).send_ticket(watch()) == 'uncertain'
    assert Sender(path, config(), transport).send_ticket(watch()) == 'duplicate'
    assert len(calls) == 1 and 'ambiguous' in caplog.text and 'secret-token-url' not in caplog.text


def test_timeout_after_send_uncertain_listed_no_autoresend_force_once(tmp_path, caplog):
    caplog.set_level('INFO')
    calls = []
    def transport(*args):
        calls.append(args)
        if len(calls) == 1:
            raise TimeoutError('secret-token-url')
    path = tmp_path / 'dedupe.sqlite'
    sender = Sender(path, config(), transport)
    assert sender.send_ticket(watch()) == 'uncertain'
    row = sender.list_uncertain()[0]
    assert row['identity'] == watch()['ticket_id']
    assert row['error_class'] == 'TimeoutError'
    assert sender.send_ticket(watch()) == 'duplicate'
    summary = render_summary([watch()], uncertain=sender.list_uncertain())
    assert 'DELIVERY_UNCERTAIN' in summary and watch()['ticket_id'] in summary
    assert sender.send_summary([watch()]) == 'sent'
    sent_text = calls[1][2]
    assert 'Uncertain delivery:' in sent_text and 'DELIVERY_UNCERTAIN' in sent_text
    assert Sender(path, config(), transport).resend_ticket(
        watch(), force=True, actor='owner-cli') == 'sent'
    assert Sender(path, config(), transport).resend_ticket(
        watch(), force=True, actor='owner-cli') == 'refused'
    assert 'Force resend refused' in caplog.text
    assert Sender(path, config(), transport).resend_ticket(
        watch(), force=True, actor='owner-cli', allow_duplicate=True) == 'sent'
    assert len(calls) == 4
    assert 'Force resend' in caplog.text and 'owner-cli' in caplog.text
    assert 'secret-token-url' not in caplog.text
    assert sender.list_uncertain() == []


def test_force_resend_uncertain_vs_delivered(tmp_path, caplog):
    caplog.set_level('INFO')
    calls = []
    def transport(*args):
        calls.append(args)
        if len(calls) == 1:
            raise TimeoutError('secret-token-url')
    path = tmp_path / 'dedupe.sqlite'
    sender = Sender(path, config(), transport)
    assert sender.send_ticket(watch()) == 'uncertain'
    assert sender.resend_ticket(watch(), force=True, actor='owner') == 'sent'
    assert sender.resend_ticket(watch(), force=True, actor='owner') == 'refused'
    assert 'refused' in caplog.text
    assert sender.resend_ticket(watch(), force=True, actor='owner', allow_duplicate=True) == 'sent'
    assert len(calls) == 3
    assert 'secret-token-url' not in caplog.text


def test_schema_gap_no_calculation():
    ticket = dict(watch(), prices={}, risk={}, structure_visual='invented POI')
    message = render_ticket(ticket)
    assert 'SCHEMA_GAP: prices.entry_reference' in message
    assert 'SCHEMA_GAP: risk.remaining_R_tp1' in message
    assert 'invented POI' not in message


def test_oversize_summary_preserves_rows_and_sends_nothing(tmp_path):
    tickets = [dict(watch(), reason_code='x' * 5000)]
    calls = []
    assert Sender(tmp_path / 'dedupe.sqlite', config(), lambda *x: calls.append(x)).send_summary(tickets) == 'blocked'
    assert calls == []


def test_import_boundary():
    code = "import sys; import telegram_delivery.adapter; assert not any(x.startswith(('mt5', 'MetaTrader5', 'execution', 'strategy_engine')) for x in sys.modules)"
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')), check=True)


def test_status_key_distinct(tmp_path):
    calls = []
    sender = Sender(tmp_path / 'dedupe.sqlite', config(), lambda *x: calls.append(x))
    assert sender.send_ticket(watch()) == 'sent'
    stale = dict(watch(), decision='INFO_ONLY_STALE', presentation='INFO_ONLY')
    assert sender.send_ticket(stale) == 'sent'
    assert len(calls) == 2


def test_default_environment_disabled(monkeypatch):
    monkeypatch.delenv('TELEGRAM_DELIVERY_ENABLED', raising=False)
    assert Config.from_env().enabled is False


def test_bot_api_plain_payload(monkeypatch):
    from telegram_delivery.adapter import bot_api
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"ok": true}'
    def open_request(request, timeout):
        captured.append((request, timeout))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', open_request)
    bot_api('fake', '123', render_ticket(watch()))
    request, timeout = captured[0]
    payload = json.loads(request.data)
    assert set(payload) == {'chat_id', 'text', 'parse_mode'}
    assert payload['parse_mode'] == 'HTML'
    assert payload['text'].startswith('<pre>') and payload['text'].endswith('</pre>')
    assert payload['chat_id'] == '123' and timeout == 15
    assert request.full_url == 'https://api.telegram.org/botfake/sendMessage'


def test_bot_api_html_escapes_source_text(monkeypatch):
    from telegram_delivery.adapter import bot_api
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"ok": true}'
    def open_request(request, timeout):
        captured.append((request, timeout))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', open_request)
    bot_api('fake-token', '123', '<signal> & "source"')
    request, timeout = captured[0]
    payload = json.loads(request.data)
    assert payload['text'] == '<pre>&lt;signal&gt; &amp; "source"</pre>'
    assert payload['chat_id'] == '123' and timeout == 15
    assert request.full_url == 'https://api.telegram.org/botfake-token/sendMessage'


def test_retry_exhaustion_logged(tmp_path, caplog):
    calls, delays = [], []
    def transport(*args):
        calls.append(args)
        raise urllib.error.HTTPError('secret', 429, 'secret', {}, None)
    sender = Sender(tmp_path / 'dedupe.sqlite', config(), transport, delays.append)
    assert sender.send_ticket(watch()) == 'failed'
    assert len(calls) == 3 and delays == [1, 2]
    assert 'HTTP failure' in caplog.text


def test_persistence_failure_sends_nothing(tmp_path):
    path = tmp_path / 'directory'
    path.mkdir()
    calls = []
    assert Sender(path, config(), lambda *x: calls.append(x)).send_ticket(watch()) == 'failed'
    assert calls == []


def test_restart_in_separate_process(tmp_path):
    store = str(tmp_path / 'dedupe.sqlite')
    code = """
import json, sys
from telegram_delivery.adapter import Config, Sender
from pathlib import Path
tickets = json.loads(Path('tests/fixtures/telegram_delivery/tickets.json').read_text())
ticket = next(t for t in tickets if t['decision'] == 'WATCH_READY')
calls = []
sender = Sender(sys.argv[1], Config(True, 'fake', '123', frozenset({'123'}), True), lambda *x: calls.append(x))
print(json.dumps([sender.send_ticket(ticket), len(calls)]))
"""
    for expected in [['sent', 1], ['duplicate', 0]]:
        result = subprocess.run([sys.executable, '-c', code, store], cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')),
                                capture_output=True, text=True, check=True)
        assert json.loads(result.stdout) == expected


@pytest.mark.parametrize('status', ['NO_TRADE', 'EXPIRED', 'INSUFFICIENT_DATA', 'BLOCKED'])
def test_force_resend_keeps_summary_only(tmp_path, status):
    calls = []
    ticket = next(t for t in TICKETS if t['decision'] == status)
    sender = Sender(tmp_path / 'dedupe.sqlite', config(), lambda *x: calls.append(x))
    assert sender.resend_ticket(ticket, force=True, actor='owner') == 'summary_only'
    assert calls == []


def test_html_escape_and_plain_fallback(monkeypatch, caplog):
    import io
    from telegram_delivery.adapter import bot_api
    payloads = []
    message = '<levels> & raw > price'
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"ok": true}'
    def transport(request, timeout):
        payloads.append(json.loads(request.data))
        if len(payloads) == 1:
            raise urllib.error.HTTPError('secret-token-url', 400, 'bad HTML', {},
                io.BytesIO(b'{"description": "Bad Request: can\'t parse entities"}'))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', transport)
    bot_api('fake', '123', message)
    assert payloads == [
        {'chat_id': '123', 'text': '<pre>&lt;levels&gt; &amp; raw &gt; price</pre>', 'parse_mode': 'HTML'},
        {'chat_id': '123', 'text': message}]
    assert 'falling back to plain text' in caplog.text
    assert 'secret-token-url' not in caplog.text


@pytest.mark.parametrize('error', [TimeoutError('secret'), ConnectionResetError('secret'),
                                 urllib.error.URLError(ConnectionResetError('secret'))])
def test_html_ambiguous_dispatched_consumed_and_next_summary(tmp_path, monkeypatch, error):
    import sqlite3
    from telegram_delivery.adapter import bot_api
    payloads, delays = [], []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"ok": true}'
    def transport(request, timeout):
        payloads.append(json.loads(request.data))  # request dispatched
        if len(payloads) == 1:
            raise error
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', transport)
    path = tmp_path / 'dedupe.sqlite'
    sender = Sender(path, config(), bot_api, delays.append)
    assert sender.send_ticket(watch()) == 'uncertain'
    assert len(payloads) == 1 and delays == []  # no HTML fallback or retry
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT identity,status,state FROM sent').fetchone() == (
            watch()['ticket_id'], 'WATCH_READY', 'DELIVERY_UNCERTAIN')
    restarted = Sender(path, config(), bot_api, delays.append)
    assert restarted.send_ticket(watch()) == 'duplicate'
    assert len(payloads) == 1
    next_session = dict(watch(), session_date='2026-10-09')
    assert restarted.send_summary([next_session]) == 'sent'
    assert 'possibly undelivered: ' + watch()['ticket_id'] in payloads[1]['text']
    assert len(payloads) == 2 and delays == []


def test_html_other_rejection_has_no_fallback(monkeypatch):
    import io
    from telegram_delivery.adapter import bot_api
    payloads = []
    def transport(request, timeout):
        payloads.append(json.loads(request.data))
        raise urllib.error.HTTPError('secret', 400, 'bad chat', {},
                                    io.BytesIO(b'{"description": "Bad Request: chat not found"}'))
    monkeypatch.setattr('urllib.request.urlopen', transport)
    with pytest.raises(urllib.error.HTTPError): bot_api('fake', '123', 'text')
    assert len(payloads) == 1


def test_html_json_rejection_fallback(monkeypatch):
    from telegram_delivery.adapter import bot_api
    payloads = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return (b'{"ok": false, "error_code": 400, "description": "cannot parse entities"}'
                    if len(payloads) == 1 else b'{"ok": true}')
    def transport(request, timeout):
        payloads.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', transport)
    bot_api('fake', '123', '&<>')
    assert len(payloads) == 2
    assert payloads[0]['text'] == '<pre>&amp;&lt;&gt;</pre>'
    assert payloads[1] == {'chat_id': '123', 'text': '&<>'}


def test_crash_pending_recovered_as_consumed_uncertain(tmp_path):
    import sqlite3
    calls = []
    def transport(*args):
        calls.append(args)
        raise SystemExit('simulated crash after request dispatch')
    path = tmp_path / 'dedupe.sqlite'
    with pytest.raises(SystemExit): Sender(path, config(), transport).send_ticket(watch())
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT state FROM sent').fetchone() == ('pending',)
    restarted = Sender(path, config(), lambda *args: calls.append(args))
    assert restarted.list_uncertain()[0]['error_class'] == 'InterruptedSend'
    assert restarted.send_ticket(watch()) == 'duplicate'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT state FROM sent').fetchone() == ('DELIVERY_UNCERTAIN',)
    assert len(calls) == 1
    assert restarted.send_summary([dict(watch(), session_date='2026-10-09')]) == 'sent'
    assert 'possibly undelivered: ' + watch()['ticket_id'] in calls[1][2]
    assert restarted.resend_ticket(watch(), force=True, actor='owner') == 'sent'
    assert len(calls) == 3


@pytest.mark.parametrize('code', [400, 429])
def test_explicit_failure_consumed_with_owner_recovery(tmp_path, code):
    import sqlite3
    calls = []
    def transport(*args):
        calls.append(args)
        raise urllib.error.HTTPError('secret', code, 'rejected', {}, None)
    path = tmp_path / 'dedupe.sqlite'
    sender = Sender(path, config(), transport, lambda _: None)
    assert sender.send_ticket(watch()) == 'failed'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT state FROM sent').fetchone() == ('DELIVERY_FAILED',)
    recovered = Sender(path, config(), lambda *args: calls.append(args))
    assert recovered.send_ticket(watch()) == 'duplicate'
    assert recovered.resend_ticket(watch(), force=True, actor='owner') == 'sent'


@pytest.mark.parametrize('code', [500, 502, 503, 504])
def test_server_error_consumes_uncertain_without_retry(tmp_path, code):
    calls, delays = [], []
    def transport(*args):
        calls.append(args)
        raise urllib.error.HTTPError('secret', code, 'server error', {}, None)
    sender = Sender(tmp_path / 'dedupe.sqlite', config(), transport, delays.append)
    assert sender.send_ticket(watch()) == 'uncertain'
    assert len(calls) == 1 and delays == []
    assert sender.list_uncertain()[0]['identity'] == watch()['ticket_id']
    assert sender.send_ticket(watch()) == 'duplicate'


def test_network_does_not_hold_global_journal_lock(tmp_path):
    path = tmp_path / 'dedupe.sqlite'
    other = dict(watch(), ticket_id='another-ticket')
    results = []
    def transport(*args):
        nested = Sender(path, config(), lambda *args: None)
        results.append(nested.send_ticket(other))
        results.append(nested.send_ticket(watch()))
        # Active pending is not prematurely recovered as crash-left uncertainty.
        assert nested.list_uncertain() == []
    assert Sender(path, config(), transport).send_ticket(watch()) == 'sent'
    assert results == ['sent', 'duplicate']


def test_c16_scope_default_off_scheduled_informational_is_summary_only(tmp_path):
    calls = []
    sender = Sender(tmp_path / 'dedupe.sqlite', Config(enabled=True, token='fake', chat_id='123',
                                                       owner_chat_ids=frozenset({'123'})),
                    transport=lambda *x: calls.append(x))
    assert sender.send_ticket(watch()) == 'summary_only'
    stale = dict(watch(), decision='INFO_ONLY_STALE', presentation='INFO_ONLY')
    assert sender.send_ticket(stale) == 'summary_only'
    assert calls == []


def test_c16_scope_default_off_refuses_owner_resend_with_scope_not_enabled(tmp_path):
    calls = []
    sender = Sender(tmp_path / 'dedupe.sqlite', config(watch_info_scope=False),
                    transport=lambda *x: calls.append(x))
    for ticket in (watch(), dict(watch(), decision='INFO_ONLY_STALE', presentation='INFO_ONLY')):
        assert sender.resend_ticket(ticket, force=True, actor='owner') == 'SCOPE_NOT_ENABLED'
    assert calls == []


def test_c16_scope_enabled_allows_owner_resend_of_informational(tmp_path):
    calls = []
    path = tmp_path / 'dedupe.sqlite'
    def ambiguous(*x):
        raise RuntimeError('network ambiguous')
    # Force resend only applies to an UNCERTAIN claim: seed one, then resend under the flag.
    assert Sender(path, config(watch_info_scope=True), transport=ambiguous).send_ticket(watch()) == 'uncertain'
    sender = Sender(path, config(watch_info_scope=True), transport=lambda *x: calls.append(x))
    assert sender.resend_ticket(watch(), force=True, actor='owner') == 'sent'
    assert len(calls) == 1


def test_c16_scope_never_gates_suppressed_or_ready_states(tmp_path):
    calls = []
    sender = Sender(tmp_path / 'dedupe.sqlite', config(watch_info_scope=False),
                    transport=lambda *x: calls.append(x))
    suppressed = dict(watch(), decision='INFO_ONLY_SUPPRESSED', presentation='INFO_ONLY')
    assert sender.resend_ticket(suppressed, force=True, actor='owner') == 'summary_only'
    no_trade = dict(watch(), decision='NO_TRADE', presentation='OTHER')
    assert sender.resend_ticket(no_trade, force=True, actor='owner') == 'summary_only'
    assert calls == []

