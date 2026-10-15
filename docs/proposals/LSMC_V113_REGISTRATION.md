---
class: proposal
state: DRAFT_NOT_APPLIED
owner_reviewed: null
review_by: 2026-11-07
---
# ST_LARGE_SMC_V1@1.1.3 registration candidate — EURUSD entry logic (AGP-LSMC113-EURUSD-ENTRY)

**Draft only.** Nothing here is applied: `strategies/registry.yaml`, `strategies/STRATEGY_LEDGER.md`,
`config/lsmc_report_lane.yaml` and every frozen 1.1.0/1.1.2 byte are unchanged. Logic verification is not
economic edge and grants no proposal, READY, demo or live authority. **Eligibility: PENDING_HOST_L5 — not eligible.**

## Evidence

Full-window replay of recorded VT data for EURUSD, 60 days (#215 D1-R2,
`tests/fixtures/vt_recorded_60d_fx`), window 2026-08-14T21:00Z → 2026-10-13T21:00Z. Earlier recorded rows are
used only as warmup. The replay ran 6 day-chunked shards with one R1 worker. Every shard COMPLETED, the
boundary-reference checks passed, protected bytes were unchanged and the reference-parity check passed.
Every shard was recorded at code `32d5c93c01bf43d818426cbfc926577e20446d08`, runner sha256 prefix `fe171028ee0b`.
The declared rule diff against 1.1.2 is exact (PASS). After the replay, a review follow-up added two checks. The replay script now requires and hash-checks `EURUSD_m5_meta.csv`; that later version of the script has a different sha256 from the one the shards recorded. Separately, the recompute script refuses incomplete or identity-mismatched shard sets. Checked after the run, the committed spread metadata the replay read matches the hash declared in its provenance (`46a47408…0254a`).

Artifacts are in `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/lsmc113_eurusd_entry/`: `merged.json`,
the per-shard `audit.json`, `scans.csv`, `signal_events.jsonl` and `mismatches.jsonl`, and `l5_recompute.json`.

To reproduce:
```sh
PYTHONPATH=src:scripts python scripts/lsmc_v113_60d_replay.py --symbol EURUSD \
  --resume-root artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/lsmc113_eurusd_entry \
  --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/lsmc113_eurusd_entry/merged.json
PYTHONPATH=src:scripts python scripts/lsmc_v113_l5_recompute.py \
  --root artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/lsmc113_eurusd_entry --symbol EURUSD
```

| Scope | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|
| EURUSD × WATCH (12,086 active scans) | PASS | PASS | PASS (LONG geometry; SHORT stop NOT_APPLICABLE, see gap) | PASS | **INSUFFICIENT** (914) | PASS |

- Scans: 12,094 in total. 8 of them are `MARKET_CLOSED` FX-weekend boundary scans; these fail L4.evaluated as expected and are excluded from the active count.
- Opportunity scans: 1,783 across 51 unique opportunities (26 LONG, 25 SHORT). 888 scans have both a stop and a target, and 305 are reward/risk eligible.
- C11 target changes per opportunity: **0** within shards and 0 across shards. C11 source counts: CONFIRMED_OPPOSING_H1_SWING 26, PRIMARY_EXTERNAL_LIQUIDITY 22, no target 3.
- **D-LSMC-6 (POI age in trading days): PASS.** Active POIs were checked 11,881 times and observed expiries 7,447 times against an independent count of distinct NY-17:00 weekday trading dates, with 0 violations. 50,477 expiry reports belong to POIs never shown as the nearest POI, so their origin was not observed and they were not checked.
- **D-LSMC-1 (C10 pip evidence): PASS.** There were 0 `C10_PIP_SIZE_NOT_EVIDENCED` results. All 914 opportunity scans that have a stop carry the host-captured pip (OD1014-FAST D2).
- **L5: INSUFFICIENT.** The recorded VT M5 spread is present. The OD1011-COMMISSION full-login binding is absent in this container: only the committed `account_login_suffix` exists, and a suffix alone is never a binding. All 914 priced rows therefore report `COMMISSION_EVIDENCE_MISSING`. `scripts/lsmc_v113_l5_recompute.py` recomputes L5 from the committed scans using the host's `config/local/owner_ticket.yaml`.
  - Note: the runner's `COST_SOURCE` description string still says "login suffix". Its code requires the full login, and the string is kept so that the runner sha256 recorded in the shard reports stays valid.

### Coverage gap (blocking for a full-scope claim)

SHORT C10 stop geometry was **NOT_EVALUATED**. C10-B requires a live bid/ask spread for SHORT
(`large_smc_core/c10_stop_policy.py`), and the recorded MqlRates spread is bar metadata, not an evidenced quote.
None is invented, so all 869 SHORT opportunity scans (25 opportunities) end with `MISSING_SPREAD` and no stop.
L3 stop geometry and L5 are therefore exercised on LONG only.

The registration draft below records exactly that coverage.

## Identity (final PR head; unchanged by the evidence commit)

| Item | sha256 |
|---|---|
| Contract `strategies/ST_LARGE_SMC_V1_1_1_3.yaml` | `e5f04912695967fdc95178e0f862d9c2af47f56529f8c97b1a8a104198f1aa7b` |
| Engine (`lsmc_v113_logic_gate.engine_sha256`, 7 `src/large_smc_v113/*.py`) | `279ef511e6e94cb4ea571c28bc30146a7c49c205282d6eb2883007ac66e34bfe` |
| `src/large_smc_core/c10_stop_policy.py` | `383143bc0c3e0687b2a4032652e800111482f7fe9e76b3536d01f1540dc641da` |
| `src/fx_discovery/features.py` | `c6ef006348c692bbee13a08ede290c65ce89351aa928fc22dd98eadd1d496731` |
| `src/large_smc_v112/targets.py` | `a047891b188e00c7db429db3ee1b1e1cbfae5cbc78226f4039ed9290fdfe0e4c` |
| `src/large_smc_v112/metadata.py` | `b0437ae640ccc19a28740f79e83a4ad3eec55f0f81fae54b2db38c7f16a74ca7` |
| `src/large_smc_v112/windows.py` | `7dcfeef1486ca8f1c8f8fa258df9cb47b7e25549b1c82c89ef67d8015db64c05` |
| `src/large_smc_v112/contract.py` | `85e61615b4c64b3bf9d3f0eb5d3941bbb89d22070cf674b97797b6a9f9249820` |
| `config/symbol_metadata/host_captured/EURUSD.json` | `e2993fff54cf42dabebd87c2256843ee8153f1415c624f569525dcc02b54be2e` |
| **Logic identity digest** — sha256 of the sorted JSON `{strategy, contract_sha256, engine_sha256, dependency_and_metadata_sha256}` | **`d27d2c9b8d4e9fa4313d7200503eb03ffb171ad241d4ba85ba6ce3292cca1b37`** |

None of this PR's changed files is in the identity set. Those files are `scripts/lsmc_v113_60d_replay.py`,
`scripts/lsmc_v113_l5_recompute.py`, `src/v1_tickets/lsmc_v113_logic_gate.py` (the gate, outside
`ENGINE_FILES`), and two test files.

## Draft registry entry (NOT APPLIED)

```yaml
# strategies/registry.yaml -> strategies.ST_LARGE_SMC_V1.candidate_versions (draft; owner applies or rejects)
candidate_versions:
  "1.1.3":
    config_source: strategies/ST_LARGE_SMC_V1_1_1_3.yaml
    status: CANDIDATE_PENDING_OWNER_CONFIRM
    contract_sha256: e5f04912695967fdc95178e0f862d9c2af47f56529f8c97b1a8a104198f1aa7b
    engine_sha256: 279ef511e6e94cb4ea571c28bc30146a7c49c205282d6eb2883007ac66e34bfe
    logic_identity_digest: d27d2c9b8d4e9fa4313d7200503eb03ffb171ad241d4ba85ba6ce3292cca1b37
    proposal_generation_authorized: false
    demo_authorized: false
    live_authorized: false
    edge_status: NOT_EVALUATED
    eligibility: PENDING_HOST_L5          # not eligible; also blocked by SHORT C10 coverage
    logic_verified_scopes:
      - symbol: EURUSD
        session: WATCH
        status: PENDING_HOST_L5           # L1-L4, L6 PASS; L5 INSUFFICIENT in container
        gates: {L1: PASS, L2: PASS, L3: PASS, L4: PASS, L5: INSUFFICIENT, L6: PASS}
        directions_evaluated: [LONG]      # SHORT C10 NOT_EVALUATED (no evidenced bid/ask)
        directions_not_evaluated: [SHORT]
        d_lsmc_6: PASS
        d_lsmc_1: PASS
        c11_target_changes: 0
        logic_identity_digest: d27d2c9b8d4e9fa4313d7200503eb03ffb171ad241d4ba85ba6ce3292cca1b37
        evidence: artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/lsmc113_eurusd_entry/merged.json
        data: tests/fixtures/vt_recorded_60d_fx (#215), 2026-08-14T21:00Z..2026-10-13T21:00Z
```

## Open before any owner promotion

1. **Host L5:** run `lsmc_v113_l5_recompute.py` on the host with the full-login `config/local/owner_ticket.yaml`. The result must be L5 PASS with no FAIL.
2. **SHORT C10:** this needs evidenced bid/ask for SHORT stops, or an owner decision on whether the recorded spread may serve as the C10-B spread.
3. **Owner registration decision:** if the owner approves, update the registry and ledger together.

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Replay/shards/boundary oracle | Existing C24 auditor | REUSED | Unmodified evaluator; adds FX inputs and resume |
| L5 cost gate | `logic_gate.l5_cost`, `manual_ticket.cost_at_or_above_block`, `resolve_commission` | REUSED | Canonical OD1009-D2 / OD1011 predicates |
| POI-age oracle | Python `zoneinfo` | REUSED | Independent NY-17:00 trading-date count |

Broker contact, order calls and mutations: **0**.
