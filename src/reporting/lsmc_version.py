"""Version selection for the REPORT_ONLY LSMC lane; frozen watch remains separate."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

def selected_version(path=None):
    path = Path(path) if path is not None else ROOT / 'config/lsmc_report_lane.yaml'
    try:
        raw = yaml.safe_load(path.read_text())
        version = raw.get('strategy_version') if isinstance(raw, dict) else None
    except (OSError, UnicodeError, yaml.YAMLError):
        return None
    return version if version in ('1.1.0', '1.1.2') else None

def observe_selected(events, *, symbol, bars, journal, now, price, archive_root, bid=None, ask=None, account=None):
    from reporting.lsmc_lane import observe_events
    version = selected_version()
    if version is None:
        from reporting.common import archive_observation, observational_canonical
        from reporting.lsmc_lane import FAMILY
        canonical = observational_canonical(
            {'strategy_id': 'ST_LARGE_SMC_V1', 'strategy_version': 'UNKNOWN',
             'symbol': symbol, 'cycle': 'LSMC_WATCH', 'session_date': now.date().isoformat(),
             'decision': 'BLOCKED', 'reason_code': 'LSMC_REPORT_VERSION_NOT_EVIDENCED'},
            now=now, report_class='BLOCKED')
        canonical['verification_status'] = 'NOT_VERIFIED'
        canonical['scope_verification_status'] = 'NOT_VERIFIED'
        archive_observation(archive_root, FAMILY, canonical)
        return [canonical]
    if version == '1.1.0':
        return observe_events(events, now=now, price=price, archive_root=archive_root, bid=bid, ask=ask, account=account)
    from large_smc_v112 import WatchTracker, evaluate_snapshot
    from reporting.common import archive_observation, block
    from reporting.lsmc_lane import FAMILY, from_event
    from reporting.sizing_preview import attach_inputs
    account = account or {}
    snap = evaluate_snapshot(symbol, bars['D1'], bars['H1'], bars['M5'], now, bid=bid, ask=ask)
    tracker = WatchTracker(str(Path(journal)/'large_smc_v112_report/state.json'),
                           str(Path(journal)/'large_smc_v112_report/engine_archive'))
    out = []
    for event in tracker.poll(snap):
        canonical = from_event(dict(event.__dict__), now=now, price=price)
        opportunity = snap.opportunity or {}
        canonical['pip_source'] = opportunity.get('pip_source')
        canonical['c11_source'] = opportunity.get('c11_source')
        canonical['reward_risk'] = opportunity.get('reward_risk')
        rr_reason = opportunity.get('reward_risk_reason')
        canonical['candidate_rule_blocks'] = [rr_reason] if rr_reason else []
        if rr_reason and canonical.get('report_class') == 'CANDIDATE':
            block(canonical, rr_reason)
        canonical['verification_status'] = 'NOT_VERIFIED'
        canonical['scope_verification_status'] = 'NOT_VERIFIED'
        attach_inputs(canonical, bid=bid, ask=ask, commission_R=account.get('commission_R'),
                      balance=account.get('balance'), account_currency=account.get('currency'),
                      quote_time=now.isoformat())
        canonical['sizing_inputs']['pip_size'] = opportunity.get('pip_size')
        archive_observation(archive_root, FAMILY, canonical)
        out.append(canonical)
    return out
