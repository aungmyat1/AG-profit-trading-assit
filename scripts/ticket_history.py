"""Read-only ticket history/statistics query and CSV/Parquet export.

python scripts/ticket_history.py query --store journal/ticket_store [--view history|stats]
python scripts/ticket_history.py export --store journal/ticket_store --output work/history.csv
Indexes must first be rebuilt with scripts/ticket_store_reindex.py. Never contacts a broker.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ticket_store.index import index_path  # noqa: E402


def query(store, *, view='history', ticket_id=None, strategy=None, symbol=None, source=None, backend='auto'):
    views = {'history': 'v_ticket_history', 'stats': 'v_strategy_stats'}
    if view not in views or backend not in ('auto', 'sqlite', 'duckdb'):
        raise ValueError('invalid view/backend')
    path = Path(index_path(store)).resolve()
    if not path.is_file():
        raise ValueError('index missing; run scripts/ticket_store_reindex.py first')
    conditions, params = [], []
    for key, value in (('ticket_id', ticket_id), ('strategy', strategy), ('symbol', symbol), ('source', source)):
        if value is not None:
            if key == 'ticket_id' and view == 'stats':
                raise ValueError('ticket_id applies only to history')
            conditions.append(f'{key}=?')
            params.append(value)
    sql = 'SELECT * FROM ' + views[view] + (' WHERE ' + ' AND '.join(conditions) if conditions else '')
    sql += ' ORDER BY ' + ('ticket_id' if view == 'history' else 'strategy,symbol,session,source')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as con:
        cur = con.execute(sql, params)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    # DuckDB consumes the already-derived portable view; no sqlite extension install/download.
    if backend != 'sqlite':
        try:
            duckdb = importlib.import_module('duckdb')
        except ImportError:
            if backend == 'duckdb':
                raise ValueError('duckdb is optional; install .[ticket-history] or use --backend sqlite')
        else:
            with duckdb.connect(':memory:') as con:
                definitions = ','.join(f'"{c}" {"DOUBLE" if c in ("win_rate","avg_R","expectancy","realized_R","max_adverse_R") else "BIGINT" if c in ("tickets","decided","filled","resolved") else "VARCHAR"}' for c in columns)
                con.execute(f'CREATE TABLE history_result ({definitions})')
                if rows:
                    con.executemany('INSERT INTO history_result VALUES (' + ','.join('?' for _ in columns) + ')', rows)
                rows = con.execute('SELECT * FROM history_result').fetchall()
    return columns, [dict(zip(columns, row)) for row in rows]


def export(columns, rows, output):
    path = Path(output)
    if path.suffix.lower() == '.csv':
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    elif path.suffix.lower() == '.parquet':
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ValueError('Parquet export requires optional .[research] pyarrow; CSV needs only sqlite') from exc
        numeric = {'win_rate', 'avg_R', 'expectancy', 'realized_R', 'max_adverse_R'}
        counts = {'tickets', 'decided', 'filled', 'resolved'}
        schema = pa.schema([(c, pa.float64() if c in numeric else pa.int64() if c in counts else pa.string())
                            for c in columns])
        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(table, path)
    else:
        raise ValueError('output suffix must be .csv or .parquet')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('query', 'export'):
        p = sub.add_parser(command)
        p.add_argument('--store', required=True)
        p.add_argument('--view', choices=('history', 'stats'), default='history')
        p.add_argument('--backend', choices=('auto', 'sqlite', 'duckdb'), default='auto')
        for field in ('ticket-id', 'strategy', 'symbol', 'source'):
            p.add_argument('--' + field)
        if command == 'export':
            p.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        columns, rows = query(args.store, view=args.view, ticket_id=args.ticket_id, strategy=args.strategy,
                              symbol=args.symbol, source=args.source, backend=args.backend)
        if args.command == 'export':
            export(columns, rows, args.output)
        else:
            print(json.dumps(rows, indent=2, allow_nan=False))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
