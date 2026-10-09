---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-C3-ASW-RATIFY — ST_ASIAN_SWEEP_5R_V1@1.1.2 logic verification, both windows (2026-10-09)

**LOGIC_VERIFICATION_REPORT:** `ST_ASIAN_SWEEP_5R_V1@1.1.2` → **LOGIC_VERIFIED** (rule conformance
and internal consistency only) on ASIAN→LONDON and LONDON→NEW YORK. **Not EDGE_VERIFIED; not
admitted.** The runtime keeps loading v1.1.1 (byte-unchanged); READY stays OFF (D6); demo/live
`false`; FX runtime risk config unchanged; no broker/MT5 call. Machine report:
[`AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.json`](AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.json);
artifact set `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_2/` (mirrors the `_2_0` set).

| Identity | Value |
|---|---|
| Contract | `strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml` `941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69` |
| Engine (`strategy_engine`, shared with 1.1.1, unchanged) | `243c4ff13b1aabe6a5ccdd3fad0b847f15cbfae99e1608ee1636c4d31c07e959` |
| Logic identity (= registry `candidate_versions."1.1.2"`) | `d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5` |
| Frozen 1.1.1 contract | `a1f331a2…f550` (unchanged) |
| Dataset | `tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv` sha256 `390fe14944f9eeec…` (RECORDED_DEVELOPMENT_FIXTURE) |
| Candidate policy (L5) | `config/v1_tickets/asw_v112_candidate_ticket_policy.yaml` (D2; read by the verifier only) |
| Command | `python scripts/asw_v112_logic_verification.py --out-dir docs/status --date 2026-10-09` (exit 0 = LOGIC_VERIFIED) |

## L1–L6 (report numbering of `LOGIC_VERIFICATION_REPORT.json`)

| Gate | 1.1.1 baseline | 1.1.2 | Evidence |
|---|---|---|---|
| L1 identity & contract | PASS | **PASS** | candidate hash + registry identity match; 1.1.1 hash unchanged; runtime bound to 1.1.1; replay determinism |
| L2 spec↔engine | FAIL | **PASS** (L2 closure reused as-is) | no undeclared / NOT_EVALUABLE check; conforming sweep passes L1–L4 in both windows |
| L3 temporal causality | PARTIAL | **PASS** | prefix mismatches 0, pre-emission signals 0, streaming/batch mismatches 0, future mutations 225 with 0 mismatches (seed 112) |
| L4 price geometry | FAIL | **PASS** | recorded failures reproduce and are blocked; synthetic 400 sessions: raw zero-stop 22, raw TP inversions LONG 94 / SHORT 111; admitted by gates 13, of which zero-stop 0, inverted 0 |
| L5 risk & friction | BLOCKED | **WARN** (no BLOCK) | risk_pct 0.5, cost warn 0.10R / block 0.25R (candidate policy only) |
| L6 freshness (`logic_gate.l6_freshness`) | PARTIAL | **PASS** | owner-ticket L6 (logic_gate.l6_freshness) on 9 signal cases: ['PASS'] |

L5 WARN reasons (explicit; nothing assumed 0, nothing invented):
- COMMISSION_NOT_AVAILABLE: no commission metadata for the FX ticket path; not assumed 0
- SPREAD_NOT_RECORDED: the recorded fixture has no bid/ask; cost_in_R not evaluable on recorded data (L2 closure uses a 0.2-pip test input only)
- SYMBOL_METADATA_PENDING: AUDUSD, USDJPY, XAUUSD -> PENDING_AGP-C2-SYMMAP (not invented)

## L4: recorded 1.1.1 failures → 1.1.2 (fixture `tests/fixtures/asian_sweep_v1_1_2/l4_recorded_failures.json`)

| Case | Kind | Reproduces in engine | 1.1.2 rule |
|---|---|---|---|
| ASIAN_LONDON 2026-07-17 SHORT | ZERO_STOP | True | `True` → blocked True |
| ASIAN_LONDON 2026-07-17 SHORT | TP_ORDER | True | `True` → blocked True |
| ASIAN_LONDON 2026-06-17 LONG | TP_ORDER | True | `True` → blocked True |
| LONDON_NEWYORK 2026-06-17 LONG | TP_ORDER | True | `True` → blocked True |
| LONDON_NEWYORK 2026-06-23 LONG | TP_ORDER | True | `True` → blocked True |
| LONDON_NEWYORK 2026-07-17 LONG | TP_ORDER | True | `True` → blocked True |

Fix: none in the engine (shared with frozen 1.1.1; changing it would alter 1.1.1). The 1.1.2
contract's declared fail-closed rules (`R.stop_loss` risk_distance > 0, `R.target_order`) block
every case, so a zero stop or TP1-beyond-TP2 can never reach an admitted ticket.
Test: `test_report_l4_recorded_zero_stop_and_tp_order_failures_reproduce_and_are_blocked`.

## Cases (recorded EURUSD; ticket-gate = `logic_gate.py` L1–L6, 0.2-pip test spread)

| Window | Day | Engine | Ticket gate | L2 FAIL ids (declared fail-closed) | First emission (bars) | Owner ticket |
|---|---|---|---|---|---|---|
| ASIAN_LONDON | 06-15 | NONE  | — | — | None | NO_SETUP |
| ASIAN_LONDON | 06-16 | TREND SHORT | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | entry_level, entry_trigger, regime_branch, stop_loss | 0 | TICKET_BLOCKED |
| ASIAN_LONDON | 06-17 | SWEEP LONG | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | entry_level, target_order | 1 | TICKET_BLOCKED |
| ASIAN_LONDON | 06-23 | SWEEP SHORT | L1 PASS / L2 PASS / L3 PASS / L4 PASS / L5 WARN / L6 PASS | — | 1 | TICKET_BLOCKED |
| ASIAN_LONDON | 07-17 | SWEEP SHORT | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | entry_level, max_spread_fraction, stop_loss, target_leg2, target_order | 2 | TICKET_BLOCKED |
| LONDON_NEWYORK | 06-15 | SWEEP SHORT | L1 PASS / L2 PASS / L3 PASS / L4 PASS / L5 WARN / L6 PASS | — | 4 | TICKET_BLOCKED |
| LONDON_NEWYORK | 06-16 | TREND LONG | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | entry_level, entry_trigger, regime_branch, stop_loss | 0 | TICKET_BLOCKED |
| LONDON_NEWYORK | 06-17 | SWEEP LONG | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | entry_level, max_spread_fraction, target_order | 2 | TICKET_BLOCKED |
| LONDON_NEWYORK | 06-23 | SWEEP LONG | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | entry_level, max_spread_fraction, target_order | 7 | TICKET_BLOCKED |
| LONDON_NEWYORK | 07-17 | SWEEP LONG | L1 PASS / L2 FAIL / L3 FAIL / L4 PASS / L5 WARN / L6 PASS | max_spread_fraction, target_order | 3 | TICKET_BLOCKED |

Every owner ticket carries `EDGE_VERIFIED=FALSE`; no case reaches `TICKET_READY`
(`RISK_CONFIG_MISSING` on the runtime owner config, or `LOGIC_GATE_FAIL:L2`). NO_TRADE / DATA_ERROR
(insufficient data) / BLOCKED stay valid outcomes. Coverage limits: EURUSD only (the only
recorded FX fixture); RANGE_REJECTION branch has no recorded day (unit check only).

## Tests (2026-10-09, Linux cloud container, Python 3)

- `python -m pytest tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py -q` → 43 passed
- `python -m pytest tests/test_asian_sweep_v1_1_2_l2_closure.py tests/test_manual_ticket_logic_gate.py -q` (unchanged) → 33 passed
- Full suite: see PR CI. Unit/fixture evidence only; nothing live-verified.

## Owner decisions needed (not recorded in the register by this mission)

1. Admission of 1.1.2 for ticketing (confirm Phase B table; switch `config_source`).
2. D6 READY re-enable for Asian Sweep (separate from admission; needs G1/G3).
3. Optional: FX commission/spread source so L5 can leave WARN.
