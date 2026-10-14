"""Recorded two-scan STATIC C11 counterexample; no engine modifications or memo."""
import bisect
import csv
import datetime as dt
import json
from pathlib import Path

import lsmc_v112_60d_replay as replay


def case_at(bars, symbol, row):
    now = bars['M5'][row].time + dt.timedelta(minutes=5)
    windows = {}
    for tf, rows in bars.items():
        end = bisect.bisect_right([b.time for b in rows], now)
        windows[tf] = rows[max(0, end-replay.A.HOST_COUNTS[tf]):end]
    return {'symbol': symbol, 'now': now, **windows}


def verify_pair(bars, before_row, after_row):
    observations = []
    for row in (before_row, after_row):
        case = case_at(bars, 'BTCUSD', row)
        snap = replay.G.evaluate_snapshot(case['symbol'], case['D1'], case['H1'], case['M5'], case['now'])
        signal = replay.G.signal_snapshot(snap)
        opportunity = signal.opportunity or {}
        observations.append({'m5_row': row, 'now': case['now'].isoformat(),
                             'window_first': {tf: case[tf][0].time.isoformat() for tf in ('D1', 'H1', 'M5')},
                             'window_bars': {tf: len(case[tf]) for tf in ('D1', 'H1', 'M5')},
                             'state': signal.state, 'operational_state': snap.state,
                             'opportunity': opportunity})
    a, b = (o['opportunity'] for o in observations)
    reproduced = bool(a and b and a['opp_id'] == b['opp_id'] and a['target_c11'] != b['target_c11'])
    return {'before': observations[0], 'after': observations[1], 'reproduced': reproduced}


def run(scan_path, out):
    info, bars = replay.inventory('BTCUSD')
    if bars is None or info['verdict'] == 'FAIL':
        raise ValueError('Committed provenance gate failed')
    previous, candidates = {}, []
    with Path(scan_path).open() as stream:
        for row in csv.DictReader(stream):
            if row['symbol'] != 'BTCUSD' or not row['opp_id'] or not row['target']:
                continue
            key = row['opp_id']
            if key in previous and previous[key]['target'] != row['target']:
                candidates.append((int(previous[key]['m5_row']), int(row['m5_row'])))
            previous[key] = row
    witnesses = [verify_pair(bars, a, b) for a, b in candidates]
    reproduced = [x for x in witnesses if x['reproduced']]
    report = {'mission': replay.MISSION, 'strategy_version': '1.1.2', 'symbol': 'BTCUSD',
              'classification': 'ENGINE_DEFECT' if reproduced else 'NOT_REPRODUCED',
              'defect_id': 'C24-C11-STATIC-ROLLING-WINDOW', 'count': len(reproduced),
              'rule': 'strategies/ST_LARGE_SMC_V1_1_1_2.yaml:138,177 (STATIC_AT_OPPORTUNITY_EVALUATION; retarget_after_selection=false)',
              'file_line': 'src/large_smc_v112/watch.py:264',
              'mechanism': 'Target is recomputed from the current rolling M5/H1 window clipped at trigger. An older selected target source can leave that window although opportunity ID and trigger remain unchanged.',
              'minimal_repro': 'Two adjacent recorded M5 scans, original 30/200/300 host windows; call unchanged G.evaluate_snapshot for each. Same opp_id, unequal target_c11.',
              'command': 'python scripts/lsmc_v112_c24_static_target_repro.py --scans <scans.csv> --out <repro.json>',
              'engine_sha256': replay.G.engine_sha256(), 'contract_sha256': replay.digest(replay.G.CONTRACT_PATH),
              'fixtures': info['sha256'], 'snapshot_or_feature_memo': False,
              'full_replay_status': 'NOT_RUN_RESOURCE; these witnesses establish a bounded defect, not full-window coverage',
              'witnesses': witnesses}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'classification': report['classification'], 'reproduced_witnesses': len(reproduced)}))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--scans', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    run(args.scans, args.out)
