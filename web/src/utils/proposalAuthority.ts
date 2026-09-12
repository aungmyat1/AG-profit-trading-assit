/**
 * WP5.2 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1, frontend-as-renderer audit):
 * positive-trust provenance check for TradeProposal objects.
 *
 * The prior check in ExecutionCockpit.tsx was negative-trust:
 *   marketDataSource !== 'SYNTHETIC'
 * which reads MISSING/UNKNOWN provenance (marketDataSource === undefined) as
 * authoritative -- exactly how api.ts's untagged client-fallback proposals slipped
 * through before that was fixed. A negative check is never sufficient on its own: any
 * future proposal source that forgets to stamp marketDataSource would silently pass.
 *
 * This uses `executionEligible` instead -- a field that already exists in the
 * TradeProposal contract (types/trading.ts) and is already documented as "True only
 * for a proposal whose geometry is safe to execute against: real broker data AND
 * canonical strategy governance (demo_authorized) both hold." Every known proposal
 * source (server.ts's /api/proposals/scan, api.ts's client fallback) already sets it
 * explicitly to false for synthetic output -- reusing it here means one strict
 * `=== true` equality check, no new schema field, and undefined/unknown always reads
 * as non-authoritative by construction (strict equality, not truthiness on an
 * inverted condition).
 */
import { TradeProposal } from '../types/trading';

export function isAuthoritativeProposal(proposal: TradeProposal | null | undefined): boolean {
  return !!proposal && proposal.executionEligible === true;
}
