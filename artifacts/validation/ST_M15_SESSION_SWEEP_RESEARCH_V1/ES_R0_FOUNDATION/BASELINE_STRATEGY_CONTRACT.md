# ST_M15_SESSION_SWEEP_RESEARCH_V1 — Baseline Strategy Contract (AGREED_DETERMINISTIC_CORE)

Every rule below is independently supported by both AG's own reconstruction (`ST_SESSION_TRADING_SOURCE_V1`, ES-S1R) **and** D:\ddev\Session Trade Codex's `STRATEGY_TRUTH_SOURCE.md` v3.0 formalization — Class A evidence per ES-R0 P3.

## Timeframe
`PRIMARY = M15`, `SIGNAL = M15`, `EXECUTION = M15`, `H1_REQUIRED = false`, `M1_REQUIRED = false`.

## Asian reference range
`00:00–07:00 UTC`. `A = AsianHigh − AsianLow`. **Note (Class B, AG_GOVERNANCE_CHOICE):** D:\'s own `ASIAN_SESSION_V2` config uses `00:00–06:00 UTC` instead, and even its own documentation notes this project has internal version-dependent session-window differences. This baseline explicitly uses `00:00–07:00 UTC` (matching provenance parent 1's already-frozen contract) and does **not** silently import D:\'s `06:00` variant.

## Sweep
- Strict boundary penetration (wick beyond Asian High/Low).
- The same M15 candle closes back inside the range.
- Entry = qualifying M15 candle's own close.
- Long/short symmetric.
- Dual-side same-candle breach → ambiguous, no occurrence (`EXACT_MATCH` with D:\'s own rule).

## Risk
```
A = AsianHigh − AsianLow
R = 0.25 × A
LONG:  SL = Entry − R
SHORT: SL = Entry + R
```

## Target
```
TP2 = Entry ± 5R
TP2 distance = 1.25 × A
```

## Management
75% closes at the opposite Asian boundary. After confirmed partial fill, the remaining 25%'s stop moves to raw entry price (no cost adjustment). The remaining 25% targets TP2.

**Note (Class B):** this matches D:\'s `STRATEGY_TRUTH_SOURCE.md` v3.0 and `ASIAN_SESSION_V2`, but **not** D:\'s current `SESSION_SIMPLE_V1` (which has removed all partial/BE management). This baseline follows the independently-overlapping deterministic core, not D:\'s most recent frozen version.

## Ambiguity governance (Class B, AG_GOVERNANCE_CHOICE — explicitly NOT inherited from D:\)
Where M15 OHLC cannot establish intrabar order (SL vs. partial target, partial vs. runner target, BE vs. runner target, all in the same candle): `INTRABAR_ORDER_UNRESOLVED`. **D:\'s own `STRATEGY_TRUTH_SOURCE.md` explicitly adopts "stop-first" for this exact ambiguity** — this baseline deliberately does not inherit that assumption; it is recorded as `FUTURE_RESEARCH_OR_ENGINE_POLICY_CANDIDATE` only (see `RESEARCH_HYPOTHESIS_REGISTRY.md`).

Because entry is defined at candle close, the entry candle's own pre-close price action is never treated as a post-entry event (`ENTRY_SL_SAME_BAR`/`ENTRY_TP_SAME_BAR` are `DETERMINISTIC` by construction, not evaluated as ambiguous cases).
