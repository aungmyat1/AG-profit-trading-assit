---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: 2026-11-12
---
# C16 defect register

Every entry is reproducible from committed inputs. Verdicts in
`C16_FINAL_SCOPE_MATRIX.json`. No defect listed here was fixed by weakening a gate, changing a
threshold, editing a frozen contract, or touching a registry/READY/demo/live surface.

**Nothing in this register grants execution permission.** Logical verification, economic-edge
verification, runtime READY, demo authorization and live authorization remain independent
states.

`D-LSMC-6` … `D-LSMC-10` were added on 2026-10-13 by the C15-LSMC follow-up independent logic
audit, completed the same day under **AGP-C17-LSMC-LOGIC-COMPLETION-R1**
(`docs/status/AGP_C15_LSMC_V110_LOGIC_AUDIT_2026-10-13.md`, machine report
`artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/lsmc_v110_logic_audit.json`,
delivery record `docs/status/AGP_C17_LSMC_LOGIC_COMPLETION_R1_2026-10-13.md`). Each of the eight open
`D-LSMC-*` entries now carries a classification against the five mission classes (implementation /
strategy-contract / data / metadata / verification-harness) and a route — see `phase_b.rows` in the machine
report and §3 of the audit document.
They continue this register's `D-LSMC-*` id space so it stays the single index; every C16 entry
above is unchanged, and no committed C15/C16 evidence file was rewritten.

| ID | Severity | Strategy | Class | Status |
|---|---|---|---|---|
| `GOVERNANCE-180` | BLOCKER (authority) | — | process / governance | **CLOSED — owner merged #180 (`7dfc8a20`)** |
| `GOVERNANCE-181` | — (record) | — | process / governance | **CLOSED — owner merged #181 (`0278653`); blocked state retained in main history** |
| `D-ASW-1` | HIGH | ASW 1.1.2 | implementation vs declaration | OPEN — v1.1.3 proposed |
| `D-ASW-2` | HIGH | ASW 1.1.2 | implementation (identity/causality) | OPEN — v1.1.3 proposed |
| `D-ASW-3` | MEDIUM | ASW 1.1.2 | missing host evidence | OPEN — owner input |
| `D-LSMC-1` | MEDIUM (by design) | LSMC 1.1.0 | missing host/broker evidence (**METADATA**) | OPEN — owner input; no fix is proposed that would invent a pip size |
| `D-LSMC-2` | LOW | LSMC 1.1.0 | stale contract pointer | OPEN — bounded fix available |
| `D-LSMC-3` | MEDIUM | LSMC 1.1.0 | identity-record staleness | OPEN — owner input |
| `D-LSMC-4` | MEDIUM | LSMC 1.1.0 | missing authority adapter | OPEN — owner input |
| `D-LSMC-5` | MEDIUM | LSMC 1.1.0 | L5 cost evidence | OPEN — owner input |
| `D-LSMC-6` | MEDIUM | LSMC 1.1.0 | declaration vs implementation (unit of a frozen rule) (**IMPLEMENTATION**) | OPEN — owner decision; candidate `1.1.2` prepared, FX-only, conservative direction |
| `D-LSMC-7` | MEDIUM | LSMC 1.1.0 | harness vacuity + undeclared contract state | **HALF FIXED 2026-10-13** (harness); `REJECTED` state still undeclared |
| `D-LSMC-8` | MEDIUM | LSMC 1.1.0 | evidence fixture defect | **FIXED 2026-10-13** (bars byte-identical; guard added) |
| `D-LSMC-9` | LOW | LSMC 1.1.0 | reporting (gate status read as coverage) | ROOT-CAUSED — fresh reports carry `check_coverage`; committed evidence untouched |
| `D-LSMC-10` | LOW | LSMC 1.1.0 | import boundary / packaging | OPEN — bounded packaging fix; owner decision |
| `D-CCFD-1` | LOW | CCFD 1.1.0 | documentation vs implementation | ROOT-CAUSED — doc fix available |
| `D-CCFD-2` | MEDIUM (identity bookkeeping) | CCFD 1.1.0 | cross-revision raw-file vs canonical identity | **RESOLVED BY ROOT CAUSE** |
| `D-CCFD-3` | MEDIUM | CCFD 1.0.0 | identity staleness (pre-existing C15) | OPEN — owner input |
| `D-CCFD-2b` | MEDIUM (documentation) | — | documentation / identity naming | OPEN — bounded docs fix; canonical identity untouched |
| `OBS-CCFD-1` | — (observation) | CCFD 1.1.0 | C15-original vs C16 engine identity | **EXPLAINED BY ROOT CAUSE** |

---

## GOVERNANCE-180 — resource authority restored; now on main

`RESOURCE-AUTHORITY-01` from PR #181 is resolved. The owner-issued policy, guard and tests were
restored byte-identically from `82e6e5cca329d1247f8a81aa308f25a80584c5fd` on PR #180 (head
`d28cacb74eec3cc3ba217ccd6892904fd000bf3a`); the guard passed 19/19 focused tests plus nine
end-to-end behaviour drills, and CI was green. At that point the policy was **not on main** and
**no owner approval was recorded**, so the agent left #180 reviewable and unmerged and reported
`GOVERNANCE_READY_FOR_OWNER_APPROVAL`, pinning those exact bytes for the campaign.

**Update:** the owner has since merged PR #180 as `7dfc8a20`. Main is now
`a8271feadbd3f0a78aef7b2cd8e814e8362534ea` and holds byte-identical copies of all three files
(policy `8bba5dba…`, guard `0970ebb1…`, tests `1122e0c3…`, verified by sha256 against the
historical source). The merge landed after the C16 replays had started, so no replay was
retro-fitted to it. Every identity the campaign pinned was recomputed at the new main tip and is
unchanged (`ASW engine 243c4ff1…`, `ASW v1.1.2 contract 941dec55…`, `CCFD engine 0a3886eb…`),
so the C16 verdicts hold at `a8271fea` too. Status: **CLOSED — governance on main.**

## GOVERNANCE-181 — blocked-state evidence landed on main

PR #181 (`codex/c16-blocked-verification-evidence`, head `666035d7…`) carried the C16 deliverables
in their **blocked** state and was merged by the owner as `0278653`; PR #182 followed as
`d6b150a`. That record was deliberately left untouched: it documents, accurately, that at
16:13:12 UTC the campaign could not proceed because resource authority was not yet established,
and its `scopes: []` matrix is the honest state for that moment. The completed campaign arrives in
a **separate, reviewable PR** that rewrites nothing retroactively — the diff between the two states
is the evidence that the blocker was cleared rather than the blocker being edited away. No
strategy rule, contract, threshold, registry entry or authorization changed in either landing.

## D-ASW-1 — zero (and negative) risk distance emitted as `VALID`

`src/strategy_engine/session/setups.py` → `entry_2_sweep` / `entry_3_range` return
`decision_status=VALID` with `risk_distance == 0.0`. The v1.1.2 contract already declares
`min_risk_distance: POSITIVE  # risk_distance <= 0 -> FAIL_CLOSED`, so this is the engine
contradicting its own frozen declaration (an L2 divergence), not a missing rule. Triggers:
an inclusive `low <= box_low` boundary touch (`entry_3_range`), and a sweep candle that opens
at its own low (`entry_2_sweep`). Downstream gates already fail closed (ticket
`TICKET_BLOCKED`, `positive_stop: false`), so no degenerate ticket can reach READY. Correction
routed to `ST_ASIAN_SWEEP_5R_V1@1.1.3` (proposal only). Pinned by
`tests/test_asw_v113_zero_risk_append_only.py`. Evidence: `C16_ASW_V113_CORRECTION_PROPOSAL.md`.

## D-ASW-2 — non-append-only per-day emission (repaint)

`src/strategy_engine/session/router.py::route_completed_session` is one-shot and re-evaluates
Entry 2 before Entry 3 across the whole growing post-session window, so on 2026-07-31 a later
qualifying sweep replaced an earlier valid range-rejection emission while the day-scoped
`signal_id` was reused: 25/25 future mutations changed the semantic, 5 prefix mismatches.
Both repainted emissions carried zero risk and were `STALE`, so no correctly-geometried
deliverable ticket was rewritten; severity is identity/causality. Correction routed to v1.1.3.
Evidence: `l3_repro_eurusd_asian_london_2026-07-31_c16.json` (byte-identical to the C15
reproducer).

## D-ASW-3 — USDJPY/XAUUSD L5 has no evidenced pip size

The lane L5 FAILs for both symbols with `SYMBOL_EVIDENCE_MISSING: pip size not evidenced for
['USDJPY'] / ['XAUUSD']`, and warns `SYMBOL_METADATA_PENDING: USDJPY, XAUUSD ->
PENDING_AGP-C2-SYMMAP (not invented)`. No value was invented. Both symbols also emit 0 valid
entries, so their entry gates are unexercised regardless.

## D-LSMC-1 — `REJECT_NO_STOP` is fail-closed missing evidence, not a missing rule

**This is the Phase 3 stop-loss question, answered.** The C10 stop rule is *not* missing:

- `strategies/ST_LARGE_SMC_V1.yaml::stop_loss_contract` defines it: contract
  `C10_STRUCTURAL_INVALIDATION_V1`, `status: SIGNED_AND_LOCKED`, buffer policy
  `DYNAMIC_ATR_WITH_HARD_FLOOR` (`atr_multiplier 0.35`, `min_buffer_pips 1.5`), side-aware
  spread handling, `min_stop_violation_action: REJECT` (*never WIDEN*), and
  `atr_not_ready_action: FAIL_CLOSED`.
- The implementation exists at `src/large_smc_core/c10_stop_policy.py`.
- `src/large_smc_watch/contract.py:53` carries the exact cause in its own comment:
  `# C10's hard floor is expressed in pips; a pip is only evidenced for 5-digit FX majors.`
  `C10_PIP_SIZE = {"EURUSD": 0.0001, "GBPUSD": 0.0001}`.
- `src/large_smc_watch/watch.py:240-242` therefore takes
  `stop_reason = "C10_PIP_SIZE_NOT_EVIDENCED"` with `stop = None` for BTCUSD/ETHUSD, and
  `watch.py:79-81` turns that into `REJECT_NO_STOP`. The 1.1.0 contract lists all six
  instruments (`instruments: [EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD]`), so the crypto
  symbols are in scope while the geometry input they need is not evidenced.

**Classification against the five permitted causes:**
1. missing contract rule — **no** (C10 is signed, locked and implemented);
2. implementation defect — **no** for the stop computation, which is present and guarded;
3. invalid signal — **no** (detection L1–L4/L6 pass 8,961/8,961 per symbol);
4. **missing market/broker metadata — YES, this is the cause** (no evidenced pip size for the
   crypto CFDs);
5. intentional information-only signal — **no** (the contract intends a real stop:
   `min_stop_violation_action: REJECT`, never widen).

**No stop-loss formula was invented.** Because the fix needs owner-supplied C10 pip/stop
evidence for BTCUSD and ETHUSD, the affected scopes stay `NOT_VERIFIED`; a versioned
correction cannot be authored by an agent without inventing the missing number. Note the
CFD contract itself forbids importing FX pip conventions or perp tick models
(`spread_cost_policy.units: [BROKER_POINTS, PRICE, PERCENT]`, `FX pip conventions FORBIDDEN`),
so the value must come from verified broker symbol metadata.

**2026-10-13 follow-up (C15-LSMC audit).** Still OPEN and still blocking, with two clarifications.
(a) New FX-side evidence that the rule *works* where a pip is evidenced: on 575 rolling scans of the
host-captured EURUSD fixture the engine produced three distinct opportunities, two with computed C10
stops sitting exactly `MIN_BUFFER_PIPS × PIP_SIZE_EURUSD` = 1.5 pips beyond the sweep extreme and passing
`L3.stop_side` / `L3.stop_beyond_sweep`, and one SHORT whose stop is `None` with `MISSING_SPREAD` — the
side-aware verified-live-spread requirement failing closed rather than guessing
(`findings[D-LSMC-1].evidence.eurusd_lane_b`). (b) Point 3 above cites "detection L1–L4/L6 pass
8,961/8,961 per symbol"; read that with **D-LSMC-9** — those are gate statuses, and on 6,921 (BTCUSD) /
8,113 (ETHUSD) of those scans every opportunity rule was NOT_APPLICABLE. The C16 text is left as written.

**2026-10-13 AGP-C17 classification: METADATA.** Not an implementation defect and not a contract defect:
`large_smc_core.c10_stop_policy.compute_c10_stop` is correct, and `contract.C10_PIP_SIZE` is deliberately
restricted to owner-evidenced pips. No fix is applied and none is proposed that would invent a pip size —
that would fabricate broker metadata, which is exactly what the fail-closed gate exists to prevent.
`strategies/ST_LARGE_SMC_V1_1_1_1.yaml::pip_size_rules` already proposes FX `10 × host_captured_point`,
XAUUSD `0.1`, BTCUSD `1.0` and ETHUSD `0.1`, each `PENDING_OWNER_CONFIRM` with
`apply_before_owner_confirmation: false`; the audit's positive control measures exactly `10 × point` for
EURUSD, i.e. what the FX proposal would produce once confirmed. Owner route: confirm the pip rules, or
supply host captures for USDJPY/XAUUSD/BTCUSD/ETHUSD. Until then those four cannot emit a deliverable
opportunity, and their scope verdicts stay `NOT_VERIFIED`. Pinned by
`tests/test_lsmc_v110_logic_audit.py::test_metadata_fails_closed_and_the_positive_control_still_resolves`.

## D-LSMC-2 — stale C10 implementation pointer in the frozen contract

`strategies/ST_LARGE_SMC_V1.yaml::stop_loss_contract.governance.implementation` names
`src/large_smc_research/c10_stop_policy.py`. That path **does not exist**; the real module is
`src/large_smc_core/c10_stop_policy.py` (imported by
`src/large_smc_watch/watch.py`). Bounded, documentation-only defect: no rule changes. The same
stale module prefix also appears in historical docs (`README.md:381`, `docs/VERSION_HISTORY.md`,
`docs/PROJECT_CAPABILITY_COMPLETENESS.md:161`, several `docs/architecture/*` ledgers), which is
consistent with a module rename that was never propagated.

## D-LSMC-3 — engine identity drift, now pinned to two commits

Independently reproduced this session with
`v1_tickets.lsmc_logic_gate.engine_sha256()`:

| Revision | `engine_sha256()` |
|---|---|
| `ce6f0f89` (the commit that recorded the C1 identity) | `ec0b2f3dc6ed2b02df3f643b38beac1c0e88630413c74e0f55e3d8aa5f5570d4` = **registry** |
| `af2b3cf6` | `5e2f9d19f6b76ed8aaea19ecaefbd8865a696594db4497850138888e49f10038` |
| `f28e0408` | `88dd9f1fb970f7811b437cb3b4c7341e0d1f84320238890eab3381eb0f51b689` = **C15/C16 gate value** |
| `65efdd87` (main) | `88dd9f1fb970f7811b437cb3b4c7341e0d1f84320238890eab3381eb0f51b689` |

Both drifting commits touched `src/large_smc_watch/watch.py` only (`af2b3cf6` +65/−11,
`f28e0408` +5/−11) and both are delivery-gate changes, exactly as C15 reported. The **contract**
hash is unaffected: `78285f9f…` matches the registry exactly. The registry identity is
therefore stale for the engine component only. Resolution is an owner choice (re-record the
identity, or move the gate back out of the engine) — C16 does not re-record an identity on its
own authority.

**2026-10-13 follow-up (C15-LSMC audit).** Reproduced unchanged: tree `88dd9f1f…`, registry
`ec0b2f3d…`, drift isolated to `watch.py` (`86ac9cdcfa864b36a06b795920bd333f8fa9cfdd81efa5eb422e1d746bc2c63d`),
`__init__`/`contract`/`detect` and both dependencies unchanged. The audit **left the pin stale on
purpose**: re-recording an identity on agent authority would reattribute the 2026-10-09/11
`LOGIC_VERIFIED` record. The one registry edit in that PR is prose only
(`detection_logic_verification.verification_basis`, see D-LSMC-8), which names both the
pre-correction bytes the historical record ran on and the corrected in-tree bytes.

## D-LSMC-4 — no `logic_identity` adapter for `ST_LARGE_SMC_V1`

`v1_tickets/authority.py::ADAPTERS` has entries only for `ST_ASIAN_SWEEP_5R_V1` and
`ST_CRYPTO_CFD_SWEEP_RETEST_V1`, so `logic_identity("ST_LARGE_SMC_V1", …)` returns `None` and
Large-SMC cannot be bound through the same identity mechanism the other two lanes use. Its
identity is carried by `v1_tickets.lsmc_logic_gate` instead. Consequence: a registry-level
identity check for LSMC is not available, and the `engine_sha256` drift (D-LSMC-3) can only be
reported, not gated.

## D-LSMC-5 — L5 unbound in the 1.1.0 alert path

Large-SMC L5 is `WARN` for every scan: no accepted spread/commission evidence is bound and the
1.1.0 alert path has no cost gate. Per OD1011-L5 the verdict is `WARN` naming the missing
source rather than an invented value.

**2026-10-13 follow-up (C15-LSMC audit).** Reproduced in all four lanes: L5 `WARN` on 18/18 fixture
cases, 575/575 EURUSD scans and 240/240 bounded crypto scans. Related environment fact now measured:
`OD1012-LSMC-RRF`'s `lsmc_min_remaining_reward_fraction: 0.5` lives in the host-local policy only, so
off-host `watch._remaining_fraction` returns `None` and every fully-costed opportunity is rejected
`REJECT_STALE` (11 of 34 rejected scans in lane B). That is an operational actionability parameter, not
a contract rule and not a cost gate.

## D-LSMC-6 — POI max age declared in trading days, implemented in calendar dates

Added 2026-10-13 (C15-LSMC follow-up audit). **Blocking for the audit verdict; not fixable on agent
authority.**

Declared: `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` `rules.poi.max_age_trading_days: 5`, the flagged
contract choice "distinct NY-17:00 trading dates", `docs/specs/LSMC_SPEC_V2_FROZEN.md` §4.2 and
`docs/specs/LSMC_SPEC_V1_FROZEN.md:259` (both "trading days").
Implemented: `src/large_smc_watch/watch.py::expires_at` applies `next_day_boundary`
`POI_MAX_AGE_TRADING_DAYS + 1` = 6 times, i.e. six consecutive **calendar** NY-17:00 dates, counting
Saturday and Sunday. `watch._poi_age_days` (line 164) implements the declared unit and has **zero
callers in the repository**.

Measured (audit lane `property_checks.poi_age_semantics`, every distinct POI origin):

| Calendar | Origins evaluated | Divergent | Trading-day instances expired early | Direction |
|---|---|---|---|---|
| Synthetic FX, 4 weeks (contract's own weekend rule) | 481 | 358 | 646 | 100% `ENGINE_EXPIRES_EARLIER` |
| EURUSD H1 committed export `SSC_V1_0_1_G2_DEV_001` | 723 | 600 | 1,080 | 100% `ENGINE_EXPIRES_EARLIER` |
| BTCUSD H1 VT-recorded 60d | 1,412 | **0** | 0 | — |

Worked example: a POI born Sun 2026-06-21T21:00Z (trading date Mon 2026-06-22) is declared valid
through Mon 2026-06-29 (`2026-06-29T17:00-04:00`); the engine expires it `2026-06-27T21:00Z`
(Sat 17:00 New York), losing that whole Monday. Origins late in the week lose two trading dates.

Materiality: conservative, and measured rather than assumed — trading dates are a subset of calendar
dates, so six calendar boundaries land at or before six trading dates; no `ENGINE_EXPIRES_LATER`
origin exists. The engine can suppress an opportunity or hold `NEAR_POI`/`DEVELOPING`; it can never
keep a POI alive longer than declared. **Scope is FX only**: BTCUSD/ETHUSD trade every calendar date
on this venue, so C15/C16 could not observe it, and the 18-case harness cannot either (its H1 windows
span fewer than six trading dates).

Why not fixed: an engine rule change is an owner decision, and `C001-PRE-RESULT-CORCTION` makes a
rule-byte change to a frozen candidate a *new candidate identity*. Owner options: amend the declared
wording to the implemented calendar unit, or ship a new version wiring `_poi_age_days`. It is also not
gated in `lsmc_logic_gate.py` — a new blocking check would silently change committed C15/C16 lane
distributions on re-run, and the choice is not the auditor's.

Reproduce: `python scripts/lsmc_v110_logic_audit.py --skip-crypto` → `property_checks.poi_age_semantics`
(FAIL) and `findings[D-LSMC-6]`.

**2026-10-13 AGP-C17 classification: IMPLEMENTATION against a declared contract rule, candidate prepared.**
The declaration is consistent across `strategies/ST_LARGE_SMC_V1_1_1_0.yaml`,
`docs/specs/LSMC_SPEC_V2_FROZEN.md` §4.2 and `docs/specs/LSMC_SPEC_V1_FROZEN.md:259`; the frozen engine
diverges from all three, and `watch._poi_age_days` (0 callers) already implements the declared unit. Because
1.1.0 is frozen, the correction is prepared as a **new candidate** instead of an edit:
`strategies/ST_LARGE_SMC_V1_1_1_2.yaml` (sha256 `5931b616f2048dd20c79bc2938ebd71a77b133c5b51b2c2d986664044b58d52f`, based on the committed 1.1.1 bytes `52203c8b…43fdb`,
`SPEC_ONLY_NOT_WIRED`, `CANDIDATE_PENDING_OWNER_CONFIRM`, `registered: false`, `active: false`, every
authority flag `false`, `economic_status: NOT_EVALUATED`). It keeps `max_age_trading_days: 5` — the number is
not the defect — and adds `max_age_unit: DISTINCT_NY1700_TRADING_DATES`, `expiry_instant`,
`weekend_and_holiday_dates_excluded: true` and an explicit implementation requirement naming `_poi_age_days`.
Its declared structural diff (15 paths, 1.1.1 → 1.1.2) is recomputed and compared by
`property_checks.candidate_rule_change_diff`, so an undeclared rule change fails the audit; the duplicated
`timeframes:` key inherited from 1.1.1 is removed as a byte-level-only fix (parsed structure identical).
No gate was weakened and no emission suppressed to reach any verdict here: `property_checks.gate_integrity`
computes that claim row by row (11/11). Activation still requires the owner's unit decision, a new registered
version, and a **fresh L1–L6 replay** of the changed candidate — 1.1.0 evidence may not be reused for it.
Details: `docs/status/AGP_C15_LSMC_V110_LOGIC_AUDIT_2026-10-13.md` §3.2, and the per-symbol scope matrix in §4.

## D-LSMC-7 — delivery gate blanked every opportunity rule in the shipped harness (half fixed)

Added 2026-10-13. `watch.gate_opportunity` (2026-10-10) renames the state to `REJECTED` off-host,
where the owner threshold `config/local/actionability_policy.yaml` is absent and
`watch._remaining_fraction` has no fallback. `v1_tickets.lsmc_logic_gate` keyed its opportunity checks
on `state == "OPPORTUNITY"`, so between 2026-10-10 and 2026-10-13 **156 per-check verdicts degraded to
NOT_APPLICABLE while L2/L3/L6 still printed PASS**: `opportunity_symbols_covered` `[]`,
`c10_stop_geometry_symbols` `[]`, L2's six opportunity rules, all of L3 geometry and all of L6 freshness
unevaluated on 18/18 cases. Same defect class as the 2026-10-09 → 2026-10-13 diff of the C1 report.

**Fixed 2026-10-13** in `src/v1_tickets/lsmc_logic_gate.py`: `signal_snapshot` inverts the delivery gate
exactly, the opportunity checks run on the detection lane, the shipped state stays in every case record,
`L2.delivery_gate_preserves_detection` asserts the inversion loses nothing (PASS 10/10 opportunity
cases), and `check_coverage` reports `checks_evaluated` / `checks_not_applicable` /
`never_exercised_checks` / `structural_na_markers` so future vacuity is visible. `L2.point_source` was
split into `L2.point_source_declared` (the rule) and `L2.point_source` (measured), because a
pre-metadata short-circuit (`MARKET_CLOSED`, `DATA_ERROR`) was being reported as a point-source failure.
After the fix: 542 checks evaluated, 78 NOT_APPLICABLE, 0 never-exercised, verdict `LOGIC_VERIFIED`.
No rule, threshold or case was loosened.

**Still open (not fixed):** `REJECTED` is a sixth state that the frozen contract's `alerts.mapping` does
not declare (it lists `DEVELOPING`, `NEAR_POI`, `OPPORTUNITY`, `INVALIDATED`, `EXPIRED`; `SUSPENDED`,
`IDLE`, `DATA_ERROR`, `MARKET_CLOSED` emit nothing). `watch.WatchTracker._emit` special-cases it to alert
level `INFO`. Needs a contract note or an owner decision.

Reproduce: `property_checks.harness_regressions.delivery_gate_does_not_blank_the_opportunity_rules` and
`.short_circuit_is_not_reported_as_a_point_source_failure` in the audit report.

## D-LSMC-8 — HOST_CAPTURED FX fixture evaluated 68 days after its own data, in the weekend (fixed)

Added and fixed 2026-10-13. `tests/fixtures/large_smc_v111/EURUSD.json` carried
`evaluated_at_utc = 2026-10-10T19:45:53.895829Z` — its own regeneration wall-clock — instead of the
manifest `decision_time_utc = 2026-08-03T00:00:00Z` carried by all five sibling fixtures. That instant is
**Saturday 15:45 America/New_York**, inside the FX weekend close, 68.8 days after the fixture's last M5
bar (`2026-08-02T23:55Z`).

Consequences, all reproduced: (1) the 18-case harness returned `LOGIC_NOT_VERIFIED` (L2 + L4 FAIL) purely
from the timestamp; (2) `scripts/audit_lsmc_v111_candidate.py`'s only `HOST_CAPTURED` row was pinned to
`MARKET_CLOSED` / `L4 FAIL`, and `tests/test_lsmc_v111_candidate_audit.py` asserted that state under a
comment claiming the snapshot was "captured Sunday", which the timestamp contradicts; (3) the AGP-4H-C
oracle's `L6_closed_ordered_inputs` check had 68 days of slack and could not fail.

Fix: `evaluated_at_utc` = manifest decision time; **all 754 bars (D1 30 / H1 120 / M5 604) byte-identical**
(0 changed), so no detection comparison resting on those bars is affected; manifest pin
`b5e1e524…` → `2ce91ea1c0eecf2debda0bd6bfb34e37d0f49cd66ccbb00ed199f7f78da6425d`;
`tests/_lsmc_v111_fixtures.check_decision_time` fails closed on any recurrence in either harness; the
candidate-audit expectations were corrected (EURUSD now `NEAR_POI` / `L4 PASS`, matching the 2026-10-09 C1
result); `strategies/registry.yaml::detection_logic_verification.verification_basis` records the correction
while keeping that historical record attributed to the pre-correction bytes it ran on.
`research_external/oracles/runs/AGP_4H_C_EURUSD_DETECTION.json` is frozen historical evidence and was
**not** rewritten; with the corrected fixture its L6 check is boundary-exact and
`pytest tests/test_agp_4h_c_detection.py` passes 9/9.

Reproduce: `property_checks.harness_regressions.fixture_decision_time_guard` and `findings[D-LSMC-8]`.

## D-LSMC-9 — a gate PASS on every scan is not coverage

Added 2026-10-13, LOW. Both committed C16 artifacts report `gate_status_counts` PASS on **8,961/8,961**
full-D1 scans for L1–L4 and L6. True, and not coverage: on 6,921 (BTCUSD) and 8,113 (ETHUSD) of those
scans the snapshot was not an `OPPORTUNITY`, so L2's six opportunity rules and all of L3/L6's opportunity
checks were NOT_APPLICABLE — and with `opportunities.with_c10_stop = 0`, `L3.stop_side` and
`L3.stop_beyond_sweep` were NOT_APPLICABLE on **every scan of both 60-day replays**. The committed
`NOT_VERIFIED` verdicts already rest on the missing stop evidence (D-LSMC-1); what was missing is the
explicit statement of how little of the gate those headlines evaluated. The bounded lane-C window shows
the same at small scale: BTCUSD 0 opportunity scans in 120, ETHUSD 13.

Committed artifacts are historical evidence and are **not** rewritten. Fresh reports now carry
`check_coverage`, with the three structural NOT_APPLICABLE markers (`L3.geometry`, `L3.stop_geometry`,
`L6.freshness` — ids that can never take a verdict) listed separately from real gaps, so the metric cannot
be misread in either direction. Lane C re-derives the committed counts from the artifacts instead of
trusting the headline (16 boolean checks per symbol, all pass).

Reproduce: `findings[D-LSMC-9].evidence.committed_c16_rederived_from_the_artifacts`.

## D-LSMC-10 — no transport or order path, but the import closure reaches the MT5 broker API

Added 2026-10-13, LOW. Statically and at runtime, nothing reachable from `large_smc_watch` imports
Telegram, `requests`, `httpx`, `aiohttp`, `urllib`, `smtplib`, `socket`, `fastapi`, `uvicorn`,
`execution.*`, `trade_management`, `authorization`, `owner_decision`, `svos`, `notifications`, `api` or
`mt5.management_gateway`: 48 repo modules in the closure, zero hits; 561 modules loaded by
`import large_smc_watch`, none of them a transport. The closure does contain `src/mt5/market_data.py:17`
and `src/mt5/symbol_resolver.py:12`, which import `MetaTrader5` unconditionally, via
`large_smc_watch.detect` → `from supply_demand.ob_config import …` → `supply_demand/__init__.py`'s eager
`.analyzer` re-export (`market_structure/__init__.py` likewise). The engine never *calls* MT5
(`tests/test_v1_large_smc_import_boundary.py` asserts no `order_send`/`order_check`/`positions_get`/
`position_close` and exempts `MetaTrader5` from its runtime check by design; `tests/conftest.py` documents
the same chain and installs an import-only stub whose every operation raises
`MT5StubOperationAttempted`).

Consequence: the `ARCHIVE_ONLY` alert engine is not import-independent of the broker API package —
off-host it is importable only through that stub. Bounded packaging fix (lazy re-exports in the two
`__init__.py` files); owner decision, not made here; no rule or gate changes.

Reproduce: `property_checks.no_transport_boundary` (PASS, with `broker_api_imports` and the runtime probe
recorded) and `findings[D-LSMC-10]`.

## D-CCFD-1 — `hash_method` prose contradicts the implementation

`strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0.yaml::research_lifecycle_contract.freeze.hash_method`
says *"SHA256 of this YAML mapping serialized with sorted keys **after removing**
freeze.contract_hash"*, while
`scripts/ccfd_sweep_retest_replay.py::canonical_contract_hash` **blanks** the field to `""`.
The two are not equivalent: removing a key changes the mapping, blanking it keeps the key.
The declared value follows the implementation, so the contract is self-consistent — but the
prose is wrong and is a plausible origin of a competing hand-computed hash. Bounded
documentation fix available; **the canonical value is not changed**.

## D-CCFD-2 — the `9a1f6759…` discrepancy: RESOLVED BY ROOT CAUSE

C15 recorded that the canonical hash it recomputed (`ac116e0a…`) "does not match the
`9a1f6759…` value requested in the original PR handoff". Root-cause result:

1. **It is not a stray citation — it is a real, recorded identity.** `9a1f6759…` is the
   **raw-bytes sha256 of an earlier revision of the contract file**, taken before PR #162
   (`559fa9e`, *fix(crypto): C15 L5 commission evidence and frozen-rule verification*) appended
   the `research_lifecycle_contract.freeze` block:

   | Revision | raw-bytes sha256 of `strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0.yaml` |
   |---|---|
   | `89f1fa6c` (*feat: add C15 crypto signal lifecycle verification*) | `9a1f6759d35cbb50fbb89dd41899f4d970b0cece6df5a40e682698a590d05968` |
   | `559fa9e` / `origin/main` / this commit | `6daa590b9a8bf0ba3427c718b12c2f23d414aaca9973cf5fd2b32694b1fca90b` |

2. **It is exactly the metric the replay driver itself reports for the 1.1.0 candidate.**
   `scripts/ccfd_sweep_retest_replay.py::research_logic_identity` computes, for
   `version == C15_VERSION` (1.1.0), `contract_hash = sha256(contract_path.read_bytes()
   .replace(b"\\r\\n", b"\\n"))` over `C15_CONTRACT_YAML`
   (`strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0.yaml`) — i.e. the raw-file metric, **not** the
   canonical sorted mapping hash. Recomputed against the historical blob, that metric is
   `9a1f6759…` bit-for-bit; against the current revision it is `6daa590b…`. That value is what the
   artifact's `contract_sha256` / `logic_identity.contract_hash` fields record — see
   `artifacts/.../ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0/vt_recorded_60d_2026-08-11_2026-10-09/replay_report.json`
   as committed on branch `feat/c15-crypto-verification` (commit `89f1fa6c`). It does **not**
   appear in that file's current revision. The artifact is self-consistent: it is the raw-file
   metric, not a competing canonical identity.
3. **So the two hash kinds are both legitimate and mean different things.** The canonical
   *mapping* identity (sorted serialization with the self-reference blanked) is `ac116e0a…` and is
   what `freeze.contract_hash` declares. The raw-file identity of the pre-#162 revision is
   `9a1f6759…`; of the current revision, `6daa590b…`. **Nothing needs overwriting and no rule is
   affected** — but C15's prose compared a raw-file hash taken before #162 against a canonical
   hash taken after it, which is the whole of the "mismatch". That is `D-CCFD-2b` below, a
   documentation defect, not an identity conflict.
4. **Neither value is reachable from the current contract as a canonical identity.** Eight
   serializations were computed; none equals `9a1f6759…`. The documented canonical method
   reproduces the declared value exactly:

   | Method | sha256 |
   |---|---|
   | sorted, self-reference blanked (**canonical**) | `ac116e0aadcca33238d0ce2d2b327368f0faa3a6bfb6f8cfdd2cf5222ca6ecf7` |
   | sorted, self-reference key removed (the prose's literal reading) | `20724220c85aed7dcd81d1a9fb61043629cb631af38114c1e900950610f717b2` |
   | sorted, whole `freeze` mapping removed | `77e6534d36bf6fa66462d71b50489aa91985dbf65738aea8e376bb8b765b2846` |
   | sorted, self-reference kept | `a245641d8dec077ad79c…` |
   | unsorted, self-reference blanked | `42789dbb7e7b8c6b9d72…` |
   | raw file bytes, current revision (= driver's 1.1.0 `contract_hash` today) | `6daa590b9a8bf0ba3427c718b12c2f23d414aaca9973cf5fd2b32694b1fca90b` |
   | raw file bytes, pre-#162 revision (= driver's 1.1.0 `contract_hash` then) | `9a1f6759d35cbb50fbb89dd41899f4d970b0cece6df5a40e682698a590d05968` |
   | `ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml` (1.0.0 base) raw | `395ede3926272cfe6112…` |

**Conclusion:** `9a1f6759…` is fully explained, and no contract-identity conflict exists.
`ac116e0a…` remains the authoritative canonical identity and is self-consistent (declared in
`freeze.contract_hash`, reproduced by the documented canonical method, independently recomputed by
both the replay report and `runtime_identity_verification.json`). **No hash was overwritten and no
hash was changed to make the discrepancy disappear.** The residual documentation defect is that two
different kinds of identity travel under one field name — a by-hand comparison across revisions
silently compares unlike things. Pinned by `tests/test_c16_ccfd_contract_identity.py` (11 tests),
including one that recomputes `9a1f6759…` from the historical blob.

## D-CCFD-3 — registered 1.0.0 still `STALE_IDENTITY` (pre-existing, from C15)

`strategies/registry.yaml` records candidate `1.0.0` with `logic_status: STALE_IDENTITY`
(`logic_status_recorded: LOGIC_VERIFIED`, `stale_identity_since: 2026-10-11`,
`logic_verified_identity: b8188dfb…`). Unchanged by C16; re-recording or re-verification is a
separate owner-governed change. The 1.1.0 candidate is not registered at all and stays
`NOT_ADMITTED_RESEARCH_ONLY`.

## OBS-CCFD-1 — C15-original vs C16 engine identity: EXPLAINED, not a defect

The C15 *original* CCFD evidence (`vt_recorded_60d_2026-08-11_2026-10-09`, `date`
`2026-10-11`) records `runtime_engine_hash` `a089001c…`; the C15 *reverify*
(`vt_recorded_60d_reverify_2026-10-12`) and C16 both record `0a3886eb…`. Both are legitimate
historical values of the same identity function.

Root cause: commit `1eb4cb57` — *OD1012-PIN-LAND: account pin on main + terminal-path pin,
RUN_IDENTITY, binding identity on failure records (#168)* — changed
`config/v1_tickets/crypto_cfd_ticket_policy.yaml` `account_login_suffix: "985"` →
`"999"` under owner decision **OD1012-ACCOUNT (2026-10-12)**. That config file is one of the
21 files in the `ST_CRYPTO_CFD_SWEEP_RETEST_V1` engine identity list
(`src/v1_tickets/authority.py::ADAPTERS`), so the identity hash moved with it.

Evidence: recomputing `_sha256_text(ADAPTERS["ST_CRYPTO_CFD_SWEEP_RETEST_V1"][1])` over the
80 most recent revisions flips exactly at that one-line config change; no engine *source* file
differs between the two states. The C15-original → C16 difference set is 17 fields: 1 replay
date argument + 16 OD1012-ACCOUNT derivations (2 account suffixes, 14 identity-hash echoes).
Zero unexplained differences. C16 is byte-identical to the C15 reverify on all four output
files (`replay_report.json` `ffb2ec16…`, `runtime_identity_verification.json` `60cb884f…`,
`signal_events.json` `4fa10520…`, `tickets.jsonl` `648f2cb5…`).

Classification: **not a defect, not a hash to overwrite** — an owner-approved account migration
that is correctly reflected in the identity hash. Recorded here so the C15→C16 difference is
never mistaken for drift.

---

## Defects deliberately NOT touched

- No strategy rule, threshold, friction or eligibility value was changed.
- `ST_ASIAN_SWEEP_5R_V1@1.1.2` and `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` are byte-identical
  to their pre-C16 state (`941dec55…` / `78285f9f…`).
- No registry entry was added, edited or re-recorded; no READY, demo or live flag moved.
- No sealed OOS material was opened; no DEV fixture was used as authoritative 60-day evidence.

**2026-10-13 C15-LSMC follow-up (the `D-LSMC-6` … `D-LSMC-10` entries above):** the same exclusions hold for
strategy rules and evidence — `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` is still byte-identical (`78285f9f…`),
no READY/demo/live flag moved, no sealed OOS material opened, and no committed C15/C16 evidence file was
rewritten. Two exceptions, both in the verification layer and both recorded above: one evidence-fixture
timestamp (`D-LSMC-8`; all 754 bars byte-identical) and one registry *annotation* —
`ST_LARGE_SMC_V1.detection_logic_verification.verification_basis` prose only. No registry status, authority,
version or identity-hash field was edited, and `engine_sha256` was deliberately left stale (`D-LSMC-3`).
