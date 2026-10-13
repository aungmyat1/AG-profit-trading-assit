"""Evidence harness checks; synthetic probes are never included in the recorded replay."""
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import lsmc_v112_60d_replay as replay


def test_missing_recorded_files_are_insufficient(tmp_path,monkeypatch):
    monkeypatch.setattr(replay,'ROOT',tmp_path)
    monkeypatch.setattr(replay,'DATASET',tmp_path/'recorded')
    info,bars=replay.inventory('BTCUSD')
    assert bars is None
    assert info['verdict']=='DATA_INSUFFICIENT'
    assert info['missing_files']==['recorded/BTCUSD_d1.csv','recorded/BTCUSD_h1.csv','recorded/BTCUSD_m5.csv','recorded/BTCUSD_provenance.json']


def test_captured_evaluator_preserves_original_and_l1_calls():
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars
    case={'case_id':'probe','symbol':'EURUSD','now':NOW,'fixture':'SYNTHETIC_TEST_ONLY','classification':'SYNTHETIC',
          'D1':d1_bars(),'H1':h1_bars(),'M5':m5_bars()}
    before=replay.G.evaluate_case(replay.C.SPEC,case)
    after,snap=replay.captured_evaluator(replay.C.SPEC,case)
    assert after==before
    assert replay.G._payload(snap)==replay.G._payload(replay.G.evaluate_snapshot('EURUSD',case['D1'],case['H1'],case['M5'],NOW))
    assert after['gate_status']['L1']=='PASS'


def test_vacuous_pass_cannot_qualify_for_proposal():
    counts=replay.new_counts();counts['scans']=1
    for gate in counts['gates'].values(): gate['PASS']=1
    assert replay.summary(counts)['qualifies_for_proposal'] is False
    counts['rr_eligible_scans']=1
    counts['gates']['L5'].clear();counts['gates']['L5']['WARN']=1
    assert replay.summary(counts)['qualifies_for_proposal'] is True
    counts['gates']['L6'].clear();counts['gates']['L6']['WARN']=1
    assert replay.summary(counts)['qualifies_for_proposal'] is False


def test_interrupted_campaign_keeps_not_run_resource(tmp_path,monkeypatch):
    monkeypatch.setattr(replay.RG,'acquire',lambda *a,**k:{'ACQUIRED':True})
    monkeypatch.setattr(replay.RG,'release',lambda *a,**k:{'RELEASED':True})
    def killed(): raise RuntimeError('sandbox interruption')
    monkeypatch.setattr(replay,'protected_identity',killed)
    path=tmp_path/'audit.json'
    with pytest.raises(RuntimeError): replay.run(path)
    assert json.loads(path.read_text())['verdict']=='NOT_RUN_RESOURCE'


def test_crypto_fixture_inventory_has_real_60_days():
    for symbol in ('BTCUSD','ETHUSD'):
        info,bars=replay.inventory(symbol)
        assert info['verdict']=='PASS_WITH_DECLARED_GAPS'
        assert len(info['days'])==60
        assert info['server']=='VTMarkets-Demo'
        assert len(bars['M5'])==16932


def test_h1_fact_memo_preserves_engine_and_l1_without_global_mutation():
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars
    original=replay.G.evaluate_snapshot
    original_h1=replay.audit.W.h1_pois
    case={'case_id':'memo_probe','symbol':'EURUSD','now':NOW,'fixture':'SYNTHETIC_TEST_ONLY','classification':'SYNTHETIC',
          'D1':d1_bars(),'H1':h1_bars(),'M5':m5_bars()}
    expected=replay.G.evaluate_case(replay.C.SPEC,case)
    evaluator=replay.EvidenceEvaluator()
    observed,_=evaluator.evaluate(replay.C.SPEC,case)
    assert observed==expected
    assert evaluator.statistics()['uncached_snapshot_reference_checks']==1
    assert evaluator.statistics()['h1_fact_cache_hits']>0
    assert replay.G.evaluate_snapshot is original
    assert replay.audit.W.h1_pois is original_h1
