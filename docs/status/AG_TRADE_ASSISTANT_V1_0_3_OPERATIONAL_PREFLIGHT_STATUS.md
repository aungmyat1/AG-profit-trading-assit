# AG_TRADE_ASSISTANT_V1_0_3 -- Operational Preflight Status (2026-09-03)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Determines
whether the frozen `AG_TRADE_ASSISTANT_V1_0_3` release candidate
(`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`) is operationally ready to enter the
separately authorized proposal-only FX shadow-validation phase. Does not promote
V1.0.3 to `RELEASED`, does not start shadow/observation collection, does not authorize
execution, and does not change strategy semantics.

## Baseline

- `manifest_freeze_head`: `be5d31a54633173f7a9f1ad5710b46e5188c691d` (recorded in
  `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s `source_baseline.git_head`).
- `current_git_head` (start of this milestone): `506d8b57469cc8825ecc926e50b67c043d8ba88a`.
- `branch`: main, `upstream`: origin/main, `origin_main_relationship`: 0 ahead / 0
  behind.
- `head_changed_since_manifest_freeze`: YES (documented anomaly, already disclosed in
  `docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md` -- an
  out-of-band commit, not made by any task/session directly, captured pre-existing
  crypto-execution scaffolding files).
- `relevant_head_delta`: independently re-verified this milestone (not solely reusing
  the prior task's own statement): `git diff --stat be5d31a 506d8b5 -- strategies/
  config/pilot/ config/releases/ src/post_asian_pilot/ src/execution/executor.py
  src/execution/coordinator.py config/trading.yaml src/session_clock.py` -- **empty**.
  None of the release manifest loading path, FX proposal runtimes, pilot
  configuration, strategy files, execution-boundary code, safety-gate config, or
  session-clock code changed between the two commits.
- `working_tree_before`: `PROJECT_STATUS.md`, `docs/VERSION_HISTORY.md`,
  `docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md` modified;
  `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` and
  `docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md` untracked.
  Also observed: the manifest and the two status/summary files had already been
  amended externally (not by this task) between the manifest-freeze milestone and
  this one, recording three new owner decisions dated 2026-09-03 (credential
  rotation, BTC market-data authority = Bybit, Large-SMC C10 conceptual model =
  AG_NATIVE_INVALIDATION). Treated as current state, not reverted, per instruction.
- `pre_existing_changes`: preserved untouched --
  `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`,
  `scripts/scheduled/`, all nine `src/execution/crypto_*.py` /
  `tests/test_crypto_*.py` files.
- `unrelated_changes_preserved`: YES.

### Mid-task instruction: withdrawal permission

During this milestone the owner stated directly, in conversation, that withdrawal
permission on the exchange credentials is already restricted. This preflight task is
explicitly barred (its own instructions, section "Security Boundary") from making any
authenticated exchange call to verify this independently, so it was not independently
re-verified. It was recorded the same way this manifest already records its other
owner-only decisions (credential rotation completion, BTC market-data authority, C10
conceptual model): as an explicit owner confirmation, not a technically verified fact.
`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s
`credential_rotation_owner_confirmation.withdrawal_permission_status` was updated from
`UNRESOLVED` to `OWNER_CONFIRMED_RESTRICTED`, and
`release_qualification_gates.security.withdrawal_permission_removed` from `UNRESOLVED`
to `true`, both dated 2026-09-03. `ip_restriction_status` and
`minimum_permission_status` remain `UNRESOLVED` -- the owner did not speak to those.
`docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md` (untracked,
unrelated, explicitly out of scope for this task's file-safety rules) was left
unmodified and still records `UNKNOWN` as of this milestone -- this is flagged as a
minor, non-blocking documentation lag, not a conflict of fact.

## Manifest

- `manifest_path`: `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`
- `load_status`: PASS -- loaded via the project's own
  `post_asian_pilot.pilot_config.load_raw_yaml()`.
- `release_status`: `RELEASE_CANDIDATE` (unchanged).
- `reference_resolution`: PASS -- `supersedes: AG_TRADE_ASSISTANT_V1_0_2` correct;
  both `fx_cycles.*.pilot_source_path` and `strategy_source_path` fields resolve to
  real, loadable files (verified below).
- `manifest_drift`: NO -- content matches what this milestone independently verified
  against `strategies/`, `config/pilot/`, and `strategies/registry.yaml` (see FX
  AUTHORITY / LARGE SMC below), aside from the withdrawal-permission edit made by
  this milestone itself.

## FX authority

Verified with `post_asian_pilot.pilot_config.load_pilot_config()` and
`strategy_engine.loader.load_strategy()` against the actual pilot configuration files
-- not inferred from filenames, and explicitly checked against the
`SESSION_TRADE_V1` naming-collision trap (`strategies/STRATEGY_LEDGER.md` line 84;
that strategy is separately signed, lives in a different repository, and was not
touched or referenced by this manifest).

```text
strategy                    = ST_ASIAN_SWEEP_5R_V1
version                     = 1.1.1
ASIAN_LONDON_owner          = ST_ASIAN_SWEEP_5R_V1 v1.1.1 (config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml)
LONDON_NEWYORK_owner        = ST_ASIAN_SWEEP_5R_V1 v1.1.1 (config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml)
symbols                     = EURUSD, GBPUSD (both cycles)
authority_status            = PROPOSAL_ONLY, PASS
```

`strategy_engine.loader.load_strategy()` independently loaded
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml` via both cycles' own `strategy_source_path` and
confirmed `strategy_id`/`version` match in both cases.

## Session / data

- `ASIAN_LONDON_session_config`: reference session `asian` (`config/canonical_sessions.yaml`),
  execution window `07:00`-`11:00` UTC -- matches the manifest and the pilot config
  byte-for-byte.
- `LONDON_NEWYORK_session_config`: reference session `london_am`, execution window
  `12:00`-`15:00` UTC -- matches the manifest and the pilot config byte-for-byte.
- `session_config_drift`: NO -- `session_clock.validate_session_contract()` (the
  project's own canonical-session-contract validator) ran and returned no conflict.
- `EURUSD_data_readiness` / `GBPUSD_data_readiness`: **UNVERIFIABLE_FROM_THIS_ENVIRONMENT**.
  `mt5.symbol_resolver.get_symbol_meta()` was called read-only for both symbols and
  failed closed with `SYMBOL_METADATA_MISSING: symbol_info(...) failed: (-10004) No
  IPC connection` for both -- there is no MetaTrader5 terminal reachable from this
  development/tool environment. This is a fail-closed result (no synthetic/default
  metadata was substituted), not a code or configuration defect, and is the same
  class of environment constraint already recorded for BTC market data (Binance
  HTTP 451 / Bybit HTTP 403) in the manifest-freeze milestone. It must be re-checked
  from the actual environment where the shadow-validation process will run (an
  operator machine with MetaTrader5 installed, running, and logged into the demo
  account) before FX shadow entry.
- `clock/session_readiness`: PASS -- `validate_session_contract()` succeeded
  independent of MT5 connectivity (it validates the static session-window contract,
  not live data).

## State / ledger

Read-only inspection via `runtime_state.store.JsonKeyValueStore` (no writes, no
mutation):

```text
ASIAN_LONDON_state     = journal/post_asian_pilot/ -- daily_trade_ledger.json (2 keys, readable), session_snapshot.json (6 keys, readable)
LONDON_NEWYORK_state   = journal/post_london_newyork_pilot/ -- daily_trade_ledger.json (1 key, readable), session_snapshot.json (2 keys, readable)
ledger_isolation       = PASS -- physically separate directories/files, independently readable, no shared store
quota_isolation        = PASS -- DailyTradeLedger is keyed strategy_id+date per state_dir; separate state_dir per cycle (existing, tested design, not modified here)
restart_readiness      = PASS -- both ledgers and snapshot stores read back without StateStoreCorrupted; no fingerprint/session-state ambiguity found
duplicate_boundary      = PASS -- separate state_dir per cycle prevents one cycle's duplicate-suppression key space from crossing into the other's (design property, unchanged, exercised by tests/test_post_asian_pilot.py and tests/test_post_london_newyork_pilot.py)
```

## Execution safety

```text
proposal_only_boundary               = PASS (config/trading.yaml: mode=ANALYSIS, execution.allow_order_check=false, execution.allow_order_send=false, account.allow_live_trading=false, trade_management.mode=DRY_RUN, trade_management.allow_live_management=false -- unchanged)
automatic_execution                  = DISABLED
FX_live_execution                    = DISABLED
BTC_execution                        = NOT_IMPLEMENTED
shadow_to_broker_reachability        = BLOCKED -- config/trading.yaml untouched by this milestone; execution/executor.py::execute() still requires a fresh, explicit, non-defaulted user_confirmed=True per call (unchanged, confirmed via the same code path exercised by the focused tests below)
execution_gates_changed               = NO
```

Focused tests (30 passed, 0 failed) exercising execution-boundary/domain-rejection and
cross-cycle isolation:

```text
pytest -q tests/test_post_asian_pilot.py tests/test_post_london_newyork_pilot.py \
  tests/test_execution_command_safety.py tests/test_btc_proposal_execution_boundary.py \
  -k "isolat or ledger or restart or recover or fingerprint or release or boundary or reject or domain"
=> 30 passed, 67 deselected
```

## BTC

```text
strategy                       = ST_LIQUIDITY_SWEEP_RETEST_V1
version                        = 2.0.0
authority                      = RESEARCH_ONLY / PROPOSAL_ONLY, execution_authority=DISABLED, CryptoExecutionAdapter=NOT_IMPLEMENTED
production_data_status         = market-data authority FROZEN_BY_OWNER as Bybit (2026-09-03); Bybit HTTP 403 (country-block) and Binance HTTP 451, both recorded environment evidence, not re-tested this milestone
testnet_evidence_classification = INFRASTRUCTURE_EVIDENCE_ONLY -- excluded from strategy-quality/observation evidence per the manifest
observation_started             = NO
```

BTC is not part of FX shadow-day accumulation and was verified only against its frozen
boundary; no BTC connectivity probe was run by this milestone (none was needed, since
the manifest already records current evidence and this task does not require fresh
BTC verification for FX shadow readiness).

## Large SMC

```text
strategy                        = ST_LARGE_SMC_V1
version                         = 1.0.6
authority                       = RESEARCH_DRAFT, RESEARCH_ONLY (strategies/registry.yaml: registered=true, active=false, research=true, demo_authorized=false, live_authorized=false)
C10                              = UNSIGNED_BLOCKED (engine runtime behavior unchanged); owner has separately selected a conceptual model (AG_NATIVE_INVALIDATION, 2026-09-03) but implementation/contract-freeze remain PENDING -- not touched, not implemented, not rerun by this milestone
proposal_generation_authorized  = false
```

## Security

```text
credential_rotation                          = OWNER_CONFIRMED_COMPLETE (Binance/MEXC/Bybit, 2026-09-03, recorded in prior milestone)
withdrawal_permission                        = OWNER_CONFIRMED_RESTRICTED (2026-09-03, stated directly by the owner during this milestone; recorded in the manifest, not independently re-verified via authenticated call)
tracked_secret_check                         = PASS -- `git diff` of this milestone's own tracked edits (manifest + PROJECT_STATUS.md + docs/VERSION_HISTORY.md) scanned for api_key/secret/password/token patterns: none found beyond the expected field-name references to the rotation/permission status itself
authenticated_exchange_validation_performed  = NO -- none attempted, none required for FX proposal-only preflight (per this task's own security-boundary instruction)
```

No secret value was printed, inspected, or compared by this milestone.

## Tests

```text
focused_tests               = 30 passed, 0 failed (see Execution safety section above)
preflight_command           = No existing CLI run: src/post_asian_pilot/preflight.py::run_preflight() hardcodes release_id == "AG_TRADE_ASSISTANT_V1_0_2" (line 80) and defaults to a single pilot (ASIAN_LONDON only) -- running it unmodified against V1.0.3 would deliberately fail WRONG_RELEASE_LOADED, and it cannot check LONDON_NEWYORK at all without a second invocation this milestone chose not to add source-code support for (out of scope: modifying that hardcoded check would change which release the operational pilot is gated against, which V1.0.2-vs-V1.0.3 boundary this task must not move). Instead, this milestone directly reused every one of run_preflight()'s own building-block functions (load_raw_yaml, load_pilot_config, load_strategy, validate_session_contract, get_symbol_meta, JsonKeyValueStore reads) against both V1.0.3 cycles, read-only, with no source change -- see the checks recorded above.
full_regression_status      = FULL_REGRESSION_NOT_RERUN -- this milestone changed only config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml, PROJECT_STATUS.md, docs/VERSION_HISTORY.md, and this new status document; no .py source file changed
prior_full_suite_evidence_classification = HISTORICAL_REFERENCE_ONLY -- "1356 passed / 1 skipped / 0 failed" is tested against be5d31a; current HEAD is 506d8b5, which this milestone independently confirmed (via scoped git diff, not by reusing the prior task's own claim) does not touch any file relevant to that evidence's continued validity
git_diff_check               = clean (only pre-existing CRLF line-ending warnings on PROJECT_STATUS.md, docs/VERSION_HISTORY.md, and docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md -- none newly introduced by this milestone)
```

## Release / shadow gates

```text
FX_preflight                    = HOLD (this milestone)
shadow_entry_ready              = NO -- blocked solely on FX_data_readiness (MT5 connectivity unverifiable from this environment)
FX_shadow_days_completed        = 0 / 20
BTC_observation_days_completed  = 0 / 30
release_status                  = RELEASE_CANDIDATE (unchanged)
unresolved_blockers             = ["MT5 live connectivity for EURUSD/GBPUSD could not be established from this development/tool environment -- must be re-run from the environment where the shadow-validation process will actually execute, with a MetaTrader5 terminal installed, running, and logged into the demo account"]
```

Every other category checked (manifest integrity, FX cycle authority, session
configuration, state/ledger isolation, restart readiness, execution-boundary
fail-closed behavior, risk/safety configuration drift, Large-SMC boundary, secrets
hygiene) returned PASS with no drift and no code change required.

## Files changed

**THIS_MILESTONE:**
- `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` (edited -- three targeted edits
  recording the owner's withdrawal-permission confirmation; no other field changed)
- `PROJECT_STATUS.md` (edited -- one new rolling-snapshot line)
- `docs/VERSION_HISTORY.md` (edited -- one line updated with preflight outcome and
  withdrawal-permission status)
- `docs/status/AG_TRADE_ASSISTANT_V1_0_3_OPERATIONAL_PREFLIGHT_STATUS.md` (new, this
  document)

**PRE_EXISTING_UNRELATED** (untouched by this milestone):
- Modified before this milestone started: `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`,
  `docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md`
- Untracked before this milestone started: `scripts/scheduled/`, all nine
  `src/execution/crypto_*.py` / `tests/test_crypto_*.py` files
- `docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md` (from the
  prior milestone; not modified by this one)

## Classification

`HOLD`

Every configuration, authority, isolation, and safety check this milestone could run
returned PASS with zero drift and zero code changes needed. The single open item is
`FX_data_readiness`: live MT5 connectivity for EURUSD/GBPUSD could not be established
from this development/tool environment ("No IPC connection"). Per this task's own
Section 26, data-source unavailability is an explicit `HOLD` condition, and
`FX_data_readiness = PASS` is a required condition for `PREFLIGHT_PASS_SHADOW_READY`
that this milestone cannot honestly claim from here.

## Next authorized step

Re-run this preflight's MT5/data-readiness check (`mt5.symbol_resolver.get_symbol_meta`
for EURUSD and GBPUSD) from the actual environment where the shadow-validation process
will execute -- a machine with a MetaTrader5 terminal installed, running, and logged
into the demo account referenced by the pilot configuration. If that check passes and
no other check has drifted, `AG_TRADE_ASSISTANT_V1_0_3` may proceed directly to
`PREFLIGHT_PASS_SHADOW_READY` without repeating the other categories verified here.
Do not begin FX shadow collection, BTC observation, or any execution/proposal-only
runtime start from this milestone.
