import React, { useState, useMemo } from 'react';
import { Position } from '../../types/trading';
import {
  Activity,
  Search,
  X,
  RotateCcw,
  SlidersHorizontal,
  ChevronRight,
  FileText,
  Plus,
  Trash2,
  Send,
  Sparkles,
  MessageSquareQuote,
  Check
} from 'lucide-react';

interface LiveManagedPositionsWidgetProps {
  positions: Position[];
  onManagePosition?: (ticket: number, action: 'BREAKEVEN' | 'PARTIAL_CLOSE' | 'CLOSE') => void;
  onAddNote?: (ticket: number, note: string) => void;
  onDeleteNote?: (ticket: number, noteIndex: number) => void;
  onOpenExecutionCockpit: () => void;
  onSelectSymbol?: (symbol: string) => void;
}

const QUICK_TAG_SUGGESTIONS = [
  'London Sweep',
  'SL Trailed to BE',
  'High-Impact News',
  'TP1 Partial 75%',
  'Key 15M OB',
  'FVG Retest'
];

export const LiveManagedPositionsWidget: React.FC<LiveManagedPositionsWidgetProps> = ({
  positions,
  onManagePosition,
  onAddNote,
  onDeleteNote,
  onOpenExecutionCockpit,
  onSelectSymbol
}) => {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sideFilter, setSideFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [pnlFilter, setPnlFilter] = useState<'ALL' | 'PROFIT' | 'DRAWDOWN'>('ALL');
  const [sortBy, setSortBy] = useState<'NEWEST' | 'PNL_DESC' | 'PNL_ASC' | 'SYMBOL'>('NEWEST');
  const [showFilters, setShowFilters] = useState<boolean>(false);

  // Note expansion and text input per ticket
  const [expandedNoteTicket, setExpandedNoteTicket] = useState<number | null>(null);
  const [noteInputs, setNoteInputs] = useState<Record<number, string>>({});
  const [saveSuccessTicket, setSaveSuccessTicket] = useState<number | null>(null);

  // Filter only active / open positions
  const activePositions = useMemo(() => {
    return positions.filter(p => p.status !== 'CLOSED');
  }, [positions]);

  // Aggregate active metrics
  const activeMetrics = useMemo(() => {
    const totalUnrealizedPnl = activePositions.reduce((sum, p) => sum + p.pnl, 0);
    const totalUnrealizedR = activePositions.reduce((sum, p) => sum + p.pnlR, 0);
    const profitCount = activePositions.filter(p => p.pnl > 0).length;
    const lossCount = activePositions.filter(p => p.pnl < 0).length;
    return {
      totalUnrealizedPnl,
      totalUnrealizedR,
      profitCount,
      lossCount,
      count: activePositions.length
    };
  }, [activePositions]);

  // Apply search query (matches symbol, ticket, or notes text) and filters
  const filteredPositions = useMemo(() => {
    let result = activePositions.filter(p => {
      // Search matching symbol, ticket number, or journal notes
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const symbolMatch = p.symbol.toLowerCase().includes(q);
        const ticketMatch = String(p.ticket).includes(q);
        const noteMatch = (p.journalNotes || []).some(n => n.toLowerCase().includes(q));

        if (!symbolMatch && !ticketMatch && !noteMatch) {
          return false;
        }
      }

      // Side filter
      if (sideFilter !== 'ALL' && p.side !== sideFilter) {
        return false;
      }

      // PnL filter
      if (pnlFilter === 'PROFIT' && p.pnl <= 0) return false;
      if (pnlFilter === 'DRAWDOWN' && p.pnl >= 0) return false;

      return true;
    });

    // Sorting
    result = [...result].sort((a, b) => {
      if (sortBy === 'PNL_DESC') return b.pnl - a.pnl;
      if (sortBy === 'PNL_ASC') return a.pnl - b.pnl;
      if (sortBy === 'SYMBOL') return a.symbol.localeCompare(b.symbol);
      // NEWEST: by openTime descending or ticket descending
      return (b.openTime || Number(b.ticket)) - (a.openTime || Number(a.ticket));
    });

    return result;
  }, [activePositions, searchQuery, sideFilter, pnlFilter, sortBy]);

  const hasActiveFilters = searchQuery.trim() !== '' || sideFilter !== 'ALL' || pnlFilter !== 'ALL';

  const handleResetFilters = () => {
    setSearchQuery('');
    setSideFilter('ALL');
    setPnlFilter('ALL');
    setSortBy('NEWEST');
  };

  const handleToggleNotes = (ticket: number) => {
    setExpandedNoteTicket(prev => (prev === ticket ? null : ticket));
  };

  const handleSaveNote = (ticket: number) => {
    const text = (noteInputs[ticket] || '').trim();
    if (!text) return;

    if (onAddNote) {
      onAddNote(ticket, text);
    }

    // Clear input
    setNoteInputs(prev => ({ ...prev, [ticket]: '' }));
    setSaveSuccessTicket(ticket);
    setTimeout(() => setSaveSuccessTicket(null), 2000);
  };

  const handleAddQuickTag = (ticket: number, tag: string) => {
    const current = noteInputs[ticket] || '';
    const updated = current ? `${current} [${tag}]` : `[${tag}]`;
    setNoteInputs(prev => ({ ...prev, [ticket]: updated }));
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md space-y-3.5">
      {/* Header & Quick Summary */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-cyan-500/10 border border-cyan-500/30 rounded-lg text-cyan-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono flex items-center gap-1.5">
              <span>Live Managed Positions</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 font-bold border border-slate-700">
                {activePositions.length} Active
              </span>
            </h3>
          </div>
        </div>

        {/* Live Unrealized PnL badge */}
        {activePositions.length > 0 && (
          <div className="text-right font-mono">
            <div className={`text-xs font-bold ${activeMetrics.totalUnrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {activeMetrics.totalUnrealizedPnl >= 0 ? `+$${activeMetrics.totalUnrealizedPnl.toFixed(2)}` : `-$${Math.abs(activeMetrics.totalUnrealizedPnl).toFixed(2)}`}
            </div>
            <div className="text-[10px] text-slate-500">
              {activeMetrics.totalUnrealizedR >= 0 ? `+${activeMetrics.totalUnrealizedR.toFixed(2)}R` : `${activeMetrics.totalUnrealizedR.toFixed(2)}R`} total
            </div>
          </div>
        )}
      </div>

      {/* Search & Filter Bar */}
      <div className="space-y-2 font-mono">
        {/* Search Input Box */}
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none text-slate-400">
            <Search className="w-3.5 h-3.5" />
          </div>
          <input
            id="positions-search-input"
            type="text"
            placeholder="Search by symbol, ticket #, or notes..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-16 py-1.5 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
          />

          <div className="absolute inset-y-0 right-0 pr-1.5 flex items-center gap-1">
            {searchQuery && (
              <button
                id="positions-search-clear"
                onClick={() => setSearchQuery('')}
                className="p-1 text-slate-500 hover:text-slate-300 rounded"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              id="positions-toggle-filters"
              onClick={() => setShowFilters(!showFilters)}
              className={`p-1 rounded transition border ${
                showFilters || hasActiveFilters
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
              title="Toggle filter options"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Quick Filter Options */}
        {(showFilters || hasActiveFilters) && (
          <div className="bg-slate-950/80 p-2.5 rounded-lg border border-slate-800/80 space-y-2 text-[11px]">
            <div className="flex flex-wrap items-center justify-between gap-1.5 text-slate-400">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Filter Direction:</span>
              <div className="flex items-center gap-1">
                {(['ALL', 'BUY', 'SELL'] as const).map(s => (
                  <button
                    key={s}
                    id={`pos-filter-side-${s.toLowerCase()}`}
                    onClick={() => setSideFilter(s)}
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                      sideFilter === s
                        ? s === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : s === 'SELL'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : 'bg-slate-800 text-slate-200 border border-slate-700'
                        : 'bg-slate-900 text-slate-500 hover:text-slate-300 border border-transparent'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-1.5 text-slate-400">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">P&L Status:</span>
              <div className="flex items-center gap-1">
                <button
                  id="pos-filter-pnl-all"
                  onClick={() => setPnlFilter('ALL')}
                  className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                    pnlFilter === 'ALL'
                      ? 'bg-slate-800 text-slate-200 border border-slate-700'
                      : 'bg-slate-900 text-slate-500 hover:text-slate-300 border border-transparent'
                  }`}
                >
                  All
                </button>
                <button
                  id="pos-filter-pnl-profit"
                  onClick={() => setPnlFilter('PROFIT')}
                  className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                    pnlFilter === 'PROFIT'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-slate-900 text-slate-500 hover:text-slate-300 border border-transparent'
                  }`}
                >
                  Profit ({activeMetrics.profitCount})
                </button>
                <button
                  id="pos-filter-pnl-drawdown"
                  onClick={() => setPnlFilter('DRAWDOWN')}
                  className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                    pnlFilter === 'DRAWDOWN'
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-slate-900 text-slate-500 hover:text-slate-300 border border-transparent'
                  }`}
                >
                  Drawdown ({activeMetrics.lossCount})
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-1.5 text-slate-400 pt-1 border-t border-slate-900">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Sort By:</span>
              <select
                id="pos-sort-select"
                value={sortBy}
                onChange={e => setSortBy(e.target.value as any)}
                className="bg-slate-900 border border-slate-800 text-cyan-300 text-[10px] rounded px-1.5 py-0.5 focus:outline-none cursor-pointer"
              >
                <option value="NEWEST">Newest First</option>
                <option value="PNL_DESC">Highest PnL</option>
                <option value="PNL_ASC">Lowest PnL</option>
                <option value="SYMBOL">Symbol (A-Z)</option>
              </select>
            </div>

            {hasActiveFilters && (
              <div className="flex items-center justify-between pt-1 border-t border-slate-900 text-[10px]">
                <span className="text-cyan-400">
                  Showing {filteredPositions.length} of {activePositions.length}
                </span>
                <button
                  id="pos-reset-filters"
                  onClick={handleResetFilters}
                  className="text-rose-400 hover:text-rose-300 flex items-center gap-1 font-semibold"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Reset filters</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Position List */}
      <div className="space-y-2.5 font-mono text-xs max-h-[380px] overflow-y-auto pr-1">
        {filteredPositions.map(pos => {
          const isProfitable = pos.pnl >= 0;
          const isNoteExpanded = expandedNoteTicket === pos.ticket;
          const notesCount = (pos.journalNotes || []).length;
          const currentNoteText = noteInputs[pos.ticket] || '';

          return (
            <div
              key={pos.ticket}
              className={`bg-slate-950 p-3 rounded-lg border transition space-y-2.5 ${
                isNoteExpanded ? 'border-cyan-500/50 shadow-md shadow-cyan-950/20' : 'border-slate-800/80 hover:border-slate-700'
              }`}
            >
              {/* Row 1: Header with Symbol, Ticket, Side, PnL */}
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-1.5">
                    {onSelectSymbol ? (
                      <button
                        onClick={() => onSelectSymbol(pos.symbol)}
                        className="font-bold text-cyan-300 hover:text-cyan-200 transition underline-offset-2 hover:underline"
                        title={`View ${pos.symbol} on chart`}
                      >
                        {pos.symbol}
                      </button>
                    ) : (
                      <span className="font-bold text-slate-200">{pos.symbol}</span>
                    )}
                    <span className="text-[10px] text-slate-500">#{pos.ticket}</span>
                    {pos.isBreakevenMoved && (
                      <span className="px-1 py-0.2 bg-amber-500/20 text-amber-300 text-[9px] rounded font-bold border border-amber-500/30">
                        BE
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 flex items-center gap-1.5 mt-0.5">
                    <span
                      className={`px-1 rounded text-[10px] font-bold ${
                        pos.side === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}
                    >
                      {pos.side}
                    </span>
                    <span>{pos.volume} Lots @ {pos.entryPrice.toFixed(5)}</span>
                  </div>
                </div>

                <div className="text-right">
                  <div className={isProfitable ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {isProfitable ? `+$${pos.pnl.toFixed(2)}` : `-$${Math.abs(pos.pnl).toFixed(2)}`}
                  </div>
                  <div className="text-[10px] text-slate-500">
                    {pos.pnlR >= 0 ? `+${pos.pnlR.toFixed(2)}R` : `${pos.pnlR.toFixed(2)}R`}
                  </div>
                </div>
              </div>

              {/* Row 2: Target Levels & Controls (BE, Close, Notes Toggle) */}
              <div className="flex items-center justify-between pt-1.5 border-t border-slate-900 text-[10px] text-slate-400">
                <div className="flex items-center gap-2">
                  <span>SL: <strong className={pos.isBreakevenMoved ? 'text-amber-400' : 'text-slate-300'}>{pos.stopLoss.toFixed(5)}</strong></span>
                  <span>TP1: <strong className="text-emerald-400">{pos.takeProfit1.toFixed(5)}</strong></span>
                </div>

                <div className="flex items-center gap-1.5">
                  {/* Note Toggle Button */}
                  <button
                    id={`pos-note-btn-${pos.ticket}`}
                    onClick={() => handleToggleNotes(pos.ticket)}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 transition ${
                      isNoteExpanded
                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                        : notesCount > 0
                        ? 'bg-slate-800 text-cyan-300 border border-slate-700 hover:border-slate-600'
                        : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                    }`}
                    title="View & add trade journal notes"
                  >
                    <FileText className="w-3 h-3 text-cyan-400" />
                    <span>{notesCount > 0 ? `${notesCount} Note${notesCount > 1 ? 's' : ''}` : '+ Note'}</span>
                  </button>

                  {onManagePosition && (
                    <>
                      {!pos.isBreakevenMoved && (
                        <button
                          onClick={() => onManagePosition(pos.ticket, 'BREAKEVEN')}
                          className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 text-[10px] font-semibold transition"
                          title="Move Stop Loss to Break-Even"
                        >
                          BE
                        </button>
                      )}
                      <button
                        onClick={() => onManagePosition(pos.ticket, 'CLOSE')}
                        className="px-1.5 py-0.5 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-800 text-rose-300 text-[10px] font-semibold transition"
                        title="Close this position immediately"
                      >
                        Close
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Row 3: Persisted Notes & Interactive Note Editor Panel */}
              {isNoteExpanded && (
                <div className="pt-2 border-t border-slate-900/80 space-y-2 bg-slate-900/60 p-2.5 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-[10px] font-bold text-cyan-400 uppercase tracking-wide">
                      <MessageSquareQuote className="w-3.5 h-3.5" />
                      <span>Trade Notes & Journal (Ticket #{pos.ticket})</span>
                    </div>
                    {saveSuccessTicket === pos.ticket && (
                      <span className="text-[10px] text-emerald-400 flex items-center gap-1 font-semibold animate-pulse">
                        <Check className="w-3 h-3" />
                        Saved!
                      </span>
                    )}
                  </div>

                  {/* List of existing persisted notes */}
                  {pos.journalNotes && pos.journalNotes.length > 0 ? (
                    <div className="space-y-1.5 max-h-[140px] overflow-y-auto pr-1">
                      {pos.journalNotes.map((note, idx) => (
                        <div
                          key={idx}
                          className="bg-slate-950/90 border border-slate-800 p-2 rounded text-[11px] text-slate-300 flex items-start justify-between gap-2 group/item"
                        >
                          <div className="flex items-start gap-1.5 flex-1 min-w-0">
                            <span className="text-cyan-500 font-bold text-[10px] mt-0.5">•</span>
                            <span className="break-words leading-relaxed text-slate-200">{note}</span>
                          </div>
                          {onDeleteNote && (
                            <button
                              onClick={() => onDeleteNote(pos.ticket, idx)}
                              className="text-slate-600 hover:text-rose-400 p-0.5 rounded opacity-60 group-hover/item:opacity-100 transition"
                              title="Delete note"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-slate-500 italic py-1">
                      No notes recorded yet for this trade ticket.
                    </p>
                  )}

                  {/* Quick Preset Tags */}
                  <div className="flex flex-wrap items-center gap-1 pt-1">
                    <span className="text-[9px] text-slate-500 flex items-center gap-1 font-semibold">
                      <Sparkles className="w-2.5 h-2.5 text-cyan-400" />
                      Quick Tags:
                    </span>
                    {QUICK_TAG_SUGGESTIONS.map(tag => (
                      <button
                        key={tag}
                        onClick={() => handleAddQuickTag(pos.ticket, tag)}
                        className="px-1.5 py-0.2 text-[9px] bg-slate-950 hover:bg-cyan-950/60 border border-slate-800 hover:border-cyan-500/40 text-slate-400 hover:text-cyan-300 rounded transition"
                      >
                        +{tag}
                      </button>
                    ))}
                  </div>

                  {/* Note Input Box & Submit */}
                  <div className="flex items-center gap-1.5 pt-1">
                    <input
                      id={`input-note-${pos.ticket}`}
                      type="text"
                      placeholder="Add short note (e.g. 'Trailed SL, waiting London high sweep')..."
                      value={currentNoteText}
                      onChange={e =>
                        setNoteInputs(prev => ({ ...prev, [pos.ticket]: e.target.value }))
                      }
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          handleSaveNote(pos.ticket);
                        }
                      }}
                      maxLength={180}
                      className="flex-1 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[11px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
                    />
                    <button
                      id={`save-note-btn-${pos.ticket}`}
                      onClick={() => handleSaveNote(pos.ticket)}
                      disabled={!currentNoteText.trim()}
                      className={`px-2.5 py-1 rounded text-[10px] font-bold flex items-center gap-1 transition ${
                        currentNoteText.trim()
                          ? 'bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm cursor-pointer'
                          : 'bg-slate-800 text-slate-500 cursor-not-allowed'
                      }`}
                      title="Save note to this position"
                    >
                      <Send className="w-3 h-3" />
                      <span>Save</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* Empty States */}
        {activePositions.length === 0 && (
          <div className="text-slate-500 text-[11px] text-center py-6 border border-dashed border-slate-800 rounded-lg">
            No active positions open
          </div>
        )}

        {activePositions.length > 0 && filteredPositions.length === 0 && (
          <div className="text-center py-5 space-y-2 border border-dashed border-slate-800 rounded-lg">
            <p className="text-slate-400 text-xs">No active trades match "{searchQuery}"</p>
            <button
              onClick={handleResetFilters}
              className="text-cyan-400 hover:text-cyan-300 text-[11px] font-semibold transition underline"
            >
              Clear search & filters
            </button>
          </div>
        )}
      </div>

      {/* Button to Open Full Execution Cockpit */}
      <button
        id="btn-open-cockpit-widget"
        onClick={onOpenExecutionCockpit}
        className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition flex items-center justify-center gap-1.5"
      >
        <span>Open Execution Cockpit</span>
        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
      </button>
    </div>
  );
};
