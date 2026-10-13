"""C21 regression gates for append-only candidate and host-evidenced pip convention."""
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from large_smc_v112.metadata import REASON, load_pip
from large_smc_v112.watch import _poi_age_days
from large_smc_watch.contract import C10_PIP_SIZE
from reporting.lsmc_version import selected_version

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('symbol,want', [('EURUSD',.0001),('GBPUSD',.0001),('USDJPY',.01),
                                         ('XAUUSD',.1),('BTCUSD',.1),('ETHUSD',.1)])
def test_owner_pip_exact(symbol,want):
    pip,source=load_pip(symbol)
    assert pip==want
    assert source.startswith('10*point host_captured ')
    if symbol in ('EURUSD','GBPUSD'):
        assert pip==C10_PIP_SIZE[symbol], 'STOP: frozen FX pip mismatch'

@pytest.fixture
def evidence(tmp_path):
    shutil.copytree(ROOT/'config/symbol_metadata',tmp_path/'config/symbol_metadata')
    shutil.copytree(ROOT/'config/broker_symbol_map',tmp_path/'config/broker_symbol_map')
    return tmp_path

@pytest.mark.parametrize('field,value', [('schema','AG_HOST_SYMBOL_METADATA_V1'),('server','other'),
    ('canonical_symbol','GBPUSD'),('broker_symbol','EURUSD'),('captured_at_utc','bad'),
    ('point',0),('point',-1),('point',float('nan')),('point',True),('point','0.00001')])
def test_bad_metadata_fails_closed(evidence,field,value):
    p=evidence/'config/symbol_metadata/host_captured/EURUSD.json'
    d=json.loads(p.read_text())
    if field=='point': d['fields'][field]=value
    else: d[field]=value
    # Re-pin altered evidence to exercise semantic checks independently of hashes.
    payload={k:v for k,v in d.items() if k!='sha256'}
    d['sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    p.write_text(json.dumps(d))
    m=evidence/'config/broker_symbol_map/vt_markets_demo.yaml'; mapping=yaml.safe_load(m.read_text())
    mapping['entries']['EURUSD']['host_capture']['sha256']=d['sha256'];m.write_text(yaml.safe_dump(mapping))
    assert load_pip('EURUSD',evidence)==(None,REASON)

def test_missing_tampered_map_and_file_fail_closed(evidence):
    p=evidence/'config/symbol_metadata/host_captured/EURUSD.json'
    p.write_text('{}')
    assert load_pip('EURUSD',evidence)==(None,REASON)
    p.unlink()
    assert load_pip('EURUSD',evidence)==(None,REASON)

def test_frozen_bytes_are_rehashed():
    pins=json.loads((ROOT/'tests/fixtures/c21/frozen_sha256.json').read_text())
    for path,want in pins.items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==want,path

def test_trading_age_skips_missing_weekend_and_holiday_dates():
    # NY 17:00 boundary; observed dates Friday, Monday, Wednesday (Tuesday holiday).
    times=[dt.datetime(2026,10,d,12,tzinfo=dt.timezone.utc) for d in (9,12,14)]
    poi=SimpleNamespace(origin_time=times[0])
    h1=[SimpleNamespace(time=t) for t in times]
    assert _poi_age_days(poi,h1,times[-1]+dt.timedelta(hours=1))==2
    assert _poi_age_days(poi,h1,times[1])==1 # future dates excluded

def test_default_report_version_and_explicit_candidate(tmp_path):
    assert selected_version()=='1.1.0'
    p=tmp_path/'selection.yaml';p.write_text("strategy_version: '1.1.2'\n")
    assert selected_version(p)=='1.1.2'
    p.write_text("strategy_version: '2.0'\n")
    with pytest.raises(ValueError): selected_version(p)

def test_declared_diff_exact():
    import sys
    sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
    from lsmc_v112_logic_audit import rule_diff
    diff=rule_diff()
    assert diff['verdict']=='PASS'
    assert 'pip_size_rules' in diff['computed'] or any(p.startswith('pip_size_rules.') for p in diff['computed'])
    assert any(p.startswith('rules.stop.pip_size') for p in diff['computed'])


def test_all_six_committed_synthetic_opportunities_are_priced():
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from large_smc_v112 import evaluate_snapshot
    scales={'EURUSD':1.,'GBPUSD':1.2,'USDJPY':140.,'XAUUSD':2400.,'BTCUSD':60000.,'ETHUSD':3000.}
    for symbol,k in scales.items():
        snap=evaluate_snapshot(symbol,d1_bars(k),h1_bars(k),m5_bars(k),NOW)
        o=snap.opportunity
        assert o and o['stop_c10'] is not None and o['target_c11'] is not None,symbol
        assert o['stop_c10'] < o['entry_reference'] < o['target_c11']
        assert o['pip_size']==load_pip(symbol)[0]
        assert o['pip_source']==load_pip(symbol)[1]
        assert o['verification_status']=='NOT_VERIFIED'


def test_crypto_poi_expiry_preserves_frozen_calendar(monkeypatch):
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from large_smc_v112 import watch as new
    from large_smc_watch import watch as old
    for k,symbol in ((60000.,'BTCUSD'),(3000.,'ETHUSD')):
        a=old.evaluate_snapshot(symbol,d1_bars(k),h1_bars(k),m5_bars(k),NOW)
        b=new.evaluate_snapshot(symbol,d1_bars(k),h1_bars(k),m5_bars(k),NOW)
        assert a.expired_poi_ids==b.expired_poi_ids
        assert a.invalidated_poi_ids==b.invalidated_poi_ids
        assert a.poi==b.poi
        assert b.opportunity['expires_at'] is not None # candidate uses declared crypto ticket windows


def test_report_candidate_is_isolated_and_stamped(tmp_path,monkeypatch):
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from reporting import lsmc_version
    monkeypatch.setattr(lsmc_version,'selected_version',lambda:'1.1.2')
    kwargs=dict(symbol='EURUSD',bars={'D1':d1_bars(),'H1':h1_bars(),'M5':m5_bars()},
                journal=str(tmp_path),now=NOW,price=m5_bars()[-1].close,archive_root=str(tmp_path/'archive'))
    rows=lsmc_version.observe_selected([],**kwargs)
    assert rows
    assert all(r['verification_status']=='NOT_VERIFIED' for r in rows)
    assert all(r['strategy_version']=='1.1.2' for r in rows)
    assert all(r['pip_source']==load_pip('EURUSD')[1] for r in rows)
    assert all(r['decision'] not in ('READY','WATCH_READY','TICKET_READY') for r in rows)
    assert not (tmp_path/'large_smc_watch/state.json').exists()
    assert lsmc_version.observe_selected([],**kwargs)==[]


def test_fx_expiry_uses_trading_age_in_the_actual_snapshot(monkeypatch):
    from dataclasses import replace

    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from fx_discovery.features import swings
    from large_smc_v112 import watch as new
    from large_smc_watch import watch as old
    from large_smc_watch.detect import h1_pois, tolerant_breaks
    bars=h1_bars()
    pois=h1_pois('EURUSD',bars,tolerant_breaks(bars,swings(bars,2),.00005))
    origin=NOW-dt.timedelta(days=8) # Dec 29; >5 calendar boundaries, only observed trading dates count.
    pois=[replace(p,origin_time=origin) for p in pois]
    monkeypatch.setattr(new,'h1_pois',lambda *_:pois)
    monkeypatch.setattr(old,'h1_pois',lambda *_:pois)
    a=old.evaluate_snapshot('EURUSD',d1_bars(),bars,m5_bars(),NOW)
    b=new.evaluate_snapshot('EURUSD',d1_bars(),bars,m5_bars(),NOW)
    assert a.expired_poi_ids
    assert not b.expired_poi_ids
    assert b.opportunity and b.opportunity['stop_c10'] is not None


def test_static_c11_target_cannot_retarget_with_later_h1(monkeypatch):
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from large_smc_v112 import evaluate_snapshot
    from strategy_engine.session import Candle
    a=evaluate_snapshot('EURUSD',d1_bars(),h1_bars(),m5_bars(),NOW)
    later=Candle(NOW,1.2,1.3,1.1,1.25)
    b=evaluate_snapshot('EURUSD',d1_bars(),h1_bars()+[later],m5_bars(),NOW)
    assert a.opportunity['target_c11']==b.opportunity['target_c11']


def test_snapshot_missing_host_metadata_names_c10_gate(tmp_path,monkeypatch):
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from large_smc_v112 import evaluate_snapshot, metadata
    monkeypatch.setattr(metadata,'REPO_ROOT',tmp_path)
    snap=evaluate_snapshot('EURUSD',d1_bars(),h1_bars(),m5_bars(),NOW)
    assert snap.state=='DATA_ERROR'
    assert snap.reason_codes==('C10_PIP_SIZE_NOT_EVIDENCED',)


def test_candidate_rr_pending_does_not_qualify():
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from large_smc_v112 import evaluate_snapshot
    snap=evaluate_snapshot('EURUSD',d1_bars(),h1_bars(),m5_bars(),NOW)
    assert snap.opportunity['reward_risk']>0
    assert snap.opportunity['reward_risk_reason']=='FAIL_CLOSED_RR_MINIMUM_UNCONFIRMED'


def test_candidate_crypto_expiry_uses_committed_window():
    from large_smc_v112.watch import opportunity_expiry
    # Weekday ticket window is 09:00–12:00 New York (January UTC-5).
    at=dt.datetime(2026,1,6,15,0,tzinfo=dt.timezone.utc)
    assert opportunity_expiry('BTCUSD',at)==dt.datetime(2026,1,6,17,0,tzinfo=dt.timezone.utc)


def test_evidenced_pip_view_does_not_cache_success(evidence,monkeypatch):
    from large_smc_v112 import contract, metadata
    monkeypatch.setattr(metadata,'REPO_ROOT',evidence)
    assert contract.C10_PIP_SIZE['EURUSD']==.0001
    (evidence/'config/symbol_metadata/host_captured/EURUSD.json').unlink()
    assert contract.C10_PIP_SIZE.get('EURUSD') is None
    assert 'EURUSD' not in contract.C10_PIP_SIZE


def test_interrupted_replay_leaves_not_run_resource(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0,str(ROOT/'scripts'))
    import lsmc_v112_logic_audit as audit
    monkeypatch.setattr(audit.RG,'acquire',lambda *_args,**_kwargs:{'ACQUIRED':True})
    monkeypatch.setattr(audit.RG,'release',lambda *_args,**_kwargs:{'RELEASED':True})
    def killed(*_args):
        raise RuntimeError('sandbox killed workload')
    monkeypatch.setattr(audit,'build_report',killed)
    path=tmp_path/'evidence.json'
    with pytest.raises(RuntimeError):
        audit.main(SimpleNamespace(out=str(path),crypto_scans=120,skip_crypto=False,lane_b_every=1))
    evidence=json.loads(path.read_text())
    assert evidence['verdict']=='NOT_RUN_RESOURCE'
    assert all(v=='NOT_RUN_RESOURCE' for s in evidence['scope_matrix'].values() for v in s['gates'].values())


def test_undeclared_rule_drift_fails(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    import lsmc_v112_logic_audit as audit
    spec=yaml.safe_load(audit.G.CONTRACT_PATH.read_text())
    spec['rules']['undeclared_probe']=True
    path=tmp_path/'spec.yaml';path.write_text(yaml.safe_dump(spec))
    monkeypatch.setattr(audit.G,'CONTRACT_PATH',path)
    assert audit.rule_diff()['verdict']=='FAIL'


def test_committed_candidate_audit_is_bound_to_engine_and_spec():
    report=json.loads((ROOT/'artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2/audit.json').read_text())
    assert report['verdict']=='NOT_VERIFIED'
    assert report['lane_failures']==[]
    assert report['rule_diff']['verdict']=='PASS'
    assert report['rule_diff']['computed']==report['rule_diff']['declared']
    assert report['frozen_v110_bytes_unchanged'] is True
    for path,digest in report['identity']['engine_file_sha256'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
    assert hashlib.sha256((ROOT/'strategies/ST_LARGE_SMC_V1_1_1_2.yaml').read_bytes()).hexdigest()==report['identity']['contract_sha256']
    for symbol,row in report['scope_matrix'].items():
        assert row['priced_opportunities']>0,symbol
        assert row['gates']=={'L1':'PASS','L2':'PASS','L3':'PASS','L4':'PASS','L5':'WARN','L6':'PASS'}
        assert row['scope_verdict']=='NOT_VERIFIED'


def test_committed_v110_parity_digest():
    folder=ROOT/'artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2'
    parity=json.loads((folder/'v110_parity.json').read_text())
    payload=(folder/'v110_baseline.json').read_bytes()
    assert parity['bytes_identical'] is True and parity['verdict']=='PASS'
    assert len(payload)==parity['bytes']
    assert hashlib.sha256(payload).hexdigest()==parity['sha256']


def test_default_report_delegates_new_main_account_inputs(monkeypatch):
    from reporting import lsmc_lane, lsmc_version
    captured={}
    def observe(events,**kwargs):
        captured.update(kwargs)
        return []
    monkeypatch.setattr(lsmc_lane,'observe_events',observe)
    monkeypatch.setattr(lsmc_version,'selected_version',lambda:'1.1.0')
    account={'balance':2500.,'commission_R':.01,'currency':'USD'}
    lsmc_version.observe_selected([],symbol='EURUSD',bars={},journal='unused',now=None,
                                  price=None,archive_root='unused',account=account)
    assert captured['account']==account


def test_candidate_report_retains_new_main_account_inputs(tmp_path,monkeypatch):
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

    from reporting import lsmc_version
    monkeypatch.setattr(lsmc_version,'selected_version',lambda:'1.1.2')
    rows=lsmc_version.observe_selected([],symbol='EURUSD',
         bars={'D1':d1_bars(),'H1':h1_bars(),'M5':m5_bars()},journal=str(tmp_path),now=NOW,
         price=m5_bars()[-1].close,archive_root=str(tmp_path/'archive'),
         account={'balance':2500.,'commission_R':.01,'currency':'USD'})
    assert rows[0]['sizing_inputs']['balance']==2500.
    assert rows[0]['sizing_inputs']['commission_R']==.01
    assert rows[0]['sizing_inputs']['account_currency']=='USD'
    assert rows[0]['sizing_inputs']['pip_size']==.0001


def test_fx_age_never_counts_closed_weekend_dates_even_in_synthetic_input():
    from types import SimpleNamespace
    times=[dt.datetime(2026,10,d,12,tzinfo=dt.timezone.utc) for d in (9,10,11,12)]
    poi=SimpleNamespace(origin_time=times[0])
    assert _poi_age_days(poi,[SimpleNamespace(time=t) for t in times],times[-1]+dt.timedelta(hours=1))==1
