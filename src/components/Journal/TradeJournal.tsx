import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  CartesianGrid,
  ReferenceLine,
  Legend
} from 'recharts';
import { Position } from '../../types/trading';
import {
  TrendingUp,
  TrendingDown,
  Calendar,
  DollarSign,
  Award,
  BarChart3,
  LineChart as LineChartIcon,
  Percent,
  Filter,
  Search,
  Plus,
  Trash2,
  Clock,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  FileText,
  ChevronDown,
  ChevronUp,
  Layers,
  Sparkles,
  ArrowUpRight,
  ArrowDownRight,
  RotateCcw
} from 'lucide-react';

export interface TradeJournalProps {
  positions: Position[];
  onSelectSymbol?: (symbol: string) => void;
  onOpenExecutionCockpit?: () => void;
  onSaveNote?: (ticket: number, note: string) => Promise<void> | void;
  onDeleteNote?: (ticket: number, noteIndex: number) => Promise<void> | void;
}

type PeriodView = 'WEEKLY' | 'MONTHLY' | 'CUMULATIVE';
type MetricView = 'USD' | 'R_MULTIPLE';

interface AggregatedPnlPoint {
  period: string;
  label: string;
  startDate: string;
  endDate?: string;
  pnl: number;
  pnlR: number;
  cumulativePnl: number;
  cumulativeR: number;
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
}

export const TradeJournal: React.FC<TradeJournalProps> = ({
  positions,
  onSelectSymbol,
  onOpenExecutionCockpit,
  onSaveNote,
  onDeleteNote
}) => {
  // Chart and aggregation view states
  const [periodView, setPeriodView] = useState<PeriodView>('WEEKLY');
  const [metricView, setMetricView] = useState<MetricView>('USD');

  // Trade journal filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL');
  const [symbolFilter, setSymbolFilter] = useState<string>('ALL');
  const [outcomeFilter, setOutcomeFilter] = useState<'ALL' | 'WIN' | 'LOSS' | 'BREAKEVEN'>('ALL');

  // Expandable journal notes row state
  const [expandedTicket, setExpandedTicket] = useState<number | null>(null);
  const [newNoteText, setNewNoteText] = useState<{ [ticket: number]: string }>({});
  const [isSavingNote, setIsSavingNote] = useState<boolean>(false);

  // Closed positions sorted chronologically (oldest to newest for growth calculation)
  const closedTradesChronological = useMemo(() => {
    return positions
      .filter(p => p.status === 'CLOSED')
      .sort((a, b) => {
        const timeA = a.closeTime || a.openTime || 0;
        const timeB = b.closeTime || b.openTime || 0;
        return timeA - timeB;
      });
  }, [positions]);

  // Closed positions sorted reverse chronologically (newest first for journal log)
  const closedTradesNewestFirst = useMemo(() => {
    return [...closedTradesChronological].reverse();
  }, [closedTradesChronological]);

  // Global Performance KPIs
  const kpiStats = useMemo(() => {
    const totalTrades = closedTradesChronological.length;
    if (totalTrades === 0) {
      return {
        totalPnl: 0,
        totalR: 0,
        wins: 0,
        losses: 0,
        breakevens: 0,
        winRate: 0,
        profitFactor: 0,
        avgR: 0,
        grossProfit: 0,
        grossLoss: 0,
        maxDrawdownPnl: 0,
        maxDrawdownPct: 0,
        bestTradePnl: 0,
        worstTradePnl: 0
      };
    }

    let totalPnl = 0;
    let totalR = 0;
    let wins = 0;
    let losses = 0;
    let breakevens = 0;
    let grossProfit = 0;
    let grossLoss = 0;
    let bestTradePnl = -Infinity;
    let worstTradePnl = Infinity;

    // Track peak for drawdown
    let runningPnl = 0;
    let peakPnl = 0;
    let maxDrawdownPnl = 0;

    closedTradesChronological.forEach(trade => {
      totalPnl += trade.pnl;
      totalR += trade.pnlR;
      runningPnl += trade.pnl;

      if (runningPnl > peakPnl) {
        peakPnl = runningPnl;
      }
      const dd = peakPnl - runningPnl;
      if (dd > maxDrawdownPnl) {
        maxDrawdownPnl = dd;
      }

      if (trade.pnl > 0.01) {
        wins++;
        grossProfit += trade.pnl;
      } else if (trade.pnl < -0.01) {
        losses++;
        grossLoss += Math.abs(trade.pnl);
      } else {
        breakevens++;
      }

      if (trade.pnl > bestTradePnl) bestTradePnl = trade.pnl;
      if (trade.pnl < worstTradePnl) worstTradePnl = trade.pnl;
    });

    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99.9 : 0;
    const avgR = totalTrades > 0 ? totalR / totalTrades : 0;
    const startingCapital = 10000;
    const maxDrawdownPct = (maxDrawdownPnl / (startingCapital + peakPnl)) * 100;

    return {
      totalPnl,
      totalR,
      wins,
      losses,
      breakevens,
      winRate,
      profitFactor,
      avgR,
      grossProfit,
      grossLoss,
      maxDrawdownPnl,
      maxDrawdownPct,
      bestTradePnl: bestTradePnl === -Infinity ? 0 : bestTradePnl,
      worstTradePnl: worstTradePnl === Infinity ? 0 : worstTradePnl
    };
  }, [closedTradesChronological]);

  // Aggregate by Weekly or Monthly periods
  const aggregatedData = useMemo<AggregatedPnlPoint[]>(() => {
    if (closedTradesChronological.length === 0) return [];

    if (periodView === 'CUMULATIVE') {
      // Point per trade
      let runPnl = 0;
      let runR = 0;
      return closedTradesChronological.map((t, idx) => {
        runPnl += t.pnl;
        runR += t.pnlR;
        const d = new Date((t.closeTime || t.openTime) * 1000);
        const label = `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} (#${t.ticket})`;
        return {
          period: `T${idx + 1}`,
          label,
          startDate: d.toISOString(),
          pnl: Number(t.pnl.toFixed(2)),
          pnlR: Number(t.pnlR.toFixed(2)),
          cumulativePnl: Number(runPnl.toFixed(2)),
          cumulativeR: Number(runR.toFixed(2)),
          trades: 1,
          wins: t.pnl > 0 ? 1 : 0,
          losses: t.pnl < 0 ? 1 : 0,
          winRate: t.pnl > 0 ? 100 : 0
        };
      });
    }

    // Helper: get year & week number
    const getWeekKey = (d: Date) => {
      const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
      date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
      const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
      const weekNo = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
      return `${date.getUTCFullYear()}-W${weekNo.toString().padStart(2, '0')}`;
    };

    // Helper: get month key
    const getMonthKey = (d: Date) => {
      const year = d.getFullYear();
      const month = (d.getMonth() + 1).toString().padStart(2, '0');
      return `${year}-${month}`;
    };

    const buckets = new Map<string, {
      trades: Position[];
      firstDate: Date;
      lastDate: Date;
    }>();

    closedTradesChronological.forEach(trade => {
      const d = new Date((trade.closeTime || trade.openTime) * 1000);
      const key = periodView === 'WEEKLY' ? getWeekKey(d) : getMonthKey(d);

      if (!buckets.has(key)) {
        buckets.set(key, { trades: [], firstDate: d, lastDate: d });
      }
      const b = buckets.get(key)!;
      b.trades.push(trade);
      if (d < b.firstDate) b.firstDate = d;
      if (d > b.lastDate) b.lastDate = d;
    });

    // Sort buckets by chronological key
    const sortedKeys = Array.from(buckets.keys()).sort();
    let cumulativePnl = 0;
    let cumulativeR = 0;

    return sortedKeys.map(key => {
      const b = buckets.get(key)!;
      let periodPnl = 0;
      let periodR = 0;
      let wins = 0;
      let losses = 0;

      b.trades.forEach(t => {
        periodPnl += t.pnl;
        periodR += t.pnlR;
        if (t.pnl > 0.01) wins++;
        else if (t.pnl < -0.01) losses++;
      });

      cumulativePnl += periodPnl;
      cumulativeR += periodR;

      let label = key;
      if (periodView === 'WEEKLY') {
        const startStr = b.firstDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        const endStr = b.lastDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        label = `${key.split('-')[1]} (${startStr} - ${endStr})`;
      } else {
        label = b.firstDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      }

      return {
        period: key,
        label,
        startDate: b.firstDate.toLocaleDateString('en-US'),
        endDate: b.lastDate.toLocaleDateString('en-US'),
        pnl: Number(periodPnl.toFixed(2)),
        pnlR: Number(periodR.toFixed(2)),
        cumulativePnl: Number(cumulativePnl.toFixed(2)),
        cumulativeR: Number(cumulativeR.toFixed(2)),
        trades: b.trades.length,
        wins,
        losses,
        winRate: b.trades.length > 0 ? Number(((wins / b.trades.length) * 100).toFixed(1)) : 0
      };
    });
  }, [closedTradesChronological, periodView]);

  // Strategy performance breakdown
  const strategyBreakdown = useMemo(() => {
    const map = new Map<string, {
      trades: number;
      wins: number;
      losses: number;
      pnl: number;
      pnlR: number;
    }>();

    closedTradesChronological.forEach(t => {
      const strat = t.strategyId || 'UNKNOWN';
      if (!map.has(strat)) {
        map.set(strat, { trades: 0, wins: 0, losses: 0, pnl: 0, pnlR: 0 });
      }
      const s = map.get(strat)!;
      s.trades++;
      s.pnl += t.pnl;
      s.pnlR += t.pnlR;
      if (t.pnl > 0.01) s.wins++;
      else if (t.pnl < -0.01) s.losses++;
    });

    return Array.from(map.entries()).map(([strategyId, data]) => ({
      strategyId,
      trades: data.trades,
      wins: data.wins,
      losses: data.losses,
      winRate: data.trades > 0 ? (data.wins / data.trades) * 100 : 0,
      pnl: data.pnl,
      pnlR: data.pnlR
    })).sort((a, b) => b.pnl - a.pnl);
  }, [closedTradesChronological]);

  // Unique symbols and strategies for filtering
  const availableStrategies = useMemo(() => {
    const set = new Set<string>();
    closedTradesChronological.forEach(t => {
      if (t.strategyId) set.add(t.strategyId);
    });
    return Array.from(set);
  }, [closedTradesChronological]);

  const availableSymbols = useMemo(() => {
    const set = new Set<string>();
    closedTradesChronological.forEach(t => {
      if (t.symbol) set.add(t.symbol);
    });
    return Array.from(set);
  }, [closedTradesChronological]);

  // Filtered closed trades for the journal list
  const filteredTrades = useMemo(() => {
    return closedTradesNewestFirst.filter(trade => {
      // Search query (ticket, symbol, strategy, or notes)
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchTicket = trade.ticket.toString().includes(query);
        const matchSymbol = trade.symbol.toLowerCase().includes(query);
        const matchStrategy = trade.strategyId.toLowerCase().includes(query);
        const matchNotes = trade.journalNotes?.some(n => n.toLowerCase().includes(query));
        if (!matchTicket && !matchSymbol && !matchStrategy && !matchNotes) {
          return false;
        }
      }

      // Strategy filter
      if (strategyFilter !== 'ALL' && trade.strategyId !== strategyFilter) {
        return false;
      }

      // Symbol filter
      if (symbolFilter !== 'ALL' && trade.symbol !== symbolFilter) {
        return false;
      }

      // Outcome filter
      if (outcomeFilter === 'WIN' && trade.pnl <= 0.01) return false;
      if (outcomeFilter === 'LOSS' && trade.pnl >= -0.01) return false;
      if (outcomeFilter === 'BREAKEVEN' && Math.abs(trade.pnl) > 0.01) return false;

      return true;
    });
  }, [closedTradesNewestFirst, searchQuery, strategyFilter, symbolFilter, outcomeFilter]);

  // Note submission handler
  const handleAddNoteSubmit = async (ticket: number) => {
    const text = newNoteText[ticket]?.trim();
    if (!text || isSavingNote) return;

    try {
      setIsSavingNote(true);
      if (onSaveNote) {
        await onSaveNote(ticket, text);
      }
      setNewNoteText(prev => ({ ...prev, [ticket]: '' }));
    } catch (err) {
      console.error('Failed to save journal note', err);
    } finally {
      setIsSavingNote(false);
    }
  };

  return (
    <div className="flex flex-col gap-6" id="trade-journal-container">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <LineChartIcon className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                <span>Deterministic Trade Journal & PnL Growth</span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  Weekly & Monthly Progress
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Institutional performance analytics tracking weekly/monthly equity progression, R-multiples, and post-trade reflections.
              </p>
            </div>
          </div>
        </div>

        {/* Quick Summary Pill */}
        <div className="flex items-center gap-3 bg-slate-950 px-4 py-2.5 rounded-xl border border-slate-800 font-mono">
          <div className="text-right">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Net Realized PnL</span>
            <div className="flex items-center gap-1.5">
              <span className={`text-base font-bold ${kpiStats.totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {kpiStats.totalPnl >= 0 ? '+' : ''}${kpiStats.totalPnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${kpiStats.totalR >= 0 ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
                {kpiStats.totalR >= 0 ? '+' : ''}{kpiStats.totalR.toFixed(2)}R
              </span>
            </div>
          </div>
          <div className="w-9 h-9 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-cyan-400" />
          </div>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 font-mono">
        {/* Card 1: Total Realized PnL */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider block">Total Realized</span>
          <div className={`text-lg font-bold ${kpiStats.totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {kpiStats.totalPnl >= 0 ? '+' : ''}${kpiStats.totalPnl.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-400">
            Composite: <span className="text-cyan-300 font-semibold">{kpiStats.totalR >= 0 ? '+' : ''}{kpiStats.totalR.toFixed(2)}R</span>
          </div>
        </div>

        {/* Card 2: Win Rate */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider block">Win Rate</span>
          <div className="text-lg font-bold text-slate-100 flex items-center gap-1.5">
            <span>{kpiStats.winRate.toFixed(1)}%</span>
            <span className="text-[11px] text-slate-400 font-normal">({kpiStats.wins}W / {kpiStats.losses}L)</span>
          </div>
          <div className="text-[11px] text-slate-400">
            Total Trades: <span className="text-slate-200 font-semibold">{closedTradesChronological.length}</span>
          </div>
        </div>

        {/* Card 3: Profit Factor */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider block">Profit Factor</span>
          <div className="text-lg font-bold text-emerald-400">
            {kpiStats.profitFactor.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-400">
            Gross: <span className="text-emerald-400 font-semibold">+${kpiStats.grossProfit.toFixed(0)}</span>
          </div>
        </div>

        {/* Card 4: Expectancy / Avg R */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider block">Expectancy</span>
          <div className={`text-lg font-bold ${kpiStats.avgR >= 0 ? 'text-cyan-400' : 'text-rose-400'}`}>
            {kpiStats.avgR >= 0 ? '+' : ''}{kpiStats.avgR.toFixed(2)}R / trade
          </div>
          <div className="text-[11px] text-slate-400">
            Asymmetric 5R Target
          </div>
        </div>

        {/* Card 5: Max Drawdown */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider block">Max Drawdown</span>
          <div className="text-lg font-bold text-amber-400">
            -{kpiStats.maxDrawdownPct.toFixed(1)}%
          </div>
          <div className="text-[11px] text-slate-400">
            Depth: <span className="text-rose-400 font-semibold">-${kpiStats.maxDrawdownPnl.toFixed(2)}</span>
          </div>
        </div>

        {/* Card 6: Best Trade */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider block">Best Trade</span>
          <div className="text-lg font-bold text-emerald-400">
            +${kpiStats.bestTradePnl.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-400">
            Worst: <span className="text-rose-400 font-semibold">${kpiStats.worstTradePnl.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Main Section: PnL Growth Line Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
        {/* Chart Controls Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-400">Aggregation Period:</span>
            <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 font-mono text-xs gap-1">
              <button
                type="button"
                id="btn-period-weekly"
                onClick={() => setPeriodView('WEEKLY')}
                className={`px-3 py-1 rounded-md font-bold transition ${
                  periodView === 'WEEKLY'
                    ? 'bg-cyan-500 text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Weekly Growth
              </button>
              <button
                type="button"
                id="btn-period-monthly"
                onClick={() => setPeriodView('MONTHLY')}
                className={`px-3 py-1 rounded-md font-bold transition ${
                  periodView === 'MONTHLY'
                    ? 'bg-cyan-500 text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Monthly Growth
              </button>
              <button
                type="button"
                id="btn-period-cumulative"
                onClick={() => setPeriodView('CUMULATIVE')}
                className={`px-3 py-1 rounded-md font-bold transition ${
                  periodView === 'CUMULATIVE'
                    ? 'bg-cyan-500 text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Trade-by-Trade
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Metric Toggle: USD vs R */}
            <div className="flex items-center gap-1.5 font-mono text-xs">
              <span className="text-slate-400">Units:</span>
              <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 gap-1">
                <button
                  type="button"
                  id="btn-metric-usd"
                  onClick={() => setMetricView('USD')}
                  className={`px-2.5 py-0.5 rounded text-xs font-bold transition ${
                    metricView === 'USD'
                      ? 'bg-emerald-500 text-slate-950'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  USD ($)
                </button>
                <button
                  type="button"
                  id="btn-metric-r"
                  onClick={() => setMetricView('R_MULTIPLE')}
                  className={`px-2.5 py-0.5 rounded text-xs font-bold transition ${
                    metricView === 'R_MULTIPLE'
                      ? 'bg-cyan-500 text-slate-950'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  R-Multiple (R)
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Recharts Line Chart Canvas */}
        <div className="h-[340px] w-full pt-2">
          {aggregatedData.length === 0 ? (
            <div className="h-full flex items-center justify-center font-mono text-xs text-slate-500">
              No closed trade records available for PnL growth projection.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={aggregatedData}
                margin={{ top: 15, right: 30, left: 10, bottom: 25 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke="#64748b"
                  fontSize={11}
                  fontFamily="monospace"
                  tickLine={false}
                  angle={-15}
                  textAnchor="end"
                  height={45}
                />
                <YAxis
                  stroke="#64748b"
                  fontSize={11}
                  fontFamily="monospace"
                  tickLine={false}
                  tickFormatter={val =>
                    metricView === 'USD'
                      ? `$${val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val}`
                      : `${val}R`
                  }
                />
                <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                <RechartsTooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as AggregatedPnlPoint;
                      return (
                        <div className="bg-slate-950 border border-slate-700 p-3.5 rounded-xl shadow-2xl font-mono text-xs space-y-2 min-w-[220px]">
                          <div className="text-slate-300 font-bold border-b border-slate-800 pb-1.5 flex justify-between items-center">
                            <span>{data.label}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                              {data.trades} trade{data.trades !== 1 ? 's' : ''}
                            </span>
                          </div>
                          <div className="space-y-1 text-[11px]">
                            <div className="flex justify-between items-center">
                              <span className="text-slate-400">Period PnL:</span>
                              <span className={`font-bold ${data.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)} ({data.pnlR >= 0 ? '+' : ''}{data.pnlR.toFixed(2)}R)
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-slate-400">Cumulative PnL:</span>
                              <span className={`font-bold ${data.cumulativePnl >= 0 ? 'text-cyan-400' : 'text-rose-400'}`}>
                                {data.cumulativePnl >= 0 ? '+' : ''}${data.cumulativePnl.toFixed(2)} ({data.cumulativeR >= 0 ? '+' : ''}{data.cumulativeR.toFixed(2)}R)
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-slate-400">Win Rate:</span>
                              <span className="text-slate-200 font-semibold">
                                {data.winRate}% ({data.wins}W - {data.losses}L)
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Legend
                  verticalAlign="top"
                  align="right"
                  wrapperStyle={{ paddingBottom: '10px', fontSize: '11px', fontFamily: 'monospace' }}
                />
                {/* Period realized PnL Line */}
                <Line
                  type="monotone"
                  dataKey={metricView === 'USD' ? 'pnl' : 'pnlR'}
                  name={metricView === 'USD' ? 'Period Realized ($)' : 'Period Realized (R)'}
                  stroke="#a855f7"
                  strokeWidth={2}
                  dot={{ r: 3.5, fill: '#a855f7', strokeWidth: 1, stroke: '#0f172a' }}
                  activeDot={{ r: 6, fill: '#d8b4fe' }}
                />
                {/* Cumulative Growth Line */}
                <Line
                  type="monotone"
                  dataKey={metricView === 'USD' ? 'cumulativePnl' : 'cumulativeR'}
                  name={metricView === 'USD' ? 'Cumulative Growth ($)' : 'Cumulative Growth (R)'}
                  stroke="#10b981"
                  strokeWidth={3}
                  dot={{ r: 4.5, fill: '#10b981', strokeWidth: 1.5, stroke: '#0f172a' }}
                  activeDot={{ r: 7, fill: '#34d399' }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Secondary Row: Strategy Attribution & Day Performance Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Strategy Performance Matrix (2 cols on lg) */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md space-y-3 font-mono">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <span>Strategy Attribution & Progress Breakdown</span>
            </h3>
            <span className="text-xs text-slate-400">
              {strategyBreakdown.length} Registered Strategies
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="pb-2 font-semibold">Strategy Contract</th>
                  <th className="pb-2 font-semibold text-center">Trades</th>
                  <th className="pb-2 font-semibold text-center">Win Rate</th>
                  <th className="pb-2 font-semibold text-right">Net R</th>
                  <th className="pb-2 font-semibold text-right">Realized ($)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {strategyBreakdown.map(s => (
                  <tr key={s.strategyId} className="hover:bg-slate-800/30 transition">
                    <td className="py-2.5 font-bold text-slate-200">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-cyan-400" />
                        <span>{s.strategyId}</span>
                      </div>
                    </td>
                    <td className="py-2.5 text-center text-slate-300">
                      {s.trades} <span className="text-slate-500 text-[10px]">({s.wins}W / {s.losses}L)</span>
                    </td>
                    <td className="py-2.5 text-center">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                        s.winRate >= 60 ? 'bg-emerald-500/20 text-emerald-300' :
                        s.winRate >= 40 ? 'bg-amber-500/20 text-amber-300' :
                        'bg-rose-500/20 text-rose-300'
                      }`}>
                        {s.winRate.toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-bold text-cyan-300">
                      {s.pnlR >= 0 ? '+' : ''}{s.pnlR.toFixed(2)}R
                    </td>
                    <td className={`py-2.5 text-right font-bold ${s.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {s.pnl >= 0 ? '+' : ''}${s.pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick Rules & Progress Guard Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md space-y-3 font-mono text-xs">
          <div className="flex items-center gap-2 text-slate-200 font-bold">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Deterministic Journaling Discipline</span>
          </div>

          <p className="text-slate-400 leading-relaxed text-[11px]">
            Every session trade proposal executes with pre-defined risk boundaries. Closed trade reflections ensure strict adherence to systematic rules:
          </p>

          <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 text-[11px]">
            <div className="flex items-start gap-2 text-slate-300">
              <span className="text-emerald-400 font-bold">• Asymmetric R:</span>
              <span>75% bank at opposite session boundary; 25% trailing runner targeting 5.0R.</span>
            </div>
            <div className="flex items-start gap-2 text-slate-300">
              <span className="text-cyan-400 font-bold">• Risk Guard:</span>
              <span>1.0% maximum account risk per execution, max 2R daily loss guard.</span>
            </div>
            <div className="flex items-start gap-2 text-slate-300">
              <span className="text-amber-400 font-bold">• Reflection Notes:</span>
              <span>Mandatory review of liquidity sweep validity, displacement, and time cutoff.</span>
            </div>
          </div>
        </div>
      </div>

      {/* Filter & Search Bar for Trade Journal Log */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-md space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100 font-mono">
              Closed Trade Log & Reflections ({filteredTrades.length} of {closedTradesChronological.length})
            </h3>
          </div>

          {/* Quick reset filters button */}
          {(searchQuery || strategyFilter !== 'ALL' || symbolFilter !== 'ALL' || outcomeFilter !== 'ALL') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setStrategyFilter('ALL');
                setSymbolFilter('ALL');
                setOutcomeFilter('ALL');
              }}
              className="text-xs font-mono text-slate-400 hover:text-slate-200 flex items-center gap-1 transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset Filters</span>
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              id="input-journal-search"
              placeholder="Search ticket, symbol, notes..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
            />
          </div>

          {/* Strategy Filter */}
          <div>
            <select
              id="select-journal-strategy"
              value={strategyFilter}
              onChange={e => setStrategyFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 transition"
            >
              <option value="ALL">All Strategies</option>
              {availableStrategies.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Symbol Filter */}
          <div>
            <select
              id="select-journal-symbol"
              value={symbolFilter}
              onChange={e => setSymbolFilter(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 transition"
            >
              <option value="ALL">All Pairs / Assets</option>
              {availableSymbols.map(sym => (
                <option key={sym} value={sym}>{sym}</option>
              ))}
            </select>
          </div>

          {/* Outcome Filter */}
          <div>
            <select
              id="select-journal-outcome"
              value={outcomeFilter}
              onChange={e => setOutcomeFilter(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 transition"
            >
              <option value="ALL">All Outcomes</option>
              <option value="WIN">Winning Trades (&gt; 0)</option>
              <option value="LOSS">Losing Trades (&lt; 0)</option>
              <option value="BREAKEVEN">Breakeven Trades (0)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Trade Journal Table List */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg font-mono">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
                <th className="py-3 px-4 font-semibold">Date & Time</th>
                <th className="py-3 px-4 font-semibold">Ticket</th>
                <th className="py-3 px-4 font-semibold">Asset & Side</th>
                <th className="py-3 px-4 font-semibold">Strategy</th>
                <th className="py-3 px-4 font-semibold text-right">Volume</th>
                <th className="py-3 px-4 font-semibold text-right">Entry / Exit</th>
                <th className="py-3 px-4 font-semibold text-right">Realized Return</th>
                <th className="py-3 px-4 font-semibold text-center">Reflections</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredTrades.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500 text-xs">
                    No closed trade records match the specified filters.
                  </td>
                </tr>
              ) : (
                filteredTrades.map(trade => {
                  const isExpanded = expandedTicket === trade.ticket;
                  const closeDate = new Date((trade.closeTime || trade.openTime) * 1000);
                  const formattedDate = closeDate.toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  });
                  const formattedTime = closeDate.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false
                  });

                  return (
                    <React.Fragment key={trade.ticket}>
                      <tr
                        className={`hover:bg-slate-800/40 transition cursor-pointer ${
                          isExpanded ? 'bg-slate-800/30' : ''
                        }`}
                        onClick={() => setExpandedTicket(isExpanded ? null : trade.ticket)}
                      >
                        {/* Date & Time */}
                        <td className="py-3 px-4 text-slate-300">
                          <div>{formattedDate}</div>
                          <div className="text-[10px] text-slate-500">{formattedTime} UTC</div>
                        </td>

                        {/* Ticket */}
                        <td className="py-3 px-4 font-bold text-cyan-400">
                          #{trade.ticket}
                        </td>

                        {/* Symbol & Side */}
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-200">{trade.symbol}</span>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              trade.side === 'BUY'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            }`}>
                              {trade.side}
                            </span>
                          </div>
                        </td>

                        {/* Strategy */}
                        <td className="py-3 px-4 text-slate-300 text-[11px]">
                          {trade.strategyId}
                        </td>

                        {/* Volume */}
                        <td className="py-3 px-4 text-right text-slate-300">
                          {trade.volume.toFixed(2)} lots
                        </td>

                        {/* Entry / Exit */}
                        <td className="py-3 px-4 text-right">
                          <div className="text-slate-200">{trade.entryPrice.toFixed(trade.symbol.includes('JPY') ? 3 : 5)}</div>
                          <div className="text-[10px] text-slate-400">{trade.currentPrice.toFixed(trade.symbol.includes('JPY') ? 3 : 5)}</div>
                        </td>

                        {/* Realized Return */}
                        <td className="py-3 px-4 text-right">
                          <div className={`font-bold ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                          </div>
                          <div className={`text-[10px] font-semibold ${trade.pnlR >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {trade.pnlR >= 0 ? '+' : ''}{trade.pnlR.toFixed(2)}R
                          </div>
                        </td>

                        {/* Notes toggle pill */}
                        <td className="py-3 px-4 text-center" onClick={e => e.stopPropagation()}>
                          <button
                            type="button"
                            onClick={() => setExpandedTicket(isExpanded ? null : trade.ticket)}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 text-[11px] transition"
                          >
                            <span>{trade.journalNotes?.length || 0} Notes</span>
                            {isExpanded ? (
                              <ChevronUp className="w-3.5 h-3.5 text-cyan-400" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                            )}
                          </button>
                        </td>
                      </tr>

                      {/* Expandable Journal Notes & Reflections Section */}
                      {isExpanded && (
                        <tr className="bg-slate-950/80 border-b border-slate-800">
                          <td colSpan={8} className="p-4 space-y-3">
                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
                              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                                <span className="font-bold text-cyan-400 text-xs flex items-center gap-2">
                                  <FileText className="w-4 h-4" />
                                  <span>Trade Reflection Notes — Ticket #{trade.ticket} ({trade.symbol} {trade.side})</span>
                                </span>
                                <div className="text-[11px] text-slate-400">
                                  Outcome: <span className={trade.pnl >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                                    {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)} ({trade.pnlR >= 0 ? '+' : ''}{trade.pnlR.toFixed(2)}R)
                                  </span>
                                </div>
                              </div>

                              {/* Existing Notes List */}
                              <div className="space-y-2">
                                {trade.journalNotes && trade.journalNotes.length > 0 ? (
                                  trade.journalNotes.map((note, nIdx) => (
                                    <div
                                      key={nIdx}
                                      className="flex items-start justify-between gap-3 bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 text-xs"
                                    >
                                      <div className="flex items-start gap-2 text-slate-300">
                                        <span className="text-cyan-500 font-bold">•</span>
                                        <span className="leading-relaxed">{note}</span>
                                      </div>
                                      {onDeleteNote && (
                                        <button
                                          type="button"
                                          title="Delete note"
                                          onClick={() => onDeleteNote(trade.ticket, nIdx)}
                                          className="text-slate-500 hover:text-rose-400 p-1 transition shrink-0"
                                        >
                                          <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                      )}
                                    </div>
                                  ))
                                ) : (
                                  <p className="text-xs text-slate-500 italic">No notes recorded yet for this trade.</p>
                                )}
                              </div>

                              {/* Add Note Input Field */}
                              <div className="pt-2 flex gap-2">
                                <input
                                  type="text"
                                  placeholder="Add reflection or review observation..."
                                  value={newNoteText[trade.ticket] || ''}
                                  onChange={e => setNewNoteText({ ...newNoteText, [trade.ticket]: e.target.value })}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter') handleAddNoteSubmit(trade.ticket);
                                  }}
                                  className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                                />
                                <button
                                  type="button"
                                  disabled={!newNoteText[trade.ticket]?.trim() || isSavingNote}
                                  onClick={() => handleAddNoteSubmit(trade.ticket)}
                                  className="px-3 py-1.5 bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-bold text-xs rounded-lg transition flex items-center gap-1.5 shadow"
                                >
                                  <Plus className="w-3.5 h-3.5" />
                                  <span>Add Note</span>
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
