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

**Integration update:** PR #186 was merged as `827faf62938addef215f1318134908aea8bee9c9` before its
three review findings were resolved. This follow-up carries the resolutions on current main
`363e5d490233dcf131399fb163d16b6ae0f01f74`; the v1.1.3 implementation bytes are the same as the
tested source commit `65bc7227f594110182d89202c6a79b0581493cc1`.

**What does not change:** no registry entry, READY, demo, live, runtime-binding or broker change,
and the v1.1.2 S1 identity `d7a8ebe5…` is unchanged. The candidate contract records the approved
BY_EMISSION_TIME decision and remains unregistered and unadmitted.

## Owner decision applied

- **`cross_branch_precedence: BY_EMISSION_TIME`** (Aung, 2026-10-13, mission instruction; recorded as
  OD1013-ASW-CROSS-BRANCH). The first emission
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
  - `CANDIDATE_ENGINE_FILES` adds `append_only.py`, the FX ticket dispatch/rounding adapter, and
    scanner version dispatch to v1.1.3's engine identity only. This addresses review finding P1.
- **`session_scanner/strategy_adapter.py`:** uses the same version selector as FX tickets. v1.1.3
  receives append-only routing; v1.1.1/v1.1.2 retain the frozen engine (review finding P2).
- Inputs are required to be chronological with unique timestamps; same-bar collision order remains
  Entry 2 before Entry 3.
- **Harness:**
  - `--contract/--version` were added to `scripts/asw_v112_60d_replay.py` and
    `scripts/asw_v112_l3_repro_0731.py`.
  - `use_candidate()` refuses a contract whose declared version doesn't match the one requested.
  - An unregistered candidate now reports `registry_identity_matches: false` instead of crashing.

## Identity

| Field | Value |
|---|---|
| v1.1.3 logic identity | `7e2324296ab6cb56147f6709aae5f8e1633e9c32475ee0f8b3988ea31adfedc9` |
| v1.1.3 contract hash | `b3623a6296a0b8b04a011583ba1d4016852a59057ad65acfd6307e92c8fff20d` |
| v1.1.3 engine identity | `8938f407ea45f53dbf82cd76439147c3553c4d3808b61046117f4e493952c228` |
| v1.1.2 S1 identity (unchanged) | `d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5` |

## Results — v1.1.3, 60 weekdays (run 1 = run 2, committed LF sha256 `bc672105…`)

| Pair | Session | Valid | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|---|---|
| EURUSD | ASIAN_LONDON | 3 | FAIL* | PASS | **PASS** | PASS | PASS | PASS |
| EURUSD | LONDON_NEWYORK | 5 | FAIL* | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | ASIAN_LONDON | 7 | FAIL* | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | LONDON_NEWYORK | 4 | FAIL* | PASS | PASS | PASS | PASS | PASS |
| USDJPY | ASIAN_LONDON | 0 | FAIL* | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |
| USDJPY | LONDON_NEWYORK | 0 | FAIL* | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |
| XAUUSD | ASIAN_LONDON | 0 | FAIL* | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |
| XAUUSD | LONDON_NEWYORK | 0 | FAIL* | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |

\*L1 fails on exactly one check: `registry_identity_matches`, because v1.1.3 is deliberately
unregistered. Every other L1 check passes: candidate contract hash, frozen v1.1.1 contract
unchanged, runtime binding v1.1.1, replay determinism and fixture provenance. L1 can pass only
after a separately authorized registry decision for identity `7e232429…`. L3 does not by itself
make any scope LOGIC_VERIFIED.

## EURUSD × ASIAN_LONDON 2026-07-31 (the v1.1.2 L3 failure)

| | v1.1.2 (C16) | v1.1.3 |
|---|---|---|
| Future-mutation mismatches | 25/25 | **0/25** |
| Prefix mismatches | 5 | **0** |
| First emission | — (rewritten) | RANGE 09:45, stable for every longer prefix (STALE at evaluation; RANGE tickets fail closed) |

`l3_repro_eurusd_asian_london_2026-07-31_v113.json` SHA256 `708721470cc7381b27a9c52d5358c17a49b3da26043fd035f9df8571aa817140`.
The full-window replay records 0/25 future-mutation mismatches, 0 prefix mismatches, and stable
signal identity per qualifying bar.

## v1.1.2 regression

The v1.1.2 replay preserves the frozen S1 engine identity and READY authority. Its 60-weekday matrix
retains the historical EURUSD ASIAN_LONDON L3 failure, as expected for v1.1.2; the v1.1.3 result does
not transfer to it.

## Owner decisions needed

1. Decide separately whether to register v1.1.3 identity `7e232429…` as a candidate. That turns L1 to PASS.
2. Consider any future v1.1.3 scope admission separately; this PR does not admit it.
3. Decide whether v1.1.3 replaces v1.1.2 as the scoped runtime candidate. Today S1 stays on
   v1.1.2.
4. USDJPY and XAUUSD stay blocked by data: no valid entries in 60 days, and L5 FAIL needs pip
   evidence.

## Evidence and commands

Hashes are of the committed (LF-normalized) files; the generator writes CRLF on Windows.

- Evidence directory: `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_3/c17_2026-10-13/`.
- Environment and resources: offline (no MT5/broker/network); R3 resource gate passed with 9.3 GB
  available RAM, one replay at a time under `scripts/resource_guard.py`, lock released after the runs.
  Run 1 and run 2 are byte-identical (SHA256 `8802e789284e982e891a7eb2974c111265894065aab0508ae0c2a623cfbae9a5`).

```
python scripts/asw_v112_l3_repro_0731.py --symbol EURUSD --cycle ASIAN_LONDON --date 2026-07-31 --dataset d60 --contract strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml --version 1.1.3 --out <dir>/l3_repro_eurusd_asian_london_2026-07-31_v113.json
python scripts/asw_v112_60d_replay.py --date 2026-10-13 --contract strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml --version 1.1.3 --out <dir>/asw_v113_60d_run1.json   (and run2)
python scripts/asw_v112_60d_replay.py --date 2026-10-12 --out <dir>/asw_v112_60d_regression.json
python -m pytest -q  # final integrated result recorded below
```

Final integration checks on the repaired branch: `python -m pytest -q` — **2,751 passed, 6 skipped**;
changed-file Ruff — PASS; `npm run lint` — PASS; Node tests — **27 passed**; docs links — PASS;
authority drift — 0 blocking errors. The docs prose drift scan reports existing advisories only.
The two old Python dependency/setup gaps were filled with the pinned repository dependencies before
the final suite (`smartmoneyconcepts`, `requests`, and research extra `pyarrow`).

OSS-FIRST: append-only router | none (project-specific frozen detectors) | NEW (thin wrapper, reuses
the frozen `entry_2_sweep`/`entry_3_range`) | no maintained OSS implements this contract's rules.
