"""C24 recorded detection comparison; reference evidence, never strategy authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from smartmoneyconcepts import smc

from fx_discovery import features as F
from large_smc_v112.contract import resolve_point
from large_smc_watch.detect import h1_pois, tolerant_breaks
from market_structure.smc_adapter import candles_to_dataframe
from strategy_engine.session import Candle

ROOT = Path(__file__).resolve().parents[2]
SPEC = 'strategies/ST_LARGE_SMC_V1_1_1_2.yaml'
DEFINITIONS = {
    'swings': ('rules.swings', 'Strict k=2 fractal, equal extrema excluded, high precedence; oracle rolling extrema and alternating swing pruning.'),
    'BOS_CHOCH': ('rules.break', 'Most recent confirmed unconsumed swing, close beyond five host points, neutral first break CHoCH; oracle four-swing pattern labeling.'),
    'FVG': ('rules.poi; implementation_choices', 'Three-candle gap without middle body direction filter; oracle requires middle body direction.'),
    'OB': ('rules.poi.models; implementation_choices', 'AG_ORDER_BLOCK_V1 displacement/FVG/break and opposing origin; SMC_OB is expressly not the contract model.'),
    'liquidity_sweeps': ('implementation_choices; src/fx_discovery/features.py:105', 'Wick through most recent strictly confirmed swing and close reclaim; oracle equal-level cluster subsequently swept, no close-reclaim requirement.'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    with path.open() as stream:
        return [Candle(datetime.fromisoformat(r['timestamp_utc']),
                       *(float(r[k]) for k in ('open', 'high', 'low', 'close')), None)
                for r in csv.DictReader(stream)]


def local_events(symbol, bars, point, include_ob):
    swings = F.swings(bars, 2)
    breaks = tolerant_breaks(bars, swings, 5 * point)
    events = {
        'swings': {(x.index, x.kind, round(x.price, 10)): x for x in swings},
        'BOS_CHOCH': {(x.index, x.event.upper(), x.direction, round(x.level, 10)): x for x in breaks},
        'FVG': {(x.index, x.direction, round(x.bottom, 10), round(x.top, 10)): x for x in F.fvgs(bars)},
        'liquidity_sweeps': {(x.index, x.direction, round(x.level, 10)): x for x in F.sweeps(bars, swings)},
    }
    if include_ob:
        indices = {b.time: i for i, b in enumerate(bars)}
        events['OB'] = {(indices[x.origin_time], 'bullish' if x.direction == 'LONG' else 'bearish',
                         round(x.low, 10), round(x.high, 10)): x
                        for x in h1_pois(symbol, bars, breaks) if x.kind.startswith('OB')}
    return events


def oracle_events(bars, include_ob):
    df = candles_to_dataframe(bars)
    swings = smc.swing_highs_lows(df, swing_length=2)
    frames = {
        'swings': swings,
        'BOS_CHOCH': smc.bos_choch(df, swings, close_break=True),
        'FVG': smc.fvg(df, join_consecutive=False),
        'liquidity_sweeps': smc.liquidity(df, swings),
    }
    if include_ob:
        frames['OB'] = smc.ob(df, swings)
    events = {name: {} for name in frames}
    for name, frame in frames.items():
        for pos, row in frame.iterrows():
            row = {k: None if v != v else float(v) for k, v in row.items()}
            index = int(pos)
            if name == 'swings':
                if row['HighLow'] is None or index < 2 or index >= len(bars)-2:
                    continue  # Raw library bookends have no k=2 confirmation.
                key = (index, 'high' if row['HighLow'] > 0 else 'low', round(row['Level'], 10))
            elif name == 'BOS_CHOCH':
                label = 'BOS' if row['BOS'] not in (None, 0) else 'CHOCH'
                if row[label] in (None, 0) or row['BrokenIndex'] is None:
                    continue
                key = (int(row['BrokenIndex']), label, 'bullish' if row[label] > 0 else 'bearish', round(row['Level'], 10))
            elif name == 'liquidity_sweeps':
                if row['Liquidity'] is None or row['Swept'] in (None, 0):
                    continue  # Compare sweeps, not unswept clusters.
                key = (int(row['Swept']), 'bearish' if row['Liquidity'] > 0 else 'bullish', round(row['Level'], 10))
            else:
                if row[name] is None:
                    continue
                key = (index, 'bullish' if row[name] > 0 else 'bearish', round(row['Bottom'], 10), round(row['Top'], 10))
            events[name][key] = row
    return events


def local_contract_check(name, key, event, bars, point):
    """Independent necessary contract checks; not an oracle-based authority override."""
    i = key[0]
    if not 0 <= i < len(bars):
        return False
    b = bars[i]
    if name == 'swings':
        if i < 2 or i+2 >= len(bars) or event.known_at != i+2:
            return False
        high = all(b.high > bars[j].high for j in (i-2, i-1, i+1, i+2))
        low = all(b.low < bars[j].low for j in (i-2, i-1, i+1, i+2))
        return (key[1] == 'high' and high and event.price == b.high) or (key[1] == 'low' and low and not high and event.price == b.low)
    if name == 'BOS_CHOCH':
        return b.close > event.level+5*point if event.direction == 'bullish' else b.close < event.level-5*point
    if name == 'FVG':
        if i < 1 or i+1 >= len(bars) or event.known_at != i+1:
            return False
        a, c = bars[i-1], bars[i+1]
        return ((event.direction == 'bullish' and event.bottom == a.high and event.top == c.low and c.low > a.high)
                or (event.direction == 'bearish' and event.bottom == c.high and event.top == a.low and a.low > c.high))
    if name == 'liquidity_sweeps':
        return ((event.direction == 'bullish' and b.low < event.level < b.close)
                or (event.direction == 'bearish' and b.close < event.level < b.high))
    return b.low <= event.low < event.high <= b.high and event.known_time > event.origin_time


def oracle_geometry_check(name, key, bars):
    i = key[0]
    if not 0 <= i < len(bars):
        return False
    if name in ('OB', 'FVG'):
        return 0 < key[2] < key[3]
    if name == 'swings':
        return key[2] == round(getattr(bars[i], key[1]), 10)
    if name == 'BOS_CHOCH':
        return bars[i].close > key[3] if key[2] == 'bullish' else bars[i].close < key[3]
    return bars[i].high > key[2] if key[1] == 'bearish' else bars[i].low < key[2]


def run(out, symbols=('BTCUSD', 'ETHUSD')):
    if version('smartmoneyconcepts') != '0.0.27':
        raise ValueError('OSS_BLOCKED: smartmoneyconcepts==0.0.27 required')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {'mission': 'AGP-C24-LSMC-V112-VERIFY-R2', 'strategy_version': '1.1.2',
              'oracle': 'smartmoneyconcepts==0.0.27', 'oracle_authority': False,
              'contract_sha256': sha(ROOT/SPEC), 'scope_days': 60, 'symbols': {},
              'agreement_metric': 'Jaccard: exact normalized event intersection / union; empty union is NOT_APPLICABLE, never 100%',
              'normalization': 'Origin index for swings/FVG/OB; BrokenIndex for BOS/CHOCH; actual Swept index for liquidity. Bookend swings without k=2 confirmation excluded. All other raw library events retained.',
              'volume': 'Recorded core CSVs have no volume. Existing dataframe adapter supplies zero; OB geometry only, not volume strength.',
              'timing': 'Full-array detection comparison is retrospective reference evidence; it does not certify oracle causality. P1 L1 tests engine decisions at every recorded M5 close.',
              'engine_defects': [], 'divergence_classes': {}, 'status': 'NOT_RUN'}
    counts = Counter()
    with out.with_name('oracle_divergences.jsonl').open('w') as stream:
        for symbol in symbols:
            point, source = resolve_point(symbol)
            if point is None:
                raise ValueError(f'{symbol}: host point not evidenced')
            result = {'point': point, 'point_source': source, 'timeframes': {}, 'aggregate': {}}
            aggregate = {}
            for tf in ('D1', 'H1', 'M5'):
                path = ROOT/'tests/fixtures/ccfd_v100/recorded_60d'/f'{symbol}_{tf.lower()}.csv'
                bars = load(path)
                local = local_events(symbol, bars, point, tf == 'H1')
                oracle = oracle_events(bars, tf == 'H1')
                rows = {'bars': len(bars), 'fixture': str(path.relative_to(ROOT)), 'sha256': sha(path), 'categories': {}}
                for name, left in local.items():
                    right = oracle[name]
                    union, matched = set(left) | set(right), set(left) & set(right)
                    rows['categories'][name] = {'engine': len(left), 'oracle': len(right), 'matched': len(matched),
                                                'union': len(union), 'agreement_percent': round(100*len(matched)/len(union), 6) if union else None}
                    totals = aggregate.setdefault(name, Counter())
                    totals.update(engine=len(left), oracle=len(right), matched=len(matched), union=len(union))
                    # Validate every engine event, including matches: a matching oracle is no exemption.
                    invalid = {key for key, event in left.items() if not local_contract_check(name, key, event, bars, point)}
                    for key in sorted((set(left)^set(right)) | invalid):
                        side = 'ENGINE' if key in left else 'ORACLE'
                        classification = ('ENGINE_DEFECT' if key in invalid else
                                          'ORACLE_DEFECT' if side == 'ORACLE' and not oracle_geometry_check(name, key, bars) else 'SPEC_DIFFERENCE')
                        counts[classification] += 1
                        rule, reason = DEFINITIONS[name]
                        row = {'symbol': symbol, 'timeframe': tf, 'category': name, 'side': side,
                               'event': key, 'bar_utc': bars[key[0]].time.isoformat() if 0 <= key[0] < len(bars) else None,
                               'classification': classification, 'rule': f'{SPEC}: {rule}', 'reason': reason,
                               'validation': 'Local necessary contract checks PASS' if key not in invalid else 'Local contract check FAIL'}
                        if classification == 'ENGINE_DEFECT':
                            row['file_line'] = 'src/large_smc_watch/detect.py:105' if name == 'OB' else 'src/fx_discovery/features.py:66' if name == 'swings' else 'src/large_smc_watch/detect.py:51' if name == 'BOS_CHOCH' else 'src/fx_discovery/features.py:127' if name == 'FVG' else 'src/fx_discovery/features.py:105'
                            row['minimal_repro'] = {'fixture': str(path.relative_to(ROOT)), 'sha256': sha(path), 'event_index': key[0], 'reproducer': 'local_events(symbol, load(fixture), point, timeframe == "H1"); local_contract_check(category, event, object, bars, point) == False'}
                            report['engine_defects'].append(row)
                        stream.write(json.dumps(row, sort_keys=True)+'\n')
                if tf != 'H1':
                    rows['categories']['OB'] = {'status': 'NOT_APPLICABLE', 'reason': 'Contract OB POIs are H1 only'}
                result['timeframes'][tf] = rows
                print(f'ORACLE {symbol} {tf}: {len(bars)} bars completed', flush=True)
            result['aggregate'] = {name: {**dict(v), 'agreement_percent': round(100*v['matched']/v['union'], 6) if v['union'] else None}
                                   for name, v in aggregate.items()}
            report['symbols'][symbol] = result
    report['divergence_classes'] = dict(counts)
    report['status'] = 'FAIL_ENGINE_DEFECT' if report['engine_defects'] else 'COMPLETED_REFERENCE_DIVERGENT'
    report['divergence_log_sha256'] = sha(out.with_name('oracle_divergences.jsonl'))
    out.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return report


def cli(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    result = run(args.out)
    return 1 if result['engine_defects'] else 0
