"""C24 evidence-only full recorded replay; canonical engine and L1-L6 calls stay unchanged."""
import bisect
import csv
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import time
import types
from collections import Counter, OrderedDict
from pathlib import Path

import lsmc_v112_logic_audit as audit

A, C, G, RG = audit.A, audit.C, audit.G, audit.RG
ROOT = audit.ROOT
DATASET = A.CRYPTO_DATASET
GATES = ('L1', 'L2', 'L3', 'L4', 'L5', 'L6')
MISSION = 'AGP-C24-LSMC-V112-VERIFY-R2'
DECLARED_WARNINGS = {'L5': 'Existing canonical L5 cost placeholder: accepted cost/account evidence is incomplete; no cost or commission is invented.'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected_identity():
    paths = subprocess.check_output(['git', 'ls-files', 'src', 'strategies', 'config'], cwd=ROOT, text=True).splitlines()
    return {p: digest(ROOT/p) for p in paths if (ROOT/p).is_file()}


def inventory(symbol):
    paths = {tf: DATASET/f'{symbol}_{tf.lower()}.csv' for tf in ('D1', 'H1', 'M5')}
    required = list(paths.values()) + [DATASET/f'{symbol}_provenance.json']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        return {'verdict': 'DATA_INSUFFICIENT', 'missing_files': missing,
                'related_M15_only': f'tests/fixtures/manual_ticket/{symbol}_M15_recorded_spread_60d.csv',
                'reason': 'A recorded M15 capture cannot provide missing M5 OHLC; no interpolation or synthetic substitution.'}, None
    provenance = json.loads(required[-1].read_text())
    issues, data, identity = [], {}, {}
    if (provenance.get('source') != 'MT5_VT_MARKETS_DEMO' or provenance.get('server') != 'VTMarkets-Demo'
            or provenance.get('symbol') != symbol or provenance.get('recorded') is not True):
        issues.append('VT_PROVENANCE_NOT_EVIDENCED')
    if len(provenance.get('days', [])) != 60 or provenance.get('days_kept') != 60:
        issues.append('60_DAY_SET_NOT_EVIDENCED')
    for tf, path in paths.items():
        identity[str(path.relative_to(ROOT))] = digest(path)
        if identity[str(path.relative_to(ROOT))] != provenance.get('sha256', {}).get(tf.lower()):
            issues.append(f'{tf}:HASH_MISMATCH')
        with path.open() as stream:
            rows = list(csv.DictReader(stream))
        bars = []
        for row in rows:
            at = dt.datetime.fromisoformat(row['timestamp_utc'])
            prices = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
            if at.tzinfo is None or at.utcoffset() != dt.timedelta(0):
                issues.append(f'{tf}:TIMESTAMP_NOT_UTC')
            op, hi, lo, close = prices
            if not all(math.isfinite(x) and x > 0 for x in prices) or not lo <= min(op, close) <= max(op, close) <= hi:
                issues.append(f'{tf}:INVALID_OHLC')
            bars.append(A.Candle(at, *prices, None))
        if not bars or any(a.time >= b.time for a,b in zip(bars,bars[1:])):
            issues.append(f'{tf}:UNSORTED_OR_DUPLICATE_OR_EMPTY')
        data[tf] = bars
    days = sorted({b.time.date().isoformat() for b in data['M5']})
    if days != provenance.get('days'):
        issues.append('M5_RECORDED_DAYS_DIFFER_FROM_DECLARED_60_DAYS')
    expected = dt.timedelta(minutes=5)
    gaps = [{'after': a.time.isoformat(), 'before': b.time.isoformat(),
             'missing_bars': int((b.time-a.time)/expected)-1}
            for a,b in zip(data['M5'], data['M5'][1:]) if b.time-a.time > expected]
    identity[str(required[-1].relative_to(ROOT))] = digest(required[-1])
    info = {'verdict': 'FAIL' if issues else 'PASS_WITH_DECLARED_GAPS', 'issues': sorted(set(issues)),
            'missing_files': [], 'source': provenance.get('source'), 'server': provenance.get('server'),
            'captured_at_utc': provenance.get('captured_at_utc'), 'days': days,
            'period_start_utc': data['M5'][0].time.isoformat(),
            'period_end_utc': (data['M5'][-1].time+expected).isoformat(),
            'bars': {tf: len(v) for tf,v in data.items()}, 'sha256': identity,
            'recorded_gaps': gaps, 'gap_policy': 'Kept exactly as recorded; no fill, interpolation or replacement.',
            'quote_policy': 'MqlRates spread is bar metadata, not an evidenced contemporaneous bid/ask. No quote is invented.',
            'time_policy': 'UTC bar-open labels; evaluate each recorded M5 close; forming bars are passed through and independently checked by canonical L1.',
            'runtime_windows': A.HOST_COUNTS}
    return info, data


def branch_key(snap, case):
    signal = G.signal_snapshot(snap)
    o = signal.opportunity or {}
    history = ('INSUFFICIENT_H1_M5' if len(G._closed(case['H1'],'H1',case['now'])) < C.MIN_H1_BARS
               or len(G._closed(case['M5'],'M5',case['now'])) < C.MIN_M5_BARS
               else 'FULL_D1' if len(case['D1']) >= A.HOST_COUNTS['D1'] else 'SHORT_D1')
    return '|'.join((history, o.get('direction') or 'NONE',
                     (signal.poi or {}).get('kind') or 'NONE', o.get('c11_source') or 'NO_TARGET_OR_NO_OPPORTUNITY'))


def new_counts():
    return {'scans': 0, 'gates': {g: Counter() for g in GATES}, 'states': Counter(),
            'opportunity_scans': 0, 'priced_opportunity_scans': 0, 'rr_eligible_scans': 0,
            'terminal_reasons': Counter(), 'evaluated_checks': Counter(), 'not_applicable_checks': Counter()}


def add_result(counts, result, snap):
    counts['scans'] += 1
    counts['states'][result['signal_state']] += 1
    for gate, status in result['gate_status'].items():
        counts['gates'][gate][status] += 1
    for gate in result['gates'].values():
        for check in gate['checks']:
            field = 'not_applicable_checks' if check['verdict'] == 'NOT_APPLICABLE' else 'evaluated_checks'
            counts[field][check['id']] += 1
    o = snap.opportunity or {}
    if result['signal_state'] == 'OPPORTUNITY':
        counts['opportunity_scans'] += 1
        if o.get('stop_c10') is not None and o.get('target_c11') is not None:
            counts['priced_opportunity_scans'] += 1
            if o.get('reward_risk_reason') is None:
                counts['rr_eligible_scans'] += 1
    for reason in result['reason_codes']:
        counts['terminal_reasons'][reason] += 1
    for field in ('stop_reason','target_reason','reward_risk_reason'):
        if o.get(field):
            counts['terminal_reasons'][o[field]] += 1


def summary(counts, history_insufficient=False):
    gates = {g: ('FAIL' if c['FAIL'] else 'WARN' if c['WARN'] else 'PASS' if c['PASS'] else 'NOT_RUN')
             for g,c in counts['gates'].items()}
    eligible = (not history_insufficient and counts['rr_eligible_scans'] > 0
                and all(gates[g] == 'PASS' for g in GATES[:4])
                and all(gates[g] == 'PASS' or gates[g] == 'WARN' and g in DECLARED_WARNINGS for g in GATES[4:]))
    return {**counts, 'gate_verdicts': gates,
            'verdict': ('DATA_INSUFFICIENT' if history_insufficient else 'FAIL' if 'FAIL' in gates.values()
                        else 'PASS_WITH_DECLARED_WARN' if eligible else 'NOT_VERIFIED'),
            'qualifies_for_proposal': eligible, 'verification_status': 'NOT_VERIFIED'}


def clone(function, **overrides):
    return types.FunctionType(function.__code__, {**function.__globals__, **overrides},
                              function.__name__, function.__defaults__, function.__closure__)


class EvidenceEvaluator:
    """Memoize immutable H1 facts in the auditor namespace, never decisions or engine globals.

    The original h1_pois function computes every cache miss. Full closed OHLC/time/volume and
    break records form the key; returned POIs are frozen dataclasses. Every H1-window change
    and new opportunity plan is also checked against the completely unmodified engine.
    """
    def __init__(self):
        self.cache = OrderedDict()
        self.hits = self.misses = self.reference_checks = 0
        self.last_h1 = self.last_plan = None
        original = audit.W.h1_pois
        def facts(symbol, h1, breaks):
            key = (symbol, tuple((b.time,b.open,b.high,b.low,b.close,b.volume) for b in h1),
                   tuple((b.index,b.level,b.event,b.direction) for b in breaks))
            if key not in self.cache:
                values = tuple(original(symbol,h1,breaks))
                assert all(p.__dataclass_params__.frozen for p in values)
                self.cache[key]=values
                self.misses+=1
                if len(self.cache)>32:
                    self.cache.popitem(last=False)
            else:
                self.hits+=1
                self.cache.move_to_end(key)
            return list(self.cache[key])
        self.snapshot=clone(audit.W.evaluate_snapshot,h1_pois=facts)
        self.l1=clone(G.l1,evaluate_snapshot=self.snapshot)
        assert self.snapshot.__code__ is audit.W.evaluate_snapshot.__code__
        assert self.l1.__code__ is G.l1.__code__

    def evaluate(self,spec,case):
        result,snap=captured_evaluator(spec,case,self.snapshot,self.l1)
        h1=tuple((b.time,b.open,b.high,b.low,b.close,b.volume) for b in G._closed(case['H1'],'H1',case['now']))
        o=snap.opportunity or {}
        plan=tuple(o.get(k) for k in ('opp_id','entry_reference','stop_c10','target_c11','expires_at','reward_risk_reason'))
        if h1!=self.last_h1 or plan!=self.last_plan:
            reference=G.evaluate_snapshot(case['symbol'],case['D1'],case['H1'],case['M5'],case['now'])
            self.reference_checks+=1
            if G._payload(reference)!=G._payload(snap):
                raise RuntimeError('AUDITOR_REFERENCE_PARITY_FAIL: '+case['case_id'])
        self.last_h1,self.last_plan=h1,plan
        return result,snap

    def statistics(self):
        return {'h1_fact_cache_hits':self.hits,'h1_fact_cache_misses':self.misses,
                'uncached_snapshot_reference_checks':self.reference_checks,
                'engine_globals_modified':False,'snapshot_or_check_cache':False,
                'reference_parity':'PASS'}


def captured_evaluator(spec, case, snapshot=None, l1=None):
    snapshots = []
    def capture(*args, **kwargs):
        snap = (snapshot or G.evaluate_snapshot)(*args, **kwargs)
        snapshots.append(snap)
        return snap
    evaluate = clone(G.evaluate_case,evaluate_snapshot=capture,l1=l1 or G.l1)
    result = evaluate(spec, case)
    return result, snapshots[0]


def write_report(path, report):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=lambda x: dict(x))+'\n')
    tmp.replace(path)


def run(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'AGP_C24_LSMC_V112_VERIFY_R2', 'mission': MISSION,
              'strategy': 'ST_LARGE_SMC_V1@1.1.2', 'base_sha': A.code_sha(),
              'verification_status': 'NOT_VERIFIED', 'verdict': 'NOT_RUN_RESOURCE',
              'phase': 'P1_CRYPTO', 'P2': 'NOT_RUN', 'P3': 'PENDING_D1',
              'declared_warnings': DECLARED_WARNINGS, 'symbols': {s: {'verdict':'NOT_RUN_RESOURCE'} for s in C.V1_SYMBOLS},
              'signal_event_log': 'signal_events.jsonl', 'scan_log': 'scans.csv', 'mismatch_log': 'mismatches.jsonl',
              'proposal': 'NOT_RUN', 'resource_class':'R1', 'workers':1}
    write_report(path, report)
    owner = {'agent':'CODEX_LOCAL', 'mission':MISSION, 'pid':os.getpid()}
    lock = RG.canonical_lock_path()
    acquired = RG.acquire(lock, **owner, resource_class='R1', command_summary='C24 full committed replay, one worker, original engine and L1-L6')
    print(json.dumps(acquired), flush=True)
    if not acquired['ACQUIRED']:
        return 2
    started = time.monotonic()
    try:
        protected = protected_identity()
        report['identity'] = {'contract_sha256':digest(G.CONTRACT_PATH), 'engine_sha256':G.engine_sha256(),
                              'engine_file_sha256':{p:G.file_sha256(p) for p in G.ENGINE_FILES},
                              'protected_file_sha256':protected, 'runner_sha256':digest(__file__)}
        report['rule_diff'] = audit.rule_diff()
        if report['rule_diff']['verdict'] != 'PASS':
            report['verdict']='FAIL';write_report(path,report);return 1
        spec = json.loads(json.dumps(C.SPEC))
        with (path.parent/'signal_events.jsonl').open('w') as events, (path.parent/'mismatches.jsonl').open('w') as mismatch, (path.parent/'scans.csv').open('w',newline='') as scans:
            writer=csv.writer(scans);writer.writerow(['symbol','m5_row','closed_at_utc','branch','operational_state','signal_state',*GATES,'opp_id','entry','stop','target','pip_source','c11_source','rr','rr_block'])
            for symbol in C.V1_SYMBOLS:
                if symbol not in C.CRYPTO_SYMBOLS:
                    report['symbols'][symbol]={'verdict':'PENDING_D1','phase':'P3','gates':{g:'NOT_RUN' for g in GATES},'required_dataset':'tests/fixtures/vt_recorded_60d_fx'}
                    write_report(path,report)
                    continue
                info, bars = inventory(symbol)
                report['symbols'][symbol]={'verdict':'NOT_RUN_RESOURCE','data_audit':info}
                if bars is None or info['verdict']=='FAIL':
                    report['symbols'][symbol].update(verdict=info['verdict'],gates={g:'NOT_RUN' for g in GATES},branch_matrix={},scans=0)
                    write_report(path,report);continue
                times={tf:[b.time for b in rows] for tf,rows in bars.items()}
                evaluator=EvidenceEvaluator()
                total, active = new_counts(),new_counts()
                branches={}; mismatches=Counter();previous=None;last_checkpoint=time.monotonic()
                for i, bar in enumerate(bars['M5']):
                    now=bar.time+dt.timedelta(minutes=5)
                    windows={tf:rows[max(0,bisect.bisect_right(times[tf],now)-A.HOST_COUNTS[tf]):bisect.bisect_right(times[tf],now)] for tf,rows in bars.items()}
                    case={'case_id':f'{symbol}:{now.isoformat()}','symbol':symbol,'now':now,'fixture':str(DATASET.relative_to(ROOT)),'classification':'VT_RECORDED',**windows}
                    result,snap=evaluator.evaluate(spec,case)
                    signal=G.signal_snapshot(snap);o=signal.opportunity or {}
                    key=branch_key(snap,case);counts=branches.setdefault(key,new_counts());add_result(counts,result,snap);add_result(total,result,snap)
                    warmup=key.startswith('INSUFFICIENT_H1_M5|')
                    if not warmup: add_result(active,result,snap)
                    row=[symbol,i,now.isoformat(),key,result['state'],result['signal_state'],*[result['gate_status'][g] for g in GATES],o.get('opp_id'),o.get('entry_reference'),o.get('stop_c10'),o.get('target_c11'),o.get('pip_source'),o.get('c11_source'),o.get('reward_risk'),o.get('reward_risk_reason')]
                    writer.writerow(row)
                    signature=(signal.state,o.get('opp_id'),(signal.poi or {}).get('poi_id'))
                    if signature!=previous:
                        events.write(json.dumps({'symbol':symbol,'m5_row':i,'evaluated_at_utc':now.isoformat(),'from_signal':previous[0] if previous else None,'branch':key,'snapshot':dataclasses.asdict(signal),'operational_state':snap.state,'gate_status':result['gate_status']},default=str,sort_keys=True)+'\n');previous=signature
                    for gate in result['blocking_failures']:
                        category='EXPECTED_INSUFFICIENT_HISTORY' if warmup and gate=='L4' else 'UNEXPECTED_'+gate
                        mismatches[category]+=1
                        mismatch.write(json.dumps({'symbol':symbol,'m5_row':i,'evaluated_at_utc':now.isoformat(),'branch':key,'category':category,'gate':result['gates'][gate]},sort_keys=True)+'\n')
                    if (i+1)%100==0 or i+1==len(bars['M5']) or time.monotonic()-last_checkpoint>=30:
                        last_checkpoint=time.monotonic()
                        report['symbols'][symbol].update(completed_scans=i+1,total_recorded_scans=len(bars['M5']),elapsed_seconds=round(time.monotonic()-started,2))
                        write_report(path,report);events.flush();mismatch.flush();scans.flush()
                        pulse=RG.heartbeat(lock,**owner)
                        if not pulse['HEARTBEAT_UPDATED']: raise RuntimeError('resource heartbeat failed')
                        print(f'{symbol} {i+1}/{len(bars["M5"])} elapsed={time.monotonic()-started:.1f}s',flush=True)
                matrix={k:summary(v,k.startswith('INSUFFICIENT_H1_M5|')) for k,v in branches.items()}
                row=summary(active)
                row.update(evaluator=evaluator.statistics(),data_audit=info,raw_all_scans=summary(total),branch_matrix=matrix,mismatch_categories=dict(mismatches),scans=len(bars['M5']),qualifies_for_proposal=any(v['qualifies_for_proposal'] for v in matrix.values()))
                row['verdict']='FAIL' if any(k.startswith('UNEXPECTED_') for k in mismatches) else 'PASS_WITH_DECLARED_WARN' if row['qualifies_for_proposal'] else 'NOT_VERIFIED'
                report['symbols'][symbol]=row;write_report(path,report)
        report['protected_bytes_unchanged']=protected==protected_identity()
        eligible=[s for s,row in report['symbols'].items() if row.get('qualifies_for_proposal')]
        report['proposal_qualifying_symbols']=eligible
        report['proposal']='PENDING_ORACLE' if eligible else 'NO_QUALIFYING_SCOPE'
        report['elapsed_seconds']=round(time.monotonic()-started,2)
        report['verdict']='FAIL' if not report['protected_bytes_unchanged'] or any(r['verdict']=='FAIL' for r in report['symbols'].values()) else 'P1_COMPLETED_P3_PENDING_D1'
        write_report(path,report)
        print(json.dumps({s:r['verdict'] for s,r in report['symbols'].items()}),flush=True)
        return 1 if report['verdict']=='FAIL' else 0
    finally:
        released=RG.release(lock,**owner);print(json.dumps(released),flush=True)
        if not released['RELEASED']: raise RuntimeError('C24 lock release failed')
        report['resource_lock_released']=True
        write_report(path,report)


def cli():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,help='full 60-day audit JSON; adjacent logs are written separately')
    return run(parser.parse_args().out)
