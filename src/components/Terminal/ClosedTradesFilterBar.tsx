import React from 'react';
import {
  Search,
  Filter,
  X,
  RotateCcw,
  SlidersHorizontal,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
  MinusCircle,
  Clock
} from 'lucide-react';
import { Position } from '../../types/trading';

export type TradeOutcomeFilter = 'ALL' | 'WIN' | 'LOSS' | 'BREAKEVEN';

export interface ClosedTradesFilterBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedSymbol: string;
  onSymbolChange: (symbol: string) => void;
  selectedOutcome: TradeOutcomeFilter;
  onOutcomeChange: (outcome: TradeOutcomeFilter) => void;
  selectedTimeframe?: string;
  onTimeframeChange?: (timeframe: string) => void;
  symbols: Array<{ symbol: string; count: number }>;
  totalClosedCount: number;
  filteredCount: number;
  onReset?: () => void;
}

/**
 * Deterministic helper to evaluate whether a closed position matches
 * the search query, symbol filter, outcome filter, side filter, and timeframe filter.
 */
export function matchesClosedTradeFilter(
  trade: Position,
  symbolFilter: string,
  outcomeFilter: TradeOutcomeFilter,
  searchQuery: string,
  sideFilter?: 'ALL' | 'LONG' | 'SHORT',
  timeframeFilter?: string
): boolean {
  // 1. Symbol Filter Dropdown
  if (symbolFilter !== 'ALL' && trade.symbol.toUpperCase() !== symbolFilter.toUpperCase()) {
    return false;
  }

  // 2. Side Filter (if applicable)
  if (sideFilter && sideFilter !== 'ALL') {
    if (sideFilter === 'LONG' && trade.side !== 'BUY') return false;
    if (sideFilter === 'SHORT' && trade.side !== 'SELL') return false;
  }

  // 3. Trade Outcome Filter Dropdown
  const isWin = trade.pnl > 0.001 || trade.pnlR > 0.01;
  const isLoss = trade.pnl < -0.001 || trade.pnlR < -0.01;
  const isBE = Math.abs(trade.pnl) <= 0.001 || Math.abs(trade.pnlR) <= 0.01;

  if (outcomeFilter === 'WIN' && !isWin) return false;
  if (outcomeFilter === 'LOSS' && !isLoss) return false;
  if (outcomeFilter === 'BREAKEVEN' && !isBE) return false;

  // 4. Timeframe / Time-Window Filter
  if (timeframeFilter && timeframeFilter !== 'ALL') {
    const tf = timeframeFilter.toUpperCase();
    const nowSec = Math.floor(Date.now() / 1000);
    const tradeTime = trade.closeTime || trade.openTime;

    if (tf === 'TODAY' || tf === '1D' || tf === '24H') {
      const oneDayAgo = nowSec - 86400;
      if (tradeTime < oneDayAgo) return false;
    } else if (tf === 'WEEK' || tf === '1W' || tf === '7D') {
      const oneWeekAgo = nowSec - 86400 * 7;
      if (tradeTime < oneWeekAgo) return false;
    } else if (tf === 'MONTH' || tf === '1M' || tf === '30D') {
      const oneMonthAgo = nowSec - 86400 * 30;
      if (tradeTime < oneMonthAgo) return false;
    } else {
      // Strategy / Execution bar timeframe (e.g. M5, M15, H1, D1)
      const matchesStratId = trade.strategyId.toUpperCase().includes(tf);
      const matchesNotes = Boolean(trade.journalNotes && trade.journalNotes.some(n => n.toUpperCase().includes(tf)));
      const tradeAnyTf = (trade as any).timeframe?.toUpperCase();
      const matchesExplicit = tradeAnyTf === tf;

      let matchesKnown = false;
      if (tf === 'M15' && (trade.strategyId.includes('ASIAN') || trade.strategyId.includes('SWEEP_RETEST') || trade.strategyId.includes('SESSION_TRADE'))) {
        matchesKnown = true;
      } else if (tf === 'M5' && trade.strategyId.includes('HIGH_RR')) {
        matchesKnown = true;
      } else if (tf === 'H1' && trade.strategyId.includes('LARGE_SMC')) {
        matchesKnown = true;
      }

      if (!matchesStratId && !matchesNotes && !matchesExplicit && !matchesKnown) {
        return false;
      }
    }
  }

  // 4. Text Search Input (search by asset name or trade outcome or ticket)
  const trimmed = searchQuery.trim().toLowerCase();
  if (trimmed) {
    // Asset / Symbol matching (e.g. 'eur', 'usd', 'eurusd', 'gbpusd')
    const symbolMatch = trade.symbol.toLowerCase().includes(trimmed);

    // Ticket matching (e.g. '9018721', '9018')
    const ticketMatch = trade.ticket.toString().includes(trimmed);

    // Direction / Side matching
    const sideMatch =
      (trade.side === 'BUY' && (trimmed === 'buy' || trimmed === 'long')) ||
      (trade.side === 'SELL' && (trimmed === 'sell' || trimmed === 'short'));

    // Strategy ID matching
    const strategyMatch = trade.strategyId.toLowerCase().includes(trimmed);

    // Outcome text keywords
    let outcomeMatch = false;
    if (
      trimmed === 'win' ||
      trimmed === 'winner' ||
      trimmed === 'wins' ||
      trimmed === 'profit' ||
      trimmed === 'profitable' ||
      trimmed === '+r' ||
      trimmed === 'green'
    ) {
      outcomeMatch = isWin;
    } else if (
      trimmed === 'loss' ||
      trimmed === 'losses' ||
      trimmed === 'loser' ||
      trimmed === 'sl' ||
      trimmed === 'stop' ||
      trimmed === '-r' ||
      trimmed === 'red'
    ) {
      outcomeMatch = isLoss;
    } else if (
      trimmed === 'be' ||
      trimmed === 'breakeven' ||
      trimmed === 'break-even' ||
      trimmed === 'even' ||
      trimmed === '0r'
    ) {
      outcomeMatch = isBE;
    } else if (trimmed === 'tp1' || trimmed === 'partial') {
      outcomeMatch =
        trade.tp1Filled ||
        Boolean(trade.journalNotes && trade.journalNotes.some(n => n.toLowerCase().includes('tp1')));
    } else if (trimmed === 'runner' || trimmed === 'tp2') {
      outcomeMatch =
        trade.pnlR >= 3.0 ||
        Boolean(trade.journalNotes && trade.journalNotes.some(n => n.toLowerCase().includes('runner')));
    }

    // Journal notes text matching
    const notesMatch = Boolean(
      trade.journalNotes && trade.journalNotes.some(n => n.toLowerCase().includes(trimmed))
    );

    // Numeric PnL or R match
    const pnlMatch =
      trade.pnl.toFixed(2).includes(trimmed) || trade.pnlR.toFixed(2).includes(trimmed);

    return (
      symbolMatch ||
      ticketMatch ||
      sideMatch ||
      strategyMatch ||
      outcomeMatch ||
      notesMatch ||
      pnlMatch
    );
  }

  return true;
}

export const ClosedTradesFilterBar: React.FC<ClosedTradesFilterBarProps> = ({
  searchQuery,
  onSearchChange,
  selectedSymbol,
  onSymbolChange,
  selectedOutcome,
  onOutcomeChange,
  selectedTimeframe = 'ALL',
  onTimeframeChange,
  symbols,
  totalClosedCount,
  filteredCount,
  onReset
}) => {
  const isFilterActive =
    searchQuery.trim().length > 0 ||
    selectedSymbol !== 'ALL' ||
    selectedOutcome !== 'ALL' ||
    selectedTimeframe !== 'ALL';

  const handleReset = () => {
    if (onReset) {
      onReset();
    } else {
      onSearchChange('');
      onSymbolChange('ALL');
      onOutcomeChange('ALL');
      if (onTimeframeChange) onTimeframeChange('ALL');
    }
  };

  return (
    <div
      id="closed-trades-filter-bar"
      className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 shadow-lg space-y-3 font-mono text-xs"
    >
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        {/* Title & Filter Icon */}
        <div className="flex items-center gap-2 text-slate-300">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <SlidersHorizontal className="w-4 h-4" />
          </div>
          <div>
            <span className="font-bold text-slate-200 tracking-wide">
              Historical Trades Filter
            </span>
            <span className="hidden sm:inline text-slate-500 text-[11px] ml-2">
              Filter closed records by asset name, outcome, ticket, or timeframe
            </span>
          </div>
        </div>

        {/* Status / Matching Indicator */}
        <div className="flex items-center gap-2 self-start lg:self-auto">
          <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-400">
            Showing <strong className="text-cyan-300 font-bold">{filteredCount}</strong> of{' '}
            <strong className="text-slate-200">{totalClosedCount}</strong>
          </span>

          {isFilterActive && (
            <button
              id="reset-closed-trades-filters"
              type="button"
              onClick={handleReset}
              className="flex items-center gap-1 px-2.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 hover:text-cyan-200 border border-slate-700 text-[11px] transition cursor-pointer"
              title="Reset all search queries, symbol, outcome, and timeframe filters"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Filter Controls: Text Search Input + Symbol Dropdown + Outcome Dropdown + Timeframe Dropdown */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-2.5 items-center pt-1 border-t border-slate-800/80">
        {/* 1. Text Search Input */}
        <div className="lg:col-span-4 relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            id="closed-trades-search-input"
            type="text"
            value={searchQuery}
            onChange={e => onSearchChange(e.target.value)}
            placeholder="Search asset, ticket, win/loss..."
            className="w-full pl-9 pr-8 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/60 transition shadow-inner"
          />
          {searchQuery && (
            <button
              id="clear-closed-trades-search"
              type="button"
              onClick={() => onSearchChange('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
              title="Clear search query"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* 2. Symbol Filter Dropdown */}
        <div className="lg:col-span-3 flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
          <Filter className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="text-slate-400 text-[11px] whitespace-nowrap">Asset:</span>
          <select
            id="closed-trades-symbol-filter-dropdown"
            value={selectedSymbol}
            onChange={e => onSymbolChange(e.target.value)}
            className="w-full bg-transparent text-cyan-300 font-semibold focus:outline-none cursor-pointer text-xs"
          >
            <option value="ALL" className="bg-slate-900 text-slate-200">
              All Assets ({totalClosedCount})
            </option>
            {symbols.map(s => (
              <option key={s.symbol} value={s.symbol} className="bg-slate-900 text-slate-200">
                {s.symbol} ({s.count})
              </option>
            ))}
          </select>
        </div>

        {/* 3. Trade Outcome Filter Dropdown */}
        <div className="lg:col-span-3 flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
          <CheckCircle2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="text-slate-400 text-[11px] whitespace-nowrap">Outcome:</span>
          <select
            id="closed-trades-outcome-filter-dropdown"
            value={selectedOutcome}
            onChange={e => onOutcomeChange(e.target.value as TradeOutcomeFilter)}
            className="w-full bg-transparent text-emerald-400 font-semibold focus:outline-none cursor-pointer text-xs"
          >
            <option value="ALL" className="bg-slate-900 text-slate-200">
              All Outcomes
            </option>
            <option value="WIN" className="bg-slate-900 text-emerald-400">
              Wins Only (+R)
            </option>
            <option value="LOSS" className="bg-slate-900 text-rose-400">
              Losses Only (-R)
            </option>
            <option value="BREAKEVEN" className="bg-slate-900 text-slate-300">
              Breakeven (0R)
            </option>
          </select>
        </div>

        {/* 4. Timeframe Filter Dropdown */}
        <div className="lg:col-span-2 flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
          <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="text-slate-400 text-[11px] whitespace-nowrap">Timeframe:</span>
          <select
            id="closed-trades-timeframe-filter-dropdown"
            value={selectedTimeframe}
            onChange={e => onTimeframeChange && onTimeframeChange(e.target.value)}
            className="w-full bg-transparent text-amber-300 font-semibold focus:outline-none cursor-pointer text-xs"
          >
            <option value="ALL" className="bg-slate-900 text-slate-200">
              All
            </option>
            <option value="TODAY" className="bg-slate-900 text-amber-300">
              Today (24h)
            </option>
            <option value="WEEK" className="bg-slate-900 text-amber-300">
              This Week
            </option>
            <option value="MONTH" className="bg-slate-900 text-amber-300">
              This Month
            </option>
            <option value="M15" className="bg-slate-900 text-cyan-300">
              M15 (Sweep)
            </option>
            <option value="M5" className="bg-slate-900 text-cyan-300">
              M5 (MSS)
            </option>
            <option value="H1" className="bg-slate-900 text-cyan-300">
              H1 (SMC)
            </option>
          </select>
        </div>
      </div>
    </div>
  );
};
