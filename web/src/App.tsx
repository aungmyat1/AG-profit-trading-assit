import React, { useState, useEffect, useMemo } from 'react';
import { Navbar } from './components/Navbar';
import { CandlestickChart } from './components/Chart/CandlestickChart';
import { SignalScanner } from './components/Scanner/SignalScanner';
import { StrategyInspector } from './components/StrategyRegistry/StrategyInspector';
import { ExecutionCockpit } from './components/Execution/ExecutionCockpit';
import { SMCConfirmationView } from './components/SMCAnalyzer/SMCConfirmationView';
import { ReplayStudio } from './components/ReplayLab/ReplayStudio';
import { AuditLogViewer } from './components/Logs/AuditLogViewer';
import { ClosedTradesSummaryCard } from './components/Terminal/ClosedTradesSummaryCard';
import {
  ClosedTradesFilterBar,
  TradeOutcomeFilter,
  matchesClosedTradeFilter
} from './components/Terminal/ClosedTradesFilterBar';
import { TradeCorrelationCard } from './components/Terminal/TradeCorrelationCard';
import { LiveManagedPositionsWidget } from './components/Terminal/LiveManagedPositionsWidget';
import { DailyPnLHeader } from './components/Terminal/DailyPnLHeader';
import { TradeJournal } from './components/Journal/TradeJournal';
import { BackendConnectionDiagnostic } from './components/Terminal/BackendConnectionDiagnostic';
import { AGBackendPanel } from './components/Terminal/AGBackendPanel';
import { AG_UI_MODE } from './utils/agApiClient';

import {
  Candle,
  SessionBox,
  SwingPoint,
  StructureBreak,
  OrderBlock,
  FairValueGap,
  LiquidityPool,
  TradeProposal,
  StrategyContract,
  Position,
  AuditLog,
  ReplayFixture
} from './types/trading';
import { SUPPORTED_SYMBOLS } from './data/marketData';
import { REGISTERED_STRATEGIES } from './data/strategies';
import {
  safeFetchJson,
  generateClientProposals,
  generateClientMarketAnalysis,
  DEFAULT_POSITIONS_FALLBACK,
  DEFAULT_LOGS_FALLBACK,
  DEFAULT_FIXTURES_FALLBACK
} from './utils/api';
import {
  Activity,
  Terminal,
  Shield,
  Zap,
  CheckCircle2,
  AlertCircle,
  Play,
  RotateCcw,
  BarChart3
} from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'terminal' | 'scanner' | 'strategies' | 'execution' | 'smc' | 'replay' | 'logs' | 'journal' | 'backend'>('terminal');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('EURUSD');

  // Market & Analysis State
  const [candles, setCandles] = useState<Candle[]>([]);
  const [sessionBoxes, setSessionBoxes] = useState<SessionBox[]>([]);
  const [swingPoints, setSwingPoints] = useState<SwingPoint[]>([]);
  const [structureBreaks, setStructureBreaks] = useState<StructureBreak[]>([]);
  const [orderBlocks, setOrderBlocks] = useState<OrderBlock[]>([]);
  const [fairValueGaps, setFairValueGaps] = useState<FairValueGap[]>([]);
  const [liquidityPools, setLiquidityPools] = useState<LiquidityPool[]>([]);
  const [proposals, setProposals] = useState<TradeProposal[]>(() => generateClientProposals());
  const [strategies, setStrategies] = useState<StrategyContract[]>(REGISTERED_STRATEGIES);
  const [positions, setPositions] = useState<Position[]>(DEFAULT_POSITIONS_FALLBACK);
  const [fixtures, setFixtures] = useState<ReplayFixture[]>(DEFAULT_FIXTURES_FALLBACK);
  const [logs, setLogs] = useState<AuditLog[]>(DEFAULT_LOGS_FALLBACK);
  const [loading, setLoading] = useState<boolean>(true);
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Closed trades filter states
  const [closedTradeSearch, setClosedTradeSearch] = useState<string>('');
  const [closedTradeSymbol, setClosedTradeSymbol] = useState<string>('ALL');
  const [closedTradeOutcome, setClosedTradeOutcome] = useState<TradeOutcomeFilter>('ALL');
  const [closedTradeTimeframe, setClosedTradeTimeframe] = useState<string>('ALL');

  // Total closed positions before filters (for symbol distribution & total baseline counts)
  const allClosedPositions = useMemo(() => {
    return positions.filter(p => p.status === 'CLOSED');
  }, [positions]);

  // Closed positions derived state filtered by status, search, symbol, outcome, and timeframe
  const closedPositions = useMemo(() => {
    return positions.filter(p => {
      if (p.status !== 'CLOSED') return false;
      return matchesClosedTradeFilter(
        p,
        closedTradeSymbol,
        closedTradeOutcome,
        closedTradeSearch,
        'ALL',
        closedTradeTimeframe
      );
    });
  }, [positions, closedTradeSymbol, closedTradeOutcome, closedTradeSearch, closedTradeTimeframe]);

  const availableClosedSymbols = useMemo(() => {
    const counts = new Map<string, number>();
    allClosedPositions.forEach(p => {
      counts.set(p.symbol, (counts.get(p.symbol) || 0) + 1);
    });
    return Array.from(counts.entries()).map(([symbol, count]) => ({ symbol, count }));
  }, [allClosedPositions]);

  const filteredClosedCount = useMemo(() => {
    return closedPositions.length;
  }, [closedPositions]);

  const showToast = (text: string, type: 'success' | 'error' = 'success') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Fetch data for selected symbol with client fallback
  const fetchMarketData = async (sym: string) => {
    const fallbackData = generateClientMarketAnalysis(sym, 'M15', 4);
    const data = await safeFetchJson<{
      symbol: string;
      timeframe: string;
      candles: Candle[];
      analysis: {
        sessionBoxes: SessionBox[];
        swingPoints: SwingPoint[];
        structureBreaks: StructureBreak[];
        orderBlocks: OrderBlock[];
        fairValueGaps: FairValueGap[];
        liquidityPools: LiquidityPool[];
      };
    }>(`/api/market-data/candles?symbol=${sym}&timeframe=M15&days=4`, undefined, fallbackData);

    if (data) {
      setCandles(data.candles || []);
      if (data.analysis) {
        setSessionBoxes(data.analysis.sessionBoxes || []);
        setSwingPoints(data.analysis.swingPoints || []);
        setStructureBreaks(data.analysis.structureBreaks || []);
        setOrderBlocks(data.analysis.orderBlocks || []);
        setFairValueGaps(data.analysis.fairValueGaps || []);
        setLiquidityPools(data.analysis.liquidityPools || []);
      }
    }
  };

  // Fetch proposals, strategies, positions, and fixtures safely
  const fetchSystemData = async () => {
    try {
      const [fetchedProposals, fetchedStrategies, fetchedPositions, fetchedFixtures, fetchedLogs] = await Promise.all([
        safeFetchJson<TradeProposal[]>('/api/proposals/scan', undefined, undefined),
        safeFetchJson<StrategyContract[]>('/api/strategies', undefined, undefined),
        safeFetchJson<Position[]>('/api/execution/positions', undefined, undefined),
        safeFetchJson<ReplayFixture[]>('/api/replay/fixtures', undefined, undefined),
        safeFetchJson<AuditLog[]>('/api/logs', undefined, undefined)
      ]);

      if (fetchedProposals) setProposals(fetchedProposals);
      if (fetchedStrategies) setStrategies(fetchedStrategies);
      if (fetchedPositions) setPositions(fetchedPositions);
      if (fetchedFixtures) setFixtures(fetchedFixtures);
      if (fetchedLogs) setLogs(fetchedLogs);
    } catch (err) {
      console.warn('System data synchronization note:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMarketData(selectedSymbol);
  }, [selectedSymbol]);

  useEffect(() => {
    fetchSystemData();
    const interval = setInterval(() => {
      fetchSystemData();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const activeProposal = proposals.find(p => p.symbol === selectedSymbol) || null;

  // Handle trade execution
  const handleExecuteTrade = async (params: {
    symbol: string;
    strategyId: string;
    side: 'BUY' | 'SELL';
    lots: number;
    entryPrice: number;
    stopLoss: number;
    takeProfit1: number;
    takeProfit2: number;
    user_confirmed: boolean;
  }) => {
    if (AG_UI_MODE === 'real') {
      showToast('Manual order entry is disabled in real mode. Use an authorized backend ticket.', 'error');
      return false;
    }

    try {
      const res = await fetch('/api/execution/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      });
      const data = res.ok && res.headers.get('content-type')?.includes('application/json')
        ? await res.json()
        : null;

      if (data && data.success) {
        showToast(`Simulated position #${data.ticket} created.`);
        fetchSystemData();
        return true;
      } else {
        showToast(data?.error || 'Execution failed', 'error');
        return false;
      }
    } catch (err) {
      showToast('Network execution error', 'error');
      return false;
    }
  };

  const handleManagePosition = async (ticket: number, action: 'BREAKEVEN' | 'PARTIAL_CLOSE' | 'CLOSE') => {
    if (AG_UI_MODE === 'real') {
      showToast('Position management is disabled in real mode until the validated management API is wired.', 'error');
      return;
    }

    try {
      const res = await fetch('/api/execution/manage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket, action })
      });
      const data = res.headers.get('content-type')?.includes('application/json')
        ? await res.json()
        : null;
      if (res.ok && data?.success) {
        showToast(data.message || `Simulated ${action} applied to position #${ticket}`);
        fetchSystemData();
      } else {
        showToast(data?.error || `Could not apply ${action} to position #${ticket}`, 'error');
      }
    } catch (err) {
      showToast('Failed to manage position', 'error');
    }
  };

  // Add and persist short notes to individual trade tickets
  const handleAddPositionNote = async (ticket: number, note: string) => {
    try {
      const trimmedNote = note.trim();
      if (!trimmedNote) return;

      // Optimistic update in UI state
      setPositions(prev =>
        prev.map(p => {
          if (p.ticket === ticket) {
            const currentNotes = p.journalNotes || [];
            return { ...p, journalNotes: [...currentNotes, trimmedNote] };
          }
          return p;
        })
      );

      // Save to localStorage as durable client backup
      try {
        const storageKey = `ag_trade_notes_${ticket}`;
        const existing = JSON.parse(localStorage.getItem(storageKey) || '[]');
        existing.push(trimmedNote);
        localStorage.setItem(storageKey, JSON.stringify(existing));
      } catch (e) {
        console.warn('LocalStorage save skipped', e);
      }

      // Persist to backend server API
      const res = await fetch(`/api/execution/positions/${ticket}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: trimmedNote })
      });

      if (res.ok) {
        showToast(`Note persisted to trade #${ticket}`);
        fetchSystemData();
      } else {
        showToast(`Note saved locally to #${ticket}`);
      }
    } catch (err) {
      showToast(`Note saved locally to #${ticket}`);
    }
  };

  const handleDeletePositionNote = async (ticket: number, noteIndex: number) => {
    try {
      // Optimistic UI update
      setPositions(prev =>
        prev.map(p => {
          if (p.ticket === ticket && p.journalNotes) {
            const updated = [...p.journalNotes];
            updated.splice(noteIndex, 1);
            return { ...p, journalNotes: updated };
          }
          return p;
        })
      );

      // Update localStorage backup
      try {
        const storageKey = `ag_trade_notes_${ticket}`;
        const existing: string[] = JSON.parse(localStorage.getItem(storageKey) || '[]');
        if (noteIndex >= 0 && noteIndex < existing.length) {
          existing.splice(noteIndex, 1);
          localStorage.setItem(storageKey, JSON.stringify(existing));
        }
      } catch (e) {
        console.warn('LocalStorage delete skipped', e);
      }

      const res = await fetch(`/api/execution/positions/${ticket}/notes/${noteIndex}`, {
        method: 'DELETE'
      });

      if (res.ok) {
        showToast(`Note deleted from #${ticket}`);
        fetchSystemData();
      }
    } catch (err) {
      console.error('Delete note failed', err);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        selectedSymbol={selectedSymbol}
        setSelectedSymbol={setSelectedSymbol}
        symbols={SUPPORTED_SYMBOLS}
      />

      <div
        role="status"
        className={`border-b px-4 py-2 text-center text-xs font-bold tracking-wide ${
          AG_UI_MODE === 'mock'
            ? 'border-amber-500/40 bg-amber-950/80 text-amber-200'
            : 'border-cyan-500/40 bg-cyan-950/80 text-cyan-200'
        }`}
      >
        {AG_UI_MODE === 'mock'
          ? 'SIMULATION MODE — prices, proposals, positions, execution, and management are generated fixtures; no broker orders are sent.'
          : 'REAL BACKEND MODE — broker status and authorized tickets are read from the backend; manual execution and management controls are fail-closed.'}
      </div>

      {/* Toast notifications */}
      {toastMessage && (
        <div
          className={`fixed bottom-5 right-5 z-50 px-4 py-3 rounded-xl border shadow-2xl font-mono text-xs flex items-center gap-2.5 transition-all ${
            toastMessage.type === 'success'
              ? 'bg-emerald-950/90 border-emerald-500 text-emerald-200'
              : 'bg-rose-950/90 border-rose-500 text-rose-200'
          }`}
        >
          {toastMessage.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-400" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Main Workspace Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 space-y-6">
        {/* VIEW 1: Live Interactive Terminal */}
        {activeTab === 'terminal' && (
          <div className="space-y-6">
            {/* Daily Profit/Loss Summary Header */}
            <DailyPnLHeader
              positions={positions}
              onSelectSymbol={setSelectedSymbol}
              onOpenExecutionCockpit={() => setActiveTab('execution')}
              onOpenTradeJournal={() => setActiveTab('journal')}
            />

            {/* Candlestick Chart */}
            <CandlestickChart
              candles={candles}
              symbol={selectedSymbol}
              timeframe="M15"
              sessionBoxes={sessionBoxes}
              swingPoints={swingPoints}
              structureBreaks={structureBreaks}
              orderBlocks={orderBlocks}
              fairValueGaps={fairValueGaps}
              liquidityPools={liquidityPools}
              activeProposal={activeProposal}
              onExecuteClick={() => setActiveTab('execution')}
            />

            {/* Trade Correlation & Multi-Asset Exposure Heatmap */}
            <TradeCorrelationCard
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              positions={positions}
            />

            {/* Quick Historical Trades Filter Bar above ClosedTradesSummaryCard */}
            <ClosedTradesFilterBar
              searchQuery={closedTradeSearch}
              onSearchChange={setClosedTradeSearch}
              selectedSymbol={closedTradeSymbol}
              onSymbolChange={setClosedTradeSymbol}
              selectedOutcome={closedTradeOutcome}
              onOutcomeChange={setClosedTradeOutcome}
              selectedTimeframe={closedTradeTimeframe}
              onTimeframeChange={setClosedTradeTimeframe}
              symbols={availableClosedSymbols}
              totalClosedCount={allClosedPositions.length}
              filteredCount={closedPositions.length}
              onReset={() => {
                setClosedTradeSearch('');
                setClosedTradeSymbol('ALL');
                setClosedTradeOutcome('ALL');
                setClosedTradeTimeframe('ALL');
              }}
            />

            {/* Closed Trades Statistical Performance Summary */}
            <ClosedTradesSummaryCard
              positions={positions}
              externalSearchQuery={closedTradeSearch}
              onSearchQueryChange={setClosedTradeSearch}
              externalSymbolFilter={closedTradeSymbol}
              onSymbolFilterChange={setClosedTradeSymbol}
              externalOutcomeFilter={closedTradeOutcome}
              onOutcomeFilterChange={setClosedTradeOutcome}
              externalTimeframeFilter={closedTradeTimeframe}
              onTimeframeFilterChange={setClosedTradeTimeframe}
              onResetFilters={() => {
                setClosedTradeSearch('');
                setClosedTradeSymbol('ALL');
                setClosedTradeOutcome('ALL');
                setClosedTradeTimeframe('ALL');
              }}
            />

            {/* Quick Signals Summary Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <SignalScanner
                  proposals={proposals}
                  selectedSymbol={selectedSymbol}
                  onSelectSymbol={setSelectedSymbol}
                  onExecuteProposal={() => setActiveTab('execution')}
                />
              </div>

              {/* Terminal Right Status & Active Positions Quick Widget */}
              <div>
                <LiveManagedPositionsWidget
                  positions={positions}
                  onManagePosition={handleManagePosition}
                  onAddNote={handleAddPositionNote}
                  onDeleteNote={handleDeletePositionNote}
                  onOpenExecutionCockpit={() => setActiveTab('execution')}
                  onSelectSymbol={setSelectedSymbol}
                />
              </div>
            </div>
          </div>
        )}

        {/* VIEW 2: Multi-Pair Signal Scanner */}
        {activeTab === 'scanner' && (
          <SignalScanner
            proposals={proposals}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={sym => {
              setSelectedSymbol(sym);
              setActiveTab('terminal');
            }}
            onExecuteProposal={() => setActiveTab('execution')}
          />
        )}

        {/* VIEW 3: Smart Money Concepts & Entry Confirmation */}
        {activeTab === 'smc' && (
          <SMCConfirmationView
            selectedSymbol={selectedSymbol}
            onSelectSymbol={setSelectedSymbol}
            candles={candles}
            sessionBoxes={sessionBoxes}
            swingPoints={swingPoints}
            structureBreaks={structureBreaks}
            orderBlocks={orderBlocks}
            fairValueGaps={fairValueGaps}
            liquidityPools={liquidityPools}
            proposals={proposals}
            onExecuteSetup={(prop) => {
              if (prop) setSelectedSymbol(prop.symbol);
              setActiveTab('execution');
            }}
          />
        )}

        {/* VIEW 4: Registered Strategy Contracts */}
        {activeTab === 'strategies' && <StrategyInspector strategies={strategies} />}

        {/* VIEW 5: Execution & Trade Management */}
        {activeTab === 'execution' && (
          <div className="space-y-4">
            <BackendConnectionDiagnostic />
            <ExecutionCockpit
              positions={positions}
              onManagePosition={handleManagePosition}
              onAddNote={handleAddPositionNote}
              onDeleteNote={handleDeletePositionNote}
              onExecuteTrade={handleExecuteTrade}
              selectedProposal={activeProposal}
            />
          </div>
        )}

        {/* VIEW 6: Deterministic Trade Journal & PnL Growth */}
        {activeTab === 'journal' && (
          <TradeJournal
            positions={positions}
            onSelectSymbol={sym => {
              setSelectedSymbol(sym);
              setActiveTab('terminal');
            }}
            onOpenExecutionCockpit={() => setActiveTab('execution')}
            onSaveNote={handleAddPositionNote}
            onDeleteNote={handleDeletePositionNote}
          />
        )}

        {/* VIEW 7: Historical Replay Lab */}
        {activeTab === 'replay' && <ReplayStudio fixtures={fixtures} />}

        {/* VIEW 8: System Audit Logs */}
        {activeTab === 'logs' && <AuditLogViewer logs={logs} />}

        {/* VIEW 9: Real AG Local Backend (read-only) */}
        {activeTab === 'backend' && (
          <div className="space-y-4">
            <BackendConnectionDiagnostic />
            <AGBackendPanel />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 px-6 py-4 text-xs font-mono text-slate-500 flex flex-wrap items-center justify-between gap-4">
        <div>AG Profit Trading Assistant • Deterministic Session Strategy Engine</div>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            Backend REST API Online
          </span>
          <span>Port 3000 (0.0.0.0)</span>
        </div>
      </footer>
    </div>
  );
};
export default App;
