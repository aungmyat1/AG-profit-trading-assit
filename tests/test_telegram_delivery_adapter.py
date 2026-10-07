import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from telegram_delivery.adapter import Config, Sender, STATUSES, render_summary, render_ticket

FIXTURES = Path(__file__).parent / 'fixtures' / 'telegram_delivery'
TICKETS = json.loads((FIXTURES / 'tickets.json').read_text())


@pytest.mark.parametrize('ticket', TICKETS, ids=lambda t: t['decision'])
def test_golden(ticket):
    assert render_ticket(ticket) + '\n' == (FIXTURES / (ticket['decision'] + '.txt')).read_text()


def test_fixture_status_coverage():
    assert {t['decision'] for t in TICKETS} == STATUSES


def test_summary():
    message = render_summary(TICKETS)
    assert message + '\n' == (FIXTURES / 'summary.txt').read_text()
    assert len([line for line in message.splitlines() if line[:1].isdigit()]) == len(TICKETS)
    for t in TICKETS:
        assert t['decision'] in message and t['reason_code'] in message


def config(**overrides):
    return Config(**({'enabled': True, 'token': 'fake', 'chat_id': '123',
                      'owner_chat_ids': frozenset({'123'})} | overrides))


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
    assert sender.send_ticket(watch()) in {'disabled', 'blocked'}
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
    eligible = ticket['decision'] == 'WATCH_READY' or ticket['decision'].startswith('INFO_ONLY_')
    assert result == ('sent' if eligible else 'summary_only')
    assert len(calls) == int(eligible)


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
    subprocess.run([sys.executable, '-c', code], env={'PYTHONPATH': 'src'}, check=True)


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
    assert set(payload) == {'chat_id', 'text'}
    assert payload['chat_id'] == '123' and timeout == 15
    assert request.full_url == 'https://api.telegram.org/botfake/sendMessage'


def test_retry_exhaustion_logged(tmp_path, caplog):
    calls, delays = [], []
    def transport(*args):
        calls.append(args)
        raise urllib.error.HTTPError('secret', 503, 'secret', {}, None)
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
sender = Sender(sys.argv[1], Config(True, 'fake', '123', frozenset({'123'})), lambda *x: calls.append(x))
print(json.dumps([sender.send_ticket(ticket), len(calls)]))
"""
    for expected in [['sent', 1], ['duplicate', 0]]:
        result = subprocess.run([sys.executable, '-c', code, store], env={'PYTHONPATH': 'src'},
                                capture_output=True, text=True, check=True)
        assert json.loads(result.stdout) == expected


@pytest.mark.parametrize('status', ['NO_TRADE', 'EXPIRED', 'INSUFFICIENT_DATA', 'BLOCKED'])
def test_force_resend_keeps_summary_only(tmp_path, status):
    calls = []
    ticket = next(t for t in TICKETS if t['decision'] == status)
    sender = Sender(tmp_path / 'dedupe.sqlite', config(), lambda *x: calls.append(x))
    assert sender.resend_ticket(ticket, force=True, actor='owner') == 'summary_only'
    assert calls == []
