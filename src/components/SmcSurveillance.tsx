import React from 'react';
import {
  Eye,
  ShieldCheck,
  AlertTriangle,
  CheckCircle,
  ArrowRight,
  Clock,
  Filter,
  Activity
} from 'lucide-react';
import { SMC_SURVEILLANCE_LIST } from '../data/tradingData';

export const SmcSurveillance: React.FC = () => {
  const items = SMC_SURVEILLANCE_LIST;

  const getStageBadge = (stage: string) => {
    switch (stage) {
      case 'STAGE_4_ENTRY_CONFIRMED':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            STAGE 4: CONFIRMED
          </span>
        );
      case 'STAGE_3_LTF_MSS':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            STAGE 3: LTF SHIFT
          </span>
        );
      case 'STAGE_2_LIQUIDITY_SWEEP':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-sky-500/20 text-sky-300 border border-sky-500/30">
            STAGE 2: LIQUIDITY
          </span>
        );
      case 'STAGE_1_POI_HIT':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            STAGE 1: POI HIT
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-400">
            MONITORING
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Authority Disclaimer */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 p-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <Eye className="w-4 h-4 text-sky-400" />
              <h2 className="text-sm font-semibold text-white tracking-wide uppercase font-mono">
                Large-SMC Multi-Symbol Surveillance Funnel
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Multi-timeframe institutional surveillance tracking HTF POIs, liquidity sweeps, and LTF Market Structure Shifts (MSS).
            </p>
          </div>
          <div className="px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-400">
            Strategy: <span className="text-amber-400 font-semibold">ST_LARGE_SMC_V1</span> (Forward Research / Non-Execution)
          </div>
        </div>
      </div>

      {/* Funnel Progress Visualizer */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { num: '01', title: 'HTF POI Reaction', desc: 'D1/H4 Order Block or Fair Value Gap tested with volume rejection' },
          { num: '02', title: 'Liquidity Purge', desc: 'Equal Highs/Lows or Prior Day High/Low swept into opposing zone' },
          { num: '03', title: 'LTF Structure Shift', desc: 'M5/M1 displacement creating valid CHoCH and inducement break' },
          { num: '04', title: 'Entry Confirmation', desc: 'C10 Stop Policy validation, risk sizing & proposal emission' }
        ].map((step, idx) => (
          <div key={step.num} className="rounded-lg bg-slate-900 border border-slate-800 p-3.5 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-lg font-mono font-bold text-slate-700">{step.num}</span>
              <span className="text-[10px] font-mono text-slate-500 uppercase">Step {idx + 1}</span>
            </div>
            <div className="mt-2 text-xs font-semibold text-slate-200">{step.title}</div>
            <p className="mt-1 text-[11px] text-slate-400 leading-normal">{step.desc}</p>
          </div>
        ))}
      </div>

      {/* Active Surveillance Watchlist Table */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">
            Watched Instruments ({items.length})
          </h3>
          <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
            <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span>Live Surveillance Engine Active</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Instrument</th>
                <th className="py-3 px-4">Timeframe</th>
                <th className="py-3 px-4">Institutional Bias</th>
                <th className="py-3 px-4">HTF Zone</th>
                <th className="py-3 px-4">Liquidity State</th>
                <th className="py-3 px-4">LTF Shift</th>
                <th className="py-3 px-4">Funnel Stage</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {items.map((row) => (
                <tr key={row.symbol} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3.5 px-4 font-bold text-white">
                    {row.symbol}
                    <div className="text-[10px] font-normal text-slate-400">{row.name}</div>
                  </td>
                  <td className="py-3.5 px-4 text-slate-300">{row.timeframe}</td>
                  <td className="py-3.5 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        row.bias === 'BULLISH'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : row.bias === 'BEARISH'
                          ? 'bg-rose-500/20 text-rose-300'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {row.bias}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-slate-300">
                    <div>{row.htfPoi.type.replace('_', ' ')}</div>
                    <div className="text-[10px] text-slate-500">
                      [{row.htfPoi.priceRange[0]} - {row.htfPoi.priceRange[1]}]
                    </div>
                  </td>
                  <td className="py-3.5 px-4">
                    {row.liquiditySwept ? (
                      <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                        <CheckCircle className="w-3 h-3" />
                        <span>Swept</span>
                      </span>
                    ) : (
                      <span className="text-slate-500">Unswept</span>
                    )}
                    <div className="text-[10px] text-slate-400 max-w-[150px] truncate">
                      {row.sweepDetails}
                    </div>
                  </td>
                  <td className="py-3.5 px-4">
                    <span
                      className={
                        row.ltfShift === 'CONFIRMED'
                          ? 'text-emerald-400 font-semibold'
                          : row.ltfShift === 'FORMING'
                          ? 'text-amber-400'
                          : 'text-slate-500'
                      }
                    >
                      {row.ltfShift}
                    </span>
                  </td>
                  <td className="py-3.5 px-4">{getStageBadge(row.confirmationStage)}</td>
                  <td className="py-3.5 px-4">
                    {row.alertStatus === 'ALERT_ACTIVE' ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30 animate-pulse">
                        ALERT ACTIVE
                      </span>
                    ) : (
                      <span className="text-slate-500 text-[10px]">Watching</span>
                    )}
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
