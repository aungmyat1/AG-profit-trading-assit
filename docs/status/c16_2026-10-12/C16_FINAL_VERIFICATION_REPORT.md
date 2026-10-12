---
class: status_evidence
state: C16_LOGIC_VERIFICATION_COMPLETE
owner_reviewed: null
review_by: 2026-11-12
---

# C16 final verification report

C16_LOGIC_VERIFICATION_COMPLETE
Generated 2026-10-12T17:33:13Z · matrix complete: True

## A. Repository and governance

- main = requested C15 baseline = `65efdd87e1f762d0ee79ebef5bc1de01d18564f3`. Revision binding: ASW: the artifact self-records verification_code_sha = 65efdd87e1f762d0ee79ebef5bc1de01d18564f3; LSMC: the driver emits no git-revision field; revision identity is carried by the C16 output path and this report; CCFD: the driver emits no git-revision field; it self-records the contract hash, the runtime engine hash and the dataset manifest, which is what it binds to.
- Resource authority: historical owner-issued commit `82e6e5cc…` restores `docs/governance/AG_RESOURCE_MANAGEMENT_POLICY_V1.md` (sha256 `8bba5dba56635416a9f5217b52cf55699f1d2a1211119a0990dc98a9be7998aa`), `scripts/resource_guard.py` (sha256 `0970ebb1dfa10d13c6926da915998444617509af1f42094e6bceb24788d36ab4`) and `tests/test_resource_guard.py` (sha256 `1122e0c3f9f8f93a58585d270fb3f58914207d3e9e7fd4aad9faa923ee192a8dd`). At campaign start these bytes were on main only as draft PR #180 (head `d28cacb7…`), so the agent pinned that exact revision and ran the guard tests and end-to-end drills first. **MERGED BY THE OWNER as commit 7dfc8a20 after the campaign began; the agent pinned the byte-identical historical revision and never merged or approved anything** — main is now `a8271fea…` (later `0278653`, `d6b150a`) and carries the same bytes (verified by sha256). The campaign itself ran at `65efdd87…`; every identity the campaign pinned was recomputed at the new main tip and is unchanged, so the verdicts below hold at `a8271fea…` too.
- No authoritative replay was started before resource authority was established: the guard revision was pinned and its tests + end-to-end drills passed first.
- Resource classification **R3** (authoritative experiment + full verification campaign + long-history replay), required RAM 3000 MB floor met, gate **PASS**, competing heavy job: none, workers = 1 (policy default).
- Resource lock held for the whole campaign by a single registered owner; released at the end. Lock file is runtime state and is never committed.
- Identity attribution: The C15 original CCFD evidence (date 2026-10-11) records runtime_engine_hash a089001c…, while the C15 reverify (2026-10-12) and C16 both record 0a3886eb…. Both are legitimate historical values. Root cause: commit 1eb4cb57 'OD1012-PIN-LAND … (#168)' changed config/v1_tickets/crypto_cfd_ticket_policy.yaml account_login_suffix "985" -> "999" under owner decision OD1012-ACCOUNT. That config file is one of the 21 files in the ST_CRYPTO_CFD_SWEEP_RETEST_V1 engine identity list, so the identity hash moved with it. Verification: Recomputed _sha256_text(ADAPTERS['ST_CRYPTO_CFD_SWEEP_RETEST_V1'][1]) over all 80 recent revisions: exactly one file differs between the two states — the account-pin line in that config — and no engine source file changed. C15-original vs C16 = 17 field differences (1 replay-date argument + 16 OD1012-ACCOUNT derivations, 0 unexplained); C16 vs the C15 reverify: BYTE_IDENTICAL (all four output files).
- Policy values were used exactly as issued: R1 ≥ 1,200 MB, R2 ≥ 2,500 MB, R3 ≥ 3,000 MB with no competing heavy local agent, one heavy workload at a time, default one worker, fail-closed on any unmet gate.

## B. Strategy verification

### ST_ASIAN_SWEEP_5R_V1@1.1.2 — PARTIALLY_LOGIC_VERIFIED

Declared scopes: **10** · LOGIC_VERIFIED **3** · NOT_VERIFIED **5** · INSUFFICIENT **2**

Scope axes: instruments[] (5) x session_pairs[] (2) = 10 declared scopes; 8 replayable

| Scope | Symbol | Dir | Session | Emissions | L1–L6 | Verdict |
|---|---|---|---|---|---|---|
| `ASW:EURUSD:ASIAN_LONDON` | EURUSD | LONG,SHORT | ASIAN_LONDON | 3 | L1:PASS L2:PASS L3:FAIL L4:PASS L5:PASS L6:PASS | **NOT_VERIFIED** |
| `ASW:EURUSD:LONDON_NEWYORK` | EURUSD | LONG,SHORT | LONDON_NEWYORK | 5 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **LOGIC_VERIFIED** |
| `ASW:GBPUSD:ASIAN_LONDON` | GBPUSD | LONG,SHORT | ASIAN_LONDON | 7 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **LOGIC_VERIFIED** |
| `ASW:GBPUSD:LONDON_NEWYORK` | GBPUSD | LONG,SHORT | LONDON_NEWYORK | 4 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **LOGIC_VERIFIED** |
| `ASW:USDJPY:ASIAN_LONDON` | USDJPY | — | ASIAN_LONDON | 0 | L1:PASS L2:INSUFFICIENT L3:PASS L4:INSUFFICIENT L5:FAIL L6:PASS | **NOT_VERIFIED** |
| `ASW:USDJPY:LONDON_NEWYORK` | USDJPY | — | LONDON_NEWYORK | 0 | L1:PASS L2:INSUFFICIENT L3:PASS L4:INSUFFICIENT L5:FAIL L6:PASS | **NOT_VERIFIED** |
| `ASW:XAUUSD:ASIAN_LONDON` | XAUUSD | — | ASIAN_LONDON | 0 | L1:PASS L2:INSUFFICIENT L3:PASS L4:INSUFFICIENT L5:FAIL L6:PASS | **NOT_VERIFIED** |
| `ASW:XAUUSD:LONDON_NEWYORK` | XAUUSD | — | LONDON_NEWYORK | 0 | L1:PASS L2:INSUFFICIENT L3:PASS L4:INSUFFICIENT L5:FAIL L6:PASS | **NOT_VERIFIED** |
| `ASW:AUDUSD:ASIAN_LONDON` | AUDUSD | — | ASIAN_LONDON | 0 | L1:INSUFFICIENT L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **INSUFFICIENT** |
| `ASW:AUDUSD:LONDON_NEWYORK` | AUDUSD | — | LONDON_NEWYORK | 0 | L1:INSUFFICIENT L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **INSUFFICIENT** |

Logical vs economic vs authorization: logical = PARTIALLY_LOGIC_VERIFIED; economic = NOT_EVALUATED / no edge claim; runtime READY = NOT_READY (no registry promotion); demo = NOT_GRANTED; live = NOT_GRANTED.

- `ASW:EURUSD:ASIAN_LONDON`: {"class": "REPRODUCED_CAUSAL_FAILURE", "gate_failures": ["L3"], "l3_revised_case_ids": ["recorded:EURUSD:ASIAN_LONDON:2026-07-31"], "detail": "an emission inside the scope violates the L3 causality contract; reproduced from recorded bars"}
- `ASW:USDJPY:ASIAN_LONDON`: {"class": "THIN_SIGNAL_COVERAGE", "gate_status": {"L1": "PASS", "L2": "INSUFFICIENT", "L3": "PASS", "L4": "INSUFFICIENT", "L5": "FAIL", "L6": "PASS"}, "detail": "no valid entry exists for this symbol x session across 57 sessions, so the entry-gate rule cells are unexercised and there is no positive example to verify", "symbol_evidence": {"l5_verdict": "BLOCK", "block_reasons": ["SYMBOL_EVIDENCE_MISSING: pip size not evidenced for ['USDJPY']"], "warn_reasons": ["SYMBOL_METADATA_PENDING: USDJPY, XAUUSD -> PENDING_AGP-C2-SYMMAP (not invented)"]}}
- `ASW:USDJPY:LONDON_NEWYORK`: {"class": "THIN_SIGNAL_COVERAGE", "gate_status": {"L1": "PASS", "L2": "INSUFFICIENT", "L3": "PASS", "L4": "INSUFFICIENT", "L5": "FAIL", "L6": "PASS"}, "detail": "no valid entry exists for this symbol x session across 57 sessions, so the entry-gate rule cells are unexercised and there is no positive example to verify", "symbol_evidence": {"l5_verdict": "BLOCK", "block_reasons": ["SYMBOL_EVIDENCE_MISSING: pip size not evidenced for ['USDJPY']"], "warn_reasons": ["SYMBOL_METADATA_PENDING: USDJPY, XAUUSD -> PENDING_AGP-C2-SYMMAP (not invented)"]}}
- `ASW:XAUUSD:ASIAN_LONDON`: {"class": "THIN_SIGNAL_COVERAGE", "gate_status": {"L1": "PASS", "L2": "INSUFFICIENT", "L3": "PASS", "L4": "INSUFFICIENT", "L5": "FAIL", "L6": "PASS"}, "detail": "no valid entry exists for this symbol x session across 58 sessions, so the entry-gate rule cells are unexercised and there is no positive example to verify", "symbol_evidence": {"l5_verdict": "BLOCK", "block_reasons": ["SYMBOL_EVIDENCE_MISSING: pip size not evidenced for ['XAUUSD']"], "warn_reasons": ["SYMBOL_METADATA_PENDING: USDJPY, XAUUSD -> PENDING_AGP-C2-SYMMAP (not invented)"]}}
- `ASW:XAUUSD:LONDON_NEWYORK`: {"class": "THIN_SIGNAL_COVERAGE", "gate_status": {"L1": "PASS", "L2": "INSUFFICIENT", "L3": "PASS", "L4": "INSUFFICIENT", "L5": "FAIL", "L6": "PASS"}, "detail": "no valid entry exists for this symbol x session across 58 sessions, so the entry-gate rule cells are unexercised and there is no positive example to verify", "symbol_evidence": {"l5_verdict": "BLOCK", "block_reasons": ["SYMBOL_EVIDENCE_MISSING: pip size not evidenced for ['XAUUSD']"], "warn_reasons": ["SYMBOL_METADATA_PENDING: USDJPY, XAUUSD -> PENDING_AGP-C2-SYMMAP (not invented)"]}}
- `ASW:AUDUSD:ASIAN_LONDON`: {"class": "NO_AUTHORITATIVE_DATASET", "detail": "declared in instruments[] but the repository holds no authoritative 60-weekday recorded fixture for this symbol, so the scope cannot be replayed at all"}
- `ASW:AUDUSD:LONDON_NEWYORK`: {"class": "NO_AUTHORITATIVE_DATASET", "detail": "declared in instruments[] but the repository holds no authoritative 60-weekday recorded fixture for this symbol, so the scope cannot be replayed at all"}


### ST_LARGE_SMC_V1@1.1.0 — BLOCKED_OR_INSUFFICIENT

Declared scopes: **6** · LOGIC_VERIFIED **0** · NOT_VERIFIED **2** · INSUFFICIENT **4**

Scope axes: instruments[] (6) x single lane = 6 declared scopes; 2 replayable

| Scope | Symbol | Dir | Session | Emissions | L1–L6 | Verdict |
|---|---|---|---|---|---|---|
| `LSMC:BTCUSD` | BTCUSD | LONG,SHORT | NONE (crypto CFD, 24h observation) | 2040 | L1:PASS L2:PASS L3:PASS L4:PASS L5:WARN L6:PASS | **NOT_VERIFIED** |
| `LSMC:ETHUSD` | ETHUSD | LONG,SHORT | NONE (crypto CFD, 24h observation) | 848 | L1:PASS L2:PASS L3:PASS L4:PASS L5:WARN L6:PASS | **NOT_VERIFIED** |
| `LSMC:EURUSD` | EURUSD | — | N/A | 0 | L1:INSUFFICIENT L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **INSUFFICIENT** |
| `LSMC:GBPUSD` | GBPUSD | — | N/A | 0 | L1:INSUFFICIENT L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **INSUFFICIENT** |
| `LSMC:USDJPY` | USDJPY | — | N/A | 0 | L1:INSUFFICIENT L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **INSUFFICIENT** |
| `LSMC:XAUUSD` | XAUUSD | — | N/A | 0 | L1:INSUFFICIENT L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **INSUFFICIENT** |

Logical vs economic vs authorization: logical = BLOCKED_OR_INSUFFICIENT; economic = NOT_EVALUATED / no edge claim; runtime READY = NOT_READY (no registry promotion); demo = NOT_GRANTED; live = NOT_GRANTED.

- `LSMC:BTCUSD`: {"class": "OPERATIONAL_REJECT_NO_STOP", "detail": "every OPPORTUNITY scan is operationally rejected (['REJECT_NO_STOP'], ['C10_PIP_SIZE_NOT_EVIDENCED']) because C10's pip-size input is unevidenced for BTCUSD; logical detection L1-L4/L6 passes on every scan"}
- `LSMC:ETHUSD`: {"class": "OPERATIONAL_REJECT_NO_STOP", "detail": "every OPPORTUNITY scan is operationally rejected (['REJECT_NO_STOP'], ['C10_PIP_SIZE_NOT_EVIDENCED']) because C10's pip-size input is unevidenced for ETHUSD; logical detection L1-L4/L6 passes on every scan"}
- `LSMC:EURUSD`: {"class": "NO_AUTHORITATIVE_DATASET", "detail": "declared in the 1.1.0 instruments[] but the repository's authoritative recorded dataset carries BTCUSD/ETHUSD only, so no replay is possible"}
- `LSMC:GBPUSD`: {"class": "NO_AUTHORITATIVE_DATASET", "detail": "declared in the 1.1.0 instruments[] but the repository's authoritative recorded dataset carries BTCUSD/ETHUSD only, so no replay is possible"}
- `LSMC:USDJPY`: {"class": "NO_AUTHORITATIVE_DATASET", "detail": "declared in the 1.1.0 instruments[] but the repository's authoritative recorded dataset carries BTCUSD/ETHUSD only, so no replay is possible"}
- `LSMC:XAUUSD`: {"class": "NO_AUTHORITATIVE_DATASET", "detail": "declared in the 1.1.0 instruments[] but the repository's authoritative recorded dataset carries BTCUSD/ETHUSD only, so no replay is possible"}

- `LSMC:BTCUSD` reported separately — logical detection: PASS (L1/L2/L3/L4/L6 on all scans; L5 WARN on all scans); ticket validity: OPERATIONALLY_REJECTED - REJECT_NO_STOP / C10_PIP_SIZE_NOT_EVIDENCED (fail-closed by design); economic: NOT_EVALUATED (no cost model bound for this symbol)
  - C10 stop rule present: C10_STRUCTURAL_INVALIDATION_V1 (`src/large_smc_core/c10_stop_policy.py`); stop status **NOT_APPLICABLE** because C10_PIP_SIZE_NOT_EVIDENCED for BTCUSD; action taken: REJECT_NO_STOP (fail-closed); no stop was invented. Missing input: src/large_smc_watch/contract.py C10_PIP_SIZE maps only EURUSD/GBPUSD; the contract's own comment states a pip is only evidenced for 5-digit FX majors.
- `LSMC:ETHUSD` reported separately — logical detection: PASS (L1/L2/L3/L4/L6 on all scans; L5 WARN on all scans); ticket validity: OPERATIONALLY_REJECTED - REJECT_NO_STOP / C10_PIP_SIZE_NOT_EVIDENCED (fail-closed by design); economic: NOT_EVALUATED (no cost model bound for this symbol)
  - C10 stop rule present: C10_STRUCTURAL_INVALIDATION_V1 (`src/large_smc_core/c10_stop_policy.py`); stop status **NOT_APPLICABLE** because C10_PIP_SIZE_NOT_EVIDENCED for ETHUSD; action taken: REJECT_NO_STOP (fail-closed); no stop was invented. Missing input: src/large_smc_watch/contract.py C10_PIP_SIZE maps only EURUSD/GBPUSD; the contract's own comment states a pip is only evidenced for 5-digit FX majors.

### ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0 — PARTIALLY_LOGIC_VERIFIED

Declared scopes: **8** · LOGIC_VERIFIED **2** · NOT_VERIFIED **6** · INSUFFICIENT **0**

Scope axes: instruments[] (2) x direction (2) x day_type (2) = 8 declared scopes; 8 replayable

| Scope | Symbol | Dir | Session | Emissions | L1–L6 | Verdict |
|---|---|---|---|---|---|---|
| `CCFD:BTCUSD:LONG:WEEKDAY` | BTCUSD | LONG | WEEKDAY | 0 | L1:PASS L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **NOT_VERIFIED** |
| `CCFD:BTCUSD:SHORT:WEEKDAY` | BTCUSD | SHORT | WEEKDAY | 2 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **LOGIC_VERIFIED** |
| `CCFD:BTCUSD:LONG:WEEKEND` | BTCUSD | LONG | WEEKEND | 0 | L1:PASS L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **NOT_VERIFIED** |
| `CCFD:BTCUSD:SHORT:WEEKEND` | BTCUSD | SHORT | WEEKEND | 0 | L1:PASS L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **NOT_VERIFIED** |
| `CCFD:ETHUSD:LONG:WEEKDAY` | ETHUSD | LONG | WEEKDAY | 3 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **LOGIC_VERIFIED** |
| `CCFD:ETHUSD:SHORT:WEEKDAY` | ETHUSD | SHORT | WEEKDAY | 1 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **NOT_VERIFIED** |
| `CCFD:ETHUSD:LONG:WEEKEND` | ETHUSD | LONG | WEEKEND | 0 | L1:PASS L2:INSUFFICIENT L3:INSUFFICIENT L4:INSUFFICIENT L5:INSUFFICIENT L6:INSUFFICIENT | **NOT_VERIFIED** |
| `CCFD:ETHUSD:SHORT:WEEKEND` | ETHUSD | SHORT | WEEKEND | 1 | L1:PASS L2:PASS L3:PASS L4:PASS L5:PASS L6:PASS | **NOT_VERIFIED** |

Logical vs economic vs authorization: logical = PARTIALLY_LOGIC_VERIFIED; economic = NOT_EVALUATED / no edge claim; runtime READY = NOT_READY (no registry promotion); demo = NOT_GRANTED; live = NOT_GRANTED.

- `CCFD:BTCUSD:LONG:WEEKDAY`: {"class": "THIN_OR_ZERO_EMISSION_SCOPE", "detail": "0 emission(s) over 44 calendar days vs declared minimum 2", "blockers": ["NO_EMISSIONS", "L2:INSUFFICIENT", "L3:INSUFFICIENT", "L4:INSUFFICIENT", "L5:INSUFFICIENT", "L6:INSUFFICIENT"]}
- `CCFD:BTCUSD:LONG:WEEKEND`: {"class": "THIN_OR_ZERO_EMISSION_SCOPE", "detail": "0 emission(s) over 16 calendar days vs declared minimum 2", "blockers": ["NO_EMISSIONS", "L2:INSUFFICIENT", "L3:INSUFFICIENT", "L4:INSUFFICIENT", "L5:INSUFFICIENT", "L6:INSUFFICIENT"]}
- `CCFD:BTCUSD:SHORT:WEEKEND`: {"class": "THIN_OR_ZERO_EMISSION_SCOPE", "detail": "0 emission(s) over 16 calendar days vs declared minimum 2", "blockers": ["NO_EMISSIONS", "L2:INSUFFICIENT", "L3:INSUFFICIENT", "L4:INSUFFICIENT", "L5:INSUFFICIENT", "L6:INSUFFICIENT"]}
- `CCFD:ETHUSD:SHORT:WEEKDAY`: {"class": "THIN_OR_ZERO_EMISSION_SCOPE", "detail": "1 emission(s) over 44 calendar days vs declared minimum 2", "blockers": ["THIN_SIGNAL_COVERAGE_LT_2"]}
- `CCFD:ETHUSD:LONG:WEEKEND`: {"class": "THIN_OR_ZERO_EMISSION_SCOPE", "detail": "0 emission(s) over 16 calendar days vs declared minimum 2", "blockers": ["NO_EMISSIONS", "L2:INSUFFICIENT", "L3:INSUFFICIENT", "L4:INSUFFICIENT", "L5:INSUFFICIENT", "L6:INSUFFICIENT"]}
- `CCFD:ETHUSD:SHORT:WEEKEND`: {"class": "THIN_OR_ZERO_EMISSION_SCOPE", "detail": "1 emission(s) over 16 calendar days vs declared minimum 2", "blockers": ["THIN_SIGNAL_COVERAGE_LT_2"]}


**Crypto CFD identity, corrected:** the `9a1f6759…` value C15 could not resolve is **not a stray
citation** — it is the raw-bytes sha256 of the contract revision `89f1fa6c`, i.e. before PR #162
appended the `freeze` block, and it is precisely the metric the replay driver computes for the
1.1.0 candidate (`research_logic_identity` hashes the contract's raw bytes) and records as
`contract_sha256`/`logic_identity.contract_hash` (present in the C15 artifact on branch
`feat/c15-crypto-verification` and absent from that file's current revision). C15's sentence
compared that raw-file hash, taken before #162, against the canonical mapping hash `ac116e0a…`
taken after it. Both are legitimate; neither was overwritten; the canonical identity is unchanged
and self-consistent. The residual issue is documentation (`D-CCFD-2b`): one field name carries two
kinds of identity, so a by-hand comparison across revisions silently compares unlike things.

## C. Evidence

Every verdict above is derived from a committed artifact; the generator recomputes hashes from the files and never transcribes them.

| Artifact | sha256 |
|---|---|
| `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c16_2026-10-12/asw_v112_60d_c16_run1.json` | `8a529ae4592404b6…` |
| `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c16_2026-10-12/asw_v112_60d_c16_run2.json` | `8a529ae4592404b6…` |
| `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c16_2026-10-12/l3_repro_eurusd_asian_london_2026-07-31_c16.json` | `a84a0a4dc6d6b7e4…` |
| `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c16_2026-10-12/lsmc_btcusd_vt_recorded_60d.json` | `27d2adfe2c6bec49…` |
| `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c16_2026-10-12/lsmc_ethusd_vt_recorded_60d.json` | `97ba1a4942b5a30c…` |
| `artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0/c16_2026-10-12/replay_report.json` | `ffb2ec1635328abb…` |
| `artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0/c16_2026-10-12/runtime_identity_verification.json` | `60cb884f870034f8…` |
| `artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0/c16_2026-10-12/signal_events.json` | `4fa10520a55a9c4d…` |

## D. GitHub deliverables

- PR #180 — resource-governance restoration: reviewed as GOVERNANCE_READY_FOR_OWNER_APPROVAL
  (19/19 guard tests, 9 end-to-end drills, CI green); the agent did not merge it. **The owner
  merged it** as `7dfc8a20`; the policy/guard/tests bytes on main are byte-identical to the pinned
  revision. The merge happened after the campaign's replays had started, so no C16 replay was
  retro-fitted to it.
- PR #181 — C16 blocked-state evidence: **also merged by the owner**, as `0278653`
  (`evidence(c16): record resource-authority blocker without replay claims`). The blocked-state
  text therefore remains a permanent record on main and was not rewritten by this campaign.
- PR #182 — S1 acceptance evidence — merged by the owner as `d6b150a`; docs only.
- **This PR** carries the completed campaign. It supersedes the five blocked-state deliverables
  that #181 landed, as an ordinary reviewable diff over them: `C16_FINAL_VERIFICATION_REPORT.md`
  (blocked → `C16_LOGIC_VERIFICATION_COMPLETE`), `C16_FINAL_SCOPE_MATRIX.json`
  (`scopes: []` → 24 decided scopes), `C16_REPRODUCIBILITY_REPORT.json` (0 runs → 3 verifier runs
  plus 3 repeats with hashes), `C16_RESOURCE_REPORT.json` (authority absent → R3 gate PASS and
  per-lane timing) and `C16_DEFECT_REGISTER.md` (one blocker → 12 root-caused defects plus one
  explained observation). The transition is visible in the diff rather than hidden by a rewrite.
- `docs/status/c16_2026-10-12/C16_ASW_V113_CORRECTION_PROPOSAL.md` records the proposed strategy
  correction; the v1.1.3 contract itself is declaration-only (all authority flags false) and is
  not registered, so merging this PR confers no authority on it.
- Main advanced during the campaign: `7dfc8a20` (#180), `a8271fea` (#183), `0278653` (#181),
  `d6b150a` (#182). Identity impact: NONE (recomputed at each tip — `ASW engine 243c4ff1…`,
  `ASW v1.1.2 contract 941dec55…`, `CCFD engine 0a3886eb…` are unchanged); contract/registry
  impact: NONE (`strategies/` frozen files and `config/` are untouched by all four). The C16
  artifacts record `65efdd87…` as the revision they ran at, and the verdicts were re-checked
  against the newer tips.
- Strategy-rule corrections travel in separate PRs; nothing in this PR changes a rule, threshold,
  contract, registry entry or authorization.
## E. Execution safeguards

All counters are read from the artifacts, not asserted:

- broker mutations: **0** · order API calls: **0** · MT5 calls: **0**
- registry changes: **0** · READY promotions: **0** · demo authorization changes: **0** · live authorization changes: **0**
- strategy parameter/threshold changes: **0** · gates weakened: **0**
- sealed OOS opened: **0** · synthetic data presented as historical: **0** · destructive cleanup: **0** · automatic merges: **0**

## F. Final status

C16_LOGIC_VERIFICATION_COMPLETE

| Family | Verdict | Verified / Declared |
|---|---|---|
| ST_ASIAN_SWEEP_5R_V1@1.1.2 | PARTIALLY_LOGIC_VERIFIED | 3 / 10 |
| ST_LARGE_SMC_V1@1.1.0 | BLOCKED_OR_INSUFFICIENT | 0 / 6 |
| ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0 | PARTIALLY_LOGIC_VERIFIED | 2 / 8 |

