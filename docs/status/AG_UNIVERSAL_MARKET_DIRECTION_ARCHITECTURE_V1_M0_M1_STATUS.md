# AG Universal Market Direction Architecture V1 -- M0 (Audit) + M1 (Canonical Contract) Status

Scope executed this pass: **M0 (audit only, no behavioral changes) + M1 (canonical
contract, no strategy migration)**, per the mission's own staged plan (P59). M2-M6 are
explicitly **NOT DONE** -- see "Deferred" at the end.

## CURRENT_DIRECTION_AUTHORITY_MAP (P1)

Real, distinct, currently-existing direction/bias authorities found by repository audit
(not exhaustive at file level, but every conceptually distinct authority is listed):

| Authority | Location | Output | Registered strategy? | Notes |
|---|---|---|---|---|
| `daytrading.decision.market_bias` | `src/daytrading/decision/market_bias.py` | `BULLISH/BEARISH/NEUTRAL/INDETERMINATE`, from H1 `market_structure.tiers` external direction | No (advisory/analysis tooling, called from `scripts/analyze_trade.py`) | Most complete, evidence-backed bias source found -- reused as M1's adapter source |
| `daytrading.narrative_bias` | `src/daytrading/narrative_bias.py` (`DAYTRADING_NARRATIVE_BIAS_V1`) | `BIAS_BULLISH/BEARISH/UNRESOLVED` + delivery direction `UP/DOWN/BALANCED`, from D1/H1 structure+liquidity+supply/demand | No | A SECOND, independently-designed bias authority within the same `daytrading` package -- different evidence composition from `decision.market_bias`, not reconciled with it |
| `daytrading.pipeline` | `src/daytrading/pipeline.py` | `TRADE_STATE` (`TRADE_READY_LONG/SHORT`, etc.), composing `narrative_bias` above | No | Orchestrates authority #2, not #1 |
| `strategy_engine.session.setups.entry_1_trend` | `src/strategy_engine/session/setups.py` | `LONG/SHORT` via `BOX_DIRECTION_V1` (session open vs close) | No (unregistered, see prior task's finding) | Used by `SESSION_FLOW_V2_SIMPLE` / my `ST_SESSION_TRIBRANCH_RESEARCH_V1` candidate |
| `ST_ASIAN_SWEEP_5R_V1.yaml` `regime_classification.trend_bias_filter` | strategy YAML | `EMA_50`-based bullish/bearish condition | YES (real, signed strategy) | **Declared but never consumed** by the live engine (`entry_2_sweep` never reads it) -- a real, pre-existing dead-config finding, not introduced by this task |
| `strategy_engine.sweep_retest.trend` | `src/strategy_engine/sweep_retest/trend.py` | H1 trend-direction gate | YES (`ST_LIQUIDITY_SWEEP_RETEST_V1`) | Strategy-intrinsic (part of its own signed sweep+retest contract), not a candidate for universal-bias migration without further audit |
| `SESSION_TRADE_V1.classify_session()` | separate repo, `D:\ddev\Session Trade Codex` | directional `RANGE/TREND` classification, own thresholds | YES (partial demo-authorized, ASIAN_LONDON) | Out of this repo's scope; explicitly "do not merge" per `docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md` |
| Large-SMC E/M model (`src/large_smc_research/`, `src/entry_confirmation/`) | multiple files | direction is intrinsic to SMC E1-E3/M1-M3 setup qualification, not a standalone bias call | YES (`ST_LARGE_SMC_V1`) | See `LARGE_SMC_BIAS_COMPATIBILITY` below -- not assessed deeply this pass |
| My own `ST_SESSION_TRIBRANCH_RESEARCH_V1` (prior task) | `src/session_tribranch_research/replay.py` | `entry_1_trend`/router-derived direction, `MAX_RANGE_PIPS_EURUSD` regime gate | No (research candidate) | Itself a duplicate authority under this new contract -- would need M3-style migration to consume `MarketBiasResult` instead of computing its own regime/direction |

**duplicate_bias_logic = YES, confirmed** (at minimum: `daytrading.decision.market_bias`
vs `daytrading.narrative_bias`, both real, both in the same package, not reconciled).
**strategy_specific_bias_logic = YES** (`ST_LIQUIDITY_SWEEP_RETEST_V1`'s H1 trend gate,
Large-SMC's E/M model, both intrinsic to their own signed contracts -- plausible
`STRATEGY_SPECIFIC` governance exceptions once assessed, not migration targets).
**skill_conflicts**: no skill in `.claude/skills`/`.agents/skills` currently returns a
raw `BUY`/`SELL` (checked); `market-swing-structure-analysis` (built concurrently during
this session) is `ADVISORY_CONTEXT_ONLY` and does not emit bias either -- good precedent,
directly reusable for the M2 `market-structure`/`multi-timeframe-market-context` skill
consolidation, not audited further this pass.

**No "supplied positive pipeline results" artifact exists in this repository** -- I
searched for the cited figures (203 trades, +1.232R average net expectancy, +250.04R
total net) and found nothing. Per P40, treated as `UNVERIFIED_EXTERNAL_RESEARCH_RESULT`;
P41 (canonical reproduction) was **not attempted** this pass -- see Deferred.

## P2 reuse-first: what already exists and was reused, not rebuilt

- `market_structure`, `liquidity`, `supply_demand`, `mtf_context` packages already exist
  and are already composed by `market_swing_structure` (built concurrently, advisory-only)
  -- M1 does not touch or duplicate any of these.
- `daytrading.decision.market_bias.derive_market_bias_from_tiers` is REUSED verbatim as
  the M1 `BiasResolver`'s adapter source (see `src/market_intelligence/bias_resolver.py`).
  No new structure/liquidity/bias detection algorithm was written.

## M1 deliverable: the canonical contract

- `src/market_intelligence/models.py` -- `MarketBiasResult` (frozen, exactly 3 states,
  `decision_cycle_id`/`decision_time`/`model_version`/`input_fingerprint`, structurally
  excludes any execution field).
- `src/market_intelligence/bias_resolver.py` -- `resolve_from_daytrading_market_bias`
  (adapter over the existing real bias source) + `resolve_unavailable` (P32 fail-closed
  entrypoint for missing/insufficient upstream evidence).
- `docs/architecture/AG_STRATEGY_DIRECTION_CONTRACT_V1.md` -- the governance contract (P30).
- `tests/test_market_intelligence.py` -- 13 tests: all 3 states, `INDETERMINATE`/unknown
  fail-closed to `NEUTRAL`, missing-data fail-closed, determinism/fingerprint stability,
  frozen-instance immutability, naive-timestamp rejection, no-execution-fields structural
  check, decision-cycle-id convention. All pass.

## Deferred (explicitly NOT done this pass -- M2-M6)

- No skill file was created/edited/deprecated (P3/P4/P35/P36).
- No strategy (`ST_ASIAN_SWEEP_5R_V1`, `ST_SESSION_TRIBRANCH_RESEARCH_V1`,
  `ST_LARGE_SMC_V1`, `ST_LIQUIDITY_SWEEP_RETEST_V1`) was migrated to consume
  `MarketBiasResult` -- every one of them still computes its own direction internally,
  unchanged.
- No fill-safe bias-gated pipeline was built or run (P17-P21, M4).
- No canonical economic replay was performed (P41-P45, M5) -- the "+250R" claim remains
  unreproduced and unaccepted, per instruction, not because it was disproven.
- `LARGE_SMC_BIAS_COMPATIBILITY` and the Crypto equivalent (P22/P23) were **not
  assessed** -- only noted as "not analyzed" in the table above, not classified.
- No `strategies/*.yaml` file was edited to declare `market_bias.source: UNIVERSAL`.

## Safety

No strategy parameter, risk parameter, or historical evidence was changed. No lifecycle
stage, demo/live authorization, or execution path was touched. `git status` before and
after this pass shows only the new, additive `src/market_intelligence/` package, this
document, the governance doc, and `tests/test_market_intelligence.py`.
