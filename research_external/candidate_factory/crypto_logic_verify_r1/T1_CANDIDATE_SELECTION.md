# T1 — Crypto Candidate Selection (AG_CRYPTO_LOGIC_VERIFY_R1)

## Governance / input verification (done first, per mission instruction)

- `MAIN_SHA` resolved live from `origin/main` at runtime: `fc60cdbf603146b1408dba9184e6c146bdcf4ea5`.
- **VT Markets BTCUSD/ETHUSD data pack from `AG_V1_HOST_HARDENING_R1` T4: DOES NOT EXIST in
  this checkout.** Searched `origin/main`, both open PR branches referenced by this
  engagement (`arena/3b8a0571-...` PR #45, this session's own branch PR #46), and every
  other currently-open PR (`gh pr list`: #48, #44, #36, #34, #33, #32, #31, #30, #20, #19,
  #18, #17, #11, #1) for any file or manifest naming `AG_V1_HOST_HARDENING_R1` or any new
  BTCUSD/ETHUSD OHLC file — zero hits. **No manifest hash exists to verify.**
  `HOST_DATA_NOT_VERIFIED` (not `NO_DATA_EXISTS` — the host mission may simply not have
  landed/pushed yet).
- Per the mission's own instruction, this blocks **real DEV replay** of OSS_CRYPTO_C001/C002
  against VT data. **T1's "re-run on the VT data" sub-task is `HOLD_DATA`.** Per the mission's
  explicit fallback ("until it lands, build everything on fixtures only — do NOT substitute
  exchange data as ticket evidence"), candidate selection below uses (a) the existing PR #46
  rule-extraction evidence (unchanged, not re-litigated) and (b) small synthetic fixture
  scenarios to compare rule clarity/structure — **never** real Bybit/Binance perpetual data
  presented as if it were VT CFD evidence.
- Related discovery (recorded, not acted on without owner input): PR #30
  (`ST_CRYPTO_CFD_SWEEP_RETEST_V1`, open, not merged) and PR #31 (eligibility/quarantine
  layer over immutable-but-checkout-absent BTCUSD/ETHUSD CFD parquet) already define a
  dedicated, swing/BOS/sweep-based internal BTCUSD/ETHUSD CFD contract — distinct from
  OSS_CRYPTO_C001/C002. This mission's T1 is explicitly scoped to C001/C002 only; PR #30/#31
  are out of scope here and are not touched, merged, or treated as a candidate.

## Candidates under comparison (unchanged identities from PR #46)

| | OSS_CRYPTO_C001 (Donchian/Turtle System Two) | OSS_CRYPTO_C002 (freqtrade DoubleEMACrossoverWithTrend) |
|---|---|---|
| Source evidence class | SB5 (explicit in-sample/out-of-sample backtest reported by source) | SB3 (code+data period identified; exact params never extracted) |
| G1 Contractable | PASS — exact N=55/M=20/ATR=20 entry/exit/sizing formulas | HOLD_SPEC — exact EMA periods/trend filter never read from source file |
| G2 Ticketable (as sourced) | FAIL_AS_SOURCED — continuously-held trend position, rolling-exit, no single fixed TP | FAIL_AS_SOURCED_PRESUMED — freqtrade ROI-table/trailing-exit paradigm presumed, not confirmed |
| License | LICENSE_UNKNOWN (rule-extraction only, no code reuse) | MIT (confirmed) |
| Venue match | FUTURES source, not CFD/spot — translation required regardless | Spot-exchange implied (unconfirmed) — translation required regardless |
| Rule clarity (fixture-based review) | HIGH — every parameter and threshold is a fixed, stated number; no ambiguity in entry/exit condition definitions | LOW — the single most consequential fact (EMA periods, exit paradigm) is unresolved; cannot even write pseudocode without guessing |

## Fixture-based structural comparison (performed; no real market data needed for this part)

Three small synthetic OHLC fixtures (clean uptrend breakout, clean downtrend breakout,
flat/ranging — see `fixtures/`) were used only to check that each candidate's *rule text*
is unambiguous enough to produce a deterministic signal count without guessing a missing
parameter:

- **C001 (Donchian/Turtle)**: fully computable on all three fixtures — breakout-above-N,
  breakout-below-N, and "no breakout in a range" are all mechanically decidable from the
  stated rule. Signal count is deterministic given the fixture.
  - **Weekend behavior**: the source rule is silent on market closure (written for
    continuously-traded futures). This repo already has an operational precedent for VT
    Markets BTCUSD/ETHUSD tickets (`config/v1_tickets/crypto_ticket_v2.yaml`:
    `window.kind: LOCAL_WEEKDAY`, Mon–Fri 09:00–12:00 America/New_York, "no weekend runs").
    T2 reuses this existing precedent rather than inventing a new one.
- **C002 (freqtrade EMA cross)**: NOT mechanically computable — the exact EMA periods and
  "with trend" filter condition are unknown (recorded as such in PR #46, not re-derived
  here since the source `.py` body still was not fetched this mission either, consistent
  with the EXTERNAL CODE RULE against importing/executing the source repo). Any signal
  count produced would require guessing a parameter, which this mission will not do.
  - **Weekend behavior**: cannot be meaningfully assessed when the entry rule itself is
    undefined.

## Decision

**PRIMARY CANDIDATE: OSS_CRYPTO_C001 (Donchian/Turtle System Two breakout)**, via a new,
explicitly-labeled **derived candidate** (see T2) that translates its continuously-held
position management into a discrete ticket (fixed initial stop + fixed target + expiry).
This is a deliberate, declared translation — not a silent rewrite to force a gate pass —
per the standing rule against silently rewriting a candidate to pass G2.

**REJECTED: OSS_CRYPTO_C002 (freqtrade DoubleEMACrossoverWithTrend)**
Reason: G1 `HOLD_SPEC` was never resolved (exact entry rule parameters unknown), which
is a strictly worse starting position than C001's single, already-labeled G2 translation
gap. Building a frozen ticket spec on an unknown rule would require inventing parameters
not present in any source — explicitly disallowed. C002 remains `HOLD_DATA`/`HOLD_SPEC`
in its PR #46 record, unchanged; it is not re-scored here, only not selected.

## Gate result

```
T1 = HOLD (partial PASS)
```
Candidate selection and rejection reasoning: **PASS** (complete, evidence-based, no data
needed). Real DEV-replay signal counts against actual VT Markets BTCUSD/ETHUSD OHLC:
**HOLD_DATA** (blocked — data pack not present in this checkout; re-run required once it
lands and its manifest hashes can be verified).
