import React from 'react';
import {
  FileCode,
  Shield,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Info,
  Terminal,
  BookOpen
} from 'lucide-react';
import { REGISTERED_STRATEGIES } from '../data/tradingData';

export const StrategyRegistryView: React.FC = () => {
  const strategies = REGISTERED_STRATEGIES;

  return (
    <div className="space-y-6">
      {/* Authority Order Banner */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 p-5">
        <h2 className="text-xs font-mono font-bold text-white uppercase tracking-wider flex items-center space-x-2 pb-2 border-b border-slate-800">
          <Terminal className="w-4 h-4 text-emerald-400" />
          <span>Execution Authority Hierarchy (Strict Determinism)</span>
        </h2>

        <div className="mt-4 p-3 rounded bg-slate-950 border border-slate-800/80 font-mono text-xs text-slate-300 space-y-1.5">
          <div className="text-emerald-400 font-bold">
            Strategy YAML &rarr; Strategy Engine &rarr; Execution Engine &rarr; MT5
          </div>
          <div className="text-amber-400/90">
            Agent Skills &rarr; ADVISORY ONLY (Reads and explains; no independent execution authority)
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 text-xs font-mono text-slate-400">
          <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800">
            <span className="text-white font-bold block mb-1">1. Strategy Engine</span>
            Deterministic calculations only. Never overrides a NO_TRADE result due to subjective sentiment.
          </div>
          <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800">
            <span className="text-white font-bold block mb-1">2. Risk Engine</span>
            Governs lot sizes, margin checks, and maximum account drawdown limits before order check.
          </div>
          <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800">
            <span className="text-white font-bold block mb-1">3. Execution Gateway</span>
            Requires explicit user confirmation (<span className="text-emerald-400">user_confirmed=True</span>). Live trading gated.
          </div>
        </div>
      </div>

      {/* Strategies List */}
      <div className="space-y-4">
        <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">
          Registered Strategy Contracts ({strategies.length})
        </h3>

        <div className="grid grid-cols-1 gap-4">
          {strategies.map((strat) => (
            <div
              key={strat.id}
              className="rounded-lg bg-slate-900 border border-slate-800 p-4 space-y-3"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-slate-800">
                <div className="flex items-center space-x-2.5">
                  <span className="font-mono font-bold text-white text-sm">{strat.id}</span>
                  <span className="text-xs text-slate-400">({strat.name})</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
                    v{strat.version}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
                  {strat.active ? (
                    <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      ACTIVE PILOT
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                      DORMANT / INCUBATION
                    </span>
                  )}

                  {strat.demoAuthorized ? (
                    <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">
                      DEMO AUTHORIZED
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      DEMO BLOCKED
                    </span>
                  )}

                  <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
                    LIVE DISABLED
                  </span>
                </div>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed font-mono">
                {strat.description}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-mono bg-slate-950 p-2.5 rounded border border-slate-800/80">
                <div>
                  <span className="text-slate-500">Engine Path:</span>
                  <span className="ml-1 text-slate-300">{strat.engine}</span>
                </div>
                <div>
                  <span className="text-slate-500">Allowed Symbols:</span>
                  <span className="ml-1 text-emerald-400 font-semibold">{strat.allowedSymbols.join(', ')}</span>
                </div>
                <div className="md:col-span-2">
                  <span className="text-slate-500">Risk Model:</span>
                  <span className="ml-1 text-slate-300">{strat.riskModel}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
