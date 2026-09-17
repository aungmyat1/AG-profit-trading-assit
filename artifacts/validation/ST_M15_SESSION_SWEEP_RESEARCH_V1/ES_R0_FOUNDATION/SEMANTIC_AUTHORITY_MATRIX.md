# Semantic Authority Matrix (ES-R0 P3, P6)

## Class A — AGREED_DETERMINISTIC_CORE
(independently supported by both AG reconstruction and D:\ formalization — see `BASELINE_STRATEGY_CONTRACT.md` for full detail)
- M15-only, no H1/M1
- Asian range = 00:00–07:00 UTC (AG's own value; D:\ has version-dependent variants, not silently imported)
- Strict penetration + close-back-inside sweep, symmetric long/short
- Dual-side same-candle → ambiguous, no occurrence
- Entry = qualifying M15 candle's own close
- `SL = Entry ∓ 0.25×A`, `TP2 = Entry ± 5R = Entry ± 1.25×A`
- 75%/25% partial+BE+runner management (pre-`SESSION_SIMPLE_V1` D:\ versions)

## Class B — AG_GOVERNANCE_CHOICE
(required for deterministic research, not claimed as recovered source truth)
- `INTRABAR_ORDER_UNRESOLVED` ambiguity policy (explicitly chosen over D:\'s own `STOP_FIRST`)
- `MANAGEMENT_END_UTC = 22:00` (carried forward from provenance parent 1's own `STRONGLY_SUPPORTED` finding, not re-derived)
- No eligibility filter of any kind in this v0.1.0 baseline (deliberate — generates the full unfiltered population)
- BE price = raw entry, no cost/friction adjustment

## Class C — FUTURE_RESEARCH_HYPOTHESIS (quarantined, not baseline authority)

| Rule | Provenance classification |
|---|---|
| `SWEEP_CANDLE_OPEN_INSIDE` (D:\'s rule: sweep candle must open inside the boundary) | `IMPLEMENTATION_RULE` (D:\ self-labels it as such, not a source claim) |
| `MIN_BREACH_1_PIP` | `IMPLEMENTATION_RULE` (D:\ self-labeled) |
| `WICK_RATIO_0_35` | `IMPLEMENTATION_RULE` / possibly `UNKNOWN_PROVENANCE` — this exact figure also appears in AG's own chat-log source material as a benchmark-fit artifact (ES-S6), raising the unresolved possibility that AG's source material is itself a downstream echo of this same D:\ project |
| `EFFICIENCY_RATIO_0_35` (Range/Trend classifier) | `IMPLEMENTATION_RULE` (D:\ self-labeled) |
| `MAX_TRADES_1` | `VERSION_SPECIFIC_RULE` — only in D:\'s current `SESSION_SIMPLE_V1`, a deliberate simplification for demo-readiness, not a general or source-claimed rule |
| `STOP_FIRST_COLLISION` | `IMPLEMENTATION_RULE` (D:\ self-labeled, deliberate determinism choice) |
| `SESSION_SIMPLE_NO_MANAGEMENT` | `VERSION_SPECIFIC_RULE` (current D:\ frozen version only) |

No rule above may move into Class A or B except through a separately preregistered ES-R1+ mission.
