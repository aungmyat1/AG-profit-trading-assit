"""Shard coverage and fail-closed evidence guards; no sampled 60-day PASS."""
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import lsmc_v113_60d_replay as replay


def test_six_shards_cover_exactly_all_recorded_rows_with_real_overlap():
    info,bars=replay.inventory('BTCUSD')
    layouts=[replay.layout(info,bars,s) for s in range(6)]
    assert layouts[0]['core_start_row']==0
    assert layouts[-1]['core_end_row_exclusive']==len(bars['M5'])==16932
    for before,after in zip(layouts,layouts[1:]):
        assert before['core_end_row_exclusive']==after['core_start_row']
        assert after['warmup_start_row']['M5'] < after['core_start_row']-300
    assert sum(p['core_scans'] for p in layouts)==16932
    assert all(len(p['days'])==10 for p in layouts)


def test_declared_diff_is_exact_and_mutation_fails(monkeypatch):
    assert replay.audit.rule_diff()['verdict']=='PASS'
    original=replay.audit.A._spec_diff
    def extra_path(a,b,path=''):
        actual=original(a,b,path)
        return actual+['rules.UNDECLARED_DRIFT'] if not path else actual
    monkeypatch.setattr(replay.audit.A,'_spec_diff',extra_path)
    assert replay.audit.rule_diff()['verdict']=='FAIL'


def test_memoized_features_match_native_new_engine_on_recorded_repro():
    _,bars=replay.inventory('BTCUSD')
    evaluator=replay.EvidenceEvaluator()
    original=replay.G.evaluate_snapshot
    for row in (1271,1272):
        case=replay.make_case('BTCUSD',bars,row)
        result,snap=evaluator.evaluate(replay.C.SPEC,case)
        assert result==replay.G.evaluate_case(replay.C.SPEC,case)
        assert replay.G._payload(snap)==replay.G._payload(replay.native_snapshot(case))
        assert result['gate_status']['L1']=='PASS'
    assert replay.G.evaluate_snapshot is original
    assert evaluator.target_hits>0


def test_boundary_reference_detects_lost_warmup():
    info,bars=replay.inventory('BTCUSD')
    plan=replay.layout(info,bars,1)
    # A one-row overlap probe with deliberately absent H1 warmup must disagree.
    row=plan['core_start_row']
    bad={**plan,'core_end_row_exclusive':row+1,'warmup_start_row':{'D1':0,'H1':1000,'M5':row}}
    result=replay.boundary_reference('BTCUSD',bars,bad)
    assert result['verdict']=='FAIL'
    assert any(not x['equal'] for x in result['checks'])


@pytest.mark.parametrize('status,expected',[('NOT_RUN_RESOURCE','PARTIAL_NOT_RUN_RESOURCE'),('FAIL','FAIL_SHARD')])
def test_merger_never_converts_killed_or_failed_shard_to_pass(tmp_path,status,expected):
    p=tmp_path/'BTCUSD/shard_00/audit.json';p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'verdict':status,'completed':False,'completed_scans':50}))
    report=replay.merge_shards(tmp_path,tmp_path/'merged.json')
    assert report['symbols']['BTCUSD']['verdict']==expected
    assert report['symbols']['BTCUSD']['qualifies_for_r3_proposal'] is False
    assert report['proposal']=='NO_QUALIFYING_SCOPE'


def test_eurusd_d1r2_window_shards_cover_every_window_row_once():
    info,bars=replay.inventory('EURUSD')
    assert info['verdict']=='PASS_WITH_DECLARED_GAPS' and not info['issues']
    layouts=[replay.layout(info,bars,s) for s in range(6)]
    for before,after in zip(layouts,layouts[1:]):
        assert before['core_end_row_exclusive']==after['core_start_row']
    window=[b for b in bars['M5'] if b.time.date().isoformat() in info['days']]
    assert sum(p['core_scans'] for p in layouts)==len(window)
    assert layouts[0]['warmup_start_row']['M5'] < layouts[0]['core_start_row']   # real recorded warmup rows


def test_fx_commission_requires_full_account_binding(monkeypatch):
    import v1_tickets.manual_ticket as mt
    prov=json.loads((replay.FX_DATASET/'EURUSD_provenance.json').read_text())
    committed=mt.load_owner_config()
    assert committed['commission'].get('account_login') is None            # suffix-only in the repo
    assert replay.fx_commission_binding(prov) is None                       # -> L5 INSUFFICIENT, never PASS
    full={**committed,'commission':{**committed['commission'],'account_login':'1234567999'}}
    monkeypatch.setattr(mt,'load_owner_config',lambda *a,**k:full)
    assert replay.fx_commission_binding(prov)['binding']=='FULL_ACCOUNT_LOGIN'
    assert replay.fx_commission_binding({**prov,'login_suffix':'985'}) is None
    assert replay.fx_commission_binding({**prov,'server':'Other'}) is None


def test_independent_poi_age_counts_weekday_ny1700_dates():
    import datetime as dt
    utc=dt.timezone.utc
    origin=dt.datetime(2026,9,7,12,tzinfo=utc)                       # Monday trading date
    h1=[replay.A.Candle(origin+dt.timedelta(hours=h),1,1,1,1,None) for h in range(0,24*9)]
    assert replay.independent_poi_age(origin,h1,dt.datetime(2026,9,7,20,tzinfo=utc))==0
    assert replay.independent_poi_age(origin,h1,dt.datetime(2026,9,14,20,tzinfo=utc))==5   # weekend not counted
    assert replay.independent_poi_age(origin,h1,dt.datetime(2026,9,14,22,tzinfo=utc))==6
