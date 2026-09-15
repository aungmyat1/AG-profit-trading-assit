# Large SMC EURUSD Friction Policy -- WP3A.1 Multi-Session Evidence Campaign (2026-09-16)

Extends WP3A's single-snapshot spread evidence into a predeclared, deterministic,
multi-day campaign. This mission builds and freezes the campaign infrastructure and
starts scheduled collection; it does **not** itself produce 5 complete trading days of
evidence in one sitting -- that requires real elapsed calendar time, which a single
session cannot fast-forward through.

## WP0 -- freeze WP3A

`WP3A_COMMIT_SHA = fe4d526` (already committed at mission start).

## WP1 -- campaign manifest (frozen before collection)

`campaign_id = LSMC_EURUSD_FRICTION_WP3A1_V1`, frozen via
`scripts/freeze_eurusd_friction_campaign_manifest.py` (refuses to run twice --
verified by test) into
`artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/campaign_manifest.json`.

`campaign_manifest_hash = 6a34439f0e141bd691f724aa7c74ea3795684ef2d497ad064e29d7c183414345`
(sha256 over canonical sorted JSON, in the companion `campaign_manifest_hash.json`).

4 predeclared UTC windows (WINDOW_A_ASIAN_REFERENCE 05:30-05:40, WINDOW_B_PRE_LONDON
06:50-07:00, WINDOW_C_LONDON 09:00-09:10, WINDOW_D_LONDON_NEWYORK 12:30-12:40) x
minimum 5 distinct FX trading days x 120 samples/window (5s grid) = 2400-observation
minimum population, exactly as specified. No window was altered based on any observed
spread.

## WP2 -- collection infrastructure (reused collector, extended, not replaced)

Extended the already-audited `src/fx_friction_research/spread_evidence.py` (no second
collector module) with `collect_fixed_grid()`: samples on a fixed absolute-time grid
anchored to each window run's own start time -- tick *i* always fires at
`start + i*5s` regardless of how long the previous capture took (no adaptive
compression), verified by a fake-clock test that makes each capture "take" 3s. A
capture that raises (`MT5ConnectionError`/`MarketDataError`) becomes a `MISSING_GAP`
row carrying the failure reason at its scheduled grid time -- never dropped, never
retried out of schedule, never backfilled.

`scripts/run_eurusd_friction_campaign_window.py` runs one window: refuses to start if
the manifest isn't frozen, refuses a weekend UTC day, and **refuses to overwrite** an
existing `<day>_<window_id>_raw.jsonl` -- a window is never silently restarted because
its result looked unfavorable.

## Real-time collection status

At mission start it was **2026-09-15 21:22 UTC (Tuesday)** -- none of the four windows
were reachable (today's had already passed; the next, WINDOW_A, was ~8 hours away).
**Zero real campaign observations exist yet.** Per your explicit choice, this mission
registered 4 Windows Task Scheduler entries (folder `\AG_LSMC_Friction_Campaign\`,
weekdays only) that run `run_eurusd_friction_campaign_window.py --window-id <id>` daily
at the local-time equivalents of the four UTC windows (this machine is UTC+6:30):

| Window | UTC | Local | Task name |
|---|---|---|---|
| WINDOW_A_ASIAN_REFERENCE | 05:30 | 12:00 | AG_LSMC_EURUSD_Friction_WindowA_AsianRef |
| WINDOW_B_PRE_LONDON | 06:50 | 13:20 | AG_LSMC_EURUSD_Friction_WindowB_PreLondon |
| WINDOW_C_LONDON | 09:00 | 15:30 | AG_LSMC_EURUSD_Friction_WindowC_London |
| WINDOW_D_LONDON_NEWYORK | 12:30 | 19:00 | AG_LSMC_EURUSD_Friction_WindowD_LondonNY |

Each task logs to `logs/friction_campaign_<WINDOW_ID>.log` and auto-expires
2026-09-30 (a ~2-week buffer past the 5-trading-day minimum, in case a day is missed).
**Operational caveat, stated plainly:** these tasks run in the interactive user
session and depend on the Vantage MT5 terminal already being logged in and running at
each trigger time, and on this machine being on and this Windows user session being
active. If either is not true at a given trigger time, `connect()` fails closed and
that run exits non-zero with nothing written (visible in the log) -- it will not
silently fabricate a window. No campaign day should be assumed complete without
re-running WP3/WP4/WP5 aggregation to check.

## WP3/WP4/WP5 -- aggregation (built, not yet run against real data)

`scripts/aggregate_eurusd_friction_campaign.py` reads every completed
`sessions/<day>_<window_id>_{raw.jsonl,summary.json}`, and reports per-window-group,
per-day, and campaign-aggregate spread statistics (min/median/mean/p75/p90/p95/p99/max,
computed from unrounded raw values, `missing_sample_count` tracked separately, never
blended into a single number that hides which trading day is incomplete), plus writes
`campaign_evidence_manifest.json` (every session's `raw_rows_hash`) and a deterministic
`combined_campaign_hash` (`combine_hashes()`, order-independent). Has not been run yet
-- `sessions/` is currently empty; running it today would correctly report
`NO_SESSIONS_COLLECTED`.

## WP6/WP7 -- commission/slippage (re-checked, unchanged from WP3A)

Re-queried this session: 0 EURUSD deals in this account's retrievable 30-day MT5
history (still only the same 3 BTCUSD deals as WP3A); the EURUSD execution journal
still has exactly n=1 record with a computed `slippage_points` value. Both remain
**UNAVAILABLE** for EURUSD specifically -- neither was cross-inferred from BTCUSD, and
n=1 was not extrapolated into a distribution.

## WP8 -- C10 (unchanged, descriptive only)

New `src/fx_friction_research/c10_friction_ratios.py`: `friction_to_stop_ratios()`
computes `{median,p90,p95,p99}_pips / 1.5` (C10's `min_buffer_pips`, read as a
reference constant only) -- pure division, no optimization, no write path to the
strategy file. `strategies/ST_LARGE_SMC_V1.yaml` is git-diff-empty against `fe4d526`.

## WP9 -- friction contract

**Not updated this mission.** `friction_policy_contract.json` is unchanged from WP3A
(still `status: PROPOSED`, `owner_signature: REQUIRED`, spread still explicitly
`SUPERSEDED_ASSUMPTION`-flagged for the old 0.8-pip figure via WP3A's evidence note).
Updating it with campaign-derived numbers before the campaign has any real data would
be premature; it will be revisited once WP3/WP4/WP5 aggregation has real sessions to
read.

## WP10 -- token/compute control

All statistics computed locally in Python (`statistics`/pure arithmetic, no LLM call on
raw ticks). This status doc and any future agent review of this campaign should consume
`campaign_manifest.json`, `campaign_manifest_hash.json`, per-session `*_summary.json`,
`campaign_evidence_manifest.json`, and `campaign_aggregate_report.json` -- raw
`*_raw.jsonl` files are for targeted spot-verification only, never bulk LLM ingestion.

## WP11 -- tests

`tests/test_large_smc_eurusd_friction_campaign_wp3a1.py` (15 tests, all pass): manifest
frozen-and-hash-matches, freeze-script refuses double-run, fixed-grid schedule is
non-adaptive (fake-clock proof), missing samples recorded not dropped, campaign summary
reproducible/order-independent, raw-hash and combined-hash deterministic/order-
independent, C10 ratios descriptive-only, commission/slippage absence preserved,
no order-placement names/imports in any new script (AST scan), strategy/validation-
core/execution-boundary git-diff-empty against `fe4d526`, execution authority
unchanged. Combined with WP3A's 29 and the broader 142-test sweep, nothing regressed.

## Output

```text
REPOSITORY_STATE: WP3A frozen at fe4d526; WP3A.1 infra additive, staged for its own commit; .vscode/settings.json and pyrightconfig.json still untouched/uncommitted
WP3A_COMMIT_SHA: fe4d526
CAMPAIGN_ID: LSMC_EURUSD_FRICTION_WP3A1_V1
CAMPAIGN_MANIFEST_HASH: 6a34439f0e141bd691f724aa7c74ea3795684ef2d497ad064e29d7c183414345
BROKER_IDENTITY: VantageMarkets-Demo, account 26088035, trade_mode=DEMO
COLLECTION_DAYS: 0 complete (campaign just frozen; scheduled collection begins with tomorrow's WINDOW_A run)
WINDOW_COMPLETION: 0/4 windows collected on any day so far
TOTAL_SAMPLE_COUNT: 0
SESSION_SPREAD_STATISTICS: none yet -- aggregator reports NO_SESSIONS_COLLECTED if run today
DAILY_SPREAD_STATISTICS: none yet
AGGREGATE_SPREAD_STATISTICS: none yet
EVIDENCE_HASHES: none yet (campaign_evidence_manifest.json not yet generated -- no sessions exist)
COMBINED_CAMPAIGN_HASH: not computed (requires >=1 session; campaign target is >=5 complete days)
COMMISSION_STATUS: UNAVAILABLE (EURUSD-specific; re-confirmed unchanged from WP3A)
SLIPPAGE_STATUS: UNAVAILABLE (n=1; re-confirmed unchanged from WP3A)
C10_FRICTION_RESEARCH_STATUS: infrastructure ready (friction_to_stop_ratios), no real ratios computed yet -- C10 itself unchanged
FRICTION_POLICY_STATUS: PROPOSED, owner_signature REQUIRED (unchanged from WP3A; not updated this mission)
FRICTION_POLICY_SIGNABILITY: INSUFFICIENT_EVIDENCE
VALIDATION_CORE_DIFF: empty (git diff fe4d526 -- validation_framework core files + strategy_lifecycle.yaml)
STRATEGY_SEMANTICS_DIFF: empty (git diff fe4d526 -- ST_LARGE_SMC_V1.yaml, large_smc_research/, large_smc_adapter.py)
EXECUTION_AUTHORITY_DIFF: empty (execution_authority_metadata unchanged: all False; git diff fe4d526 -- src/execution/, management_gateway.py, mt5_gateway.py all empty)
TEST_RESULTS: 15/15 new WP3A.1 tests pass; 44/44 combined with WP3A+WP2 regression suite
FILES_CHANGED:
  M  src/fx_friction_research/spread_evidence.py (extended: collect_fixed_grid, summarize_campaign_rows, raw_rows_hash, combine_hashes, MISSING_SOURCE)
  A  src/fx_friction_research/c10_friction_ratios.py
  A  scripts/freeze_eurusd_friction_campaign_manifest.py
  A  scripts/run_eurusd_friction_campaign_window.py
  A  scripts/aggregate_eurusd_friction_campaign.py
  A  artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/campaign_manifest.json
  A  artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/campaign_manifest_hash.json
  A  tests/test_large_smc_eurusd_friction_campaign_wp3a1.py
  A  docs/status/AG_LARGE_SMC_EURUSD_FRICTION_CAMPAIGN_WP3A1_STATUS.md
  (OS-level, outside this repo/commit) 4 Windows Task Scheduler entries under \AG_LSMC_Friction_Campaign\, expiring 2026-09-30
  (not touched/not committed) .vscode/settings.json, pyrightconfig.json
DATA_GAPS: entire campaign population (2400 observations, 5 days, 4 windows/day) is outstanding -- this mission froze the plan and started scheduled collection but collected zero real samples itself (no window was live during this session)
BLOCKERS: real-time elapsed-day dependency (cannot be resolved within one session); scheduled-task collection depends on the MT5 terminal and this Windows user session both being live at each trigger time -- a missed day is recorded as an absent session file, not fabricated
NEXT_SAFE_ACTION: let the scheduled tasks run for >=5 trading days, then run scripts/aggregate_eurusd_friction_campaign.py and re-open this mission (or a WP3A.2) to review real daily/aggregate statistics, C10 ratios, and only then reconsider FRICTION_POLICY_SIGNABILITY -- still not to be set to READY_FOR_OWNER_REVIEW merely because 2400 samples exist
```

STOP.
