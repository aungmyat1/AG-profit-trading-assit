# MI V1 contract

Schema identifier: `AG_MARKET_INTELLIGENCE_SNAPSHOT_V1`. The snapshot is a frozen,
serializable value. A changed event or input produces a new snapshot; no field is
mutated in place.

## Required shape

```text
MarketIntelligenceSnapshot {
  schema_version
  snapshot_id
  identity: {symbol, as_of, event_id, evaluation_mode, decision_cycle}
  provenance: {event_id, visibility_rule_version, dataset_identities, source_labels}
  quality: {overall_status, reason_codes, missing_components, completeness}
  sessions: {reference_session_facts, session_windows, session_data_quality}
  higher_timeframe_context: {topdown_context_id, tiers, h1_bias_evidence}
  structure: {swings, bos_choch_events, ranges, zones, feature_versions}
  liquidity: {levels, equal_levels, sweep_states, feature_versions}
  regime: {state, evidence, model_version}
  volatility: {atr_by_timeframe, ema_by_timeframe, availability, feature_versions}
  execution_timeframe_lineage: {timeframe, participating_series, last_closed_bar,
                                  confirmation_cutoffs, m1_used}
}
```

`identity` answers which evaluation this is. `provenance` answers where every series
came from. `quality` prevents partial evidence from being presented as complete.
Sessions, structure, liquidity, regime, and volatility contain observations only.
`execution_timeframe_lineage` records the lowest timeframe actually used and all
confirmation cutoffs. It does not contain an order or a trade recommendation.

Forbidden fields include BUY/SELL, long/short, entry price, stop loss, take profit,
risk, lot size, order type, proposal authorization, and execution status. MI builders
must accept either a TD-8E replay context or an explicitly bounded live input bundle;
they must never fetch live data from inside a replay build.

Serialization must preserve timezone-aware UTC timestamps, stable field ordering, and
deterministic fingerprints over schema version, event identity, provenance, quality,
and all component evidence.
