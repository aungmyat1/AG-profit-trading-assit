"""Storage-only lifecycle records; no decision, transition or execution authority."""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

from ticket_store.store import SOURCES, TicketStoreError, _seal, _sha256

ORDER_EVENTS = ('INITIALIZED', 'SUBMITTED', 'ACCEPTED', 'REJECTED', 'MODIFIED', 'FILLED',
                'PARTIALLY_FILLED', 'CANCELED', 'EXPIRED')
COMMON = ('schema', 'record_id', 'ticket_id', 'record_ref', 'recorded_at_utc', 'source')
FIELDS = {
    'deliveries': COMMON + ('channel', 'status', 'attempt_ref', 'provenance', 'record_sha256'),
    'owner_decisions': COMMON + ('evaluation_source', 'decision', 'actor', 'reason', 'provenance', 'record_sha256'),
    'order_events': COMMON + ('event', 'actor', 'account', 'broker_order_id', 'price', 'sl', 'tp', 'volume',
                              'order_type', 'side', 'average', 'filled', 'remaining', 'cost',
                              'provenance', 'record_sha256'),
    'position_closes': COMMON + ('close_price', 'close_reason', 'realized_R', 'realized_pnl', 'commission',
                                'swap', 'max_adverse_R', 'provenance', 'record_sha256'),
}
SCHEMAS = dict(zip(FIELDS, ('TICKET_STORE_V2_DELIVERY', 'TICKET_STORE_V2_OWNER_DECISION',
                          'TICKET_STORE_V2_ORDER_EVENT', 'TICKET_STORE_V2_POSITION_CLOSE')))
NUMERIC = {'price', 'sl', 'tp', 'volume', 'average', 'filled', 'remaining', 'cost', 'close_price',
           'realized_R', 'realized_pnl', 'commission', 'swap', 'max_adverse_R'}


def cohort(record: dict) -> str:
    return record['evaluation_source'] if record['schema'] == SCHEMAS['owner_decisions'] else record['source']


def build_record(kind: str, **values: Any) -> dict:
    fields = FIELDS[kind]
    unknown = set(values) - set(fields)
    if unknown:
        raise TicketStoreError(f'unknown {kind} fields: {sorted(unknown)}')
    record = {k: values.get(k) for k in fields}
    record['schema'] = SCHEMAS[kind]
    required = ['ticket_id', 'record_ref', 'recorded_at_utc']
    required += {'deliveries': ['channel', 'status', 'attempt_ref'],
                 'owner_decisions': ['decision', 'actor'], 'order_events': ['event', 'actor', 'account'],
                 'position_closes': ['close_reason']}[kind]
    if any(not isinstance(record[k], str) or not record[k] for k in required):
        raise TicketStoreError(f'{kind} requires nonempty strings: {required}')
    try:
        at = dt.datetime.fromisoformat(record['recorded_at_utc'].replace('Z', '+00:00'))
        if at.utcoffset() != dt.timedelta(0):
            raise ValueError('timestamp must be aware UTC')
    except ValueError as exc:
        raise TicketStoreError('recorded_at_utc must be aware UTC ISO timestamp') from exc
    if cohort(record) not in SOURCES:
        raise TicketStoreError(f'invalid evaluation source: {cohort(record)!r}')
    if kind == 'owner_decisions' and record['source'] not in ('TELEGRAM', 'LOCAL'):
        raise TicketStoreError('owner decision source must be TELEGRAM or LOCAL')
    if kind == 'order_events':
        if record['account'] != 'DEMO':
            raise TicketStoreError('ORDER_EVENT account must be DEMO; LIVE is rejected')
        if record['actor'] not in ('SYSTEM', 'OWNER') or record['event'] not in ORDER_EVENTS:
            raise TicketStoreError('invalid order event or actor')
    for key in NUMERIC & set(fields):
        value = record[key]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value)):
            raise TicketStoreError(f'{key} must be a finite number or null')
    record['record_id'] = _sha256([record['schema'], record['ticket_id'], cohort(record), record['record_ref']])
    return _seal(record, fields)


def build_delivery(**fields):
    return build_record('deliveries', **fields)


def build_owner_decision(**fields):
    return build_record('owner_decisions', **fields)


def build_order_event(**fields):
    return build_record('order_events', **fields)


def build_position_close(**fields):
    return build_record('position_closes', **fields)
