import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  LineChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ReferenceLine,
  CartesianGrid
} from 'recharts';
import { Position } from '../../types/trading';
import { EquityCurveChart } from './EquityCurveChart';
import { ClosedTradesSparkline } from './ClosedTradesSparkline';
import { ClosedTradeDetailModal } from './ClosedTradeDetailModal';
import { StrategyProfitDistributionChart } from './StrategyProfitDistributionChart';
import { TradeOutcomeFilter, matchesClosedTradeFilter } from './ClosedTradesFilterBar';
import {
  TrendingUp,
  TrendingDown,
  Award,
  BarChart2,
  PieChart,
  Percent,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  Filter,
  DollarSign,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  LineChart as LineChartIcon,
  Activity,
  Maximize2
} from 'lucide-react';

interface CumulativePnlPoint {
  index: number;
  ticket: number | string;
  timeStr: string;
  shortTime: string;
  timestamp: number;
  symbol: string;
  side: string;
  tradePnl: number;
  tradeR: number;
  cumulativePnl: number;
  cumulativeR: number;
  equity: number;
  peakCumulativePnl: number;
  peakEquity: number;
  drawdownDollars: number;
  drawdownPercent: number;
}

export interface ClosedTradesSummaryCardProps {
  positions: Position[];
  externalSearchQuery?: string;
  onSearchQueryChange?: (query: string) => void;
  externalSymbolFilter?: string;
  onSymbolFilterChange?: (symbol: string) => void;
  externalOutcomeFilter?: TradeOutcomeFilter;
  onOutcomeFilterChange?: (outcome: TradeOutcomeFilter) => void;
  externalTimeframeFilter?: string;
  onTimeframeFilterChange?: (timeframe: string) => void;
  onResetFilters?: () => void;
}

export const ClosedTradesSummaryCard: React.FC<ClosedTradesSummaryCardProps> = ({
  positions,
  externalSearchQuery,
  onSearchQueryChange,
  externalSymbolFilter,
  onSymbolFilterChange,
  externalOutcomeFilter,
  onOutcomeFilterChange,
  externalTimeframeFilter,
  onTimeframeFilterChange,
  onResetFilters
}) => {
  const [internalFilter, setInternalFilter] = useState<string>('ALL');
  const [internalSearchQuery, setInternalSearchQuery] = useState<string>('');
  const [internalOutcomeFilter, setInternalOutcomeFilter] = useState<TradeOutcomeFilter>('ALL');
  const [internalTimeframeFilter, setInternalTimeframeFilter] = useState<string>('ALL');
  const [sideFilter, setSideFilter] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [chartMetricMode, setChartMetricMode] = useState<'pnl' | 'r' | 'equity'>('pnl');
  const [activeTab, setActiveTab] = useState<'both' | 'curve' | 'sparkline' | 'stats' | 'strategies'>('both');
  const [showTradesList, setShowTradesList] = useState<boolean>(false);
  const [selectedTradeForModal, setSelectedTradeForModal] = useState<Position | null>(null);

  // Synchronized filter states (external prop prioritized if provided)
  const searchQuery = externalSearchQuery !== undefined ? externalSearchQuery : internalSearchQuery;
  const selectedFilter = externalSymbolFilter !== undefined ? externalSymbolFilter : internalFilter;
  const outcomeFilter = externalOutcomeFilter !== undefined ? externalOutcomeFilter : internalOutcomeFilter;
  const timeframeFilter = externalTimeframeFilter !== undefined ? externalTimeframeFilter : internalTimeframeFilter;

  const handleSearchChange = (val: string) => {
    setInternalSearchQuery(val);
    if (onSearchQueryChange) onSearchQueryChange(val);
  };

  const handleSymbolChange = (sym: string) => {
    setInternalFilter(sym);
    if (onSymbolFilterChange) onSymbolFilterChange(sym);
  };

  const handleOutcomeChange = (out: TradeOutcomeFilter) => {
    setInternalOutcomeFilter(out);
    if (onOutcomeFilterChange) onOutcomeFilterChange(out);
  };

  const handleTimeframeChange = (tf: string) => {
    setInternalTimeframeFilter(tf);
    if (onTimeframeFilterChange) onTimeframeFilterChange(tf);
  };

  // Filter closed positions
  const closedPositions = useMemo(() => {
    return positions.filter(p => p.status === 'CLOSED');
  }, [positions]);

  // Counts for each side across symbol/outcome/query/timeframe-filtered closed positions
  const sideCounts = useMemo(() => {
    const matchingTrades = closedPositions.filter(p =>
      matchesClosedTradeFilter(p, selectedFilter, outcomeFilter, searchQuery, 'ALL', timeframeFilter)
    );

    const longCount = matchingTrades.filter(p => p.side === 'BUY').length;
    const shortCount = matchingTrades.filter(p => p.side === 'SELL').length;
    return {
      all: matchingTrades.length,
      long: longCount,
      short: shortCount
    };
  }, [closedPositions, selectedFilter, outcomeFilter, searchQuery, timeframeFilter]);

  const filteredClosedTrades = useMemo(() => {
    return closedPositions.filter(p =>
      matchesClosedTradeFilter(p, selectedFilter, outcomeFilter, searchQuery, sideFilter, timeframeFilter)
    );
  }, [closedPositions, selectedFilter, outcomeFilter, searchQuery, sideFilter, timeframeFilter]);

  // Compute statistical metrics
  const stats = useMemo(() => {
    const totalTrades = filteredClosedTrades.length;
    if (totalTrades === 0) {
      return {
        totalTrades: 0,
        wins: 0,
        losses: 0,
        breakevens: 0,
        winRate: 0,
        profitFactor: 0,
        avgR: 0,
        totalR: 0,
        grossProfit: 0,
        grossLoss: 0,
        netPnl: 0,
        avgWinR: 0,
        avgLossR: 0,
        maxWinR: 0,
        maxLossR: 0,
        payoffRatio: 0
      };
    }

    let wins = 0;
    let losses = 0;
    let breakevens = 0;
    let grossProfit = 0;
    let grossLoss = 0;
    let totalR = 0;
    let winRTotal = 0;
    let lossRTotal = 0;
    let maxWinR = 0;
    let maxLossR = 0;

    filteredClosedTrades.forEach(trade => {
      totalR += trade.pnlR;

      if (trade.pnl > 0.001) {
        wins += 1;
        grossProfit += trade.pnl;
        winRTotal += trade.pnlR;
        if (trade.pnlR > maxWinR) maxWinR = trade.pnlR;
      } else if (trade.pnl < -0.001) {
        losses += 1;
        grossLoss += Math.abs(trade.pnl);
        lossRTotal += Math.abs(trade.pnlR);
        if (trade.pnlR < maxLossR) maxLossR = trade.pnlR;
      } else {
        breakevens += 1;
      }
    });

    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99.9 : 0;
    const avgR = totalTrades > 0 ? totalR / totalTrades : 0;
    const netPnl = grossProfit - grossLoss;
    const avgWinR = wins > 0 ? winRTotal / wins : 0;
    const avgLossR = losses > 0 ? lossRTotal / losses : 0;
    const payoffRatio = avgLossR > 0 ? avgWinR / avgLossR : avgWinR > 0 ? avgWinR : 0;

    return {
      totalTrades,
      wins,
      losses,
      breakevens,
      winRate,
      profitFactor,
      avgR,
      totalR,
      grossProfit,
      grossLoss,
      netPnl,
      avgWinR,
      avgLossR,
      maxWinR,
      maxLossR,
      payoffRatio
    };
  }, [filteredClosedTrades]);

  // Unique symbols present in closed trades
  const uniqueSymbols = useMemo(() => {
    const syms = Array.from(new Set(closedPositions.map(p => p.symbol)));
    return ['ALL', ...syms];
  }, [closedPositions]);

  // Build chronological Cumulative Profit/Loss equity curve points for Recharts LineChart
  const cumulativeCurveData = useMemo(() => {
    if (filteredClosedTrades.length === 0) return [];

    // Chronological sort by closeTime (or openTime)
    const sortedTrades = [...filteredClosedTrades].sort(
      (a, b) => (a.closeTime || a.openTime) - (b.closeTime || b.openTime)
    );

    const baseTime = sortedTrades[0].openTime
      ? sortedTrades[0].openTime - 3600
      : Math.floor(Date.now() / 1000) - 86400 * 7;
    const baseDate = new Date(baseTime * 1000);
    const baseShortTime = `${baseDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
    const baseTimeStr = `${baseShortTime} Base`;

    const startingBalance = 10000;
    const points: CumulativePnlPoint[] = [
      {
        index: 0,
        ticket: 'START',
        timeStr: baseTimeStr,
        shortTime: 'Base',
        timestamp: baseTime,
        symbol: 'BASE',
        side: 'FLAT',
        tradePnl: 0,
        tradeR: 0,
        cumulativePnl: 0,
        cumulativeR: 0,
        equity: startingBalance,
        peakCumulativePnl: 0,
        peakEquity: startingBalance,
        drawdownDollars: 0,
        drawdownPercent: 0
      }
    ];

    let runningPnl = 0;
    let runningR = 0;
    let runningEquity = startingBalance;
    let peakPnl = 0;
    let peakEquity = startingBalance;

    sortedTrades.forEach((trade, i) => {
      runningPnl += trade.pnl;
      runningR += trade.pnlR;
      runningEquity = startingBalance + runningPnl;

      if (runningPnl > peakPnl) peakPnl = runningPnl;
      if (runningEquity > peakEquity) peakEquity = runningEquity;

      const ddDollars = Math.max(0, peakPnl - runningPnl);
      const ddPct = peakEquity > 0 ? ((peakEquity - runningEquity) / peakEquity) * 100 : 0;

      const tradeTime = trade.closeTime || trade.openTime;
      const d = new Date(tradeTime * 1000);
      const shortTime = `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
      const timeStr = `${shortTime} ${d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })}`;

      points.push({
        index: i + 1,
        ticket: trade.ticket,
        timeStr,
        shortTime: `${shortTime} #${trade.ticket}`,
        timestamp: tradeTime,
        symbol: trade.symbol,
        side: trade.side,
        tradePnl: Number(trade.pnl.toFixed(2)),
        tradeR: Number(trade.pnlR.toFixed(2)),
        cumulativePnl: Number(runningPnl.toFixed(2)),
        cumulativeR: Number(runningR.toFixed(2)),
        equity: Number(runningEquity.toFixed(2)),
        peakCumulativePnl: Number(peakPnl.toFixed(2)),
        peakEquity: Number(peakEquity.toFixed(2)),
        drawdownDollars: Number(ddDollars.toFixed(2)),
        drawdownPercent: Number(ddPct.toFixed(2))
      });
    });

    return points;
  }, [filteredClosedTrades]);

  // Curve summary statistics
  const curveSummary = useMemo(() => {
    if (cumulativeCurveData.length <= 1) {
      return {
        currentPnl: 0,
        currentR: 0,
        currentEquity: 10000,
        peakPnl: 0,
        maxDrawdownDollars: 0,
        maxDrawdownPct: 0
      };
    }
    const lastPoint = cumulativeCurveData[cumulativeCurveData.length - 1];
    const maxDdDollars = Math.max(...cumulativeCurveData.map(p => p.drawdownDollars), 0);
    const maxDdPct = Math.max(...cumulativeCurveData.map(p => p.drawdownPercent), 0);
    const peakPnl = Math.max(...cumulativeCurveData.map(p => p.peakCumulativePnl), 0);

    return {
      currentPnl: lastPoint.cumulativePnl,
      currentR: lastPoint.cumulativeR,
      currentEquity: lastPoint.equity,
      peakPnl,
      maxDrawdownDollars: maxDdDollars,
      maxDrawdownPct: maxDdPct
    };
  }, [cumulativeCurveData]);

  // Dynamic domain bounds for Recharts YAxis
  const { minDomain, maxDomain } = useMemo(() => {
    if (chartMetricMode === 'pnl') {
      const vals = cumulativeCurveData.map(d => d.cumulativePnl);
      const min = Math.min(...vals, 0);
      const max = Math.max(...vals, 0);
      const padding = Math.max((max - min) * 0.18, 50);
      return {
        minDomain: Math.floor(min - padding),
        maxDomain: Math.ceil(max + padding)
      };
    } else if (chartMetricMode === 'r') {
      const vals = cumulativeCurveData.map(d => d.cumulativeR);
      const min = Math.min(...vals, 0);
      const max = Math.max(...vals, 0);
      const padding = Math.max((max - min) * 0.2, 0.5);
      return {
        minDomain: Number((min - padding).toFixed(1)),
        maxDomain: Number((max + padding).toFixed(1))
      };
    } else {
      const vals = cumulativeCurveData.map(d => d.equity);
      const min = Math.min(...vals, 10000);
      const max = Math.max(...vals, 10000);
      const padding = Math.max((max - min) * 0.15, 100);
      return {
        minDomain: Math.floor(min - padding),
        maxDomain: Math.ceil(max + padding)
      };
    }
  }, [cumulativeCurveData, chartMetricMode]);

  // Custom Recharts Tooltip for the cumulative Profit/Loss curve
  const CustomEquityTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;
    const data = payload[0].payload;

    if (data.ticket === 'START') {
      return (
        <div className="bg-slate-950 border border-slate-700 p-3 rounded-lg shadow-xl font-mono text-xs text-slate-200">
          <div className="text-slate-400 font-bold mb-1">Baseline Starting Capital</div>
          <div>Cumulative P&L: <strong className="text-emerald-400">$0.00 (0.00 R)</strong></div>
          <div>Account Balance: <strong className="text-slate-200">$10,000.00</strong></div>
          <div className="text-[10px] text-slate-500 mt-1">{data.timeStr}</div>
        </div>
      );
    }

    const isWin = data.tradePnl > 0;

    return (
      <div className="bg-slate-950/95 border border-slate-700 p-3.5 rounded-xl shadow-2xl font-mono text-xs space-y-2 min-w-[230px] backdrop-blur-md">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
          <div className="flex items-center gap-1.5 font-bold">
            <span className="text-cyan-300">{data.symbol}</span>
            <span className={`text-[10px] px-1.5 py-0.2 rounded font-semibold ${data.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
              {data.side === 'BUY' ? 'LONG' : 'SHORT'}
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
            <span className="text-slate-400">Cumulative P&L:</span>
            <span className={`font-bold ${data.cumulativePnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {data.cumulativePnl >= 0 ? `+$${data.cumulativePnl.toFixed(2)}` : `-$${Math.abs(data.cumulativePnl).toFixed(2)}`}
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-slate-400">Cumulative Return:</span>
            <span className="font-bold text-cyan-300">
              {data.cumulativeR >= 0 ? `+${data.cumulativeR.toFixed(2)} R` : `${data.cumulativeR.toFixed(2)} R`}
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-slate-400">Account Balance:</span>
            <span className="font-bold text-slate-100">
              ${data.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {data.drawdownDollars > 0 && (
            <div className="flex justify-between text-amber-400/90 text-[11px] pt-1 border-t border-slate-800/80">
              <span>Drawdown from Peak:</span>
              <span>-${data.drawdownDollars.toFixed(2)} (-{data.drawdownPercent.toFixed(1)}%)</span>
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
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
      {/* Header & Filter Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400">
            <Award className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span>Closed Trades Statistical Summary</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-semibold">
                {stats.totalTrades} Settled
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Verified performance metrics across closed session trade executions
            </p>
          </div>
        </div>

        {/* View Switcher & Filter Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Tab Switcher */}
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            <button
              id="closed-view-both"
              onClick={() => setActiveTab('both')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                activeTab === 'both'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Full Overview</span>
            </button>
            <button
              id="closed-view-curve"
              onClick={() => setActiveTab('curve')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                activeTab === 'curve'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <LineChartIcon className="w-3.5 h-3.5" />
              <span>Equity Curve</span>
            </button>
            <button
              id="closed-view-sparkline"
              onClick={() => setActiveTab('sparkline')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                activeTab === 'sparkline'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>10-Trade Sparkline</span>
            </button>
            <button
              id="closed-view-strategies"
              onClick={() => setActiveTab('strategies')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                activeTab === 'strategies'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Strategy Distribution</span>
            </button>
            <button
              id="closed-view-stats"
              onClick={() => setActiveTab('stats')}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 text-[11px] font-semibold ${
                activeTab === 'stats'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" />
              <span>Stats Matrix</span>
            </button>
          </div>

          {/* Direction / Side Filter Toggle */}
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            <button
              id="closed-filter-side-all"
              type="button"
              onClick={() => setSideFilter('ALL')}
              className={`px-2 py-1 rounded transition flex items-center gap-1 text-[11px] font-semibold ${
                sideFilter === 'ALL'
                  ? 'bg-slate-800 text-slate-100 border border-slate-700 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>All Sides</span>
              <span className="text-[10px] text-slate-400 font-mono">({sideCounts.all})</span>
            </button>
            <button
              id="closed-filter-side-long"
              type="button"
              onClick={() => setSideFilter('LONG')}
              className={`px-2 py-1 rounded transition flex items-center gap-1 text-[11px] font-semibold ${
                sideFilter === 'LONG'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ArrowUpRight className="w-3 h-3 text-emerald-400" />
              <span>Long</span>
              <span className={`text-[10px] font-mono ${sideFilter === 'LONG' ? 'text-emerald-300' : 'text-slate-500'}`}>
                ({sideCounts.long})
              </span>
            </button>
            <button
              id="closed-filter-side-short"
              type="button"
              onClick={() => setSideFilter('SHORT')}
              className={`px-2 py-1 rounded transition flex items-center gap-1 text-[11px] font-semibold ${
                sideFilter === 'SHORT'
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ArrowDownRight className="w-3 h-3 text-rose-400" />
              <span>Short</span>
              <span className={`text-[10px] font-mono ${sideFilter === 'SHORT' ? 'text-rose-300' : 'text-slate-500'}`}>
                ({sideCounts.short})
              </span>
            </button>
          </div>

          {/* Symbol Filter Selector */}
          {uniqueSymbols.length > 2 && (
            <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 text-xs font-mono">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-slate-400 text-[11px]">Symbol:</span>
              <select
                id="closed-trades-symbol-filter"
                value={selectedFilter}
                onChange={e => handleSymbolChange(e.target.value)}
                className="bg-transparent text-cyan-300 font-semibold focus:outline-none cursor-pointer"
              >
                {uniqueSymbols.map(sym => (
                  <option key={sym} value={sym} className="bg-slate-900 text-slate-200">
                    {sym}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Empty State when 0 trades match the filters */}
      {filteredClosedTrades.length === 0 ? (
        <div className="p-8 text-center bg-slate-950/60 rounded-xl border border-slate-800 font-mono space-y-2">
          <div className="text-slate-400 text-sm font-semibold">No closed trades found matching criteria</div>
          <div className="text-xs text-slate-500">
            Asset: <span className="text-cyan-300 font-semibold">{selectedFilter}</span>
            {outcomeFilter !== 'ALL' && (
              <> • Outcome: <span className="text-emerald-400 font-semibold">{outcomeFilter}</span></>
            )}
            {searchQuery && (
              <> • Query: <span className="text-amber-300 font-semibold">"{searchQuery}"</span></>
            )}
            • Direction: <span className="text-slate-300 font-bold">{sideFilter}</span>
          </div>
          <button
            id="reset-closed-trades-empty-filters"
            type="button"
            onClick={() => {
              handleSymbolChange('ALL');
              handleOutcomeChange('ALL');
              handleSearchChange('');
              setSideFilter('ALL');
              if (onResetFilters) onResetFilters();
            }}
            className="mt-2 text-xs text-emerald-400 hover:text-emerald-300 underline font-semibold cursor-pointer"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <>
          {/* 1. Cumulative Profit/Loss Equity Curve Visualizer (Recharts Line Chart) */}
          {(activeTab === 'both' || activeTab === 'curve') && (
            <div
              id="closed-trades-recharts-equity-curve"
              className="bg-slate-950/85 rounded-xl border border-slate-800 p-4 space-y-4 shadow-md font-mono"
            >
              {/* Header & Mode Switcher */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400">
                    <TrendingUp className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-bold text-slate-100 flex items-center gap-1.5">
                        <span>Cumulative Profit/Loss Equity Curve</span>
                      </h4>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-emerald-300 border border-emerald-500/30 font-semibold">
                        Recharts LineChart
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">
                      Chronological cumulative P/L trajectory across {filteredClosedTrades.length} settled trades
                    </p>
                  </div>
                </div>

                {/* Metric Mode Switcher */}
                <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-xs">
                  <button
                    id="chart-mode-pnl"
                    type="button"
                    onClick={() => setChartMetricMode('pnl')}
                    className={`px-2.5 py-1 rounded transition text-[11px] font-semibold cursor-pointer ${
                      chartMetricMode === 'pnl'
                        ? 'bg-emerald-500 text-slate-950 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Cumulative P&L ($)
                  </button>
                  <button
                    id="chart-mode-r"
                    type="button"
                    onClick={() => setChartMetricMode('r')}
                    className={`px-2.5 py-1 rounded transition text-[11px] font-semibold cursor-pointer ${
                      chartMetricMode === 'r'
                        ? 'bg-indigo-500 text-slate-950 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Cumulative Return (R)
                  </button>
                  <button
                    id="chart-mode-equity"
                    type="button"
                    onClick={() => setChartMetricMode('equity')}
                    className={`px-2.5 py-1 rounded transition text-[11px] font-semibold cursor-pointer ${
                      chartMetricMode === 'equity'
                        ? 'bg-cyan-500 text-slate-950 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Account Balance ($)
                  </button>
                </div>
              </div>

              {/* Curve Stat Metrics Strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Net Cumulative P&L</span>
                  <div className={`text-base font-bold mt-0.5 ${curveSummary.currentPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {curveSummary.currentPnl >= 0 ? `+$${curveSummary.currentPnl.toFixed(2)}` : `-$${Math.abs(curveSummary.currentPnl).toFixed(2)}`}
                  </div>
                  <span className="text-[10px] text-slate-400">
                    Equity: ${curveSummary.currentEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>

                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Total Compound R</span>
                  <div className={`text-base font-bold mt-0.5 ${curveSummary.currentR >= 0 ? 'text-cyan-300' : 'text-rose-400'}`}>
                    {curveSummary.currentR >= 0 ? `+${curveSummary.currentR.toFixed(2)} R` : `${curveSummary.currentR.toFixed(2)} R`}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Across {filteredClosedTrades.length} trades
                  </span>
                </div>

                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Peak P&L Watermark</span>
                  <div className="text-base font-bold text-emerald-400 mt-0.5">
                    +${curveSummary.peakPnl.toFixed(2)}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    High Water Mark
                  </span>
                </div>

                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 text-[10px] uppercase tracking-wider block">Max Peak Drawdown</span>
                  <div className={`text-base font-bold mt-0.5 ${curveSummary.maxDrawdownDollars > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {curveSummary.maxDrawdownDollars > 0 ? `-$${curveSummary.maxDrawdownDollars.toFixed(0)} (-${curveSummary.maxDrawdownPct.toFixed(1)}%)` : '0.00%'}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Max pullback from peak
                  </span>
                </div>
              </div>

              {/* Recharts Line / Area Chart Container */}
              <div className="h-64 w-full pt-1">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={cumulativeCurveData}
                    margin={{ top: 12, right: 16, left: 10, bottom: 5 }}
                  >
                    <defs>
                      <linearGradient id="pnlGreenGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.28} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="pnlRedGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.28} />
                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="rMultipleGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.28} />
                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>

                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />

                    <XAxis
                      dataKey="shortTime"
                      stroke="#64748b"
                      fontSize={10}
                      tickLine={false}
                      axisLine={{ stroke: '#334155' }}
                      tickFormatter={(val) => {
                        return typeof val === 'string' ? val.split(' ')[0] : val;
                      }}
                    />

                    <YAxis
                      domain={[minDomain, maxDomain]}
                      stroke="#64748b"
                      fontSize={10}
                      tickLine={false}
                      axisLine={{ stroke: '#334155' }}
                      tickFormatter={(val) => {
                        if (chartMetricMode === 'pnl') {
                          return `${val >= 0 ? `+$${val}` : `-$${Math.abs(val)}`}`;
                        } else if (chartMetricMode === 'r') {
                          return `${val >= 0 ? `+${val}` : val}R`;
                        } else {
                          return `$${val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val}`;
                        }
                      }}
                    />

                    <RechartsTooltip content={<CustomEquityTooltip />} />

                    {/* Baseline Reference Line */}
                    <ReferenceLine
                      y={chartMetricMode === 'equity' ? 10000 : 0}
                      stroke="#64748b"
                      strokeDasharray="4 4"
                      label={{
                        value: chartMetricMode === 'equity' ? 'Base $10,000' : 'Breakeven ($0.00)',
                        fill: '#94a3b8',
                        fontSize: 10,
                        position: 'insideBottomLeft'
                      }}
                    />

                    {/* Gradient Area Fill */}
                    <Area
                      type="monotone"
                      dataKey={
                        chartMetricMode === 'pnl'
                          ? 'cumulativePnl'
                          : chartMetricMode === 'r'
                          ? 'cumulativeR'
                          : 'equity'
                      }
                      fill={
                        chartMetricMode === 'pnl'
                          ? curveSummary.currentPnl >= 0
                            ? 'url(#pnlGreenGradient)'
                            : 'url(#pnlRedGradient)'
                          : chartMetricMode === 'r'
                          ? 'url(#rMultipleGradient)'
                          : 'url(#equityGradient)'
                      }
                      stroke="none"
                      isAnimationActive={false}
                    />

                    {/* Main Recharts Line */}
                    <Line
                      type="monotone"
                      dataKey={
                        chartMetricMode === 'pnl'
                          ? 'cumulativePnl'
                          : chartMetricMode === 'r'
                          ? 'cumulativeR'
                          : 'equity'
                      }
                      stroke={
                        chartMetricMode === 'pnl'
                          ? curveSummary.currentPnl >= 0
                            ? '#10b981'
                            : '#f43f5e'
                          : chartMetricMode === 'r'
                          ? '#818cf8'
                          : '#06b6d4'
                      }
                      strokeWidth={2.5}
                      dot={{
                        r: 3.5,
                        fill:
                          chartMetricMode === 'pnl'
                            ? curveSummary.currentPnl >= 0
                              ? '#10b981'
                              : '#f43f5e'
                            : chartMetricMode === 'r'
                            ? '#818cf8'
                            : '#06b6d4',
                        stroke: '#0f172a',
                        strokeWidth: 1.5
                      }}
                      activeDot={{
                        r: 6,
                        fill: '#38bdf8',
                        stroke: '#ffffff',
                        strokeWidth: 2
                      }}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* Chart Legend Footer */}
              <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-800/60">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                    <span className="text-slate-400">Winning Execution (+P/L)</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                    <span className="text-slate-400">Losing Execution (-P/L)</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-0.5 bg-slate-500 inline-block" />
                    <span className="text-slate-400">Breakeven Zero Line</span>
                  </div>
                </div>
                <div className="text-slate-500">
                  Hover data points to inspect execution tickets and drawdowns
                </div>
              </div>
            </div>
          )}

      {/* 2. Sparkline Chart: 10-Trade Volatility & Drawdown Trend */}
      {(activeTab === 'both' || activeTab === 'sparkline' || activeTab === 'curve' || activeTab === 'stats') && (
        <ClosedTradesSparkline positions={filteredClosedTrades} startingBalance={10000} />
      )}

      {/* 3. Primary Metrics Grid (Win Rate, Profit Factor, Avg R-Multiple) */}
      {(activeTab === 'both' || activeTab === 'stats' || activeTab === 'sparkline' || activeTab === 'strategies') && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Metric 1: Win Rate */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Percent className="w-3.5 h-3.5 text-cyan-400" />
              <span>Win Rate</span>
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              {stats.wins}W / {stats.losses}L
            </span>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-100">
              {stats.totalTrades > 0 ? `${stats.winRate.toFixed(1)}%` : '0.0%'}
            </span>
            <span className="text-xs font-mono text-slate-500">
              ({stats.totalTrades} trades)
            </span>
          </div>

          {/* Win Rate Progress Bar */}
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden flex">
            <div
              className="bg-emerald-500 h-full transition-all duration-500"
              style={{ width: `${stats.winRate}%` }}
            />
            <div
              className="bg-rose-500 h-full transition-all duration-500"
              style={{ width: `${100 - stats.winRate}%` }}
            />
          </div>
        </div>

        {/* Metric 2: Profit Factor */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <BarChart2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Profit Factor</span>
            </span>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                stats.profitFactor >= 2.0
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                  : stats.profitFactor >= 1.0
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
              }`}
            >
              {stats.profitFactor >= 2.0 ? 'OPTIMAL' : stats.profitFactor >= 1.0 ? 'PROFITABLE' : 'SUBPAR'}
            </span>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-emerald-400">
              {stats.totalTrades > 0
                ? stats.profitFactor >= 99.9
                  ? '∞'
                  : stats.profitFactor.toFixed(2)
                : '0.00'}
            </span>
            <span className="text-xs font-mono text-slate-500">Gross P/L Ratio</span>
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span className="text-emerald-400">+${stats.grossProfit.toFixed(0)}</span>
            <span className="text-slate-600">/</span>
            <span className="text-rose-400">-${stats.grossLoss.toFixed(0)}</span>
          </div>
        </div>

        {/* Metric 3: Average R-Multiple */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
              <span>Avg R-Multiple</span>
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              NET {stats.totalR >= 0 ? `+${stats.totalR.toFixed(2)}` : stats.totalR.toFixed(2)} R
            </span>
          </div>

          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-bold font-mono ${
                stats.avgR >= 0 ? 'text-cyan-400' : 'text-rose-400'
              }`}
            >
              {stats.avgR >= 0 ? `+${stats.avgR.toFixed(2)} R` : `${stats.avgR.toFixed(2)} R`}
            </span>
            <span className="text-xs font-mono text-slate-500">per trade</span>
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>Avg Win: <strong className="text-emerald-400">+{stats.avgWinR.toFixed(2)}R</strong></span>
            <span>Avg Loss: <strong className="text-rose-400">-{stats.avgLossR.toFixed(2)}R</strong></span>
          </div>
        </div>
      </div>

      {/* Secondary Statistical Badges / Payoff Detail */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 text-xs font-mono">
        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/60 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">Net PnL:</span>
          <span className={`font-bold ${stats.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {stats.netPnl >= 0 ? `+$${stats.netPnl.toFixed(2)}` : `-$${Math.abs(stats.netPnl).toFixed(2)}`}
          </span>
        </div>

        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/60 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">Payoff Ratio:</span>
          <span className="font-bold text-slate-200">
            {stats.payoffRatio.toFixed(2)}:1
          </span>
        </div>

        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/60 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">Best Win:</span>
          <span className="font-bold text-emerald-400">
            +{stats.maxWinR.toFixed(2)} R
          </span>
        </div>

        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/60 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">Max Loss:</span>
          <span className="font-bold text-rose-400">
            {stats.maxLossR !== 0 ? `${stats.maxLossR.toFixed(2)} R` : '0.00 R'}
          </span>
        </div>
      </div>

      {/* 4. Strategy Profit Distribution: Horizontal Bar Chart Breakdown */}
      <StrategyProfitDistributionChart
        closedTrades={filteredClosedTrades}
        currentTimeframeFilter={timeframeFilter}
        onTimeframeChange={handleTimeframeChange}
        className="my-3"
      />

      {/* Expandable Trade Ledger Accordion */}
      {filteredClosedTrades.length > 0 && (
        <div className="pt-2 border-t border-slate-800/80">
          <button
            id="toggle-closed-trades-list"
            onClick={() => setShowTradesList(!showTradesList)}
            className="w-full flex items-center justify-between text-xs font-mono text-slate-400 hover:text-slate-200 transition py-1"
          >
            <span className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              <span>Inspect Closed Trades Breakdown ({filteredClosedTrades.length})</span>
            </span>
            {showTradesList ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {showTradesList && (
            <div className="mt-3 space-y-2 max-h-60 overflow-y-auto pr-1">
              {filteredClosedTrades.map(trade => {
                const isWin = trade.pnl > 0;
                return (
                  <div
                    key={trade.ticket}
                    className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 flex items-center justify-between font-mono text-xs hover:border-slate-700 transition"
                  >
                    <div className="flex items-center gap-2.5">
                      {isWin ? (
                        <div className="p-1 rounded bg-emerald-500/20 text-emerald-400">
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </div>
                      ) : (
                        <div className="p-1 rounded bg-rose-500/20 text-rose-400">
                          <ArrowDownRight className="w-3.5 h-3.5" />
                        </div>
                      )}

                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-200">{trade.symbol}</span>
                          <span className="text-[10px] text-slate-500">#{trade.ticket}</span>
                          <span
                            className={`text-[9px] px-1.5 py-0.2 rounded font-bold ${
                              trade.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'
                            }`}
                          >
                            {trade.side === 'BUY' ? 'LONG' : 'SHORT'}
                          </span>
                        </div>
                        <div className="text-[10px] text-slate-500">
                          Entry: {trade.entryPrice.toFixed(5)} • Volume: {trade.volume} lots
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className={`font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {isWin ? `+$${trade.pnl.toFixed(2)}` : `-$${Math.abs(trade.pnl).toFixed(2)}`}
                        </div>
                        <div className="text-[10px] font-bold text-cyan-300">
                          {trade.pnlR >= 0 ? `+${trade.pnlR.toFixed(2)} R` : `${trade.pnlR.toFixed(2)} R`}
                        </div>
                      </div>

                      <button
                        id={`expand-trade-${trade.ticket}`}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedTradeForModal(trade);
                        }}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-900 hover:bg-cyan-950/60 border border-slate-800 hover:border-cyan-500/50 text-[11px] font-mono text-slate-300 hover:text-cyan-300 transition shadow-sm group cursor-pointer"
                        title={`Expand trade #${trade.ticket} detailed breakdown`}
                      >
                        <Maximize2 className="w-3 h-3 text-slate-400 group-hover:text-cyan-400 transition" />
                        <span>Expand</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
        </>
      )}
    </>
  )}

  {/* Detailed Trade Breakdown Modal */}
  <ClosedTradeDetailModal
    trade={selectedTradeForModal}
    onClose={() => setSelectedTradeForModal(null)}
  />
</div>
);
};
