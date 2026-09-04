# AG_TRADE_ASSISTANT_V1_0_3 -- FX Report Decision-Key Remediation Status (2026-09-04)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Fixes the
report/persistence-key defect discovered during
`AG_V1_0_3_FX_SHADOW_SERIES_002_DAY_001`. Defect remediation only -- no strategy,
session, risk, quota, or execution semantics changed.

## Baseline before

```text
git_head             = f45c9ead4008ea6347c7cfdb31bde8be7adc9a99 (unchanged at start)
working_tree              = clean except journal/reports/ (runtime evidence, untracked)
pre_existing_status_changes    = PROJECT_STATUS.md and the Series 002 Day 001 status
                                 document had been edited (uncommitted) by the prior
                                 milestone recording INVALID_DAY -- both were reviewed
                                 and correctly classified as this remediation's own
                                 intended documentation updates, not unrelated drift
```

## Defect reproduction (read-only, before any edit)

```text
persisted_decision_key    = "ST_ASIAN_SWEEP_5R_V1|EURUSD|2026-09-04|Asian"
                            (journal/post_asian_pilot/decision.json, status READY)
report_lookup_key             = "ST_ASIAN_SWEEP_5R_V1|EURUSD|2026-09-04|asian"
                                (report.render_pilot_end_report, built from
                                pilot.reference_session_name)
mismatch                          = YES -- "Asian" != "asian"
reproduced                            = YES, directly from real 2026-09-04 journal
                                       files (not synthetic), confirmed before any
                                       source change: the CLI report showed
                                       "final_strategy_state": "NO_RECORD" for both
                                       ASIAN_LONDON symbols despite two real, claimed
                                       READY proposals existing in the same-day ledger
```

A second, distinct instance of the same class of defect was also found and confirmed
while reproducing: LONDON_NEWYORK's persisted `reference_session` is `"London"`
(`journal/post_london_newyork_pilot/decision.json`) while the pilot config's
`reference_session_name` is `"london_am"` -- these differ by more than case
(`"london" != "london_am"`), so a case-insensitive-only fix would have left this unit
broken. The prior milestone's status document had incorrectly stated LONDON_NEWYORK's
report "correctly shows WATCH" -- re-verified against the actual JSON output (not
just the raw decision-file key) this was wrong; it also showed `NO_RECORD`. Corrected
in place in that document (see its own "Correction" note), not silently rewritten.

## Root cause

```text
identity_source_before   = report.render_pilot_end_report() built its lookup key from
                           PilotConfig.reference_session_name (config/pilot/*.yaml,
                           itself sourced from config/canonical_sessions.yaml -- lowercase,
                           e.g. "asian"/"london_am")
identity_source_conflicting  = a real, strategy-engine-evaluated decision is saved
                                (decision.py::map_trade_signal_to_decision,
                                store.py::save_decision) under
                                TradeSignal.reference_session -- copied verbatim from
                                strategies/ST_ASIAN_SWEEP_5R_V1.yaml's
                                session_pairs[].reference_session.name (display-cased,
                                "Asian"/"London") -- a genuinely different string from
                                pilot config's own name, not merely differently cased
                                for the LONDON_NEWYORK pair
classification                   = B (normalized session name) was considered and
                                    rejected -- "London" cannot be normalized to
                                    "london_am" by any case-insensitive string
                                    transform without inventing an ad hoc mapping
                                    table. D (an already-existing stable key) was
                                    used instead: (strategy_id, symbol, trading_date)
                                    is already the real identity WITHIN one pilot
                                    cycle's own isolated decision store (each cycle
                                    persists to its own state_dir -- see
                                    PilotConfig.state_dir / PilotStores.default,
                                    unchanged) -- reference_session was never actually
                                    needed to disambiguate anything, since cycle
                                    isolation is already enforced at the directory
                                    level, not the key level
```

## Fix

```text
files_changed        = src/post_asian_pilot/store.py (new function find_decision()),
                       src/post_asian_pilot/report.py (render_pilot_end_report now
                       calls find_decision() instead of building/reading a
                       reference_session-keyed dict key directly; unused import
                       removed)
normalization_or_canonical_key_used   = (strategy_id, symbol, trading_date) prefix scan
                                        within one already-isolated decision store,
                                        picking the record with the latest
                                        evaluation_time when more than one candidate
                                        matches (handles the case where a stale
                                        pre-close WATCH and a later real evaluation
                                        legitimately coexist as two distinct JSON keys)
                                        -- reference_session is accepted as an optional
                                        parameter for call-signature compatibility but
                                        no longer participates in matching
historical_data_rewritten                 = NO -- no journal/decision.json file was
                                            edited; the fix changes only how an
                                            existing record is found, never what is
                                            written or when
```

`pipeline.py`, `decision.py`, `governor.py`, `pilot_config.py`,
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`, and every config/pilot/*.yaml file are
untouched -- the write path (how/when a decision or proposal is persisted) was not
modified at all, only the report's read path.

## Semantic invariants

```text
strategy_semantics_changed        = NO
sessions_changed                     = NO
risk_changed                            = NO
quota_changed                               = NO
proposal_logic_changed                         = NO
execution_authority_changed                       = NO
```

Verified from a fresh `git diff` before staging: the two source-file diffs touch only
a lookup/reader function and its one call site; no line in either diff references
`strategy_engine`, `execution`, session windows, risk, or quota.

## Tests

```text
focused_tests       = 6 new/updated tests in tests/test_post_asian_pilot.py:
                      find_decision exact-match, find_decision tolerates strategy-YAML
                      casing mismatch (reproduces the real ASIAN_LONDON defect),
                      find_decision returns None for no record, find_decision tolerates
                      the non-casing "London"/"london_am" mismatch (reproduces the real
                      LONDON_NEWYORK defect), find_decision prefers the latest record
                      when a stale WATCH and a real evaluation both exist, and an
                      end-to-end render_pilot_end_report test proving a READY decision
                      with a claimed proposal is no longer reported as NO_RECORD
affected_suite          = tests/test_post_asian_pilot.py + test_post_london_newyork_pilot.py
                          + test_daily_fx_report.py -- 78 passed, 0 failed (72 prior +
                          6 new)
git_diff_check              = clean
full_regression                = NOT RERUN -- change confined to one reader function in
                                 post_asian_pilot; reused prior full-suite evidence per
                                 project convention for scoped fixes
```

## 2026-09-04 reconstruction (proof only, does not recount Day 001)

Re-ran the existing, unmodified canonical daily report against the same already-persisted
2026-09-04 journals (no strategy re-evaluation):

```text
ASIAN_LONDON_EURUSD          = READY (was NO_RECORD)
ASIAN_LONDON_GBPUSD             = READY (was NO_RECORD)
proposal_ids_preserved              = YES -- PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-04,
                                     PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-04
                                     (identical IDs/entry/stop/targets to the
                                     already-claimed ledger slots -- nothing
                                     re-derived or re-computed)
LONDON_NEWYORK_actual_persisted_state    = WATCH / WATCH (NO_SETUP_BY_WINDOW_END,
                                            genuinely still open at check time -- no
                                            proposal, correctly reported as such)
original_archive_preserved                  = YES -- journal/reports/fx/2026/2026-09-04.json
                                            (the original defect-era archive) untouched
correction_created                             = YES -- journal/reports/fx/2026/2026-09-04.correction-00N.json
                                                (numbered corrections from each
                                                verification re-run this milestone;
                                                append-only mechanism, unmodified by
                                                this fix, worked exactly as designed)
```

Full detail appended to
`docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md` under
its own `POST_REMEDIATION_RECONSTRUCTION` heading, per instruction, rather than
duplicated here.

## Day 001 (unchanged)

```text
official_classification   = INVALID_DAY
counted                       = NO
valid_days                       = 0/20
invalid_days                        = 1
```

Not altered by this milestone.

## Commit

```text
commit_created            = YES
REMEDIATION_COMMIT             = (recorded after commit -- see final report)
committed_files                    = src/post_asian_pilot/store.py,
                                    src/post_asian_pilot/report.py,
                                    tests/test_post_asian_pilot.py,
                                    PROJECT_STATUS.md,
                                    docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md
                                    (correction note + reconstruction section),
                                    docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md (this file)
unrelated_files_committed              = NONE -- journal/reports/ (runtime evidence,
                                         including this milestone's own correction
                                         files from verification) deliberately excluded,
                                         same convention as the prior baseline-freeze
                                         milestone
```

## Validation baseline

```text
previous_source_baseline           = 68d76f6b1982f2b2936e12128151a308ba153a13
new_validation_source_baseline         = (this milestone's commit hash -- see final report)
metadata_freeze_commit_if_any               = not created separately this milestone --
                                             this status document itself, committed
                                             alongside the fix in the same commit,
                                             already records the new hash faithfully;
                                             a second metadata-only commit was judged
                                             unnecessary busywork for a same-day,
                                             single-purpose fix (unlike the earlier
                                             two-commit baseline freeze, which recorded
                                             a hash that did not exist at documentation
                                             time)
```

## Series continuity

```text
existing_series             = AG_V1_0_3_FX_SHADOW_SERIES_002 (preserved -- same series ID)
contract_requires_new_series    = NO -- the frozen evidence contract
                                  (AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1) defines
                                  VALID_DAY/EXCLUDED_DAY/INVALID_DAY/PENDING_RECONCILIATION
                                  per trading day, not per source revision; an
                                  INVALID_DAY followed by a defect fix does not, by that
                                  contract's own terms, require opening a new series --
                                  it requires collecting the NEXT eligible day under the
                                  corrected baseline, still within Series 002
next_countable_series               = AG_V1_0_3_FX_SHADOW_SERIES_002 (continues; Day 001
                                      stays INVALID_DAY, Day 002 will be the next
                                      countable attempt)
```

## Execution

```text
proposal_only          = YES
automatic_execution        = DISABLED
FX_live_execution              = DISABLED
broker_mutation                  = NO
```

No proposal was executed; the two real READY proposals from 2026-09-04 remain exactly
as claimed (unactioned) in the ledger.

## Readiness

```text
REPORTING_TRUSTWORTHY        = YES (for the defect class found and fixed this milestone;
                                not a claim that no other defect exists anywhere in the
                                reporting/history stack)
SHADOW_COLLECTION_READY          = YES (once the new validation baseline below is
                                    treated as authoritative for the next countable day)
DEMO_EXECUTION_READY                 = NO
REAL_EXECUTION_READY                    = NO
```

Trustworthy reporting -> valid shadow evidence -> demo execution (separate
authorization) -> real execution (later approval) remain distinct, sequential stages;
this milestone advances only the first.

## Classification

**`REPORT_KEY_REMEDIATION_COMPLETE`**

## Next authorized step

"Freeze the remediated validation baseline, then collect the next eligible countable
FX day under the new baseline." **Not performed in this milestone.**
