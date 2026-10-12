---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: 2026-11-12
---
# C16 — `ST_ASIAN_SWEEP_5R_V1@1.1.3` correction proposal (D-ASW-1, D-ASW-2)

**Status: PROPOSAL ONLY. Not implemented, not registered, no authority.** This document and
`strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml` are a *declaration* of the two bounded defects
C15 and C16 independently reproduced at `recorded:EURUSD:ASIAN_LONDON:2026-07-31`, plus the
exact rule text that would close them. No engine, registry, READY, demo, live, broker or
threshold surface changes. `ST_ASIAN_SWEEP_5R_V1@1.1.2` is left byte-identical.

## 1. Why this is a new version and not a patch

`AGENTS.md` → *Frozen strategy version preservation*:

> Do not modify a frozen production or current-authority strategy version in place. A
> behavior-changing correction must be implemented in a new candidate strategy version and may
> replace the current authority only after explicit validation and promotion.

Both defects below are behaviour-changing if corrected at the decision point, so they must
land in a successor candidate. `strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml` is unmodified;
its raw sha256 stays `4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf` and its
canonical identity stays `941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69`.

## 2. D-ASW-1 — zero (and negative) risk distance emitted as `VALID`

| | |
|---|---|
| Site | `src/strategy_engine/session/setups.py` → `entry_2_sweep`, `entry_3_range` |
| Classification | **Implementation defect against the v1.1.2 declaration** (an L2 divergence) — not a missing rule |
| Observed | `decision_status = VALID` with `risk_distance == 0.0` |
| Fail-closed today? | Yes, but only *downstream*: the ticket is `TICKET_BLOCKED` with `positive_stop: false`, so no degenerate ticket can reach READY |

Two exact triggers, both from ordinary recorded bars (no corruption, no inference):

- `entry_3_range` LONG: the test is `candle.low <= box.session_low` (**inclusive**) and it sets
  `entry_reference = box.session_low`, `stop_reference = candle.low`. An exact boundary touch
  therefore gives `entry == stop` → `risk_distance = box.session_low - candle.low = 0.0`.
  Reproduced with 08:30 bar `o 1.15075 / l 1.15044 / c 1.15092` against box low `1.15044`.
- `entry_2_sweep` LONG: `entry_reference = min(open, close)`, `stop_reference = candle.low`. A
  sweep candle that **opens at its own low** and closes back up gives `min(open, close) == low`
  → `risk_distance = 0.0`. Reproduced with 09:45 bar `o 1.15035 / l 1.15035 / c 1.15055`.

**The rule already exists in v1.1.2.** `risk_and_money_management.min_risk_distance: POSITIVE`
with the inline rule `# risk_distance <= 0 -> FAIL_CLOSED`, and the v1.1.1→v1.1.2 changelog
rows `B-STOP` (*"Zero/negative risk distance is undefined -> FAIL_CLOSED"*) and `B-MINRANGE`
(*"risk_distance must be > 0"*). The engine simply does not enforce its own frozen
declaration. That is why this is an implementation gap rather than a rule gap — and why the
proposal changes **no threshold and invents no stop-loss formula**: the whole rule is the
existing boundary "a non-positive risk distance is undefined behaviour → no candidate".

### Proposed v1.1.3 text
```yaml
risk_and_money_management:
  min_risk_distance: STRICTLY_POSITIVE
  non_positive_risk_action: FAIL_CLOSED
```
with `decision_status_on_violation: NO_SETUP` — enforced where the decision is made, so the
degenerate emission never exists, instead of being caught only by the gates.

## 3. D-ASW-2 — non-append-only per-day signal stream (repaint)

| | |
|---|---|
| Site | `src/strategy_engine/session/router.py::route_completed_session` |
| Classification | **Implementation defect** (emission identity/semantics), owner must choose the precedence rule |
| Observed at 2026-07-31 | 16 bars, `first_emission_prefix_len 7`, `future_mutations 25`, `future_mutation_mismatches 25`, `prefix_mismatches 5`, `pre_emission_signals 0`, `streaming_hash_parity true` |
| Repainted fields | `setup_type`, `reason_code`, `signal_timestamp`, `entry_reference`, `stop_reference` (`signal_id` reused — day-scoped) |

`route_completed_session` is documented as *one-shot*, and it evaluates `entry_2_sweep` before
`entry_3_range` over the **whole** supplied `post_session_candles` slice. As the trading window
grows, the same day is re-routed from scratch:

- prefix ending 08:30 → `RANGE / LOWER_BOUNDARY_REJECTION`, risk `0.0`;
- prefix ending 09:45 → `SWEEP / LOWER_SWEEP_STRICT_PENETRATION`, risk `0.0`.

The earlier emission is not preserved anywhere; the harness's day-scoped `signal_id` is reused,
so an observer holding the first emission sees its content change. Both repainted emissions on
this date carried zero risk and were `STALE` at evaluation time, so no correctly-geometried
deliverable ticket was rewritten — the severity is an identity/causality defect, not (on this
date) a ticket-integrity one. It still trips L3 by construction.

### Proposed v1.1.3 text
```yaml
signal_stream:
  mode: APPEND_ONLY
  identity: PER_QUALIFYING_BAR
  republish_action: FORBIDDEN
  later_qualification_action: APPEND_NEW_EMISSION
  unfilled_invalidation_action: APPEND_WITHDRAWN
  filled_signal_action: IMMUTABLE
  cross_branch_precedence: BY_EMISSION_TIME
```
The owner may instead prefer an explicit **static** cross-branch precedence. Either choice is
a rule the owner must sign; the defect is the *silent replacement*, not the branch order
itself.

## 4. Why the engine change is deliberately not part of this proposal

`strategy_engine/session/*` is **shared** by the frozen v1.1.1 authority and the v1.1.2
candidate. Editing it in place moves the registry-bound S1 identity
`d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5` (engine
`243c4ff1…`), which would silently invalidate the only admitted scope. Enforcing D-ASW-1/D-ASW-2
therefore needs an owner decision *plus* a new identity record, and the change must be
delivered behind the successor version rather than as a shared-engine edit.

## 5. Evidence and reproduction

| Artifact | Path | sha256 |
|---|---|---|
| C16 60-weekday matrix (run 1) | `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c16_2026-10-12/asw_v112_60d_c16_run1.json` | `8a529ae4…` |
| C16 60-weekday matrix (run 2, independent) | `…/asw_v112_60d_c16_run2.json` | `8a529ae4…` (byte-identical to run 1) |
| C16 L3 reproducer | `…/l3_repro_eurusd_asian_london_2026-07-31_c16.json` | `a84a0a4d…` (byte-identical to the C15 reproducer) |
| Regression pin + successor contract tests | `tests/test_asw_v113_zero_risk_append_only.py` | 12 passed |
| Successor contract | `strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml` | declaration only |

```sh
.venv/bin/python scripts/asw_v112_60d_replay.py --date 2026-10-12 \
  --out artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c16_2026-10-12/asw_v112_60d_c16_run1.json
.venv/bin/python scripts/asw_v112_l3_repro_0731.py --symbol EURUSD --cycle ASIAN_LONDON \
  --date 2026-07-31 --dataset d60 \
  --out artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/c16_2026-10-12/l3_repro_eurusd_asian_london_2026-07-31_c16.json
.venv/bin/python -m pytest tests/test_asw_v113_zero_risk_append_only.py -q
```

## 6. Authority statement

- `ST_ASIAN_SWEEP_5R_V1@1.1.2` remains `CANDIDATE_PENDING_OWNER_CONFIRM`; **no v1.1.2 scope
  changes verdict.** EURUSD stays `SUSPENDED` (`L3_REPAINT_UNRESOLVED_2026-07-31`) and the S1
  scope (GBPUSD × ASIAN_LONDON × RANGE_SWEEP) stays `LOGIC_VERIFIED` **for v1.1.2 only**.
- `ST_ASIAN_SWEEP_5R_V1@1.1.3` inherits **nothing**: `inherits_identity_from: null`,
  `v112_pass_scopes_remain_not_verified: true`, `reverification_required_before_any_pass: true`.
- No registry entry, no READY promotion, no demo/live authorization, no broker mutation.
  A logical-verification result never grants execution permission (C14 demo execution is out of
  scope for this mission).
