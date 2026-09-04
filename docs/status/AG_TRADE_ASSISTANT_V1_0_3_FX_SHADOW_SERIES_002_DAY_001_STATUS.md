# AG_TRADE_ASSISTANT_V1_0_3 -- FX Shadow Series 002 Day 001 Status (2026-09-04)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. **Supersedes the
prior entry in this same file** (preserved below, not erased): that entry recorded
`BASELINE_NOT_READY` before the baseline-freeze commits existed. This entry records the
actual first Series 002 evaluation attempt, now that the baseline is frozen.

**Result: `INVALID_DAY`.** A real, previously-undiscovered material defect in the
existing (unchanged-by-this-session) daily end-of-window reporting path was found
during evidence collection. Per instruction, evidence was preserved, the day was
classified, and no source code was touched to fix it.

## Baseline (verified, not assumed)

```text
application_release        = AG_TRADE_ASSISTANT_V1_0_3
SOURCE_BASELINE_COMMIT          = 68d76f6b1982f2b2936e12128151a308ba153a13
FREEZE_METADATA_COMMIT              = f45c9ead4008ea6347c7cfdb31bde8be7adc9a99
actual_HEAD                             = f45c9ead4008ea6347c7cfdb31bde8be7adc9a99 (matches)
baseline_verified                          = YES
source_drift                                  = NO -- only `journal/reports/` (runtime
                                                evidence) was dirty before this
                                                milestone's own read-only report
                                                invocation added today's archive entry
```

## Series

```text
series_id           = AG_V1_0_3_FX_SHADOW_SERIES_002
initialized              = YES (this milestone)
day_number                  = 001
trading_date                    = 2026-09-04 (Friday -- ordinary FX trading day, not a
                                  weekend/holiday exclusion)
counters_before                    = valid=0/20, excluded=0, invalid=0, pending=0
```

## Eligibility

`eligible_trading_day = YES` -- 2026-09-04 is a normal weekday with both reference
sessions available; no evidence-contract exclusion applies.

## Real state observed (read-only; only `python scripts/run_fx_daily_report.py --date
2026-09-04` was invoked -- no strategy cycle re-run, no `--watch`, no proposal claimed
by this milestone)

```text
ASIAN_LONDON
  ledger (journal/post_asian_pilot/daily_trade_ledger.json, key ...:2026-09-04):
    EURUSD  CLAIMED  proposal_id=PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-04
                     ready_at=2026-09-04T07:45:00Z  claimed_at=2026-09-04T12:05:40Z
    GBPUSD  CLAIMED  proposal_id=PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-04
                     ready_at=2026-09-04T07:45:00Z  claimed_at=2026-09-04T12:05:40Z
  decision.json (journal/post_asian_pilot/decision.json):
    key "ST_ASIAN_SWEEP_5R_V1|EURUSD|2026-09-04|Asian"  -> status READY
    key "ST_ASIAN_SWEEP_5R_V1|GBPUSD|2026-09-04|Asian"  -> status READY
  -- both slots (2/2) legitimately claimed; real, non-synthesized evidence, produced by
     the existing runtime before this milestone began (this milestone created none of it)

LONDON_NEWYORK
  ledger: no 2026-09-04 entry yet (0/2 -- window 12:00-15:00 UTC still open at check
          time, 13:51 UTC; correctly isolated from ASIAN_LONDON's ledger/state_dir)
  decision.json (journal/post_london_newyork_pilot/decision.json):
    key "ST_ASIAN_SWEEP_5R_V1|EURUSD|2026-09-04|London"  -> status WATCH
    key "ST_ASIAN_SWEEP_5R_V1|GBPUSD|2026-09-04|London"  -> status WATCH
  -- consistent with the cycle still being open (final checkpoint 15:00 UTC not yet
     reached)
```

## Defect discovered: reference-session key-casing mismatch in the existing
## end-of-window report (`report.render_pilot_end_report`)

`render_pilot_end_report` looks up each symbol's decision via:

```
key = f"{strategy_id}|{symbol}|{trading_date.isoformat()}|{pilot.reference_session_name}"
stores.decision_store.get(key)
```

`pilot.reference_session_name` comes from the **pilot config** (lowercase, matching
`config/canonical_sessions.yaml`): `"asian"` for
`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`, `"london_am"` for the
LONDON_NEWYORK pilot config.

But once a symbol's reference session actually closes and `pipeline._evaluate_pair`
calls the real strategy engine, the resulting `PostAsianDecision.reference_session`
comes from `TradeSignal.reference_session` -- copied verbatim from
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`'s own `session_pairs[].reference_session.name`,
which is **capitalized**: `"Asian"` (ASIAN_LONDON pair, yaml line 46) and `"London"`
(LONDON_NEWYORK pair, yaml line 57). `save_decision` (store.py) persists under whatever
`reference_session` string the decision object carries, so a real post-close decision
(READY, as observed today, but also real NO_TRADE/EXPIRED/DATA_ERROR) is saved under a
**different key** than the one `render_pilot_end_report` looks up.

This is why today's report shows `"final_strategy_state": "NO_RECORD"` for both
ASIAN_LONDON symbols despite two real, legitimately claimed READY proposals existing
in the ledger and decision store -- confirmed directly by reading
`journal/post_asian_pilot/decision.json`'s actual keys (above), not inferred.

The only reason this did not surface in the 2026-09-03 smoke test earlier this session
is timing, not a fix: the pre-close `WATCH` decision saved by `_evaluate_pair`'s
`now < ref_end` branch (pipeline.py) passes `pilot.reference_session_name` directly
(matching the lowercase report-lookup key) -- so a day whose only persisted decision so
far is still that early "waiting" record reports correctly by coincidence. The mismatch
only manifests once a symbol reaches a real, closed-session evaluation, which is
exactly the meaningful case a daily decision report exists to capture. This is a
**pre-existing defect in already-committed code this session did not modify**
(`report.py`'s lookup construction and/or `pipeline.py`'s two different
`reference_session` sources), not something introduced by the earlier FX
release-identity or daily-reporting-infrastructure milestones.

```text
defect_scope      = report.render_pilot_end_report() (and therefore
                    daily_fx_report.build_fx_daily_report(), which calls it unchanged)
                    silently under-reports real decisions whenever the persisted
                    decision's reference_session casing (from the strategy YAML)
                    differs from the pilot config's reference_session_name casing
severity              = material -- the "final_strategy_state"/"proposal_id" fields, the
                        primary content of the required daily decision report, are
                        wrong (falsely NO_RECORD) for both ASIAN_LONDON symbols today,
                        despite real READY decisions and claimed proposals existing
fix_applied              = NO -- not touched this milestone, per instruction ("do not
                            fix the defect inside the countable day")
```

## Required daily units (four)

```text
1. ASIAN_LONDON / EURUSD    -- real decision: READY (proposal claimed); report shows
                              NO_RECORD due to the defect above -- CANONICAL REPORT
                              EVIDENCE FOR THIS UNIT IS WRONG
2. ASIAN_LONDON / GBPUSD    -- same as above
3. LONDON_NEWYORK / EURUSD    -- real decision: WATCH; report ALSO shows NO_RECORD
4. LONDON_NEWYORK / GBPUSD      -- same as above
```

**Correction (recorded during the follow-up remediation milestone, not silently
edited away):** this section originally claimed LONDON_NEWYORK's report "correctly
shows WATCH ... lowercase/capitalized keys happen to not have diverged yet for this
still-open cycle." That was wrong -- re-checked against the actual JSON output (not
just the raw decision.json key, which is what the original check inspected), the
LONDON_NEWYORK report also showed `NO_RECORD` for both symbols, for a related but
distinct reason: the strategy YAML's session name for this pair is `"London"`, not
merely a different *case* of the pilot config's `"london_am"` -- `"london" !=
"london_am"` even case-insensitively. All four units were actually affected by the
same class of defect, not two of four as first reported. See
`AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md` for the
corrected root cause and fix.

All four required canonical-report units were not trustworthy today because of
the defect above -- the evidence contract's requirement that "all required daily
decision units [be] collected" (correctly, in the authoritative artifact) is not met.

## Proposals

```text
proposal_count   = 2 (both ASIAN_LONDON, real/pre-existing, not created by this
                   milestone: EURUSD and GBPUSD, ready_at 2026-09-04T07:45:00Z)
proposal_ids         = PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-04,
                       PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-04
```

Neither proposal's field-level content (direction/entry/SL/TP) was independently
re-verified as part of this milestone -- doing so was unnecessary once the reporting
defect made this day non-countable; preserved as-is in the journal, not touched.

## Isolation / duplicates

```text
state_isolation           = OK (separate state_dir per cycle, confirmed)
ledger_isolation             = OK (separate daily_trade_ledger.json per cycle,
                                confirmed -- LONDON_NEWYORK has no 2026-09-04 entry at
                                all while ASIAN_LONDON has 2/2 claimed)
quota_isolation                = OK
cross_cycle_contamination         = NO
duplicate_proposals                  = 0 (ledger shows exactly 2 claimed slots, matching
                                      2 proposal_ids, no duplicate claim entries)
duplicate_quota_claims                   = 0
duplicate_archive_write                     = N/A this check (archive write for
                                            2026-09-04 was this milestone's first)
restart_anomalies                              = none observed; LONDON_NEWYORK counters
                                                show duplicate_proposals_suppressed=8
                                                (idempotent re-evaluation suppression
                                                working as designed on repeated
                                                background polling of the same
                                                still-forming setup -- not an anomaly)
```

## Daily report / archive

```text
canonical_report     = generated (schema AG_FX_DAILY_REPORT_V1)
release_identity        = AG_TRADE_ASSISTANT_V1_0_3 (correct)
archive_path                = journal/reports/fx/2026/2026-09-04.json (new -- first
                             write for this date, no correction needed)
idempotency                    = untested this run (first write)
correction_created                 = NO
```

The archive mechanism itself worked correctly; the content it faithfully archived is
what is wrong, per the defect above.

## Execution safety

```text
proposal_only          = YES
automatic_execution        = DISABLED
FX_live_execution              = DISABLED
broker_mutation                  = NO
```

Only a read-only report/archive invocation ran this milestone; no strategy cycle,
`--watch`, `order_check`, or `order_send` call was made.

## Source changes

**NONE.** No strategy/session/risk/quota/proposal/execution/report/archive/scheduler
source file was modified this milestone. The defect above is documented, not repaired.

## Classification

**`INVALID_DAY`**

`classification_reason`: a material defect in the existing daily end-of-window
reporting path (reference-session key-casing mismatch between pilot config and
strategy-engine-produced decisions) causes the canonical daily FX report to falsely
show `NO_RECORD` for both ASIAN_LONDON units today, despite real READY decisions and
claimed proposals existing. This is exactly the "evidence corruption" /
"material runtime defect" case in the frozen evidence contract's `INVALID_DAY`
definition -- not a data-timing issue (`PENDING_RECONCILIATION`), not a pre-declared
exclusion (`EXCLUDED_DAY`), and not a broker-mutation safety violation (`NO_GO`).

## Counters after

```text
valid_days           = 0/20
excluded_days            = 0
invalid_days                = 1
pending_days                    = 0
```

## Series progress

**0/20 VALID DAYS**

## BTC

```text
evidence                        = 0/30 (unchanged)
daily_production_decision           = NOT_OPERATIONAL (unchanged)
```

Not touched this milestone.

## Overall release

```text
application            = AG_TRADE_ASSISTANT_V1_0_3
status                     = RELEASE_CANDIDATE
qualification_complete         = NO
```

## Next authorized step

"Preserve Day 001 evidence and open a separate remediation milestone before collecting
another countable day." Specifically: the `reference_session` casing mismatch between
`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`
/`config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml` (`"asian"`/`"london_am"`) and
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`'s `session_pairs[].reference_session.name`
(`"Asian"`/`"London"`) needs an owner-authorized fix to
`report.render_pilot_end_report`'s (or `pipeline.py`'s) key construction before Series
002 can produce trustworthy daily evidence. Not fixed here.

## POST_REMEDIATION_RECONSTRUCTION (2026-09-04, added after the follow-up remediation)

`AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md` fixed the
defect above (`src/post_asian_pilot/store.py::find_decision`, `report.py` wired to use
it). Re-running the existing, unmodified canonical daily report against the SAME
already-persisted 2026-09-04 journals (no strategy re-evaluation, no new proposal)
now correctly reconstructs:

```text
ASIAN_LONDON / EURUSD    = READY  (LOWER_SWEEP_STRICT_PENETRATION,
                                   proposal_id=PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-04)
ASIAN_LONDON / GBPUSD    = READY  (UPPER_SWEEP_STRICT_PENETRATION,
                                   proposal_id=PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-04)
LONDON_NEWYORK / EURUSD     = WATCH  (NO_SETUP_BY_WINDOW_END, no proposal)
LONDON_NEWYORK / GBPUSD        = WATCH  (NO_SETUP_BY_WINDOW_END, no proposal)
```

Archived (append-only, original never overwritten) at
`journal/reports/fx/2026/2026-09-04.correction-00N.json` (numbered corrections
accumulated from each re-run during verification; the original, defect-era
`2026-09-04.json` is preserved untouched).

**This reconstruction does NOT change Day 001's official classification.** Day 001
remains `INVALID_DAY` (the defect was real and material at the time of the original
observation); `valid_days` stays `0/20`; `invalid_days` stays `1`. This artifact exists
only to prove the fix against real evidence, per instruction ("this is for proving the
fix only").

---

## Preserved prior entry (2026-09-04, before the baseline-freeze commits existed)

> Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`.
> **STOPPED at the hard prerequisite gate -- no countable evidence was collected.**
>
> **Baseline check (the gate)**
> ```
> application_release        = AG_TRADE_ASSISTANT_V1_0_3 (working tree)
> FX strategy                    = ST_ASIAN_SWEEP_5R_V1 v1.1.1
> actual_git_head                    = fad8ee2df8361f32df765805367b721c3cbd04f7
> validation_baseline_commit             = NONE RECORDED -- ... exist ONLY in the
>                                          uncommitted working tree ...
> source_baseline_frozen                     = NO
> Series_001                                    = PRE_REMEDIATION_NON_COUNTING_EVIDENCE
> Series_002                                       = NOT INITIALIZED (blocked by the
>                                                     gate above)
> ```
>
> **Classification: `BASELINE_NOT_READY`**

This was resolved by the subsequent `AG_TRADE_ASSISTANT_V1_0_3_BASELINE_FREEZE_BEFORE_FX_SERIES_002_STATUS.md`
milestone (commits `68d76f6` / `f45c9ea`), enabling this Day 001 attempt above.
