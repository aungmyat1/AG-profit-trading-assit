# Scheduler + Large SMC Watch Hardening (2026-09-20)

Mission `AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1`. Prepares the repository for
reliable scheduled FX proposal production while preserving the running Large SMC
validation campaign. **No demo or live execution authority was granted or exercised by
this mission.**

`HEAD_BEFORE = 415d0622b82a8bedbabdc620d018969cec51c2cb`

---

## 1. Existing scheduler state (audited before mutation)

Two FX tasks already existed and were **corrected in place**, not duplicated:

| Task | Prior trigger (defect) | Corrected trigger |
|---|---|---|
| `AG_FX_ASIAN_LONDON_SHADOW` | `TimeTrigger` start 2026-09-03T00:00, `PT15M`, **no `DaysOfWeek`**, **no `EndBoundary`**, **no offset** | Weekly Mon–Fri at 13:30:20 local (07:00:20 UTC), `PT15M`, duration `PT4H` |
| `AG_FX_LONDON_NEWYORK_SHADOW` | same shape | Weekly Mon–Fri at 18:30:20 local (12:00:20 UTC), `PT15M`, duration `PT3H` |

Three concrete defects in the prior configuration:

1. **No window bound** — a window-scoped proposal cycle was invoked outside its own
   execution window, indefinitely.
2. **No weekday bound** — weekend invocations can only produce `DATA_ERROR` against a
   closed market (observed directly: the 2026-09-20 Sunday runs logged
   `strategy_state=DATA_ERROR`, `reason_codes=[DATA_MISSING]`).
3. **Fired at the M15 OPEN, not the CLOSE** — a `PT15M` repetition anchored at `00:00:00`
   fires at `:00/:15/:30/:45`, i.e. the instant a bar opens, while the pilot's entire
   premise is acting on a *closed* bar.

Both tasks previously ran a **bare `python`** (which on this machine resolves to
`C:\Python314\python.exe`, *not* the project virtualenv). The wrapper scripts now use
the repository virtualenv explicitly and fail closed if it is missing.

Prior trigger XML is preserved at `logs/scheduler/AG_FX_*_SHADOW.before*.json`.

Other pre-existing AG tasks were left untouched: `AG Profit Trading - BTC Daily
Decision`, and the four `\AG_LSMC_Friction_Campaign\` window tasks.

**No duplicate tasks were installed.** Exactly two `AG_FX_*` tasks exist, verified after
the change.

## 2. FX scheduler status — `FX_SCHEDULER_READY`

Deterministic weekday `--once` scheduling, no `--watch`:

| Cycle | Window (UTC) | Window (MMT) | Slots/day | Slot times |
|---|---|---|---|---|
| `ASIAN_LONDON` | 07:00–11:00 | 13:30–17:30 | 17 | every M15 close + 20s |
| `LONDON_NEWYORK` | 12:00–15:00 | 18:30–21:30 | 13 | every M15 close + 20s |

The windows are the pilots' own canonical `execution_window` values
(`config/pilot/*.yaml`), not independently chosen.

New components:

- `src/scheduling/fx_schedule.py` — pure schedule computation, the four gates, the
  frozen-campaign guard, and a slot ledger.
- `scripts/run_fx_cycle_once.py` — the fail-closed runner.
- `scripts/install_fx_scheduler.ps1` — idempotent installer/verifier with backup.
- `scripts/scheduled/run_{asian_london,london_newyork}_once.bat` — now delegate to the
  runner via the virtualenv.

**Four ordered fail-closed gates**, each evaluated before anything is delegated; exit
code `2` means "refused, nothing ran" (a correct outcome, not a failure):

| Gate | Refusal |
|---|---|
| Weekday | `REFUSED_WEEKEND_MARKET_CLOSED` |
| Inside window | `REFUSED_OUTSIDE_EXECUTION_WINDOW` |
| Friction campaign | `REFUSED_FRICTION_CAMPAIGN_WINDOW_ACTIVE:<window>` |
| Slot idempotency | `REFUSED_SLOT_ALREADY_EXECUTED` |

`--watch` is **rejected outright** (`REFUSED_WATCH_NOT_SUPPORTED`), not silently
ignored — the runner exists precisely to avoid a continuous process.

### Friction-campaign protection (Window D)

The guard reads the **frozen** WP3A.1 manifest, never a hardcoded window list, and is
active only while the campaign is still collecting. Collision map:

| Frozen window (UTC) | Collides with |
|---|---|
| `WINDOW_A_ASIAN_REFERENCE` 05:30–05:40 | neither cycle |
| `WINDOW_B_PRE_LONDON` 06:50–07:00 | touches `ASIAN_LONDON`'s 07:00 open |
| `WINDOW_C_LONDON` 09:00–09:10 | inside `ASIAN_LONDON` |
| `WINDOW_D_LONDON_NEWYORK` 12:30–12:40 | inside `LONDON_NEWYORK` |

So **three of the four** frozen windows would otherwise be sampled by a scheduled FX
slot. An unreadable manifest fails closed (`REFUSED_FRICTION_CAMPAIGN_UNREADABLE`)
rather than being treated as "no campaign".

## 3. Duplicate proposal identity — reproduced and characterised

**Reproduced on the live ledger.** `state/proposal_ledger/proposal_ledger.json` holds
**69 records for only 13 distinct logical setups** — 56 duplicate records, a **5.31×
inflation**. Worst case: 11 records for one unchanged
`ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-09-15` occurrence, every one with
byte-identical `direction`/`entry`/`stop`/`targets`.

**Root cause — a layer collapse, not a ledger bug.** Three distinct identities are
required, and all three already exist canonically:

| Layer | Canonical source | Volatility |
|---|---|---|
| Logical setup | `confirmation_evidence.setup_id` (`strategy:cycle:symbol:date`) | stable per setup |
| Observation | `proposals.identity.snapshot_id` → `data_provenance.data_version` + `market_data_asof` | every poll, by design |
| Proposal | `proposal_envelope_id` (WP7 canonical `proposal_id`) | should be per setup |

`proposal_envelope/adapters/fx_adapter.py` builds
`proposal_envelope_id = f"FX:{decision.decision_id}"`, and
`post_asian_pilot/decision.py::_decision_id` hashes **`evaluation_time`** into its
digest. Since the weekday scheduler polls every M15 close, each poll re-observes the
same setup with a fresh `evaluation_time` → a fresh `decision_id` → a fresh
`proposal_envelope_id` → a **new ledger record every 15 minutes for an unchanged
setup**. `ProposalLedger.record_proposal`'s geometry-match idempotency only fires for
the *same* key, so it never triggers.

This is documented verbatim in the repo's own `ticket_delivery/identity.py`:
`_decision_id` "was deliberately NOT reused here — it hashes in `evaluation_time`, which
differs on every retry, so it cannot serve as a stable logical-ticket key."

**Governed remediation (candidate, not an in-place change).** The mission requires that
frozen canonical behavior not be modified in place, so this mission delivers an
**additive, read-only** resolver rather than editing the frozen path:

- `src/proposal_envelope/identity_audit.py` — `resolve_identity_layers()` (pure,
  deterministic) and `audit_ledger_records()` / `audit_ledger_file()` (read-only).

The repo already contains the canonical three-layer identity contract
(`src/proposals/occurrence_identity.py`: `SETUP_FAMILY_ID` / `ELIGIBILITY_INTERVAL_ID` /
`CANDIDATE_OCCURRENCE_ID`), which its own docstring states is **"not wired into either
yet"**. This mission does not wire it in either — that is a behavior-changing correction
that must land as a new versioned candidate promoted only after validation.

One real adapter gap surfaced: `proposal_envelope/adapters/ssc_adapter.py` emits **no
`confirmation_evidence.setup_id`** (its `setup_evidence` carries
`campaign_id`/`session_pair`/`setup_model`/`trading_date` instead). Those 6 records get
a **derived** key explicitly flagged `identity_source=DERIVED_SSC_COMPOSITE` /
`logical_identity_is_authoritative == False`, so a derived key can never be mistaken for
the canonical field. Unknown families fail closed (`UNRESOLVABLE_LOGICAL_SETUP_IDENTITY`).

**No strategy economics were changed** — no entry, stop, target, risk, sizing, or
strategy-YAML value was touched. `_decision_id`, the FX adapter's
`proposal_envelope_id`, and `ProposalLedger` keying are all **unchanged**.

## 4. Large SMC campaign protection (WP3A.1) — unchanged

`LSMC_EURUSD_FRICTION_WP3A1_V1` inspected only; **no campaign configuration, manifest,
or evidence was modified.**

| Item | State |
|---|---|
| Complete trading days | **3 of 5 minimum** (2026-09-16, 09-17, 09-18) |
| Sessions | 12 (4 windows × 3 days) |
| Samples | **120/120 per session, `missing_sample_count = 0` for all 12** |
| Task state | all four `Ready`, weekday-only, auto-expire 2026-09-30 |
| Next runs | 2026-09-21 at 12:00 / 13:20 / 15:30 / 19:00 local |

The frozen `campaign_manifest_hash` is untouched. Collection is **incomplete** and was
left to continue; 2 more trading days are required (Mon 2026-09-21, Tue 2026-09-22).

One anomaly examined and cleared: `2026-09-18_WINDOW_D_LONDON_NEWYORK` has a file
mtime of 2026-09-19T02:24 local, i.e. the run landed after local midnight. Its log
contains exactly three day markers (one per day, no repeats) and the summary declares
`day = 2026-09-18` with 120/120 samples, so no duplicate and no misattribution occurred.

## 5. Large SMC time alignment — **DEFECT CONFIRMED** (research-only fix)

`scripts/run_large_smc_live_watch.py` passed **true-UTC** candle times to
`resample_broker_aligned`, which requires **broker wall-clock** readings:

```python
broker_times = [c.time for c in m5_candles]   # c.time is TRUE UTC
```

`mt5.market_data.get_candles` already subtracts the broker offset, so `c.time` is UTC;
the function's own contract (and `mt5_export_loader`'s `IngestionReport.broker_times`)
requires the raw un-normalized broker reading. Feeding UTC in **degrades
broker-anchored bucketing to UTC-midnight bucketing** — precisely the failure the
function exists to prevent ("a UTC-midnight-bucketed resample mismatched EVERY SINGLE
bar of a native MT5 D1 export").

Demonstrated on a synthetic +3 broker feed: the buggy path yields 4 buckets anchored on
UTC midnight; the fixed path yields 3 complete broker days anchored at 21:00 UTC. H4 is
equally affected (boundaries land on UTC 21/01/05/09/13/17, not 00/04/08/12/16/20), so
the 60-D1 / 50-H1 warm-up and every D1/H4-anchored detection input were computed on the
wrong calendar.

**Fix** (`large_smc_research/live_watch.py::resolve_broker_times`): reconstruct the
broker wall-clock reading from the broker's own detected UTC offset. The offset is
**re-detected every run** (the broker shifts seasonally +2/+3) and recorded in the run
report, so a stale-offset run is visible rather than silent. M15/H1 stay UTC-bucketed,
which is correct for whole-hour offsets.

## 6. Large SMC incremental watch — **DEFECT CONFIRMED** (research-only fix)

The watcher re-fetched 150 days of M5 and re-ran `run_replay` over the **entire window
on every invocation**, re-deriving warm-up from scratch and re-evaluating ~43,000
already-evaluated M5 bars. Cost grew with the calendar, not with new information; only
the ledger's idempotent upsert hid the redundancy.

**Fix**: a persisted watermark (`next_start_utc`) means each run evaluates only bars
closed since the previous run, while the **warm-up lookback is still fetched and loaded
in full** so warm-up is preserved. `run_replay`'s clock filter (`as_of >= start_utc`) is
exact at M5 close boundaries, so consecutive windows neither overlap nor skip. A
binary-searched warm-up floor (`find_warmup_floor`) guarantees the incremental window
never starts before warm-up is cleared.

New/changed:

- `src/large_smc_research/live_watch.py` — both fixes, watcher state, fail-closed rules.
- `scripts/run_large_smc_live_watch.py` — now a thin adapter over the tested module.
- `journal/large_smc_research/watch_state.json` — watermark (does not exist yet; the
  watcher has **never been run**).

### Fail-closed rules

| Condition | Reason code |
|---|---|
| History cannot clear D1/H1/M5 warm-up | `INSUFFICIENT_WARMUP_DATA` |
| Newest closed M5 bar implausibly old (>72h) | `STALE_DATA` |
| Fetch returned nothing | `NO_M5_CANDLES_RETURNED` |
| Non-ascending / duplicated base series | `OUT_OF_ORDER_OR_DUPLICATE_CANDLES` |
| Zero valid steps despite cleared warm-up | `NO_VALID_STEPS` |

`INSUFFICIENT_WARMUP_DATA` matters most: previously a too-short window produced
`valid_steps=0` and an empty ledger, **indistinguishable from "no setups found"** — a
silent false negative. It is now a hard refusal.

### Parity against native broker candles

Cross-validated against MT5's own native exports on real data
(`tests/test_large_smc_live_watch_hardening.py`):

- **D1**: derived broker-aligned D1 matched **all** compared native broker D1 bars
  (>300 bars, 0 mismatches).
- **H4**: derived broker-aligned H4 matched **all** 390 compared native broker H4 bars
  over a constant-offset summer window, 0 mismatches.
- **Negative control**: UTC bucketing produces a different bar count and never lands on
  a broker-midnight boundary, confirming the defect was real.

The D1/H4 parity tests skip cleanly when the `D:\EURUSD_*.csv` exports are absent.

## 7. Watch lifecycle — projected, not invented

The mission's requested
`WATCHING → QUALIFIED → ENTRY_AVAILABLE → FILLED/UNFILLED → RESOLVED/EXPIRED` is
implemented as a **deterministic, total, documented projection** of existing canonical
states (`src/large_smc_research/watch_lifecycle.py`) — **not** a new lifecycle
authority. `AGENTS.md` forbids inventing a lifecycle-stage label; lifecycle authority
remains `EntryModelState` / `fill_simulator` statuses.

- `FILLED` / `UNFILLED` use the fill simulator's own `STATUS_FILLED` /
  `STATUS_UNFILLED_AS_OF_DATA_END` **verbatim** — no synonym introduced.
- `RESOLVED` is **deliberately unreachable**: resolving `FILLED → TARGET_HIT/STOP_HIT`
  needs C10 (broker stop distance), still unsigned. A filled occurrence reports
  `resolution_status = UNRESOLVED_REQUIRES_C10` rather than fabricating a favourable
  resolution.
- The projection is **total** over every `EntryModelState` member and every fill status
  (`assert_projection_is_total()`); an unmapped state fails closed rather than
  defaulting.
- The canonical state is retained **verbatim** alongside the projected stage, with
  `canonical_state_source` recording which authority produced it.
- Provenance is retained end to end: setup family / symbol / combination / direction /
  reference key, all timestamps, entry condition, maneuver, entry type, invalidation
  trigger.

`Large SMC remains RESEARCH_ONLY`. The watcher is **not scheduled** — an assertion in
the test suite fails if any installer script references it.

## 8. Test results

| Suite | Result |
|---|---|
| `tests/test_proposal_identity_layering.py` (new, P2) | **16 passed** |
| `tests/test_fx_scheduler_once.py` (new, P1) | **30 passed** |
| `tests/test_large_smc_live_watch_hardening.py` (new, P4) | **32 passed** |
| `tests/test_large_smc_watch_lifecycle.py` (new, P5) | **31 passed** |
| Affected-surface regression (`test_large_smc_live_watch_execution_boundary`, `test_large_smc_live_ledger`, `test_large_smc_execution_boundary`, `test_large_smc_registration`, `test_large_smc_research_engine`) | **45 passed** |

Command: `.venv\Scripts\python.exe -m pytest -q --tb=short <paths>`
Environment: Windows, Python 3.14 venv, offline (no live MT5 dependency in the new
tests; broker-parity tests read local `D:\` exports and skip if absent).

No frozen dataset bytes were altered to make any hash pass.

## 9. Authority

| | |
|---|---|
| `DEMO_AUTHORITY` | **NONE** — unchanged by this mission |
| `LIVE_AUTHORITY` | **NONE** — unchanged by this mission |

`config/trading.yaml` was not modified. No execution, order-check, order-send, or
management path was made reachable. All new modules are statically asserted to have no
reach to `execution.executor` / `execution.coordinator` / `execution.adapter` /
`mt5.management_gateway` / order functions.

Large SMC economic edge is **not** claimed; the campaign has 3 of 5 required days and no
economic gate was evaluated.
