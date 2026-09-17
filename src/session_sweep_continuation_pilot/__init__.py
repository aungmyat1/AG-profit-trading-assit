"""AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2: real-market orchestration for
ST_SESSION_SWEEP_CONTINUATION_V1 (SSC). Fetches real closed MT5 candles, drives the
canonical, UNCHANGED session_sweep_continuation.replay.run_replay, adapts accepted
setups into CanonicalProposal via proposal_envelope.adapters.ssc_adapter, and persists
them through the existing ProposalLedger. No strategy semantics live here -- this
package is orchestration only, mirroring post_asian_pilot's own pattern for a different
strategy.
"""
