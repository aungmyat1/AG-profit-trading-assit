import React, { useState } from 'react';
import { TradeProposal, OpportunityAnalysis, SymbolName } from '../../types/trading';
import {
  KeyRound,
  ShieldCheck,
  CheckCircle,
  XCircle,
  Compass,
  AlertCircle,
  Code,
  Lock,
} from 'lucide-react';

interface OwnerAnalysisBridgeProps {
  selectedProposal: TradeProposal | null;
  opportunity: OpportunityAnalysis | null;
  symbol: SymbolName;
  onConfirmDecision: (proposalId: string, ownerKey: string) => void;
  onRejectDecision: (proposalId: string, ownerKey: string) => void;
  decisionResult?: {
    status: 'CONFIRMED' | 'REJECTED';
    commandTemplate?: string;
  } | null;
}

export const OwnerAnalysisBridge: React.FC<OwnerAnalysisBridgeProps> = ({
  selectedProposal,
  opportunity,
  symbol,
  onConfirmDecision,
  onRejectDecision,
  decisionResult,
}) => {
  const [ownerKey, setOwnerKey] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const handleAction = (type: 'CONFIRM' | 'REJECT') => {
    if (!selectedProposal) {
      setErrorMsg('Please select a proposal first.');
      return;
    }
    if (!ownerKey.trim()) {
      setErrorMsg('Owner Key required for authenticated decision (X-AG-Owner-Key).');
      return;
    }
    setErrorMsg('');
    if (type === 'CONFIRM') {
      onConfirmDecision(selectedProposal.id, ownerKey);
    } else {
      onRejectDecision(selectedProposal.id, ownerKey);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2.5">
          <Compass className="w-5 h-5 text-emerald-400" />
          <div>
            <h3 className="font-extrabold text-white text-base tracking-wide">
              OWNER ANALYSIS & DECISION DESK
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Top-Down Multi-Timeframe Alignment & Authenticated Decision Bridge
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-mono">
          <Lock className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-slate-400">Security Gate:</span>
          <span className="text-amber-300 font-semibold">REQUIRE_OWNER_AUTH (X-AG-Owner-Key)</span>
        </div>
      </div>

      {/* Multi-Timeframe Alignment Cards */}
      {opportunity && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block mb-1">
              HTF Trend (D1 / H4)
            </span>
            <div className="flex items-center justify-between">
              <span className="text-base font-bold text-white font-mono">
                {opportunity.timeframeAlignment.htfTrend}
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono font-medium ${
                  opportunity.timeframeAlignment.htfTrend === 'BULLISH'
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                    : 'bg-rose-950 text-rose-300 border border-rose-800'
                }`}
              >
                Structure Order
              </span>
            </div>
          </div>

          <div className="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block mb-1">
              MTF Bias (H1 Session Anchor)
            </span>
            <div className="flex items-center justify-between">
              <span className="text-base font-bold text-white font-mono">
                {opportunity.timeframeAlignment.mtfBias}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-indigo-950 text-indigo-300 border border-indigo-800">
                Session Range
              </span>
            </div>
          </div>

          <div className="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block mb-1">
              LTF Confirmation (M15 / M5)
            </span>
            <div className="flex items-center justify-between">
              <span className="text-base font-bold text-emerald-400 font-mono">
                {opportunity.timeframeAlignment.ltfConfirmation}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-emerald-950 text-emerald-300 border border-emerald-800">
                Imbalance / Breaker
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Narrative Section */}
      {opportunity && (
        <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 text-xs leading-relaxed">
          <div className="text-slate-400 font-mono text-[11px] uppercase tracking-wider mb-1 font-semibold flex items-center justify-between">
            <span>Opportunity Analysis Read-Model ({symbol})</span>
            <span className="text-emerald-400">Confidence: {opportunity.confidenceScore}%</span>
          </div>
          <p className="text-slate-200 mb-2">{opportunity.narrative}</p>
          <div className="text-emerald-300 font-mono text-[11px] bg-emerald-950/40 p-2 rounded border border-emerald-900/50">
            <strong>Recommended Action:</strong> {opportunity.recommendedAction}
          </div>
        </div>
      )}

      {/* Selected Proposal Overview */}
      {selectedProposal ? (
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 font-mono text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-400">Active Ticket for Owner Adjudication:</span>
            <span className="text-emerald-400 font-bold">{selectedProposal.id}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-slate-300 mb-3">
            <div>
              Direction: <strong className="text-white">{selectedProposal.direction}</strong>
            </div>
            <div>
              Entry: <strong className="text-white">{selectedProposal.entryPrice}</strong>
            </div>
            <div>
              SL: <strong className="text-rose-400">{selectedProposal.stopLoss}</strong>
            </div>
            <div>
              TP (5R): <strong className="text-emerald-400">{selectedProposal.target2}</strong>
            </div>
          </div>

          {/* Owner Key & Actions */}
          <div className="border-t border-slate-800/80 pt-3">
            <label className="block text-[11px] text-slate-400 mb-1 flex items-center gap-1.5 font-medium">
              <KeyRound className="w-3.5 h-3.5 text-amber-400" />
              <span>Owner Decision Key (X-AG-Owner-Key):</span>
            </label>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input
                type="password"
                placeholder="Enter owner key (e.g. AG-OWNER-KEY-...)"
                value={ownerKey}
                onChange={(e) => setOwnerKey(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-mono text-white focus:outline-none focus:border-emerald-500 placeholder:text-slate-600"
              />
              <button
                type="button"
                onClick={() => setOwnerKey('AG-OWNER-KEY-DEMO-V1')}
                className="px-2 py-1.5 text-[10px] font-mono text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-700 rounded-lg whitespace-nowrap"
              >
                Use Local Dev Key
              </button>
              <button
                type="button"
                onClick={() => handleAction('CONFIRM')}
                className="px-4 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-lg transition flex items-center justify-center gap-1.5 shadow-sm"
              >
                <CheckCircle className="w-4 h-4" />
                <span>CONFIRM PROPOSAL</span>
              </button>
              <button
                type="button"
                onClick={() => handleAction('REJECT')}
                className="px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg transition flex items-center justify-center gap-1.5 shadow-sm"
              >
                <XCircle className="w-4 h-4" />
                <span>REJECT</span>
              </button>
            </div>
            {errorMsg && (
              <p className="text-rose-400 text-[11px] mt-2 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errorMsg}
              </p>
            )}
          </div>
        </div>
      ) : (
        <div className="p-6 text-center text-slate-500 font-mono text-xs bg-slate-950/40 border border-dashed border-slate-800 rounded-xl">
          Select a session trade proposal from the left panel to review and record an authenticated owner decision.
        </div>
      )}

      {/* Generated Deterministic Execution Command Template */}
      {decisionResult && (
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 font-mono text-xs">
          <div className="flex items-center gap-2 text-slate-300 font-semibold mb-2">
            <Code className="w-4 h-4 text-emerald-400" />
            <span>Deterministic Command Artifact (Advisory State: {decisionResult.status})</span>
          </div>
          <p className="text-[11px] text-slate-400 mb-2 leading-relaxed">
            Per <code className="text-emerald-300">AGENTS.md</code> Authority Order #3: CONFIRM only produces a prepared, unconfirmed command template. It does not submit an order directly.
          </p>
          <pre className="bg-slate-900 p-3 rounded-lg border border-slate-800 text-slate-200 overflow-x-auto text-[11px] leading-relaxed">
            {decisionResult.commandTemplate ||
              `# Status: ${decisionResult.status}\n# Ticket: ${selectedProposal?.id}\n# Timestamp: ${new Date().toISOString()}`}
          </pre>
        </div>
      )}
    </div>
  );
};
