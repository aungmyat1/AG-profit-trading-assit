# LSMC_ACTIONABILITY_POLICY_V1 -- frozen spec v1.0.0

Status: FROZEN at commit time of AG_V1_HOST_HARDENING_R1 T2. Any future change to a threshold
or rule below requires a new signed owner decision and a new version (`..._V2`), never an edit
to this file in place.

Source of authority: `docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`
(PR #48, signed 2026-10-07, status SIGNED) decisions D1, D2, D3, D4, D7. That file lives only on
PR #48's branch (`audit/v1-followup-2026-10-07`), which is open/unmerged as of this writing --
this mission's own branch does not carry it, so it is cited here by content (fetched and read
directly from that branch), not reproduced in this repo tree. D5/D6/D8 from the same decision
packet are governance/display statements, not actionability mechanics, and are out of scope for
this module (see "Non-scope" below). The mission instruction that commissioned this module
paraphrased D1-D4/D7 in brief operational terms (e.g. "actionable"/"INFO_ONLY"); this spec
implements that paraphrase while also aligning field names and the two nuances below to the
underlying signed doc's own fuller wording, since both describe the same decisions.

Two nuances adopted directly from the signed doc's own text (not inferable from the paraphrase
alone):
- D2 says "Persist: reference_price, send_price, **R_AT_TRIGGER**, R_AT_SEND" -- both R values,
  not just the send-time one. `remaining_r_at_trigger` (computed from the candidate's own entry
  price, fixed at trigger time) is carried on every decision alongside `remaining_r` (R_AT_SEND).
  Only R_AT_SEND gates ACTIONABLE/INFO_ONLY; R_AT_TRIGGER is audit-only.
- D7 says "Add CORRELATION_CLUSTER_ID + CORRELATED_EXPOSURE (e.g. USD_SHORT,
  **USD_SHORT_SENSITIVE for XAUUSD**)" -- gold is deliberately bucketed separately from a plain
  USD-quoted FX pair. `correlated_exposure()` returns the `_SENSITIVE` suffix for XAUUSD;
  `tag_and_rank_correlated()` groups on this (not on the plain `usd_direction()`), so an XAUUSD
  candidate is never pooled into the same correlation cluster as e.g. EURUSD.

Implementation: `src/lsmc_actionability_policy/policy.py`. Tests:
`tests/test_lsmc_actionability_policy.py`.

## Decisions implemented

### D1 -- Freshness

A candidate is actionable only if it is evaluated (sent) at most **2 trigger-timeframe bars**
after the triggering bar's close; otherwise it is `INFO_ONLY`.

- Trigger timeframe: Large-SMC's own M5 sweep/CHoCH trigger (`large_smc_watch`'s documented
  `TIMEFRAME_CHAIN = "D1 context -> H1 bias + POI -> M5 sweep/CHoCH"`) -- 5 minutes per bar.
- `bars_since_close = max(0, (now - trigger_close_utc).total_seconds() / 60) / tf_minutes`.
- Actionable iff `bars_since_close <= 2` (inclusive boundary -- exactly 2 bars is still fresh).
- Example (the signed "07:01 case"): a trigger bar closing at 06:50 UTC is fresh through and
  including 07:00 UTC (exactly 2 bars later); at 07:01 UTC (2.2 bars) it is stale ->
  `INFO_ONLY`, reason `STALE_BEYOND_2_TRIGGER_BARS`.

### D2 -- Minimum remaining R

A candidate is actionable only if the **remaining reward**, measured from the send-time quote
to the target and expressed in multiples of the original risk distance, is **>= 1.5**.

- `risk = abs(entry - stop)`; unmeasurable (`risk <= 0`) fails closed (never actionable).
- Reference price is the send-time quote side that is conservative for the direction being
  taken: `bid` for `LONG` (you would eventually have to sell into the bid), `ask` for `SHORT`.
  This mirrors the existing spread-as-cost convention in `v1_tickets.guards.spread_check()`.
- `remaining_r = (target - reference_price) / risk` for LONG, `(reference_price - target) / risk`
  for SHORT.
- The send-time bid **and** ask are always persisted with the decision
  (`send_time_bid`/`send_time_ask`), regardless of whether the candidate passes D2 -- this is
  the audit trail the owner decision requires, not just the side actually used in the formula.
- `remaining_r_at_trigger` (R_AT_TRIGGER) is also always persisted, computed the same way but
  from the candidate's own `entry` price instead of a live quote -- this is the R the setup was
  designed with at trigger time. It never gates the classification; only R_AT_SEND does.

### D3 -- No catch-up READYs

After a detected downtime gap (elapsed time since the last successful run exceeds the
operator's configured normal poll-cadence tolerance), no candidate whose trigger closed before
or during that gap is ever sent as an actionable READY once the run resumes. Instead, exactly
**one** combined digest, labeled `"MISSED - NOT ACTIONABLE"`, is produced summarizing every
candidate the gap caused to be withheld (`missed_digest()`): count, affected symbols, and the
downtime window. `detect_downtime(last_run_at=None, ...)` is never downtime (nothing to have
missed on the very first run).

### D4 -- Unclosed signal bar

If the bar a signal is actually built from has not closed yet, the candidate is classified
`PENDING_BAR_CLOSE` -- explicitly **not** `STALE`/`INFO_ONLY`, because nothing was missed; the
bar simply has not finished forming. `PENDING_BAR_CLOSE` short-circuits D1/D2 entirely (there is
nothing meaningful to measure freshness or remaining-R against yet) and the caller re-evaluates
once the bar closes -- D4 does not define a retry/scheduling mechanism itself, only the
classification a caller's next poll should see instead of a false STALE/INFO_ONLY.

### D7 -- Correlated READYs

Among the candidates that are independently `ACTIONABLE` in the same evaluation batch, any two
or more that imply the **same CORRELATED_EXPOSURE** (`correlated_exposure()`: the net USD
direction from `usd_direction()` -- long EURUSD/GBPUSD/XAUUSD/BTCUSD/ETHUSD = `USD_SHORT`; long
USDJPY = `USD_LONG`; mirror image for SHORT -- except XAUUSD, which gets its own
`USD_SHORT_SENSITIVE`/`USD_LONG_SENSITIVE` bucket per the signed doc's own example, and is
therefore never pooled with a plain USD-quoted FX pair) are tagged `correlated=True`, grouped
under a deterministic `correlation_cluster_id` (`"<exposure>:<sorted symbols joined by '+'>"`),
and ranked **1..N by friction ascending, then remaining R (R_AT_SEND) descending** as the
tie-break. Friction is the candidate's spread expressed as a fraction of its risk distance (the
same `spread_risk_fraction` concept already used by `v1_tickets.guards.spread_check()`) -- lower
friction ranks first. A candidate with unmeasured friction (`None`) ranks last within its group.
**D7 never changes `classification` or suppresses a send** -- it is a tag and an order, not a
filter; example (the signed "GBPUSD dedup case"): GBPUSD LONG and EURUSD LONG sent in the same
batch are both still `ACTIONABLE`, both tagged `CORRELATED` under cluster id
`"USD_SHORT:EURUSD+GBPUSD"`, with the lower-friction one ranked `#1`.

## Non-scope (explicit)

- **D5** (precision stays display-only; "normalize-at-proposal" recorded as a Demo gate) and
  **D6** (`ST_ASIAN_SWEEP_5R_V1` stays paused) and **D8** (`SESSION_TRADE_V1` Demo authority
  denied) are governance statements already recorded in
  `docs/status/AG_V1_HOST_HARDENING_R1_STATUS.md`; this module intentionally contains no code
  for them.
- This module does not decide **what** gets evaluated (it never produces a POI, a sweep, a
  CHoCH, an entry/stop/target, or a direction) and never calls Telegram or a broker. It is a
  pure classification layer a caller places between an already-produced candidate and a send.
- Crypto candidate tickets routing through this policy (requested alongside
  `AG_CRYPTO_LOGIC_VERIFY_R1`) is **not wired** by this mission -- T2's scope, and the signed
  decision's own context (PR #48's body: "Large-SMC confirmation... sends... at most once"), is
  the Large-SMC watch alert path. `LsmcCandidate`/`MarketQuote`/`classify()` are generic enough
  that a future mission can adapt a crypto ticket's entry/stop/target/direction into this same
  shape, but that adaptation (and any crypto-specific friction/USD-direction nuance, e.g.
  BTCUSD/ETHUSD both being `USD_SHORT` on a LONG) is deliberately left to that future, explicitly
  scoped mission rather than built here as an unrequested substitute.

## Fixtures (named per the owner's T2 instruction)

| Fixture | Decision exercised | Expectation |
|---|---|---|
| "07:01 case" | D1 boundary | fresh at 07:00 (2.0 bars), stale at 07:01 (2.2 bars) |
| "XAUUSD late case" | D1, far past the boundary | XAUUSD evaluated 30 min (6 bars) after trigger close -> `INFO_ONLY` |
| "ETH low-R case" | D2, independent of D1 | ETHUSD fresh (1 bar) but remaining R at the send-time quote is 1.2 (<1.5) -> `INFO_ONLY` |
| "GBPUSD dedup case" | D7 | GBPUSD LONG + EURUSD LONG both ACTIONABLE in the same batch -> both `CORRELATED` under `USD_SHORT`, ranked by friction then R |
