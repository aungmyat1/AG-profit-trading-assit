---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-C18-TICKET-QUALITY-R1 — real Telegram message audit (2026-10-13)

The audit was read-only on the host: no change to the host, tasks, account, READY or execution
controls.

- **Source:** real messages from the C18 acceptance run.
- **Host:** `D:/wp3-main-integ` @ `6ebe5b9`, VTMarkets-Demo …999.
- **Evidence:**
  - `journal/ticket_delivery/report_lane/delivery_2026-10-13.jsonl`
  - `journal/ticket_delivery/archive/report_lane/2026-10-13_*.jsonl`
  - `…/fx_ticket_archive/ST_LARGE_SMC_V1/EURUSD/LSMC_WATCH-*`
  - `journal/ticket_delivery/mt5_guard/2026-10-13.jsonl`

## 1. Bound observations

| Msg | Sent (UTC) | Strategy@version | Observation | Data/bar time |
|---|---|---|---|---|
| 12749 | 08:31 | ASW@1.1.2 | EURUSD × ASIAN_LONDON BLOCKED `SUSPENDED_L3_REPAINT`. Run `fx-20261013T083124Z-12496`. Expected behaviour; the 08:46 resend was deduplicated (`duplicate`). | n/a, not evaluated |
| 12760 | 08:46 | ASW@1.1.2 | USDJPY × ASIAN_LONDON LONG CANDIDATE, signal id `…|USDJPY|ASIAN_LONDON|LONG|2026-10-13T07:30Z` | signal bar 07:30, close 07:45 |
| 12750 / 12758 | 08:38 / 08:43 | LSMC@1.1.0 | EURUSD WATCH SHORT, then WATCH LONG | H1 FVG origins 2026-10-12 09:00 and 2026-10-13 01:00 |
| 12755–12757 | 08:38 | LSMC@1.1.0 | crypto day summaries for 10-10, 10-11, 10-12 (once-only catch-up) | windows 10-10 to 10-12 |

"07:30" is the USDJPY signal bar. "08:08–08:13" in the Telegram view is local display time; the archive is in UTC.

## 2. ASW target geometry (USDJPY, message 12760): CONFIRMED DEFECT

- Prices: ENTRY 158.182, SL 158.121.
  - Risk = 0.061.
  - TP1 158.524 = **5.607R** (opposite session boundary).
  - TP2 158.487 = **5.0R** (fixed multiple).
- **TP1 lies beyond TP2.**
- The frozen v1.1.2 contract says `target_order_rule: FAIL_CLOSED_IF_TP1_BEYOND_TP2`, with changelog B-TGT-ORDER: "TP1 may pass TP2: unsafe → FAIL_CLOSED on inversion". That makes it **explicitly prohibited**.
- **Where the rule is enforced today:**
  - The manual-ticket path enforces it (`logic_gate.py` `R.target_order`).
  - The C18 report lane did **not**.
- The record was also `INFO_ONLY_STALE` (`FRESHNESS_EXCEEDED`: signal 07:30, evaluated 08:46), yet it was presented as a CANDIDATE.
- **Fix in this PR:**
  - `reporting.asw_lane.enforce_target_order` reads the rule from the frozen contract. An inversion becomes BLOCKED `TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2`, and prices are never swapped or relabelled.
  - `reporting.common`: `INFO_ONLY_STALE`, `MISSED` and `EXPIRED` are BLOCKED diagnostics and never candidates.
- **Separate finding, not fixed here:** the canonical S1 READY path (daily_evaluator → actionability) also does not apply the target-order rule. Owner decision **TQ-D1** below.

## 3. Large-SMC EURUSD SHORT → LONG: expected behaviour, but a silent setup switch

| Time | Transition | Reference (setup) |
|---|---|---|
| 08:38:13 | OPPORTUNITY→NEAR_POI | `EURUSD:H1:FVG:SHORT:2026-10-12T09:00:00+00:00` |
| 08:43:11 | NEAR_POI→DEVELOPING | `EURUSD:H1:FVG:LONG:2026-10-13T01:00:00+00:00` |

- These were **two independent setups** (different POI ids and origin times), not one setup flipping direction.
- The data was FRESH, and H1 bars are closed-only (`copy_rates_from_pos(…, 1, n)`).
- Two issues with how it was reported:
  1. The SHORT setup was dropped without an INVALIDATED or EXPIRED transition.
  2. `OPPORTUNITY` was stale tracker state from 2026-10-10, persisted while the task was disabled.
- No detection logic was changed.
- **Fix in this PR (reporting only):** observations carry `setup_id` (the tracker reference) and `transition` (`from->to`). WATCH is identified per setup, so NEAR_POI↔DEVELOPING churn on one setup reports once, while a new setup reports anew.
- **Owner decision TQ-D2:** whether the tracker should emit an explicit reason when it switches reference (an engine-adjacent change, which needs its own review).

## 4. Reporting diagnostics

| # | Item | Finding | Disposition |
|---|---|---|---|
| 1 | `SCHEMA_GAP: direction` on blocked ASW scopes | `render_report` printed the missing-value marker for an absent direction | **Fixed:** shows `n/a` |
| 2 | Overlapping `REJECT_NO_STOP` and `UNSPECIFIED` counts | The LSMC crypto summary counted every reasonless DEVELOPING/NEAR_POI evaluation as an `UNSPECIFIED` rejection | **Fixed:** reasonless watch states are not rejections. IDLE-with-reason (e.g. `NO_BIAS`) is still counted, as the existing contract requires. |
| 3 | Historical summaries with zero evaluations | 10-11 and 10-12 are `EMPTY_WINDOW` because the task was disabled, not because the market was empty | **Fixed:** the summary now says "no evaluations recorded … not a market observation" |
| 4 | Repeated WATCH notifications | The identity was per day, class and reason, so per-symbol NEAR_POI↔DEVELOPING churn re-sent | **Fixed:** per-setup identity (§3) |
| 5 | Missing strategy and market timestamps | The report had no evaluated time or bar-close time | **Fixed:** `evaluated:` and `bar close:` lines on every report |
| 6 | C10 stop-geometry blocking | Only EURUSD/GBPUSD have pip evidence (`C10_PIP_SIZE`). Other symbols give BLOCKED `C10_PIP_SIZE_NOT_EVIDENCED`. | **Expected behaviour.** Pip evidence is an owner/host input (TQ-D3). |

## 5. Owner decisions

- **TQ-D1:** apply `FAIL_CLOSED_IF_TP1_BEYOND_TP2` to the canonical S1 READY path. This is an authorized-path change and needs a separately reviewed PR.
- **TQ-D2:** require an explicit tracker transition reason on a Large-SMC reference switch (engine-adjacent).
- **TQ-D3:** C10 pip evidence for USDJPY, XAUUSD, BTCUSD and ETHUSD.

## 6. Tests

- `tests/test_report_ticket_quality.py` covers:
  - 12760 reproduced exactly, with no swap;
  - both directions, and the rule read from the contract;
  - stale → BLOCKED;
  - no `SCHEMA_GAP`, timestamps present, ASCII only;
  - EURUSD setup identity and transition;
  - the summary not counting watch states;
  - the empty-window label.
- Regression: lanes, delivery, LSMC summaries, canonical FX, adapter. **175 passed.**
- No strategy engine, contract, admission, READY, account, task or execution change.
