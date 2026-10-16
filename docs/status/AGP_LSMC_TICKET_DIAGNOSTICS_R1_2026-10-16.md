# AGP-LSMC-TICKET-DIAGNOSTICS-R1 — 2026-10-16

Status: research diagnostics only; not host-verified. Base main: d7a5d5e.
No strategy status, registration, READY, execution settings or S1 behavior changes.
ORDER_API_CALLS=0; BROKER_MUTATION_COUNT=0. No merge or deployment.

## Evidence and root causes

- Runtime authority: strategies/registry.yaml ST_LARGE_SMC_V1 remains inactive,
  research-only, demo/live false; detection-only LOGIC_VERIFIED is scoped to
  EURUSD 1.1.0. strategies/ST_LARGE_SMC_V1_1_1_0.yaml remains frozen.
  No registration or authorization of 1.1.2.
- watch.evaluate_snapshot: selected directional POI distance is zero inside the
  zone, otherwise price-high for LONG or low-price for SHORT; negative distances
  are excluded. NEAR_POI means distance <= 0.5 * ATR(H1,14), otherwise DEVELOPING.
  Telegram format_alert computes unsigned nearest-edge distance at its supplied
  price, potentially a different time/source from the evaluator's last M5 close.
  These are different observations, not evidence of a pip arithmetic defect.
- features.fvgs uses strict c.low > a.high / c.high < a.low, known at the third
  candle. Any positive gap qualifies; no minimum-zone width is specified.
  A tick-width warning must not become a new frozen-strategy rejection rule.
- detect.h1_pois identity includes symbol, timeframe, kind, direction and middle
  candle origin timestamp. Consecutive GBPUSD/XAUUSD FVGs have independent IDs.
  watch.WatchTracker stores only one latest reference per symbol. Replacement
  archives a new reference but does not terminalize/retain every older reference.
  Full independent lifecycle tracking is therefore NOT established.
- m5_opportunities returns only complete sweep + CHoCH + displacement sequences.
  A missing opportunity cannot distinguish absent sweep, CHoCH or displacement.
  Diagnostics must report NOT_AVAILABLE, not FAIL or an invented rejection.
- C10 pip authority exists only for EURUSD/GBPUSD (0.0001). USDJPY display pips
  (0.01) are not C10 authorization. Gold/crypto display price units.
  Point/tick sizes are separate verified host metadata fields; historical captures
  are not current spread, commission, slippage or executable-price evidence.
- Tracker archive writes are idempotent by transition ID and skip existing files.
  Delivery AlertLedger separately suppresses repeated confirmations and preserves
  uncertain delivery. Existing records must never be backfilled or rewritten.

## October 15–16 observations

The six original ticket payloads/timestamps were not supplied and are not present
in the committed date-specific evidence inspected. All six reconstruction slots
are UNRESOLVED; no exact prices, distances, FVG widths or event identities can be
attributed. Specifically, USDJPY NEAR_POI -> DEVELOPING is user-reported, not
reconstructed. For an unchanged POI this requires distance to cross the current
ATR band; price movement and/or band movement can cause it. A POI replacement is
another possibility. Selecting the actual cause requires both original snapshots,
POI IDs, M5 closes and H1 ATR values.

Inspected persisted date-specific evidence:
status/evidence/host_tkt_r2_2026-10-15.json and
status/evidence/host_tkt_r3_s4_2026-10-15/summary.json.
These establish host ticket tooling/acceptance facts, not the six LSMC alerts.
No host journal or MT5 connection was accessed.

## Open PR conflicts

#239 changes manual READY scope checks; its description reports frozen CCFD
identity failures. Do not incorporate it into this diagnostics change.
#232 proposes ASW/CCFD authority; LSMC remains deferred. Do not incorporate it.
#231 is a read-only host order-history runner, not host-run; no dependency here.
#240 is already merged in the inspected base and restricts report-only delivery
to complete setups.

## Minimal change and limits

host_delivery.lsmc_diagnostics builds a read-only view from persisted event
evidence; telegram_message.format_alert adds ASCII diagnostic lines. Existing
event payloads and archive bytes remain unchanged. Sweep/CHoCH timestamps pass
through; BOS and displacement remain unavailable because no explicit evidence
fields are persisted. Entry/stop/target and gross R:R are informational candidates;
spread and total cost remain unavailable. Freshness requires an explicit expiry
and observation time; no expiry is guessed. No diagnostic grants authority.

Files/functions requiring a separate candidate change, not modified here:
watch.evaluate_snapshot (persist decision-time price, ATR/band and gate evidence);
detect.m5_opportunities (typed partial-stage evidence);
WatchTracker.poll/_emit (per-reference lifecycle and immutable evidence schema);
host runner (timestamped bid/ask and cost provenance). These require identity
impact review and candidate validation before adoption.

OSS-FIRST: reporting adapter | existing watch/detect + stdlib | REUSED | no new
indicator or trading logic; no external package required.

## Verification

2026-10-16, Linux cloud, resource class R1: 84 passed in 1.49s.
Command: PYTHONPATH="$PWD/src" /workspace/AG-profit-trading-assit/.venv/bin/python -m pytest -q tests/test_lsmc_ticket_diagnostics_r1.py tests/test_v1_large_smc_110_watch.py tests/test_lsmc_alert_dedup.py tests/test_telegram_message_format.py tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_execution_boundary.py.
Resource guard acquired/released; one worker; no heavy process left running.
Default Python lacked pytest; repository venv used successfully. Ruff unavailable
in that venv; lint NOT_RUN. git diff --check passed.
Fake transport only; live Telegram and host validation
remain NOT_EVALUATED. Missing original observations, partial M5 stage evidence,
current quotes/costs and per-reference terminal lifecycles remain blockers.

## Verified metadata conventions (historical captures)

| Symbol | Point | Trade tick | Digits | Display pip | C10 pip authority |
|---|---:|---:|---:|---|---|
| EURUSD | 0.00001 | 0.00001 | 5 | 0.0001 | 0.0001 |
| GBPUSD | 0.00001 | 0.00001 | 5 | 0.0001 | 0.0001 |
| USDJPY | 0.001 | 0.001 | 3 | 0.01 | NOT_EVIDENCED |
| XAUUSD | 0.01 | 0.01 | 2 | price units | NOT_EVIDENCED |
| BTCUSD | 0.01 | 0.01 | 2 | price units | NOT_EVIDENCED |
| ETHUSD | 0.01 | 0.01 | 2 | price units | NOT_EVIDENCED |

Source: config/symbol_metadata/host_captured/*.json. No current spread inference.

## ASCII Telegram diagnostic example (missing M5 evidence)

```text
M5 DIAGNOSTICS -- READ ONLY -- NO EXECUTION AUTHORITY
liquidity sweep time: NOT_AVAILABLE
CHoCH time: NOT_AVAILABLE; BOS: NOT_AVAILABLE
displacement evidence: NOT_AVAILABLE
entry candidate: NOT_AVAILABLE; stop candidate: NOT_AVAILABLE; target candidate: NOT_AVAILABLE
gross R:R candidate: NOT_AVAILABLE; net R:R: NOT_AVAILABLE
spread: NOT_AVAILABLE; total cost: NOT_AVAILABLE
freshness: NOT_AVAILABLE; expires_at: NOT_AVAILABLE
explicit rejection reason: NOT_AVAILABLE
```

Freshness describes the archived evaluation time only, never current delivery-time
eligibility. Explicitly rejected events pass through their recorded rejection code;
no opportunity is not evidence of any particular failed stage.
