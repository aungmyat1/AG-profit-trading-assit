"""Observational candidate declarations never confer verification or execution authority."""
import json
from pathlib import Path

import pytest

from v1_tickets import scope_status as ss

BASELINES = json.loads((Path(__file__).parent / 'fixtures/report_scope_baseline_6ca624a.json').read_text())


@pytest.mark.parametrize('row', BASELINES, ids=lambda row: '/'.join(row['args']))
def test_existing_scope_output_is_byte_identical(row):
    assert json.dumps(ss.resolve_ticket_scope(*row['args']), separators=(',', ':')) == row['serialized']


@pytest.mark.parametrize('symbol', ss.FAMILIES[ss.LARGE_SMC]['pairs'])
@pytest.mark.parametrize('session', ['WATCH', 'LSMC_WATCH-abc'])
def test_lsmc_candidate_is_explicitly_unverified(symbol, session):
    scope = ss.resolve_ticket_scope('ST_LARGE_SMC_V1', '1.1.2', symbol, session)
    assert scope == {
        'scope_family': ss.LARGE_SMC, 'scope_verification_status': ss.UNVERIFIED,
        'scope_route': ss.REPORT_ONLY, 'scope_reason': ss.CANDIDATE_NOT_VERIFIED,
        'verification_identity': None, 'scope_detail': '', 'execution_eligible': False,
    }


def test_unknown_version_still_rejected():
    scope = ss.resolve_ticket_scope('ST_LARGE_SMC_V1', '9.9.9', 'EURUSD', 'WATCH')
    assert scope['scope_reason'] == 'VERSION_NOT_IN_SCOPE:9.9.9'
    assert scope['verification_identity'] is None


@pytest.mark.parametrize('family', ss.FAMILIES)
def test_candidate_table_takes_precedence_over_verified_version_paths(monkeypatch, family):
    spec = ss.FAMILIES[family]
    # Include a normally verified version in the table: even it must short-circuit.
    versions = (spec['strategy_version'], *ss.REPORT_LANE_VERSIONS.get(family, ()))
    monkeypatch.setattr(ss, 'REPORT_ONLY_CANDIDATES', {family: versions})

    def forbidden(*args, **kwargs):
        pytest.fail('observational candidate reached registry or verification resolution')

    monkeypatch.setattr(ss, 'scope_status', forbidden)
    monkeypatch.setattr(ss, '_recorded_identity', forbidden)
    monkeypatch.setattr('v1_tickets.authority.load_registry', forbidden)
    for version in versions:
        scope = ss.resolve_ticket_scope(spec['strategy_id'], version, spec['pairs'][0], spec['sessions'][0])
        assert scope['scope_reason'] == ss.CANDIDATE_NOT_VERIFIED
        assert scope['scope_verification_status'] == ss.UNVERIFIED
        assert scope['scope_route'] == ss.REPORT_ONLY
        assert scope['verification_identity'] is None
        assert scope['execution_eligible'] is False


@pytest.mark.parametrize('decision', ['READY', 'SHADOW_INFO_ONLY', 'BLOCKED', 'NO_TRADE'])
def test_candidate_canonical_ticket_never_execution_authorized(decision):
    import datetime as dt

    from v1_tickets.canonical_ticket import build_canonical_ticket

    now = dt.datetime(2026, 10, 15, 7, tzinfo=dt.timezone.utc)
    ticket = build_canonical_ticket({
        'strategy_id': 'ST_LARGE_SMC_V1', 'strategy_version': '1.1.2',
        'symbol': 'EURUSD', 'cycle': 'LSMC_WATCH', 'session_date': now.date().isoformat(),
        'decision': decision, 'reason_code': 'TEST', 'evaluated_at': now.isoformat(),
        'execution_authorization': True, 'demo_authorized': True, 'live_authorized': True,
    }, now=now)
    assert ticket['scope_reason'] == ss.CANDIDATE_NOT_VERIFIED
    assert ticket['verification_identity'] is None
    assert ticket['scope_route'] == ss.REPORT_ONLY
    assert all(ticket[key] is False for key in ('execution_authorization', 'demo_authorized', 'live_authorized'))
