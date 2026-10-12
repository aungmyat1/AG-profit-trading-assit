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

| ID | Severity | Strategy | Class | Status |
|---|---|---|---|---|
| `GOVERNANCE-180` | BLOCKER (authority) | — | process / governance | OPEN — ready for owner |
| `D-ASW-1` | HIGH | ASW 1.1.2 | implementation vs declaration | OPEN — v1.1.3 proposed |
| `D-ASW-2` | HIGH | ASW 1.1.2 | implementation (identity/causality) | OPEN — v1.1.3 proposed |
| `D-ASW-3` | MEDIUM | ASW 1.1.2 | missing host evidence | OPEN — owner input |
| `D-LSMC-1` | MEDIUM (by design) | LSMC 1.1.0 | missing host/broker evidence | OPEN — owner input |
| `D-LSMC-2` | LOW | LSMC 1.1.0 | stale contract pointer | OPEN — bounded fix available |
| `D-LSMC-3` | MEDIUM | LSMC 1.1.0 | identity-record staleness | OPEN — owner input |
| `D-LSMC-4` | MEDIUM | LSMC 1.1.0 | missing authority adapter | OPEN — owner input |
| `D-LSMC-5` | MEDIUM | LSMC 1.1.0 | L5 cost evidence | OPEN — owner input |
| `D-CCFD-1` | LOW | CCFD 1.1.0 | documentation vs implementation | ROOT-CAUSED — doc fix available |
| `D-CCFD-2` | LOW (investigation) | CCFD 1.1.0 | unverifiable citation / hash-name ambiguity | **RESOLVED BY ROOT CAUSE** |
| `D-CCFD-3` | MEDIUM | CCFD 1.0.0 | identity staleness (pre-existing C15) | OPEN — owner input |

---

## GOVERNANCE-180 — resource authority restored but unmerged

`RESOURCE-AUTHORITY-01` from PR #181 is resolved as far as an agent may resolve it: the
owner-issued policy, guard and tests are restored byte-identically from
`82e6e5cca329d1247f8a81aa308f25a80584c5fd` on PR #180 (head
`d28cacb74eec3cc3ba217ccd6892904fd000bf3a`), the guard passes 19/19 focused tests plus nine
end-to-end behaviour drills, and CI is green. The policy is **not on main** and **no owner
approval is recorded**, so #180 was left reviewable and unmerged. Verdict:
`GOVERNANCE_READY_FOR_OWNER_APPROVAL`. This campaign ran under the pinned policy.

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

1. **No such handoff exists.** The clone was shallow; after `git fetch --unshallow origin`
   (1 → 877 commits), `git log --all -S 9a1f6759` matches exactly two commits: `559fa9e5`
   (PR #162, which *introduced* the sentence) and `65efdd87` (PR #179, which repeats it).
   `git grep 9a1f6759 <sha>` in each resolves to the same two status documents that *assert*
   the discrepancy and to nothing else.
2. **GitHub has no other carrier.** Every PR body/comment and every issue body/comment in the
   repository was scanned; only PR #179 mentions it.
3. **It is not derivable from the contract.** Eight serializations were computed; none starts
   with `9a1f6759`. The documented canonical method reproduces the declared value exactly:

   | Method | sha256 |
   |---|---|
   | sorted, self-reference blanked (**canonical**) | `ac116e0aadcca33238d0ce2d2b327368f0faa3a6bfb6f8cfdd2cf5222ca6ecf7` |
   | sorted, self-reference key removed (the prose's literal reading) | `20724220c85aed7dcd81d1a9fb61043629cb631af38114c1e900950610f717b2` |
   | sorted, whole `freeze` mapping removed | `77e6534d36bf6fa66462d71b50489aa91985dbf65738aea8e376bb8b765b2846` |
   | sorted, self-reference kept | `a245641d8dec077ad79c…` |
   | unsorted, self-reference blanked | `42789dbb7e7b8c6b9d72…` |
   | raw file bytes | `6daa590b9a8bf0ba3427c718b12c2f23d414aaca9973cf5fd2b32694b1fca90b` |
   | `ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml` (1.0.0 base) raw | `395ede3926272cfe6112…` |

**Conclusion: there is no contract-identity conflict.** `ac116e0a…` is authoritative and
self-consistent (declared in `freeze.contract_hash`, reproduced by the documented canonical
method, independently recomputed by both the replay report and
`runtime_identity_verification.json`). `9a1f6759…` is an **unverifiable citation** with no
provenance in any commit, PR or issue; it must be reported as unresolvable rather than
overwritten. No hash was overwritten, and no hash was changed to make the mismatch disappear.
Pinned by `tests/test_c16_ccfd_contract_identity.py` (10 tests).

**Contributing ambiguity (still open, `D-CCFD-2b`):** a single CCFD artifact carries two
different *kinds* of identity under the same field name in different blocks —
`contract_hash` = `ac116e0a…` (canonical mapping identity) at the top level, while
`logic_verification.<SYM>.logic_identity.contract_hash` = `6daa590b…` (raw-file identity).
Both are legitimate; naming them identically is what makes a by-hand comparison ambiguous.

## D-CCFD-3 — registered 1.0.0 still `STALE_IDENTITY` (pre-existing, from C15)

`strategies/registry.yaml` records candidate `1.0.0` with `logic_status: STALE_IDENTITY`
(`logic_status_recorded: LOGIC_VERIFIED`, `stale_identity_since: 2026-10-11`,
`logic_verified_identity: b8188dfb…`). Unchanged by C16; re-recording or re-verification is a
separate owner-governed change. The 1.1.0 candidate is not registered at all and stays
`NOT_ADMITTED_RESEARCH_ONLY`.

---

## Defects deliberately NOT touched

- No strategy rule, threshold, friction or eligibility value was changed.
- `ST_ASIAN_SWEEP_5R_V1@1.1.2` and `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` are byte-identical
  to their pre-C16 state (`941dec55…` / `78285f9f…`).
- No registry entry was added, edited or re-recorded; no READY, demo or live flag moved.
- No sealed OOS material was opened; no DEV fixture was used as authoritative 60-day evidence.
