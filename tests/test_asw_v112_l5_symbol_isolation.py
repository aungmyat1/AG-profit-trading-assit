"""Pin pre-R3 EURUSD bytes and ensure unrelated metadata cannot block it."""
import hashlib
import json

import scripts.asw_v112_logic_verification as h


def eur_bytes(report):
    projection = {k: report[k]['EURUSD'] for k in
                  ('per_symbol', 'day_types', 'gates_by_symbol', 'verdicts', 'dataset_identity')}
    projection['cases'] = [c for c in report['cases'] if c['case_id'].startswith('recorded:EURUSD:')]
    return json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def test_eurusd_default_bytes_and_cross_symbol_block(monkeypatch):
    default = h.build_report('2026-10-10T00:00:00Z')
    normalized = dict(default)
    normalized.pop("verification_code_sha")
    default_bytes = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert hashlib.sha256(default_bytes).hexdigest() == "59e50b91109705253b8cabe71cd783bd804288ca3f5f0a5fc2fb4073974b44f0"
    baseline = eur_bytes(default)
    # Captured from unmodified PR #129 c2ba6fe, including every EURUSD case and evidence field.
    assert hashlib.sha256(baseline).hexdigest() == '4a8ded8e6d97fd017a146200931704dc641df716193c7cab9cd027ff7312a50b'
    monkeypatch.setattr(h, 'SYMBOLS', h.R2_SYMBOLS)
    mixed = h.build_report('2026-10-10T00:00:00Z')
    assert eur_bytes(mixed) == baseline
    assert mixed['gates_by_symbol']['GBPUSD']['L5'] == 'WARN'
    for symbol in ('USDJPY', 'XAUUSD'):
        assert mixed['gates_by_symbol'][symbol]['L5'] == 'BLOCK'
        reasons = mixed['checks']['L5_risk_and_friction']['by_symbol'][symbol]['block_reasons']
        assert reasons == [f"SYMBOL_EVIDENCE_MISSING: pip size not evidenced for {[symbol]}"]
