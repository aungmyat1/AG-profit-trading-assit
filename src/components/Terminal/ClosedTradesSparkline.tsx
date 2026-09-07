import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid
} from 'recharts';
import { Position } from '../../types/trading';
import {
  TrendingDown,
  Activity,
  ShieldAlert,
  ArrowDownRight,
  ArrowUpRight,
  Maximize2,
  Sparkles,
  Zap,
  Info
} from 'lucide-react';

interface ClosedTradesSparklineProps {
  positions: Position[];
  startingBalance?: number;
}

type SparklineMode = 'DRAWDOWN' | 'VOLATILITY';

interface SparkPoint {
  index: number;
  tradeNum: number;
  ticket: number;
  symbol: string;
  side: string;
  pnl: number;
  pnlR: number;
  equity: number;
  peakEquity: number;
  drawdownPercent: number;
  drawdownR: number;
  volatilityR: number; // absolute R deviation or trade return
  rollingStdDevR: number;
}

export const ClosedTradesSparkline: React.FC<ClosedTradesSparklineProps> = ({
  positions,
  startingBalance = 10000
}) => {
  const [mode, setMode] = useState<SparklineMode>('DRAWDOWN');

  // Filter closed positions and sort chronologically
  const closedSorted = useMemo(() => {
    return positions
      .filter(p => p.status === 'CLOSED')
      .sort((a, b) => (a.closeTime || a.openTime) - (b.closeTime || b.openTime));
  }, [positions]);

  // Take the last 10 closed trades (or all if less than 10)
  const last10Trades = useMemo(() => {
    return closedSorted.slice(-10);
  }, [closedSorted]);

  // Calculate drawdown and volatility series over this 10-trade window
  const sparkData = useMemo(() => {
    if (last10Trades.length === 0) return [];

    let currentEquity = startingBalance;
    let peakEquity = startingBalance;
    let peakR = 0;
    let runningR = 0;

    // Calculate baseline before window if prior trades exist
    const priorTrades = closedSorted.slice(0, Math.max(0, closedSorted.length - last10Trades.length));
    priorTrades.forEach(t => {
      currentEquity += t.pnl;
      runningR += t.pnlR;
      if (currentEquity > peakEquity) peakEquity = currentEquity;
      if (runningR > peakR) peakR = runningR;
    });

    const points: SparkPoint[] = [];
    const rValues: number[] = [];

    last10Trades.forEach((trade, idx) => {
      currentEquity += trade.pnl;
      runningR += trade.pnlR;
      rValues.push(trade.pnlR);

      if (currentEquity > peakEquity) {
        peakEquity = currentEquity;
      }
      if (runningR > peakR) {
        peakR = runningR;
      }

      // Drawdown calculation
      const ddDollars = Math.max(0, peakEquity - currentEquity);
      const ddPercent = peakEquity > 0 ? (ddDollars / peakEquity) * 100 : 0;
      const ddR = Math.max(0, peakR - runningR);

      // Rolling Volatility calculation (Standard Deviation of R-returns over available window)
      const meanR = rValues.reduce((a, b) => a + b, 0) / rValues.length;
      const variance = rValues.reduce((sum, r) => sum + Math.pow(r - meanR, 2), 0) / rValues.length;
      const stdDevR = Math.sqrt(variance);

      points.push({
        index: idx + 1,
        tradeNum: idx + 1,
        ticket: trade.ticket,
        symbol: trade.symbol,
        side: trade.side,
        pnl: trade.pnl,
        pnlR: trade.pnlR,
        equity: currentEquity,
        peakEquity,
        drawdownPercent: Number(ddPercent.toFixed(2)),
        drawdownR: Number(ddR.toFixed(2)),
        volatilityR: Math.abs(trade.pnlR),
        rollingStdDevR: Number(stdDevR.toFixed(2))
      });
    });

    return points;
  }, [last10Trades, closedSorted, startingBalance]);

  // Key metrics for the last 10 trades window
  const windowMetrics = useMemo(() => {
    if (sparkData.length === 0) {
      return {
        maxDrawdownPercent: 0,
        maxDrawdownR: 0,
        currentDrawdownPercent: 0,
        avgVolatilityR: 0,
        winCount: 0,
        lossCount: 0,
        windowWinRate: 0,
        windowNetR: 0,
        windowNetPnl: 0
      };
    }

    let maxDDPercent = 0;
    let maxDDR = 0;
    let totalVolR = 0;
    let wins = 0;
    let losses = 0;
    let netR = 0;
    let netPnl = 0;

    sparkData.forEach(p => {
      if (p.drawdownPercent > maxDDPercent) maxDDPercent = p.drawdownPercent;
      if (p.drawdownR > maxDDR) maxDDR = p.drawdownR;
      totalVolR += p.volatilityR;
      netR += p.pnlR;
      netPnl += p.pnl;
      if (p.pnl > 0) wins += 1;
      else if (p.pnl < 0) losses += 1;
    });

    const currentPoint = sparkData[sparkData.length - 1];

    return {
      maxDrawdownPercent: maxDDPercent,
      maxDrawdownR: maxDDR,
      currentDrawdownPercent: currentPoint ? currentPoint.drawdownPercent : 0,
      avgVolatilityR: Number((totalVolR / sparkData.length).toFixed(2)),
      winCount: wins,
      lossCount: losses,
      windowWinRate: Number(((wins / sparkData.length) * 100).toFixed(1)),
      windowNetR: Number(netR.toFixed(2)),
      windowNetPnl: netPnl
    };
  }, [sparkData]);

  if (sparkData.length === 0) {
    return null;
  }

  return (
    <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 shadow-sm font-sans space-y-3">
      {/* Top Header with Mode Switcher & Window Tag */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
            {mode === 'DRAWDOWN' ? (
              <TrendingDown className="w-4 h-4 text-rose-400" />
            ) : (
              <Activity className="w-4 h-4 text-cyan-400" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-200 font-mono uppercase tracking-wider">
                {mode === 'DRAWDOWN' ? 'Drawdown Curve' : 'Return Volatility'}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700 font-semibold">
                Last {sparkData.length} Trades Sparkline
              </span>
            </div>
          </div>
        </div>

        {/* Segmented Sparkline Toggle */}
        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-mono">
          <button
            id="sparkline-mode-drawdown"
            type="button"
            onClick={() => setMode('DRAWDOWN')}
            className={`px-2.5 py-1 rounded transition text-[11px] font-semibold flex items-center gap-1 ${
              mode === 'DRAWDOWN'
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingDown className="w-3 h-3 text-rose-400" />
            <span>Drawdown (%)</span>
          </button>
          <button
            id="sparkline-mode-volatility"
            type="button"
            onClick={() => setMode('VOLATILITY')}
            className={`px-2.5 py-1 rounded transition text-[11px] font-semibold flex items-center gap-1 ${
              mode === 'VOLATILITY'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Activity className="w-3 h-3 text-cyan-400" />
            <span>R-Volatility (σ)</span>
          </button>
        </div>
      </div>

      {/* Sparkline Visualizer Area */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
        {/* Chart Canvas */}
        <div className="md:col-span-8 h-28 w-full">
          <ResponsiveContainer width="100%" height="100%">
            {mode === 'DRAWDOWN' ? (
              <AreaChart data={sparkData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="drawdownSparkGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 2" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="index"
                  tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'monospace' }}
                  tickFormatter={val => `T${val}`}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <YAxis
                  reversed
                  domain={[0, (dataMax: number) => Math.max(1.5, Math.ceil(dataMax * 1.2))]}
                  tick={{ fill: '#64748b', fontSize: 9, fontFamily: 'monospace' }}
                  tickFormatter={val => `-${val}%`}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as SparkPoint;
                      return (
                        <div className="bg-slate-900 border border-slate-700 p-2 rounded shadow-xl font-mono text-[11px] space-y-1">
                          <div className="flex items-center justify-between gap-3 text-slate-300 font-bold border-b border-slate-800 pb-1">
                            <span>Trade #{data.ticket} ({data.symbol})</span>
                            <span className={data.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)} ({data.pnlR >= 0 ? '+' : ''}{data.pnlR.toFixed(2)}R)
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-slate-400">
                            <span>Drawdown:</span>
                            <span className="text-rose-400 font-bold">
                              -{data.drawdownPercent}% (-{data.drawdownR}R)
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-slate-400">
                            <span>Account Equity:</span>
                            <span className="text-slate-200">${data.equity.toFixed(2)}</span>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="drawdownPercent"
                  stroke="#f43f5e"
                  strokeWidth={2}
                  fill="url(#drawdownSparkGrad)"
                  dot={{ r: 2.5, fill: '#f43f5e', strokeWidth: 1, stroke: '#881337' }}
                  activeDot={{ r: 4, fill: '#fda4af', stroke: '#f43f5e', strokeWidth: 2 }}
                />
              </AreaChart>
            ) : (
              <LineChart data={sparkData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="volatilitySparkGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 2" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="index"
                  tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'monospace' }}
                  tickFormatter={val => `T${val}`}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <YAxis
                  domain={[-1.5, (dataMax: number) => Math.max(3.0, Math.ceil(dataMax * 1.1))]}
                  tick={{ fill: '#64748b', fontSize: 9, fontFamily: 'monospace' }}
                  tickFormatter={val => `${val}R`}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as SparkPoint;
                      return (
                        <div className="bg-slate-900 border border-slate-700 p-2 rounded shadow-xl font-mono text-[11px] space-y-1">
                          <div className="flex items-center justify-between gap-3 text-slate-300 font-bold border-b border-slate-800 pb-1">
                            <span>Trade #{data.ticket} ({data.symbol})</span>
                            <span className={data.pnlR >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {data.pnlR >= 0 ? '+' : ''}{data.pnlR.toFixed(2)} R
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-slate-400">
                            <span>Rolling StdDev:</span>
                            <span className="text-cyan-400 font-bold">±{data.rollingStdDevR} R</span>
                          </div>
                          <div className="flex items-center justify-between text-slate-400">
                            <span>Dollar PnL:</span>
                            <span className={data.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="pnlR"
                  stroke="#06b6d4"
                  strokeWidth={2}
                  dot={props => {
                    const { cx, cy, payload } = props;
                    const isWin = payload.pnlR >= 0;
                    return (
                      <circle
                        key={`dot-${payload.ticket}`}
                        cx={cx}
                        cy={cy}
                        r={3}
                        fill={isWin ? '#10b981' : '#f43f5e'}
                        stroke="#0f172a"
                        strokeWidth={1}
                      />
                    );
                  }}
                  activeDot={{ r: 5, fill: '#38bdf8', stroke: '#0369a1', strokeWidth: 2 }}
                />
              </LineChart>
            )}
          </ResponsiveContainer>
        </div>

        {/* Key Metrics Chips beside the chart */}
        <div className="md:col-span-4 grid grid-cols-2 gap-2 text-xs font-mono">
          <div className="bg-slate-900/90 border border-slate-800/80 p-2 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">
              {mode === 'DRAWDOWN' ? 'Max DD (10T)' : 'Avg Volatility'}
            </span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span
                className={`text-sm font-bold ${
                  mode === 'DRAWDOWN' ? 'text-rose-400' : 'text-cyan-300'
                }`}
              >
                {mode === 'DRAWDOWN'
                  ? `-${windowMetrics.maxDrawdownPercent}%`
                  : `±${windowMetrics.avgVolatilityR}R`}
              </span>
              {mode === 'DRAWDOWN' && (
                <span className="text-[10px] text-slate-500">
                  (-{windowMetrics.maxDrawdownR}R)
                </span>
              )}
            </div>
          </div>

          <div className="bg-slate-900/90 border border-slate-800/80 p-2 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">
              {mode === 'DRAWDOWN' ? 'Current DD' : '10-Trade Net R'}
            </span>
            <div className="flex items-baseline gap-1 mt-0.5">
              {mode === 'DRAWDOWN' ? (
                <span
                  className={`text-sm font-bold ${
                    windowMetrics.currentDrawdownPercent > 0
                      ? 'text-amber-400'
                      : 'text-emerald-400'
                  }`}
                >
                  {windowMetrics.currentDrawdownPercent === 0
                    ? '0.0% (Peak)'
                    : `-${windowMetrics.currentDrawdownPercent}%`}
                </span>
              ) : (
                <span
                  className={`text-sm font-bold ${
                    windowMetrics.windowNetR >= 0
                      ? 'text-emerald-400'
                      : 'text-rose-400'
                  }`}
                >
                  {windowMetrics.windowNetR >= 0 ? '+' : ''}{windowMetrics.windowNetR}R
                </span>
              )}
            </div>
          </div>

          <div className="bg-slate-900/90 border border-slate-800/80 p-2 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">
              Win Rate (10T)
            </span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="text-sm font-bold text-slate-200">
                {windowMetrics.windowWinRate}%
              </span>
              <span className="text-[10px] text-slate-500">
                ({windowMetrics.winCount}W / {windowMetrics.lossCount}L)
              </span>
            </div>
          </div>

          <div className="bg-slate-900/90 border border-slate-800/80 p-2 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">
              Window Return
            </span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span
                className={`text-sm font-bold ${
                  windowMetrics.windowNetPnl >= 0
                    ? 'text-emerald-400'
                    : 'text-rose-400'
                }`}
              >
                {windowMetrics.windowNetPnl >= 0 ? '+' : '-'}${Math.abs(windowMetrics.windowNetPnl).toFixed(0)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
