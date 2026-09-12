// WP5.2 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): positive-trust provenance checks.
// Proves isAuthoritativeProposal() fails closed for synthetic, missing, and unknown
// provenance, and only trusts a proposal with executionEligible === true explicitly.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isAuthoritativeProposal } from '../src/utils/proposalAuthority';
import { TradeProposal } from '../src/types/trading';

function baseProposal(overrides: Partial<TradeProposal> = {}): TradeProposal {
  return {
    id: 'p1', symbol: 'EURUSD', strategyId: 'ST_ASIAN_SWEEP_5R_V1', strategyName: 'x',
    timestamp: Date.now(), state: 'READY' as any, bias: 'BULLISH',
    riskReward: 3, riskPips: 20, suggestedLots: 1, reasons: [],
    regime: { ema50Trend: 'BULLISH', rangePips: 10, isRangeValid: true },
    safetyGate: { spreadOk: true, dailyLossOk: true, sessionTimeOk: true },
    ...overrides,
  };
}

test('synthetic proposal is non-authoritative', () => {
  const p = baseProposal({ marketDataSource: 'SYNTHETIC', executionEligible: false });
  assert.equal(isAuthoritativeProposal(p), false);
});

test('missing provenance (untagged) is non-authoritative', () => {
  const p = baseProposal(); // no marketDataSource, no executionEligible
  assert.equal(isAuthoritativeProposal(p), false);
});

test('unknown/malformed executionEligible value is non-authoritative', () => {
  const p = baseProposal({ executionEligible: undefined });
  assert.equal(isAuthoritativeProposal(p), false);
});

test('null/undefined proposal is non-authoritative', () => {
  assert.equal(isAuthoritativeProposal(null), false);
  assert.equal(isAuthoritativeProposal(undefined), false);
});

test('only executionEligible === true is authoritative', () => {
  const p = baseProposal({ marketDataSource: 'MT5', executionEligible: true });
  assert.equal(isAuthoritativeProposal(p), true);
});

test('MT5 source alone without executionEligible flag is still non-authoritative', () => {
  // Guards against a future proposal source that tags marketDataSource correctly but
  // forgets to compute executionEligible -- must fail closed, not trust source alone.
  const p = baseProposal({ marketDataSource: 'MT5' });
  assert.equal(isAuthoritativeProposal(p), false);
});
