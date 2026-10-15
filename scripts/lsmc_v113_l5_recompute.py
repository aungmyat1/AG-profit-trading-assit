"""Offline L5 recompute for the committed LSMC 1.1.3 replay artifacts (AGP-LSMC113-EURUSD-ENTRY).

Reads every priced OPPORTUNITY row of <root>/<SYM>/shard_NN/scans.csv plus the recorded VT M5 spreads of the
same dataset, and applies the unchanged gate L5 (v1_tickets.lsmc_v113_logic_gate.l5_od1011). FX/gold commission
binds only through the full login in gitignored config/local/owner_ticket.yaml (OD1011-COMMISSION); without it
every row is INSUFFICIENT, never PASS. Read-only; no broker contact.

    PYTHONPATH=src:scripts python scripts/lsmc_v113_l5_recompute.py \
        --root artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/lsmc113_eurusd_entry --symbol EURUSD --out l5.json
"""
import argparse
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import lsmc_v113_60d_replay as R

from v1_tickets.lsmc_v113_logic_gate import l5_od1011

IDENTITY_KEYS = ('contract_sha256', 'engine_sha256', 'runner_sha256', 'frozen_file_sha256', 'code_sha')


def artifact_set(root, symbol):
    """All six shard audits COMPLETED, one identity, and scans.csv rows == completed_scans; else the reason."""
    identities = set()
    for shard in range(R.SHARDS):
        folder = Path(root, symbol, f'shard_{shard:02d}')
        audit, scans = folder/'audit.json', folder/'scans.csv'
        if not audit.is_file() or not scans.is_file():
            return f'SHARD_{shard:02d}_MISSING'
        report = json.loads(audit.read_text())
        if report.get('verdict') != 'COMPLETED' or not report.get('completed'):
            return f'SHARD_{shard:02d}_NOT_COMPLETED'
        with scans.open() as stream:
            if sum(1 for _ in csv.DictReader(stream)) != report.get('completed_scans'):
                return f'SHARD_{shard:02d}_SCAN_COUNT_MISMATCH'
        identities.add(json.dumps({k: (report.get('identity') or {}).get(k) for k in IDENTITY_KEYS}, sort_keys=True))
    return None if len(identities) == 1 else 'IDENTITY_MISMATCH'


def recompute(root, symbol):
    problem = artifact_set(root, symbol)
    if problem:      # partial or mixed artifacts can never satisfy the host-L5 gate
        return {'symbol': symbol, 'L5': 'INCOMPLETE_ARTIFACTS', 'reason': problem}
    data, _bars = R.inventory(symbol)            # spread metadata + provenance hashes authenticated first
    if data['verdict'] != 'PASS_WITH_DECLARED_GAPS':
        return {'symbol': symbol, 'L5': 'DATA_NOT_AUTHENTICATED', 'reason': data.get('issues') or data['verdict']}
    cost = R.cost_source(symbol)
    counts, reasons, actions, rows = Counter(), Counter(), Counter(), 0
    for scans in (Path(root, symbol, f'shard_{s:02d}', 'scans.csv') for s in range(R.SHARDS)):
        with scans.open() as stream:
            for row in csv.DictReader(stream):
                if row['signal_state'] != 'OPPORTUNITY' or not row['entry'] or not row['stop']:
                    continue
                rows += 1
                now = dt.datetime.fromisoformat(row['closed_at_utc'])
                last_open = now - dt.timedelta(minutes=5)
                case = {'symbol': symbol, 'now': now, 'cost_evidence': {
                    'spread': cost['spread'].get(last_open), 'spread_bar_close_utc': now.isoformat(),
                    'commission_binding': cost['binding']}}
                sig = SimpleNamespace(state='OPPORTUNITY', opportunity={'entry_reference': float(row['entry']),
                                                                        'stop_c10': float(row['stop'])})
                gate = l5_od1011(case, sig)
                counts[gate['status']] += 1
                if gate.get('reason'):
                    reasons[gate['reason']] += 1
                if gate.get('actionability'):
                    actions[gate['actionability']] += 1
    verdict = ('NOT_RUN' if not rows else 'FAIL' if counts['FAIL'] else
               'INSUFFICIENT' if counts['INSUFFICIENT'] else 'PASS')
    return {'symbol': symbol, 'priced_opportunity_rows': rows, 'l5_status': dict(counts),
            'insufficient_reasons': dict(reasons), 'actionability': dict(actions), 'L5': verdict,
            'commission_binding': (cost['binding'] or {}).get('binding', 'NONE (no full-login OD1011 binding)'),
            'source': R.COST_SOURCE}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--symbol', required=True, choices=R.SYMBOLS)
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    report = recompute(args.root, args.symbol)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + '\n')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
