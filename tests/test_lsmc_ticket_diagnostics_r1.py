"""Research diagnostics: synthetic evidence only; no broker or real transport."""
import copy
import datetime as dt

import pytest

from fx_discovery.features import fvgs
from host_delivery.lsmc_diagnostics import diagnostic_lines
from large_smc_watch.watch import Snapshot, WatchTracker
from strategy_engine.session import Candle

AT = '2026-10-15T08:00:00+00:00'


def event(**updates):
    opp = dict(direction='LONG', entry_reference=10, stop_c10=9, target_c11=12,
               sweep_time='2026-10-15T07:50:00+00:00', choch_time='2026-10-15T07:55:00+00:00',
               expires_at='2026-10-15T09:00:00+00:00')
    opp.update(updates)
    return dict(evaluated_at=AT, to_state='OPPORTUNITY', payload={'opportunity': opp})


def test_diagnostics_are_immutable_and_do_not_infer_stage_or_cost():
    e = event()
    before = copy.deepcopy(e)
    text = '\n'.join(diagnostic_lines(e))
    assert e == before
    assert 'gross R:R candidate: 2.000' in text
    assert 'AT_EVALUATION_ONLY' in text
    assert 'BOS: NOT_AVAILABLE' in text
    assert 'displacement evidence: NOT_AVAILABLE' in text
    assert 'spread: NOT_AVAILABLE; total cost: NOT_AVAILABLE' in text
    assert text.isascii()


@pytest.mark.parametrize('updates', [dict(stop_c10=None), dict(target_c11=float('nan')),
    dict(entry_reference=True), dict(stop_c10=10), dict(target_c11=8), dict(stop_reason='MISSING')])
def test_invalid_levels_never_yield_rr(updates):
    assert 'gross R:R candidate: NOT_AVAILABLE' in '\n'.join(diagnostic_lines(event(**updates)))


@pytest.mark.parametrize('expiry,expected', [(None, 'NOT_AVAILABLE'), ('bad', 'NOT_AVAILABLE'),
    ('2026-10-15T08:00:00', 'NOT_AVAILABLE'), (AT, 'EXPIRED')])
def test_missing_or_expired_evidence_fails_closed(expiry, expected):
    assert f'freshness: {expected};' in '\n'.join(diagnostic_lines(event(expires_at=expiry)))


def test_absent_opportunity_is_unknown_not_failed():
    text = '\n'.join(diagnostic_lines({'payload': {}, 'evaluated_at': AT}))
    assert 'liquidity sweep time: NOT_AVAILABLE' in text
    assert 'explicit rejection reason: NOT_AVAILABLE' in text
    e = event()
    e.update(to_state='REJECTED')
    e['payload']['reason_codes'] = ['REJECT_NO_STOP']
    assert 'explicit rejection reason: REJECT_NO_STOP' in '\n'.join(diagnostic_lines(e))


@pytest.mark.parametrize('symbol', ['GBPUSD', 'XAUUSD'])
def test_consecutive_references_and_near_developing_preserve_archive(tmp_path, symbol):
    tracker = WatchTracker(str(tmp_path / 'state.json'), str(tmp_path / 'archive'))
    def snap(ref, state):
        return Snapshot(symbol, AT, state, poi={'poi_id': ref})
    a, = tracker.poll(snap('FVG-A', 'NEAR_POI'))
    files = {p: p.read_bytes() for p in (tmp_path / 'archive').rglob('*.json')}
    b, = tracker.poll(snap('FVG-A', 'DEVELOPING'))
    c, = tracker.poll(snap('FVG-B', 'DEVELOPING'))
    assert b.from_state == 'NEAR_POI'
    assert a.reference_id != c.reference_id
    assert tracker.poll(snap('FVG-B', 'DEVELOPING')) == []
    assert all(p.read_bytes() == content for p, content in files.items())
    # Characterize current limitation: a replaced reference has no independent terminal event.
    assert c.from_state == 'DEVELOPING' and c.to_state == 'DEVELOPING'


@pytest.mark.parametrize('gap,count', [(0, 0), (0.000001, 1)])
def test_positive_narrow_fvg_remains_frozen_behavior(gap, count):
    now = dt.datetime.fromisoformat(AT)
    bars = [Candle(now + dt.timedelta(hours=i), 1, high, low, 1)
            for i, (high, low) in enumerate([(1, .9), (1.2, .9), (1.3, 1 + gap)])]
    zones = fvgs(bars)
    assert len(zones) == count
    if zones:
        assert zones[0].known_at == 2


def test_renderer_adds_ascii_diagnostics_without_mutating_event():
    from host_delivery.telegram_message import format_alert
    e = dict(symbol='USDJPY', strategy_id='ST_LARGE_SMC_V1', strategy_version='1.1.0',
             to_state='NEAR_POI', alert_level='WATCH', reference_id='FVG-A',
             evaluated_at=AT, payload={'poi': {'low': 149, 'high': 150}})
    before = copy.deepcopy(e)
    text = format_alert(e, price=150.1)
    assert 'distance to POI: 10.0 pips' in text
    assert 'M5 DIAGNOSTICS -- READ ONLY -- NO EXECUTION AUTHORITY' in text
    assert 'freshness: NOT_AVAILABLE' in text
    assert e == before
    assert text.isascii()
