import React, { useState } from 'react';
import {
  FileText,
  TrendingUp,
  Award,
  BarChart3,
  CheckCircle,
  XCircle,
  Clock,
  ExternalLink,
  GitCompare
} from 'lucide-react';
import { HISTORICAL_JOURNAL } from '../data/tradingData';

export const JournalLedger: React.FC = () => {
  const [showReplayComparison, setShowReplayComparison] = useState<boolean>(false);
  const records = HISTORICAL_JOURNAL;

  const totalTrades = records.length;
  const wins = records.filter((r) => r.realizedR > 0).length;
  const winRate = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : '0';
  const totalR = records.reduce((acc, r) => acc + r.realizedR, 0).toFixed(1);

  return (
    <div className="space-y-6">
      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg bg-slate-900 border border-slate-800 p-3.5">
          <div className="text-[10px] text-slate-400 font-mono uppercase">Total Trades Logged</div>
          <div className="text-2xl font-mono font-bold text-white mt-1">{totalTrades}</div>
          <div className="text-[11px] text-slate-500 font-mono mt-0.5">Automated Shadow Runs</div>
        </div>
        <div className="rounded-lg bg-slate-900 border border-slate-800 p-3.5">
          <div className="text-[10px] text-slate-400 font-mono uppercase">Win Rate</div>
          <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">{winRate}%</div>
          <div className="text-[11px] text-slate-500 font-mono mt-0.5">Asymmetric 5R model</div>
        </div>
        <div className="rounded-lg bg-slate-900 border border-slate-800 p-3.5">
          <div className="text-[10px] text-slate-400 font-mono uppercase">Cumulative Realized R</div>
          <div className="text-2xl font-mono font-bold text-emerald-300 mt-1">+{totalR}R</div>
          <div className="text-[11px] text-slate-500 font-mono mt-0.5">+$550 Net P&L (1% risk)</div>
        </div>
        <div className="rounded-lg bg-slate-900 border border-slate-800 p-3.5">
          <div className="text-[10px] text-slate-400 font-mono uppercase">Profit Factor</div>
          <div className="text-2xl font-mono font-bold text-sky-400 mt-1">2.85</div>
          <div className="text-[11px] text-slate-500 font-mono mt-0.5">High expectancy baseline</div>
        </div>
      </div>

      {/* Replay Candidate Notice */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <GitCompare className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                Candidate Model A (Session Range 25%) Counterfactual Replay
              </h3>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Evaluates whether replacing arbitrary 2-pip tight buffers with 25% reference session range geometry eliminates whipsaw stopouts.
            </p>
          </div>
          <button
            onClick={() => setShowReplayComparison(!showReplayComparison)}
            className={`px-3 py-1.5 rounded text-xs font-mono font-semibold transition-colors flex items-center space-x-1.5 ${
              showReplayComparison
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'bg-slate-950 text-slate-300 border border-slate-800 hover:border-slate-700'
            }`}
          >
            <span>{showReplayComparison ? 'Showing Replay Data' : 'View Replay Comparison'}</span>
          </button>
        </div>

        {showReplayComparison && (
          <div className="mt-3 p-3 rounded bg-slate-950 border border-amber-500/30 text-xs font-mono space-y-2">
            <div className="text-amber-300 font-semibold">Counterfactual Finding (Sept 1-4, 2026):</div>
            <p className="text-slate-300 leading-relaxed text-[11px]">
              On EURUSD 2026-09-01, Legacy v1.1.1 used a 2.0-pip stop (1.16010) and got tagged at 07:11 UTC (-1.0R). Candidate Model A v1.1.2-RC1 computed SL at 1.15976 (5.4 pips buffer), held safely through the retest volatility, and successfully reached TP1 (+2.5R) and TP2 (+5.0R).
            </p>
          </div>
        )}
      </div>

      {/* Ledger Table */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider flex items-center space-x-2">
            <FileText className="w-4 h-4 text-emerald-400" />
            <span>Resolution Ledger (Contract AG_OUTCOME_RESOLUTION_V1)</span>
          </h3>
          <span className="text-xs font-mono text-slate-500">Immutable Records</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4">Proposal / Symbol</th>
                <th className="py-3 px-4">Cycle</th>
                <th className="py-3 px-4">Direction</th>
                <th className="py-3 px-4">Entry / SL</th>
                <th className="py-3 px-4">Outcome</th>
                <th className="py-3 px-4">Realized R</th>
                <th className="py-3 px-4">Net P&L</th>
                <th className="py-3 px-4">Evidence Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {records.map((r) => (
                <tr key={r.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3.5 px-4 text-slate-300 whitespace-nowrap">{r.date}</td>
                  <td className="py-3.5 px-4">
                    <span className="font-bold text-white">{r.symbol}</span>
                    <div className="text-[10px] text-slate-500 truncate max-w-[160px]">{r.proposalId}</div>
                  </td>
                  <td className="py-3.5 px-4 text-slate-300">{r.cycle}</td>
                  <td className="py-3.5 px-4">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        r.direction === 'LONG'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}
                    >
                      {r.direction}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-slate-300">
                    <div>{r.entry}</div>
                    <div className="text-[10px] text-rose-400">SL: {r.stopLoss}</div>
                  </td>
                  <td className="py-3.5 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        r.terminalState === 'RESOLVED_TP2'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : r.terminalState === 'RESOLVED_TP1'
                          ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      }`}
                    >
                      {r.terminalState.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-bold">
                    <span className={r.realizedR > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                      {r.realizedR > 0 ? `+${r.realizedR.toFixed(1)}R` : `${r.realizedR.toFixed(1)}R`}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-bold text-slate-200">
                    {r.profitUsd >= 0 ? `+$${r.profitUsd.toFixed(2)}` : `-$${Math.abs(r.profitUsd).toFixed(2)}`}
                  </td>
                  <td className="py-3.5 px-4 text-[11px] text-slate-400 max-w-[220px]">
                    {r.notes}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
