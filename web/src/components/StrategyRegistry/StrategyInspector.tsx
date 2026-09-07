import React, { useState } from 'react';
import { StrategyContract } from '../../types/trading';
import {
  BookOpen,
  Shield,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileCode,
  Clock,
  Layers,
  ChevronRight,
  TrendingUp,
  BarChart2,
  ListChecks,
  Milestone,
  Flame,
  Coins,
  Check,
  Percent,
  Sparkles,
  Lock
} from 'lucide-react';

interface StrategyInspectorProps {
  strategies: StrategyContract[];
}

export const StrategyInspector: React.FC<StrategyInspectorProps> = ({ strategies }) => {
  const [selectedId, setSelectedId] = useState<string>(strategies[0]?.id || 'ST_ASIAN_SWEEP_5R_V1');
  const [activeTab, setActiveTab] = useState<'CONTRACT' | 'BACKTEST' | 'CONFLUENCE' | 'PROMOTION'>('CONTRACT');

  const selectedStrategy = strategies.find(s => s.id === selectedId) || strategies[0];

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Strategy Selector Sidebar */}
      <div className="w-full lg:w-80 flex flex-col gap-2">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-md">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider font-mono flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-cyan-400" />
              <span>Strategy Registry</span>
            </h3>
            <span className="text-[10px] font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
              {strategies.length} Registered
            </span>
          </div>

          <div className="space-y-2">
            {strategies.map(s => {
              const isSelected = s.id === selectedId;
              const isActive = s.status === 'ACTIVE_INCUBATION';

              return (
                <button
                  key={s.id}
                  id={`strat-card-${s.id}`}
                  onClick={() => setSelectedId(s.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex flex-col gap-1.5 ${
                    isSelected
                      ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-sm'
                      : 'bg-slate-950/60 border-slate-800/80 text-slate-300 hover:bg-slate-800/50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold">{s.id}</span>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                        isActive
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {s.status}
                    </span>
                  </div>
                  <div className="text-xs text-slate-300 truncate font-medium">{s.name}</div>
                  <div className="text-[10px] font-mono text-slate-400 flex items-center gap-2 mt-1">
                    <span>v{s.version}</span>
                    <span>•</span>
                    <span>{s.timeframe}</span>
                    <span>•</span>
                    <span className="text-cyan-400 font-semibold">{s.targets.totalTargetR}R Target</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Authority Hierarchy Notice */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3.5 text-slate-400 text-xs space-y-1.5 font-mono">
          <div className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-cyan-400" />
            <span>Authority Architecture</span>
          </div>
          <p className="text-[10px] text-slate-400 leading-relaxed">
            Deterministic strategy code dictates signal validity. Advisory skills explain context without independent execution authority. Live orders require human confirmation.
          </p>
        </div>
      </div>

      {/* Selected Strategy Deep-Dive Contract & Details Viewer */}
      <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
        {/* Header Banner */}
        <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-slate-100">{selectedStrategy.name}</h2>
              <span className="px-2.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-mono text-xs font-bold">
                {selectedStrategy.id}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 font-mono">
              Family: <strong className="text-slate-200">{selectedStrategy.family}</strong> | Magic Number: <strong className="text-slate-200">#{selectedStrategy.magicNumber}</strong> | Base TF: <strong className="text-slate-200">{selectedStrategy.timeframe}</strong>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono">
              <Shield className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-slate-400">Demo Auth:</span>
              <span className={selectedStrategy.authority.demoAuthorized ? 'text-emerald-400 font-bold' : 'text-slate-500'}>
                {selectedStrategy.authority.demoAuthorized ? 'YES (AUTHORIZED)' : 'NO (ADVISORY)'}
              </span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono">
              <Lock className="w-3.5 h-3.5 text-rose-400" />
              <span className="text-slate-400">Live Auth:</span>
              <span className="text-rose-400 font-bold">LOCKED</span>
            </div>
          </div>
        </div>

        {/* View Mode Navigation Tabs */}
        <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 font-mono text-xs gap-1">
          <button
            type="button"
            id="tab-strat-contract"
            onClick={() => setActiveTab('CONTRACT')}
            className={`flex-1 py-2 rounded-lg font-bold transition flex items-center justify-center gap-1.5 ${
              activeTab === 'CONTRACT'
                ? 'bg-cyan-500 text-slate-950 shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <FileCode className="w-3.5 h-3.5" />
            <span>Rules & Contract</span>
          </button>
          <button
            type="button"
            id="tab-strat-backtest"
            onClick={() => setActiveTab('BACKTEST')}
            className={`flex-1 py-2 rounded-lg font-bold transition flex items-center justify-center gap-1.5 ${
              activeTab === 'BACKTEST'
                ? 'bg-emerald-500 text-slate-950 shadow'
                : 'text-emerald-400 hover:text-emerald-300 hover:bg-slate-900'
            }`}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span>Backtest & EV Edge</span>
          </button>
          <button
            type="button"
            id="tab-strat-confluence"
            onClick={() => setActiveTab('CONFLUENCE')}
            className={`flex-1 py-2 rounded-lg font-bold transition flex items-center justify-center gap-1.5 ${
              activeTab === 'CONFLUENCE'
                ? 'bg-indigo-500 text-slate-950 shadow'
                : 'text-indigo-400 hover:text-indigo-300 hover:bg-slate-900'
            }`}
          >
            <ListChecks className="w-3.5 h-3.5" />
            <span>Confluence Checklist</span>
          </button>
          <button
            type="button"
            id="tab-strat-promotion"
            onClick={() => setActiveTab('PROMOTION')}
            className={`flex-1 py-2 rounded-lg font-bold transition flex items-center justify-center gap-1.5 ${
              activeTab === 'PROMOTION'
                ? 'bg-amber-500 text-slate-950 shadow'
                : 'text-amber-400 hover:text-amber-300 hover:bg-slate-900'
            }`}
          >
            <Milestone className="w-3.5 h-3.5" />
            <span>Promotion Gates</span>
          </button>
        </div>

        {/* TAB 1: RULES & CONTRACT */}
        {activeTab === 'CONTRACT' && (
          <div className="space-y-6">
            {/* Instruments & Session Pairs */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <h4 className="text-xs font-mono font-bold text-slate-400 uppercase mb-2 flex items-center gap-1.5">
                  <Coins className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Supported Instruments</span>
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {selectedStrategy.instruments.map(inst => (
                    <span
                      key={inst}
                      className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-xs font-mono text-cyan-300 font-semibold"
                    >
                      {inst}
                    </span>
                  ))}
                </div>
              </div>

              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <h4 className="text-xs font-mono font-bold text-slate-400 uppercase mb-2 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Session Windows (UTC)</span>
                </h4>
                <div className="space-y-2 text-xs font-mono text-slate-300">
                  {selectedStrategy.sessionPairs.map(sp => (
                    <div key={sp.pairId} className="flex justify-between items-center bg-slate-900 p-2 rounded border border-slate-800">
                      <span className="text-indigo-300">{sp.referenceSession.name} ({sp.referenceSession.startTimeGmt}-{sp.referenceSession.endTimeGmt})</span>
                      <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                      <span className="text-emerald-300">{sp.tradeSession.name} ({sp.tradeSession.startTimeGmt}-{sp.tradeSession.endTimeGmt})</span>
                    </div>
                  ))}
                  {selectedStrategy.sessionPairs.length === 0 && (
                    <span className="text-slate-500">Higher Timeframe (HTF) / No intraday session boundary restriction</span>
                  )}
                </div>
              </div>
            </div>

            {/* Deterministic Entry & Invalidation Rules */}
            <div className="space-y-3">
              <h4 className="text-xs font-mono font-bold text-slate-400 uppercase">Deterministic Trigger Specifications</h4>

              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3 font-mono text-xs">
                <div>
                  <span className="text-cyan-400 font-bold block mb-1">Long Entry Trigger:</span>
                  <div className="bg-slate-900 p-2.5 rounded border border-slate-800 text-slate-200">
                    <strong className="text-cyan-300">{selectedStrategy.entryRules.longTrigger}</strong>: {selectedStrategy.entryRules.condition}
                  </div>
                </div>

                <div>
                  <span className="text-rose-400 font-bold block mb-1">Short Entry Trigger:</span>
                  <div className="bg-slate-900 p-2.5 rounded border border-slate-800 text-slate-200">
                    <strong className="text-rose-300">{selectedStrategy.entryRules.shortTrigger}</strong>: {selectedStrategy.entryRules.condition}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                  <div className="bg-slate-900/80 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-400 block text-[11px]">Time Cutoff Invalidation:</span>
                    <span className="text-amber-300 font-semibold">{selectedStrategy.invalidation.time}</span>
                  </div>
                  <div className="bg-slate-900/80 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-400 block text-[11px]">Structural Invalidation:</span>
                    <span className="text-rose-400 font-semibold">{selectedStrategy.invalidation.structural}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Position Split & Multi-Leg Targets */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-mono font-bold text-slate-400 uppercase">
                  Multi-Leg Target Split Execution
                </h4>
                <span className="text-cyan-400 font-bold font-mono text-xs">
                  {selectedStrategy.targets.totalTargetR}R Composite Target
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-xs">
                {selectedStrategy.targets.legs.map(leg => (
                  <div key={leg.legId} className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1.5">
                    <div className="flex justify-between text-cyan-300 font-bold">
                      <span>Leg #{leg.legId} ({leg.volumePct * 100}% Volume)</span>
                      <span>{leg.fixedR ? `${leg.fixedR}R Target` : leg.targetType}</span>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Target Type: <span className="text-slate-200">{leg.targetType}</span>
                    </div>
                    {leg.actionOnFill && (
                      <div className="text-[11px] text-emerald-400 font-semibold flex items-center gap-1">
                        <Check className="w-3 h-3" />
                        <span>Action on Fill: {leg.actionOnFill}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: BACKTEST & EV EDGE */}
        {activeTab === 'BACKTEST' && selectedStrategy.backtestMetrics && (
          <div className="space-y-4 font-mono text-xs">
            {/* Top Stat Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5">
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase block">Win Rate</span>
                <span className="text-lg font-bold text-emerald-400">
                  {selectedStrategy.backtestMetrics.winRate}%
                </span>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase block">Profit Factor</span>
                <span className="text-lg font-bold text-cyan-400">
                  {selectedStrategy.backtestMetrics.profitFactor}
                </span>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase block">Expected Value</span>
                <span className="text-lg font-bold text-emerald-300">
                  +{selectedStrategy.backtestMetrics.expectedValueR}R
                </span>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase block">Sharpe Ratio</span>
                <span className="text-lg font-bold text-indigo-400">
                  {selectedStrategy.backtestMetrics.sharpeRatio}
                </span>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase block">Max Drawdown</span>
                <span className="text-lg font-bold text-rose-400">
                  {selectedStrategy.backtestMetrics.maxDrawdownPct}%
                </span>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase block">Sample Size</span>
                <span className="text-lg font-bold text-slate-200">
                  N={selectedStrategy.backtestMetrics.sampleSize}
                </span>
              </div>
            </div>

            {/* Edge Analysis Summary */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-slate-300 uppercase flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-emerald-400" />
                  <span>Quantitative Edge Breakdown</span>
                </h4>
                <span className="text-slate-400 text-[11px]">
                  Avg Trade Duration: <strong className="text-slate-200">{selectedStrategy.backtestMetrics.avgTradeDuration}</strong>
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px] text-slate-300 leading-relaxed">
                <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1">
                  <span className="font-bold text-cyan-300 block">Asymmetric Reward Advantage:</span>
                  <p className="text-slate-400">
                    By securing 75% of profits at the opposite session boundary (+2.5R to +3.0R) and allowing 25% to run to 5.0R risk-free, the system achieves a high expectancy even with realistic conservative execution slippage.
                  </p>
                </div>
                <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1">
                  <span className="font-bold text-emerald-300 block">Drawdown Resistance:</span>
                  <p className="text-slate-400">
                    Peak drawdown is constrained to {selectedStrategy.backtestMetrics.maxDrawdownPct}%. Under a 1.0% risk model, 10 consecutive stop-outs produce &lt;9.6% peak-to-trough account contraction, well inside capital preservation guidelines.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: CONFLUENCE CHECKLIST */}
        {activeTab === 'CONFLUENCE' && selectedStrategy.confluenceCriteria && (
          <div className="space-y-3 font-mono text-xs">
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
              <h4 className="text-xs font-bold text-slate-300 uppercase mb-3 flex items-center gap-2">
                <ListChecks className="w-4 h-4 text-indigo-400" />
                <span>Pre-Flight Execution Criteria (Institutional Confluence)</span>
              </h4>

              <div className="space-y-2.5">
                {selectedStrategy.confluenceCriteria.map(crit => (
                  <div
                    key={crit.id}
                    className="bg-slate-900 p-3 rounded-lg border border-slate-800 flex items-start gap-3"
                  >
                    <span className="p-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mt-0.5">
                      <CheckCircle2 className="w-4 h-4" />
                    </span>
                    <div className="flex-1 space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-200 font-bold">{crit.title}</span>
                        {crit.mandatory ? (
                          <span className="text-[9px] font-bold uppercase px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                            Mandatory Gate
                          </span>
                        ) : (
                          <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                            Secondary
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed">
                        {crit.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: PROMOTION GATES */}
        {activeTab === 'PROMOTION' && selectedStrategy.promotionGates && (
          <div className="space-y-4 font-mono text-xs">
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 uppercase block">Current Lifecycle Stage</span>
                  <span className="text-sm font-bold text-amber-300">
                    {selectedStrategy.promotionGates.stage}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-slate-400 uppercase block">Target Stage</span>
                  <span className="text-sm font-bold text-cyan-300">
                    {selectedStrategy.promotionGates.nextStage}
                  </span>
                </div>
              </div>

              {/* Progress Bar */}
              <div>
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="text-slate-400">Stage Qualification Progress</span>
                  <span className="text-cyan-400 font-bold">{selectedStrategy.promotionGates.currentProgressPct}%</span>
                </div>
                <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-500"
                    style={{ width: `${selectedStrategy.promotionGates.currentProgressPct}%` }}
                  />
                </div>
              </div>

              {/* Requirements Checklist */}
              <div>
                <h5 className="text-[11px] font-bold text-slate-300 uppercase mb-2">
                  Remaining Promotion Requirements:
                </h5>
                <div className="space-y-2">
                  {selectedStrategy.promotionGates.criteriaNeeded.map((req, i) => (
                    <div key={i} className="flex items-center gap-2 bg-slate-900 p-2.5 rounded border border-slate-800 text-[11px] text-slate-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                      <span>{req}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
