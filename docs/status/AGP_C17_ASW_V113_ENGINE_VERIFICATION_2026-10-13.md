---
class: evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: null
---
# AGP-C17 — `ST_ASIAN_SWEEP_5R_V1@1.1.3` engine implementation and L1–L6 replay (2026-10-13)

This change implements the two v1.1.3 corrections (D-ASW-1, D-ASW-2) from the C16 proposal behind
v1.1.3 only, then replays L1–L6 on the AGP-DATA-R3 60-weekday recorded VT fixtures for EURUSD,
GBPUSD, USDJPY and XAUUSD, both sessions.

**What does not change:** no registry entry, READY, demo, live, runtime-binding or broker change,
and the v1.1.2 S1 identity `d7a8ebe5…` is unchanged. The v1.1.3 contract file is unchanged.

## Owner decision applied

- **`cross_branch_precedence: BY_EMISSION_TIME`** (Aung, 2026-10-13, chat). The first emission
  of a session is final and is never rewritten. Later qualifications are appended
  (`max_entries_per_session` stays 1).
- **Scope:** all four pairs × both sessions.

## Implementation

- **New `src/strategy_engine/append_only.py`.** It walks the trade window bar by bar and calls the
  frozen detectors `entry_2_sweep` / `entry_3_range` one candle at a time. Within a bar, Entry 2 is
  checked before Entry 3, as in v1.1.2.
- **D-ASW-1:** a candidate with `risk_distance <= 0` is NO_SETUP at the detection site, so a
  zero-risk sweep falls through to Entry 3 on the same bar. If nothing qualifies, the reason is
  `NON_POSITIVE_RISK_DISTANCE`.
- **D-ASW-2:**
  - The decision is the first emission.
  - `emission_stream()` exposes the appended stream.
  - `signal_id` is per qualifying bar.
- **Untouched shared modules:** `engine.py` and `session/*` are not edited. They are shared with
  v1.1.1 and v1.1.2 and bound by S1.
- **`v1_tickets/fx.py`:**
  - Dispatches only `uses_append_only(strategy)` (v1.1.3) to the new path. v1.1.1 and v1.1.2 keep
    the module-level `evaluate`.
  - Rounds v1.1.3+ ticket prices with Decimal ROUND_HALF_UP per **OD1011-ROUNDING**. v1.1.2 keeps
    its frozen `round()`.
- **`v1_tickets/authority.py`:**
  - v1.1.3 gets an identity-only `CANDIDATE_CONTRACTS` entry. Without it, `logic_identity`
    hashed the v1.1.1 contract.
  - `CANDIDATE_ENGINE_FILES` adds `append_only.py` to v1.1.3's engine identity only.
- **Harness:**
  - `--contract/--version` were added to `scripts/asw_v112_60d_replay.py` and
    `scripts/asw_v112_l3_repro_0731.py`.
  - `use_candidate()` refuses a contract whose declared version doesn't match the one requested.
  - An unregistered candidate now reports `registry_identity_matches: false` instead of crashing.

## Identity

| Field | Value |
|---|---|
| v1.1.3 logic identity | `628f6100f673ed25772f3e8cd0cd754c14c45be9133aa44c244c3ac30555656a` |
| v1.1.2 S1 identity (unchanged) | `d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5` |

## Results — v1.1.3, 60 weekdays (run 1 = run 2, committed LF sha256 `bc672105…`)

| Pair | Session | Valid | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|---|---|
| EURUSD | ASIAN_LONDON | 3 | FAIL* | PASS | **PASS** | PASS | PASS | PASS |
| EURUSD | LONDON_NEWYORK | 5 | FAIL* | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | ASIAN_LONDON | 7 | FAIL* | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | LONDON_NEWYORK | 4 | FAIL* | PASS | PASS | PASS | PASS | PASS |
| USDJPY | both | 0 | FAIL* | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |
| XAUUSD | both | 0 | FAIL* | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |

\*L1 fails on exactly one check: `registry_identity_matches`, because v1.1.3 is deliberately
unregistered. Every other L1 check passes: candidate contract hash, frozen v1.1.1 contract
unchanged, runtime binding v1.1.1, replay determinism and fixture provenance. L1 can pass only
once the owner records identity `628f6100…`.

## EURUSD × ASIAN_LONDON 2026-07-31 (the v1.1.2 L3 failure)

| | v1.1.2 (C16) | v1.1.3 |
|---|---|---|
| Future-mutation mismatches | 25/25 | **0/25** |
| Prefix mismatches | 5 | **0** |
| First emission | — (rewritten) | RANGE 09:45, stable for every longer prefix (STALE at evaluation; RANGE tickets fail closed) |

`l3_repro_eurusd_asian_london_2026-07-31_v113.json` committed LF sha256 `9eedc857…`.

## v1.1.2 regression

The v1.1.2 rerun with the C16 date has a verdict matrix identical to C16. One case differs,
GBPUSD ASIAN_LONDON 2026-09-18: `SHADOW_INFO_ONLY` → `READY`. That is #184 (OD1012-S1-READY),
merged after C16, and is unrelated to this change. File committed LF sha256: `5923dac5…`.

## Owner decisions needed

1. Register v1.1.3 identity `628f6100…` as a candidate. That turns L1 to PASS.
2. Admit scopes, for example EURUSD × ASIAN_LONDON under v1.1.3.
3. Decide whether v1.1.3 replaces v1.1.2 as the scoped runtime candidate. Today S1 stays on
   v1.1.2.
4. USDJPY and XAUUSD stay blocked by data: no valid entries in 60 days, and L5 FAIL needs pip
   evidence.

## Evidence and commands

Hashes are of the committed (LF-normalized) files; the generator writes CRLF on Windows.

- Evidence directory: `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_3/c17_2026-10-13/`.
- Environment and resources: Windows workstation, Python 3.14, offline (no MT5/broker/network).
  Every run was R1 under `scripts/resource_guard.py`, one at a time, with the lock released after.

```
python scripts/asw_v112_l3_repro_0731.py --symbol EURUSD --cycle ASIAN_LONDON --date 2026-07-31 --dataset d60 --contract strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml --version 1.1.3 --out <dir>/l3_repro_eurusd_asian_london_2026-07-31_v113.json
python scripts/asw_v112_60d_replay.py --date 2026-10-13 --contract strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml --version 1.1.3 --out <dir>/asw_v113_60d_run1.json   (and run2)
python scripts/asw_v112_60d_replay.py --date 2026-10-12 --out <dir>/asw_v112_60d_regression.json
python -m pytest -q tests/test_asw_v113_append_only_engine.py tests/test_asw_v113_zero_risk_append_only.py tests/test_scope_status.py tests/test_d6_*.py tests/test_v1_tickets.py tests/test_manual_ticket_build.py tests/test_manual_ticket_logic_gate.py tests/test_manual_ticket_authority.py tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py tests/test_s1_activation.py tests/test_s1_recovery_ready_validation.py tests/test_strategy_engine.py tests/test_stale_fix_1_signal_time.py  -> 364 passed, 1 skipped
```

OSS-FIRST: append-only router | none (project-specific frozen detectors) | NEW (thin wrapper, reuses
the frozen `entry_2_sweep`/`entry_3_range`) | no maintained OSS implements this contract's rules.
