---
class: status
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# STALE-FIX-1 — truthful signal time + funnel fields (2026-10-08)

> **Superseded in part (2026-10-09).** STALE-FIX-1 merged through #94: `fx.py` no longer
> substitutes the first trade-session bar, and a SIGNAL without an engine time is
> `DATA_ERROR` / `SIGNAL_TIME_UNAVAILABLE`. The `FIRST_TRADE_SESSION_BAR` /
> `ENGINE_M15_SIGNAL_BAR` / `NONE` labelling and `signal_time_basis_utc` described below
> were therefore not applied.
>
> PR #95 now carries only the pass-through of #94's `signal_time_source` (`ENGINE` /
> `MISSING` / `NOT_APPLICABLE`) into actionability and the canonical `trigger` block. The
> record below is kept as historical evidence of the proposal.

**Mission correction of record.** A same-day record
([AG_STALE_FIX_1_VERIFICATION_2026-10-08.md](AG_STALE_FIX_1_VERIFICATION_2026-10-08.md),
PR #93, closed unmerged) misidentified STALE-FIX-1 as the already-merged AGP-TTU-02 fix
(PR #61). The coordinator clarified: STALE-FIX-1 is a **separate, previously unapplied
patch** — _truthful signal time + funnel fields_ — because `main` still substitutes the
first trade-session bar when the engine supplies no signal time (`src/v1_tickets/fx.py`,
the `signal_open = sig.signal_timestamp or post_session_candles[0].time` line). PR #93 was
closed by its author with that explanation; this PR replaces it as the STALE-FIX-1
deliverable. The verification record itself stays factually correct about AGP-TTU-02 and is
preserved unchanged.

## 1. Problem (pre-fix `main`)

`build_fx_ticket` fed the gate a `signal_close` derived from the **first trade-session bar**
whenever the engine stamped no signal time (`entry_1` box-based setups; `signal_timestamp`
is `None`). The ticket then carried `signal_close_utc` values indistinguishable from an
engine-observed signal time: no field said the close was window-derived, not observed.
Every downstream funnel stage (gate → actionability → canonical ticket → archive → owner
report) consumed a surrogate presented as a real signal time.

## 2. Patch (this PR) — truthful signal time + funnel fields

Gate math, gate decisions, freshness windows, RC1/RC2 (AGP-TTU-02), the D6 READY-authority
switch: **all unchanged**. The change is purely additive provenance:

| File | Change |
|---|---|
| `src/v1_tickets/fx.py` | New constants `SIGNAL_TIME_SOURCE_ENGINE_BAR` / `_FIRST_TRADE_BAR` / `_NONE`; ticket now carries `signal_time_source` (ENGINE_M15_SIGNAL_BAR \| FIRST_TRADE_SESSION_BAR \| NONE) and `signal_time_basis_utc` (the bar OPEN the gate close derives from; `None` when none). `signal_timestamp` remains exactly what the engine supplied. |
| `src/v1_tickets/actionability.py` | `_out()` passes the two fields through verbatim (`None` when the ticket never supplied them — never inferred). |
| `src/v1_tickets/canonical_ticket.py` | `trigger` block gains `signal_time_source` / `signal_time_basis_utc`, emitting `NOT_AVAILABLE` (existing convention) for source tickets that carry none (crypto/manual paths). |
| `tests/test_stale_fix_1_signal_time_truth.py` | 10 new regression tests (below). |

## 3. Evidence

### Truthful signal time
- entry_1: `signal_timestamp` stays `None` (engine truth); ticket records
  `signal_time_source = FIRST_TRADE_SESSION_BAR` and `signal_time_basis_utc = <first trade
  bar open>`; `signal_close_utc` keeps its pre-fix gate value (`basis + 15 min`) but is now
  labeled as derived, not observed.
- entry_2/entry_3: `signal_time_source = ENGINE_M15_SIGNAL_BAR`, basis == engine stamp.
- no post-session candles: `NONE`, basis `None`, gate still withholds `STALE/STALE_SIGNAL`.
- engine `NO_TRADE`: fields truthful; gate (per AGP-TTU-02) adds no `signal_close_utc`.
- Consumers without the fields (pre-fix archived tickets, crypto/manual paths): pass-through
  `None` / `NOT_AVAILABLE` — verified by tests; nothing is back-filled or guessed.

### Gate parity (empirical, this container)
The pre-patch `fx.py` (base `59900b2` blob) and the patched `fx.py` were run side by side on six gate scenarios (fresh entry_1, stale-data entry_1, fresh engine-stamped, stale-signal
engine-stamped, spread-wide, no-quote): **identical decisions and reason codes in all six;
the only ticket difference is the two added keys.** `PARITY: PROVEN`.

### Tests (Linux cloud container, Python 3.11.2, pytest 9.1.1)
- New: `tests/test_stale_fix_1_signal_time_truth.py` — **10 passed** (field labeling for
  entry_1/entry_2/NONE/NO_TRADE; AGP-TTU-02 RC1 composition; actionability + canonical
  pass-through, incl. the None/`NOT_AVAILABLE` honest-absence cases; gate-decision parity).
- The six stale-gate regression suites: `test_stale_gate_trigger_close` 18,
  `test_actionability_and_canonical_ticket` 19, `test_mt5_provider_integration` 29,
  `test_mt5_candles_readonly` 19, `test_d6_actionability_suppressed` 8,
  `test_d6_ready_authority` 13 — **106 passed, 0 failed**.
- Full suite `python -m pytest -q tests/`: **1506 passed, 3 skipped, 0 failed** (~111 s).

Note: the new test file deliberately runs against the **production** READY-authority config
(D6 OFF): a fresh engine READY asserts `SHADOW_INFO_ONLY` with `suppressed_decision=READY`,
locking in that this patch does not re-open strategy admission. (The conftest READY-ON
shim remains opt-in for the 11 pre-D6 files only; untouched.)

## 4. Authority boundary

- No strategy YAML, registry, threshold, session, sizing, or timing-rule change;
  gate/freshness inputs and outputs are provably identical (parity proof above).
- No `execution/`, `mt5/`, or broker call-site change; no demo/live flag touched.
- `ST_ASIAN_SWEEP_5R_V1` admission state unchanged (`ready: OFF` since D6; `demo_authorized:
  false`). `BROKER_MUTATIONS=0`, `STRATEGY_ADMISSIONS=0`, `TELEGRAM_AUTHORITY_CHANGED=FALSE`.
- Scope is exactly the FX ticket builder; `crypto.py` has no such substitution (verified by
  inspection — it passes no post-session bar into a signal close) and is untouched.

## 5. Not claimed

- No live evaluator run; no change to host acceptance evidence. This is an offline,
  fixture-level proof. An open-window live evaluator run remains AGP-LIVE-01.
- Pre-fix historical archives keep their unlabeled `signal_close_utc`; this patch does not
  rewrite historical evidence.
