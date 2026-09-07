import React from 'react';
import { TradeProposal, DecisionState } from '../../types/trading';
import {
  CheckCircle2,
  Clock,
  XCircle,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  ShieldCheck,
  Zap,
  Coins,
  Sparkles,
  DollarSign
} from 'lucide-react';

interface ScannerProps {
  proposals: TradeProposal[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onExecuteProposal: (prop: TradeProposal) => void;
}

export const SignalScanner: React.FC<ScannerProps> = ({
  proposals,
  selectedSymbol,
  onSelectSymbol,
  onExecuteProposal
}) => {
  const getStateBadge = (state: DecisionState) => {
    switch (state) {
      case 'READY':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            READY
          </span>
        );
      case 'WATCH':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
            <Clock className="w-3 h-3 text-amber-400" />
            WATCH
          </span>
        );
      case 'NO_TRADE':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-slate-800 text-slate-400 border border-slate-700">
            <XCircle className="w-3 h-3 text-slate-500" />
            NO_TRADE
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
            <AlertCircle className="w-3 h-3" />
            DATA_ERROR
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Scanner Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Zap className="w-5 h-5 text-cyan-400" />
              <span>Deterministic Session Signal Scanner</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Continuously evaluates canonical Asian Session Ranges (&le; 25.0 pips), London Open wicks (07:00-11:00 UTC), EMA 50 trend alignment, and computes 5.0R split-target proposals.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 text-center font-mono">
              <div className="text-[10px] text-slate-400 uppercase">Ready Signals</div>
              <div className="text-base font-bold text-emerald-400">
                {proposals.filter(p => p.state === 'READY').length}
              </div>
            </div>
            <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 text-center font-mono">
              <div className="text-[10px] text-slate-400 uppercase">Monitoring</div>
              <div className="text-base font-bold text-amber-400">
                {proposals.filter(p => p.state === 'WATCH').length}
              </div>
            </div>
            <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 text-center font-mono">
              <div className="text-[10px] text-slate-400 uppercase">Target Multiplier</div>
              <div className="text-base font-bold text-cyan-400">5.0 R</div>
            </div>
          </div>
        </div>
      </div>

      {/* Proposals Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {proposals.map(prop => {
          const isSelected = selectedSymbol === prop.symbol;
          const isReady = prop.state === 'READY';

          return (
            <div
              key={prop.id}
              className={`flex flex-col justify-between bg-slate-900 border rounded-xl p-4 transition-all shadow-md ${
                isSelected
                  ? 'border-cyan-500/60 ring-1 ring-cyan-500/30'
                  : 'border-slate-800 hover:border-slate-700'
              } ${isReady ? 'bg-gradient-to-b from-emerald-950/20 to-slate-900 border-emerald-500/30' : ''}`}
            >
              {/* Card Top */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-base font-bold text-slate-100">{prop.symbol}</span>
                    <span className="text-[11px] font-mono text-slate-400">{prop.strategyId}</span>
                  </div>
                  {getStateBadge(prop.state)}
                </div>

                {/* Regime & Session Range Metrics */}
                <div className="grid grid-cols-2 gap-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 mb-3 text-xs font-mono">
                  <div>
                    <span className="text-[10px] text-slate-400 block">Asian Range</span>
                    <span
                      className={`font-semibold ${
                        prop.regime.isRangeValid ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {prop.regime.rangePips > 0 ? `${prop.regime.rangePips} pips` : 'N/A'}{' '}
                      {prop.regime.isRangeValid ? '(&le;25p)' : '(>25p)'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">50 EMA Bias</span>
                    <span
                      className={`font-semibold flex items-center gap-1 ${
                        prop.regime.ema50Trend === 'BULLISH' ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {prop.regime.ema50Trend === 'BULLISH' ? (
                        <TrendingUp className="w-3 h-3" />
                      ) : (
                        <TrendingDown className="w-3 h-3" />
                      )}
                      {prop.regime.ema50Trend}
                    </span>
                  </div>
                </div>

                {/* Trade Setup Parameters if READY */}
                {isReady && prop.entryPrice && prop.stopLoss && (
                  <div className="bg-emerald-950/30 border border-emerald-500/20 rounded-lg p-3 mb-3 text-xs font-mono space-y-2">
                    <div className="flex justify-between items-center text-emerald-300 font-bold border-b border-emerald-500/20 pb-1">
                      <span className="flex items-center gap-1">
                        <Sparkles className="w-3 h-3 text-emerald-400" />
                        <span>{prop.entrySide} MARKET</span>
                      </span>
                      <span className="text-[11px] bg-emerald-500/20 px-1.5 py-0.5 rounded text-emerald-300 font-mono">
                        {prop.suggestedLots} Lots
                      </span>
                    </div>
                    <div className="space-y-1 text-slate-300 text-[11px]">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Entry:</span>
                        <span>{prop.entryPrice.toFixed(5)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Stop Loss:</span>
                        <span className="text-rose-400">{prop.stopLoss.toFixed(5)} ({prop.riskPips} pips)</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">TP1 (75% opposite):</span>
                        <span className="text-emerald-400">{prop.takeProfit1?.toFixed(5)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">TP2 (25% 5R):</span>
                        <span className="text-cyan-400 font-bold">{prop.takeProfit2?.toFixed(5)}</span>
                      </div>
                    </div>
                    {/* Money-Making Expectancy Ribbon */}
                    <div className="pt-1.5 border-t border-emerald-500/20 flex items-center justify-between text-[10px]">
                      <div>
                        <span className="text-slate-400 block">ASYMMETRIC EDGE</span>
                        <span className="text-emerald-400 font-bold font-mono">+1.85R Expectancy</span>
                      </div>
                      <div className="text-right">
                        <span className="text-slate-400 block">COMPOSITE TARGET</span>
                        <span className="text-cyan-300 font-bold font-mono">3.125R Net</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Decision Reasons */}
                <div className="space-y-1 text-[11px] text-slate-400 mb-3">
                  {prop.reasons.slice(0, 2).map((r, i) => (
                    <div key={i} className="flex items-start gap-1.5">
                      <span className="text-cyan-500 mt-0.5">•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Card Footer Actions */}
              <div className="flex items-center gap-2 pt-2 border-t border-slate-800">
                <button
                  id={`inspect-${prop.symbol}`}
                  onClick={() => onSelectSymbol(prop.symbol)}
                  className={`flex-1 py-1.5 px-3 rounded text-xs font-medium transition flex items-center justify-center gap-1 ${
                    isSelected
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                  }`}
                >
                  <span>View Chart</span>
                  <ArrowRight className="w-3 h-3" />
                </button>

                {isReady && (
                  <button
                    id={`exec-btn-${prop.symbol}`}
                    onClick={() => onExecuteProposal(prop)}
                    className="py-1.5 px-3 rounded text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950 transition shadow flex items-center gap-1"
                  >
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Execute</span>
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
