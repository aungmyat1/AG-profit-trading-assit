"""Append-only 1.1.3 contract drift check and sharded replay entry point."""
import hashlib
from pathlib import Path

import lsmc_v110_logic_audit as A
import resource_guard as RG
import yaml

from large_smc_v113 import contract as C
from large_smc_v113 import watch as W
from v1_tickets import lsmc_v113_logic_gate as G

__all__ = ['A', 'C', 'G', 'W', 'RG', 'ROOT', 'rule_diff', 'frozen_identity']

ROOT = Path(__file__).resolve().parents[1]


def rule_diff():
    before = yaml.safe_load((ROOT/'strategies/ST_LARGE_SMC_V1_1_1_2.yaml').read_text())
    current = yaml.safe_load(G.CONTRACT_PATH.read_text())
    actual = sorted(A._spec_diff(before, current))
    declared = sorted(current['candidate_rule_changes']['declared_diff_paths'])
    return {'computed': actual, 'declared': declared, 'verdict': 'PASS' if actual == declared else 'FAIL'}


def frozen_identity():
    paths = ['strategies/ST_LARGE_SMC_V1_1_1_0.yaml', 'strategies/ST_LARGE_SMC_V1_1_1_2.yaml',
             'config/lsmc_report_lane.yaml']   # registry identity is L1 registry_identity_matches, not frozen bytes
    for folder in ('src/large_smc_watch', 'src/large_smc_v112'):
        paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT/folder).glob('*.py'))]
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


if __name__ == '__main__':
    from lsmc_v113_60d_replay import cli
    raise SystemExit(cli())
