"""Native recorded C11 regressions and deterministic causal prefix properties."""
import bisect
import csv
import datetime as dt
import hashlib
import random
import subprocess
from pathlib import Path

import pytest
import yaml

from large_smc_v112 import watch as old
from large_smc_v113 import contract as C
from large_smc_v113 import watch as new
from large_smc_v113.targets import _candidate_target_at_creation
from strategy_engine.session import Candle
from v1_tickets.lsmc_v113_logic_gate import signal_snapshot

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {'D1': 30, 'H1': 200, 'M5': 300}
BASE = '50bd6db5b2d3253ee8fdb70ec463201ab852da9d'  # main after #212 (registry D8/D9) and #214


@pytest.fixture(scope='module')
def bars():
    result = {}
    for tf in COUNTS:
        with (ROOT/'tests/fixtures/ccfd_v100/recorded_60d'/f'BTCUSD_{tf.lower()}.csv').open() as stream:
            result[tf] = [Candle(dt.datetime.fromisoformat(r['timestamp_utc']),
                                *(float(r[k]) for k in ('open','high','low','close')), None)
                          for r in csv.DictReader(stream)]
    return result


def inputs(bars, row):
    now = bars['M5'][row].time + dt.timedelta(minutes=5)
    full, windows = {}, {}
    for tf, rows in bars.items():
        end = bisect.bisect_right(rows, now, key=lambda b: b.time)
        full[tf] = rows[:end]
        windows[tf] = rows[max(0,end-COUNTS[tf]):end]
    history = {tf:full[tf] for tf in ('H1','M5')}
    history['capture_start_utc'] = {tf:bars[tf][0].time.isoformat() for tf in ('H1','M5')}
    return now, windows, history


@pytest.mark.parametrize('a,b', [(1271,1272),(1487,1488),(1633,1634)])
def test_three_native_recorded_static_target_repros_are_fixed(bars,a,b):
    before, after, legacy = [], [], []
    for row, into in ((a,before),(b,after)):
        now,w,h = inputs(bars,row)
        args = ('BTCUSD',w['D1'],w['H1'],w['M5'],now)
        legacy.append(signal_snapshot(old.evaluate_snapshot(*args)).opportunity)
        into.append(signal_snapshot(new.evaluate_snapshot(*args,target_history=h)).opportunity)
    x,y = before[0],after[0]
    assert legacy[0]['opp_id'] == legacy[1]['opp_id']
    assert legacy[0]['target_c11'] != legacy[1]['target_c11']
    assert x['opp_id'] == y['opp_id'] == legacy[0]['opp_id']
    assert x['target_c11'] == y['target_c11'] == legacy[0]['target_c11']
    assert x['c11_source'] == y['c11_source'] == 'PRIMARY_EXTERNAL_LIQUIDITY'
    assert x['target_selection'] == y['target_selection']


def test_later_prefixes_and_future_prices_cannot_retarget_existing_id(bars):
    # Seed is fixed; test all three identities against growing history and arbitrary later prices.
    rng = random.Random(20261014)
    for row in (1271,1487,1633):
        now,w,h = inputs(bars,row)
        opportunity = signal_snapshot(new.evaluate_snapshot('BTCUSD',w['D1'],w['H1'],w['M5'],now,target_history=h)).opportunity
        creation = dt.datetime.fromisoformat(opportunity['target_selection']['creation_bar_close_utc'])
        expected = _candidate_target_at_creation(opportunity,creation,h)
        later_rows = sorted(set([row,row+1,len(bars['M5'])-1]+[rng.randrange(row,len(bars['M5'])) for _ in range(24)]))
        for later_row in later_rows:
            _,_,later = inputs(bars,later_row)
            assert _candidate_target_at_creation(opportunity,creation,later) == expected
        altered = {tf:[b if b.time+dt.timedelta(minutes=C.TIMEFRAME_MINUTES[tf]) <= creation else
                       Candle(b.time,900000.0,1000000.0,1.0,900000.0,None) for b in bars[tf]]
                   for tf in ('H1','M5')}
        altered['capture_start_utc'] = h['capture_start_utc']
        assert _candidate_target_at_creation(opportunity,creation,altered) == expected


def test_every_later_scan_before_expiry_preserves_an_existing_id_target(bars):
    for row in (1271,1487,1633):
        now,w,h = inputs(bars,row)
        initial = signal_snapshot(new.evaluate_snapshot('BTCUSD',w['D1'],w['H1'],w['M5'],now,target_history=h)).opportunity
        expiry = dt.datetime.fromisoformat(initial['expires_at'])
        matches = 0
        for later in range(row+1,len(bars['M5'])):
            now,w,h = inputs(bars,later)
            if now >= expiry:
                break
            o = signal_snapshot(new.evaluate_snapshot('BTCUSD',w['D1'],w['H1'],w['M5'],now,target_history=h)).opportunity
            if o and o['opp_id'] == initial['opp_id']:
                matches += 1
                assert o['target_c11'] == initial['target_c11']
                assert o['target_selection'] == initial['target_selection']
        assert matches > 0


def test_missing_or_clipped_creation_context_cannot_select_later_fallback(bars):
    now,w,h = inputs(bars,1272)
    args = ('BTCUSD',w['D1'],w['H1'],w['M5'],now)
    missing = signal_snapshot(new.evaluate_snapshot(*args)).opportunity
    assert missing['target_c11'] is None
    assert missing['target_reason'] == 'C11_CREATION_HISTORY_NOT_EVIDENCED'
    clipped = {**h,'M5':w['M5']}
    o = signal_snapshot(new.evaluate_snapshot(*args,target_history=clipped)).opportunity
    assert o['target_c11'] is None
    assert o['c11_source'] is None
    assert o['target_reason'] == 'C11_CREATION_HISTORY_NOT_EVIDENCED'


def test_frozen_versions_and_report_selection_are_byte_identical():
    paths = subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'src/large_smc_watch',
        'src/large_smc_v112','src/v1_tickets/lsmc_logic_gate.py','src/v1_tickets/lsmc_v112_logic_gate.py',
        'strategies/ST_LARGE_SMC_V1_1_1_0.yaml','strategies/ST_LARGE_SMC_V1_1_1_2.yaml',
        'config/lsmc_report_lane.yaml','strategies/registry.yaml'],cwd=ROOT,text=True).splitlines()
    for p in paths:
        before = subprocess.check_output(['git','show',f'{BASE}:{p}'],cwd=ROOT)
        assert hashlib.sha256((ROOT/p).read_bytes()).digest() == hashlib.sha256(before).digest(),p
    assert yaml.safe_load((ROOT/'config/lsmc_report_lane.yaml').read_text())['strategy_version'] == '1.1.2'
