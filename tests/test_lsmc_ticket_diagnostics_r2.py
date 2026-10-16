"""Defensive reporting only: no live market data, execution or transport."""
import copy
import datetime as dt

import pytest

from host_delivery import telegram_message as tg
from host_delivery.lsmc_diagnostics import (
    MAX_ALERT_UNITS,
    alert_units,
    diagnostic_lines,
)

AT = '2026-10-15T08:00:00+00:00'


def event(**opp):
    values = dict(direction='LONG', entry_reference=10., stop_c10=9., target_c11=12.,
                  choch_time='2026-10-15T07:55:00+00:00', sweep_time='2026-10-15T07:50:00+00:00',
                  expires_at='2026-10-15T09:00:00+00:00')
    values.update(opp)
    return dict(symbol='EURUSD', strategy_id='ST_LARGE_SMC_V1', strategy_version='1.1.0',
                reference_id='ref-1', evaluated_at=AT, to_state='NEAR_POI', alert_level='WATCH',
                payload={'opportunity': values})


@pytest.mark.parametrize('bad', [None, [], True, 7, 'bad', {}, {'payload': []}, {'payload': True}])
def test_malformed_event_does_not_crash_or_mutate(bad):
    before = copy.deepcopy(bad)
    lines = diagnostic_lines(bad)
    text = tg.format_alert(bad)
    assert text.startswith('LARGE-SMC ALERT -- INFORMATIONAL -- NOT A BROKER ORDER')
    assert text.count('M5 DIAGNOSTICS --') == 1
    assert 'gross R:R candidate: NOT_AVAILABLE' in '\n'.join(lines)
    assert bad == before


@pytest.mark.parametrize('bad', [None, [], True, 'bad', 5, {'entry_reference': []}])
def test_malformed_opportunity(bad):
    e = event()
    e['payload']['opportunity'] = bad
    before = copy.deepcopy(e)
    assert 'entry candidate: NOT_AVAILABLE' in '\n'.join(diagnostic_lines(e))
    assert tg.format_alert(e).count('M5 DIAGNOSTICS --') == 1
    assert e == before


@pytest.mark.parametrize('bad', ['REJECT_NO_STOP', {'REJECT_NO_STOP': True}, 7, True,
    [None], ['REJECT_NO_STOP', []], ['မြန်မာ'], ['REJECT_NO_STOP\nREADY'], ['X' * 65], ['A'] * 9])
def test_bad_reason_codes_are_unavailable_ascii_and_bounded(bad):
    e = event()
    e.update(to_state='REJECTED')
    e['payload']['reason_codes'] = bad
    text = '\n'.join(diagnostic_lines(e))
    assert text.isascii()
    assert 'explicit rejection reason: NOT_AVAILABLE' in text
    assert tg.format_alert(e).count('M5 DIAGNOSTICS --') == 1


@pytest.mark.parametrize('field', ['entry_reference', 'stop_c10', 'target_c11', 'sweep_extreme'])
@pytest.mark.parametrize('bad', [None, float('nan'), float('inf'), -float('inf'), True,
    0, -1, '10', [], {}, 10**1000])
def test_invalid_prices_never_break_renderer(field, bad):
    e = event(**{field: bad})
    text = tg.format_alert(e)
    assert 'nan' not in text and 'inf' not in text
    if field != 'sweep_extreme':
        assert 'gross R:R candidate: NOT_AVAILABLE' in text


@pytest.mark.parametrize('signal,expiry,now,expected', [
    ('2026-10-15T14:25:00+06:30', '2026-10-15T15:30:00+06:30', AT, 'AT_EVALUATION_ONLY'),
    ('2026-10-15T07:55:00Z', '2026-10-15T11:00:00+02:00', '2026-10-15T14:30:00+06:30', 'AT_EVALUATION_ONLY'),
    (AT, '2026-10-15T09:00:00Z', AT, 'AT_EVALUATION_ONLY'),
    ('2026-10-15T07:55:00Z', AT, AT, 'EXPIRED'),
    ('2026-10-15T06:00:00Z', '2026-10-15T07:00:00Z', AT, 'EXPIRED'),
    ('2026-10-15T08:01:00Z', '2026-10-15T09:00:00Z', AT, 'NOT_AVAILABLE'),
    (AT, '2026-10-15T07:00:00Z', AT, 'NOT_AVAILABLE'),
    (AT, AT, AT, 'NOT_AVAILABLE'),
    (None, '2026-10-15T07:00:00Z', AT, 'NOT_AVAILABLE'),
    ('2026-10-15T07:55:00', '2026-10-15T09:00:00Z', AT, 'NOT_AVAILABLE'),
    ('bad', '2026-10-15T09:00:00Z', AT, 'NOT_AVAILABLE'),
    ('2026-10-15T07:55:00Z', 'bad', AT, 'NOT_AVAILABLE'),
    ('2026-10-15T07:55:00Z', '2026-10-15T09:00:00Z', 'bad', 'NOT_AVAILABLE'),
    ('2026-10-15T07:55:00Z', '2026-10-15T09:00:00Z', '2026-10-15T08:00:00', 'NOT_AVAILABLE'),
])
def test_timestamp_offsets_and_chronology(signal, expiry, now, expected):
    e = event(choch_time=signal, expires_at=expiry, sweep_time=None)
    e['evaluated_at'] = now
    text = '\n'.join(diagnostic_lines(e))
    assert f'freshness: {expected};' in text
    assert tg.format_alert(e)


def test_offsets_normalize_to_identical_utc_evidence():
    utc = event()
    mmt = event(choch_time='2026-10-15T14:25:00+06:30',
                sweep_time='2026-10-15T14:20:00+06:30', expires_at='2026-10-15T15:30:00+06:30')
    mmt['evaluated_at'] = dt.datetime.fromisoformat('2026-10-15T14:30:00+06:30')
    assert diagnostic_lines(utc) == diagnostic_lines(mmt)


@pytest.mark.parametrize('direction,stop,target,expected', [
    ('LONG', 9, 12, '2.000'), ('SHORT', 11, 8, '2.000'),
    ('LONG', 10, 12, 'NOT_AVAILABLE'), ('SHORT', 9, 8, 'NOT_AVAILABLE'),
    ('SHORT', 11, 12, 'NOT_AVAILABLE'), ('BAD', 9, 12, 'NOT_AVAILABLE'),
    ([], 9, 12, 'NOT_AVAILABLE'),
])
def test_directional_rr_and_missing_costs(direction, stop, target, expected):
    text = '\n'.join(diagnostic_lines(event(direction=direction, stop_c10=stop, target_c11=target)))
    assert f'gross R:R candidate: {expected}; net R:R: NOT_AVAILABLE' in text
    assert 'spread: NOT_AVAILABLE; total cost: NOT_AVAILABLE' in text


def test_rr_overflow_fails_closed():
    text = '\n'.join(diagnostic_lines(event(entry_reference=1e-300, stop_c10=5e-301, target_c11=1e300)))
    assert 'gross R:R candidate: NOT_AVAILABLE' in text


def test_non_ascii_timestamp_and_rejection_do_not_inject_diagnostic_lines():
    e = event(choch_time='မြန်မာ', sweep_time='\nREADY', expires_at='ထွက်')
    e['payload']['reason_codes'] = ['REJECT_\u202eSTOP']
    e['to_state'] = 'REJECTED'
    text = '\n'.join(diagnostic_lines(e))
    assert text.isascii() and len(text.splitlines()) == 9


def test_alert_budget_boundary_never_slices_safety_information(monkeypatch):
    e = event()
    text = tg.format_alert(e)
    units = alert_units(text)
    from host_delivery import lsmc_diagnostics as diag
    monkeypatch.setattr(diag, 'MAX_ALERT_UNITS', units)
    assert tg.format_alert(e) == text
    monkeypatch.setattr(diag, 'MAX_ALERT_UNITS', units - 1)
    with pytest.raises(tg.TelegramSendError, match='exceeds message budget') as caught:
        tg.format_alert(e)
    assert caught.value.delivery_state == 'BLOCKED'
    assert units < MAX_ALERT_UNITS <= 4096
    assert alert_units('\U0001f600') == 2


def test_large_rejection_is_replaced_as_invalid_evidence_not_sliced():
    e = event()
    e['to_state'] = 'REJECTED'
    e['payload']['reason_codes'] = ['A' * 10000]
    text = tg.format_alert(e)
    assert text.endswith('explicit rejection reason: NOT_AVAILABLE')
    assert alert_units(text) < MAX_ALERT_UNITS


@pytest.mark.parametrize('bad', [None, [], True, 5, 'bad', {'low': True, 'high': {}},
                                {'low': 12, 'high': 10}])
def test_malformed_poi_and_broker_metadata_are_display_only(bad):
    e = event()
    e['payload']['poi'] = bad
    e['display_broker_symbol'] = []
    before = copy.deepcopy(e)
    assert tg.format_alert(e)
    assert e == before


def test_future_sweep_cannot_support_freshness_claim():
    text = '\n'.join(diagnostic_lines(event(sweep_time='2026-10-15T10:00:00Z')))
    assert 'freshness: NOT_AVAILABLE;' in text
