"""Committed-fixture 1.1.2 audit, reusing the frozen audit lanes and L1–L6 gates."""
import hashlib
import json
import os
import types
from pathlib import Path

import lsmc_v110_logic_audit as A
import resource_guard as RG
import yaml
from _lsmc_v111_fixtures import fixture_manifest

from large_smc_v112 import contract as C
from large_smc_v112 import watch as W
from v1_tickets import lsmc_v112_logic_gate as G

ROOT = Path(__file__).resolve().parents[1]

def rule_diff():
    old = yaml.safe_load(A.CANDIDATE_1_1_1_PATH.read_text())
    current = yaml.safe_load(G.CONTRACT_PATH.read_text())
    actual = sorted(A._spec_diff(old, current))
    declared = sorted(current['candidate_rule_changes']['declared_diff_paths'])
    return {'computed': actual, 'declared': declared, 'verdict': 'PASS' if actual == declared else 'FAIL'}

def _candidate_lane(function, *args):
    # A new function namespace keeps legacy audit modules and runtime imports untouched.
    namespace = {**function.__globals__, 'C': C, 'G': G, 'W': W}
    return types.FunctionType(function.__code__, namespace, function.__name__,
                              function.__defaults__, function.__closure__)(*args)


def build_report(crypto_scans=120, skip_crypto=False, lane_b_every=1):
    spec = yaml.safe_load(G.CONTRACT_PATH.read_text())
    cases = A.HARNESS.cases()
    sources = fixture_manifest()['sources']
    classifications = {A.HARNESS.VT_NAME.get(r['symbol'], r['symbol']): r for r in sources}
    results = [G.evaluate_case(spec, c) for c in cases]
    lane_b = _candidate_lane(A.lane_b, lane_b_every)
    lane_c = {'verdict': 'NOT_RUN', 'reason': '--skip-crypto'} if skip_crypto else _candidate_lane(A.lane_c, crypto_scans)
    matrix = {}
    for symbol in C.V1_SYMBOLS:
        rs = [r for r in results if r['symbol'] == symbol]
        gates = {}
        for name in ('L1', 'L2', 'L3', 'L4', 'L5', 'L6'):
            statuses = {r['gate_status'][name] for r in rs}
            replay = lane_b if symbol == 'EURUSD' else lane_c.get(symbol, {})
            replay_counts = dict(replay.get('gate_status_counts', {}).get(name, {}))
            # A closed FX market is an explicit input precondition, not an active-market gate PASS.
            if name == 'L4' and symbol == 'EURUSD' and lane_b.get('l4_fail_equals_market_closed'):
                replay_counts.pop('FAIL', None)
            statuses.update(k for k, count in replay_counts.items() if count)
            gates[name] = ('FAIL' if 'FAIL' in statuses else 'WARN' if 'WARN' in statuses
                           else 'PASS' if 'PASS' in statuses else 'NOT_APPLICABLE')
        priced = sum(r['stop_c10'] is not None and r['target_c11'] is not None for r in rs)
        matrix[symbol] = {'gates': gates, 'scope_verdict': 'NOT_VERIFIED', 'priced_opportunities': priced,
                          'fixture_provenance': classifications[symbol],
                          'pip_size': C.resolve_pip(symbol)[0], 'pip_source': C.resolve_pip(symbol)[1],
                          'replay_scope': ('575 EURUSD rolling fixture scans' if symbol == 'EURUSD'
                                           else f'{crypto_scans} bounded recorded full-D1 scans' if symbol in C.CRYPTO_SYMBOLS
                                           else 'committed synthetic/mixed fixtures only'),
                          'excluded_market_closed_scans': lane_b.get('market_closed_scans', 0) if symbol == 'EURUSD' else 0}
    pins = json.loads((ROOT/'tests/fixtures/c21/frozen_sha256.json').read_text())
    frozen = all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == v for p,v in pins.items())
    drift = rule_diff()
    lane_failures = []
    if lane_b['verdict'] == 'FAIL':
        lane_failures.append('B_historical_EURUSD')
    for symbol in C.CRYPTO_SYMBOLS:
        if lane_c.get(symbol, {}).get('verdict') == 'FAIL':
            lane_failures.append('C_recorded_' + symbol)
    return {'schema': 'AGP_C21_LSMC_V112_ENGINE_R2', 'strategy': 'ST_LARGE_SMC_V1@1.1.2',
            'verification_status': 'NOT_VERIFIED', 'scope_matrix': matrix, 'results': results,
            'check_coverage': G.check_coverage(results), 'rule_diff': drift,
            'identity': {'contract_sha256': A.sha256(G.CONTRACT_PATH), 'engine_sha256': G.engine_sha256(),
                         'engine_file_sha256': {p: G.file_sha256(p) for p in G.ENGINE_FILES},
                         'base_sha': A.code_sha(),
                         'fixture_manifest_sha256': A.sha256(ROOT/'tests/fixtures/large_smc_v111/manifest.json')},
            'frozen_v110_bytes_unchanged': frozen, 'lane_failures': lane_failures,
            'lanes': {'A_committed_18case': 'RUN', 'per_symbol_committed_fixtures': 'RUN',
                      'B_historical_EURUSD': lane_b, 'C_recorded_crypto_60d': lane_c},
            'verdict': 'FAIL' if (not frozen or drift['verdict'] == 'FAIL' or lane_failures
                                 or any(r['blocking_failures'] for r in results)) else 'NOT_VERIFIED'}

def main(args):
    # Persist an uncompleted-run marker first: a sandbox kill can never leave stale PASS evidence.
    path = Path(args.out) if args.out else None
    pending = {'schema': 'AGP_C21_LSMC_V112_ENGINE_R2', 'strategy': 'ST_LARGE_SMC_V1@1.1.2',
               'verdict': 'NOT_RUN_RESOURCE', 'verification_status': 'NOT_VERIFIED',
               'scope_matrix': {symbol: {'gates': {g: 'NOT_RUN_RESOURCE' for g in
                                                  ('L1', 'L2', 'L3', 'L4', 'L5', 'L6')}}
                                for symbol in C.V1_SYMBOLS}}
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pending, indent=2, sort_keys=True)+'\n')
    lock = RG.canonical_lock_path()
    owner = {'agent': 'CODEX_LOCAL', 'mission': 'AGP-C21-LSMC-V112-ENGINE-R2', 'pid': os.getpid()}
    resource = RG.acquire(lock, **owner, resource_class='R1',
                          command_summary='C21 committed fixtures; one worker')
    print(json.dumps(resource, sort_keys=True))
    if not resource['ACQUIRED']:
        return 2
    try:
        report = build_report(args.crypto_scans, args.skip_crypto, args.lane_b_every)
        report['resource_class'] = 'R1'
        report['worker_count'] = 1
        if path:
            path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str)+'\n')
        print(report['strategy'], report['verdict'])
        for symbol, row in report['scope_matrix'].items():
            print(symbol, row['gates'], 'priced=', row['priced_opportunities'], 'pip=', row['pip_size'])
        return 1 if report['verdict'] == 'FAIL' else 0
    finally:
        released = RG.release(lock, **owner)
        print(json.dumps(released, sort_keys=True))
        if not released['RELEASED']:
            raise RuntimeError('C21 resource lock release failed')
