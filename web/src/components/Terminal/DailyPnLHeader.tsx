import React, { useState, useMemo } from 'react';
import { Position } from '../../types/trading';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Calendar,
  Clock,
  Shield,
  ShieldCheck,
  ShieldAlert,
  Percent,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Sparkles,
  Award,
  Activity,
  AlertCircle,
  FileText,
  LineChart as LineChartIcon
} from 'lucide-react';

interface DailyPnLHeaderProps {
  positions: Position[];
  onSelectSymbol?: (symbol: string) => void;
  onOpenExecutionCockpit?: () => void;
  onOpenTradeJournal?: () => void;
}

type HorizonFilter = 'TODAY_UTC' | 'TODAY_LOCAL' | 'LAST_24H' | 'THIS_WEEK';

export const DailyPnLHeader: React.FC<DailyPnLHeaderProps> = ({
  positions,
  onSelectSymbol,
  onOpenExecutionCockpit,
  onOpenTradeJournal
}) => {
  const [horizon, setHorizon] = useState<HorizonFilter>('TODAY_UTC');
  const [showTradesDrawer, setShowTradesDrawer] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Filter closed positions by the selected time horizon
  const { filteredClosedTrades, horizonLabel } = useMemo(() => {
    const closed = positions.filter(p => p.status === 'CLOSED');
    const now = new Date();

    let filtered: Position[] = [];
    let label = "Today's Trading Session";

    if (horizon === 'TODAY_UTC') {
      label = "Today's Session (UTC)";
      const startOfUtcToday = Date.UTC(
        now.getUTCFullYear(),
        now.getUTCMonth(),
        now.getUTCDate()
      ) / 1000;

      filtered = closed.filter(p => {
        const time = p.closeTime || p.openTime;
        return time >= startOfUtcToday;
      });
    } else if (horizon === 'TODAY_LOCAL') {
      label = "Today's Session (Local Time)";
      const startOfLocalToday = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate()
      ).getTime() / 1000;

      filtered = closed.filter(p => {
        const time = p.closeTime || p.openTime;
        return time >= startOfLocalToday;
      });
    } else if (horizon === 'LAST_24H') {
      label = 'Rolling Last 24 Hours';
      const twentyFourHoursAgo = Math.floor(Date.now() / 1000) - 86400;
      filtered = closed.filter(p => {
        const time = p.closeTime || p.openTime;
        return time >= twentyFourHoursAgo;
      });
    } else if (horizon === 'THIS_WEEK') {
      label = 'This Week (WTD)';
      const day = now.getUTCDay();
      const diffToMonday = (day === 0 ? -6 : 1) - day;
      const mondayUtc = new Date(now);
      mondayUtc.setUTCDate(now.getUTCDate() + diffToMonday);
      mondayUtc.setUTCHours(0, 0, 0, 0);
      const startOfWeek = Math.floor(mondayUtc.getTime() / 1000);

      filtered = closed.filter(p => {
        const time = p.closeTime || p.openTime;
        return time >= startOfWeek;
      });
    }

    return { filteredClosedTrades: filtered, horizonLabel: label };
  }, [positions, horizon]);

  // Compute stats for the filtered closed trades
  const stats = useMemo(() => {
    const totalTrades = filteredClosedTrades.length;
    let netPnl = 0;
    let netR = 0;
    let wins = 0;
    let losses = 0;
    let breakevens = 0;
    let grossProfit = 0;
    let grossLoss = 0;
    let maxWin = 0;
    let maxLoss = 0;

    filteredClosedTrades.forEach(trade => {
      netPnl += trade.pnl;
      netR += trade.pnlR;

      if (trade.pnl > 0.001) {
        wins += 1;
        grossProfit += trade.pnl;
        if (trade.pnl > maxWin) maxWin = trade.pnl;
      } else if (trade.pnl < -0.001) {
        losses += 1;
        grossLoss += Math.abs(trade.pnl);
        if (trade.pnl < maxLoss) maxLoss = trade.pnl;
      } else {
        breakevens += 1;
      }
    });

    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99.9 : 0;
    const avgR = totalTrades > 0 ? netR / totalTrades : 0;

    // Daily risk guard configuration (Default 3.0R max daily drawdown or $1,000 limit)
    const maxDailyLossR = 3.0;
    const currentLossR = netR < 0 ? Math.abs(netR) : 0;
    const dailyLimitRemainingR = Math.max(0, maxDailyLossR - currentLossR);
    const riskGuardPercentage = Math.min(100, (currentLossR / maxDailyLossR) * 100);

    let riskStatus: 'SAFE' | 'CAUTION' | 'BREACHED' = 'SAFE';
    if (netR <= -maxDailyLossR) {
      riskStatus = 'BREACHED';
    } else if (netR < -1.5) {
      riskStatus = 'CAUTION';
    }

    return {
      totalTrades,
      netPnl,
      netR,
      wins,
      losses,
      breakevens,
      grossProfit,
      grossLoss,
      winRate,
      profitFactor,
      avgR,
      maxWin,
      maxLoss,
      maxDailyLossR,
      dailyLimitRemainingR,
      riskGuardPercentage,
      riskStatus
    };
  }, [filteredClosedTrades]);

  // Open / floating positions metrics for contextual overview
  const openPositions = useMemo(() => {
    return positions.filter(p => p.status !== 'CLOSED');
  }, [positions]);

  const openFloatingPnl = useMemo(() => {
    return openPositions.reduce((sum, p) => sum + p.pnl, 0);
  }, [openPositions]);

  const openFloatingR = useMemo(() => {
    return openPositions.reduce((sum, p) => sum + p.pnlR, 0);
  }, [openPositions]);

  const handleCopySummary = () => {
    const summaryText = `[AG Profit Trading - ${horizonLabel}]\n` +
      `Net Realized PnL: ${stats.netPnl >= 0 ? '+' : ''}$${stats.netPnl.toFixed(2)} (${stats.netR >= 0 ? '+' : ''}${stats.netR.toFixed(2)}R)\n` +
      `Trades: ${stats.totalTrades} (Wins: ${stats.wins}, Losses: ${stats.losses}, BE: ${stats.breakevens})\n` +
      `Win Rate: ${stats.winRate.toFixed(1)}% | Profit Factor: ${stats.profitFactor.toFixed(2)}x\n` +
      `Gross Profit: +$${stats.grossProfit.toFixed(2)} | Gross Loss: -$${stats.grossLoss.toFixed(2)}\n` +
      `Risk Guard: ${stats.riskStatus} (Used: ${stats.riskGuardPercentage.toFixed(0)}% of max ${stats.maxDailyLossR}R limit)\n` +
      `Open Floating: ${openFloatingPnl >= 0 ? '+' : ''}$${openFloatingPnl.toFixed(2)} (${openPositions.length} active)`;

    navigator.clipboard.writeText(summaryText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const isNetPositive = stats.netPnl > 0.001;
  const isNetNegative = stats.netPnl < -0.001;

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl shadow-lg p-4 md:p-5 backdrop-blur font-sans">
      {/* Top Bar: Title, Horizon Selector, and Quick Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider font-mono">
                Daily Profit & Loss Summary
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>REALIZED MT5 METRICS</span>
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              Deterministic calculation from executed demo/managed position ledger
            </p>
          </div>
        </div>

        {/* Horizon Picker & Action Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-xs font-mono">
            <button
              id="horizon-btn-utc"
              type="button"
              onClick={() => setHorizon('TODAY_UTC')}
              className={`px-2.5 py-1 rounded transition font-medium ${
                horizon === 'TODAY_UTC'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Today (UTC)
            </button>
            <button
              id="horizon-btn-local"
              type="button"
              onClick={() => setHorizon('TODAY_LOCAL')}
              className={`px-2.5 py-1 rounded transition font-medium ${
                horizon === 'TODAY_LOCAL'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Local
            </button>
            <button
              id="horizon-btn-24h"
              type="button"
              onClick={() => setHorizon('LAST_24H')}
              className={`px-2.5 py-1 rounded transition font-medium ${
                horizon === 'LAST_24H'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              24h
            </button>
            <button
              id="horizon-btn-week"
              type="button"
              onClick={() => setHorizon('THIS_WEEK')}
              className={`px-2.5 py-1 rounded transition font-medium ${
                horizon === 'THIS_WEEK'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Week
            </button>
          </div>

          <button
            id="btn-copy-daily-pnl"
            type="button"
            onClick={handleCopySummary}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition flex items-center gap-1 text-xs font-mono"
            title="Copy formatted daily performance report to clipboard"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-emerald-400 text-[11px]">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span className="hidden sm:inline text-[11px]">Report</span>
              </>
            )}
          </button>

          {onOpenTradeJournal && (
            <button
              id="btn-open-trade-journal"
              type="button"
              onClick={onOpenTradeJournal}
              className="p-1.5 px-2.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 transition flex items-center gap-1.5 text-xs font-mono"
              title="Open full deterministic Trade Journal & weekly/monthly PnL growth charts"
            >
              <LineChartIcon className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden sm:inline text-[11px] font-bold">Trade Journal</span>
            </button>
          )}
        </div>
      </div>

      {/* Main KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: Net Realized PnL (Primary Anchor) */}
        <div
          className={`rounded-xl p-4 border transition-all flex flex-col justify-between ${
            isNetPositive
              ? 'bg-emerald-950/25 border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.08)]'
              : isNetNegative
              ? 'bg-rose-950/25 border-rose-500/40 shadow-[0_0_15px_rgba(244,63,94,0.08)]'
              : 'bg-slate-950/50 border-slate-800'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Net Realized P&L
            </span>
            <div
              className={`p-1.5 rounded-md ${
                isNetPositive
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : isNetNegative
                  ? 'bg-rose-500/20 text-rose-400'
                  : 'bg-slate-800 text-slate-400'
              }`}
            >
              {isNetPositive ? (
                <TrendingUp className="w-4 h-4" />
              ) : isNetNegative ? (
                <TrendingDown className="w-4 h-4" />
              ) : (
                <DollarSign className="w-4 h-4" />
              )}
            </div>
          </div>

          <div className="my-2">
            <div className="flex items-baseline gap-2">
              <span
                id="daily-net-pnl-value"
                className={`text-2xl lg:text-3xl font-extrabold font-mono tracking-tight ${
                  isNetPositive
                    ? 'text-emerald-400'
                    : isNetNegative
                    ? 'text-rose-400'
                    : 'text-slate-300'
                }`}
              >
                {stats.netPnl >= 0 ? '+' : '-'}${Math.abs(stats.netPnl).toFixed(2)}
              </span>
              <span
                id="daily-net-r-value"
                className={`text-xs font-mono font-bold px-2 py-0.5 rounded-full border ${
                  isNetPositive
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : isNetNegative
                    ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}
              >
                {stats.netR >= 0 ? '+' : ''}{stats.netR.toFixed(2)}R
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 border-t border-slate-800/60 pt-2">
            <span>Avg R/Trade:</span>
            <span className={stats.avgR >= 0 ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
              {stats.avgR >= 0 ? '+' : ''}{stats.avgR.toFixed(2)}R
            </span>
          </div>
        </div>

        {/* Metric 2: Win Rate & Closed Trades Count */}
        <div className="rounded-xl p-4 bg-slate-950/60 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Win Rate & Trades
            </span>
            <div className="p-1.5 rounded-md bg-cyan-500/10 text-cyan-400">
              <Percent className="w-4 h-4" />
            </div>
          </div>

          <div className="my-2">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl lg:text-3xl font-extrabold font-mono text-slate-100">
                {stats.winRate.toFixed(1)}%
              </span>
              <span className="text-xs font-mono text-slate-400">
                ({stats.totalTrades} closed)
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono border-t border-slate-800/60 pt-2">
            <div className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold">{stats.wins}W</span>
              <span className="text-slate-600">/</span>
              <span className="text-rose-400 font-bold">{stats.losses}L</span>
              <span className="text-slate-600">/</span>
              <span className="text-slate-400">{stats.breakevens}BE</span>
            </div>
            <span className="text-slate-400">
              PF: <strong className="text-slate-200">{stats.profitFactor > 0 ? stats.profitFactor.toFixed(2) : '0.00'}x</strong>
            </span>
          </div>
        </div>

        {/* Metric 3: Gross Profit vs Gross Loss */}
        <div className="rounded-xl p-4 bg-slate-950/60 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Gross Volume P&L
            </span>
            <div className="p-1.5 rounded-md bg-indigo-500/10 text-indigo-400">
              <Activity className="w-4 h-4" />
            </div>
          </div>

          <div className="my-2 space-y-1">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400 flex items-center gap-1">
                <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                <span>Gross Profit:</span>
              </span>
              <span className="text-emerald-400 font-bold font-mono">
                +${stats.grossProfit.toFixed(2)}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400 flex items-center gap-1">
                <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" />
                <span>Gross Loss:</span>
              </span>
              <span className="text-rose-400 font-bold font-mono">
                -${stats.grossLoss.toFixed(2)}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 border-t border-slate-800/60 pt-2">
            <span>Best Trade:</span>
            <span className="text-emerald-300 font-semibold font-mono">
              {stats.maxWin > 0 ? `+$${stats.maxWin.toFixed(2)}` : '$0.00'}
            </span>
          </div>
        </div>

        {/* Metric 4: Risk Guard & Open Floating PnL */}
        <div className="rounded-xl p-4 bg-slate-950/60 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Risk Guard & Floating
            </span>
            <div
              className={`p-1.5 rounded-md ${
                stats.riskStatus === 'SAFE'
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : stats.riskStatus === 'CAUTION'
                  ? 'bg-amber-500/10 text-amber-400'
                  : 'bg-rose-500/10 text-rose-400'
              }`}
            >
              {stats.riskStatus === 'SAFE' ? (
                <ShieldCheck className="w-4 h-4" />
              ) : stats.riskStatus === 'CAUTION' ? (
                <Shield className="w-4 h-4" />
              ) : (
                <ShieldAlert className="w-4 h-4" />
              )}
            </div>
          </div>

          <div className="my-2 space-y-1.5">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400">Daily Loss Cap (3R):</span>
              <span
                className={`font-bold px-1.5 py-0.2 rounded text-[10px] ${
                  stats.riskStatus === 'SAFE'
                    ? 'bg-emerald-500/20 text-emerald-300'
                    : stats.riskStatus === 'CAUTION'
                    ? 'bg-amber-500/20 text-amber-300'
                    : 'bg-rose-500/20 text-rose-300'
                }`}
              >
                {stats.riskStatus}
              </span>
            </div>

            {/* Risk Guard mini progress bar */}
            <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  stats.riskStatus === 'SAFE'
                    ? 'bg-emerald-500'
                    : stats.riskStatus === 'CAUTION'
                    ? 'bg-amber-500'
                    : 'bg-rose-500'
                }`}
                style={{ width: `${Math.max(5, stats.riskGuardPercentage)}%` }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono border-t border-slate-800/60 pt-2">
            <span className="text-slate-400">Open Floating:</span>
            <div className="flex items-center gap-1.5">
              <span
                className={`font-bold ${
                  openFloatingPnl > 0
                    ? 'text-emerald-400'
                    : openFloatingPnl < 0
                    ? 'text-rose-400'
                    : 'text-slate-300'
                }`}
              >
                {openFloatingPnl >= 0 ? '+' : ''}${openFloatingPnl.toFixed(2)}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                ({openPositions.length} active)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Expandable Today's Closed Trades Breakdown */}
      <div className="mt-3 pt-3 border-t border-slate-800/80">
        <div className="flex items-center justify-between">
          <button
            id="toggle-closed-trades-drawer"
            type="button"
            onClick={() => setShowTradesDrawer(!showTradesDrawer)}
            className="text-xs font-mono text-slate-400 hover:text-cyan-300 flex items-center gap-1.5 transition py-1"
          >
            {showTradesDrawer ? (
              <ChevronUp className="w-4 h-4 text-cyan-400" />
            ) : (
              <ChevronDown className="w-4 h-4 text-cyan-400" />
            )}
            <span className="font-semibold text-slate-200">
              {showTradesDrawer ? 'Hide Closed Trade Ledger' : 'View Closed Trade Ledger'}
            </span>
            <span className="text-slate-500">
              ({filteredClosedTrades.length} {filteredClosedTrades.length === 1 ? 'position' : 'positions'} closed)
            </span>
          </button>

          {onOpenExecutionCockpit && (
            <button
              type="button"
              onClick={onOpenExecutionCockpit}
              className="text-xs font-mono text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1"
            >
              <span>Execution Cockpit</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Drawer Contents */}
        {showTradesDrawer && (
          <div className="mt-3 space-y-2 animate-in fade-in slide-in-from-top-1 duration-200">
            {filteredClosedTrades.length === 0 ? (
              <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-center font-mono text-xs text-slate-400">
                No closed trades found for {horizonLabel}. Active open positions will populate here once closed.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                {filteredClosedTrades.map(trade => {
                  const isTradeWin = trade.pnl > 0.001;
                  const isTradeLoss = trade.pnl < -0.001;
                  const closeDate = trade.closeTime ? new Date(trade.closeTime * 1000) : null;
                  const timeFormatted = closeDate
                    ? `${closeDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                    : 'N/A';

                  return (
                    <div
                      key={trade.ticket}
                      onClick={() => onSelectSymbol && onSelectSymbol(trade.symbol)}
                      className={`p-3 rounded-lg border text-xs font-mono transition cursor-pointer hover:border-cyan-500/50 ${
                        isTradeWin
                          ? 'bg-emerald-950/20 border-emerald-800/40'
                          : isTradeLoss
                          ? 'bg-rose-950/20 border-rose-800/40'
                          : 'bg-slate-950 border-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              trade.side === 'BUY'
                                ? 'bg-emerald-500/20 text-emerald-300'
                                : 'bg-rose-500/20 text-rose-300'
                            }`}
                          >
                            {trade.side}
                          </span>
                          <span className="font-bold text-slate-100">{trade.symbol}</span>
                          <span className="text-[10px] text-slate-500">#{trade.ticket}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <span>{timeFormatted}</span>
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs my-1">
                        <span className="text-slate-400">
                          {trade.volume} lots @ {trade.entryPrice.toFixed(trade.symbol.includes('JPY') ? 3 : 5)}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`font-bold ${
                              isTradeWin
                                ? 'text-emerald-400'
                                : isTradeLoss
                                ? 'text-rose-400'
                                : 'text-slate-300'
                            }`}
                          >
                            {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                          </span>
                          <span
                            className={`px-1.5 py-0.2 rounded text-[10px] font-semibold ${
                              isTradeWin
                                ? 'bg-emerald-500/20 text-emerald-300'
                                : isTradeLoss
                                ? 'bg-rose-500/20 text-rose-300'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {trade.pnlR >= 0 ? '+' : ''}{trade.pnlR.toFixed(2)}R
                          </span>
                        </div>
                      </div>

                      {trade.journalNotes && trade.journalNotes.length > 0 && (
                        <div className="mt-1.5 pt-1.5 border-t border-slate-800/60 text-[11px] text-slate-400 flex items-start gap-1">
                          <FileText className="w-3 h-3 text-cyan-400 shrink-0 mt-0.5" />
                          <span className="truncate">{trade.journalNotes[trade.journalNotes.length - 1]}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
