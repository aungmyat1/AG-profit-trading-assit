---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-C17-LSMC-LOGIC-COMPLETION-R1 — delivery record (2026-10-13)

Owner-issued mission: finish the independent logic audit of Large-SMC v1.1.0, classify and resolve its
defects, verify L1–L6 independently for every supported scope, and deliver the evidence.

Constraints honoured throughout: read-only research and replay; **no `order_check`, no `order_send`, no
broker mutation, no demo or live activation**; `ST_LARGE_SMC_V1` stays `ARCHIVE_ONLY` with
`proposal_generation_authorized` / `demo_authorized` / `live_authorized` all `false` and
`economic_status: NOT_EVALUATED`; unverified scopes stay `REPORT_ONLY` or stricter; frozen v1.1.0 and its
historical verdict are preserved; no gate was weakened and no emission suppressed to obtain a result.

Primary documents:

- Audit report — `docs/status/AGP_C15_LSMC_V110_LOGIC_AUDIT_2026-10-13.md` (keeps its C15-follow-up
  filename because `strategies/registry.yaml` cites that path).
- Machine report — `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_audit.json`.
- Defect index — `docs/status/c16_2026-10-12/C16_DEFECT_REGISTER.md` (extended, never rewritten).
- Candidate prepared for D-LSMC-6 — `strategies/ST_LARGE_SMC_V1_1_1_2.yaml`.
- Regression tests — `tests/test_lsmc_v110_logic_audit.py`.

## Phase D — delivery summary

| Item | Value |
|---|---|
| Branch | `arena/b50fb2fa-ag-profit-trading-assit` → `main` |
| Pull request | PENDING_DELIVERY_COMMIT |
| Delivery commit (HEAD when the PR was opened) | PENDING_DELIVERY_COMMIT |
| Strategy version audited | `ST_LARGE_SMC_V1@1.1.0` — frozen; **no contract or engine byte edited** |
| Contract SHA-256 | `78285f9fabcb20af14de327d010e48684dc12205f4435eff886fcc2373a357b4` (= the registry pin) |
| Engine SHA-256 (`src/large_smc_watch/`) | `88dd9f1fb970f7811b437cb3b4c7341e0d1f84320238890eab3381eb0f51b689` |
| Registry engine pin | `ec0b2f3dc6ed2b02df3f643b38beac1c0e88630413c74e0f55e3d8aa5f5570d4` — differs (**D-LSMC-3**, drift isolated to `watch.py`, left stale on purpose) |
| Candidate contract (new) | `strategies/ST_LARGE_SMC_V1_1_1_2.yaml` `5931b616f2048dd20c79bc2938ebd71a77b133c5b51b2c2d986664044b58d52f` — `SPEC_ONLY_NOT_WIRED`, `CANDIDATE_PENDING_OWNER_CONFIRM`, not registered |
| Machine report SHA-256 | `49aecfba08366bb59c98b589bc298076c6c6ba3da7db0fdb304fa95ce03a4742` — byte-identical across **three** full runs |
| Audit verdict | **`NOT_VERIFIED`** (2 blocking findings: D-LSMC-6, D-LSMC-1) |
| Shipped 18-case harness scope | **`LOGIC_VERIFIED`** — rule conformance and internal consistency only, after the harness repair |
| Per-symbol scope verdicts | **`NOT_VERIFIED` for all six instruments**; `logic_verified_scopes: []` |
| Candidate 1.1.2 scope verdict | **`NOT_VERIFIED`** — no runtime; 1.1.0 evidence is not reusable for it |
| Resource class | **R1** — 50.0 s wall, 119.5 MB peak RSS, single process, no competing job |

### Dataset identities

| Dataset | Path | Identity |
|---|---|---|
| FX fixture set (6 symbols) | `tests/fixtures/large_smc_v111/manifest.json` | decision time `2026-08-03T00:00:00Z`; every per-file pin recomputed from the bytes (`manifest_pins_match_files: true`) |
| EURUSD fixture (corrected, D-LSMC-8) | `tests/fixtures/large_smc_v111/EURUSD.json` | `2ce91ea1c0eecf2debda0bd6bfb34e37d0f49cd66ccbb00ed199f7f78da6425d`; D1 30 / H1 120 / M5 604 bars; bars untouched, one timestamp field fixed |
| FX H1 export (lanes A/D, POI age) | `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_001/raw/EURUSD_H1.csv` | `63d8227541909adff009f121e7b3ed1cb4e12c718aaeea53b8e55426917bb55c`; dataset manifest `cc87303fe36369c3db8c4787d38d6315410cebaa01984245f82caa41959c9d96` |
| BTCUSD recorded 60d | `tests/fixtures/ccfd_v100/recorded_60d/BTCUSD_{d1,h1,m5}.csv` (+ `_meta`) | D1 `85110e81…6559`, H1 `f1d7ba4b…3127`, M5 `60a9b5a4…05bb`; 60/1412/16932 bars; 2026-08-11 → 2026-10-09; server `VTMarkets-Demo`; capture report `2d59d235…5ef8` |
| ETHUSD recorded 60d | `tests/fixtures/ccfd_v100/recorded_60d/ETHUSD_{d1,h1,m5}.csv` (+ `_meta`) | D1 `72734a14…1fec`, H1 `4159be1d…8aeb`, M5 `7ad85602…5561`; same bar counts, window, server and capture report |
| Symbol metadata | `config/symbol_metadata/host_captured/*.json` | all six points `HOST_CAPTURED`; pip evidenced for EURUSD/GBPUSD only (`contract.C10_PIP_SIZE`) |

Every crypto file hash above is re-verified against the CSVs by `verify_committed_c16`
(`dataset_sha256_matches_files`, `dataset_bar_counts_match_files`, `capture_report_sha256_matches_file`),
together with the committed artifact's own sha256 — 17 boolean re-derivation checks per symbol, all passing.
The 60-day replays themselves were **not** re-run (owner scope decision `audit_only`).

### Tests, checks and CI

| Check | Result |
|---|---|
| `pytest -q tests/test_lsmc_v110_logic_audit.py` (new) | **21 passed** |
| Focused LSMC + docs suite | **201 passed, 1 skipped, 1 known-environment failure** in 22.5 s (`tests/test_*lsmc*.py`, `tests/test_*large_smc*.py`, `test_agp_4h_c_detection.py`, `test_docs_live.py`, `test_context_pack.py`, `test_generated_files_ci.py`) |
| Full applicable suite (`pytest -q`, `-m "not slow"` per `pyproject.toml`) | **2,686 passed, 8 skipped, 1 failed** in 215.9 s (Python 3.11, `pyarrow` installed per `requirements.txt`); the single failure is the known environment artifact below |
| Known environment failure (1) | `tests/test_lsmc_actionability.py::test_complete_fresh_opportunity_and_sent_text_byte_exact` needs `git show 5b671996ef91934f2e8b58f9748ee78b1804a099:src/host_delivery/telegram_message.py`, which does not exist in this depth-1 squashed checkout (exit 128) — an artifact of how the workspace was delivered, not a defect. Three further failures seen on the first full run were a missing optional `pyarrow` in the local venv and disappeared once it was installed |
| `ruff check` (F, I) on every file this PR touches | **All checks passed** (`scripts/lsmc_v110_logic_audit.py`, `src/v1_tickets/lsmc_logic_gate.py`, `tests/_lsmc_v111_fixtures.py`, `tests/test_lsmc_v111_candidate_audit.py`, `tests/test_lsmc_v110_logic_audit.py`) |
| `scripts/check_docs_links.py` | `DOCS_LINK_CHECK = PASS`, 0 broken links |
| `scripts/docs/check_drift.py` | `docs-drift blocking: 0 error(s)` (2 pre-existing ADVISORY allowlist anchors, untouched by this PR) |
| `scripts/check_skill_mirror_drift.py` | `NO_DRIFT` |
| `scripts/docs/check_generated_files.py --mode strict` | PENDING_FULL_SUITE |
| GitHub Actions | PENDING_DELIVERY_COMMIT |

## Phase A — completing the audit

1. **Ruff fixes without touching unrelated files.** Four findings in the new audit driver were resolved:
   import order (`I001`), an unused local (`F841`), and two unused imports (`F401`) that were turned into a
   *real* check instead of being deleted — `archive_path_matches_the_exactly_once_guard` reconstructs
   `report_archive.archive_path(ticket_delivery.archive._report_type(...), trading_date, root)` for every
   emitted event and compares it with the paths actually archived, because a divergence there would silently
   break exactly-once delivery. Pre-existing `I001` findings in two sibling scripts were left alone: CI lints
   changed `src/**` and `tests/**` only, and fixing them would have modified unrelated files.
2. **Archive-path / exactly-once coverage finalised** (above, plus the crash-between-archive-and-state-save,
   duplicate-poll, silent-`SUSPENDED` and `MARKET_CLOSED` steps).
3. **Lightweight deterministic regression tests** — `tests/test_lsmc_v110_logic_audit.py`, 21 tests, ~6 s.
   They do not re-run the four lanes; they bind the committed report to the tree (the pattern of
   `tests/test_lsmc_c15_symbol_replay.py`), re-derive the committed C16 artifacts from their own bytes,
   reproduce the POI-age divergence, compute the declared trading-day rule independently, and re-check every
   sha256 the audit document cites.
4. **Binding to frozen identities** — the report pins the contract, the composite engine hash, all four engine
   files, both dependencies, both gate modules, the fixture manifest (decision time + per-file pins), the FX H1
   export and its dataset manifest; the tests additionally hardcode the frozen contract/engine hashes and the
   corrected EURUSD fixture hash, so editing frozen v1.1.0 fails a normal `pytest -q`.
5. **Artifact regenerated after the final code change**, then all sha256 references recomputed and reconciled:
   the audit document carries a 22-row full-hash table, and
   `test_report_doc_cites_the_hashes_of_the_files_it_cites` re-verifies it against the files (the two source
   files this PR adds are deliberately not rows there — a table that pinned its own checker could never be
   updated).
6. **Reproduction** — three consecutive full runs, `cmp`-clean, identical sha256
   `49aecfba…a4742` each time. The report has no wall-clock field, no run id and no hostname; the only
   run-dependent value is `identity.code_sha` (`git rev-parse HEAD`). The two companion artifacts reproduce
   too: the candidate rows byte-identically, and the shipped 18-case report byte-identically apart from its own
   `generated_at_utc` (emitted by `scripts/lsmc_v110_logic_verification.py`, which this PR does not modify).
   While reconciling, the `lsmc_v111_candidate_audit.json` capture was found to be **invalid JSON** (it had
   captured the producer's stderr banner and markdown summary table along with the payload) and was
   re-captured as the payload only, with the exact pipeline documented in §8 of the audit report.
7. **Reviewable PR** through the repository's normal workflow — see the delivery summary above.

## Phase B — defect resolution and classification

Full rows: `phase_b.rows` in the machine report; §3 of the audit document; the register entries carry the same
classification.

| ID | Class (mission taxonomy) | Route | Owner decision | Outcome before → after |
|---|---|---|---|---|
| `D-LSMC-6` | **IMPLEMENTATION** against a declared contract rule | new candidate `1.1.2` rule-change diff | required | declared 5 *trading* days / implemented 5 *calendar* days → candidate pins `max_age_unit: DISTINCT_NY1700_TRADING_DATES`, number unchanged, activation blocked on owner confirmation + a fresh replay |
| `D-LSMC-1` | **METADATA** (no owner-confirmed broker pip evidence) | confirm `pip_size_rules` + host capture | required | 4 of 6 instruments fail closed → unchanged; inventing a pip size is refused |
| `D-LSMC-7` | **VERIFICATION_HARNESS** | fixed in this PR | no | 541 checks / 0 opportunity rules exercised (vacuous `LOGIC_VERIFIED`) → 542 checks / all 6 opportunity rules exercised on 10 cases each, `never_exercised_checks: []`, 156 verdicts moved |
| `D-LSMC-8` | **VERIFICATION_HARNESS** (evidence fixture) | fixed in this PR | no | EURUSD fixture evaluated 68 days after its own data → all six fixtures at the manifest decision time, guarded by `check_decision_time` |
| `D-LSMC-3` | **METADATA** (repository identity record) | owner decision | required | stale registry engine pin → still stale and still reported (`engine_matches_registry: false`); prose annotation only |
| `D-LSMC-5` | **DATA** (no accepted spread/commission evidence off-host) | host evidence | required | L5 `WARN` in every lane → unchanged, never forced to `PASS` |
| `D-LSMC-9` | **VERIFICATION_HARNESS** (committed evidence lacks coverage) | recorded, no re-run | no | headline PASS with no coverage → same bytes, re-derived and qualified (`with_c10_stop: 0`; 6,921/8,961 BTCUSD and 8,113/8,961 ETHUSD full-D1 scans had every opportunity rule `NOT_APPLICABLE`) |
| `D-LSMC-10` | **VERIFICATION_HARNESS** (boundary evidence) | recorded | no | vacuous 1-module boundary scan → 48-module ast graph + runtime probe with an anti-vacuity positive control; MT5 import sites recorded |

Class counts: IMPLEMENTATION 1, METADATA 2, DATA 1, VERIFICATION_HARNESS 4.

**Frozen v1.1.0 preserved.** No byte of `strategies/ST_LARGE_SMC_V1_1_1_0.yaml`, `src/large_smc_watch/**`,
`src/large_smc_core/**`, `src/fx_discovery/features.py` or the frozen specs was edited; the historical C15/C16
verdicts and evidence files are untouched. `gate_integrity` re-hashes the frozen contract and engine on every
run and fails if they move.

**Harness defects fixed without touching trading logic.** The three fixes are in
`src/v1_tickets/lsmc_logic_gate.py` (verification layer), `tests/fixtures/large_smc_v111/EURUSD.json` +
`manifest.json` (evidence) and `tests/_lsmc_v111_fixtures.py` (guard). Each has a regression test.

**Genuine strategy defect → new candidate with an explicit rule-change diff.**
`strategies/ST_LARGE_SMC_V1_1_1_2.yaml` is bound to the committed 1.1.1 bytes it was derived from
(`based_on_sha256`), which are themselves bound to the committed 1.1.0 bytes. It changes the *unit*, not the
number, and declares its own structural diff (15 paths, 1.1.1 → 1.1.2) which
`property_checks.candidate_rule_change_diff` recomputes and compares — undeclared rule drift fails the audit.
It is `SPEC_ONLY_NOT_WIRED`, unregistered, inactive, authority-free, and its scope verdict is `NOT_VERIFIED`.

**No fix hides a failure.** `property_checks.gate_integrity` (11 rows, all computed from the run) proves: the
blocking gate set is still `(L1, L2, L3, L4)`; L5 is still emitted as `WARN` 1,779× and never as `PASS`
(invented cost evidence) or `FAIL` (a stronger gate than `OD1011-L5` signed); no declared check is
never-exercised in any lane where its rules are reachable; coverage grew rather than shrank; emissions survive
in every lane (18 / 575 / 120 / 120 shipped states); every emitted transition is archived exactly once and the
guard path that enforces it matches the archived bytes; the alert-level mapping still equals the contract's;
the fail-closed metadata paths still fail closed; and the frozen engine and contract bytes are unchanged. The
one lane where six opportunity checks are legitimately never exercised (lane C on BTCUSD, whose bounded window
contains no opportunity scan) is disclosed per lane and carried by D-LSMC-9 rather than hidden.

## Phase C — independent L1–L6 verification per supported scope

Gate meanings as implemented by `src/v1_tickets/lsmc_logic_gate.py` (blocking: L1–L4; advisory: L5, L6):

| Gate | Verifies |
|---|---|
| **L1** | contract/engine identity, closed bars only, determinism and truncation invariance (unclosed or future bars cannot change the snapshot) |
| **L2** | rule conformance: alert mapping, bias direction, entry by reference, sweep→CHoCH window, POI expiry at session end, C10 stop, C11 target, and that the delivery gate preserves detection |
| **L3** | geometry: entry inside the CHoCH bar, sweep extreme on the correct side, stop side and stop beyond the sweep, target beyond entry |
| **L4** | the snapshot is an evaluable trading instant: no `DATA_ERROR` / `MARKET_CLOSED`, minimum H1/M5 history, M5 freshness, `STALE` consistency |
| **L5** | broker metadata and trading friction — advisory (`OD1011-L5`): no accepted spread/commission evidence off-host |
| **L6** | freshness fields (`valid_until`) and delivery-layer consistency — advisory in the shipped gate, **required** in this mission's scope matrix |

Scope matrix (from `scope_matrix`; §4 of the audit document carries the same table):

| Symbol | Evidence | L1 | L2 | L3 | L4 | L5 | L6 | Blocking findings for the scope | Scope verdict |
|---|---|---|---|---|---|---|---|---|---|
| `EURUSD` | fixture harness + 575 host-captured scans | PASS | PASS | PASS | FAIL† | WARN | PASS | `D-LSMC-6` | **NOT_VERIFIED** |
| `GBPUSD` | fixture harness | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-6` | **NOT_VERIFIED** |
| `USDJPY` | fixture harness | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-6`, `D-LSMC-1` | **NOT_VERIFIED** |
| `XAUUSD` | fixture harness | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-6`, `D-LSMC-1` | **NOT_VERIFIED** |
| `BTCUSD` | fixture harness + 120 bounded scans + C16 re-derivation | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-1` | **NOT_VERIFIED** |
| `ETHUSD` | fixture harness + 120 bounded scans + C16 re-derivation | PASS | PASS | PASS | PASS | WARN | PASS | `D-LSMC-1` | **NOT_VERIFIED** |
| `1.1.2` candidate | none — `SPEC_ONLY_NOT_WIRED` | N/A | N/A | N/A | N/A | N/A | N/A | n/a | **NOT_VERIFIED** |

† EURUSD's single `L4 FAIL` is the one `MARKET_CLOSED` scan in the rolling replay: a weekend snapshot is not an
evaluable trading instant, which is what L4 asserts. The matrix does not excuse it — `required_gates_pass` is
`false` for EURUSD and the reason is recorded, so the scope fails closed on the gate as well as on D-LSMC-6.

Emissions per scope: `delivery_mode` `ARCHIVE_ONLY`; the alert-level mapping equals the contract's; the
undeclared `REJECTED` shipped state is reported where it occurs (second half of D-LSMC-7); exactly-once
archival is verified for EURUSD; no transport, order or authorization path is reachable statically
(48 repo modules) or at runtime (561 modules loaded).

Independent replay results: lane B replays the host-captured EURUSD fixture at every M5 close (575 scans,
3 distinct opportunities, 2 with real C10 stops, 1 fully costed with RR `0.99`); lane C replays the recorded
crypto datasets over a bounded 120-scan full-D1 window per symbol and re-derives the committed 60-day C16
artifacts from their own bytes; lane D recomputes detection semantics from `fx_discovery.features` primitives
(tie tolerance, breaks, sweeps, entry = CHoCH close, targets beyond entry). v1.1.0 evidence is **not** reused
for the 1.1.2 candidate, whose gates are `NOT_APPLICABLE` for lack of a runtime.

No scope is marked `LOGIC_VERIFIED`: the rule is that every required gate must pass on evidence covering that
symbol *and* no blocking finding may apply to it, and today a blocking finding applies to all six.
No scope is `EDGE_VERIFIED`; nothing here is economic evidence.

## What was deliberately not done

- The unbounded 60-day crypto replays were not re-run (owner scope decision `audit_only`); their committed
  artifacts were re-derived instead, and the coverage gap they leave is D-LSMC-9.
- No engine or frozen-contract byte was edited; the registry's stale `engine_sha256` pin was left stale
  (D-LSMC-3) rather than quietly re-pinned, because re-pinning is an owner identity decision.
- The 1.1.2 candidate was not wired, not registered, not activated, and not verified: it is a proposal.
- No pip size, spread or commission value was invented to make a gate evaluable.
- Lane C's bounded window was not enlarged to manufacture opportunity coverage for BTCUSD; the honest
  zero-opportunity result is recorded.
- **The mission is not declared complete because tests pass.** It is complete when the evidence above is
  delivered and the remaining owner/host requests below are answered; two blocking findings remain open and
  every per-symbol scope verdict is `NOT_VERIFIED`.

## OSS-FIRST check (AGENTS.md standing rule)

Search order applied per component: (a) existing repo code/registry, (b) pinned OSS already in
`requirements.txt`, (c) maintained OSS, (d) new code only if none fit. **No new dependency was added to the
repository**, no OSS code path imports a broker or order module, and no OSS result is treated as authority.

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| L1–L6 logic gate | `src/v1_tickets/lsmc_logic_gate.py` + `src/v1_tickets/logic_gate.py` (repo) | REUSED | the repository's signed gate; the audit calls it as-is (the only edits are the D-LSMC-7/8 harness repairs) |
| 18-case fixture harness | `scripts/lsmc_v110_logic_verification.py` (repo) | REUSED | case list unchanged; audited in-process and re-derived |
| SMC primitives (swings, sweeps, FVG/OB, breaks) | `smartmoneyconcepts==0.0.27` through `src/fx_discovery/features.py` (pinned OSS) | WRAPPED | OSS stays ORACLE/REFERENCE; the engine's own causal primitives are authority, and divergence is documented rather than adopted |
| C10 stop policy | `src/large_smc_core/c10_stop_policy.py` (repo, signed) | REUSED | no reimplementation; the audit only measures its output geometry |
| Exactly-once alert archive | `src/post_asian_pilot/report_archive.py`, `src/ticket_delivery/archive.py` (repo) | REUSED | the audit reconstructs the real guard path from these modules instead of duplicating it |
| Import-boundary analysis | stdlib `ast` vs `pydeps` / `grimp` / `importlib-metadata` | REJECTED (stdlib) | no new dependency, no license or egress surface; an ast graph over 48 repo modules plus a runtime probe with an anti-vacuity positive control is sufficient |
| Lint | `ruff` (repo tooling, `F` + `I`) | REUSED | CI's own linter; fixes confined to files this PR touches |
| Parquet engine for the full suite | `pyarrow` (already in `requirements.txt`) | REUSED | installed into the local venv only, so three parquet tests run instead of erroring on a missing optional dependency |
| Replay/backtest engine for lanes B and C | `backtesting.py`, `vectorbt`, `ccxt` | REJECTED | the lanes must replay *this* engine over committed recorded fixtures; an external engine would replace the system under test and could not verify the frozen contract |
| Market data | Dukascopy / HistData / exchange CSVs | REJECTED | provenance: only committed host-captured (`VTMarkets-Demo`) and repo fixtures are admissible evidence for this contract; external data would need `source=EXTERNAL:<name>` and a separate cohort |

## Remaining owner and host requests

1. **D-LSMC-6** — confirm `max_age_unit: DISTINCT_NY1700_TRADING_DATES` in candidate 1.1.2 (number stays 5),
   or restate the declared unit to calendar boundaries. Either way the engine change ships as a new registered
   version with a fresh L1–L6 replay on real FX H1 data.
2. **D-LSMC-1** — confirm the `pip_size_rules` proposals (FX `10 × host_captured_point`, XAUUSD `0.1`,
   BTCUSD `1.0`, ETHUSD `0.1`) or supply host captures for USDJPY, XAUUSD, BTCUSD and ETHUSD. Until then those
   four cannot emit a deliverable opportunity.
3. **D-LSMC-3** — re-record the engine identity for the delivery-gate engine, or move the gate back to the
   post-signal layer.
4. **D-LSMC-7 (second half)** — declare `REJECTED` in `alerts.mapping`, or remove the state.
5. **D-LSMC-5** — bound spread/commission evidence and add a cost gate to the alert path (L5 is advisory today).
6. **D-LSMC-9** — on the next 60-day crypto re-run, record `check_coverage` and C10 stop geometry in the
   artifacts so a headline PASS can be read as coverage.
7. **D-LSMC-10** — lazy re-exports in `supply_demand/__init__.py` and `market_structure/__init__.py` so the
   alert engine is importable without the MT5 package.
8. **Scope evidence for GBPUSD, USDJPY and XAUUSD** — fixture-only today; a host capture or recorded dataset is
   needed before their scope verdicts can strengthen.
9. **Reward/risk minimum** — 1.1.0 declares none; the only fully-costed FX opportunity in the repository
   measures RR `0.99`, so the candidate's proposed `minimum_rr: 2.0` would reject it. Confirm, restate or drop.
10. **Host/CI** — the depth-1 squashed checkout cannot satisfy
    `tests/test_lsmc_actionability.py::test_complete_fresh_opportunity_and_sent_text_byte_exact`
    (it needs `git show 5b671996…`); a full-history checkout or an owner waiver is required for that one test.
