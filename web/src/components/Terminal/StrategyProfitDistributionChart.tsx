import React, { useMemo, useState } from 'react';
import { Position } from '../../types/trading';
import { REGISTERED_STRATEGIES } from '../../data/strategies';
import {
  Layers,
  TrendingUp,
  TrendingDown,
  Clock,
  ArrowUpDown,
  Filter,
  CheckCircle2,
  Percent,
  Sparkles,
  RotateCcw
} from 'lucide-react';

export interface StrategyProfitDistributionProps {
  closedTrades: Position[];
  currentTimeframeFilter: string;
  onTimeframeChange?: (tf: string) => void;
  className?: string;
}

export interface StrategyStatItem {
  strategyId: string;
  name: string;
  shortName: string;
  family: string;
  timeframe: string;
  tradeCount: number;
  wins: number;
  losses: number;
  breakevens: number;
  winRate: number;
  totalProfit: number;
  totalR: number;
  grossProfit: number;
  grossLoss: number;
  profitFactor: number;
  avgR: number;
  bestTradePnl: number;
  bestTradeR: number;
  worstTradePnl: number;
  worstTradeR: number;
  profitSharePct: number;
  relativeBarWidthPct: number;
  colorClass: string;
  barGradient: string;
}

const STRATEGY_COLOR_PALETTES = [
  {
    border: 'border-emerald-500/40',
    badgeBg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    barGradient: 'from-emerald-500 via-teal-400 to-emerald-400',
    indicatorDot: 'bg-emerald-400',
    hex: '#10b981'
  },
  {
    border: 'border-cyan-500/40',
    badgeBg: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    barGradient: 'from-cyan-500 via-sky-400 to-cyan-400',
    indicatorDot: 'bg-cyan-400',
    hex: '#06b6d4'
  },
  {
    border: 'border-indigo-500/40',
    badgeBg: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    barGradient: 'from-indigo-500 via-violet-400 to-indigo-400',
    indicatorDot: 'bg-indigo-400',
    hex: '#6366f1'
  },
  {
    border: 'border-amber-500/40',
    badgeBg: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    barGradient: 'from-amber-500 via-yellow-400 to-amber-400',
    indicatorDot: 'bg-amber-400',
    hex: '#f59e0b'
  },
  {
    border: 'border-fuchsia-500/40',
    badgeBg: 'bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20',
    barGradient: 'from-fuchsia-500 via-purple-400 to-fuchsia-400',
    indicatorDot: 'bg-fuchsia-400',
    hex: '#d946ef'
  }
];

export const StrategyProfitDistributionChart: React.FC<StrategyProfitDistributionProps> = ({
  closedTrades,
  currentTimeframeFilter,
  onTimeframeChange,
  className = ''
}) => {
  const [sortBy, setSortBy] = useState<'profit' | 'trades' | 'winrate'>('profit');
  const [hoveredStrategyId, setHoveredStrategyId] = useState<string | null>(null);

  // Strategy metadata registry lookup map
  const strategyRegistryMap = useMemo(() => {
    const map = new Map<string, { name: string; shortName: string; family: string; timeframe: string }>();
    REGISTERED_STRATEGIES.forEach(strat => {
      let short = strat.name;
      if (strat.name.includes('Asian Session')) short = 'Asian Sweep 5R';
      else if (strat.name.includes('Canonical Session')) short = 'Session Trade V1';
      else if (strat.name.includes('Large SMC')) short = 'Large SMC V1';
      else if (strat.name.includes('Crypto & FX Sweep')) short = 'Sweep & Retest V1';

      map.set(strat.id, {
        name: strat.name,
        shortName: short,
        family: strat.family,
        timeframe: strat.timeframe
      });
    });
    return map;
  }, []);

  // Compute Strategy aggregations
  const { strategyStats, totalPortfolioProfit, totalPortfolioR, positiveProfitSum } = useMemo(() => {
    const stratMap = new Map<string, Position[]>();

    closedTrades.forEach(trade => {
      const id = trade.strategyId || 'UNKNOWN_STRATEGY';
      const list = stratMap.get(id) || [];
      list.push(trade);
      stratMap.set(id, list);
    });

    let totalProfitSum = 0;
    let totalRSum = 0;
    let posProfitSum = 0;

    const rawStats: Array<{
      strategyId: string;
      name: string;
      shortName: string;
      family: string;
      timeframe: string;
      tradeCount: number;
      wins: number;
      losses: number;
      breakevens: number;
      winRate: number;
      totalProfit: number;
      totalR: number;
      grossProfit: number;
      grossLoss: number;
      profitFactor: number;
      avgR: number;
      bestTradePnl: number;
      bestTradeR: number;
      worstTradePnl: number;
      worstTradeR: number;
    }> = [];

    stratMap.forEach((trades, stratId) => {
      const reg = strategyRegistryMap.get(stratId);
      const name = reg?.name || stratId;
      const shortName = reg?.shortName || stratId;
      const family = reg?.family || 'Trading Strategy';
      const timeframe = reg?.timeframe || 'M15';

      let pnlSum = 0;
      let rSum = 0;
      let wins = 0;
      let losses = 0;
      let breakevens = 0;
      let grossProfit = 0;
      let grossLoss = 0;
      let bestPnl = -Infinity;
      let bestR = -Infinity;
      let worstPnl = Infinity;
      let worstR = Infinity;

      trades.forEach(t => {
        pnlSum += t.pnl;
        rSum += t.pnlR;
        totalProfitSum += t.pnl;
        totalRSum += t.pnlR;

        if (t.pnl > 0.001 || t.pnlR > 0.01) {
          wins++;
          grossProfit += t.pnl;
        } else if (t.pnl < -0.001 || t.pnlR < -0.01) {
          losses++;
          grossLoss += Math.abs(t.pnl);
        } else {
          breakevens++;
        }

        if (t.pnl > bestPnl) bestPnl = t.pnl;
        if (t.pnlR > bestR) bestR = t.pnlR;
        if (t.pnl < worstPnl) worstPnl = t.pnl;
        if (t.pnlR < worstR) worstR = t.pnlR;
      });

      if (pnlSum > 0) {
        posProfitSum += pnlSum;
      }

      const count = trades.length;
      const winRate = count > 0 ? (wins / count) * 100 : 0;
      const avgR = count > 0 ? rSum / count : 0;
      const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99.9 : 0;

      rawStats.push({
        strategyId: stratId,
        name,
        shortName,
        family,
        timeframe,
        tradeCount: count,
        wins,
        losses,
        breakevens,
        winRate,
        totalProfit: pnlSum,
        totalR: rSum,
        grossProfit,
        grossLoss,
        profitFactor,
        avgR,
        bestTradePnl: bestPnl === -Infinity ? 0 : bestPnl,
        bestTradeR: bestR === -Infinity ? 0 : bestR,
        worstTradePnl: worstPnl === Infinity ? 0 : worstPnl,
        worstTradeR: worstR === Infinity ? 0 : worstR
      });
    });

    // Find max absolute profit for scale
    const maxAbsProfit = Math.max(...rawStats.map(s => Math.abs(s.totalProfit)), 1);

    const formattedStats: StrategyStatItem[] = rawStats.map((item, index) => {
      const palette = STRATEGY_COLOR_PALETTES[index % STRATEGY_COLOR_PALETTES.length];
      const profitSharePct = posProfitSum > 0 && item.totalProfit > 0
        ? (item.totalProfit / posProfitSum) * 100
        : 0;

      // Bar width percentage relative to max absolute profit, minimum 6% for visibility
      const relativeBarWidthPct = Math.min(100, Math.max(6, (Math.abs(item.totalProfit) / maxAbsProfit) * 100));

      const barGradient = item.totalProfit >= 0
        ? palette.barGradient
        : 'from-rose-500 via-rose-600 to-amber-500';

      return {
        ...item,
        profitSharePct,
        relativeBarWidthPct,
        colorClass: palette.badgeBg,
        barGradient
      };
    });

    // Sort according to selection
    formattedStats.sort((a, b) => {
      if (sortBy === 'profit') return b.totalProfit - a.totalProfit;
      if (sortBy === 'trades') return b.tradeCount - a.tradeCount;
      if (sortBy === 'winrate') return b.winRate - a.winRate;
      return 0;
    });

    return {
      strategyStats: formattedStats,
      totalPortfolioProfit: totalProfitSum,
      totalPortfolioR: totalRSum,
      positiveProfitSum: posProfitSum
    };
  }, [closedTrades, strategyRegistryMap, sortBy]);

  // Label for active timeframe filter
  const timeframeFilterLabel = useMemo(() => {
    switch (currentTimeframeFilter.toUpperCase()) {
      case 'TODAY':
      case '1D':
      case '24H':
        return 'Today (24h)';
      case 'WEEK':
      case '1W':
      case '7D':
        return 'This Week (7D)';
      case 'MONTH':
      case '1M':
      case '30D':
        return 'This Month (30D)';
      case 'M15':
        return 'M15 Timeframe';
      case 'H1':
        return 'H1 Timeframe';
      case 'M5':
        return 'M5 Timeframe';
      case 'ALL':
      default:
        return 'All Timeframes';
    }
  }, [currentTimeframeFilter]);

  return (
    <div
      id="strategy-profit-distribution-card"
      className={`bg-slate-900/90 border border-slate-800/90 rounded-xl p-4 sm:p-5 shadow-lg backdrop-blur-sm ${className}`}
    >
      {/* Header section with active timeframe indicator and controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <Layers className="w-4 h-4" />
            </span>
            <h3 className="text-sm font-semibold tracking-wide text-slate-100 uppercase">
              Strategy Profit Distribution
            </h3>
            {/* Active Timeframe Badge */}
            <span
              id="active-timeframe-filter-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-cyan-950/60 border border-cyan-700/40 text-cyan-300"
              title={`Filtered by timeframe: ${timeframeFilterLabel}`}
            >
              <Clock className="w-3 h-3 text-cyan-400 animate-pulse" />
              <span>{timeframeFilterLabel}</span>
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Visual breakdown of net realized P&L and R-multiple generated by each strategy contract
          </p>
        </div>

        {/* Sort Controls & Quick Stats */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <div className="flex items-center gap-1 bg-slate-800/80 p-1 rounded-lg border border-slate-700/60 text-xs">
            <span className="text-slate-400 text-[11px] px-1.5 flex items-center gap-1">
              <ArrowUpDown className="w-3 h-3" />
              Sort:
            </span>
            <button
              id="sort-strategy-by-profit-btn"
              type="button"
              onClick={() => setSortBy('profit')}
              className={`px-2 py-1 rounded transition-colors ${
                sortBy === 'profit'
                  ? 'bg-emerald-500/20 text-emerald-300 font-semibold shadow-sm border border-emerald-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              P&L
            </button>
            <button
              id="sort-strategy-by-trades-btn"
              type="button"
              onClick={() => setSortBy('trades')}
              className={`px-2 py-1 rounded transition-colors ${
                sortBy === 'trades'
                  ? 'bg-emerald-500/20 text-emerald-300 font-semibold shadow-sm border border-emerald-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Trades
            </button>
            <button
              id="sort-strategy-by-winrate-btn"
              type="button"
              onClick={() => setSortBy('winrate')}
              className={`px-2 py-1 rounded transition-colors ${
                sortBy === 'winrate'
                  ? 'bg-emerald-500/20 text-emerald-300 font-semibold shadow-sm border border-emerald-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Win Rate
            </button>
          </div>

          {currentTimeframeFilter !== 'ALL' && onTimeframeChange && (
            <button
              id="reset-timeframe-filter-btn"
              type="button"
              onClick={() => onTimeframeChange('ALL')}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200 bg-slate-800/60 hover:bg-slate-800 border border-slate-700 rounded-lg flex items-center gap-1 transition-all"
              title="Reset timeframe filter to show all trades"
            >
              <RotateCcw className="w-3 h-3" />
              <span className="hidden sm:inline">Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* Aggregate Portfolio Summary Strip */}
      {strategyStats.length > 0 && (
        <div className="my-4 p-3 rounded-lg bg-slate-950/70 border border-slate-800/80">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-medium">Aggregate Contribution:</span>
              <span className="text-slate-200 font-mono">
                {strategyStats.length} {strategyStats.length === 1 ? 'Strategy' : 'Strategies'} Active
              </span>
              <span className="text-slate-500">•</span>
              <span className="text-slate-300 font-mono">{closedTrades.length} settled trades</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-slate-400">Total Net:</span>
              <span
                className={`font-mono font-bold ${
                  totalPortfolioProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {totalPortfolioProfit >= 0 ? '+' : ''}${totalPortfolioProfit.toFixed(2)}
              </span>
              <span
                className={`px-1.5 py-0.5 rounded font-mono text-[11px] font-bold ${
                  totalPortfolioR >= 0
                    ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                }`}
              >
                {totalPortfolioR >= 0 ? '+' : ''}{totalPortfolioR.toFixed(2)} R
              </span>
            </div>
          </div>

          {/* Stacked Proportional Distribution Track */}
          {positiveProfitSum > 0 && (
            <div className="w-full">
              <div className="h-2 w-full bg-slate-800/90 rounded-full overflow-hidden flex shadow-inner">
                {strategyStats
                  .filter(s => s.totalProfit > 0)
                  .map((s, idx) => (
                    <div
                      key={`stacked-${s.strategyId}`}
                      id={`stacked-bar-${s.strategyId}`}
                      className={`h-full bg-gradient-to-r ${s.barGradient} transition-all duration-300 hover:brightness-125 cursor-pointer`}
                      style={{ width: `${s.profitSharePct}%` }}
                      title={`${s.shortName}: $${s.totalProfit.toFixed(2)} (${s.profitSharePct.toFixed(1)}% of total profit)`}
                      onMouseEnter={() => setHoveredStrategyId(s.strategyId)}
                      onMouseLeave={() => setHoveredStrategyId(null)}
                    />
                  ))}
              </div>
              {/* Mini legend dots */}
              <div className="flex flex-wrap items-center gap-3 mt-2 text-[11px] text-slate-400">
                {strategyStats.map((s, i) => {
                  const palette = STRATEGY_COLOR_PALETTES[i % STRATEGY_COLOR_PALETTES.length];
                  return (
                    <div
                      key={`legend-${s.strategyId}`}
                      className={`flex items-center gap-1.5 transition-opacity ${
                        hoveredStrategyId && hoveredStrategyId !== s.strategyId ? 'opacity-40' : 'opacity-100'
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${s.totalProfit >= 0 ? palette.indicatorDot : 'bg-rose-500'}`} />
                      <span className="text-slate-300">{s.shortName}</span>
                      <span className="font-mono text-slate-400">({s.profitSharePct.toFixed(0)}%)</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main Horizontal Bar Chart List */}
      <div className="space-y-3.5 mt-4" id="strategy-horizontal-bars-container">
        {strategyStats.length === 0 ? (
          <div className="py-8 text-center bg-slate-950/40 rounded-xl border border-dashed border-slate-800 p-6">
            <Filter className="w-8 h-8 text-slate-500 mx-auto mb-2 opacity-60" />
            <p className="text-sm font-medium text-slate-300">
              No closed trades found for {timeframeFilterLabel}
            </p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              None of the closed positions in your historical ledger match the currently applied timeframe or search filters.
            </p>
            {currentTimeframeFilter !== 'ALL' && onTimeframeChange && (
              <button
                type="button"
                onClick={() => onTimeframeChange('ALL')}
                className="mt-3 px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all inline-flex items-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset Timeframe Filter to All
              </button>
            )}
          </div>
        ) : (
          strategyStats.map((stat, index) => {
            const isHovered = hoveredStrategyId === stat.strategyId;
            const isProfitable = stat.totalProfit >= 0;

            return (
              <div
                key={stat.strategyId}
                id={`strategy-bar-row-${stat.strategyId}`}
                onMouseEnter={() => setHoveredStrategyId(stat.strategyId)}
                onMouseLeave={() => setHoveredStrategyId(null)}
                className={`p-3.5 rounded-xl border transition-all duration-200 ${
                  isHovered
                    ? 'bg-slate-800/80 border-slate-600 shadow-md transform -translate-y-0.5'
                    : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700/80 hover:bg-slate-900/60'
                }`}
              >
                {/* Line 1: Strategy Name, Badges, and Profit Value */}
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono text-slate-500 font-bold">#{index + 1}</span>
                    <span className="text-sm font-semibold text-slate-100 tracking-tight">
                      {stat.name}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 border border-slate-700 text-slate-400">
                      {stat.strategyId}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-cyan-950/80 text-cyan-300 border border-cyan-800/50">
                      {stat.timeframe}
                    </span>
                  </div>

                  {/* Profit & R-multiple Display */}
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`text-sm font-mono font-bold tracking-tight ${
                        isProfitable ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {isProfitable ? '+' : ''}${stat.totalProfit.toFixed(2)}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-mono font-bold shadow-sm ${
                        stat.totalR >= 0
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                      }`}
                    >
                      {stat.totalR >= 0 ? '+' : ''}{stat.totalR.toFixed(2)} R
                    </span>
                  </div>
                </div>

                {/* Line 2: The Horizontal Bar Visualizing Profit Distribution */}
                <div className="relative my-2.5">
                  <div className="h-3 w-full bg-slate-800/80 rounded-full overflow-hidden p-0.5 border border-slate-700/50">
                    <div
                      id={`horizontal-bar-fill-${stat.strategyId}`}
                      className={`h-full rounded-full bg-gradient-to-r ${stat.barGradient} transition-all duration-500 ease-out shadow-sm`}
                      style={{ width: `${stat.relativeBarWidthPct}%` }}
                    />
                  </div>
                </div>

                {/* Line 3: Supporting Distribution Metrics */}
                <div className="flex flex-wrap items-center justify-between text-xs text-slate-400 gap-2 pt-1 border-t border-slate-800/50">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="flex items-center gap-1">
                      <span className="text-slate-300 font-mono font-medium">{stat.tradeCount}</span>
                      <span>{stat.tradeCount === 1 ? 'trade' : 'trades'}</span>
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                      <span className="text-slate-200 font-mono font-medium">{stat.winRate.toFixed(1)}% WR</span>
                      <span className="text-slate-500 text-[11px]">
                        ({stat.wins}W / {stat.losses}L{stat.breakevens > 0 ? ` / ${stat.breakevens}BE` : ''})
                      </span>
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="text-slate-400">
                      Avg: <span className="text-slate-200 font-mono">{stat.avgR >= 0 ? '+' : ''}{stat.avgR.toFixed(2)} R</span>
                    </span>
                    {stat.profitFactor > 0 && (
                      <>
                        <span className="text-slate-600">•</span>
                        <span className="text-slate-400">
                          PF: <span className="text-slate-200 font-mono">{stat.profitFactor >= 99 ? '∞' : stat.profitFactor.toFixed(2)}</span>
                        </span>
                      </>
                    )}
                  </div>

                  {/* Share of Portfolio / Contribution */}
                  {stat.profitSharePct > 0 && (
                    <div className="flex items-center gap-1.5 text-slate-300 font-mono text-[11px]">
                      <span className="text-slate-500">Share:</span>
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-emerald-300 font-bold">
                        {stat.profitSharePct.toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer hint */}
      <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between text-[11px] text-slate-500 gap-2">
        <span className="flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-emerald-400" />
          Synchronized automatically with current timeframe, asset, and outcome filters.
        </span>
        <span className="font-mono text-slate-400">
          Formula: Relative Bar Width = |Strategy Profit| / Max Strategy Profit
        </span>
      </div>
    </div>
  );
};

export default StrategyProfitDistributionChart;
