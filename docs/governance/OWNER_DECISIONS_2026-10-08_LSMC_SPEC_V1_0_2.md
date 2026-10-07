# Owner decisions, 2026-10-08 -- LSMC_SPEC_V1 batch 2

- **Owner:** Aung
- **Status:** SIGNED
- **Provenance:** **Transcribed by Arena on explicit owner instruction; text authored by owner.**
  Arena did not originate, edit, summarize or reorder any decision text in section 1.
- **Applies to:** `docs/specs/LSMC_SPEC_V1_FROZEN.md` v1.0.1,
  SHA-256 `900593d9420d9860907ca8c8460fcd970cd6b25de624d37a977aca7f0ab323a7`
- **Produces:** `docs/specs/LSMC_SPEC_V1_FROZEN.md` v1.0.2
- **Scope:** LSMC **strategy logic** only. Does not touch `LSMC_ACTIONABILITY_POLICY_V1`
  (delivery/actionability, decisions D1-D8, 2026-10-07).
- **Supersedes:** the 2026-10-07 batch rulings on `LSMC-OD-02` and `LSMC-OD-14`, which this
  batch explicitly replaces/revises.

---

## 1. Decision text (verbatim, authored by owner)

```text
OWNER DECISIONS on LSMC_SPEC_V1.0.1 (SHA-256 900593d9…23a7). Record this block verbatim in
docs/governance/OWNER_DECISIONS_2026-10-08_LSMC_SPEC_V1_0_2.md, marked "transcribed by Arena on
explicit owner instruction; text authored by owner".

OD-21/22: OD-02 ruling REPLACED. Non-C10 symbols: stop = sweep_extreme +/- 0.35 x ATR14 (C10 ATR
term reused; pip floor not applied). STOP_BASIS = SWEEP_EXTREME_ATR_BUFFER. INVALIDATED must be
reachable; add a fixture proving it.

OD-23/24/25: OD-14 REVISED. V1 resolves all levels on bid. Short TARGET_REACHED carries flag
SIDE_APPROX_BID. No typical-spread constants in V1. v1.1 will adopt empirical per-symbol spreads
from host-recorded samples.

OD-26: accepted; M1 resolution deferred to v1.1; AMBIGUOUS_SAME_BAR stays unresolved, counted
separately.

OD-16: accepted, under the bid + SIDE_APPROX_BID rule.

OD-01, 03, 04, 07, 08, 11, 15, 18, 19, 20: recommended defaults ACCEPTED.

OD-05: cap = min(session_end, choch + 24 M5 bars), PROVISIONAL constant. OD-06: floor = 6 M5 bars,
PROVISIONAL constant.
```

## 2. Execution directives as received (verbatim, not decisions)

Reproduced for provenance completeness. These are task instructions, not policy.

```text
TASKS: apply -> LSMC_SPEC_V1.0.2 + SHA-256 sidecar + changelog vs 900593d9. If applying any ruling
creates a new contradiction, add it as OD-27+ instead of resolving it. Commit to PR #51 only. STOP.

REPORT: v1.0.2 SHA-256, any new OD rows.
```

## 3. Rows closed by this batch

| Row | Disposition |
|---|---|
| `LSMC-OD-01` | recommended default ACCEPTED |
| `LSMC-OD-03` | recommended default ACCEPTED |
| `LSMC-OD-04` | recommended default ACCEPTED |
| `LSMC-OD-05` | cap = `min(session_end, choch + 24 M5 bars)` -- **PROVISIONAL constant** |
| `LSMC-OD-06` | floor = 6 M5 bars -- **PROVISIONAL constant** |
| `LSMC-OD-07` | recommended default ACCEPTED |
| `LSMC-OD-08` | recommended default ACCEPTED |
| `LSMC-OD-11` | recommended default ACCEPTED |
| `LSMC-OD-15` | recommended default ACCEPTED |
| `LSMC-OD-16` | ACCEPTED under the bid + `SIDE_APPROX_BID` rule |
| `LSMC-OD-18` | recommended default ACCEPTED |
| `LSMC-OD-19` | recommended default ACCEPTED |
| `LSMC-OD-20` | recommended default ACCEPTED |
| `LSMC-OD-21` | `STOP_BASIS = SWEEP_EXTREME_ATR_BUFFER`; `INVALIDATED` must be reachable + fixture |
| `LSMC-OD-22` | same ruling as `LSMC-OD-21` |
| `LSMC-OD-23` | `OD-14` REVISED -- all levels resolved on bid in V1 |
| `LSMC-OD-24` | same ruling as `LSMC-OD-23` |
| `LSMC-OD-25` | no typical-spread constants in V1; empirical per-symbol spreads deferred to v1.1 |
| `LSMC-OD-26` | ACCEPTED; M1 deferred to v1.1 |

Two earlier rulings are explicitly overturned by this batch:

- **`LSMC-OD-02` (2026-10-07) is REPLACED.** `STOP_BASIS = SWEEP_EXTREME` becomes
  `STOP_BASIS = SWEEP_EXTREME_ATR_BUFFER`.
- **`LSMC-OD-14` (2026-10-07) is REVISED.** Ask reconstruction is withdrawn from V1; all
  levels resolve on bid.

## 4. Consequences recorded, not resolved

The owner directed: *"If applying any ruling creates a new contradiction, add it as OD-27+
instead of resolving it."* Applying this batch produced **five** new contradictions, raised
as `LSMC-OD-27` through `LSMC-OD-31` in `docs/specs/LSMC_SPEC_V1_FROZEN.md` section 8.2.
None was resolved. Summary:

| Row | Contradiction |
|---|---|
| `LSMC-OD-27` | With the pip floor dropped, a non-C10 stop now depends on ATR14. When ATR is `NOT_READY` both available behaviours break a signed ruling: no stop (contradicts "no symbol is stopless") or a bare `sweep_extreme` stop (contradicts "INVALIDATED must be reachable"). |
| `LSMC-OD-28` | `atr == 0` is not a fail-closed condition in `c10_stop_policy.py` (only `atr < 0` raises). Buffer -> 0 restores the exact unreachability `LSMC-OD-21` was raised to fix, and the pip floor -- the only former lower bound -- is now explicitly not applied. |
| `LSMC-OD-29` | SHORT-side measurement bias compounds: C10-B's embedded spread widens the SHORT stop (fewer `STOP_REACHED`) while `SIDE_APPROX_BID` makes the SHORT target optimistic (more `TARGET_REACHED`). Both push the same way. |
| `LSMC-OD-30` | v1.0.2 amends four rules v1.0.1 marked `FROZEN` (3.3, 4.1, 7.1, 7.2). Spec section 9.2 requires a **new file** (`LSMC_SPEC_V2_...`) for any `FROZEN` change, but this batch directs an in-file v1.0.2. |
| `LSMC-OD-31` | `LSMC-OD-06`'s floor is counted in wall-clock M5 bars, so a Friday-evening trigger can have its entire 30-minute floor fall inside the weekend closure -- defeating the floor's stated purpose. |

## 5. Fixture required by `LSMC-OD-21`

`verification/AG_ARENA_RESET_A1_R1/fixtures/LSMC_INVALIDATED_REACHABLE_V1.json`, with the
worked arithmetic in the companion `.md`. It demonstrates LONG and SHORT bars that close
beyond `sweep_extreme` without touching the ATR-buffered stop, and shows the same bars
resolving as `STOP_REACHED` under the replaced `LSMC-OD-02` basis.

The fixture is **data plus worked proof only**. Wiring it into `tests/` requires a
code-touching mission; this session's scope is `docs/` and `verification/`.
