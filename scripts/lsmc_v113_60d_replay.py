"""C24 evidence-only sharded recorded replay; canonical engine and L1-L6 calls stay unchanged."""
import bisect
import copy
import csv
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

import lsmc_v113_logic_audit as audit

from large_smc_v113 import targets as T

A, C, G, RG = audit.A, audit.C, audit.G, audit.RG
ROOT = audit.ROOT
DATASET = A.CRYPTO_DATASET
FX_DATASET = ROOT/'tests/fixtures/vt_recorded_60d_fx'   # #215 D1-R2 recorded VT 60d FX/gold capture
SYMBOLS = ('EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD')
GATES = ('L1', 'L2', 'L3', 'L4', 'L5', 'L6')
MISSION = 'AGP-LSMC113-EURUSD-ENTRY'
SHARDS = 6


def dataset(symbol):
    return DATASET if symbol in C.CRYPTO_SYMBOLS else FX_DATASET
# OD1011-L5: L5 is PASS / INSUFFICIENT (cost-blocked = actionability outcome); no declared WARN is accepted.
COST_SOURCE = ('VT recorded M5 spread_price of the last closed bar (<dataset>/<SYM>_m5_meta.csv) + OD1011-COMMISSION: '
               'crypto via scripts/ccfd_sweep_retest_replay.commission_binding (the accepted source of the CCFD 1.0.0 L5 PASS), '
               'FX/gold via config/owner_ticket.yaml bound to the capture server/login suffix, OD1009-D2 thresholds')
_COST = {}


def cost_source(symbol):
    """Spread by M5 bar open time + commission binding, loaded once per symbol (read-only)."""
    if symbol not in _COST:
        import ccfd_sweep_retest_replay as ccfd
        with (dataset(symbol)/f'{symbol}_m5_meta.csv').open() as stream:
            spread = {dt.datetime.fromisoformat(r['timestamp_utc']): float(r['spread_price']) for r in csv.DictReader(stream)}
        provenance = json.loads((dataset(symbol)/f'{symbol}_provenance.json').read_text())
        binding = (ccfd.commission_binding(provenance) if symbol in C.CRYPTO_SYMBOLS
                   else fx_commission_binding(provenance))
        _COST[symbol] = {'spread': spread, 'binding': binding}
    return _COST[symbol]


def fx_commission_binding(provenance):
    """OD1011-COMMISSION (FX and gold, OD1012-ACCOUNT): FULL account binding only, via the canonical
    manual_ticket.resolve_commission. The full login lives only in gitignored config/local/owner_ticket.yaml and
    must end with the capture's recorded login suffix on the same server; a committed suffix alone is never a
    binding (-> None -> L5 INSUFFICIENT, never PASS)."""
    from v1_tickets.manual_ticket import load_owner_config, resolve_commission
    owner = load_owner_config()
    full = (owner.get('commission') or {}).get('account_login')
    suffix = str(provenance.get('login_suffix') or '')
    if (full is None or not suffix or not str(full).endswith(suffix) or provenance.get('server') != 'VTMarkets-Demo'
            or provenance.get('source') != 'MT5_VT_MARKETS_DEMO'):
        return None
    value = resolve_commission(owner, full)
    if type(value) not in (int, float) or value != 0:
        return None
    return {'value': 0.0, 'source': 'OD1011-COMMISSION', 'policy': 'OD1009-D2', 'bound_server': 'VTMarkets-Demo',
            'account_login_suffix': suffix, 'binding': 'FULL_ACCOUNT_LOGIN'}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected_identity():
    paths = subprocess.check_output(['git', 'ls-files', 'src', 'strategies', 'config'], cwd=ROOT, text=True).splitlines()
    return {p: digest(ROOT/p) for p in paths if (ROOT/p).is_file()}


def inventory(symbol):
    paths = {tf: dataset(symbol)/f'{symbol}_{tf.lower()}.csv' for tf in ('D1', 'H1', 'M5')}
    required = list(paths.values()) + [dataset(symbol)/f'{symbol}_provenance.json']
    fx = symbol not in C.CRYPTO_SYMBOLS
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
    if fx:   # D1-R2 shape: window_start/end + per-file hashes; warmup rows precede the 60-day window
        if provenance.get('window_days') != 60:
            issues.append('60_DAY_SET_NOT_EVIDENCED')
        expected_hash = {tf: (provenance.get('files') or {}).get(f'{symbol}_{tf.lower()}.csv') for tf in paths}
    else:
        if len(provenance.get('days', [])) != 60 or provenance.get('days_kept') != 60:
            issues.append('60_DAY_SET_NOT_EVIDENCED')
        expected_hash = {tf: provenance.get('sha256', {}).get(tf.lower()) for tf in paths}
    for tf, path in paths.items():
        identity[str(path.relative_to(ROOT))] = digest(path)
        if identity[str(path.relative_to(ROOT))] != expected_hash[tf]:
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
    if fx:
        start, end = (dt.datetime.fromisoformat(provenance[k]) for k in ('window_start_utc', 'window_end_utc'))
        days = sorted({b.time.date().isoformat() for b in data['M5'] if start <= b.time < end})
        if (end - start).days != 60 or not days:
            issues.append('M5_RECORDED_DAYS_DIFFER_FROM_DECLARED_60_DAYS')
    else:
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
            'window_policy': ('FX: recorded window_start..window_end (60 calendar days, UTC dates with M5 bars); earlier '
                              'recorded rows are warmup only' if fx else 'crypto: 60 declared recorded days'),
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
    history = ('MARKET_CLOSED' if snap.state == 'MARKET_CLOSED'
               else 'INSUFFICIENT_H1_M5' if len(G._closed(case['H1'],'H1',case['now'])) < C.MIN_H1_BARS
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
    gates = {g: ('FAIL' if c['FAIL'] else 'WARN' if c['WARN'] else 'INSUFFICIENT' if c['INSUFFICIENT']
                 else 'PASS' if c['PASS'] else 'NOT_RUN')
             for g,c in counts['gates'].items()}
    eligible = (not history_insufficient and counts['rr_eligible_scans'] > 0
                and all(gates[g] == 'PASS' for g in GATES))
    return {**counts, 'gate_verdicts': gates,
            'verdict': ('DATA_INSUFFICIENT' if history_insufficient else 'FAIL' if 'FAIL' in gates.values()
                        else 'PASS' if eligible else 'INSUFFICIENT'),
            'qualifies_for_proposal': eligible, 'verification_status': 'NOT_VERIFIED'}


def clone(function, **overrides):
    result = types.FunctionType(function.__code__, {**function.__globals__, **overrides},
                                function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


class EvidenceEvaluator:
    """Memoize immutable H1 facts in the auditor namespace, never decisions or engine globals.

    The original h1_pois function computes every cache miss. Full closed OHLC/time/volume and
    break records form the key; returned POIs are frozen dataclasses. Every H1-window change
    and new opportunity plan is also checked against the completely unmodified engine.
    """
    def __init__(self):
        self.cache = OrderedDict()
        self.hits = self.misses = self.reference_checks = 0
        self.target_cache = OrderedDict()
        self.target_hits = self.target_misses = 0
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
        original_target = audit.W._candidate_target_at_creation
        def creation_facts(opportunity, creation, history):
            if not isinstance(history, dict) or not isinstance(history.get('capture_start_utc'), dict):
                return original_target(opportunity, creation, history)
            windows = {tf:T._creation_window(history.get(tf),tf,creation,history['capture_start_utc'].get(tf))
                       for tf in ('M5','H1')}
            if any(value is None for value in windows.values()):
                return original_target(opportunity,creation,history)
            key = (creation,opportunity.get('symbol'),opportunity.get('direction'),opportunity.get('entry_reference'),
                   tuple((tf,history['capture_start_utc'].get(tf),
                          tuple((b.time,b.open,b.high,b.low,b.close,b.volume) for b in windows[tf]))
                         for tf in ('M5','H1')))
            if key not in self.target_cache:
                self.target_cache[key] = original_target(opportunity,creation,history)
                self.target_misses += 1
                if len(self.target_cache)>256:
                    self.target_cache.popitem(last=False)
            else:
                self.target_hits += 1
                self.target_cache.move_to_end(key)
            return copy.deepcopy(self.target_cache[key])
        self.snapshot=clone(audit.W.evaluate_snapshot,h1_pois=facts,_candidate_target_at_creation=creation_facts)
        self.l1=clone(G.l1,evaluate_snapshot=self.snapshot)
        assert self.snapshot.__code__ is audit.W.evaluate_snapshot.__code__
        assert self.l1.__code__ is G.l1.__code__

    def evaluate(self,spec,case):
        result,snap=captured_evaluator(spec,case,self.snapshot,self.l1)
        h1=tuple((b.time,b.open,b.high,b.low,b.close,b.volume) for b in G._closed(case['H1'],'H1',case['now']))
        o=snap.opportunity or {}
        plan=tuple(o.get(k) for k in ('opp_id','entry_reference','target_c11','c11_source','expires_at','reward_risk_reason'))
        if h1!=self.last_h1 or plan!=self.last_plan:
            reference=G.evaluate_snapshot(case['symbol'],case['D1'],case['H1'],case['M5'],case['now'],target_history=case.get('target_history'))
            self.reference_checks+=1
            if G._payload(reference)!=G._payload(snap):
                raise RuntimeError('AUDITOR_REFERENCE_PARITY_FAIL: '+case['case_id'])
        self.last_h1,self.last_plan=h1,plan
        return result,snap

    def statistics(self):
        return {'h1_fact_cache_hits':self.hits,'h1_fact_cache_misses':self.misses,
                'creation_fact_cache_hits':self.target_hits,'creation_fact_cache_misses':self.target_misses,
                'uncached_snapshot_reference_checks':self.reference_checks,
                'engine_globals_modified':False,'snapshot_or_check_cache':False,
                'native_reference_schedule':'Every closed H1 window change and new opportunity/C11/eligibility plan; C10 is always recomputed, never memoized.',
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


SHARD_DAYS = 10
BOUNDARY_BARS = 12
INACTIVE_BRANCHES = ('INSUFFICIENT_H1_M5', 'MARKET_CLOSED')   # expected L4.evaluated/history FAILs, excluded from active


def inactive(branch):
    return branch.startswith(INACTIVE_BRANCHES)


def ny_trading_date(t):
    """Independent NY-17:00 trading date (zoneinfo), not the engine's trading_date."""
    from zoneinfo import ZoneInfo
    return (t.astimezone(ZoneInfo('America/New_York')) + dt.timedelta(hours=7)).date()


def independent_poi_age(origin, h1, now):
    """D-LSMC-6 contract unit: distinct observed closed-H1 NY-17 weekday trading dates since origin, minus one."""
    dates = {ny_trading_date(b.time) for b in h1 if origin <= b.time and b.time + dt.timedelta(hours=1) <= now}
    dates |= {ny_trading_date(origin), ny_trading_date(now)}
    first, last = ny_trading_date(origin), ny_trading_date(now)
    return max(0, len({d for d in dates if first <= d <= last and d.weekday() < 5}) - 1)


def crypto_calendar_expiry(origin):
    """Crypto keeps the seven-day calendar unit: expiry at the (max_age+1)-th NY-17 boundary after origin."""
    from zoneinfo import ZoneInfo
    ny = ZoneInfo('America/New_York')
    local = origin.astimezone(ny)
    boundary = local.replace(hour=17, minute=0, second=0, microsecond=0)
    if local >= boundary:
        boundary = (local.replace(tzinfo=None) + dt.timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0).replace(tzinfo=ny)
    for _ in range(C.POI_MAX_AGE_TRADING_DAYS):
        boundary = (boundary.replace(tzinfo=None) + dt.timedelta(days=1)).replace(tzinfo=ny)
    return boundary.astimezone(dt.timezone.utc)


def new_dlsmc():
    return {'D-LSMC-6': Counter(), 'D-LSMC-1': Counter()}


def check_dlsmc(state, symbol, case, snap, sig, origins, violations):
    """D-LSMC-6: every observed active POI is within age; every expiry it later reports is past age.
    D-LSMC-1: every detected OPPORTUNITY carries a C10 stop from the host-captured pip; no C10_PIP_SIZE_NOT_EVIDENCED."""
    now, crypto = case['now'], symbol in C.CRYPTO_SYMBOLS
    h1 = G._closed(case['H1'], 'H1', now)
    for poi in [sig.poi] if sig.poi and sig.poi.get('origin_time') else []:
        origin = dt.datetime.fromisoformat(poi['origin_time'])
        origins[poi['poi_id']] = origin
        ok = now < crypto_calendar_expiry(origin) if crypto else independent_poi_age(origin, h1, now) <= C.POI_MAX_AGE_TRADING_DAYS
        state['D-LSMC-6']['active_checks'] += 1
        if not ok:
            state['D-LSMC-6']['active_violations'] += 1
            violations.append({'defect': 'D-LSMC-6', 'kind': 'ACTIVE_PAST_AGE', 'poi_id': poi['poi_id'], 'at': now.isoformat()})
    for poi_id in snap.expired_poi_ids:
        if poi_id not in origins:
            state['D-LSMC-6']['expiry_unobserved_origin'] += 1
            continue
        origin = origins[poi_id]
        ok = now >= crypto_calendar_expiry(origin) if crypto else independent_poi_age(origin, h1, now) > C.POI_MAX_AGE_TRADING_DAYS
        state['D-LSMC-6']['expiry_checks'] += 1
        if not ok:
            state['D-LSMC-6']['expiry_violations'] += 1
            violations.append({'defect': 'D-LSMC-6', 'kind': 'EXPIRED_WITHIN_AGE', 'poi_id': poi_id, 'at': now.isoformat()})
    if 'C10_PIP_SIZE_NOT_EVIDENCED' in snap.reason_codes:
        state['D-LSMC-1']['pip_not_evidenced_scans'] += 1
        violations.append({'defect': 'D-LSMC-1', 'kind': 'C10_PIP_SIZE_NOT_EVIDENCED', 'at': now.isoformat()})
    o = sig.opportunity or {}
    if sig.state == 'OPPORTUNITY' and o:
        state['D-LSMC-1']['opportunity_scans'] += 1
        pip, source = C.resolve_pip(symbol)
        if o.get('stop_c10') is None and o.get('stop_reason') != 'C10_PIP_SIZE_NOT_EVIDENCED':
            state['D-LSMC-1'][f"stop_none_contract_reason:{o.get('stop_reason')}"] += 1   # C10 evaluated, not a pip gap
        elif o.get('stop_c10') is None:
            state['D-LSMC-1']['stop_missing'] += 1
            violations.append({'defect': 'D-LSMC-1', 'kind': 'STOP_MISSING', 'opp_id': o.get('opp_id'),
                               'stop_reason': o.get('stop_reason'), 'at': now.isoformat()})
        elif [o.get('pip_size'), o.get('pip_source')] != [pip, source]:
            state['D-LSMC-1']['pip_source_mismatch'] += 1
            violations.append({'defect': 'D-LSMC-1', 'kind': 'PIP_SOURCE_MISMATCH', 'opp_id': o.get('opp_id'), 'at': now.isoformat()})
        else:
            state['D-LSMC-1']['stop_present_host_pip'] += 1


def dlsmc_verdicts(state):
    six, one = state['D-LSMC-6'], state['D-LSMC-1']
    return {'D-LSMC-6': ('FAIL' if six['active_violations'] or six['expiry_violations'] else
                         'PASS' if six['active_checks'] and six['expiry_checks'] else 'INSUFFICIENT'),
            'D-LSMC-1': ('FAIL' if one['stop_missing'] or one['pip_source_mismatch'] or one['pip_not_evidenced_scans'] else
                         'PASS' if one['stop_present_host_pip'] else 'INSUFFICIENT')}


def layout(info, bars, shard):
    if shard not in range(SHARDS):
        raise ValueError('60 recorded days require shards 0..5')
    size = math.ceil(len(info['days'])/SHARDS)
    days = info['days'][shard*size:(shard+1)*size]
    indices = [i for i,b in enumerate(bars['M5']) if b.time.date().isoformat() in days]
    start, end = min(indices),max(indices)+1
    probe = max(0,start-BOUNDARY_BARS)
    first_now = bars['M5'][probe].time+dt.timedelta(minutes=5)
    formation_start = max(0,bisect.bisect_right(bars['M5'],first_now,key=lambda b:b.time)-A.HOST_COUNTS['M5'])
    oldest_creation = bars['M5'][formation_start].time+dt.timedelta(minutes=5)
    starts = {}
    for tf, rows in bars.items():
        current_end = bisect.bisect_right(rows,first_now,key=lambda b:b.time)
        current_start = max(0,current_end-A.HOST_COUNTS[tf])
        creation_end = bisect.bisect_right(rows,oldest_creation-dt.timedelta(minutes=C.TIMEFRAME_MINUTES[tf]),key=lambda b:b.time)
        target_start = max(0,creation_end-C.SPEC['rules']['targets']['creation_window']['lookback_closed_bars'].get(tf,0))
        starts[tf] = min(current_start,target_start) if tf != 'D1' else current_start
    return {'days':days,'core_start_row':start,'core_end_row_exclusive':end,'core_scans':end-start,
            'warmup_start_row':starts,'oldest_possible_creation_close':oldest_creation.isoformat(),
            'boundary_overlap_bars_each_side':BOUNDARY_BARS,
            'warmup_policy':'Current host windows plus the complete declared creation lookback before the oldest possible active creation bar; original capture start retained; no synthetic overlap.'}


def make_case(symbol, bars, row, starts=None):
    now = bars['M5'][row].time+dt.timedelta(minutes=5)
    windows, history = {},{}
    for tf, rows in bars.items():
        end = bisect.bisect_right(rows,now,key=lambda b:b.time)
        begin = (starts or {}).get(tf,0)
        available = rows[begin:end]
        windows[tf] = available[-A.HOST_COUNTS[tf]:]
        if tf in ('H1','M5'):
            history[tf] = available
    history['capture_start_utc'] = {tf:bars[tf][0].time.isoformat() for tf in ('H1','M5')}
    cost = cost_source(symbol)
    last = bars['M5'][row]
    return {'cost_evidence':{'spread':cost['spread'].get(last.time),
                             'spread_bar_close_utc':(last.time+dt.timedelta(minutes=5)).isoformat(),
                             'commission_binding':cost['binding']},'case_id':f'{symbol}:{now.isoformat()}','symbol':symbol,'now':now,
            'fixture':str(dataset(symbol).relative_to(ROOT)),'classification':'VT_RECORDED',
            'target_history':history,**windows}


def native_snapshot(case):
    return G.evaluate_snapshot(case['symbol'],case['D1'],case['H1'],case['M5'],case['now'],
                               target_history=case['target_history'])


def boundary_reference(symbol,bars,plan):
    start,end = plan['core_start_row'],plan['core_end_row_exclusive']
    rows = sorted(set(range(max(0,start-BOUNDARY_BARS),min(len(bars['M5']),start+BOUNDARY_BARS))) |
                  set(range(max(0,end-BOUNDARY_BARS),min(len(bars['M5']),end+BOUNDARY_BARS))))
    checks=[]
    for row in rows:
        a = native_snapshot(make_case(symbol,bars,row,plan['warmup_start_row']))
        b = native_snapshot(make_case(symbol,bars,row))
        left,right = G._payload(a),G._payload(b)
        checks.append({'m5_row':row,'at':a.evaluated_at,'equal':left==right,
                       'shard_sha256':hashlib.sha256(json.dumps(left,sort_keys=True).encode()).hexdigest(),
                       'reference_sha256':hashlib.sha256(json.dumps(right,sort_keys=True).encode()).hexdigest(),
                       'opportunity_id':(a.opportunity or {}).get('opp_id')})
    return {'verdict':'PASS' if checks and all(x['equal'] for x in checks) else 'FAIL',
            'method':'Unmodified evaluator on overlapping boundary rows; warmed shard inputs vs independent full-recorded-history reference inputs; compare complete snapshot, not only signal id.',
            'checks':checks,'overlapping_reference_shard_rows':rows}


def run_shard(path,symbol,shard):
    if symbol not in SYMBOLS:
        raise ValueError(f'unknown symbol {symbol}')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    report={'mission':MISSION,'strategy':'ST_LARGE_SMC_V1@1.1.3','symbol':symbol,'shard':shard,
            'scope_days':60,'shard_days':SHARD_DAYS,'verdict':'NOT_RUN_RESOURCE','completed':False,
            'verification_status':'NOT_VERIFIED','resource_class':'R1','workers':1,
            'l5_cost_source':COST_SOURCE,'boundary_reference':{'verdict':'NOT_RUN'},
            'engine_defects':[],'dataset':str(dataset(symbol).relative_to(ROOT))}
    write_report(path,report)
    owner={'agent':'CLAUDE_CODE_WEB','mission':MISSION,'pid':os.getpid()};lock=RG.canonical_lock_path()
    acquired=RG.acquire(lock,**owner,resource_class='R1',command_summary=f'{MISSION} {symbol} shard {shard}; one worker')
    print(json.dumps(acquired),flush=True)
    if not acquired['ACQUIRED']:
        return 2
    started=time.monotonic()
    try:
        protected=protected_identity()
        report['identity']={'code_sha':A.code_sha(),'contract_sha256':digest(G.CONTRACT_PATH),
                            'engine_sha256':G.engine_sha256(),'runner_sha256':digest(__file__),
                            'frozen_file_sha256':audit.frozen_identity()}
        report['rule_diff']=audit.rule_diff()
        if report['rule_diff']['verdict']!='PASS':
            report['verdict']='FAIL_UNDECLARED_RULE_DRIFT';write_report(path,report);return 1
        info,bars=inventory(symbol);report['data_audit']=info
        if bars is None or info['verdict']=='FAIL':
            report['verdict']=info['verdict'];write_report(path,report);return 1
        plan=layout(info,bars,shard);report['layout']=plan;write_report(path,report)
        evaluator=EvidenceEvaluator();total,active=new_counts(),new_counts();branches={};previous=None
        selections={};mismatch_counts=Counter();last_checkpoint=time.monotonic()
        dlsmc,origins,dviolations=new_dlsmc(),{},[]
        with (path.parent/'signal_events.jsonl').open('w') as events,(path.parent/'mismatches.jsonl').open('w') as mismatches,(path.parent/'scans.csv').open('w',newline='') as scans:
            writer=csv.writer(scans);writer.writerow(['symbol','m5_row','closed_at_utc','branch','operational_state','signal_state',*GATES,'opp_id','entry','stop','target','pip_source','c11_source','rr','rr_block','creation_target_sha256','l5_cost_R','l5_actionability'])
            for row in range(plan['core_start_row'],plan['core_end_row_exclusive']):
                case=make_case(symbol,bars,row,plan['warmup_start_row'])
                result,snap=evaluator.evaluate(C.SPEC,case);signal=G.signal_snapshot(snap);o=signal.opportunity or {}
                branch=branch_key(snap,case);add_result(total,result,snap)
                add_result(branches.setdefault(branch,new_counts()),result,snap)
                if not inactive(branch):
                    add_result(active,result,snap)
                check_dlsmc(dlsmc,symbol,case,snap,signal,origins,dviolations)
                target={k:o.get(k) for k in ('target_c11','target_reason','c11_source','target_selection')}
                target_hash=hashlib.sha256(json.dumps(target,sort_keys=True).encode()).hexdigest() if o else ''
                if o:
                    opp_id=o['opp_id']
                    if opp_id in selections and selections[opp_id]['target_sha256']!=target_hash:
                        defect={'category':'ENGINE_DEFECT','defect_id':'C24-C11-RETARGET-V113','file_line':'src/large_smc_v113/watch.py:264','opp_id':opp_id,'before':selections[opp_id],'after':{'m5_row':row,'target':target,'target_sha256':target_hash},'minimal_repro':'make_case(symbol, committed_bars, before/after row, warmup starts); native_snapshot(case)'}
                        report['engine_defects'].append(defect);mismatches.write(json.dumps(defect,sort_keys=True)+'\n');mismatch_counts['ENGINE_DEFECT']+=1
                    selections[opp_id]={'m5_row':row,'target':target,'target_sha256':target_hash}
                signature=(signal.state,o.get('opp_id'),(signal.poi or {}).get('poi_id'),o.get('entry_reference'),o.get('stop_c10'),o.get('target_c11'),o.get('reward_risk_reason'))
                if signature!=previous:
                    events.write(json.dumps({'symbol':symbol,'m5_row':row,'evaluated_at_utc':snap.evaluated_at,
                                             'branch':branch,'operational_state':snap.state,'gate_status':result['gate_status'],
                                             'snapshot':G._payload(signal)},sort_keys=True)+'\n');previous=signature
                for gate in GATES:
                    if result['gate_status'][gate]=='FAIL':
                        category=('EXPECTED_INSUFFICIENT_HISTORY' if branch.startswith('INSUFFICIENT_H1_M5') and gate=='L4'
                                  else 'EXPECTED_MARKET_CLOSED' if branch.startswith('MARKET_CLOSED') and gate=='L4' else f'UNEXPECTED_{gate}')
                        mismatch_counts[category]+=1
                        mismatches.write(json.dumps({'category':category,'symbol':symbol,'m5_row':row,'gate':gate,'at':snap.evaluated_at,'checks':result['gates'][gate]},sort_keys=True)+'\n')
                writer.writerow([symbol,row,snap.evaluated_at,branch,snap.state,signal.state,*[result['gate_status'][g] for g in GATES],o.get('opp_id'),o.get('entry_reference'),o.get('stop_c10'),o.get('target_c11'),o.get('pip_source'),o.get('c11_source'),o.get('reward_risk'),o.get('reward_risk_reason'),target_hash,result['gates']['L5'].get('cost_R'),result['gates']['L5'].get('actionability')])
                done=row-plan['core_start_row']+1
                if done%100==0 or time.monotonic()-last_checkpoint>30:
                    for stream in (events,mismatches,scans):stream.flush()
                    report.update(completed_scans=done,elapsed_seconds=round(time.monotonic()-started,2),evaluator=evaluator.statistics())
                    write_report(path,report);RG.heartbeat(lock,**owner);last_checkpoint=time.monotonic()
                    print(f'{symbol} shard{shard} {done}/{plan["core_scans"]} elapsed={report["elapsed_seconds"]}s',flush=True)
        report['boundary_reference']=boundary_reference(symbol,bars,plan)
        report['protected_bytes_unchanged']=protected==protected_identity()
        report['raw_all_scans']=summary(total);report['active_history_scans']=summary(active)
        report['branch_matrix']={key:summary(value,history_insufficient=inactive(key)) for key,value in sorted(branches.items())}
        report['dlsmc_recheck']={'counts':{k:dict(v) for k,v in dlsmc.items()},'verdicts':dlsmc_verdicts(dlsmc),
                                 'violations':dviolations[:50],'violation_count':len(dviolations)}
        report['mismatch_categories']=dict(mismatch_counts);report['selections']=selections
        report.update(completed=True,completed_scans=plan['core_scans'],elapsed_seconds=round(time.monotonic()-started,2),evaluator=evaluator.statistics())
        failed=(not report['protected_bytes_unchanged'] or report['engine_defects'] or report['boundary_reference']['verdict']!='PASS'
                or any(k.startswith('UNEXPECTED_') for k in mismatch_counts) or dviolations)
        report['verdict']='FAIL' if failed else 'COMPLETED'
        write_report(path,report)
        print(json.dumps({'symbol':symbol,'shard':shard,'verdict':report['verdict'],'scans':report['completed_scans'],'seconds':report['elapsed_seconds'],'engine_defects':len(report['engine_defects'])}),flush=True)
        return 1 if failed else 0
    finally:
        released=RG.release(lock,**owner)
        print(json.dumps(released),flush=True)
        report['resource_lock_released']=released.get('RELEASED',False);write_report(path,report)


def accumulate(counts,row):
    for key in ('scans','opportunity_scans','priced_opportunity_scans','rr_eligible_scans'):
        counts[key]+=row[key]
    for key in ('states','terminal_reasons','evaluated_checks','not_applicable_checks'):
        counts[key].update(row[key])
    for gate in GATES:
        counts['gates'][gate].update(row['gates'][gate])


def merge_shards(root,out,symbols=SYMBOLS):
    root=Path(root);report={'mission':MISSION,'strategy':'ST_LARGE_SMC_V1@1.1.3','scope_days':60,
                          'verification_status':'NOT_VERIFIED','symbols':{},'proposal':'NO_QUALIFYING_SCOPE','rule_diff':audit.rule_diff()}
    for symbol in symbols:
        active=new_counts();raw=new_counts();branches={};seen={};cross=[];shards=[];identities=set();dlsmc=new_dlsmc()
        for shard in range(SHARDS):
            path=root/symbol/f'shard_{shard:02d}'/'audit.json'
            if not path.exists():
                shards.append({'shard':shard,'verdict':'NOT_RUN'});continue
            row=json.loads(path.read_text());shards.append({'shard':shard,'verdict':row['verdict'],'completed_scans':row.get('completed_scans',0),'completed':row.get('completed',False)})
            if not row.get('completed') or row['verdict']!='COMPLETED':
                continue
            identity=row['identity']
            identities.add(json.dumps({k:identity[k] for k in ('contract_sha256','engine_sha256','runner_sha256','frozen_file_sha256')},sort_keys=True))
            accumulate(raw,row['raw_all_scans']);accumulate(active,row['active_history_scans'])
            for key,counts in row['dlsmc_recheck']['counts'].items():dlsmc[key].update(counts)
            for key,counts in row['branch_matrix'].items():accumulate(branches.setdefault(key,new_counts()),counts)
            for opp,value in row['selections'].items():
                if opp in seen and seen[opp]['target_sha256']!=value['target_sha256']:
                    cross.append({'classification':'ENGINE_DEFECT','opp_id':opp,'before':seen[opp],'after':value,'file_line':'src/large_smc_v113/watch.py:264'})
                seen[opp]=value
        complete=all(x.get('completed') and x['verdict']=='COMPLETED' for x in shards)
        matrix={key:summary(value,history_insufficient=inactive(key)) for key,value in branches.items()}
        failed_shard=any(x['verdict'].startswith('FAIL') for x in shards)
        identity_mismatch=len(identities)>1
        verdict=('FAIL_ENGINE_DEFECT' if cross else 'FAIL_SHARD' if failed_shard else 'FAIL_IDENTITY_MISMATCH' if identity_mismatch
                 else 'COMPLETED' if complete else 'PARTIAL_NOT_RUN_RESOURCE' if any(x['verdict']=='NOT_RUN_RESOURCE' for x in shards) else 'NOT_RUN')
        report['symbols'][symbol]={'verdict':verdict,'shards':shards,'completed':complete,'raw_all_scans_completed_shards_only':summary(raw),'active_history_completed_shards_only':summary(active),'branch_matrix_completed_shards_only':matrix,'cross_shard_engine_defects':cross,'unique_opportunities_completed_shards_only':len(seen),
                                   'dlsmc_recheck':{'counts':{k:dict(v) for k,v in dlsmc.items()},'verdicts':dlsmc_verdicts(dlsmc)},
                                   'active_gate_verdicts':summary(active)['gate_verdicts']}
        # R3 explicitly asks for L1-L6 PASS; advisory WARN is never manufactured into PASS.
        eligible=complete and not cross and not failed_shard and not identity_mismatch and any(v['qualifies_for_proposal'] and all(v['gate_verdicts'][g]=='PASS' for g in GATES) for v in matrix.values())
        report['symbols'][symbol]['qualifies_for_r3_proposal']=eligible
    if any(v['qualifies_for_r3_proposal'] for v in report['symbols'].values()):report['proposal']='ELIGIBLE_PROPOSAL_REQUIRED'
    report['verdict']='FAIL' if any(v['verdict'].startswith('FAIL') for v in report['symbols'].values()) else 'COMPLETED' if all(v['completed'] for v in report['symbols'].values()) else 'PARTIAL_NOT_RUN_RESOURCE'
    report['proposal_gate_note']='A scope qualifies only with L1-L6 all PASS (OD1011-L5 cost evidence) and target stability PASS.'
    write_report(Path(out),report);print(json.dumps({s:v['verdict'] for s,v in report['symbols'].items()}))
    return report


def resume(root,out,only=None):
    """NOT_RUN_RESOURCE fix: a managed-environment restart killed one long process (#213). Each symbol/shard is a
    short independent unit (one R1 lock, one worker) with its own atomic report; re-invoking skips COMPLETED shards,
    so a restart loses at most one shard. A FAIL shard is kept as evidence and not re-run."""
    root=Path(root);rc=0
    for symbol in [only] if only else SYMBOLS:
        for shard in range(SHARDS):
            path=root/symbol/f'shard_{shard:02d}'/'audit.json'
            if path.exists() and json.loads(path.read_text()).get('verdict')=='COMPLETED':
                continue
            rc=max(rc,run_shard(path,symbol,shard))
    merge_shards(root,out,[only] if only else SYMBOLS)
    return rc


def cli(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbol',choices=SYMBOLS);parser.add_argument('--shard',type=int)
    parser.add_argument('--out',required=True);parser.add_argument('--merge-root')
    parser.add_argument('--resume-root',help='run every shard under ROOT/<SYM>/shard_NN/ not yet COMPLETED, then merge to --out')
    args=parser.parse_args(argv)
    if args.resume_root:
        return resume(args.resume_root,args.out,args.symbol)
    if args.merge_root:
        merge_shards(args.merge_root,args.out);return 0
    if args.symbol is None or args.shard is None:parser.error('--symbol and --shard required')
    return run_shard(args.out,args.symbol,args.shard)


if __name__ == "__main__":
    raise SystemExit(cli())
