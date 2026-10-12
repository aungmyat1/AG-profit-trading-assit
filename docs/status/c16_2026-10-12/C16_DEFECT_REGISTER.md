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
| `GOVERNANCE-180` | BLOCKER (authority) | — | process / governance | **CLOSED — owner merged #180 (`7dfc8a20`)** |
| `GOVERNANCE-181` | — (record) | — | process / governance | **CLOSED — owner merged #181 (`0278653`); blocked state retained in main history** |
| `D-ASW-1` | HIGH | ASW 1.1.2 | implementation vs declaration | OPEN — v1.1.3 proposed |
| `D-ASW-2` | HIGH | ASW 1.1.2 | implementation (identity/causality) | OPEN — v1.1.3 proposed |
| `D-ASW-3` | MEDIUM | ASW 1.1.2 | missing host evidence | OPEN — owner input |
| `D-LSMC-1` | MEDIUM (by design) | LSMC 1.1.0 | missing host/broker evidence | OPEN — owner input |
| `D-LSMC-2` | LOW | LSMC 1.1.0 | stale contract pointer | OPEN — bounded fix available |
| `D-LSMC-3` | MEDIUM | LSMC 1.1.0 | identity-record staleness | OPEN — owner input |
| `D-LSMC-4` | MEDIUM | LSMC 1.1.0 | missing authority adapter | OPEN — owner input |
| `D-LSMC-5` | MEDIUM | LSMC 1.1.0 | L5 cost evidence | OPEN — owner input |
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
