---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# ST_ASIAN_SWEEP_5R_V1@1.1.2 logic verification — EURUSD + GBPUSD (2026-10-09)

**LOGIC_VERIFICATION_REPORT:** `ST_ASIAN_SWEEP_5R_V1@1.1.2`, both windows, per symbol. **EURUSD:
LOGIC_VERIFIED** (unchanged; byte-identical to the #108 report
[`AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.md`](AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.md)).
**GBPUSD: PARTIAL**: L2 is NOT_EVIDENCED in LONDON_NEWYORK because the 10 recorded days contain no
conforming ticket in that window. No cross-symbol verdict is formed. Rule conformance only: **not
EDGE_VERIFIED; not admitted.** Runtime keeps v1.1.1; READY OFF (D6); no broker/MT5 call. Machine report:
[`AGP_C3_ASW_V112_GBPUSD_LOGIC_VERIFICATION_2026-10-09.json`](AGP_C3_ASW_V112_GBPUSD_LOGIC_VERIFICATION_2026-10-09.json);
artifacts `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/eurusd_gbpusd_2026-10-09/`.

## GBPUSD input

| Item | Value |
|---|---|
| Fixture | `tests/fixtures/manual_ticket/GBPUSD_M15_recorded.csv` sha256 `f0b15f864a8bea72ad287427109106996f431047e2b283ad0777e804133b0cfe` (git blob, LF; `-text`) |
| Provenance | `tests/fixtures/manual_ticket/GBPUSD_M15_recorded.PROVENANCE.md`; sha256 verified before use (fail closed): True |
| Source | VT Markets MT5 demo, read-only capture (#114): 10 days 2026-09-28 → 2026-10-09, per-day offset measured, M1 cross-check 64/64 |

## Gates per symbol

L2 rule (unchanged from #108): no undeclared or NOT_EVALUABLE check **and** a conforming sweep passing
L1–L4 in both windows. A window without a conforming ticket is reported NOT_EVIDENCED, never PASS. A
proposed change to this rule is at
[`docs/proposals/l2-absence-semantics.md`](../proposals/l2-absence-semantics.md) (OWNER_DECISION_PENDING,
not implemented).

| Symbol | L1 | L2 | L3 | L4 | L5 | L6 | Verdict |
|---|---|---|---|---|---|---|---|
| EURUSD | PASS | PASS | PASS | PASS | WARN | PASS | **LOGIC_VERIFIED** |
| GBPUSD | PASS | NOT_EVIDENCED | PASS | PASS | WARN | PASS | **PARTIAL** |

L5 WARN (both symbols): D2 from `config/owner_ticket.yaml`; commission and spread absent (WARN with a
reason, never 0); USDJPY/XAUUSD metadata PENDING_AGP-C2-SYMMAP.

| Symbol | Days | Cases | Conforming windows | L3 prefix / pre-emission / stream / future-mutation | L4 raw zero-stop / TP-inversion | Admitted |
|---|---|---|---|---|---|---|
| EURUSD | 5 | 10 | ASIAN_LONDON, LONDON_NEWYORK | 0 / 0 / 0 / 0 of 225 | 1 / 5 → leaked 0 | 2 |
| GBPUSD | 10 | 20 | ASIAN_LONDON | 0 / 0 / 0 / 0 of 325 | 1 / 7 → leaked 0 | 1 |

## Day types (harness classification of the engine ticket only)

| Symbol | Window | long-sweep | short-sweep | TREND | no-setup | range-rejection | insufficient-data |
|---|---|---|---|---|---|---|---|
| EURUSD | ASIAN_LONDON | 1 | 2 | 1 | 1 | 0 | 0 |
| EURUSD | LONDON_NEWYORK | 3 | 1 | 1 | 0 | 0 | 0 |
| GBPUSD | ASIAN_LONDON | 4 | 1 | 0 | 5 | 0 | 0 |
| GBPUSD | LONDON_NEWYORK | 3 | 3 | 2 | 2 | 0 | 0 |

## Coverage

| Instrument | Status |
|---|---|
| EURUSD | LOGIC_VERIFIED |
| GBPUSD | PARTIAL: 10 recorded days; conforming ticket NOT_EVIDENCED in LONDON_NEWYORK |
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

## Open items

- RANGE behaviour untested on recorded data (0 RANGE days in fixture).
- GBPUSD LONDON_NEWYORK conforming ticket NOT_EVIDENCED (10 recorded days).

## Tests (2026-10-09, Linux cloud container)

- `python -m pytest tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py tests/test_asian_sweep_v1_1_2_l2_closure.py tests/test_manual_ticket_logic_gate.py tests/test_capture_recorded_m15.py -q` → 87 passed
- `test_report_eurusd_results_byte_identical_to_the_108_report` pins EURUSD against the #108 JSON.
- Full suite: see PR CI. Fixture evidence only; nothing live-verified.

## Owner decisions needed

1. L2 absence semantics: `docs/proposals/l2-absence-semantics.md` (OWNER_DECISION_PENDING).
2. Admission of 1.1.2 and D6 READY re-enable remain separate rows.
