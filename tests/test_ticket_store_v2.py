"""Storage-only V2 lifecycle integrity, V1 byte preservation, and cohort statistics."""
import copy
import csv
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from ticket_store import (
    TicketStore,
    TicketStoreConflict,
    TicketStoreCorrupt,
    TicketStoreError,
    build_delivery,
    build_evaluation,
    build_order_event,
    build_outcome,
    build_owner_decision,
    build_position_close,
    index,
)
from ticket_store.v2 import FIELDS, ORDER_EVENTS

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ticket_history_cli', ROOT / 'scripts/ticket_history.py')
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
NOW = '2026-10-10T12:00:00+00:00'
BUILDERS = {'deliveries': build_delivery, 'owner_decisions': build_owner_decision,
            'order_events': build_order_event, 'position_closes': build_position_close}
METHODS = {'deliveries': 'append_delivery', 'owner_decisions': 'append_owner_decision',
           'order_events': 'append_order_event', 'position_closes': 'append_position_close'}


def event(kind, **over):
    values = dict(ticket_id='T', record_ref='ref', recorded_at_utc=NOW, source='DEMO')
    values.update({'deliveries': dict(channel='TELEGRAM', status='SENT', attempt_ref='attempt'),
                   'owner_decisions': dict(source='LOCAL', evaluation_source='DEMO', decision='CONFIRM', actor='owner'),
                   'order_events': dict(event='INITIALIZED', actor='SYSTEM', account='DEMO'),
                   'position_closes': dict(close_reason='TP', realized_R=2)}[kind])
    values.update(over)
    return BUILDERS[kind](**values)


def evaluation(ticket_id='T', source='DEMO', **over):
    values = dict(ticket_id=ticket_id, source=source, strategy='S@2', symbol='BTCUSD', session='WEEKEND',
                  evaluated_at_utc=NOW, state='NO_TRADE')
    values.update(over)
    return build_evaluation(**values)


@pytest.mark.parametrize('kind', FIELDS)
def test_lifecycle_immutable_idempotent_cross_day_conflict_and_corrupt(kind, tmp_path):
    store = TicketStore(str(tmp_path))
    append = getattr(store, METHODS[kind])
    record = event(kind)
    assert tuple(record) == FIELDS[kind]
    assert append(record) and not append(copy.deepcopy(record))
    path = Path(store.files(kind)[0]); before = path.read_bytes()
    with pytest.raises(TicketStoreConflict):
        append(event(kind, recorded_at_utc='2026-10-11T12:00:00+00:00'))
    assert path.read_bytes() == before
    altered = {**record, 'ticket_id': 'tampered'}
    with pytest.raises(TicketStoreError):
        append(altered)
    path.write_bytes(before + b'{')
    corrupt = path.read_bytes()
    with pytest.raises(TicketStoreCorrupt):
        store.lifecycle_records(kind)
    with pytest.raises(TicketStoreCorrupt):
        append(event(kind, record_ref='new'))
    assert path.read_bytes() == corrupt


@pytest.mark.parametrize('kind', FIELDS)
def test_reindex_checks_all_new_tables(kind, tmp_path):
    store = TicketStore(str(tmp_path))
    getattr(store, METHODS[kind])(event(kind))
    index.rebuild(str(tmp_path))
    assert index.check(str(tmp_path))['tables'][kind]['index'] == 1
    getattr(store, METHODS[kind])(event(kind, record_ref='second'))
    assert not index.check(str(tmp_path))['ok']


@pytest.mark.parametrize('status', ORDER_EVENTS)
def test_order_vocabulary_and_demo_only(status):
    assert event('order_events', event=status)['event'] == status
    with pytest.raises(TicketStoreError, match='DEMO'):
        event('order_events', event=status, account='LIVE')


@pytest.mark.parametrize('over', [dict(event='TRIGGERED'), dict(actor='BOT'), dict(account=None),
                                  dict(volume=float('nan')), dict(price=float('inf'))])
def test_invalid_execution_metadata_rejected(over):
    with pytest.raises(TicketStoreError):
        event('order_events', **over)


def test_every_v1_corpus_file_reads_and_roundtrips_byte_identically(tmp_path):
    # Corpus emitted by the frozen 5b67199 V1 module, not by the V2 writer.
    fixture = ROOT / 'tests/fixtures/ticket_store_v1'
    shutil.copytree(fixture, tmp_path, dirs_exist_ok=True)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.jsonl')}
    store = TicketStore(str(tmp_path))
    for kind in ('evaluations', 'outcomes'):
        for path in store.files(kind):
            records = [r for p, n, r in store.iter_records(kind) if p == path]
            assert (''.join(json.dumps(r, sort_keys=True) + '\n' for r in records)).encode() == Path(path).read_bytes()
        assert len(list(store.iter_records(kind))) == 3
    for kind in FIELDS:
        getattr(store, METHODS[kind])(event(kind))
    index.rebuild(str(tmp_path))
    cli.query(str(tmp_path), backend='sqlite')
    assert all((tmp_path / rel).read_bytes() == raw for rel, raw in before.items())


def test_zero_execution_rows_and_empty_store(tmp_path):
    index.rebuild(str(tmp_path))
    assert cli.query(str(tmp_path), backend='sqlite')[1] == []
    store = TicketStore(str(tmp_path)); store.append_evaluation(evaluation())
    index.rebuild(str(tmp_path))
    row = cli.query(str(tmp_path), backend='sqlite')[1][0]
    assert row['orders'] == row['closes'] == '[]'
    stats = cli.query(str(tmp_path), view='stats', backend='sqlite')[1][0]
    assert (stats['tickets'], stats['decided'], stats['filled'], stats['resolved']) == (1, 0, 0, 0)
    assert stats['win_rate'] is stats['avg_R'] is stats['expectancy'] is stats['max_adverse_R'] is None


def test_history_one_row_no_fanout_and_statistics_cohort_isolation(tmp_path):
    store = TicketStore(str(tmp_path))
    for source in ('LIVE', 'DEMO', 'REPLAY', 'LEGACY'):
        for minute, (tid, ret) in enumerate((('a', 2), ('b', -1), ('c', 0))):
            store.append_evaluation(evaluation(tid, source, evaluated_at_utc=f'2026-10-10T12:{minute:02d}:00+00:00'))
            store.append_evaluation(evaluation(tid, source, evaluated_at_utc=f'2026-10-10T13:{minute:02d}:00+00:00'))
            store.append_owner_decision(event('owner_decisions', ticket_id=tid, evaluation_source=source))
            for i in range(2):
                store.append_delivery(event('deliveries', ticket_id=tid, source=source, record_ref=str(i)))
                store.append_order_event(event('order_events', ticket_id=tid, source=source,
                                              record_ref=str(i), event='FILLED'))
            store.append_position_close(event('position_closes', ticket_id=tid, source=source,
                                               realized_R=ret if source in ('LIVE','DEMO') else 999,
                                               max_adverse_R=1.5))
    index.rebuild(str(tmp_path))
    history = cli.query(str(tmp_path), backend='sqlite')[1]
    assert len(history) == 3
    assert all(len(json.loads(r['orders'])) == 2 and len(json.loads(r['evaluations'])) == 2 for r in history)
    stats = cli.query(str(tmp_path), view='stats', backend='sqlite')[1]
    assert {r['source'] for r in stats} == {'LIVE', 'DEMO'}
    for row in stats:
        assert (row['tickets'], row['decided'], row['filled'], row['resolved']) == (3,3,3,3)
        assert row['win_rate'] == row['avg_R'] == row['expectancy'] == pytest.approx(1/3)
        assert row['max_adverse_R'] == 1.5
    assert cli.query(str(tmp_path), view='stats', source='REPLAY', backend='sqlite')[1] == []


def test_v1_outcomes_are_source_filtered_and_counterfactual_excluded(tmp_path):
    store = TicketStore(str(tmp_path)); store.append_evaluation(evaluation(source='LIVE'))
    for source, kind, net in [('REPLAY','FIRST_TOUCH_M1_V1',999), ('LIVE','COUNTERFACTUAL_M1_V1',99),
                              ('LIVE','FIRST_TOUCH_M1_V1',-1)]:
        store.append_outcome(build_outcome(ticket_id='T', source=source, outcome_kind=kind,
                             recorded_at_utc=NOW, payload={'net_R':net,'mae_R':1}, result='SL'))
    index.rebuild(str(tmp_path))
    row = cli.query(str(tmp_path), view='stats', backend='sqlite')[1][0]
    assert row['avg_R'] == -1 and row['win_rate'] == 0 and row['max_adverse_R'] == 1


def test_query_export_csv_parquet_and_optional_duckdb_fallback(tmp_path, monkeypatch):
    store = TicketStore(str(tmp_path / 'store')); store.append_evaluation(evaluation())
    index.rebuild(store.root)
    original = cli.importlib.import_module
    def missing(name, *args, **kwargs):
        if name == 'duckdb':
            raise ImportError('optional')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(cli.importlib, 'import_module', missing)
    columns, rows = cli.query(store.root, ticket_id='T', backend='auto')
    assert len(rows) == 1
    with pytest.raises(ValueError, match='optional'):
        cli.query(store.root, backend='duckdb')
    assert cli.query(store.root, symbol="' OR 1=1 --", backend='sqlite')[1] == []
    assert cli.main(['export','--store',store.root,'--backend','sqlite','--output',str(tmp_path/'a.csv')]) == 0
    assert list(csv.DictReader((tmp_path/'a.csv').open()))[0]['ticket_id'] == 'T'
    pq = pytest.importorskip('pyarrow.parquet')
    cli.export(columns, rows, tmp_path/'a.parquet')
    assert pq.read_table(tmp_path/'a.parquet').to_pylist() == rows


def test_duckdb_matches_sqlite_and_empty_parquet(tmp_path):
    pytest.importorskip('duckdb')
    store = TicketStore(str(tmp_path/'store'))
    store.append_evaluation(evaluation())
    store.append_position_close(event('position_closes', realized_R=-0.25, max_adverse_R=0.5))
    index.rebuild(store.root)
    for view in ('history','stats'):
        assert cli.query(store.root, view=view, backend='duckdb') == cli.query(store.root, view=view, backend='sqlite')
    pq = pytest.importorskip('pyarrow.parquet')
    columns, rows = cli.query(store.root, view='stats', source='REPLAY', backend='sqlite')
    cli.export(columns, rows, tmp_path/'empty.parquet')
    table = pq.read_table(tmp_path/'empty.parquet')
    assert table.num_rows == 0 and str(table.schema.field('tickets').type) == 'int64'


@pytest.mark.parametrize('kind', FIELDS)
def test_valid_json_with_tampered_seal_is_corrupt_and_index_preserved(kind, tmp_path):
    store = TicketStore(str(tmp_path)); getattr(store, METHODS[kind])(event(kind))
    index.rebuild(str(tmp_path))
    before = Path(index.index_path(str(tmp_path))).read_bytes()
    path = Path(store.files(kind)[0]); record = json.loads(path.read_text()); record['record_ref'] = 'tampered'
    path.write_text(json.dumps(record)+'\n')
    with pytest.raises(TicketStoreCorrupt):
        index.rebuild(str(tmp_path))
    assert Path(index.index_path(str(tmp_path))).read_bytes() == before


def test_threaded_duplicate_event_has_one_append(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store = TicketStore(str(tmp_path)); record = event('deliveries')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.append_delivery(record), range(8)))
    assert results.count(True) == 1 and len(store.lifecycle_records('deliveries')) == 1
