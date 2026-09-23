// PANEL-R4/R5A canonical rewire: unit tests for the pure decision logic backing
// OwnerAnalysisPanel (web/src/components/OwnerAnalysis/ownerDecisionLogic.ts). Follows
// this repo's existing tsx --test / node:test convention (see wp5_proposal_authority.test.ts) --
// there is no component-rendering test infra, so only the dependency-free logic
// module is exercised here, with realistic fixture shapes matching src/api/schemas.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  classifySubmissionOutcome,
  createSubmitGuard,
  deriveDecisionId,
} from '../src/components/OwnerAnalysis/ownerDecisionLogic';
import { AgApiError, OwnerDecisionResponse } from '../src/utils/agApiClient';

function baseResponse(overrides: Partial<OwnerDecisionResponse> = {}): OwnerDecisionResponse {
  return {
    decision_id: 'OWNER_DECISION:EURUSD:abc123',
    proposal_envelope_id: 'EURUSD:abc123',
    status: 'REJECTED',
    reason_code: 'PROPOSAL_NOT_READY',
    reasons: [],
    execution_decision_prepared: false,
    trade_command: null,
    ...overrides,
  };
}

// -- deriveDecisionId --------------------------------------------------------------

test('deriveDecisionId is stable and deterministic per proposal_id', () => {
  const a1 = deriveDecisionId('EURUSD:abc123');
  const a2 = deriveDecisionId('EURUSD:abc123');
  assert.equal(a1, a2);
  assert.equal(a1, 'OWNER_DECISION:EURUSD:abc123');
});

test('deriveDecisionId differs for different proposal_ids', () => {
  assert.notEqual(deriveDecisionId('EURUSD:abc123'), deriveDecisionId('EURUSD:xyz789'));
});

// -- classifySubmissionOutcome: success/denial paths -------------------------------

test('AUTHORIZED response classifies as AUTHORIZED', () => {
  const response = baseResponse({
    status: 'AUTHORIZED',
    reason_code: 'OWNER_APPROVED_DEMO',
    execution_decision_prepared: true,
    trade_command: {
      command_id: 'OWNER_DECISION:EURUSD:abc123',
      action: 'OPEN',
      symbol: 'EURUSD',
      order_type: 'MARKET',
      proposal_id: 'EURUSD:abc123',
    },
  });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'AUTHORIZED');
});

test('OWNER_REJECTED reason_code classifies as REJECTED for a REJECT request', () => {
  const response = baseResponse({ status: 'REJECTED', reason_code: 'OWNER_REJECTED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'REJECT', response });
  assert.equal(outcome.kind, 'REJECTED');
});

test('DEMO_NOT_AUTHORIZED reason_code classifies as EXECUTION_DENIED', () => {
  const response = baseResponse({ status: 'REJECTED', reason_code: 'DEMO_NOT_AUTHORIZED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'EXECUTION_DENIED');
});

test('SYMBOL_MISMATCH reason_code gets its own distinct outcome, not folded into ERROR', () => {
  const response = baseResponse({ status: 'REJECTED', reason_code: 'SYMBOL_MISMATCH' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'SYMBOL_MISMATCH');
});

test('PROPOSAL_STALE reason_code gets its own distinct outcome', () => {
  const response = baseResponse({ status: 'REJECTED', reason_code: 'PROPOSAL_STALE' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'PROPOSAL_STALE');
});

test('PROPOSAL_MALFORMED reason_code gets its own distinct outcome', () => {
  const response = baseResponse({ status: 'REJECTED', reason_code: 'PROPOSAL_MALFORMED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'PROPOSAL_MALFORMED');
});

test('BROKER_MUTATION_BLOCKED and other governance denials classify as REJECTED (general bucket), never ERROR', () => {
  const response = baseResponse({ status: 'REJECTED', reason_code: 'BROKER_MUTATION_BLOCKED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'REJECTED');
});

// -- classifySubmissionOutcome: idempotent-replay cases -----------------------------

test('identical replay of the same decision_id classifies to the persisted outcome, not a fresh result', () => {
  // Simulates: owner clicked CONFIRM, got AUTHORIZED, then the same request replays
  // (e.g. a retried network call) with the SAME decision_id and the SAME requestedAction.
  const response = baseResponse({ status: 'AUTHORIZED', reason_code: 'OWNER_APPROVED_DEMO' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response });
  assert.equal(outcome.kind, 'AUTHORIZED');
});

// bridge.py:239-246 checks idempotency FIRST, before re-evaluating the requested
// action -- a replay of an existing decision_id ALWAYS returns the ORIGINAL stored
// ExecutionDecision verbatim, regardless of what the new request's `action` says. The
// three scenarios below simulate the HTTP layer already having done that replay (the
// `response` fixture IS the original stored outcome, unchanged) and check that
// classifySubmissionOutcome (1) never presents it as if the new click succeeded or
// replaced the original, and (2) preserves the original stored status/reason_code
// verbatim in the outcome it returns.

test('(a) original decision was REJECT; a later replay request with action=APPROVE_DEMO must reflect the original REJECTED result, never show APPROVE as having succeeded', () => {
  const originalReject = baseResponse({ status: 'REJECTED', reason_code: 'OWNER_REJECTED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', response: originalReject });
  assert.equal(outcome.kind, 'ALREADY_DECIDED_MISMATCH');
  if (outcome.kind === 'ALREADY_DECIDED_MISMATCH') {
    assert.equal(outcome.requestedAction, 'APPROVE_DEMO');
    // The original stored outcome is preserved verbatim -- never overwritten to look
    // like the new APPROVE_DEMO request took effect.
    assert.equal(outcome.response.status, 'REJECTED');
    assert.equal(outcome.response.reason_code, 'OWNER_REJECTED');
  }
});

test('(b) original decision was APPROVE_DEMO and was AUTHORIZED; a later replay request with action=REJECT must reflect the original AUTHORIZED result, never show REJECT as having succeeded', () => {
  const originalAuthorized = baseResponse({
    status: 'AUTHORIZED',
    reason_code: 'OWNER_APPROVED_DEMO',
    execution_decision_prepared: true,
  });
  const outcome = classifySubmissionOutcome({ requestedAction: 'REJECT', response: originalAuthorized });
  assert.equal(outcome.kind, 'ALREADY_DECIDED_MISMATCH');
  if (outcome.kind === 'ALREADY_DECIDED_MISMATCH') {
    assert.equal(outcome.requestedAction, 'REJECT');
    assert.equal(outcome.response.status, 'AUTHORIZED');
    assert.equal(outcome.response.reason_code, 'OWNER_APPROVED_DEMO');
  }
});

test('(c) original decision was an APPROVE_DEMO attempt the backend itself REJECTED (e.g. DEMO_NOT_AUTHORIZED); a later replay request with action=REJECT must reflect that original outcome, never imply the second REJECT click changed anything', () => {
  const originalGovernanceDenial = baseResponse({ status: 'REJECTED', reason_code: 'DEMO_NOT_AUTHORIZED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'REJECT', response: originalGovernanceDenial });
  assert.equal(outcome.kind, 'ALREADY_DECIDED_MISMATCH');
  if (outcome.kind === 'ALREADY_DECIDED_MISMATCH') {
    assert.equal(outcome.requestedAction, 'REJECT');
    assert.equal(outcome.response.status, 'REJECTED');
    assert.equal(outcome.response.reason_code, 'DEMO_NOT_AUTHORIZED');
  }
});

test('same decision_id replayed with the SAME action (true idempotent replay, not a mismatch) classifies to the persisted outcome itself', () => {
  const originalReject = baseResponse({ status: 'REJECTED', reason_code: 'OWNER_REJECTED' });
  const outcome = classifySubmissionOutcome({ requestedAction: 'REJECT', response: originalReject });
  assert.equal(outcome.kind, 'REJECTED');
});

// -- classifySubmissionOutcome: AgApiError paths -------------------------------------

test('NETWORK AgApiError classifies as CLIENT_OUTCOME_UNKNOWN, never SUBMISSION_UNKNOWN', () => {
  const err = new AgApiError('Network error reaching backend', 'NETWORK');
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'CLIENT_OUTCOME_UNKNOWN');
  // SubmissionOutcome's type union has no 'SUBMISSION_UNKNOWN' member at all -- this
  // is enforced at compile time (tsc --noEmit), not re-asserted at runtime here.
});

test('TIMEOUT AgApiError classifies as CLIENT_OUTCOME_UNKNOWN', () => {
  const err = new AgApiError('Request timed out', 'TIMEOUT');
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'CLIENT_OUTCOME_UNKNOWN');
});

test('HTTP 401 AgApiError classifies as AUTH_FAILED (OWNER_AUTH_REJECTED)', () => {
  const err = new AgApiError('HTTP 401 from .../owner-decision', 'HTTP', 401);
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'AUTH_FAILED');
});

test('HTTP 503 with OWNER_AUTH_NOT_CONFIGURED body classifies as AUTH_NOT_CONFIGURED, not AUTH_FAILED', () => {
  const err = new AgApiError(
    'HTTP 503 from /api/canonical-proposals/x/owner-decision: {"detail":{"reason_code":"OWNER_AUTH_NOT_CONFIGURED"}}',
    'HTTP',
    503,
  );
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'AUTH_NOT_CONFIGURED');
});

test('HTTP 503 with no parseable/matching reason_code classifies as SERVER_UNAVAILABLE, never AUTH_FAILED', () => {
  const err = new AgApiError('HTTP 503 from /api/canonical-proposals/x/owner-decision', 'HTTP', 503);
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'SERVER_UNAVAILABLE');
  assert.notEqual(outcome.kind, 'AUTH_FAILED');
});

test('HTTP 400 AgApiError (UNSUPPORTED_ACTION) classifies as generic ERROR with status carried through', () => {
  const err = new AgApiError('HTTP 400 from .../owner-decision', 'HTTP', 400);
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'ERROR');
  if (outcome.kind === 'ERROR') assert.equal(outcome.status, 400);
});

test('PARSE AgApiError classifies as ERROR', () => {
  const err = new AgApiError('Could not parse JSON', 'PARSE');
  const outcome = classifySubmissionOutcome({ requestedAction: 'APPROVE_DEMO', agApiError: err });
  assert.equal(outcome.kind, 'ERROR');
});

// -- createSubmitGuard: duplicate-click protection -----------------------------------

test('createSubmitGuard rejects a second concurrent tryStart before finish()', () => {
  const guard = createSubmitGuard();
  assert.equal(guard.tryStart(), true);
  assert.equal(guard.isInFlight(), true);
  assert.equal(guard.tryStart(), false, 'a second in-flight submission must be rejected');
  guard.finish();
  assert.equal(guard.isInFlight(), false);
  assert.equal(guard.tryStart(), true, 'a new submission is allowed once the prior one finished');
  guard.finish();
});
