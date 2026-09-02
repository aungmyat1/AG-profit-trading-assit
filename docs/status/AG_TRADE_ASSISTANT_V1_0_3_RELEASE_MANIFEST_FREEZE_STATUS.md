# AG_TRADE_ASSISTANT_V1_0_3 -- Release Manifest Freeze Status (2026-09-03)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Records the
manifest-freeze milestone for `AG_TRADE_ASSISTANT_V1_0_3`. This is a
documentation/configuration-freeze milestone only -- no strategy, execution, or
runtime source code was changed.

**Amendment (same day, 2026-09-03):** the manifest as first written did not yet reflect
three owner decisions that arrived in a follow-up instruction: (1) credential rotation
OWNER_CONFIRMED_COMPLETE for Binance/MEXC/Bybit, (2) BTC production market-data
authority FROZEN_BY_OWNER as **Bybit** (previously the manifest only described Binance,
which is not the frozen authority), and (3) Large-SMC C10's conceptual stop model
FROZEN_BY_OWNER as **AG_NATIVE_INVALIDATION** (previously recorded only as
`UNSIGNED_BLOCKED` with no owner decision). This amendment pass corrected
`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` in place (targeted edits, not a
rewrite) and updated this document to match. `status` remains `RELEASE_CANDIDATE`;
nothing below was promoted to `RELEASED`; no strategy/execution/risk semantics changed;
C10's runtime behavior (engine fails closed to `BLOCKED`) is unchanged -- only the
recorded owner decision changed, not the implementation.

## Baseline

- `git_head` (start of this milestone): `be5d31a54633173f7a9f1ad5710b46e5188c691d`
- Branch: `main`, upstream `origin/main`, 0 ahead / 0 behind at start.
- **Anomaly during this milestone:** an out-of-band commit
  (`506d8b57469cc8825ecc926e50b67c043d8ba88a`, "Add comprehensive tests for crypto
  execution modules") appeared as the new `HEAD` partway through this task. This
  session never ran `git commit`. This is the same class of environment behavior
  already disclosed in
  `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md` ("something in
  this environment... committed both sessions' work together"). The commit captured
  exactly the pre-existing untracked/modified files listed below (crypto execution
  scaffolding, `scripts/scheduled/`, the security status doc, and the pre-existing
  edit state of `PROJECT_STATUS.md`/`docs/VERSION_HISTORY.md` from *before* this
  milestone's own edits -- this task's edits to those two files remained uncommitted
  working-tree changes on top, confirmed via `git show 506d8b5:<path>`, which does not
  contain this milestone's added text). Diffed `be5d31a` against `506d8b5` restricted
  to `strategies/`, `config/pilot/`, `config/releases/` -- empty, confirming none of
  this manifest's evidentiary sources were altered. `git_head` is therefore reported as
  `be5d31a` (the actual baseline this manifest was built and verified against); current
  repository `HEAD` is `506d8b5` due to this external event, not a value this task chose
  or authorized.
- Working tree at start contained pre-existing, unrelated changes (not touched by this
  milestone): modified `PROJECT_STATUS.md`, `docs/VERSION_HISTORY.md`,
  `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`; untracked
  `docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md`,
  `scripts/scheduled/`, and nine untracked `src/execution/crypto_*.py` /
  `tests/test_crypto_*.py` files (crypto execution scaffolding, unrelated to this
  release-manifest task). `docs/VERSION_HISTORY.md` and `PROJECT_STATUS.md` were
  already modified before this milestone (pre-existing edits already anticipated a
  V1.0.3 manifest); this milestone made further, additive edits on top of that
  pre-existing state -- see FILES CHANGED below for exactly what this milestone added.

## Manifest

- Path: `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` (new file, created by this
  milestone).
- `release_id: AG_TRADE_ASSISTANT_V1_0_3`, `status: RELEASE_CANDIDATE`,
  `supersedes: AG_TRADE_ASSISTANT_V1_0_2`.
- Validated by: (1) `yaml.safe_load` parse plus assertions on every required top-level
  field/invariant; (2) the project's own `src/post_asian_pilot/pilot_config.py`
  `load_raw_yaml()` loader, which loads it without error. No stricter schema/loader
  exists in this repository for `config/releases/*.yaml` beyond plain YAML parsing --
  `preflight.py`'s `release_id` string-equality check remains hardcoded to
  `AG_TRADE_ASSISTANT_V1_0_2` and was intentionally left unchanged, since V1.0.2
  remains the current documented/operational release.

## Authority verified

- FX strategy: `ST_ASIAN_SWEEP_5R_V1` v1.1.1 (`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`,
  `strategies/registry.yaml`).
- `ASIAN_LONDON` cycle owner: `ST_ASIAN_SWEEP_5R_V1` v1.1.1 -- verified against
  `config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml` (`strategy_id`,
  `strategy_version` fields, not inferred from filename).
- `LONDON_NEWYORK` cycle owner: `ST_ASIAN_SWEEP_5R_V1` v1.1.1 -- verified against
  `config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml` (`strategy_id`,
  `strategy_version` fields, not inferred from filename).
- Explicitly checked for, and ruled out, the naming trap `strategies/STRATEGY_LEDGER.md`
  itself warns about (line 84): `SESSION_TRADE_V1` (a separate, independently-signed
  strategy in `D:\ddev\Session Trade Codex`) also uses an `ASIAN_LONDON`/
  `LONDON_NEWYORK` cycle-naming convention with its own, different magic numbers
  (123456/123457) and its own execution authority. No rule, authority, or evidence was
  borrowed from `SESSION_TRADE_V1`; the manifest's `fx_cycles` block references only
  `ST_ASIAN_SWEEP_5R_V1`'s own pilot config paths and strategy IDs.
- State/ledger isolation verified: `ASIAN_LONDON` -> `journal/post_asian_pilot`
  (`src/post_asian_pilot/store.py::DEFAULT_STATE_DIR`, implicit default);
  `LONDON_NEWYORK` -> `journal/post_london_newyork_pilot` (explicit `state_dir` in its
  pilot config). Both isolated per `DailyTradeLedger` (keyed `strategy_id+date`,
  per-process/per-state_dir) -- existing, tested behavior, not redesigned here.
- BTC strategy: `ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0, `ACTIVE_INCUBATION`
  (`strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml`). `execution_domain=CRYPTO_RESEARCH`,
  `execution_authority=DISABLED`; `execution.adapter.CryptoExecutionAdapter` remains
  `NOT_IMPLEMENTED`.
- BTC market-data authority: **Bybit**, `FROZEN_BY_OWNER` (2026-09-03) -- distinct from
  strategy authority and execution authority (see manifest's `btc_market_data_authority`
  block). Bybit's public market-data endpoint returned **HTTP 403** (explicit
  CloudFront country-block) when tested from this development environment on
  2026-09-03, the same class of restriction already recorded for Binance production
  (HTTP 451, `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md` Gap
  6). Both are environment constraints, not unresolved source-selection decisions --
  source selection is frozen. No circumvention attempted. The Bybit adapter itself is
  `NOT_IMPLEMENTED` (next milestone: `AG_BYBIT_BTC_MARKET_DATA_V1`), not built by this
  task.
- Large-SMC strategy: `ST_LARGE_SMC_V1` v1.0.6, `RESEARCH_DRAFT`
  (`strategies/ST_LARGE_SMC_V1.yaml`, `strategies/registry.yaml`). C10's conceptual
  stop model is now owner-decided as **AG_NATIVE_INVALIDATION** (2026-09-03; structural
  stop source = the already-frozen `invalidation_price` field, plus a not-yet-specified
  buffer/minimum-distance constraint) -- recorded in the manifest as a decision only.
  Implementation, contract freeze, and lifecycle simulation are all `PENDING`/
  `NOT_STARTED`; the engine's own runtime behavior is unchanged and still fails closed
  to `BLOCKED`. `proposal_generation_authorized`, `demo_authorized`, and
  `live_authorized` all remain `false`. Not implemented, not resolved, not rerun.

## Scope

- `capabilities_pinned = YES` -- application authority matrix pinned using existing
  project vocabulary (`AVAILABLE`, `PROPOSAL_ONLY`, `DISABLED`, `NOT_IMPLEMENTED`,
  `RESEARCH_ONLY`, etc.).
- `new_capabilities_added = NO`
- `strategy_semantics_changed = NO`
- `strategy_versions_changed = NO`
- `risk_semantics_changed = NO`
- `session_semantics_changed = NO`

## Validation

- `manifest_loader`: PASS (`load_raw_yaml`, project loader).
- `schema_validation`: PASS (plain YAML parse + key-invariant assertions; no stricter
  schema exists in-repo for release manifests).
- `authority_invariant_tests`: `tests/test_post_asian_pilot.py` and
  `tests/test_post_london_newyork_pilot.py`, filtered `-k "release or preflight or
  fingerprint"` -- 4 passed, 62 deselected. These exercise the existing V1.0.2-pinned
  preflight/fingerprint machinery and were unaffected by adding a new, separate V1.0.3
  manifest file.
- `focused_tests`: as above; no new tests were added (no source/loader code changed).
- `full_regression_status`: `FULL_REGRESSION_NOT_RERUN`. This milestone changed only
  YAML/Markdown files (one new release manifest, edits to `docs/VERSION_HISTORY.md`,
  `PROJECT_STATUS.md`, and this new status document). No `.py` source file was changed.
  Reused evidence: **1356 passed / 1 skipped / 0 failed**, tested baseline
  `f7d7eaf..be5d31a` (`AG_COMPLETE_TRADE_OPPORTUNITY_V1` remediation pass, recorded
  2026-09-02/03), which matches this milestone's own unchanged `git_head` = `be5d31a`.
  See `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`.
- `git_diff_check`: clean (`git diff --check`; only pre-existing CRLF warnings elsewhere
  in the repo, none newly introduced by this milestone).
- `documentation_consistency`: verified -- V1.0.2 remains "current documented release"
  everywhere it is stated; V1.0.3 is stated as `RELEASE_CANDIDATE` (never `RELEASED`)
  in `docs/VERSION_HISTORY.md`, `PROJECT_STATUS.md`, and the new manifest; FX/BTC/
  Large-SMC authority statements agree across all three; the manifest path is now
  referenced (previously "Manifest pending") in `docs/VERSION_HISTORY.md`'s release
  table and required-upgrades section.

## Release gates (recorded, not completed by this milestone)

```text
FX_preflight                          = NOT_RUN
FX_shadow_days_completed              = 0 / 20
FX_duplicate_status                   = NOT_YET_COLLECTED
FX_cross_cycle_isolation              = VERIFIED_BY_DESIGN (state_dir separation); NOT_YET_OPERATIONALLY_VALIDATED
BTC_source_decision                   = FROZEN_BY_OWNER (Bybit, 2026-09-03)
BTC_production_data_available         = NO (Bybit HTTP 403 / Binance HTTP 451 -- environment
                                          constraint, both recorded 2026-09-02/03, not an
                                          unresolved source-selection decision)
BTC_bybit_adapter                     = NOT_IMPLEMENTED (next milestone)
BTC_observation_days_completed        = 0 / 30
BTC_testnet_excluded_from_evidence    = YES
credential_rotation                   = OWNER_CONFIRMED_COMPLETE (Binance, MEXC, Bybit;
                                          2026-09-03) -- confirmation only, not
                                          independently re-verified by any agent call
withdrawal_permission_removed         = UNRESOLVED
ip_restriction_status                 = UNRESOLVED
Large_SMC_C10_owner_decision           = AG_NATIVE_INVALIDATION (2026-09-03, conceptual
                                          model only)
Large_SMC_C10_implementation           = PENDING / engine remains UNSIGNED_BLOCKED at runtime
unresolved_blockers                   = none that block manifest freeze; all listed
                                          items are RELEASED-gate items, not
                                          RELEASE_CANDIDATE-gate items
```

Incomplete FX shadow evidence (0/20) and incomplete BTC observation evidence (0/30) do
not prevent manifest freeze / `RELEASE_CANDIDATE` status; they prevent promotion to
`RELEASED`. This milestone did not start FX shadow collection, BTC observation
collection, credential rotation, or any operational preflight run.

## Files changed by this milestone

- `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` (new, then amended same day with the
  three owner-decision corrections above -- targeted edits, not a rewrite)
- `docs/VERSION_HISTORY.md` (edited -- manifest path filled in, three targeted edits)
- `PROJECT_STATUS.md` (edited -- one new rolling-snapshot line, then amended for the
  same three corrections)
- `docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md` (new, this
  document, then amended same day)

## Pre-existing unrelated changes (present before this milestone, left untouched)

- Modified: `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`
- Untracked: `docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md`,
  `scripts/scheduled/`, `src/execution/crypto_client_order_id.py`,
  `src/execution/crypto_clock.py`, `src/execution/crypto_filter_refresh.py`,
  `src/execution/crypto_journal.py`, `src/execution/crypto_metadata.py`,
  `src/execution/crypto_models.py`, `src/execution/crypto_reconciliation.py`,
  `src/execution/crypto_router.py`, `src/execution/crypto_snapshot.py`, and their
  corresponding nine `tests/test_crypto_*.py` files.

## Classification

`MANIFEST_FROZEN_RELEASE_CANDIDATE`

All items in the success contract are satisfied: manifest created and valid; V1.0.3
status is `RELEASE_CANDIDATE` (not `RELEASED`); both FX cycles' strategy authority
verified explicit against pilot configuration (not filename inference); strategy
versions pinned; no authority, strategy semantics, risk semantics, session semantics,
or execution gates changed; no new feature added; scope freeze recorded; shadow/BTC/
security/Large-SMC requirements recorded (not completed); documentation consistent;
no secrets added.

## Next authorized step

Run V1.0.3 operational preflight, then begin the separately authorized proposal-only
shadow-validation phase.
