"""C24 evidence guardrails, including the recorded STATIC counterexample."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from lsmc_v112_60d_replay import inventory
from lsmc_v112_c24_static_target_repro import verify_pair

from research_external.oracles import lsmc_c24_recorded as oracle


def test_unpinned_oracle_fails_before_creating_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(oracle, 'version', lambda name: '0.0.28')
    out = tmp_path/'oracle.json'
    with pytest.raises(ValueError, match='OSS_BLOCKED'):
        oracle.run(out)
    assert not out.exists()


def test_recorded_static_target_defect_is_reproducible_without_memo():
    _, bars = inventory('BTCUSD')
    witness = verify_pair(bars, 1271, 1272)
    assert witness['reproduced']
    a, b = witness['before']['opportunity'], witness['after']['opportunity']
    assert a['opp_id'] == b['opp_id']
    assert a['target_c11'] == 63238.3
    assert b['target_c11'] == 63113.99


def test_committed_campaign_never_promotes_partial_gate_passes():
    root = ROOT/'artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c24_r2'
    report = json.loads((root/'p1_crypto/audit.json').read_text())
    assert report['verdict'] == 'NOT_RUN_RESOURCE'
    assert report['symbols']['BTCUSD']['verdict'] == 'NOT_RUN_RESOURCE'
    assert report['symbols']['ETHUSD']['verdict'] == 'NOT_RUN_RESOURCE'
    campaign = json.loads((root/'campaign.json').read_text())
    assert campaign['P4'] == 'NO_PROPOSAL'
