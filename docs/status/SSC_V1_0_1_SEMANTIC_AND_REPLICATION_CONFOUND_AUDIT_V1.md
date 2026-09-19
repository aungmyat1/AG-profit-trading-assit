# SSC_V1_0_1_SEMANTIC_AND_REPLICATION_CONFOUND_AUDIT_V1

Read-only audit of ST_SESSION_SWEEP_CONTINUATION_V1 (SSC) v1.0.1 semantics and
replication confounds, ahead of accepting prospective replication
infrastructure. No replay, no economics recomputation, no optimization, no
strategy parameter change, no protected-data access.

## 1. Version semantics — v1.0.0 economic counting status

**Confirmed and remediated.** v1.0.0 had a documented partial-target
direction inversion (`INVERSE_BOUNDARY: LONG -> reference_low, SHORT ->
reference_high`), introduced at `src/session_sweep_continuation/outcome_resolution.py`
(commit `c36bf235`, 2026-09-12), fixed in v1.0.1 per
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/V1_0_1_REMEDIATION/V1_0_1_REMEDIATION_MANIFEST.json`
(`final_status: SSC_V1_0_1_REMEDIATION_VERIFIED`).

- **GEN_001** — `counting_status: NON_COUNTING_FOR_V1_0_1`.
- **GEN_002 / HYP_002** — `strategy_version_used: "1.0.0 (pre-remediation)"`,
  `counting_status: PRE_REMEDIATION_NON_COUNTING`; HYP_002's own closure
  record independently confirms `strategy_version: "1.0.0"`.

Both are already excluded from v1.0.1 economic counting in
`SSC_V1_0_1_DATA_CONSUMPTION_REGISTRY_V1.json` — no pooling exists to undo.
The frozen v1.0.1 G2 population (`SSC_V1_0_1_G2_DEV_002_POPULATION_V1`, N=22)
is built from an entirely separate dataset (DEV_002), not from GEN_001/GEN_002.
**No action taken or needed** — this mission does not recompute or repool
anything; it only confirms the existing exclusion is real.

## 2. Partial target contract — canonical v1.0.1 semantic

**Confirmed: `OPPOSITE_SESSION_BOUNDARY`.** `src/session_sweep_continuation/outcome_resolution.py:142`:

```
partial_target_price = reference_high if is_long else reference_low
```

LONG → reference session high; SHORT → reference session low. A fail-closed
guard sets `partial_target_price = None` (rather than computing a negative-R
first leg) if the resolved target is already behind entry.

Protected by existing tests — verified passing, none added or edited:
`tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py`
(`test_wp6_long_mapping_is_reference_high`,
`test_wp6_short_mapping_is_reference_low`, plus lifecycle and cross-module
parity tests against `src/execution/validator.py`), and
`tests/test_session_sweep_continuation_gap_remediation.py`,
`tests/test_trade_management_execution_conformance.py`. `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`
was not edited — `partial_target_mode: NEXT_LIQUIDITY_TARGET` remains the
declared name; the semantic mapping above is recorded here as the
executable interpretation, not a rename of the field.

## 3. DST / calendar confound

**NOT_ESTABLISHED as tracked metadata.** No DST-phase field exists anywhere
for DEV_002 (`data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/dataset_manifest.json`)
or any other SSC dataset. Session windows are fixed UTC by design —
`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` session_pairs use plain
`HH:MM` UTC strings, and `src/session_sweep_continuation/sessions.py`
(`_parse_utc_time`, `SessionWindow.bounds_for_date`) never applies a DST
offset. This mission does not change the session windows.

**Recorded DST phase (calendar fact, observational only — not code, not a
strategy input):**
- DEV_002 decision window 2026-06-21 → 2026-08-02: **US/EU daylight saving
  active** for the entire window (US DST 2026-03-08 to 2026-11-01; EU summer
  time 2026-03-29 to 2026-10-25).
- Prospective DEV_003, earliest possible start 2026-12-08 (see §7 below and
  the archive mission's P7 finding): **US/EU daylight saving inactive**
  (standard time) for that date.

Any DEV_003-vs-DEV_002 disagreement must not be attributed to strategy edge
without first ruling out this DST/seasonal microstructure difference — the
UTC session clock is identical, but the underlying local-time trading
population behind those UTC hours shifts by an hour each way.

## 4. Session dependence (ASIAN_LONDON / LONDON_NEWYORK)

**Confirmed overlap.** ASIAN_LONDON's trade window (07:00–11:00 UTC) sits
entirely inside LONDON_NEWYORK's reference window (06:00–11:00 UTC) — the
same UTC hours on the same calendar day serve as ASIAN_LONDON trade time and
LONDON_NEWYORK reference time. Empirically confirmed co-occurring in the
frozen population: `G2_POPULATION_V1.json` records both an ASIAN_LONDON and
a LONDON_NEWYORK occurrence on 2026-06-23.

**NOT_ESTABLISHED.** No document in
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/` adjudicates
statistical independence of same-day multi-session occurrences; no
`RAW_N` / same-day multi-occurrence count exists. This is an **open,
unresolved methodological question**, recorded here as such — this mission
does not change the session definitions and does not compute or assert an
independence-adjusted N.

## 5. EMA invariant

**Holds by current value inspection**: `regime.ema_fast_period` (20) ==
`ema.fast_period` (20); `regime.ema_slow_period` (50) == `ema.slow_period`
(50) — but it was previously **unpinned by any test**. Added
`tests/test_session_sweep_continuation_ema_invariant.py`
(`test_regime_and_signal_ema_periods_stay_in_sync`), which fails closed if
either pair diverges in the future. Current YAML values were not changed.

## 6. Sample-size semantics

**Classification: `REPORTING_OR_SCREENING_FLOOR`.** `min_sample_size` is
consumed only in `src/session_sweep_continuation/performance_attribution.py`
(`_slice_metrics`): below the threshold it returns
`INSUFFICIENT_EVIDENCE`; at/above it returns `EVALUATED` with computed
metrics. No repository authority ties crossing this threshold to
`EDGE_VALIDATED`, `CAPACITY_VALIDATED`, or `DEMO_ELIGIBLE` — those terms
exist elsewhere (`docs/svos/SVOS_LIFECYCLE_AND_GATES.md`,
`docs/architecture/AG_STRATEGY_DIRECTION_CONTRACT_V1.md`) as separate,
stricter holdout/OOS/confirmation-based gates, unconnected to
`min_sample_size`. `EVALUATED` means only "a metric was computed," nothing
about validated edge, capacity, or demo eligibility.

## 7. Friction authority

`src/session_sweep_continuation/friction.py`'s `estimate_friction()` stamps
`cost_status`: **KNOWN** (all of live spread/commission/slippage supplied —
functionally "broker-evidenced"), **MODELED** (falls back to the yaml's
`friction.default_*_pips` block), or **UNAVAILABLE** (fails closed to
`REJECT_SETUP`).

**DEV_002's frozen economics are 100% MODELED** — every one of the 22
records in `G2_DESCRIPTIVE_PERFORMANCE_V1.json` and
`G2_FAILURE_DECOMPOSITION_V1.json` carries `cost_status: "MODELED"`; no
KNOWN entries exist. This is consistent with the `H2_FRICTION_VERIFICATION_PREREGISTRATION`
campaign (EURUSD+GBPUSD, planned window 2026-09-21→2026-09-25) still being
`NOT_YET_COLLECTED` as of this audit (registry `generated_at_utc`
2026-09-19T11:14:21Z) — no broker-evidenced friction existed at the time
DEV_002 was frozen. **This mission does not replace or touch DEV_002's
frozen economics.** Any future H2 or archive-derived friction observation is
for calibration/replication comparison only, never a retroactive edit of
DEV_002's MODELED numbers.

## 8. GBPUSD

| Aspect | Status |
|---|---|
| CONFIG_SUPPORTED | **YES** — `instruments: [EURUSD, GBPUSD]` |
| DATA_AVAILABLE | **YES** — `data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914/` (full H1/M15/M1) and `SSC_HYP001_GBPUSD_R1_H1_WARMUP_CONTEXT_20260528_20260802/` (H1 warmup only) |
| VALIDATION_STATUS | **Not part of the frozen v1.0.1 G2 population** (DEV_002/G2 is EURUSD-only, N=22). GBPUSD's only economic runs to date are v1.0.0 `PRE_REMEDIATION_NON_COUNTING` (HYP_002) or `REPLICATION_INCONCLUSIVE_INSUFFICIENT_SAMPLE` (HYP_001_GBPUSD_REPLICATION_R1, TREATMENT_N=15 vs minimum_N=20, frozen v1.0.0 detector). **GBPUSD has no v1.0.1-counting economic evidence.** |
| FRICTION_VALIDATED | **NO** — only MODELED defaults (`default_spread_pips.GBPUSD: 1.4`, etc.); the H2 campaign covering it is `NOT_YET_COLLECTED`. |

Config inclusion is **not** treated as validation authority here — GBPUSD's
`demo_eligible`/`demo_authorized` remain hardcoded `false` in code per the
strategy file's own header, independent of this audit.

## 9. Summary table

| Item | Finding |
|---|---|
| v1.0.0 economic counting status | `NON_COUNTING_FOR_V1_0_1` / `PRE_REMEDIATION_NON_COUNTING` (already enforced) |
| v1.0.1 canonical semantic mapping | `OPPOSITE_SESSION_BOUNDARY`: LONG→reference_high, SHORT→reference_low |
| DEV_002 DST phase | US/EU daylight saving **active** (2026-06-21→2026-08-02) |
| DEV_003 expected DST phase | US/EU daylight saving **inactive** (earliest start 2026-12-08) |
| Session dependence | ASIAN_LONDON trade window ⊂ LONDON_NEWYORK reference window; same-day co-occurrence confirmed; independence **not adjudicated anywhere** (open question) |
| EMA invariant status | Holds by value; now pinned by `tests/test_session_sweep_continuation_ema_invariant.py` |
| min_sample_size interpretation | `REPORTING_OR_SCREENING_FLOOR` only — not edge/capacity/demo proof |
| Friction authority | DEV_002 = 100% MODELED; no KNOWN/broker-evidenced friction exists yet (H2 not yet collected) |
| GBPUSD validation status | CONFIG_SUPPORTED + DATA_AVAILABLE, but **not validated** — no v1.0.1-counting economics, no friction validation |

## Safety confirmation

```
REPLAY_EXECUTED=false
ECONOMICS_RECOMPUTED=false
OPTIMIZATION_RUN=false
STRATEGY_PARAMETERS_CHANGED=false
PROTECTED_DATA_ACCESSED=false
```

Files touched by this audit: this document and
`tests/test_session_sweep_continuation_ema_invariant.py` (additive test
only — item 5 explicitly requested a regression test; no other file was
modified).
