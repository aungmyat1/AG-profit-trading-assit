import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
  Area,
  ComposedChart
} from 'recharts';
import { Position } from '../../types/trading';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Award,
  Activity,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Maximize2,
  Calendar,
  Sparkles
} from 'lucide-react';

interface EquityCurveChartProps {
  positions: Position[];
  startingBalance?: number;
}

interface EquityPoint {
  index: number;
  ticket: number | string;
  timeStr: string;
  timestamp: number;
  symbol: string;
  side: string;
  tradePnl: number;
  tradeR: number;
  equity: number;
  cumulativePnl: number;
  cumulativeR: number;
  peakEquity: number;
  drawdownDollars: number;
  drawdownPercent: number;
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({
  positions,
  startingBalance = 10000
}) => {
  const [metricMode, setMetricMode] = useState<'equity' | 'rMultiple'>('equity');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('ALL');

  // Filter and sort closed trades chronologically by closeTime (or openTime)
  const closedTrades = useMemo(() => {
    return positions
      .filter(p => p.status === 'CLOSED')
      .sort((a, b) => (a.closeTime || a.openTime) - (b.closeTime || b.openTime));
  }, [positions]);

  const uniqueSymbols = useMemo(() => {
    const syms = Array.from(new Set(closedTrades.map(p => p.symbol)));
    return ['ALL', ...syms];
  }, [closedTrades]);

  const filteredTrades = useMemo(() => {
    if (selectedSymbol === 'ALL') return closedTrades;
    return closedTrades.filter(p => p.symbol === selectedSymbol);
  }, [closedTrades, selectedSymbol]);

  // Build equity time series data points
  const equityData: EquityPoint[] = useMemo(() => {
    const points: EquityPoint[] = [];

    // Starting baseline point (before first trade)
    const baseTime = filteredTrades.length > 0
      ? (filteredTrades[0].openTime - 3600)
      : Math.floor(Date.now() / 1000) - 86400 * 7;

    const baseDate = new Date(baseTime * 1000);
    const baseDateStr = `${baseDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} Base`;

    points.push({
      index: 0,
      ticket: 'START',
      timeStr: baseDateStr,
      timestamp: baseTime,
      symbol: 'BASE',
      side: 'FLAT',
      tradePnl: 0,
      tradeR: 0,
      equity: startingBalance,
      cumulativePnl: 0,
      cumulativeR: 0,
      peakEquity: startingBalance,
      drawdownDollars: 0,
      drawdownPercent: 0
    });

    let runningEquity = startingBalance;
    let runningCumulativePnl = 0;
    let runningCumulativeR = 0;
    let peak = startingBalance;

    filteredTrades.forEach((trade, i) => {
      runningCumulativePnl += trade.pnl;
      runningCumulativeR += trade.pnlR;
      runningEquity = startingBalance + runningCumulativePnl;

      if (runningEquity > peak) {
        peak = runningEquity;
      }

      const ddDollars = peak - runningEquity;
      const ddPct = peak > 0 ? (ddDollars / peak) * 100 : 0;

      const tradeTime = trade.closeTime || trade.openTime;
      const d = new Date(tradeTime * 1000);
      const timeStr = `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })}`;

      points.push({
        index: i + 1,
        ticket: trade.ticket,
        timeStr,
        timestamp: tradeTime,
        symbol: trade.symbol,
        side: trade.side,
        tradePnl: trade.pnl,
        tradeR: trade.pnlR,
        equity: Number(runningEquity.toFixed(2)),
        cumulativePnl: Number(runningCumulativePnl.toFixed(2)),
        cumulativeR: Number(runningCumulativeR.toFixed(2)),
        peakEquity: Number(peak.toFixed(2)),
        drawdownDollars: Number(ddDollars.toFixed(2)),
        drawdownPercent: Number(ddPct.toFixed(2))
      });
    });

    return points;
  }, [filteredTrades, startingBalance]);

  // Overall Statistics from the series
  const summaryStats = useMemo(() => {
    const lastPoint = equityData[equityData.length - 1];
    const totalReturnDollars = lastPoint.equity - startingBalance;
    const totalReturnPercent = (totalReturnDollars / startingBalance) * 100;
    const maxDrawdownPct = Math.max(...equityData.map(p => p.drawdownPercent), 0);
    const maxDrawdownDollars = Math.max(...equityData.map(p => p.drawdownDollars), 0);
    const finalR = lastPoint.cumulativeR;
    const peakEquity = Math.max(...equityData.map(p => p.equity), startingBalance);

    return {
      currentEquity: lastPoint.equity,
      totalReturnDollars,
      totalReturnPercent,
      maxDrawdownPct,
      maxDrawdownDollars,
      finalR,
      peakEquity,
      tradesCount: filteredTrades.length
    };
  }, [equityData, startingBalance, filteredTrades.length]);

  // Min and max for domain bounds on chart
  const { minVal, maxVal } = useMemo(() => {
    if (metricMode === 'equity') {
      const vals = equityData.map(d => d.equity);
      const min = Math.min(...vals, startingBalance);
      const max = Math.max(...vals, startingBalance);
      const padding = (max - min) * 0.15 || 100;
      return {
        minVal: Math.floor(min - padding),
        maxVal: Math.ceil(max + padding)
      };
    } else {
      const vals = equityData.map(d => d.cumulativeR);
      const min = Math.min(...vals, 0);
      const max = Math.max(...vals, 0);
      const padding = (max - min) * 0.2 || 1.0;
      return {
        minVal: Number((min - padding).toFixed(1)),
        maxVal: Number((max + padding).toFixed(1))
      };
    }
  }, [equityData, metricMode, startingBalance]);

  // Custom Recharts Tooltip Component
  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;
    const data: EquityPoint = payload[0].payload;

    if (data.ticket === 'START') {
      return (
        <div className="bg-slate-950 border border-slate-700 p-3 rounded-lg shadow-xl font-mono text-xs text-slate-200">
          <div className="text-slate-400 font-bold mb-1">Baseline Starting Capital</div>
          <div>Initial Balance: <strong className="text-emerald-400">${startingBalance.toLocaleString()}</strong></div>
          <div className="text-[10px] text-slate-500 mt-1">{data.timeStr}</div>
        </div>
      );
    }

    const isWin = data.tradePnl > 0;

    return (
      <div className="bg-slate-950/95 border border-slate-700 p-3.5 rounded-xl shadow-2xl font-mono text-xs space-y-2 min-w-[220px] backdrop-blur-md">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
          <div className="flex items-center gap-1.5 font-bold">
            <span className="text-cyan-300">{data.symbol}</span>
            <span className={`text-[10px] px-1.5 py-0.2 rounded ${data.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
              {data.side}
            </span>
          </div>
          <span className="text-slate-500 text-[10px]">#{data.ticket}</span>
        </div>

        <div className="space-y-1 text-slate-300">
          <div className="flex justify-between">
            <span className="text-slate-400">Trade Result:</span>
            <span className={`font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isWin ? `+$${data.tradePnl.toFixed(2)}` : `-$${Math.abs(data.tradePnl).toFixed(2)}`} ({data.tradeR >= 0 ? `+${data.tradeR.toFixed(2)}R` : `${data.tradeR.toFixed(2)}R`})
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-slate-400">Account Equity:</span>
            <span className="font-bold text-slate-100">${data.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>

          <div className="flex justify-between">
            <span className="text-slate-400">Cumulative Return:</span>
            <span className={`font-bold ${data.cumulativePnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {data.cumulativePnl >= 0 ? `+$${data.cumulativePnl.toFixed(2)}` : `-$${Math.abs(data.cumulativePnl).toFixed(2)}`}
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-slate-400">Cumulative R:</span>
            <span className="font-bold text-cyan-300">
              {data.cumulativeR >= 0 ? `+${data.cumulativeR.toFixed(2)} R` : `${data.cumulativeR.toFixed(2)} R`}
            </span>
          </div>

          {data.drawdownPercent > 0 && (
            <div className="flex justify-between text-amber-400/90 text-[11px] pt-1 border-t border-slate-800/80">
              <span>Peak Drawdown:</span>
              <span>-{data.drawdownPercent.toFixed(1)}% (-${data.drawdownDollars.toFixed(0)})</span>
            </div>
          )}
        </div>

        <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
          Closed: {data.timeStr}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-slate-950/80 rounded-xl border border-slate-800 p-4 space-y-4 shadow-md">
      {/* Header & Mode Toggles */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-indigo-500/10 border border-indigo-500/30 rounded-lg text-indigo-400">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-bold text-slate-100 flex items-center gap-1.5">
                <span>Account Equity & Performance Curve</span>
              </h4>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700 font-semibold">
                Recharts Engine
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Real-time balance trajectory & R-multiple compounding across closed trades
            </p>
          </div>
        </div>

        {/* Metric & Filter Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Symbol Filter */}
          {uniqueSymbols.length > 2 && (
            <div className="flex items-center bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800 text-xs font-mono">
              <span className="text-slate-500 text-[10px] mr-1.5">Pair:</span>
              <select
                id="equity-chart-symbol-filter"
                value={selectedSymbol}
                onChange={e => setSelectedSymbol(e.target.value)}
                className="bg-transparent text-cyan-300 font-semibold focus:outline-none cursor-pointer text-xs"
              >
                {uniqueSymbols.map(sym => (
                  <option key={sym} value={sym} className="bg-slate-900 text-slate-200">
                    {sym}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Mode Switcher ($ vs R) */}
          <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-xs font-mono">
            <button
              id="equity-mode-usd"
              onClick={() => setMetricMode('equity')}
              className={`px-2.5 py-1 rounded transition text-[11px] font-semibold ${
                metricMode === 'equity'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Account Balance ($)
            </button>
            <button
              id="equity-mode-r"
              onClick={() => setMetricMode('rMultiple')}
              className={`px-2.5 py-1 rounded transition text-[11px] font-semibold ${
                metricMode === 'rMultiple'
                  ? 'bg-indigo-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Cumulative Return (R)
            </button>
          </div>
        </div>
      </div>

      {/* Metric Stat Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono">
        <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
          <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Current Equity</span>
          <div className="text-base font-bold text-slate-100 mt-0.5">
            ${summaryStats.currentEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <span className={`text-[10px] font-semibold ${summaryStats.totalReturnDollars >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {summaryStats.totalReturnDollars >= 0 ? `+${summaryStats.totalReturnPercent.toFixed(2)}%` : `${summaryStats.totalReturnPercent.toFixed(2)}%`} (${summaryStats.totalReturnDollars >= 0 ? `+$${summaryStats.totalReturnDollars.toFixed(0)}` : `-$${Math.abs(summaryStats.totalReturnDollars).toFixed(0)}`})
          </span>
        </div>

        <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
          <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Total Compound R</span>
          <div className="text-base font-bold text-cyan-300 mt-0.5">
            {summaryStats.finalR >= 0 ? `+${summaryStats.finalR.toFixed(2)} R` : `${summaryStats.finalR.toFixed(2)} R`}
          </div>
          <span className="text-[10px] text-slate-500">
            Across {summaryStats.tradesCount} trades
          </span>
        </div>

        <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
          <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Peak Watermark</span>
          <div className="text-base font-bold text-emerald-400 mt-0.5">
            ${summaryStats.peakEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <span className="text-[10px] text-slate-500">
            High Water Mark
          </span>
        </div>

        <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
          <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Max Drawdown</span>
          <div className="text-base font-bold text-amber-400 mt-0.5">
            {summaryStats.maxDrawdownPct > 0 ? `-${summaryStats.maxDrawdownPct.toFixed(1)}%` : '0.0%'}
          </div>
          <span className="text-[10px] text-slate-500">
            {summaryStats.maxDrawdownDollars > 0 ? `-$${summaryStats.maxDrawdownDollars.toFixed(0)} drop` : 'Optimal'}
          </span>
        </div>
      </div>

      {/* Main Recharts Line / Area Visualizer */}
      <div className="h-64 w-full pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={equityData}
            margin={{ top: 10, right: 15, left: 10, bottom: 5 }}
          >
            <defs>
              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="rGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
              </linearGradient>
            </defs>

            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#1e293b"
              vertical={false}
            />

            <XAxis
              dataKey="timeStr"
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: '#334155' }}
              tickFormatter={(val) => {
                // Shorten string on x-axis
                return typeof val === 'string' ? val.split(' ')[0] : val;
              }}
            />

            <YAxis
              domain={[minVal, maxVal]}
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: '#334155' }}
              tickFormatter={(val) => {
                if (metricMode === 'equity') {
                  return `$${val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val}`;
                } else {
                  return `${val >= 0 ? `+${val}` : val}R`;
                }
              }}
            />

            <Tooltip content={<CustomTooltip />} />

            {/* Baseline Reference Line */}
            <ReferenceLine
              y={metricMode === 'equity' ? startingBalance : 0}
              stroke="#475569"
              strokeDasharray="4 4"
              label={{
                value: metricMode === 'equity' ? `Initial $${startingBalance}` : '0.00 R Baseline',
                fill: '#64748b',
                fontSize: 10,
                position: 'insideBottomLeft'
              }}
            />

            {/* Area Fill */}
            <Area
              type="monotone"
              dataKey={metricMode === 'equity' ? 'equity' : 'cumulativeR'}
              fill={metricMode === 'equity' ? 'url(#equityGradient)' : 'url(#rGradient)'}
              stroke="none"
            />

            {/* Primary High-Precision Line */}
            <Line
              type="monotone"
              dataKey={metricMode === 'equity' ? 'equity' : 'cumulativeR'}
              stroke={metricMode === 'equity' ? '#10b981' : '#818cf8'}
              strokeWidth={2.5}
              dot={{
                r: 4,
                fill: metricMode === 'equity' ? '#10b981' : '#818cf8',
                stroke: '#0f172a',
                strokeWidth: 2
              }}
              activeDot={{
                r: 6,
                fill: '#38bdf8',
                stroke: '#ffffff',
                strokeWidth: 2
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Chart Footer / Trade Milestone Annotation */}
      <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-500 pt-2 border-t border-slate-800/60">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="text-slate-400">Profitable Trade Event</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
            <span className="text-slate-400">Cumulative R Trajectory</span>
          </div>
        </div>
        <div>
          Hover over data points to inspect execution tickets and drawdown
        </div>
      </div>
    </div>
  );
};
