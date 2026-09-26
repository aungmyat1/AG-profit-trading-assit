import React from 'react';
import { BacktestSummary } from '../../types/trading';
import {
  FlaskConical,
  BarChart2,
  CheckCircle,
  FileCode,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';

interface ResearchLabProps {
  backtest: BacktestSummary;
}

export const ResearchLab: React.FC<ResearchLabProps> = ({ backtest }) => {
  const strategies = [
    {
      id: 'ST_ASIAN_SWEEP_5R_V1',
      version: '1.1.2-RC1',
      state: 'VALIDATED / FROZEN',
      assetClass: 'FX (EURUSD, GBPUSD)',
      role: 'Session Sweeps',
      rules: 'Asian session range sweep into London Open, M15 displacement, FVG fill, 5R TP',
    },
    {
      id: 'ST_SESSION_SWEEP_CONTINUATION_V1',
      version: '1.0.1',
      state: 'CANDIDATE',
      assetClass: 'FX (EURUSD, GBPUSD)',
      role: 'Trend Continuation',
      rules: 'London high/low liquidity sweep with multi-timeframe trend alignment, 3R TP',
    },
    {
      id: 'ST_LARGE_SMC_V1',
      version: '1.0.7',
      state: 'RESEARCH_DRAFT',
      assetClass: 'FX & Crypto (BTCUSDT)',
      role: 'SMC Funnel Surveillance',
      rules: 'Higher timeframe (D1/H4) supply/demand blocks with lower timeframe (H1/M5) confirmation',
    },
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-5 shadow-sm">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-emerald-400" />
            <h3 className="font-extrabold text-white text-base tracking-wide">
              RESEARCH LAB & VALIDATION LEDGER
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono">
            Deterministic Strategy Registry & Historical Replay Evidence (Aug-Sep 2025)
          </p>
        </div>

        <div className="flex items-center gap-2 bg-emerald-950/40 px-3 py-1.5 rounded-lg border border-emerald-800/80 text-xs font-mono text-emerald-300">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>Readiness Overall: PASS (2,666 tests clean)</span>
        </div>
      </div>

      {/* Replay Metrics Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">TOTAL REPLAY STEPS</div>
          <div className="font-bold text-white text-base mt-0.5">{backtest.totalSteps.toLocaleString()}</div>
          <div className="text-[10px] text-slate-400 mt-1">M5 Closed Candles</div>
        </div>

        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">WIN RATE</div>
          <div className="font-bold text-emerald-400 text-base mt-0.5">{backtest.winRate}%</div>
          <div className="text-[10px] text-slate-400 mt-1">Ready Setups: {backtest.readySignals}</div>
        </div>

        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">PROFIT FACTOR</div>
          <div className="font-bold text-emerald-400 text-base mt-0.5">{backtest.profitFactor}</div>
          <div className="text-[10px] text-slate-400 mt-1">Sharpe: {backtest.sharpeRatio}</div>
        </div>

        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">MAX DRAWDOWN</div>
          <div className="font-bold text-amber-400 text-base mt-0.5">{backtest.maxDrawdownR} R</div>
          <div className="text-[10px] text-slate-400 mt-1">Controlled Risk Floor</div>
        </div>
      </div>

      {/* Combinations Chart */}
      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
        <div className="flex items-center gap-2 mb-3">
          <BarChart2 className="w-4 h-4 text-emerald-400" />
          <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300 font-mono">
            SMC Entry-Confirmation Funnel Combinations (Discovery 2mo)
          </h4>
        </div>
        <div className="h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={backtest.combinations} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <XAxis dataKey="name" stroke="#475569" fontSize={10} tickLine={false} />
              <YAxis stroke="#475569" fontSize={10} tickLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#090d16',
                  borderColor: '#1e293b',
                  borderRadius: '8px',
                  color: '#fff',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                }}
              />
              <Bar dataKey="setups" name="Total Setups" fill="#334155" radius={[4, 4, 0, 0]} />
              <Bar dataKey="ready" name="Confirmed Ready" fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Registered Strategies Table */}
      <div>
        <div className="flex items-center gap-2 mb-2 font-mono text-xs text-slate-300 font-bold uppercase tracking-wider">
          <FileCode className="w-4 h-4 text-emerald-400" />
          <span>Frozen Strategy Contracts (strategies/registry.yaml)</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-xs">
          {strategies.map((st) => (
            <div key={st.id} className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-bold text-white text-xs truncate">{st.id}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                    {st.version}
                  </span>
                </div>
                <div className="text-[10px] text-emerald-400 font-semibold mb-2">{st.state}</div>
                <p className="text-[11px] text-slate-400 leading-relaxed mb-3">{st.rules}</p>
              </div>
              <div className="text-[10px] text-slate-500 border-t border-slate-800/80 pt-2 flex items-center justify-between">
                <span>{st.assetClass}</span>
                <span className="text-slate-400">{st.role}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
