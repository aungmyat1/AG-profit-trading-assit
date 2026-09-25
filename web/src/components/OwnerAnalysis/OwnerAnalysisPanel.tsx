import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Lock, ShieldCheck, XCircle } from 'lucide-react';
import {
  agApiClient,
  AgApiError,
  CanonicalProposalResponse,
  OpportunityAnalysisResponse,
  OwnerDecisionResponse,
} from '../../utils/agApiClient';
import {
  classifySubmissionOutcome,
  createSubmitGuard,
  deriveDecisionId,
  RequestedAction,
  SubmissionOutcome,
} from './ownerDecisionLogic';

interface Props {
  /** Canonical proposals for the currently-selected symbol, as computed in App.tsx
   * via canonicalProposals.filter(p => p.symbol === selectedSymbol). ProposalLedger
   * enforces no symbol-uniqueness, so this is an array, not a single value -- see
   * the multi-proposal selection UX below. */
  proposals: CanonicalProposalResponse[];
  onRefresh?: () => void;
}

const submitGuard = createSubmitGuard();

export const OwnerAnalysisPanel: React.FC<Props> = ({ proposals, onRefresh }) => {
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [ownerKeyInput, setOwnerKeyInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [outcome, setOutcome] = useState<SubmissionOutcome | null>(null);
  const [analysis, setAnalysis] = useState<OpportunityAnalysisResponse | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Identity of the underlying proposal set, independent of the array's object
  // reference -- App.tsx creates a new array on every poll even when the same
  // proposals are still current, and resetting on that reference would drop the
  // owner's decision feedback every ~10s for no reason.
  const proposalsKey = useMemo(() => proposals.map(p => p.proposal_id).sort().join('|'), [proposals]);

  // Reset selection/outcome whenever the underlying proposal set for this symbol
  // actually changes (e.g. symbol switch, a proposal appearing/disappearing) --
  // never carry a stale decision outcome across a different proposal_id.
  useEffect(() => {
    setOutcome(null);
    if (proposals.length === 1) {
      setSelectedProposalId(proposals[0].proposal_id);
    } else if (proposals.length === 0) {
      setSelectedProposalId(null);
    } else if (selectedProposalId && !proposals.some(p => p.proposal_id === selectedProposalId)) {
      setSelectedProposalId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposalsKey]);

  // The singleton case is resolved synchronously here (not only in the effect
  // above) so a render that follows a fresh fetch never sees selectedProposal as
  // null while proposals.length === 1 -- the effect's setSelectedProposalId only
  // takes effect on the *next* render, and this component renders the selected
  // proposal unconditionally once exactly one is available.
  const selectedProposal = useMemo(() => {
    if (proposals.length === 1) return proposals[0];
    return proposals.find(p => p.proposal_id === selectedProposalId) || null;
  }, [proposals, selectedProposalId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedProposal) {
      setAnalysis(null);
      return;
    }
    agApiClient
      .getOpportunityAnalysis(selectedProposal.symbol)
      .then(results => {
        if (cancelled) return;
        // Never fall back to another strategy's analysis: on a symbol evaluated by
        // more than one strategy, showing results[0] would attribute a different
        // strategy's states/reasons/evidence to this proposal.
        const match = results.find(r => r.strategy_id === selectedProposal.strategy_id) || null;
        setAnalysis(match);
      })
      .catch(() => {
        // Display-only context; a failure here never blocks CONFIRM/REJECT.
        if (!cancelled) setAnalysis(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedProposal]);

  const submit = async (requestedAction: RequestedAction) => {
    if (!selectedProposal) return;
    if (!ownerKeyInput) {
      setOutcome({ kind: 'AUTH_FAILED', message: 'Enter the Owner Key before confirming or rejecting.' });
      return;
    }
    if (!submitGuard.tryStart()) return;
    setSubmitting(true);
    setOutcome(null);
    try {
      const response: OwnerDecisionResponse = await agApiClient.submitOwnerDecision(
        selectedProposal.proposal_id,
        {
          decision_id: deriveDecisionId(selectedProposal.proposal_id),
          action: requestedAction,
          symbol: selectedProposal.symbol,
          environment: 'DEMO',
        },
        ownerKeyInput,
      );
      if (!mountedRef.current) return;
      setOutcome(classifySubmissionOutcome({ requestedAction, response }));
    } catch (err) {
      if (!mountedRef.current) return;
      if (err instanceof AgApiError) {
        setOutcome(classifySubmissionOutcome({ requestedAction, agApiError: err }));
      } else {
        setOutcome({ kind: 'ERROR', message: err instanceof Error ? err.message : String(err) });
      }
    } finally {
      submitGuard.finish();
      if (mountedRef.current) setSubmitting(false);
    }
  };

  if (proposals.length === 0) {
    return (
      <section data-testid="owner-analysis" className="rounded-2xl border border-amber-500/30 bg-slate-900 p-6">
        <div className="flex items-center gap-3 text-amber-300">
          <AlertTriangle className="h-5 w-5" />
          <h2 className="text-lg font-bold">OWNER ANALYSIS · NO PROPOSAL</h2>
        </div>
        <p className="mt-3 text-sm text-slate-400">
          No canonical proposal is available for this symbol. The owner panel stays read-only
          until the backend's canonical proposal ledger publishes one.
        </p>
        {onRefresh && (
          <button onClick={onRefresh} className="mt-4 text-xs text-slate-500 underline">
            Refresh
          </button>
        )}
      </section>
    );
  }

  if (proposals.length > 1 && !selectedProposal) {
    return (
      <section data-testid="owner-analysis" className="rounded-2xl border border-cyan-500/30 bg-slate-900 p-6">
        <div className="flex items-center gap-3 text-cyan-300">
          <AlertTriangle className="h-5 w-5" />
          <h2 className="text-lg font-bold">OWNER ANALYSIS · MULTIPLE PROPOSALS</h2>
        </div>
        <p className="mt-3 text-sm text-slate-400">
          More than one canonical proposal exists for this symbol. Select one before
          CONFIRM/REJECT become available.
        </p>
        <ul className="mt-4 space-y-2">
          {proposals.map(p => (
            <li key={p.proposal_id}>
              <button
                onClick={() => setSelectedProposalId(p.proposal_id)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-3 text-left text-sm hover:border-cyan-400"
              >
                <div className="font-mono text-xs text-slate-400">{p.proposal_id}</div>
                <div className="mt-1">
                  {p.strategy_id} · {p.direction ?? '—'} · {p.proposal_state}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  const proposal = selectedProposal as CanonicalProposalResponse;
  const eligible =
    proposal.demo_authorized && !proposal.broker_mutation_blocked && proposal.proposal_state === 'PROPOSAL_READY';

  return (
    <section data-testid="owner-analysis" className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-cyan-500/30 bg-slate-900 p-5">
        <div>
          <p className="text-xs font-mono tracking-widest text-cyan-300">OWNER DECISION EXPERIENCE</p>
          <h1 className="mt-1 text-2xl font-bold">
            {proposal.symbol} · {proposal.direction ?? '—'}
          </h1>
          <p className="text-sm text-slate-400">
            {proposal.strategy_id} · v{proposal.strategy_version} · {proposal.proposal_id}
          </p>
        </div>
        <div
          className={`rounded-full border px-3 py-1 text-xs font-bold ${
            eligible ? 'border-emerald-500/40 text-emerald-300' : 'border-amber-500/40 text-amber-300'
          }`}
        >
          {proposal.proposal_state}
        </div>
      </div>

      {proposals.length > 1 && (
        <button
          onClick={() => setSelectedProposalId(null)}
          className="text-xs text-slate-500 underline"
        >
          Change selected proposal
        </button>
      )}

      {!eligible && (
        <div role="alert" className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200">
          This proposal is not currently eligible for a demo decision (demo_authorized=
          {String(proposal.demo_authorized)}, broker_mutation_blocked={String(proposal.broker_mutation_blocked)},
          proposal_state={proposal.proposal_state}). REJECT remains available; CONFIRM will be denied by the
          backend if attempted.
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Evidence title="CANONICAL PROPOSAL (backend-authoritative)" tone="cyan">
            <ul className="grid gap-2 text-sm text-slate-300 sm:grid-cols-2">
              <li>Direction: <b>{proposal.direction ?? '—'}</b></li>
              <li>Entry: <b>{proposal.entry ?? '—'}</b></li>
              <li>Stop: <b>{proposal.stop ?? '—'}</b></li>
              <li>Targets: <b>{proposal.targets.join(', ') || '—'}</b></li>
              <li>Watcher state: <b>{proposal.watcher_state}</b></li>
              <li>Market data: <b>{proposal.market_data_source ?? '—'} / {proposal.market_data_mode ?? '—'}</b></li>
            </ul>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-400">
              {proposal.reasons.map(reason => <li key={reason}>{reason}</li>)}
            </ul>
          </Evidence>
          {analysis && (
            <Evidence title="OPPORTUNITY ANALYSIS (observe-only narrative)" tone="slate">
              <ul className="grid gap-2 text-sm text-slate-300 sm:grid-cols-2">
                <li>Decision state: <b>{analysis.decision_state}</b></li>
                <li>Portfolio state: <b>{analysis.portfolio_state}</b></li>
                {analysis.missing_condition && <li>Missing: <b>{analysis.missing_condition}</b></li>}
                {analysis.next_required_evidence && <li>Next evidence: <b>{analysis.next_required_evidence}</b></li>}
              </ul>
              {analysis.reason_codes.length > 0 && (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-400">
                  {analysis.reason_codes.map(rc => <li key={rc}>{rc}</li>)}
                </ul>
              )}
            </Evidence>
          )}
        </div>

        <div className="space-y-5">
          <Evidence title="GOVERNANCE (fail-closed, backend-authoritative)" tone="slate">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Economic edge" value={String(proposal.economic_edge_established)} />
              <Metric label="Demo eligible" value={String(proposal.demo_eligible)} />
              <Metric label="Demo authorized" value={String(proposal.demo_authorized)} />
              <Metric label="Live authorized" value={String(proposal.live_authorized)} />
              <Metric label="Broker mutation blocked" value={String(proposal.broker_mutation_blocked)} />
              <Metric label="Lifecycle stage" value={proposal.lifecycle_stage ?? '—'} />
            </div>
            <p className="mt-4 text-xs text-amber-300">
              execution_authority is always NONE / execution_eligible is always false on this read
              model -- eligibility is decided entirely by demo_authorized/broker_mutation_blocked
              above, never by this panel.
            </p>
          </Evidence>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <label className="mb-2 flex items-center gap-2 text-xs font-bold tracking-widest text-slate-300">
              <Lock className="h-4 w-4" /> OWNER KEY (in-memory only, cleared on refresh)
            </label>
            <input
              type="password"
              autoComplete="off"
              value={ownerKeyInput}
              onChange={e => setOwnerKeyInput(e.target.value)}
              placeholder="X-AG-Owner-Key"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
            />
            <p className="mt-2 text-xs text-slate-500">
              Never stored, never logged. Sent only as a request header on CONFIRM/REJECT. Re-enter
              after any page reload.
            </p>
          </div>

          {outcome && <OutcomePanel outcome={outcome} />}

          <div className="flex gap-2">
            <button
              onClick={() => submit('REJECT')}
              disabled={submitting}
              className="flex items-center gap-2 rounded-lg border border-rose-500/50 px-4 py-2 text-sm text-rose-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <XCircle className="h-4 w-4" /> REJECT
            </button>
            <button
              onClick={() => submit('APPROVE_DEMO')}
              disabled={submitting}
              className="flex items-center gap-2 rounded-lg bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ShieldCheck className="h-4 w-4" /> CONFIRM DEMO (APPROVE)
            </button>
          </div>
        </div>
      </div>
      {onRefresh && (
        <button onClick={onRefresh} className="text-xs text-slate-500 underline">
          Refresh owner read model
        </button>
      )}
    </section>
  );
};

const OutcomePanel: React.FC<{ outcome: SubmissionOutcome }> = ({ outcome }) => {
  switch (outcome.kind) {
    case 'AUTHORIZED':
      return (
        <div className="rounded-2xl border border-emerald-500/40 bg-emerald-950/20 p-4">
          <p className="flex items-center gap-2 font-bold text-emerald-300">
            <CheckCircle2 className="h-4 w-4" /> AUTHORIZED
          </p>
          <p className="mt-2 text-sm text-slate-300">
            {outcome.response.execution_decision_prepared
              ? 'A trade command has been PREPARED but NOT submitted to any broker. A separate, explicitly-confirmed execution step is required before any order reaches MT5.'
              : 'Authorized, but no trade command was prepared.'}
          </p>
          {outcome.response.trade_command && (
            <pre className="mt-3 overflow-auto rounded-lg bg-slate-950/60 p-3 text-xs text-slate-400">
              {JSON.stringify(outcome.response.trade_command, null, 2)}
            </pre>
          )}
        </div>
      );
    case 'REJECTED':
      return (
        <Alert tone="slate">Rejected by backend ({outcome.response.reason_code}).</Alert>
      );
    case 'EXECUTION_DENIED':
      return (
        <Alert tone="amber">
          This strategy/proposal is not demo_authorized -- see strategies/registry.yaml governance.
          Denied ({outcome.response.reason_code}).
        </Alert>
      );
    case 'PROVENANCE_BLOCKED':
      return <Alert tone="amber">Blocked on data provenance grounds ({outcome.response.reason_code}).</Alert>;
    case 'ACCOUNT_BLOCKED':
      return <Alert tone="amber">Blocked on account/environment grounds ({outcome.response.reason_code}).</Alert>;
    case 'SYMBOL_MISMATCH':
      return <Alert tone="rose">Symbol mismatch between decision and proposal -- rejected.</Alert>;
    case 'PROPOSAL_STALE':
      return <Alert tone="rose">This proposal has expired (stale) -- rejected. Refresh to obtain a current proposal.</Alert>;
    case 'PROPOSAL_MALFORMED':
      return <Alert tone="rose">The proposal could not be converted to an execution template -- rejected.</Alert>;
    case 'ALREADY_DECIDED_MISMATCH':
      return (
        <Alert tone="amber">
          Already decided: this proposal's decision was already recorded as {outcome.response.status} (
          {outcome.response.reason_code}). Your {outcome.requestedAction} click did not take effect -- the
          stored decision is authoritative and immutable for this proposal.
        </Alert>
      );
    case 'AUTH_FAILED':
      return <Alert tone="rose">Owner authentication failed (wrong or missing key): {outcome.message}</Alert>;
    case 'AUTH_NOT_CONFIGURED':
      return (
        <Alert tone="rose">
          Backend owner authentication is not configured (AG_OWNER_API_KEY unset) -- this is a server
          misconfiguration, not your key: {outcome.message}
        </Alert>
      );
    case 'NOT_FOUND':
      return <Alert tone="rose">Not found: {outcome.message}</Alert>;
    case 'CONFLICT':
      return <Alert tone="rose">Conflict: {outcome.message}</Alert>;
    case 'CLIENT_OUTCOME_UNKNOWN':
      return (
        <Alert tone="amber">
          This browser could not confirm whether the request reached the backend ({outcome.message}). The
          decision may or may not have been processed. Re-submitting is safe -- the same decision_id will
          replay the original outcome rather than reprocessing.
        </Alert>
      );
    case 'SERVER_UNAVAILABLE':
      return <Alert tone="rose">Backend unavailable: {outcome.message}</Alert>;
    case 'ERROR':
    default:
      return <Alert tone="rose">Request failed: {outcome.message}</Alert>;
  }
};

const Alert: React.FC<{ tone: 'rose' | 'amber' | 'slate'; children: React.ReactNode }> = ({ tone, children }) => (
  <div
    role="alert"
    className={`rounded-xl border p-3 text-sm ${
      tone === 'rose'
        ? 'border-rose-500/40 bg-rose-950/30 text-rose-200'
        : tone === 'amber'
        ? 'border-amber-500/40 bg-amber-950/20 text-amber-200'
        : 'border-slate-700 bg-slate-900 text-slate-300'
    }`}
  >
    {children}
  </div>
);

const Evidence: React.FC<{ title: string; tone: 'cyan' | 'slate' | 'violet'; children: React.ReactNode }> = ({
  title,
  tone,
  children,
}) => (
  <div
    className={`rounded-2xl border p-4 ${
      tone === 'cyan'
        ? 'border-cyan-500/30 bg-cyan-950/10'
        : tone === 'violet'
        ? 'border-violet-500/30 bg-violet-950/10'
        : 'border-slate-800 bg-slate-900'
    }`}
  >
    <h2 className="mb-3 text-xs font-bold tracking-widest text-slate-300">{title}</h2>
    {children}
  </div>
);

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <p className="text-xs text-slate-500">{label}</p>
    <p className="font-mono text-sm text-slate-200">{value}</p>
  </div>
);
