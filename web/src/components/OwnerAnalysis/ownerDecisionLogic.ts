/**
 * Pure decision logic for the Owner Analysis panel (PANEL-R4/R5A canonical rewire).
 * No React import, no fetch -- deliberately dependency-free so it can be unit-tested
 * with plain node:test (see web/tests/owner_decision_panel_logic.test.ts), matching
 * this repo's existing test convention (no component-rendering test infra exists).
 *
 * This module owns three things only:
 *   1. Deterministic decision_id derivation (deriveDecisionId).
 *   2. Response/error -> UI outcome classification (classifySubmissionOutcome).
 *   3. A tiny duplicate-click / in-flight-request guard (createSubmitGuard).
 * It never calls agApiClient, never touches the DOM, never holds the owner key.
 */
import type { AgApiError, OwnerDecisionResponse } from '../../utils/agApiClient';

/**
 * DECISION_ID_CONTRACT_AMBIGUOUS mitigation (see
 * docs/status/AG_FRONTEND_OWNER_DECISION_REWIRE_STATUS.md): the backend's own
 * OwnerDecision.decision_id docstring (src/owner_decision/models.py:35-37) frames
 * decision_id as minted per-click/per-attempt, but idempotency is keyed strictly by
 * decision_id (bridge.py:239-246), and NEITHER src/owner_decision/ NOR
 * proposal_envelope.ledger.ProposalLedger enforces any proposal-level "one decision
 * per proposal" uniqueness anywhere. Deriving decision_id deterministically from
 * proposal_id instead of a fresh UUID per click is FRONTEND retry/recovery
 * defense-in-depth ONLY, scoped to THIS panel instance -- it is NOT a system-wide
 * guarantee. What it does buy, precisely: (a) a lost/retried response after CONFIRM,
 * from the SAME browser tab/session, replays safely against the same idempotency key
 * (no reprocessing); (b) a browser refresh in that SAME session can re-derive the same
 * key purely from the proposal_id already in hand, giving the only recovery path
 * available without a new backend read route; (c) from THIS UI, repeated clicks on the
 * same proposal_id in the same session always hit the same decision_id, so a second
 * click of the other button surfaces as ALREADY_DECIDED_MISMATCH below rather than
 * silently appearing to succeed. It does NOT prevent a second, different decision_id
 * (a second tab, a different device, a naive UUID-based retry elsewhere) from
 * producing an independent AUTHORIZED outcome server-side for the same proposal --
 * that residual gap is the bridge's/ledger's, not something this frontend trick
 * closes. Concretely: PROPOSAL_LEVEL_OWNER_DECISION_UNIQUENESS is NOT enforced by the
 * backend, and CROSS_CLIENT_AT_MOST_ONCE is NOT guaranteed by this mitigation.
 */
export function deriveDecisionId(proposalId: string): string {
  return `OWNER_DECISION:${proposalId}`;
}

export type RequestedAction = 'APPROVE_DEMO' | 'REJECT';

/**
 * UI-facing outcome classification. Distinct from OwnerDecisionResponse.status/
 * reason_code so the panel can render plain-language, distinctly-labeled copy for
 * every case without a generic "Trade failed" catch-all.
 *
 * Mapping notes (see status doc for the full rationale):
 *   - AUTHORIZED / REJECTED: the bridge's own terminal outcomes for THIS decision_id.
 *   - EXECUTION_DENIED <- reason_code === 'DEMO_NOT_AUTHORIZED' (strategy governance,
 *     strategies/registry.yaml-sourced, fails closed).
 *   - PROVENANCE_BLOCKED / ACCOUNT_BLOCKED: grepped against bridge.py and
 *     proposal_envelope/* -- NEITHER reason_code exists anywhere in this frozen
 *     backend today. Both are kept here as named outcomes for forward-compatibility
 *     (a future backend reason_code can be wired in without a frontend contract
 *     change) but nothing in classifySubmissionOutcome currently produces them; any
 *     rejection that isn't one of the concretely-known reason_codes below falls into
 *     the general ERROR/REJECTED buckets instead of being silently mapped to these.
 *   - ALREADY_DECIDED_MISMATCH <- the replayed/stored decision's underlying action
 *     disagrees with what was just requested (e.g. requested APPROVE_DEMO but the
 *     stored outcome's reason_code/status reflects an earlier REJECT, or vice versa).
 *   - AUTH_FAILED <- HTTP 401/503 from require_owner_auth (OWNER_AUTH_REJECTED /
 *     OWNER_AUTH_NOT_CONFIGURED).
 *   - NOT_FOUND <- reserved for a real HTTP 404; the owner-decision route itself never
 *     404s (an unknown proposal_id comes back HTTP 200 REJECTED/PROPOSAL_NOT_READY --
 *     see bridge.py:267-271), so this is only reachable if some other layer 404s.
 *   - CONFLICT <- HTTP 409, reserved (no current backend path uses it here).
 *   - CLIENT_OUTCOME_UNKNOWN <- a browser-side NETWORK/TIMEOUT AgApiError: this client
 *     genuinely does not know whether the server processed the request. Deliberately
 *     NOT named SUBMISSION_UNKNOWN -- there is no distinct server-side "submission"
 *     lifecycle state on this endpoint at all (no broker submission happens here).
 *   - SERVER_UNAVAILABLE <- HTTP 503 that isn't the owner-auth-not-configured case
 *     (kept distinct from AUTH_FAILED where the 503 body confirms OWNER_AUTH_NOT_CONFIGURED).
 *   - ERROR <- anything else (PARSE errors, unexpected reason_codes, etc).
 */
export type SubmissionOutcome =
  | { kind: 'AUTHORIZED'; response: OwnerDecisionResponse }
  | { kind: 'REJECTED'; response: OwnerDecisionResponse }
  | { kind: 'EXECUTION_DENIED'; response: OwnerDecisionResponse }
  | { kind: 'PROVENANCE_BLOCKED'; response: OwnerDecisionResponse }
  | { kind: 'ACCOUNT_BLOCKED'; response: OwnerDecisionResponse }
  | { kind: 'SYMBOL_MISMATCH'; response: OwnerDecisionResponse }
  | { kind: 'PROPOSAL_STALE'; response: OwnerDecisionResponse }
  | { kind: 'PROPOSAL_MALFORMED'; response: OwnerDecisionResponse }
  | { kind: 'ALREADY_DECIDED_MISMATCH'; response: OwnerDecisionResponse; requestedAction: RequestedAction }
  | { kind: 'AUTH_FAILED'; message: string; status?: number }
  // Distinct from AUTH_FAILED: HTTP 503 whose body's reason_code is specifically
  // OWNER_AUTH_NOT_CONFIGURED (app.py:151-156) -- a SERVER MISCONFIGURATION (the
  // AG_OWNER_API_KEY env var is unset), not a bad/missing owner key. AUTH_FAILED is
  // reserved for 401 OWNER_AUTH_REJECTED (a real, distinguishable credential failure).
  | { kind: 'AUTH_NOT_CONFIGURED'; message: string; status?: number }
  | { kind: 'NOT_FOUND'; message: string; status?: number }
  | { kind: 'CONFLICT'; message: string; status?: number }
  | { kind: 'CLIENT_OUTCOME_UNKNOWN'; message: string }
  // Any other 5xx, including a 503 that isn't OWNER_AUTH_NOT_CONFIGURED (e.g. a
  // network-level 503 from a proxy/load balancer, or a body that doesn't parse) --
  // never assumed to be an auth problem.
  | { kind: 'SERVER_UNAVAILABLE'; message: string; status?: number }
  | { kind: 'ERROR'; message: string; status?: number };

const REASON_DEMO_NOT_AUTHORIZED = 'DEMO_NOT_AUTHORIZED';
const REASON_OWNER_REJECTED = 'OWNER_REJECTED';
const REASON_SYMBOL_MISMATCH = 'SYMBOL_MISMATCH';
const REASON_PROPOSAL_STALE = 'PROPOSAL_STALE';
const REASON_PROPOSAL_MALFORMED = 'PROPOSAL_MALFORMED';
const REASON_PROPOSAL_NOT_READY = 'PROPOSAL_NOT_READY';
const REASON_BROKER_MUTATION_BLOCKED = 'BROKER_MUTATION_BLOCKED';
const REASON_NON_DEMO_ENVIRONMENT = 'NON_DEMO_ENVIRONMENT_REJECTED';
const REASON_MALFORMED_DECISION = 'MALFORMED_DECISION';
const REASON_OWNER_APPROVED_DEMO = 'OWNER_APPROVED_DEMO';

const STATUS_AUTHORIZED = 'AUTHORIZED';

/** True when a REJECTED response's reason_code reflects the decision itself being
 * rejected as an owner REJECT action (i.e. the stored/returned outcome IS a REJECT
 * decision, as opposed to an APPROVE_DEMO attempt that was denied by governance). */
function isOwnerRejectOutcome(response: OwnerDecisionResponse): boolean {
  return response.reason_code === REASON_OWNER_REJECTED;
}

/** Every reason_code the bridge can only reach on the APPROVE_DEMO path (see
 * bridge.py's own "From here on, action == APPROVE_DEMO" comment at line 260) except
 * REASON_MALFORMED_DECISION, which can occur before the action branch and so does not
 * reliably identify which action produced it. */
function isApproveDenialOutcome(response: OwnerDecisionResponse): boolean {
  return (
    response.status !== STATUS_AUTHORIZED &&
    [
      REASON_DEMO_NOT_AUTHORIZED,
      REASON_BROKER_MUTATION_BLOCKED,
      REASON_NON_DEMO_ENVIRONMENT,
      REASON_PROPOSAL_NOT_READY,
      REASON_SYMBOL_MISMATCH,
      REASON_PROPOSAL_STALE,
      REASON_PROPOSAL_MALFORMED,
    ].includes(response.reason_code)
  );
}

export function classifySubmissionOutcome(input: {
  requestedAction: RequestedAction;
  response?: OwnerDecisionResponse;
  httpStatus?: number;
  agApiError?: AgApiError;
}): SubmissionOutcome {
  const { requestedAction, response, httpStatus, agApiError } = input;

  if (agApiError) {
    if (agApiError.kind === 'NETWORK' || agApiError.kind === 'TIMEOUT') {
      return { kind: 'CLIENT_OUTCOME_UNKNOWN', message: agApiError.message };
    }
    if (agApiError.kind === 'HTTP') {
      const status = agApiError.status;
      if (status === 401) {
        // require_owner_auth: 401 OWNER_AUTH_REJECTED -- a missing/incorrect
        // X-AG-Owner-Key. A real, distinguishable credential failure.
        return { kind: 'AUTH_FAILED', message: agApiError.message, status };
      }
      if (status === 503) {
        // require_owner_auth's 503 body is {"reason_code": "OWNER_AUTH_NOT_CONFIGURED"}
        // (app.py:151-156). agFetch's HTTP error message embeds the parsed JSON body
        // verbatim (see agApiClient.ts's agFetch: `HTTP ${status} from ${path}: ${detail}`),
        // so a body-confirmed OWNER_AUTH_NOT_CONFIGURED is detectable by substring
        // match without this module importing agFetch's internals. Any other 503 (no
        // parseable body, a proxy/network-level 503, or a different reason_code) is
        // NOT assumed to be an auth problem and falls through to SERVER_UNAVAILABLE.
        if (agApiError.message.includes('OWNER_AUTH_NOT_CONFIGURED')) {
          return { kind: 'AUTH_NOT_CONFIGURED', message: agApiError.message, status };
        }
        return { kind: 'SERVER_UNAVAILABLE', message: agApiError.message, status };
      }
      if (status === 404) {
        return { kind: 'NOT_FOUND', message: agApiError.message, status };
      }
      if (status === 409) {
        return { kind: 'CONFLICT', message: agApiError.message, status };
      }
      if (status && status >= 500) {
        return { kind: 'SERVER_UNAVAILABLE', message: agApiError.message, status };
      }
      return { kind: 'ERROR', message: agApiError.message, status };
    }
    // PARSE or any other AgApiError kind.
    return { kind: 'ERROR', message: agApiError.message };
  }

  if (!response) {
    return { kind: 'ERROR', message: 'No response and no error -- unexpected caller state.' };
  }

  // Idempotent-replay mismatch check FIRST: a stored outcome whose underlying action
  // disagrees with what was just requested must never be presented as if the new
  // click took effect (bridge.py idempotency returns the ORIGINAL outcome verbatim).
  const storedIsReject = isOwnerRejectOutcome(response);
  const storedIsApproveDenial = isApproveDenialOutcome(response);
  const storedIsAuthorized =
    response.status === STATUS_AUTHORIZED && response.reason_code === REASON_OWNER_APPROVED_DEMO;

  if (requestedAction === 'APPROVE_DEMO' && storedIsReject) {
    return { kind: 'ALREADY_DECIDED_MISMATCH', response, requestedAction };
  }
  if (requestedAction === 'REJECT' && (storedIsAuthorized || storedIsApproveDenial)) {
    return { kind: 'ALREADY_DECIDED_MISMATCH', response, requestedAction };
  }

  if (response.status === STATUS_AUTHORIZED) {
    return { kind: 'AUTHORIZED', response };
  }

  switch (response.reason_code) {
    case REASON_DEMO_NOT_AUTHORIZED:
      return { kind: 'EXECUTION_DENIED', response };
    case REASON_SYMBOL_MISMATCH:
      return { kind: 'SYMBOL_MISMATCH', response };
    case REASON_PROPOSAL_STALE:
      return { kind: 'PROPOSAL_STALE', response };
    case REASON_PROPOSAL_MALFORMED:
      return { kind: 'PROPOSAL_MALFORMED', response };
    case REASON_OWNER_REJECTED:
      return { kind: 'REJECTED', response };
    default:
      // REASON_PROPOSAL_NOT_READY, REASON_BROKER_MUTATION_BLOCKED,
      // REASON_NON_DEMO_ENVIRONMENT, REASON_MALFORMED_DECISION, and any other real
      // rejection reason_code not given a more specific bucket above -- a general,
      // still-distinctly-labeled REJECTED outcome (never silently folded into ERROR;
      // reason_code/reasons remain in `response` for the panel to render verbatim).
      return { kind: 'REJECTED', response };
  }
}

/** Duplicate-click / in-flight-request guard. `tryStart()` returns false (does not
 * start a second submission) if a submission is already in flight; the caller must
 * call `finish()` in a finally block once the request settles (success or error). */
export function createSubmitGuard(): { tryStart: () => boolean; finish: () => void; isInFlight: () => boolean } {
  let inFlight = false;
  return {
    tryStart: () => {
      if (inFlight) return false;
      inFlight = true;
      return true;
    },
    finish: () => {
      inFlight = false;
    },
    isInFlight: () => inFlight,
  };
}
