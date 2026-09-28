# AG FX Opportunity Live Proof + Proposal Qualification V1 — Status

**Date:** 2026-09-28
**Classification:** `QUALIFICATION_CONTRACT_BLOCKED` (the live proof is also `LIVE_MT5_AUTH_BLOCKED`)
**Candidate:** `restore/fx-opportunity-foundation-v1` @ `a060f5fe1cbc984a84063395527dae07a58699d6` (identity verified)
**Authority (owner decision, unchanged):** `ST_ASIAN_SWEEP_5R_V1` OPPORTUNITY_AUTHORITY=ALLOWED, PROPOSAL_AUTHORITY=NONE, DEMO_AUTHORITY=NONE

This mission computed **no economic outcomes**. The rest of this page explains why.

## Phase 1 — live MT5: `LIVE_MT5_AUTH_BLOCKED`

At 15:58 UTC on Monday, one attempt was made:

```
python scripts/run_fx_opportunity_once.py --cycle POST_ASIAN --terminal-path "C:\Users\aungp\AppData\Roaming\MetaTrader 5\terminal64.exe"
```

It returned `MT5_INITIALIZE_FAILED [-6, "Terminal: Authorization failed"]`. The terminal was the same process (PID 12328, started 13:27 UTC) that failed at about 14:55 UTC.

Both cycle windows had already closed (ASIAN_LONDON at 11:00, LONDON_NEWYORK at 15:00), so both evaluations would have been meaningful. Per the mission, live probing stopped after that one attempt; `POST_LONDON` was not attempted. No credentials were read, requested or stored, and there was no reconnect loop.

## Phase 2 — qualification contract freeze

### Frozen, non-ambiguous inputs

| Field | Value | Authority |
|---|---|---|
| Strategy / version | `ST_ASIAN_SWEEP_5R_V1` / `1.1.1` | registry, lifecycle, adapter |
| Strategy YAML | sha256 `ba7f5de859e6b4287a25252ec8195f172473ebea83aa88427d4b730449763826` (blob `36a16ee9`) | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` |
| Application SHA | `a060f5fe1cbc984a84063395527dae07a58699d6` | this branch |
| Dataset | `SSC_V1_0_1_G2_DEV_001`. M15 sha256 `cefed9705bf9609329183c9bc44b7536eafdf070950ff6bcd45b759623ccd063`; M1 is also present. GEN_002 is excluded (quarantined). | `dataset_manifest.json` |
| Symbols / sessions | EURUSD. ASIAN_LONDON: ref 00:00–06:00, trade 07:00–11:00. LONDON_NEWYORK: ref 06:00–11:00, trade 12:00–15:00 UTC. | YAML, pilot configs, `canonical_sessions.yaml` |
| Entry | MARKET at `Sweep_Candle_Body_Close` (ledger-resolved 2026-08-31) | YAML, ledger |
| Targets | TP1 = opposite session boundary, 75%, then runner SL → breakeven; TP2 = entry ± 5R, 25%, no trailing | YAML; `AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED` |
| Session exit | the pair's own trade-session end (11:00 / 15:00 UTC), marked at the last bar's close | owner-signed 2026-09-09 (P1A) |
| Same-bar policy | SL+TP1 or BE+TP2 in one bar → `AMBIGUOUS_SEQUENCE` (unresolved, never assumed) | signed contract |
| Intrabar granularity | M1, falling back to M15 marked `APPROXIMATED` | signed contract |
| Friction | `CONTRACT_CEILING`: 2.0-pip spread + 1.0-pip slippage per trade, commission 0.0 marked `UNVERIFIED`; applied additively to gross R; no other scenario is signed | historical `performance/cost_model.py`, from the YAML's `max_spread_allowed_pips` and `slippage_limit_points` |
| Duplicate handling | one candidate per (symbol, pair, trading_date); first qualified sweep only (`max_entries_per_session: 1`) | engine, funnel identity |

### Economically material fields that are ambiguous or unsigned (why qualification stopped)

1. **Resolution window start versus the fill instant. The signed contract contradicts its own implementation.**
   - The contract text says the position is "FILLED … at `ready_at` at the recorded entry price (the close of the M15 candle that produced the sweep signal)".
   - `ready_at` is `TradeSignal.signal_timestamp`, which is `Candle.time`, the sweep candle's **open** time (`strategy_engine/session/setups.py::entry_2_sweep`).
   - The implementation (`scripts/resolve_forward_shadow_outcomes.py::resolve_proposal`) resolves from `get_candles(symbol, "M1", ready_at, cutoff)`, which includes the sweep candle's own pre-fill M1 bars.
   - The stop *is* that candle's wick extreme, so a stop "hit" before the fill is close to structural.
   - Empirical evidence: all 13 existing records in `artifacts/outcome_resolution/records/` are `RESOLVED_SL` at −1.0R, and every SL event falls inside `[ready_at, ready_at + 15m)` (for example ready 07:00 → SL 07:11, ready 12:30 → SL 12:43, and four records with SL at the exact `ready_at` minute).
   - Choosing between "resolve from `ready_at`" and "resolve from `ready_at + 15m`" changes every outcome. It is a behavior change to a signed contract and needs an owner decision.
2. **Stop definition: YAML versus engine.**
   - The YAML declares `stop_loss_mode: PERCENT_OF_SESSION_RANGE, stop_loss_range_pct: 0.25`.
   - The engine (and the historical `execution/intent_builder.py`) uses the sweep candle's wick extreme. `stop_loss_range_pct` is loaded but read by nothing.
   - The signed contract says to "read [the stop] from the record" and claims that record derives from `stop_loss_range_pct=0.25`. That claim is false for the implemented engine.
   - The stop defines 1R, so every R figure depends on this.
3. **Structural invalidation.** `invalidation_rules.structural_invalidation: "M15 Candle Close fully outside the sweep wick low/high with expansion volume"` leaves "expansion volume" undefined. The signed resolver does not apply this exit at all and does not say that it doesn't.
4. **Detection-side YAML filters are not implemented.** `regime_classification.trend_bias_filter` (EMA_50) and `range_session_check.max_range_pips_eurusd: 25.0` are declared, but the engine classifies with ER_ONLY_V2 only. `max_range_pips_eurusd` is loaded and unused. This changes *which* Opportunities exist. Detection was not modified, per the mission.

No rule was invented. The mission forbade computing outcomes under competing readings, since that would let results pick the rule.

## Phase 3 / 4 — outcome dataset and economic report: NOT_EVALUATED

These were not run because Phase 2 is blocked (see above). Existing Opportunity detection evidence is unchanged: `artifacts/validation/AG_FX_OPPORTUNITY_FOUNDATION_V1/EURUSD_REPLAY_SSC_V1_0_1_G2_DEV_001.json`, with 38 end-of-window opportunities over 30 days. That is TECHNICAL_PIPELINE_VALIDATION only. It is **not** ECONOMIC_STRATEGY_QUALIFICATION.

## Phase 5 / 6 — authority and execution (unchanged)

- `proposal_authority`, `proposal_generation_authorized`, `demo_authorized` and `live_authorized` were not modified. No ticket was created.
- No production code changed in this mission. `pytest tests/test_fx_opportunity_runner.py -k "zero_broker or imports_no_execution or static_scan or authority"` gave 5 passed.
  - broker `order_check` = 0, `order_send` = 0, other mutations = 0;
  - no execution, authorization, ticket-delivery or `proposal_envelope` module is reachable from `fx_opportunity`.
- `pytest -q tests` gave 501 passed, 4 skipped, 1 failed. The failure is the pre-existing `api.app` test, the same as the base.

## Owner decisions needed before qualification can run

1. The resolution window start: from the sweep-bar open (current implementation) or from the fill at the sweep-bar close (current text).
2. Which stop is authoritative: the engine's wick stop or the YAML's 25% of session range.
3. Whether structural invalidation applies, and a definition of "expansion volume".
4. Whether the unimplemented EMA_50 and 25-pip filters are part of the strategy. Implementing them would require a new candidate strategy version, since frozen versions are not edited in place.

Decisions 1–3 would be recorded as `AG_OUTCOME_RESOLUTION_CONTRACT_V2`. The existing 13 records stay attributed to V1.
