import React from 'react';
import { TradeProposal, SymbolName } from '../../types/trading';
import {
  FileText,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Target,
  Shield,
  Layers,
  Send,
} from 'lucide-react';

interface ProposalsPanelProps {
  proposals: TradeProposal[];
  selectedProposalId?: string;
  onSelectProposal: (p: TradeProposal) => void;
  onSendToDecisionDesk: (p: TradeProposal) => void;
  activeSymbol: SymbolName;
}

export const ProposalsPanel: React.FC<ProposalsPanelProps> = ({
  proposals,
  selectedProposalId,
  onSelectProposal,
  onSendToDecisionDesk,
  activeSymbol,
}) => {
  const filtered = proposals.filter((p) => p.symbol === activeSymbol);
  const displayList = filtered.length > 0 ? filtered : proposals;

  const getStatusBadge = (status: TradeProposal['status']) => {
    switch (status) {
      case 'READY':
        return {
          bg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />,
        };
      case 'WATCH':
        return {
          bg: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
          icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />,
        };
      case 'PENDING':
        return {
          bg: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
          icon: <FileText className="w-3.5 h-3.5 text-blue-400" />,
        };
      default:
        return {
          bg: 'bg-slate-700/20 text-slate-400 border-slate-700',
          icon: null,
        };
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-4 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-emerald-400" />
          <h3 className="font-bold text-white text-sm tracking-wide">
            DETERMINISTIC SESSION TRADE TICKETS
          </h3>
        </div>
        <span className="text-xs font-mono text-slate-400">
          Showing {displayList.length} registered proposals
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {displayList.map((p) => {
          const statusInfo = getStatusBadge(p.status);
          const isSelected = selectedProposalId === p.id;
          const isLong = p.direction === 'LONG';

          return (
            <div
              key={p.id}
              onClick={() => onSelectProposal(p)}
              className={`p-4 rounded-xl border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-slate-800/80 border-emerald-500/60 ring-1 ring-emerald-500/30 shadow-md'
                  : 'bg-slate-950/60 border-slate-800 hover:border-slate-700 hover:bg-slate-950'
              }`}
            >
              {/* Header row */}
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-black font-mono border ${
                      isLong
                        ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                        : 'bg-rose-950 text-rose-400 border-rose-800'
                    }`}
                  >
                    {isLong ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                    {p.direction} {p.symbol}
                  </span>
                  <span className="text-xs font-mono text-slate-300 font-semibold">{p.session}</span>
                  <span className="text-[11px] font-mono text-slate-500">({p.strategyVersion})</span>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-medium border ${statusInfo.bg}`}
                  >
                    {statusInfo.icon}
                    {p.status}
                  </span>
                </div>
              </div>

              {/* ID row */}
              <div className="text-[11px] font-mono text-slate-400 mb-3 truncate">
                Ticket: <span className="text-slate-300">{p.id}</span>
              </div>

              {/* Grid of pricing & risk geometry */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-900/90 p-2.5 rounded-lg border border-slate-800/80 font-mono text-xs mb-3">
                <div>
                  <div className="text-slate-500 text-[10px]">ENTRY PRICE</div>
                  <div className="font-bold text-white text-sm">{p.entryPrice}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px]">STOP LOSS (SL)</div>
                  <div className="font-semibold text-rose-400">{p.stopLoss}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px]">TARGET (5R)</div>
                  <div className="font-semibold text-emerald-400">{p.target2}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px]">LOTS / RISK</div>
                  <div className="font-semibold text-indigo-300">
                    {p.lotSize} lots (${p.riskAmount.toFixed(0)})
                  </div>
                </div>
              </div>

              {/* Rationale snippet */}
              <p className="text-xs text-slate-300 mb-3 leading-relaxed">
                {p.rationale}
              </p>

              {/* Reason codes & Decision Desk CTA */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800/70">
                <div className="flex flex-wrap items-center gap-1.5">
                  {p.reasonCodes.map((rc, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-900 text-slate-400 border border-slate-800"
                    >
                      {rc}
                    </span>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSendToDecisionDesk(p);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-medium rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 transition shadow-sm"
                >
                  <Send className="w-3 h-3" />
                  <span>Review in Decision Desk</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
