import React, { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
  Copy,
  Check,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  Info,
  Sliders
} from 'lucide-react';
import { SessionDecision, SessionCycle } from '../types';

interface DecisionMatrixProps {
  decisions: SessionDecision[];
  onClaimTicket?: (ticketId: string) => void;
}

export const DecisionMatrix: React.FC<DecisionMatrixProps> = ({ decisions, onClaimTicket }) => {
  const [selectedCycle, setSelectedCycle] = useState<string>('ALL');
  const [activeTicketModal, setActiveTicketModal] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [claimedStatus, setClaimedStatus] = useState<Record<string, boolean>>({});

  const filteredDecisions = decisions.filter((d) => {
    if (selectedCycle === 'ALL') return true;
    return d.cycle === selectedCycle;
  });

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleClaim = (ticketId: string) => {
    setClaimedStatus((prev) => ({ ...prev, [ticketId]: true }));
    if (onClaimTicket) onClaimTicket(ticketId);
  };

  const getDecisionBadge = (decision: string) => {
    switch (decision) {
      case 'READY':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded text-xs font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            READY
          </span>
        );
      case 'WATCH':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded text-xs font-mono font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30">
            <Clock className="w-3.5 h-3.5 mr-1" />
            WATCH
          </span>
        );
      case 'NO_TRADE':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded text-xs font-mono font-medium bg-slate-800 text-slate-400 border border-slate-700">
            <XCircle className="w-3.5 h-3.5 mr-1" />
            NO TRADE
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded text-xs font-mono font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30">
            <AlertTriangle className="w-3.5 h-3.5 mr-1" />
            DATA ERROR
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Deterministic Philosophy */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-white tracking-wide uppercase font-mono">
              Session Trade Decision Matrix
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Deterministic post-Asian & post-London session evaluations with fail-closed reason codes. Informational tickets only.
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400 font-mono">Filter Cycle:</span>
            <div className="flex bg-slate-950 p-0.5 rounded border border-slate-800 text-xs font-mono">
              {['ALL', 'ASIAN_LONDON', 'LONDON_NEWYORK', 'CRYPTO_DAILY'].map((c) => (
                <button
                  key={c}
                  onClick={() => setSelectedCycle(c)}
                  className={`px-2.5 py-1 rounded transition-colors ${
                    selectedCycle === c
                      ? 'bg-slate-800 text-white font-medium'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {c.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Grid of Decision Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredDecisions.map((item) => {
          const hasTicket = item.decision === 'READY' && item.entryTicket;
          const ticket = item.entryTicket;

          return (
            <div
              key={item.symbol + item.cycle}
              id={`card-${item.symbol}`}
              className={`rounded-lg border bg-slate-900 transition-all ${
                item.decision === 'READY'
                  ? 'border-emerald-500/50 shadow-lg shadow-emerald-950/20'
                  : 'border-slate-800'
              } p-4 flex flex-col justify-between`}
            >
              <div>
                {/* Symbol & State Header */}
                <div className="flex items-start justify-between pb-3 border-b border-slate-800">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-base font-bold text-white font-mono">{item.symbol}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                        {item.cycle}
                      </span>
                    </div>
                    <span className="text-xs text-slate-400">{item.name}</span>
                  </div>
                  <div>{getDecisionBadge(item.decision)}</div>
                </div>

                {/* Session Geometry & Telemetry */}
                <div className="grid grid-cols-2 gap-2 my-3 text-xs font-mono">
                  <div className="bg-slate-950/70 p-2 rounded border border-slate-800/80">
                    <div className="text-slate-500 text-[10px]">SESSION RANGE</div>
                    <div className="text-slate-200 font-semibold mt-0.5">
                      {item.sessionRangePips ? `${item.sessionRangePips} pips` : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-slate-950/70 p-2 rounded border border-slate-800/80">
                    <div className="text-slate-500 text-[10px]">SWEEP DETECTION</div>
                    <div className="text-slate-200 font-semibold mt-0.5">
                      {item.sweepDetected ? (
                        <span className="text-emerald-400">
                          {item.sweepSide} SWEPT
                        </span>
                      ) : (
                        <span className="text-slate-400">None detected</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Reason Code */}
                <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60 mb-3">
                  <div className="text-[10px] text-slate-500 font-mono">REASON CODE</div>
                  <div className="text-xs font-mono text-slate-300 break-words mt-0.5">
                    {item.reasonCode}
                  </div>
                </div>
              </div>

              {/* Action Button for READY tickets */}
              {hasTicket && ticket ? (
                <div className="pt-2 border-t border-slate-800">
                  <button
                    id={`view-ticket-${item.symbol}`}
                    onClick={() => setActiveTicketModal(activeTicketModal === item.symbol ? null : item.symbol)}
                    className="w-full py-2 px-3 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-semibold flex items-center justify-center space-x-1.5 transition-colors shadow"
                  >
                    <span>{activeTicketModal === item.symbol ? 'Hide Entry Ticket' : 'View Complete Entry Ticket'}</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              ) : (
                <div className="pt-2 border-t border-slate-800/50 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                  <span>No broker order sent</span>
                  <span>Evaluated 07:15 UTC</span>
                </div>
              )}

              {/* Expandable Entry Ticket */}
              {hasTicket && ticket && activeTicketModal === item.symbol && (
                <div className="mt-3 p-3 rounded bg-slate-950 border border-emerald-500/40 text-xs font-mono space-y-2.5">
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                    <div className="flex items-center space-x-1.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                        ENTRY TICKET (INFORMATIONAL)
                      </span>
                    </div>
                    <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300">
                      {ticket.direction}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      <span className="text-slate-500">Entry:</span>
                      <span className="ml-1 text-slate-100 font-bold">{ticket.entryPrice}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Stop Loss:</span>
                      <span className="ml-1 text-rose-400 font-bold">{ticket.stopLoss}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">TP1 (2.5R):</span>
                      <span className="ml-1 text-emerald-300">{ticket.tp1}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">TP2 (5.0R):</span>
                      <span className="ml-1 text-emerald-400 font-bold">{ticket.tp2}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Risk Sizing:</span>
                      <span className="ml-1 text-slate-200">{ticket.recommendedLots} Lots (${ticket.riskAmountUsd})</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Cutoff:</span>
                      <span className="ml-1 text-amber-300">{ticket.cutoffUtc.split('T')[1].substring(0, 5)} UTC</span>
                    </div>
                  </div>

                  <p className="text-[10px] text-slate-400 leading-relaxed italic bg-slate-900/60 p-2 rounded border border-slate-800/80">
                    "{ticket.rationale}"
                  </p>

                  <div className="flex items-center space-x-2 pt-1">
                    <button
                      onClick={() =>
                        handleCopy(
                          JSON.stringify(ticket, null, 2),
                          ticket.ticketId
                        )
                      }
                      className="flex-1 py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] flex items-center justify-center space-x-1 transition-colors"
                    >
                      {copiedId === ticket.ticketId ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-400" />
                          <span>Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3 text-slate-400" />
                          <span>Copy Proposal JSON</span>
                        </>
                      )}
                    </button>

                    <button
                      onClick={() => handleClaim(ticket.ticketId)}
                      disabled={claimedStatus[ticket.ticketId]}
                      className={`flex-1 py-1.5 px-2 rounded text-[10px] font-medium transition-colors ${
                        claimedStatus[ticket.ticketId]
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/40 cursor-default'
                          : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                      }`}
                    >
                      {claimedStatus[ticket.ticketId] ? 'Position Claimed (P6)' : 'Claim Ticket (Manual P6)'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
