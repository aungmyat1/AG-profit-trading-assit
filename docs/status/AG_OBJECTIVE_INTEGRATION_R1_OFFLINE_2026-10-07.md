---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AG_OBJECTIVE_INTEGRATION_R1_OFFLINE — 2026-10-07

STATUS_EVIDENCE: deterministic Linux fixture validation only; no live MT5 run,
economic backtest, execution authorization, merge, or production deployment.

## Data and provider contract

The existing `daily_evaluator.CandleProvider` callable receives an instrument,
cycle, date and UTC evaluation timestamp and returns `CandleBundle`.
`MT5CandleProvider` implements it through a typed `CandleRangeReader` and the
accepted `mt5.mt5_candles_readonly.fetch_candles_range` boundary. Conversion uses
`CanonicalCandle.to_engine_candle()`. The accepted adapter and frozen strategy
rules are unchanged. Crypto imports are deferred until crypto evaluation is
requested, so FX evaluator imports do not require the native MetaTrader5 package.

The frozen FX evaluator requires **M15 only**:

- ASIAN_LONDON: 24 reference bars, 00:00–06:00 UTC; completed trade-window bars
  from 07:00 to the earlier of the evaluation's completed-bar boundary and 11:00.
- LONDON_NEWYORK: 20 reference bars, 06:00–11:00 UTC; completed trade-window bars
  from 12:00 to the earlier of the evaluation's completed-bar boundary and 15:00.

D1, H1 and other timeframes are not required. Each requested bar must be present
in sequence, at its exact expected UTC opening timestamp. No forward fill,
synthetic bars, symbol suffix guessing or alternate venue is permitted. Current
price is the direction-independent observed bid/ask midpoint, never a candle
close substituted for a quote. Spread is observed ask minus bid in price units.
Missing, inverted, nonfinite, future or over-one-M15-bar-old quotes fail closed.
The host snapshots quotes before fixing the evaluation clock.

Missing required data becomes `INSUFFICIENT_DATA`; the existing evaluator retains
the clock-based `OUT_OF_SESSION` reference lifecycle outcome. The eight-pair
matrix is checked by multiplicity, including missing and duplicate evaluations.

## Policy, provenance and firewall

Production policy remains owner-unresolved; no local policy is committed and no
production threshold is supplied. Tests demonstrate
`INFO_ONLY_POLICY_UNRESOLVED` with the existing unsigned policy and technically
reachable `WATCH_READY` with an explicitly signed TEST-only fixture.

No H1 premium/discount, D1 directional bias or POI is inferred from direction.
Optional missing H1/POI remain `NOT_AVAILABLE` with `NOT_AVAILABLE` provenance.
The accepted #55 legacy `d1_context` fallback still carries the **M15 engine
regime** with `RUNTIME_FACT / ticket.regime` provenance; the bridge neither
fabricates nor relabels it as a measured D1 bias. Engine setup and price geometry
remain authoritative facts. Invented context count: **0**.

The transitive import/call firewall and runtime allowlist guard prove no order
API or broker-mutation dependency in this integration path. Demo and live
authorization are unchanged and disabled on these canonical tickets.

## Verification

Linux, Python 3.12, no Windows terminal; adapter-shaped deterministic fixtures:

```text
python -m pytest -q tests/test_mt5_provider_integration.py
24 passed, 0 failed

python -m pytest -q tests/test_actionability_and_canonical_ticket.py tests/test_mt5_candles_readonly.py
38 passed, 0 failed

python -m pytest -q
1120 passed, 2 skipped, 1 existing Starlette deprecation warning
```

The full regression run preceded the final two direction-only provenance tests;
the final focused suite includes those additional cases. Live MT5 skips are
deferred Windows checks, not passes. The full suite was justified by the shared
evaluator's deferred-import boundary; no economic backtests were run.

Tests cover provider conversion through the real accepted adapter, all eight
terminal evaluations, required reference/post data failures, unresolved policy,
signed TEST policy, LONG/SHORT provenance, stable logical identity, missing and
duplicate evaluations, transitive execution firewall, runtime guard refusal,
exact symbol mapping, closed bars, quote validity, and native-MT5-free imports.

## Windows acceptance handoff — not run here

From the Windows checkout root, with its existing authenticated Demo terminal:

```powershell
.venv\Scripts\python.exe scripts\host\live_eval_smoke.py
```

The script uses the existing host initialization, Demo-account gate and MT5 lock.
The provider sees only guarded accepted candle/metadata reads. It writes sanitized
JSON rows and outcome counts to
`artifacts/validation/live_evaluator_r1/<UTC_DATE>_live_evaluator_report.json`.
Each row includes instrument/session, decision/reason, ticket identity, validity,
logic/economic status, actionability/policy identity/status, source and UTC time.
Prices and remaining R appear only when actually available. Account identifiers,
raw diagnostic details, policy signatories and host-specific paths are excluded.
Exit 0 establishes matrix completeness and zero refused broker calls; it does
not by itself prove market-data readiness. Windows acceptance must inspect the
reported outcomes, missing-data reasons and applicable session state.

```text
MT5 adapter = live-host accepted independently (mission-supplied evidence)
provider/evaluator bridge = deterministic/offline verified
live evaluator = NOT YET HOST ACCEPTED
economic edge = unchanged
demo execution = disabled
live execution = disabled
```
