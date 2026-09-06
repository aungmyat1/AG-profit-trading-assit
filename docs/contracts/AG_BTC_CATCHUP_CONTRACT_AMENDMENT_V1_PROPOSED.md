# AG_BTC_CATCHUP_CONTRACT_AMENDMENT_V1 -- PROPOSED, NOT YET AUTHORIZED

STATUS: **PROPOSED**. This document is a draft prospective amendment to
`docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`, produced by the CATCHUP-1
recoverability audit (`docs/status/AG_INTERMITTENT_PC_CATCHUP_CONTRACT_AUDIT_V1_STATUS.md`).
It is **NOT APPLIED**. It does not amend `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`,
does not touch `strategies/registry.yaml`, and does not change any qualification counter.
Nothing in this document is authoritative until an explicit, separate, owner-authorized
commit adopts it. Until adopted, the existing frozen `AG_BTC_DAILY_OBSERVATION_CONTRACT_V1`
governs BTC evidence exactly as before, unchanged.

Rationale for proposing this now rather than after Day 1: per the governing audit
prompt's section 7, BTC is the cleanest campaign to amend prospectively, because
`campaign_started=false`, `valid_observations=0/30`, and no counted evidence exists yet --
amending afterward would require reclassifying already-counted days, which this repo's
existing evidence-integrity posture (immutable/append-only archives, see
`post_asian_pilot.report_archive`) is specifically built to avoid ever needing to do.

---

## Required fields (per governing prompt section 54)

```
effective_from:                       <owner-decided date, NOT BEFORE this document's authorization>
campaign_started_before_amendment:    NO
evaluation_modes:                     [LIVE_WINDOW, CATCH_UP]
normal_report_window:                 [D+1 00:05 UTC, D+1 00:15 UTC)   # unchanged from AG_BTC_DAILY_OBSERVATION_CONTRACT_V1
maximum_catch_up_delay:               PROPOSED: until the next observation's own report window opens
                                       (i.e. a catch-up evaluation for day D must complete before
                                       day D+1's own normal report window opens at D+2 00:05 UTC) --
                                       see "Delay bound options considered" below; OWNER DECISION REQUIRED
observation_interval:                 [D 00:00:00Z, D+1 00:00:00Z)     # unchanged
historical_data_authority:            Bybit (or the configured production CryptoCandleFeed adapter),
                                       same provider/exchange_id already recorded per report;
                                       PROPOSED ADDITION: pin provider identity into the fingerprint bundle (see below)
required_H1_count:                    24   (previous UTC day; verified against
                                       btc_sweep_research.daily_report._prefetch_and_audit_observation's
                                       existing constant, not newly invented)
required_M5_count:                    288  (observation UTC day; same verification)
fingerprint_requirement:              PROPOSED ADDITION: report payload gains
                                       `input_fingerprint: {h1: <sha256>, m5: <sha256>, strategy_config: <sha256>}`
                                       computed via the existing, unmodified
                                       post_asian_pilot.fingerprint.fingerprint() over the exact
                                       candle arrays used and the loaded SweepRetestStrategyConfig
                                       content -- no new hash primitive, reuse only
lookahead_prohibition:                Evaluation must use only candles with time <= the observation
                                       interval's own end instant; ALREADY ENFORCED unconditionally by
                                       btc_sweep_research.pipeline.run_research_cycle's existing
                                       `c.time <= now` / `today_start <= c.time <= now` filters and by
                                       daily_report.build_btc_daily_report's fixed
                                       `evaluation_now = observation_date 23:59:59.999999 UTC` pinning --
                                       this amendment does not change that logic, it makes the audit
                                       (`validate_observation_data=True`) MANDATORY for any catch-up call
                                       and adds the fingerprint capture on top of it
DATA_ERROR_policy:                    Distinguish (see "DATA_ERROR semantics" below):
                                       MISSING_AT_NORMAL_REPORT_WINDOW,
                                       DATA_RECOVERED_LATER,
                                       PERMANENT_DATA_ERROR,
                                       MISSED_UNRECOVERABLE
                                       -- as report-level METADATA on the existing DATA_ERROR decision
                                       state, not as new public decision states (existing
                                       READY/WATCH/NO_TRADE/DATA_ERROR vocabulary is preserved unchanged)
counter_model:                        valid_live_window, valid_catch_up, invalid, missed_unrecoverable
                                       (proposed; see "Counter model" below -- OWNER DECISION REQUIRED
                                       on whether valid_catch_up contributes to the 30-observation target)
qualification_threshold_policy:       NOT DECIDED BY THIS DOCUMENT -- explicitly deferred to a later,
                                       separate governance decision (per governing prompt CATCHUP-5);
                                       this amendment only makes the counters representable, it does not
                                       decide which ones count toward release readiness
execution_eligible_for_catch_up:      false (permanent, non-negotiable, structurally enforceable per
                                       audit finding 2.4 -- execution.executor already fails closed on
                                       foreign execution_domain/execution_authority objects; a
                                       CATCH_UP-tagged BTCSweepResearchProposal must additionally carry
                                       evaluation_mode=CATCH_UP so no future code path can promote it)
retroactive_2026_09_05_allowed:       false (unchanged, explicitly reaffirmed -- the 2026-09-05
                                       diagnostic run remains permanently excluded and is never backfilled
                                       under any evaluation_mode)
scheduler_required:                   false (this amendment is designed specifically so BTC catch-up
                                       reporting works on an intermittently-available owner PC with NO
                                       Task Scheduler/cron/daemon -- a manual/on-demand invocation within
                                       the delay bound is sufficient)
```

## Delay bound options considered (for `maximum_catch_up_delay`)

1. **Same UTC day only** -- simplest, but defeats the entire purpose of this amendment
   (an owner PC that was off overnight could never recover day D at all if it must run on
   day D+1 before D+1 ends -- actually this option is workable since D's report runs
   during D+1, but it gives zero slack for a PC that stays off longer than one day).
2. **Within 24 hours of the normal report window** -- simple, bounded, but arbitrary
   relative to campaign structure.
3. **Within N calendar days** -- flexible but requires picking N without a principled
   anchor; risks silently accumulating a backlog of stale "catch-up" evidence.
4. **Until the next observation's own report window is due** (RECOMMENDED) -- i.e. day D
   must be caught up before day D+1's own normal window (D+2 00:05-00:15 UTC) opens. This
   keeps campaign ordering strictly sequential (no two unresolved days ever stack), keeps
   archive uniqueness trivial (append-only, one file per day, written at most once per
   day in strict order), and gives a naturally self-limiting, operationally meaningful
   bound tied to how the campaign already runs day-by-day -- rather than an arbitrary
   duration. This audit recommends option 4, but flags it as an OWNER DECISION, not a
   technical necessity -- Bybit's historical data availability does not itself constrain
   the choice (verified as materially longer-lived than any of these bounds).

## DATA_ERROR semantics -- proposed refinement (report-level metadata only)

The current contract's `DATA_ERROR` state (`daily_report.DECISION_DATA_ERROR`) is raised
whenever `run_research_cycle`/`_prefetch_and_audit_observation` throws, regardless of
whether the missing data might still arrive later. This amendment proposes NO new public
decision state (still exactly READY/WATCH/NO_TRADE/DATA_ERROR) but adds an internal
`data_error_class` field to the persisted report only:

- `MISSING_AT_NORMAL_REPORT_WINDOW` -- DATA_ERROR raised inside the normal
  00:05-00:15 UTC window; data may still recover before the catch-up delay bound expires.
- `DATA_RECOVERED_LATER` -- a subsequent catch-up attempt for the same day, within the
  delay bound, now passes the same completeness audit that failed before. Per the existing
  observation contract's own late-data policy, this is recorded as an ADDITIVE_CORRECTION
  (never overwriting the original DATA_ERROR archive entry) -- **retroactive VALID_DAY
  counting for a corrected DATA_ERROR day remains an explicitly unresolved governance
  question, as the base contract already states, and this amendment does not resolve it.**
- `PERMANENT_DATA_ERROR` -- the delay bound expired while data was still incomplete;
  this day can never be corrected and is not eligible for any future catch-up attempt.
- `MISSED_UNRECOVERABLE` -- no evaluation was ever attempted for day D before its delay
  bound expired (the owner PC was never run in time) -- distinct from
  `PERMANENT_DATA_ERROR` (data was unavailable) because here the DATA may have been fine;
  the operational opportunity was simply missed. This maps to the `missed_unrecoverable`
  counter.

## Counter model (proposed)

```
valid_live_window   += 1   when a VALID observation completes inside the normal report window
valid_catch_up       += 1   when a VALID observation completes after the normal window but
                             within maximum_catch_up_delay, with a full input_fingerprint recorded
invalid              += 1   unchanged meaning (a completed, evaluable observation that is not VALID)
missed_unrecoverable += 1   when neither of the above happened before the delay bound expired
```

**This amendment explicitly does NOT decide** whether `valid_catch_up` contributes to the
existing 30-observation qualification target, at what weight, or whether it is reported
only as a separate, non-counting metric. Per the governing audit's section 4/49, that
decision belongs to a later, explicit governance step (CATCHUP-5), not to this contract
amendment. Until that governance step occurs, this amendment's DEFAULT (if adopted as-is)
is: **`valid_catch_up` observations are recorded and reported, but do NOT count toward the
30-observation target** -- they are `evidence_weight=DETERMINISTIC_REPLAY`,
`execution_eligible=false`, informational only, same treatment as any other
`NON_COUNTING_DIAGNOSTIC` until the owner explicitly upgrades their counting weight.

## What this amendment does NOT change

- The 00:05-00:15 UTC normal report window (unchanged).
- The observation interval definition (unchanged).
- The 24 H1 / 288 M5 completeness requirement (unchanged, only now made mandatory to check
  via `validate_observation_data=True` for any catch-up-mode call).
- The strategy, its version, its YAML config, or any BTC guard/tradability logic (unchanged).
- The 2026-09-05 diagnostic exclusion (reaffirmed, unchanged).
- The current campaign authorization state (`campaign_started=false`,
  `scheduler_installation=NOT_AUTHORIZED`) -- this amendment does not authorize starting
  the campaign; that remains a separate decision already recorded in
  `docs/status/AG_V1_0_3_BTC_OBSERVATION_CAMPAIGN_AUTHORIZATION_STATUS.md`.

## Adoption path (not performed by this document)

1. Owner reviews and either approves, amends, or rejects this proposal.
2. If approved, a separate commit updates
   `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md` (or supersedes it with a V2)
   with the agreed `maximum_catch_up_delay`, the fingerprint schema addition, and the
   DATA_ERROR-class metadata field -- plus corresponding, narrowly-scoped code changes to
   `daily_report.py` (make `validate_observation_data=True` the default/only path for any
   report call, and add the `input_fingerprint` field to the returned payload).
3. Only after that adoption commit lands does BTC Day 1 begin counting under the amended
   contract; until then, BTC evidence continues to be governed exactly as
   `AG_BTC_DAILY_OBSERVATION_CONTRACT_V1` already specifies, unchanged.
