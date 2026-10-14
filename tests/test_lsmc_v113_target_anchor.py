"""Native recorded C11 regressions and deterministic causal prefix properties."""
import bisect
import csv
import datetime as dt
import hashlib
import random
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
# Frozen LSMC 1.1.0 / 1.1.2 engine, gate, contract and report-selection bytes (sha256 on main 50bd6db).
# strategies/registry.yaml is deliberately absent: registry identity is L1 registry_identity_matches.
FROZEN_SHA256 = {
    'config/lsmc_report_lane.yaml': 'ac9ce5b42d3c399d44f091fba0193fd5ce7a167472da89f475c4b3c0714a3628',
    'src/large_smc_v112/__init__.py': '5c2e9e5205d83618e7bf2b4783d818c19c98dbf50c9deede2b5ee43e4816a228',
    'src/large_smc_v112/contract.py': '85e61615b4c64b3bf9d3f0eb5d3941bbb89d22070cf674b97797b6a9f9249820',
    'src/large_smc_v112/detect.py': 'b336f1c4958caefc33fcf4a73dbd3b60b730870f76366a7faec37c5012779161',
    'src/large_smc_v112/metadata.py': 'b0437ae640ccc19a28740f79e83a4ad3eec55f0f81fae54b2db38c7f16a74ca7',
    'src/large_smc_v112/targets.py': 'a047891b188e00c7db429db3ee1b1e1cbfae5cbc78226f4039ed9290fdfe0e4c',
    'src/large_smc_v112/watch.py': '8aef629782c928e40bb754c750af34c5daac8fcb6691cd7704630e20437196f5',
    'src/large_smc_v112/windows.py': '7dcfeef1486ca8f1c8f8fa258df9cb47b7e25549b1c82c89ef67d8015db64c05',
    'src/large_smc_watch/__init__.py': 'ebbca3c124487c79a41912b6bbf75688d06529257bdc4ee53d0ffe2df789950f',
    'src/large_smc_watch/contract.py': '51f9a0d088e750399b7ef4d98c978c6974b0b9ef2814f1c4251bbed79a9a5e1c',
    'src/large_smc_watch/detect.py': 'e3fd5e1fe699046c8b4c552e68d6a19a6f4abc51ea9cec3c4734c02db4e27973',
    'src/large_smc_watch/watch.py': '86ac9cdcfa864b36a06b795920bd333f8fa9cfdd81efa5eb422e1d746bc2c63d',
    'src/v1_tickets/lsmc_logic_gate.py': 'e3133071f126d744b34cd8feae6379bdd41b9474cf9e9775991d4d75ae3ac799',
    'src/v1_tickets/lsmc_v112_logic_gate.py': '3689d467325987550555ca2e47e7be18beb0f011be975abc2914b13bc695629f',
    'strategies/ST_LARGE_SMC_V1_1_1_0.yaml': '78285f9fabcb20af14de327d010e48684dc12205f4435eff886fcc2373a357b4',
    'strategies/ST_LARGE_SMC_V1_1_1_2.yaml': '1f9b6cace2e1be33e5b3572e2c13e3e526b992478f91c8f09955b0f44b73024f',
}


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
    assert len(FROZEN_SHA256) == 16
    for p, want in FROZEN_SHA256.items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == want, p
    assert yaml.safe_load((ROOT/'config/lsmc_report_lane.yaml').read_text())['strategy_version'] == '1.1.2'
