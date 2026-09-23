"""PANEL_R3_OWNER_DECISION_BRIDGE.

Translates an explicit owner action on a CanonicalProposal (surfaced by the read-only
Panel-R2 Opportunity Analysis model, frozen at 40376ce51afc819951aebc7438511421cf6fe48e
-- PANEL_R2_AUDIT_PASS) into the existing, already-audited execution boundary. See
owner_decision.models for the OwnerDecision / ExecutionDecision data shapes and
owner_decision.bridge for the single evaluation function.

Architecture (see docs/status/ dated evidence doc for the full writeup):

    CanonicalProposal -> Owner Analysis Panel -> explicit owner action -> OwnerDecision
        -> ExecutionDecision (this module's output: an AUTHORIZED-but-UNCONFIRMED
           execution.models.TradeCommand template, or a REJECTED outcome)
        -> STOP. A separate, later, explicitly-user-confirmed call to
           assistant.commands.execute_command(trade_command, user_confirmed=True) is
           required to reach a broker order -- this module never makes that call.

This module never imports execution.executor or execution.mt5_gateway, and never sets
user_confirmed=True anywhere. It is advisory/preparatory only, exactly like every
skill under AGENTS.md point 4 -- except it additionally has the authority (via
assistant.commands.build_proposal_from_canonical, already execution-free) to persist a
prepared TradeProposal so a later, separately-authorized execute_command() call can
resolve it.
"""
