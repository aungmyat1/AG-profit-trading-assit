---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: 2026-11-12
---
# AGP-C15 three-lane logic verification — off-host re-run, 2026-10-12

Fresh L1–L6 re-runs of the three C15 strategy lanes
(`docs/governance/AGP_C15_THREE_STRATEGY_LOGIC_FIRST_2026-10-11.md`), plus the pending
C15-ASW EURUSD L2/L3 failure reproducer and cause classification. Off-host, read-only,
hermetic: committed recorded fixtures only, no broker/network/MT5 call, no rule change, no
registry/READY/demo/live change. Environment: Linux, Python 3.11.2, pinned dependencies
(pyyaml 6.0.3 / numpy 2.2.6 / pandas 2.3.3 / smartmoneyconcepts 0.0.27).

**Lane verdicts do not change any authority.** Every lane below is already
`demo_authorized: false`, `live_authorized: false`, `edge_verified: false`; Large-SMC stays
`ARCHIVE_ONLY` and both crypto versions stay research-only/not admitted.

| Lane | Identity | Freshly reproduced scope | Result |
|---|---|---|---|
| FX / gold | `ST_ASIAN_SWEEP_5R_V1@1.1.2` (`941dec55…`, engine `243c4ff1…`, identity `d7a8ebe5…`) | GBPUSD × ASIAN_LONDON, GBPUSD × LONDON_NEWYORK, EURUSD × LONDON_NEWYORK: L1–L6 PASS; EURUSD × ASIAN_LONDON: **L3 FAIL** (single case 2026-07-31); USDJPY/XAUUSD: 0 valid entries → INSUFFICIENT | S1 (`GBPUSD × ASIAN_LONDON × SWEEP`) is the only admitted scope and still holds; EURUSD remains SUSPENDED |
| Large-SMC | `ST_LARGE_SMC_V1@1.1.0` (contract `78285f9f…` = registry) | BTCUSD (recorded #156) and **ETHUSD (new)**: signal L1–L4/L6 PASS 8,961/8,961; L5 WARN 8,961/8,961; stop geometry NOT_APPLICABLE | **NOT_VERIFIED** for both; operational lane rejects every OPPORTUNITY with `REJECT_NO_STOP` |
| Crypto CFD | `ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0` (canonical `ac116e0a…`) | 60 days, 17,280 scans/symbol, both symbols, all 10 mismatch categories 0 | BTCUSD × SHORT × WEEKDAY PASS; ETHUSD × LONG × WEEKDAY PASS; ETHUSD × SHORT (both windows) gate-PASS but `NOT_VERIFIED` (thin coverage); BTCUSD LONG / all WEEKEND scopes INSUFFICIENT (0 emissions) |

## 1. FX lane — `ST_ASIAN_SWEEP_5R_V1@1.1.2` (AGP-DATA-R3 60-weekday fixture)

Driver: `scripts/asw_v112_60d_replay.py` (unchanged harness; `D60_SYMBOLS` routing).
Evidence: [`AGP_ASW_V112_60D_2026-10-12.json`](AGP_ASW_V112_60D_2026-10-12.json),
sha256 `73c31289…`.

| Symbol | Session | L1 | L2 | L3 | L4 | L5 (lane) | L6 | valid entries |
|---|---|---|---|---|---|---|---|---|
| EURUSD | ASIAN_LONDON | PASS | PASS | **FAIL** | PASS | PASS | PASS | 3 |
| EURUSD | LONDON_NEWYORK | PASS | PASS | PASS | PASS | PASS | PASS | 5 |
| GBPUSD | ASIAN_LONDON | PASS | PASS | PASS | PASS | PASS | PASS | 7 |
| GBPUSD | LONDON_NEWYORK | PASS | PASS | PASS | PASS | PASS | PASS | 4 |
| USDJPY | both | PASS | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS | 0 |
| XAUUSD | both | PASS | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS | 0 |

- Identity binds to the registry S1 record: contract `941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69`,
  engine `243c4ff13b1aabe6a5ccdd3fad0b847f15cbfae99e1608ee1636c4d31c07e959`,
  logic identity `d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5`.
- Reproduction check against the previously recorded 2026-10-10/11 evidence: same verdicts,
  same `valid_entry_case_ids`, same `l3_revised_case_ids`
  (`recorded:EURUSD:ASIAN_LONDON:2026-07-31`). The only difference is L5: the earlier
  matrix recorded `INSUFFICIENT` for EURUSD/GBPUSD, this run records lane L5 `PASS` because
  `OD1011-COMMISSION` is now bound to the host-captured `VTMarkets-Demo` server and the
  cost gate applies it correctly (kept entries 3/5/7/4; spread source `HOST_SNAPSHOT`;
  e.g. GBPUSD ASIAN_LONDON median `spread_R` 0.283, 4 of 7 kept entries `COST_BLOCKED`).
  The harness-level per-symbol L5 remains `WARN`. No rule changed.
- Extra passing windows (EURUSD LONDON_NEWYORK, GBPUSD LONDON_NEWYORK) are **evidence only**:
  the D6 reader admits an exact identity-bound scope only, so nothing outside S1 becomes
  ticket-eligible without a separate owner decision.

## 2. AGP-L3-0731 — EURUSD × ASIAN_LONDON × 2026-07-31 (C15-ASW deliverable)

Reproducer: `scripts/asw_v112_l3_repro_0731.py` (new, calls existing engine/gate code only).
Evidence:
`artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c15_l3_repro_2026-10-12/l3_repro_eurusd_asian_london_2026-07-31.json`.

Observed mechanism (all values from the recorded fixture, box high 1.15266 / low 1.15044):

| Prefix | Emission | Entry | Stop | Risk | Signal bar |
|---|---|---|---|---|---|
| k=7 (first direction) | `RANGE` / `LOWER_BOUNDARY_REJECTION` | 1.15044 (= box low) | 1.15044 (= candle low) | **0.0** | 08:30 |
| full window | `SWEEP` / `LOWER_SWEEP_STRICT_PENETRATION` | 1.15035 (= min(open, close)) | 1.15035 (= candle low) | **0.0** | 09:45 |

The 08:45-through-09:45 bars repaint the day's ticket: `setup`, `entry`, `stop_loss`,
`signal_timestamp` and `targets` all change (25/25 future mutations change the semantic,
5 prefix mismatches, `signal_id` unchanged). Per-candle qualification shows why the
**zero risk** arises:

- 08:30 bar (o 1.15075 / l 1.15044 / c 1.15092): Entry 3 uses an *inclusive* boundary touch
  (`low <= box_low`) and sets `entry = box_low`, `stop = candle.low` → 1.15044 − 1.15044 = 0.
- 09:45 bar (o 1.15035 / l 1.15035 / c 1.15055): Entry 2 sets `entry = min(open, close)`,
  `stop = candle.low`; the bar opened at its low, so both are 1.15035 → 0.
- Entry 1–3 precedence is evaluated over the whole window on every scan: Entry 2 qualifies
  only from 09:45, so the earlier valid RANGE signal is superseded rather than appended.

**Cause classification (data / rule / implementation):**

- **Data — no defect.** The bars are legitimate recorded VT bars; the patterns are an exact
  boundary touch and a bar opening at its extreme. Nothing is corrupt, missing or inferred.
- **Rule — declaration/implementation divergence (already recorded as the v1.1.2 L2 reasons).**
  Declared entry `Sweep_Candle_Body_Close` ≠ engine `min/max(open, close)`; declared stop
  (25% of reference range) ≠ engine `candle.low`; Entry 3 uses `<=` where Entry 2 requires
  strict penetration `<`. Neither the declared nor the implemented rule forbids
  `risk_distance == 0`, so a legitimate price pattern yields a zero-risk signal.
- **Implementation — two bounded defects.** (a) `setups.entry_2_sweep` / `entry_3_range`
  return `VALID` with `risk_distance == 0`; only the downstream gates catch it (the ticket
  is `TICKET_BLOCKED` with `positive_stop: false`, so the fail-closed chain does hold — no
  degenerate ticket can become READY). (b) The day-scoped `signal_id` is reused across
  qualifying bars, and window-wide re-evaluation means a later qualifying sweep replaces an
  earlier valid range-rejection emission (non-append-only emission), which is what trips L3.

**Severity:** the two repainted emissions both carry zero stop distance and are `STALE` at
the harness's evaluation time, so no deliverable, correctly-geometried ticket was repainted
away on this date. The gate fails closed on identity, as designed — this is why EURUSD is
SUSPENDED rather than admitted. A fix requires an owner-approved strategy contract change
(reject zero/negative risk; make the signal stream append-only per qualifying bar; or define
which branch wins across time) — **not** a verification-side relaxation.

## 3. Large-SMC lane — `ST_LARGE_SMC_V1@1.1.0`

Driver: `scripts/lsmc_c15_symbol_replay.py`. BTCUSD result (#156) was read back from the
committed report and verified against the same dataset hashes; **ETHUSD was run fresh** this
session: `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_ethusd_vt_recorded_60d/replay_report.json`,
sha256 `97ba1a49…` (about 25 minutes; report is byte-reproducible and carries no wall-clock field).

| Symbol | Signal L1–L4/L6 (8,961 full-D1 scans) | L5 | Stop geometry | Operational lane |
|---|---|---|---|---|
| BTCUSD | PASS 8,961/8,961; streaming/prefix parity 0 mismatches | WARN 8,961 | NOT_APPLICABLE (`C10_PIP_SIZE_NOT_EVIDENCED`) | `REJECT_NO_STOP` 2,923/2,923 OPPORTUNITY scans |
| ETHUSD | PASS 8,961/8,961; streaming/prefix parity 0 mismatches | WARN 8,961 | NOT_APPLICABLE (`C10_PIP_SIZE_NOT_EVIDENCED`) | `REJECT_NO_STOP` 1,940/1,940 OPPORTUNITY scans |

- Verdict **NOT_VERIFIED** for both, with the same three reasons: L5 WARN (no stop distance,
  commission unbound off-host, no cost gate in the 1.1.0 alert path), stop geometry
  NOT_APPLICABLE, and a fully rejecting operational lane. No instrument can emit a
  deliverable opportunity under 1.1.0 as bound.
- Dataset identity: `tests/fixtures/ccfd_v100/recorded_60d`, `VTMarkets-Demo`, 60 D1 /
  1,412 H1 / 16,932 M5 bars, 2026-08-11 → 2026-10-09, per-bar spread (16,932/16,932).
  ETHUSD host-snapshot spread 2.5 (BTCUSD 17.02), point 0.01.
- Engine-hash drift WARN is unchanged and applies to both symbols: gate-method engine
  `88dd9f1f…` ≠ registry `ec0b2f3d…` (the `watch.py` delivery-gate change of 2026-10-10).
  Contract hash matches registry (`78285f9f…`); detection files unchanged.
- Resolution path is an owner input, not code: BTCUSD/ETHUSD C10 pip (stop) evidence and a
  Large-SMC cost gate. Per the C15-LSMC exit condition, ETHUSD is published as **BLOCKED
  with cause**, not admitted.

## 4. Crypto CFD lane — `ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0`

Driver: `scripts/ccfd_sweep_retest_replay.py --dataset recorded_60d --strategy-version 1.1.0`.
Evidence (fresh, both symbols, does not overwrite the earlier recorded artifacts):
`artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0/vt_recorded_60d_reverify_2026-10-12/`,
replay report sha256 `ffb2ec16…`.

60 days, 17,280 scans per symbol, every manifest sha256 verified before use; every mismatch
category is **0** for both symbols (10 categories for BTCUSD; 11 for ETHUSD, which adds
`reissue_expiry`) — the recorded scope table reproduces exactly:

| Symbol × direction × window | L1–L6 | Entry-valid scans | Emissions | Withdrawn | Status |
|---|---|---:|---:|---:|---|
| BTCUSD × SHORT × WEEKDAY | all PASS | 77 | 2 | 0 | **PASS** |
| ETHUSD × LONG × WEEKDAY | all PASS | 354 | 3 | 0 | **PASS** |
| ETHUSD × SHORT × WEEKDAY | all PASS | 72 | 1 | 0 | NOT_VERIFIED |
| ETHUSD × SHORT × WEEKEND | all PASS | 175 | 1 | 0 | NOT_VERIFIED |
| BTCUSD LONG (both windows), BTCUSD WEEKEND SHORT, ETHUSD LONG WEEKEND | L1 PASS, L2–L6 INSUFFICIENT | 0 | 0 | 0 | NOT_VERIFIED |

- `registry.modified: false`, `logic_verified_claim: false`,
  `candidate_runtime_binding: NOT_ADMITTED_RESEARCH_ONLY`, runtime engine
  `0a3886eb…` matches the candidate identity, and the loader still loads registered **1.0.0**
  (unchanged, still `STALE_IDENTITY` in the registry).
- Open identity discrepancy (pre-existing, unresolved): the canonical frozen contract hash
  recomputed here is `ac116e0aadcca33238d0ce2d2b327368f0faa3a6bfb6f8cfdd2cf5222ca6ecf7`,
  which does not match the `9a1f6759…` value requested in the original PR handoff.
  Independent review must resolve this before any verification authority is considered.
- Thin coverage is the blocker on the two gate-PASS ETHUSD SHORT scopes (1 emission each vs
  a 2-emission minimum); weekend/BTCUSD-LONG scopes have zero emissions, so entry gates are
  simply not exercised. Zero emissions do not exercise entry gates and are never reported as
  PASS.

## 5. Invariants held by this record

- No strategy rule, contract, threshold or gate was changed, relaxed or bypassed.
- No registry, READY, demo or live authority changed; production READY remains OFF;
  `demo_authorized=false` and `live_authorized=false` for all three lanes.
- No broker/network/MT5 call (`broker_calls: 0`, `ORDER_API_CALLS: 0`,
  `BROKER_MUTATION_COUNT: 0` in every artifact); Large-SMC delivery stays `ARCHIVE_ONLY`.
- Logic verification remains distinct from `EDGE_VERIFIED`; every artifact carries
  `edge_verified: false`.

## 6. Reproduce

```sh
# FX lane: 60-weekday matrix (seconds)
python scripts/asw_v112_60d_replay.py --date 2026-10-12 --out docs/status/AGP_ASW_V112_60D_2026-10-12.json

# EURUSD 2026-07-31 L3 reproducer (seconds)
python scripts/asw_v112_l3_repro_0731.py --symbol EURUSD --cycle ASIAN_LONDON --date 2026-07-31 \
  --dataset d60 --out artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c15_l3_repro_2026-10-12/l3_repro_eurusd_asian_london_2026-07-31.json

# Large-SMC ETHUSD replay (~25 minutes)
python scripts/lsmc_c15_symbol_replay.py --symbol ETHUSD \
  --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_ethusd_vt_recorded_60d/replay_report.json

# Crypto CFD 60-day replay, both symbols (~17 minutes)
python scripts/ccfd_sweep_retest_replay.py --date 2026-10-12 --dataset recorded_60d \
  --strategy-version 1.1.0 \
  --out-dir artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0/vt_recorded_60d_reverify_2026-10-12
```

## 7. Open items (owner decisions, not verification actions)

1. **EURUSD L3 repaint (AGP-L3-0731)** — cause is now classified (section 2). Closing it
   requires an owner-approved contract/implementation change: reject zero/negative risk
   distance, make the per-day signal stream append-only (or define cross-branch precedence
   in time). Until then EURUSD stays SUSPENDED and D6 stays OFF.
2. **Large-SMC stop geometry** — needs owner-approved C10 pip/stop evidence for BTCUSD and
   ETHUSD plus a cost gate in the alert path; without it every crypto opportunity is
   `REJECT_NO_STOP` by construction.
3. **Crypto contract-hash discrepancy** — `ac116e0a…` (recomputed) vs `9a1f6759…` (handoff).
4. **Registered crypto version** — `1.0.0` carries `STALE_IDENTITY`; re-recording or
   re-verification is a separate owner-governed change.
5. **Large-SMC engine drift** — `watch.py` moved the delivery gate inside the engine
   (`88dd9f1f…` ≠ registry `ec0b2f3d…`); either re-record the identity or move the gate back
   to the post-signal layer.
