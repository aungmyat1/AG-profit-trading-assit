---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# ST_ASIAN_SWEEP_5R_V1@1.1.2 logic verification — EURUSD + GBPUSD (2026-10-09)

**LOGIC_VERIFICATION_REPORT:** `ST_ASIAN_SWEEP_5R_V1@1.1.2` on the committed EURUSD and GBPUSD
fixtures, both windows → **LOGIC_VERIFIED** (rule conformance only). EURUSD results are byte-identical
to the #108 report ([`AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.md`](AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.md),
unchanged). **Not EDGE_VERIFIED; not admitted.** Runtime keeps v1.1.1; READY OFF (D6); no broker/MT5
call. Machine report: [`AGP_C3_ASW_V112_GBPUSD_LOGIC_VERIFICATION_2026-10-09.json`](AGP_C3_ASW_V112_GBPUSD_LOGIC_VERIFICATION_2026-10-09.json);
artifacts `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/eurusd_gbpusd_2026-10-09/`.

**Scope limit (read first).** The GBPUSD fixture is the #114 capture: 10 days (2026-09-28 → 10-09).
It contains no RANGE (Entry 3) day, so L3 here says nothing about that branch. On an uncommitted
owner-uploaded GBPUSD MT5 export (409 days, not in the repo), the same harness found 6 sessions where a
RANGE emission was later replaced by a SWEEP in the same window (SWEEP and TREND emissions were never
revised). RANGE already fails closed in 1.1.2, so no admitted ticket is affected, but the finding stands
until a recorded fixture reproduces or refutes it. The registry `logic_status` is not changed by this
report.

## GBPUSD input

| Item | Value |
|---|---|
| Fixture | `tests/fixtures/manual_ticket/GBPUSD_M15_recorded.csv` sha256 `f0b15f864a8bea72ad287427109106996f431047e2b283ad0777e804133b0cfe` (git blob, LF; `-text`) |
| Provenance | `tests/fixtures/manual_ticket/GBPUSD_M15_recorded.PROVENANCE.md`; sha256 verified before use (fail closed): True |
| Source | VT Markets MT5 demo, read-only capture (#114), per-day offset +3h measured, M1 cross-check 64/64 |

## L1–L6

| Gate | Verdict | Evidence |
|---|---|---|
| L1 identity & contract | **PASS** | contract/registry identity, 1.1.1 unchanged, runtime on 1.1.1, replay determinism, GBPUSD provenance sha256 |
| L2 spec↔engine | **PASS** | no undeclared / NOT_EVALUABLE check on any case; GBPUSD conforming ticket NOT_EVIDENCED in LONDON_NEWYORK (no such day in 10 days) |
| L3 temporal causality | **PASS** | 0 mismatches on both symbols (scope limit above) |
| L4 price geometry | **PASS** | every raw zero-stop / TP inversion blocked; no admitted bad geometry |
| L5 risk & friction | **WARN** (no BLOCK) | D2 from `config/owner_ticket.yaml`; commission and spread absent (WARN, not 0) |
| L6 freshness | **PASS** | owner-ticket L6 (logic_gate.l6_freshness) on 22 signal cases: ['PASS'] |

| Symbol | Days | Cases | Conforming windows | L3 prefix / pre-emission / stream / future-mutation | L4 raw zero-stop / TP-inversion | Admitted | L6 |
|---|---|---|---|---|---|---|---|
| EURUSD | 5 | 10 | ASIAN_LONDON, LONDON_NEWYORK | 0 / 0 / 0 / 0 of 225 | 1 / 5 → leaked 0 | 2 | PASS |
| GBPUSD | 10 | 20 | ASIAN_LONDON | 0 / 0 / 0 / 0 of 325 | 1 / 7 → leaked 0 | 1 | PASS |

## Day types (harness classification of the engine ticket only)

| Symbol | Window | TREND | insufficient-data | long-sweep | no-setup | range-rejection | short-sweep |
|---|---|---|---|---|---|---|---|
| EURUSD | ASIAN_LONDON | 1 | 0 | 1 | 1 | 0 | 2 |
| EURUSD | LONDON_NEWYORK | 1 | 0 | 3 | 0 | 0 | 1 |
| GBPUSD | ASIAN_LONDON | 0 | 0 | 4 | 5 | 0 | 1 |
| GBPUSD | LONDON_NEWYORK | 2 | 0 | 3 | 2 | 0 | 3 |

## Coverage

| Instrument | Status |
|---|---|
| EURUSD | VERIFIED_RECORDED_FIXTURE |
| GBPUSD | VERIFIED_RECORDED_FIXTURE (10 days); conforming ticket NOT_EVIDENCED in LONDON_NEWYORK |
| USDJPY | PENDING_AGP-C2-SYMMAP |
| XAUUSD | PENDING_AGP-C2-SYMMAP |

| Branch | Status |
|---|---|
| RANGE_REJECTION | UNIT_ONLY (no recorded day yields Entry 3) |
| SWEEP | VERIFIED_RECORDED_FIXTURE |
| TREND | VERIFIED_RECORDED_FIXTURE (fails closed) |

| Symbol | long-sweep | short-sweep | TREND | no-setup |
|---|---|---|---|---|
| EURUSD | EVIDENCED (4) | EVIDENCED (3) | EVIDENCED (2) | EVIDENCED (1) |
| GBPUSD | EVIDENCED (7) | EVIDENCED (4) | EVIDENCED (2) | EVIDENCED (7) |

## Tests (2026-10-09, Linux cloud container)

- `python -m pytest tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py tests/test_asian_sweep_v1_1_2_l2_closure.py tests/test_manual_ticket_logic_gate.py tests/test_capture_recorded_m15.py -q` → 87 passed
- `test_report_eurusd_results_byte_identical_to_the_108_report` pins EURUSD against the #108 JSON.
- Full suite: see PR CI. Fixture evidence only; nothing live-verified.

## Owner decisions needed

1. Extend the GBPUSD fixture backwards (host capture) so L3 covers the RANGE branch and LONDON_NEWYORK
   gets a conforming ticket; or decide L3 scope for 1.1.2 (ticket-eligible branches only).
2. Admission of 1.1.2 and D6 READY re-enable remain separate rows.
