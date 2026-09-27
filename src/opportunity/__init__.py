"""AG V2 Opportunity Finder core contracts (AG_V2_PRE_ARCHITECTURE_BASELINE).

Additive-only domain package: MarketEvent, the strategy-neutral funnel vocabulary
(FunnelStage/FunnelOutcome/FunnelTransition), OpportunityCandidate, the
ProposalEligibilityDecision boundary, StrategyBinding, and the shared
DataAuthority/WarmupRequirement/FrictionEvidence evidence contracts.

Nothing in this package mutates or replaces an existing canonical authority --
see each module's docstring for what it wraps/reuses instead of duplicating
(MarketSnapshot in strategy_contract.market_snapshot, CanonicalProposal in
proposal_envelope.models, the strategy registry in strategies/registry.yaml).
This package never imports execution/order-send code -- see
docs/architecture/AG_V2_PRE_ARCHITECTURE (P2, adapter import-boundary rules).
"""
