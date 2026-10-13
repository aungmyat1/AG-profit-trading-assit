---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-C15-LSMC follow-up — independent logic audit of `ST_LARGE_SMC_V1@1.1.0` (2026-10-13)

**AGP-C17-LSMC-LOGIC-COMPLETION-R1**, Phases A–C, completing the C15-LSMC follow-up mission
(`docs/governance/AGP_C15_THREE_STRATEGY_LOGIC_FIRST_2026-10-11.md`). Off-host,
committed inputs only: no broker, no network, no MT5 call, no live candle. **No frozen rule, threshold,
contract byte, registry status, READY, demo or live surface was changed.** Alerts stay `ARCHIVE_ONLY`.
Resource class **R1** (`docs/governance/AG_RESOURCE_MANAGEMENT_POLICY_V1.md`): 50 s wall, 120 MB peak RSS,
single process, no competing heavy job. Measured on the final
artifact: 50.0 s wall, 119.5 MB peak RSS, three runs, all byte-identical. The unbounded 60-day crypto replays were **not** re-run (owner scope
decision `audit_only`); the committed C16 artifacts were re-derived from their own bytes instead.

**Audit verdict: `NOT_VERIFIED`** — scope: rule conformance, causality and internal consistency across the whole
1.1.0 book. Two blocking findings: **D-LSMC-6** (a declared rule is implemented in a different unit) and
**D-LSMC-1** (C10 stop geometry is not evaluable on 4 of the 6 contracted instruments). Neither is fixable on
agent authority.

**The shipped 18-case harness verdict is `LOGIC_VERIFIED`** (18/18 cases, L1–L4 + L6 PASS, L5 WARN, zero
blocking failures) — *after* this PR repairs the harness and one evidence fixture. Before the repair the same
harness returned `LOGIC_NOT_VERIFIED`, and for 4 days before that it returned `LOGIC_VERIFIED` while evaluating
none of its opportunity rules. Both failures were in the verification layer, not in the strategy.

Logic verification ≠ EDGE_VERIFIED ≠ execution authorization. `proposal_generation_authorized`,
`demo_authorized` and `live_authorized` remain `false`; economic status remains `NOT_EVALUATED`.

| Item | Value |
|---|---|
| Strategy / contract | `ST_LARGE_SMC_V1@1.1.0`, `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` sha256 `78285f9f…357b4` = **registry** ✔ |
| Engine (`src/large_smc_watch/{__init__,contract,detect,watch}.py`) | `88dd9f1f…b689` ≠ registry `ec0b2f3d…70d4` (**D-LSMC-3**, drift isolated to `watch.py` `86ac9cdc…`) |
| Dependencies | `fx_discovery/features.py` `c6ef0063…`, `large_smc_core/c10_stop_policy.py` `383143bc…` — both unchanged since C1 |
| Gate | `src/v1_tickets/lsmc_logic_gate.py` `e3133071…`, `src/v1_tickets/logic_gate.py` `e912068a…` |
| `code_sha` in the report | `761f00fa…` = `git rev-parse HEAD` at run time (the branch base); every other hash is over the working-tree bytes actually exercised |
| Audit driver | `scripts/lsmc_v110_logic_audit.py` (new, schema `AGP_C15_LSMC_V110_LOGIC_AUDIT_V1`) |
| Candidate prepared for D-LSMC-6 | `strategies/ST_LARGE_SMC_V1_1_1_2.yaml` (new; `SPEC_ONLY_NOT_WIRED`, `CANDIDATE_PENDING_OWNER_CONFIRM`, not registered, all authority `false`) |
| Machine report | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_audit.json` sha256 `49aecfba…a4742` |
| Lane-A report (18 cases) | `…/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_verification_18case.json` sha256 `2addd81b…cefd6` |
| v1.1.1 candidate rows | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v111_candidate_audit.json` sha256 `2dff4692…598b0` — re-captured as the producer's JSON payload only; the earlier capture of this file also contained the `smartmoneyconcepts` stdout banner and the script's markdown summary table, which made a `.json` file that was not valid JSON |
| Reproducibility | **byte-identical across three full runs** (`cmp` clean; sha256 `49aecfba…a4742` on all three runs): no wall-clock field, no run id, no hostname, fixed rng seed `20261013`; the only run-dependent value is `identity.code_sha` |

### Full SHA-256 reconciliation (Phase A.7)

Every **evidence** hash this report cites, recomputed from the working tree at write time. `tests/test_lsmc_v110_logic_audit.py::test_report_doc_cites_the_hashes_of_the_files_it_cites` re-checks this table against the files, so a stale sha here fails a normal `pytest -q`. The two source files this PR adds (the audit driver and that test file) are deliberately not rows here: a table that pinned its own checker could never be updated. The gate modules *are* pinned, both here and in the report's `identity.gate_file_sha256`.

| Item | Path | SHA-256 | Note |
|---|---|---|---|
| Frozen contract 1.1.0 | `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` | `78285f9fabcb20af14de327d010e48684dc12205f4435eff886fcc2373a357b4` | equals the registry pin ✔ — not edited |
| Candidate contract 1.1.1 | `strategies/ST_LARGE_SMC_V1_1_1_1.yaml` | `52203c8bfd463f37f7591e7127e982101259c4670dd7af155347434fbb143fdb` | unchanged; `based_on` of 1.1.2 |
| Candidate contract 1.1.2 (new) | `strategies/ST_LARGE_SMC_V1_1_1_2.yaml` | `5931b616f2048dd20c79bc2938ebd71a77b133c5b51b2c2d986664044b58d52f` | carries the D-LSMC-6 rule-change diff; `SPEC_ONLY_NOT_WIRED`, not registered |
| Engine composite (4 files) | `src/large_smc_watch/` | `88dd9f1fb970f7811b437cb3b4c7341e0d1f84320238890eab3381eb0f51b689` | ≠ registry pin `ec0b2f3d…70d4` (D-LSMC-3) — not edited |
| Engine file | `src/large_smc_watch/__init__.py` | `ebbca3c124487c79a41912b6bbf75688d06529257bdc4ee53d0ffe2df789950f` | unchanged since C1 |
| Engine file | `src/large_smc_watch/contract.py` | `51f9a0d088e750399b7ef4d98c978c6974b0b9ef2814f1c4251bbed79a9a5e1c` | unchanged since C1 |
| Engine file | `src/large_smc_watch/detect.py` | `e3fd5e1fe699046c8b4c552e68d6a19a6f4abc51ea9cec3c4734c02db4e27973` | unchanged since C1 |
| Engine file | `src/large_smc_watch/watch.py` | `86ac9cdcfa864b36a06b795920bd333f8fa9cfdd81efa5eb422e1d746bc2c63d` | drift vs the registry pin is isolated to `watch.py` |
| Dependency | `src/fx_discovery/features.py` | `c6ef006348c692bbee13a08ede290c65ce89351aa928fc22dd98eadd1d496731` | unchanged since C1 |
| Dependency | `src/large_smc_core/c10_stop_policy.py` | `383143bc0c3e0687b2a4032652e800111482f7fe9e76b3536d01f1540dc641da` | unchanged since C1 |
| Verification gate | `src/v1_tickets/logic_gate.py` | `e912068adbdbf0c91348c182ec39d375d4e8de7055d5bdeca540a4cf3068cabe` | unchanged |
| Verification gate | `src/v1_tickets/lsmc_logic_gate.py` | `e3133071f126d744b34cd8feae6379bdd41b9474cf9e9775991d4d75ae3ac799` | harness fix (D-LSMC-7) |
| FX H1 export (lanes A/D + POI age) | `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_001/raw/EURUSD_H1.csv` | `63d8227541909adff009f121e7b3ed1cb4e12c718aaeea53b8e55426917bb55c` | committed MT5 export; broker/server/account per its own dataset_manifest.json |
| FX dataset manifest | `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_001/dataset_manifest.json` | `cc87303fe36369c3db8c4787d38d6315410cebaa01984245f82caa41959c9d96` | broker/server/account provenance |
| Fixture set manifest | `tests/fixtures/large_smc_v111/manifest.json` | `1307e1e79a0a48c4e9a9c4aa61a8c0d8cb582fdab3f22a182d15e2cdfb3988e0` | decision time 2026-08-03T00:00:00Z; every pin recomputes ✔ |
| EURUSD fixture (corrected) | `tests/fixtures/large_smc_v111/EURUSD.json` | `2ce91ea1c0eecf2debda0bd6bfb34e37d0f49cd66ccbb00ed199f7f78da6425d` | D-LSMC-8 fix: one timestamp field, bars untouched |
| Machine report | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_audit.json` | `49aecfba08366bb59c98b589bc298076c6c6ba3da7db0fdb304fa95ce03a4742` | **byte-identical across three full runs** |
| Lane-A report (18 cases) | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_verification_18case.json` | `2addd81b81c869f52062788aae35c148a209e66428895f784b58e5b91b7cefd6` | reproduces except its own `generated_at_utc` |
| v1.1.1 candidate rows | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v111_candidate_audit.json` | `2dff4692e3003a5591f629553b68dc97dd3d2296bac1c75f1ac9ae64c27598b0` | captured JSON payload; byte-identical across two runs |
| Committed C16 replay (BTCUSD) | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c16_2026-10-12/lsmc_btcusd_vt_recorded_60d.json` | `27d2adfe2c6bec491ff4d86f297d0d88006f7021dacd70b55814a711c8c6a67c` | re-derived from its own bytes: 17/17 checks pass |
| Committed C16 replay (ETHUSD) | `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c16_2026-10-12/lsmc_ethusd_vt_recorded_60d.json` | `97ba1a4942b5a30c7091a3a654e9a451998e08793c8a8536968e0ccb561387fc` | re-derived from its own bytes: 17/17 checks pass |
| `code_sha` in the report | ``git rev-parse HEAD`` | `761f00fa4594ee5598e810d925bbda51bf3f2985` | branch base commit; the only run-dependent field |

## 1. What was audited

Four lanes plus eleven property checks, all reading committed inputs:

| Lane | Scope | Result |
|---|---|---|
| **A** — shipped fixture harness | `scripts/lsmc_v110_logic_verification.py::cases` (18 cases, unchanged case list) evaluated in-process through `v1_tickets.lsmc_logic_gate` | `LOGIC_VERIFIED`; 542 checks evaluated, 78 NOT_APPLICABLE, **0 never-exercised** |
| **B** — EURUSD host-captured rolling replay | the only `HOST_CAPTURED` FX fixture, every M5 close, host windows D1 30 / H1 200 / M5 300 | `PASS`; 575 scans, 13,692 checks evaluated, 3 distinct opportunities with real C10 stops |
| **C** — bounded crypto replay + committed-C16 re-derivation | first 120 full-D1-window scans per crypto symbol, then every sha256 and count in the two committed C16 artifacts | `PASS`; all 16 boolean re-derivation checks pass per symbol (plus the artifact sha256); committed verdicts reproduce as `NOT_VERIFIED` |
| **D** — detection semantics | tie tolerance, sweeps, sweep→CHoCH window, entry = CHoCH close, C11 causality, recomputed from `fx_discovery.features` primitives | `PASS` |

| Property check | What it proves | Result |
|---|---|---|
| `causality` | 12 sampled EURUSD scans: determinism (replay hash stable), truncation invariance (unclosed bars dropped), future-mutation invariance (forming/future OHLC rewritten), future-append invariance | `PASS` (4/4 tests, 12/12 samples, 1 forming bar present in every input) |
| `window_sensitivity` | the decision-time snapshot under host / half / all-available windows | `PASS` (identical state `NEAR_POI`, bias `LONG`, same POI id) — recorded, not gated: bias/POI selection is window-dependent by construction |
| `calendar_and_sessions` | NY-17:00 day boundary across both 2026 DST transitions, the FX weekend window edge-for-edge, `session_end` inside/outside the canonical sessions (incl. half-open ends), crypto weekend bypass | `PASS` (23.0 h trading day on 2026-03-08, 24.0 h on 2026-11-02; Fri 16:59 NY open / 17:00 closed / Sun 16:59 closed / 17:00 open; 7/7 expiry cases) |
| `poi_age_semantics` | contract unit (trading days) vs implementation (calendar NY-17:00 dates) on three calendars | **`FAIL` → D-LSMC-6** |
| `fail_closed_symbol_metadata` | `resolve_point` against a temp `AG_EVIDENCE_ROOT`: missing file, malformed JSON, sha mismatch, wrong schema, plus a positive control | `PASS` (all four → `(None, MISSING)` and `DATA_ERROR SYMBOL_METADATA_MISSING`; control resolves point `1e-05` `HOST_CAPTURED` and the evidenced C10 pip `0.0001` = exactly 10 points) |
| `archive_only_exactly_once` | `WatchTracker`: duplicate poll, crash between archive and state save, stale→suspend→expire, `MARKET_CLOSED` no-op | `PASS` (5/5 steps: 0 duplicate events, archive not rewritten, identical `transition_id`s after the crash replay, `SUSPENDED` from `NEAR_POI` with no event, then `EXPIRED` at `INFO`) |
| `no_transport_boundary` | static transitive import graph over **repo** modules reachable from `large_smc_watch` (third-party = leaves) + a clean-subprocess runtime probe | `PASS` (48 repo modules, **0** transport/executor/authorization/notification imports statically and at runtime; positive control reached all five pinned modules). MT5 broker-API imports are recorded, not gated → **D-LSMC-10** |
| `harness_regressions` | the three verification-layer defects found here, pinned so they cannot return silently | `PASS` (3/3) |
| `gate_integrity` | Phase B.7 — no fix in this PR hides a failure by suppressing an emission or weakening a gate. Computed, not asserted: the blocking gate set is read from the gate module, coverage from the lanes, emitted-vs-archived counts from the archive lane, the alert-level mapping from the contract, and the frozen engine/contract bytes are re-hashed | `PASS` (11/11 rows; L5 emitted as WARN 1779× and never PASS or FAIL; shipped emissions per lane {'A': 18, 'B': 575, 'C_BTCUSD': 120, 'C_ETHUSD': 120}) |
| `candidate_rule_change_diff` | Phase B.5 — the 1.1.2 candidate contains exactly the rule-change diff it declares: a structural diff of the two parsed contracts, plus frozen-byte, authority, registry and gate-preservation checks | `PASS` (12/12 rows; 15 declared diff paths, 0 undeclared) |
| `phase_b_classification` | Phase B.2 — every reported finding carries one of the five mission classes and a route, and every blocking row is an owner/host route rather than an agent fix | `PASS` (DATA 1, IMPLEMENTATION 1, METADATA 2, VERIFICATION_HARNESS 4) |

An anti-vacuity control is built into the boundary check: if the traversal fails to reach
`large_smc_watch.{contract,detect,watch}`, `fx_discovery.features` and `large_smc_core.c10_stop_policy`, the
check reports `FAIL` instead of a green result over an empty graph. It caught a real traversal bug during this
audit (`from fx_discovery import features as F` was not being followed) before the report was written.

## 2. Findings

Full evidence for every row is in the machine report's `findings[]`. New ids continue the `D-LSMC-*` space of
`docs/status/c16_2026-10-12/C16_DEFECT_REGISTER.md`, which this PR extends; nothing in that register was rewritten.

| ID | Sev | Class | Blocking | Status |
|---|---|---|---|---|
| `D-LSMC-6` | MEDIUM | declaration vs implementation (unit of a frozen rule) | **YES** | NEW — owner decision |
| `D-LSMC-1` | MEDIUM (by design) | missing host/broker evidence | **YES** | REPRODUCED with new FX-side evidence (registered by C16) |
| `D-LSMC-7` | MEDIUM | harness vacuity + undeclared contract state | no | NEW — harness **fixed here** |
| `D-LSMC-8` | MEDIUM | evidence fixture defect | no | NEW — fixture **fixed here** |
| `D-LSMC-3` | MEDIUM | identity-record staleness | no | REPRODUCED (registered by C16) — owner decision |
| `D-LSMC-9` | LOW | reporting (gate status read as coverage) | no | NEW — committed evidence untouched |
| `D-LSMC-10` | LOW | import boundary / packaging | no | NEW — chain already documented in `tests/conftest.py` |
| `D-LSMC-5` | MEDIUM | L5 cost evidence | no | REPRODUCED (registered by C16) |

### D-LSMC-6 — POI max age is declared in **trading days** and implemented in **calendar** NY-17:00 dates (blocking)

`strategies/ST_LARGE_SMC_V1_1_1_0.yaml` declares `rules.poi.max_age_trading_days: 5`, the flagged contract choice
reads "distinct NY-17:00 trading dates", and both frozen specs agree (`docs/specs/LSMC_SPEC_V2_FROZEN.md` §4.2,
`docs/specs/LSMC_SPEC_V1_FROZEN.md:259`). `src/large_smc_watch/watch.py::expires_at` instead applies
`next_day_boundary` `POI_MAX_AGE_TRADING_DAYS + 1` = 6 times, which counts **Saturday and Sunday**.
`watch._poi_age_days` (line 164) implements the declared unit — distinct trading dates — and has **zero callers
in the repository**.

Measured on three calendars (every distinct POI origin, engine expiry vs the declared rule):

| Calendar | Instants | Trading dates | Origins divergent | Trading-day instances expired early | Direction |
|---|---|---|---|---|---|
| Synthetic FX, 4 weeks (contract's own weekend rule; spans the 2026-03-08 DST start) | 481 | 21 | 358 | 646 | 100% `ENGINE_EXPIRES_EARLIER` |
| EURUSD H1 committed export (`SSC_V1_0_1_G2_DEV_001`, 2026-06-21 → 2026-08-02) | 723 | 31 | **600** | **1,080** | 100% `ENGINE_EXPIRES_EARLIER` |
| BTCUSD H1, VT-recorded 60 days | 1,412 | 61 | **0** | 0 | — |

Worked example (EURUSD): a POI born Sun 2026-06-21 21:00 UTC (trading date Mon 2026-06-22) is declared valid
through trading date Mon 2026-06-29, i.e. until 2026-06-29T17:00-04:00. The engine expires it
2026-06-27T21:00Z — Saturday 17:00 New York — so the whole of Monday 2026-06-29 is lost. Origins late in the
week lose two trading dates.

**Materiality.** The direction is conservative and that is measured, not assumed: the trading-date set is a
subset of the calendar-date set, so six calendar boundaries land at or before six trading dates. No
`ENGINE_EXPIRES_LATER` origin exists on any calendar. The engine can suppress an opportunity or hold a state at
`NEAR_POI`/`DEVELOPING`; it can never keep a POI alive longer than the contract allows. **Scope is FX only** —
BTCUSD/ETHUSD trade every calendar date on this venue, so both clocks coincide there, which is why C15/C16 could
not see this and why the 18-case harness cannot either (its H1 windows span fewer than six trading dates).

**Why it is not fixed here.** An engine rule change is an owner decision, and `C001-PRE-RESULT-CORCTION` is
explicit that a rule-byte change to a frozen candidate produces a *new candidate identity*, not a repaired one.
The owner's options are (a) amend the contract/frozen-spec wording to the implemented calendar-date unit, or
(b) ship a new strategy version that wires `_poi_age_days`. It is also not gated in `lsmc_logic_gate.py`: a new
blocking L2 check would silently change the committed C15/C16 lane distributions on any re-run, and the
resolution is not the auditor's to choose.

### D-LSMC-1 — C10 stop geometry is evaluable on 2 of 6 instruments (blocking, by design)

`contract.C10_PIP_SIZE = {"EURUSD": 0.0001, "GBPUSD": 0.0001}`; C10's hard floor is expressed in pips, so
USDJPY, XAUUSD, BTCUSD and ETHUSD take `stop_reason = C10_PIP_SIZE_NOT_EVIDENCED` and the delivery gate rejects
with `REJECT_NO_STOP`. Registered by C16; unchanged. What is **new** is FX-side evidence that the rule works
where a pip *is* evidenced (lane B, §5): two computed C10 stops, each exactly `MIN_BUFFER_PIPS × PIP_SIZE_EURUSD`
= 1.5 pips beyond the sweep extreme, both passing `L3.stop_side` and `L3.stop_beyond_sweep`; and one SHORT
opportunity whose stop is `None` with `MISSING_SPREAD` — C10's side-aware verified-live-spread requirement
failing closed on bars that carry no bid/ask, rather than inventing a spread.

### D-LSMC-7 — the delivery gate blanked every opportunity rule in the shipped harness (fixed here)

`watch.gate_opportunity` (2026-10-10) renames the state to `REJECTED` off-host, because the owner threshold
`config/local/actionability_policy.yaml` is host-only and `watch._remaining_fraction` has no fallback. The gate
keyed its opportunity checks on `state == "OPPORTUNITY"`, so from 2026-10-10 to 2026-10-13 **156 per-check
verdicts silently degraded to NOT_APPLICABLE while L2, L3 and L6 still printed PASS**: `opportunity_symbols_covered`
was `[]`, `c10_stop_geometry_symbols` was `[]`, and all of L2's six opportunity rules, all of L3's geometry and
all of L6's freshness fields were unevaluated on 18/18 cases.

Fixed in `src/v1_tickets/lsmc_logic_gate.py`: `signal_snapshot` inverts the delivery gate exactly (detection lane),
the opportunity checks run on that lane, the shipped state stays in every case record, a new
`L2.delivery_gate_preserves_detection` check asserts the inversion loses nothing (PASS on all 10 opportunity
cases), and `check_coverage` reports `checks_evaluated` / `checks_not_applicable` / `never_exercised_checks` so
any future vacuity is visible in the report itself. `L2.point_source` was split into the declared rule
(`L2.point_source_declared`) and the measured value, because a pre-metadata short-circuit (`MARKET_CLOSED`,
`DATA_ERROR`) was being reported as a point-source failure. No rule was loosened: the same 18 cases, the same
thresholds, the same verdicts on every check that could already be evaluated.

Second half of the finding, **not** fixed: `REJECTED` is a sixth state that `alerts.mapping` in the frozen
contract does not declare (it lists `DEVELOPING`, `NEAR_POI`, `OPPORTUNITY`, `INVALIDATED`, `EXPIRED`, and says
`SUSPENDED`/`IDLE`/`DATA_ERROR`/`MARKET_CLOSED` emit nothing). `watch.WatchTracker._emit` special-cases it to
alert level `INFO`. That needs a contract note or an owner decision.

### D-LSMC-8 — the only HOST_CAPTURED FX fixture was evaluated 68 days after its own data, in the FX weekend (fixed here)

`tests/fixtures/large_smc_v111/EURUSD.json` carried `evaluated_at_utc = 2026-10-10T19:45:53.895829Z` — its own
regeneration wall-clock — instead of the manifest's `decision_time_utc = 2026-08-03T00:00:00Z` that all five
sibling fixtures carry. `2026-10-10T19:45:53Z` is **Saturday 15:45 America/New_York**, inside the FX weekend
close, 68.8 days after the fixture's last M5 bar (`2026-08-02T23:55Z`). Consequences, all reproduced:

1. the 18-case harness verdict was `LOGIC_NOT_VERIFIED` (L2 + L4 FAIL) purely from the fixture timestamp;
2. `scripts/audit_lsmc_v111_candidate.py`'s only `HOST_CAPTURED` row was pinned to `MARKET_CLOSED` / `L4 FAIL` —
   and `tests/test_lsmc_v111_candidate_audit.py` asserted that state under a comment claiming the snapshot was
   "captured Sunday", which the timestamp contradicts;
3. the AGP-4H-C oracle's `L6_closed_ordered_inputs` check had 68 days of slack and could not fail.

Fixed: `evaluated_at_utc` is now the manifest decision time; **all 754 bars (D1 30 / H1 120 / M5 604) are
byte-identical** (0 changed), so no detection comparison resting on those bars is affected; the manifest pin is
updated `b5e1e524…` → `2ce91ea1…`; `tests/_lsmc_v111_fixtures.check_decision_time` now fails closed on any
fixture whose `evaluated_at_utc` diverges from the manifest decision time, in both harnesses; the candidate-audit
expectations were corrected (EURUSD is now `NEAR_POI` / `L4 PASS`, matching the 2026-10-09 C1 result); and
`strategies/registry.yaml::detection_logic_verification.verification_basis` records the correction while keeping
that historical record attributed to the pre-correction bytes it ran on. The oracle's own run JSON
(`research_external/oracles/runs/AGP_4H_C_EURUSD_DETECTION.json`) is frozen historical evidence and was **not**
rewritten; with the corrected fixture its L6 check is boundary-exact (the last H1/M5 bar closes exactly at the
decision instant) and `pytest tests/test_agp_4h_c_detection.py` passes 9/9.

### D-LSMC-9 — a gate PASS on every scan is not coverage

Both committed C16 artifacts report `gate_status_counts` of PASS on **8,961/8,961** full-D1 scans for L1–L4 and
L6. That is true, and it is not coverage: on 6,921 (BTCUSD) and 8,113 (ETHUSD) of those scans the snapshot was
not an `OPPORTUNITY`, so L2's six opportunity rules and all of L3/L6's opportunity checks were NOT_APPLICABLE —
and because `opportunities.with_c10_stop = 0`, `L3.stop_side` and `L3.stop_beyond_sweep` were NOT_APPLICABLE on
**every scan of both 60-day replays**. The committed `NOT_VERIFIED` verdicts already rest on the missing stop
evidence; what was missing is the explicit statement of how little of the gate those headlines evaluated.
Lane C's bounded window shows the same effect at small scale: BTCUSD had 0 opportunity scans in 120, ETHUSD 13.
Committed artifacts are historical evidence and are not rewritten; fresh reports now carry `check_coverage`,
with the three structural NOT_APPLICABLE markers (`L3.geometry`, `L3.stop_geometry`, `L6.freshness`) listed
separately from real gaps so the metric cannot be misread in either direction.

### D-LSMC-10 — no transport or order path, but the import closure does reach the MT5 broker API

Statically and at runtime, nothing reachable from `large_smc_watch` imports Telegram, `requests`, `httpx`,
`aiohttp`, `urllib`, `smtplib`, `socket`, `fastapi`, `uvicorn`, `execution.*`, `trade_management`,
`authorization`, `owner_decision`, `svos`, `notifications`, `api` or `mt5.management_gateway` — 48 repo modules
in the closure, zero hits, 561 modules loaded by `import large_smc_watch` and none of them a transport. But the
closure does contain `src/mt5/market_data.py:17` and `src/mt5/symbol_resolver.py:12`, which import
`MetaTrader5` unconditionally. Path: `large_smc_watch.detect` → `from supply_demand.ob_config import …` →
`supply_demand/__init__.py` eagerly re-exports `.analyzer` → `mt5.market_data` → `MetaTrader5`
(`market_structure/__init__.py` does the same). The engine never *calls* MT5
(`tests/test_v1_large_smc_import_boundary.py` asserts no `order_send`/`order_check`/`positions_get`/
`position_close`, and exempts `MetaTrader5` from its runtime check by design), and `tests/conftest.py` documents
the chain and installs an import-only Linux stub whose every operation raises `MT5StubOperationAttempted`.
Consequence: the `ARCHIVE_ONLY` alert engine is not import-independent of the broker API package — off-host it
is importable only through that stub. Resolution is a packaging decision (lazy re-exports), owner's call, not
made here; no rule or gate changes.

### D-LSMC-3 / D-LSMC-5 — reproduced, unchanged

Engine identity drift (`88dd9f1f…` vs registry `ec0b2f3d…`, isolated to `watch.py`, contract hash matching) and
L5 `WARN` on every scan of every lane (no accepted spread/commission evidence, no cost gate in the 1.1.0 alert
path, per `OD1011-L5`). Both are owner inputs already registered by C16; this PR re-records neither.
`OD1012-LSMC-RRF`'s `lsmc_min_remaining_reward_fraction: 0.5` is a host-local operational parameter, not a
contract rule and not a cost gate; off-host its absence is exactly why lane B's fully-costed opportunities come
back `REJECT_STALE`.

## 3. Phase B — defect classification, harness fixes and the 1.1.2 candidate

Every finding is classified against the mission's five classes (implementation / strategy-contract / data /
metadata / verification-harness) and given a route. Machine-readable rows: `phase_b.rows`; the classification
check itself is `property_checks.phase_b_classification` (**PASS**, {'DATA': 1, 'IMPLEMENTATION': 1, 'METADATA': 2, 'VERIFICATION_HARNESS': 4}).

| ID | Class (mission taxonomy) | Route | Owner decision | Fixed in this PR | Regression test |
|---|---|---|---|---|---|
| `D-LSMC-1` **(blocking)** | **METADATA** | `OWNER_DECISION_REQUIRED_AND_HOST_CAPTURE` | **required** | no | `test_metadata_fails_closed_and_the_positive_control_still_resolves` |
| `D-LSMC-6` **(blocking)** | **IMPLEMENTATION** | `CANDIDATE_1_1_2_RULE_DIFF` | **required** | no | `test_poi_age_divergence_reproduces_and_is_conservative`, `test_declared_trading_day_rule_is_what_the_candidate_must_implement` |
| `D-LSMC-3` | **METADATA** | `OWNER_DECISION_REQUIRED` | **required** | no | `test_frozen_strategy_and_data_identities_are_unchanged` |
| `D-LSMC-5` | **DATA** | `HOST_EVIDENCE_REQUIRED` | **required** | no | `test_verdict_is_not_verified_with_exactly_two_blocking_findings` |
| `D-LSMC-7` | **VERIFICATION_HARNESS** | `FIX_APPLIED_IN_THIS_PR` | no | yes | `test_harness_lane_evaluates_the_opportunity_rules_it_once_blanked`, `test_archive_only_stays_exactly_once` |
| `D-LSMC-8` | **VERIFICATION_HARNESS** | `FIX_APPLIED_IN_THIS_PR` | no | yes | `test_every_fixture_is_pinned_and_evaluated_at_the_manifest_decision_time` |
| `D-LSMC-9` | **VERIFICATION_HARNESS** | `RECORDED_NO_RERUN` | no | no | `test_committed_c16_artifacts_still_rederive_from_their_own_bytes` |
| `D-LSMC-10` | **VERIFICATION_HARNESS** | `RECORDED_NO_ACTION` | no | check rewritten | `test_boundary_check_reaches_the_engine_and_finds_no_transport` |

Full before → after outcomes, one per defect, are in `phase_b.rows` of the machine report (each row also
carries `class_detail`, `fix_applied_in_this_pr`, `prepared_artifact` and the regression test); §2 below has
the evidence narrative for every id.

Two classification notes that matter for the owner's decision:

- **D-LSMC-6 is an implementation defect against a declared contract rule**, not a wording dispute. The 1.1.0
  contract, `docs/specs/LSMC_SPEC_V2_FROZEN.md` §4.2 and `docs/specs/LSMC_SPEC_V1_FROZEN.md:259` all read
  "distinct NY-17:00 trading dates", and the repository already contains that implementation
  (`watch._poi_age_days`, 0 callers). The frozen engine counts calendar boundaries instead. Because 1.1.0 is
  frozen, the correction is prepared as a **new candidate version** rather than as an edit to 1.1.0
  (`C001-PRE-RESULT-CORCTION`).
- **D-LSMC-1 is a metadata defect, and it is deliberately not "fixed".** Making C10 evaluable on USDJPY,
  XAUUSD, BTCUSD and ETHUSD would require inventing a pip size, i.e. fabricating broker metadata — exactly
  what the fail-closed gate exists to prevent. The route is owner confirmation of the `pip_size_rules`
  proposals that 1.1.1 already carries (FX `10 × host_captured_point`, XAUUSD `0.1`, BTCUSD `1.0`,
  ETHUSD `0.1`, all `PENDING_OWNER_CONFIRM` with `apply_before_owner_confirmation: false`) plus a host capture
  for the four symbols that have none. The audit's positive control measures exactly `10 × point` for EURUSD,
  which is what the FX proposal would produce.

### 3.1 No fix hides a failure (Phase B.7)

`property_checks.gate_integrity` is **PASS**. Every row is computed from this run rather than
asserted: the blocking gate set is read from the gate module, coverage from the lanes, emitted-vs-archived
counts from the archive lane, the alert-level mapping from the contract, and the frozen engine and contract
bytes are re-hashed.

| Row | Result |
|---|---|
| `alert_level_mapping_is_still_the_contract_mapping` | ✔ |
| `blocking_gate_set_is_unchanged` | ✔ |
| `coverage_did_not_shrink` | ✔ |
| `emissions_are_still_produced_in_every_lane` | ✔ |
| `every_coverage_gap_is_disclosed_not_hidden` | ✔ |
| `every_emitted_transition_is_archived_exactly_once` | ✔ |
| `fail_closed_metadata_paths_still_fail_closed` | ✔ |
| `l5_stays_advisory_and_is_never_silently_dropped` | ✔ |
| `no_declared_check_is_never_exercised_where_the_rules_are_reachable` | ✔ |
| `no_engine_byte_was_edited_by_this_pr` | ✔ |
| `opportunity_rules_are_now_exercised` | ✔ |

Measured detail: L5 was emitted as `WARN` 1779 times
across lanes A and B and never as `PASS` (that would be invented cost evidence) or `FAIL` (that would be a
stronger gate than `OD1011-L5` signed); shipped emissions per lane {'A': 18, 'B': 575, 'C_BTCUSD': 120, 'C_ETHUSD': 120};
coverage now 542 checks evaluated / 78
NOT_APPLICABLE / 0 never-exercised, against the pre-fix baseline of
541 / 79 with
0 opportunity-rule checks exercised. All
6 opportunity-rule checks
(`L2.c10_stop`, `L2.c11_target`, `L2.direction_matches_bias`, `L2.entry_by_reference`, `L2.expiry_session_end`, `L2.sweep_window_measured`) are exercised on
10 cases each.

The one lane where six opportunity checks are legitimately never exercised — lane C on BTCUSD, whose bounded
window contains no opportunity scan at all — is **disclosed, not hidden**: it is counted per lane
(`scans_where_opportunity_rules_were_not_applicable`), reported as **D-LSMC-9**, and `gate_integrity` fails if
that disclosure disappears.

### 3.2 The 1.1.2 candidate and its explicit rule-change diff (Phase B.5)

`strategies/ST_LARGE_SMC_V1_1_1_2.yaml` (new, sha256 `5931b616f2048dd20c79bc2938ebd71a77b133c5b51b2c2d986664044b58d52f`) is a
**specification-only** candidate: `implementation: SPEC_ONLY_NOT_WIRED`, `registered: false`, `active: false`,
`status: CANDIDATE_PENDING_OWNER_CONFIRM`, `economic_status: NOT_EVALUATED`, every authority flag `false`. It is
bound to the committed 1.1.1 bytes it was derived from (`based_on_sha256`
`52203c8bfd463f37f7591e7127e982101259c4670dd7af155347434fbb143fdb`), and 1.1.1 is bound to the committed 1.1.0 bytes.

The diff it declares is exactly the diff it contains — recomputed as a structural diff of the two parsed
contracts, so an undeclared rule change fails the audit:

| Change | Class | Number changed | Unit changed | Owner decision |
|---|---|---|---|---|
| `C17-D-LSMC-6` (D-LSMC-6) | IMPLEMENTATION_AGAINST_A_DECLARED_CONTRACT_RULE | False | True | PENDING_OWNER_CONFIRM |
| `C17-SPEC-HYGIENE` (spec hygiene) | SPECIFICATION_HYGIENE | False | False | n/a |
| `C17-D-LSMC-1-NOT-A-RULE-CHANGE` (D-LSMC-1) | METADATA_MISSING_OWNER_CONFIRMED_BROKER_PIP_EVIDENCE | False | False | n/a |

Declared structural diff, 1.1.1 → 1.1.2 (15 paths, 0 undeclared, 0 stale):

  - `based_on`
  - `based_on_sha256`
  - `candidate_created_local_date`
  - `candidate_provenance.rule_change_evidence`
  - `candidate_provenance.rule_change_mission`
  - `candidate_rule_changes`
  - `implementation_choices_flagged`
  - `not_specified`
  - `rules.poi.expiry_instant`
  - `rules.poi.expiry_session_basis`
  - `rules.poi.implementation_requirement`
  - `rules.poi.max_age_unit`
  - `rules.poi.max_age_unit_status`
  - `rules.poi.weekend_and_holiday_dates_excluded`
  - `version`

The duplicated top-level `timeframes:` key that 1.1.1 declared twice is removed as a byte-level fix only: the
parsed structure is identical (`duplicate_timeframes_key_was_byte_level_only` ✔), which is why it does not
appear in the diff above. PyYAML silently keeps the last of two duplicate keys, so a duplicate mapping key is
not a valid specification artifact even though it parses.

The candidate's rule text for D-LSMC-6 (number unchanged at 5):

```yaml
poi:
  max_age_trading_days: 5
  max_age_unit: DISTINCT_NY1700_TRADING_DATES
  expiry_instant: START_OF_THE_TRADING_DATE_AFTER_THE_LAST_VALID_TRADING_DATE
  weekend_and_holiday_dates_excluded: true
```

`property_checks.candidate_rule_change_diff` is **PASS**:

| Row | Result |
|---|---|
| `authority_surfaces_stay_false_in_the_candidate` | ✔ |
| `candidate_is_bound_to_the_committed_1_1_1_bytes` | ✔ |
| `candidate_is_not_registered_in_the_registry` | ✔ |
| `d_lsmc_1_carries_no_rule_change` | ✔ |
| `declared_diff_paths_match_the_computed_structural_diff` | ✔ |
| `declared_number_is_unchanged` | ✔ |
| `declared_unit_matches_the_dead_helper_semantics` | ✔ |
| `duplicate_timeframes_key_was_byte_level_only` | ✔ |
| `frozen_1_1_0_contract_bytes_unchanged` | ✔ |
| `frozen_1_1_0_engine_bytes_unchanged` | ✔ |
| `no_gate_is_weakened_and_no_emission_is_suppressed` | ✔ |
| `unit_is_now_explicit` | ✔ |

Before this candidate can be activated: the owner confirms the unit (or restates it), an engine change is
authorized as a **new registered version**, and a **fresh L1–L6 replay** of the changed candidate is run on real
FX H1 data. The 1.1.0 evidence in this report may not be reused for it — see §4.

## 4. Phase C — per-symbol L1–L6 scope matrix and emissions

Rule (`scope_matrix.rule`, computed): a scope is `LOGIC_VERIFIED` only when every **required** gate
(L1–L4 and L6; L5 is advisory per `OD1011-L5`) passes on evidence that actually covers that symbol **and** no
blocking finding applies to it. **No scope qualifies today** — `logic_verified_scopes: []`. No scope is
`EDGE_VERIFIED`; `economic_status` stays `NOT_EVALUATED` everywhere.

| Symbol | Evidence | L1 | L2 | L3 | L4 | L5 | L6 | Blocking findings for this scope | Scope verdict |
|---|---|---|---|---|---|---|---|---|---|
| `EURUSD` | A + B | PASS | PASS | PASS | FAIL† | WARN | PASS | `D-LSMC-6` | **NOT_VERIFIED** |
| `GBPUSD` | A | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-6` | **NOT_VERIFIED** |
| `USDJPY` | A | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-6`, `D-LSMC-1` | **NOT_VERIFIED** |
| `XAUUSD` | A | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-6`, `D-LSMC-1` | **NOT_VERIFIED** |
| `BTCUSD` | A + C | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-1` | **NOT_VERIFIED** |
| `ETHUSD` | A + C | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-1` | **NOT_VERIFIED** |
| `1.1.2` candidate | none — `SPEC_ONLY_NOT_WIRED` | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | n/a (no runtime) | **NOT_VERIFIED** |

The matrix is deliberately **stricter than the shipped gate** on one point, and says so
(`scope_matrix.scopes.<sym>.required_gate_note`): `v1_tickets.logic_gate.BLOCKING` is `(L1, L2, L3, L4)` with L5
and L6 advisory, while this matrix also requires **L6** to PASS. L5 stays advisory per `OD1011-L5` and is never
counted as a required gate — it is `WARN` in every lane, in every scope.

† EURUSD's single `L4 FAIL` is the one `MARKET_CLOSED` scan in lane B: a weekend snapshot is not an evaluable
trading instant, which is precisely what L4 asserts. The scope matrix does **not** excuse it — `required_gates_pass`
is `false` for EURUSD and the reason is recorded (`scope_matrix.scopes.EURUSD.l4_note`), so the symbol fails
closed on the gate as well as on D-LSMC-6.

Evidence classes, per symbol (`scope_matrix.scopes.<sym>.evidence`):

- **A** — the shipped 18-case fixture harness: 2–4 cases per symbol, synthetic plus (for EURUSD/GBPUSD)
  `v111_fixture` cases, all evaluated at the manifest decision time `2026-08-03T00:00:00Z`.
- **B** — EURUSD only: 575 rolling scans over the `HOST_CAPTURED` fixture, 2026-07-30T00:10Z →
  2026-08-03T00:00Z, 3 distinct opportunities of which 2 carry a real C10 stop, 1 of which is fully costed
  (entry + stop + target) and therefore the only place in the repository where positive-risk geometry and a
  reward/risk ratio are measurable at all (§5, §5.1).
- **C** — BTCUSD/ETHUSD: 120 bounded full-D1-window scans each, plus a re-derivation of the committed 60-day
  C16 artifacts from their own bytes (§6). The 60-day replays were **not** re-run (owner scope decision
  `audit_only`).
- GBPUSD, USDJPY and XAUUSD have **fixture-only** evidence: no recorded host data for them exists in this
  repository, so their L1–L6 statuses come from lane A alone and their scope verdicts are correspondingly weak.
  That is recorded here rather than padded with an unbounded replay.

Emissions (`scope_matrix.scopes.<sym>.emissions`): `delivery_mode` is `ARCHIVE_ONLY` for every symbol, the
alert-level mapping equals the contract's, no transport or order path is reachable, and exactly-once archival is
verified for EURUSD. The undeclared `REJECTED` shipped state is reported per symbol where it occurs
(the second half of D-LSMC-7).

The `1.1.2` candidate row is deliberately `NOT_APPLICABLE` on all six gates: it has no runtime, and reusing
1.1.0 evidence for a changed candidate is prohibited by this mission. Its verdict is `NOT_VERIFIED` until it is
owner-confirmed, wired into a new registered version, and independently replayed.

## 5. Lane B — first FX-side C10/C11 evidence in the repository

575 scans over 2026-07-30T00:10Z → 2026-08-03T00:00Z on the host-captured EURUSD fixture (point `1e-05`,
`HOST_CAPTURED`; windows D1 30 / H1 120 available / M5 300, cadence = every M5 close).

| Gate | Result |
|---|---|
| L1 determinism + causality | PASS 575 |
| L2 contract conformance | PASS 575 |
| L3 geometry | PASS 575 (`L3.stop_side` + `L3.stop_beyond_sweep` evaluated on the 2 opportunities that carry a stop) |
| L4 data/state | PASS 574, **FAIL 1** — and that 1 is the single `MARKET_CLOSED` scan (the relation `L4 FAIL == MARKET_CLOSED count` is asserted by the lane, so an evaluable scan cannot fail a blocking gate unnoticed) |
| L5 cost | WARN 575 (`OD1011-L5`) |
| L6 freshness fields | PASS 575 |

States (shipped): `DEVELOPING` 396, `NEAR_POI` 139, `REJECTED` 34, `IDLE` 5, `MARKET_CLOSED` 1.
Delivery rejections: `REJECT_NO_STOP` 16, `REJECT_NO_TARGET` 7, `REJECT_STALE` 11 — the last one is an
environment fact (no host threshold off-host), not a rule failure.

Three distinct opportunities, all on H1 FVG POIs, all on 2026-07-31:

| CHoCH (UTC) | Dir | Entry | Sweep extreme | C10 stop | C11 target | Delivered |
|---|---|---|---|---|---|---|
| 08:45 | LONG | 1.15141 | 1.15053 | **1.15038** | **1.15243** (`C11_FALLBACK_M5_SWING_CAUSAL`) | `REJECT_STALE` (11 scans) |
| 20:20 | LONG | 1.15368 | 1.15233 | **1.15218** | none — `REJECT_NO_TARGET` (7 scans) | `REJECT_NO_TARGET` |
| 13:35 | SHORT | 1.14580 | 1.15007 | none — `MISSING_SPREAD` | none — `REJECT_NO_TARGET` (16 scans) | `REJECT_NO_STOP` |

Both computed stops sit exactly 1.5 pips (`0.00015`) beyond the sweep extreme, i.e. the C10 hard floor
`MIN_BUFFER_PIPS × PIP_SIZE_EURUSD` bound the `0.35 × ATR14(M5)` term — the policy's
`DYNAMIC_ATR_WITH_HARD_FLOOR` behaving as signed, with the stop on the loss side of entry and at/beyond the
sweep. The SHORT row is the fail-closed side of the same policy: a SHORT stop needs a verified live spread, the
fixture bars carry none, so the stop is `None` with a reason rather than a guessed number.

### 5.1 Positive-risk geometry (Phase C)

`positive_risk_geometry`, in the lane-B block of the machine report, measures entry/stop/target as *distances*
rather than as levels: risk `|entry − stop|`, reward `|target − entry|`, `RR = reward / risk`, in price and in
pips (pip `0.0001`, owner-evidenced; C10 hard floor `1.5` pips).

| Opportunity (CHoCH UTC / dir) | Evaluable | Risk | Reward | RR | Meets candidate `minimum_rr: 2.0` | Delivered |
|---|---|---|---|---|---|---|
|  LONG | yes | 10.3 pips | 10.2 pips | **0.990291** | **no** | `REJECT_STALE` |
|  LONG | no — `REJECT_NO_TARGET` | — | — | — | n/a | `REJECT_NO_TARGET` |
|  SHORT | no — `MISSING_SPREAD` | — | — | — | n/a | `REJECT_NO_STOP` |

Verdict **PASS** on 7/7 computed rows:

| Row | Result |
|---|---|
| `at_least_one_opportunity_was_evaluable` | ✔ |
| `every_evaluable_opportunity_has_positive_risk_and_reward` | ✔ |
| `no_level_was_invented_for_a_non_evaluable_opportunity` | ✔ |
| `non_evaluable_opportunities_carry_the_engine_reason` | ✔ |
| `reward_risk_is_measured_for_every_evaluable_opportunity` | ✔ |
| `stop_and_target_are_on_the_correct_side_of_entry` | ✔ |
| `stop_respects_the_c10_hard_floor_beyond_the_sweep` | ✔ |

The single fully-costed opportunity has RR **0.990291** — 10.3 pips of
risk against 10.2 pips of reward. The frozen 1.1.0 contract declares **no** reward/risk
minimum, so nothing fails and no gate was added; the `minimum_rr: 2.0` proposed by the 1.1.1/1.1.2 candidate
(`PENDING_OWNER_CONFIRM`) would reject it. That is measured and reported, not gated: gating it would change a
frozen rule. It is also the only FX opportunity in this repository carrying all three levels, so the owner's RR
decision currently rests on a single observation — which is itself worth recording (§9).

## 6. Lane C — bounded crypto replay and re-derivation of the committed C16 evidence

Scope: the first 120 full-D1-window scans per symbol (2026-09-08T21:00Z → 2026-09-09T06:55Z), **not** a re-run
of the 60-day replays.

- **BTCUSD**: 120 scans, `DEVELOPING` 102 / `NEAR_POI` 18, **0 opportunities** → L2's six opportunity rules
  NOT_APPLICABLE on all 120 (reported as a real coverage gap for this window, not hidden behind the gate PASS).
- **ETHUSD**: 120 scans, 13 opportunities → every one `C10_PIP_SIZE_NOT_EVIDENCED`, targets computed on all 13,
  `L3.entry_in_choch_bar` / `L3.sweep_extreme_side` / `L3.target_direction` PASS 13, delivered
  `REJECT_NO_STOP` 13, `never_exercised_checks: []`. The fail-closed crypto path reproduces exactly.
- **Committed C16 re-derivation** (16 boolean checks per symbol plus the artifact sha256, all pass): artifact sha256, contract sha256 vs tree,
  engine sha256 vs tree, per-file engine shas vs tree, the registry pin still differing, all six dataset file
  shas, the capture-report sha, dataset bar counts vs the CSVs, and the report's internal arithmetic (signal and
  operational state counts summing to 8,961; opportunity scans equalling operational rejections; gate counts
  summing to the full-D1 scan count; opportunity items matching `distinct` and summing across the short-D1 lane;
  `by_direction` summing to `distinct`; the scans split being exhaustive; verdict `NOT_VERIFIED`).

## 7. What this PR changes, and what it does not

Changed (verification layer and evidence only):

1. `src/v1_tickets/lsmc_logic_gate.py` — signal lane, `L2.delivery_gate_preserves_detection`, split point-source
   checks, `registry_identity()`, `check_coverage()` (+ `STRUCTURAL_NA_MARKERS`), report fields
   `lane_semantics` / `opportunity_symbols_covered` / `operational_opportunity_symbols` /
   `c10_stop_price_symbols`.
2. `tests/fixtures/large_smc_v111/EURUSD.json` + `manifest.json` — one timestamp field and its pin (bars untouched).
3. `tests/_lsmc_v111_fixtures.py` — `decision_time_utc()` / `check_decision_time()` fail-closed guard.
4. `tests/test_lsmc_v111_candidate_audit.py` — EURUSD expectations corrected, with the weekend/Sunday error in
   the old comment fixed.
5. `strategies/registry.yaml` — `detection_logic_verification.verification_basis` annotation only. The
   `engine_sha256` pin is **deliberately left stale** (D-LSMC-3, owner decision); no status, authority or
   identity field was touched.
6. `scripts/lsmc_v110_logic_audit.py` (new; four lanes, eleven property checks, the scope matrix and the
   Phase B classification) + the three artifacts above. The `lsmc_v111_candidate_audit.json` artifact is
   re-captured as the producer's JSON payload only (the previous capture of that path was not valid JSON).
7. `docs/status/c16_2026-10-12/C16_DEFECT_REGISTER.md` — five new entries appended; existing entries unchanged.
8. `strategies/ST_LARGE_SMC_V1_1_1_2.yaml` (new) — specification-only candidate carrying the D-LSMC-6
   rule-change diff (§3.2). Not registered, not active, not wired, all authority flags `false`.
9. `tests/test_lsmc_v110_logic_audit.py` (new, 14 tests) — binds the committed report to the tree's frozen
   identities, re-derives the committed C16 artifacts, reproduces the POI-age divergence and the declared
   trading-day rule, and re-checks every sha256 this document cites.

No gate was weakened and no emission was suppressed to obtain any result in this report; §3.1 computes that
claim row by row instead of asserting it.

Not changed: `src/large_smc_watch/**`, `src/large_smc_core/**`, `src/fx_discovery/features.py`,
`strategies/ST_LARGE_SMC_V1_1_1_0.yaml`, `strategies/ST_LARGE_SMC_V1_1_1_1.yaml`,
`docs/specs/LSMC_SPEC_V*_FROZEN.md`,
`research_external/oracles/runs/AGP_4H_C_EURUSD_DETECTION.json`, the two committed C16 replay artifacts, the
C15/C16 status documents, and every registry/READY/demo/live/authority surface.

Generated files: `status/facts.json` exposes only `id`/`version`/`demo_authorized`/`logic_verified`/
`edge_verified` per strategy, so the registry annotation is **fingerprint-only** drift
(`REGEN_REQUIRED_AFTER_MERGE`, a warning, not a failure) for `PROJECT_STATUS.md`,
`docs/status/PROJECT_LIVE_STATUS.md` and `docs/agents/CONTEXT_PACK.md`.

## 8. Reproduce

```sh
# The whole audit: 50 s, 120 MB peak, byte-reproducible (resource class R1)
python scripts/lsmc_v110_logic_audit.py \
  --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_audit.json

# Lane A on its own (exit 0 = LOGIC_VERIFIED)
python scripts/lsmc_v110_logic_verification.py \
  --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_verification_18case.json

# v1.1.1 candidate rows: capture the JSON payload only (the script also prints a markdown
# summary table to stdout and smartmoneyconcepts prints a banner to stderr)
python scripts/audit_lsmc_v111_candidate.py 2>/dev/null | awk '/^JSON:$/{f=1;next} f' \
  > artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v111_candidate_audit.json

# Reproducibility (Phase A.8): run the whole audit twice and compare bytes.
# All three runs took ~50 s and were byte-identical (sha256 49aecfba…a4742 each, `cmp` clean).
python scripts/lsmc_v110_logic_audit.py --out /tmp/lsmc_audit_run2.json
cmp artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_audit.json \
    /tmp/lsmc_audit_run2.json && echo BYTE-IDENTICAL

# Tests touched by this PR
pytest -q tests/test_lsmc_v110_logic_audit.py                                          # 14 passed
pytest -q tests/test_lsmc_v110_logic_gate.py tests/test_lsmc_v111_candidate_audit.py   # 17 passed
pytest -q tests/test_agp_4h_c_detection.py                                             # 9 passed
```

The 18-case artifact carries one wall-clock field of its own (`generated_at_utc`, emitted by the shipped
`scripts/lsmc_v110_logic_verification.py`, which this PR does not modify). A fresh run of that script is
byte-identical to the committed artifact apart from that single field — verified by a structural diff, one
changed key, no semantic difference. The audit report itself has no wall-clock field anywhere and is
byte-reproducible.

Useful flags: `--skip-crypto` (drop lane C), `--crypto-scans N` (bounded full-D1 scans per crypto symbol,
default 120), `--lane-b-every N` (evaluate every Nth M5 close in lane B).

## 9. Open items (owner decisions, not verification actions)

1. **D-LSMC-6** — trading days vs calendar dates for POI max age. A prepared candidate exists
   (`strategies/ST_LARGE_SMC_V1_1_1_2.yaml`, §3.2): confirm `max_age_unit: DISTINCT_NY1700_TRADING_DATES`
   (number unchanged at 5), or restate the declared unit to calendar boundaries. Either way the engine change
   ships as a new registered version with a fresh L1–L6 replay. FX-only impact, conservative direction
   (the frozen engine expires POIs early).
2. **D-LSMC-1** — evidenced C10 pip/stop geometry for USDJPY, XAUUSD, BTCUSD, ETHUSD (a contract input, not a
   code change). Until then those four cannot emit a deliverable opportunity.
3. **D-LSMC-3** — re-record the engine identity for the delivery-gate engine, or move the gate back to the
   post-signal layer.
4. **D-LSMC-7 (second half)** — declare `REJECTED` in `alerts.mapping`, or remove the state.
5. **D-LSMC-5** — bound spread/commission evidence and add a cost gate to the alert path.
6. **D-LSMC-10** — lazy re-exports in `supply_demand/__init__.py` and `market_structure/__init__.py` so the
   alert engine is importable without the MT5 package.
7. **D-LSMC-9** — when the 60-day crypto replays are next re-run (out of scope for this audit-only mission),
   record `check_coverage` and C10 stop geometry in the artifacts so a headline PASS can be read as coverage.
8. **Scope evidence for GBPUSD, USDJPY and XAUUSD** — these three have fixture-only evidence in this
   repository. A host capture or a recorded dataset is needed before their scope verdicts can be stronger than
   `NOT_VERIFIED` (§4).
9. **Reward/risk minimum** — the frozen 1.1.0 contract declares none. The only fully-costed FX opportunity in
   the repository measures RR `0.99` (§5.1), so the `minimum_rr: 2.0` proposed in the 1.1.1/1.1.2 candidate
   would reject it. Confirm, restate or drop that proposal; either way the decision rests on one observation
   until more FX-side opportunities are captured.

OSS-FIRST: the audit driver reuses the shipped harness, gate, engine, tracker, fixture loaders and
`v1_tickets.code_identity` unchanged (REUSED); it adds one new off-host analysis script and no trading,
indicator or rule logic; `smartmoneyconcepts` is reached only through the repository's existing adapters, and
no third-party package was added for this mission.

C21 R2 historical-input note (2026-10-14): the 1.1.2 candidate cited above is the pre-D2
specification, preserved byte-for-byte at `tests/fixtures/c21/v112_pre_d2.yaml` with SHA-256
`5931b616f2048dd20c79bc2938ebd71a77b133c5b51b2c2d986664044b58d52f`. The default 1.1.0
audit retains that input and its original output. `--version 1.1.2` reads the current amended
candidate; [C21 registration proposal](../proposals/C21_LSMC_V112_REGISTRATION.md) records
its separate evidence. The historical C15 findings and authority remain unchanged.
