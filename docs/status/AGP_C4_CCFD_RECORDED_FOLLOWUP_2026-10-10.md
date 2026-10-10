---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: 2026-11-07
---
# PR126 recorded CCFD follow-up — 2026-10-10

Base PR131: `451bcfcd183b7cb56a877a1da71cae031db14585`. Concurrent PR126 changes at `c0f985c` were preserved by merge; three add/add conflicts were resolved without overwriting remote history.

`expected_result=null` runs all gates in CONFORMANCE_ONLY mode without expected-result or expected-direction comparisons. RECORDED manifests without per-timeframe provenance SHA256s are rejected. REFERENCE_INCOMPLETE is an explicit data-coverage gap, not L2 failure; L3 remains NOT_EVIDENCED, preventing a complete coverage claim. Shared captures are hashed in full, parsed with PR131's UTC parser, cached and sliced to fully closed prefixes for replay. No fixture bytes are changed.

| Symbol | L1 | L2 | L3 | L4 | L5 | L6 | Verdict |
|---|---|---|---|---|---|---|---|
| BTCUSD | PASS | PASS | NOT_EVIDENCED | NOT_EVIDENCED | NOT_EVIDENCED | NOT_EVIDENCED | NOT_VERIFIED |
| ETHUSD | PASS | PASS | NOT_EVIDENCED | NOT_EVIDENCED | NOT_EVIDENCED | NOT_EVIDENCED | NOT_VERIFIED |

| Symbol | WAITING_SWEEP | WAITING_MSS | REFERENCE_INCOMPLETE | ENTRY_VALID | Other states | Signals/day |
|---|---|---|---|---|---|---|
| BTCUSD | 124 | 12 | 16 | 0 | 0 | 0 |
| ETHUSD | 136 | 0 | 16 | 0 | 0 | 0 |

Each symbol has 152 scan points over 14 UTC days, 2026-09-26 through 2026-10-09. All 304 cases are conformance-only. Zero ENTRY_VALID scans and zero distinct retest signals occur on every scanned day. L4–L6 have no entry evidence; unknown commission remains an explicit capture gap. All eight LONG/SHORT × WEEKDAY/WEEKEND × BTCUSD/ETHUSD qualifying-entry combinations remain uncovered. Provenance raw-file hashes validate. The JSON records per-file hashes, manifest hash, daily counts and exact replay identity.

The 10% spread boundary moved WARN→OK per OD1009. Independent cost thresholds remain WARN at 0.10R and BLOCK at 0.25R; required policy keys fail closed. Existing crypto_cfd_cost_gate is reused.

Validation: 77 focused tests passed, covering all three requested behaviors and shared recorded prefix parsing. Runner exits 1 for the truthful NOT_VERIFIED result; this is not a replay exception.

```bash
python -m pytest -q tests/test_ccfd_v100_logic_verification.py tests/test_crypto_cfd_proposal_policy.py tests/test_crypto_cfd_strategy_contract_v1.py
python scripts/ccfd_v100_logic_verification.py --fixtures tests/fixtures/ccfd_v100/recorded/manifest.json --out-dir work/ccfd-recorded
```

OSS-FIRST: recorded replay | existing CCFD evaluator/gates and PR131 UTC parser | REUSED | no new strategy or data-acquisition logic.

Frozen contracts, registry, READY, scheduler and generated status files are unchanged. NO_BROKER_MUTATION: ORDER_API_CALLS=0; BROKER_MUTATION_COUNT=0.
