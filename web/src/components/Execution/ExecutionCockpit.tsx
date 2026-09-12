import React, { useState, useMemo, useEffect } from 'react';
import { Position, TradeProposal, AuditLog, OrderSide } from '../../types/trading';
import { isAuthoritativeProposal as isAuthoritativeProposalCheck } from '../../utils/proposalAuthority';
import { PositionSizeCalculator } from './PositionSizeCalculator';
import { QuickRiskCalculatorWidget } from './QuickRiskCalculatorWidget';
import {
  Terminal,
  Shield,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Play,
  X,
  TrendingUp,
  TrendingDown,
  Lock,
  RotateCcw,
  Check,
  Search,
  SlidersHorizontal,
  Filter,
  FileText,
  Trash2,
  Send,
  Calculator,
  Zap,
  ArrowRight,
  Server,
  DollarSign
} from 'lucide-react';
import { BrokerConnectionModal } from '../Terminal/BrokerConnectionModal';

interface ExecutionCockpitProps {
  positions: Position[];
  onManagePosition: (ticket: number, action: 'BREAKEVEN' | 'PARTIAL_CLOSE' | 'CLOSE') => void;
  onAddNote?: (ticket: number, note: string) => void;
  onDeleteNote?: (ticket: number, noteIndex: number) => void;
  onExecuteTrade: (params: {
    symbol: string;
    strategyId: string;
    side: 'BUY' | 'SELL';
    lots: number;
    entryPrice: number;
    stopLoss: number;
    takeProfit1: number;
    takeProfit2: number;
    user_confirmed: boolean;
  }) => Promise<boolean>;
  selectedProposal: TradeProposal | null;
}

export const ExecutionCockpit: React.FC<ExecutionCockpitProps> = ({
  positions,
  onManagePosition,
  onAddNote,
  onDeleteNote,
  onExecuteTrade,
  selectedProposal
}) => {
  const [ticketInput, setTicketInput] = useState<string>('');
  const [claimStatus, setClaimStatus] = useState<string | null>(null);
  const [isBrokerModalOpen, setIsBrokerModalOpen] = useState<boolean>(false);

  // Left panel mode: Order Execution vs Position Size Calculator
  const [leftPanelMode, setLeftPanelMode] = useState<'ORDER' | 'CALCULATOR'>('ORDER');
  const [appliedCalcNotice, setAppliedCalcNotice] = useState<string | null>(null);

  // Broker live equity tracking
  const [brokerBalance, setBrokerBalance] = useState<number>(1000.00);
  const [brokerEquity, setBrokerEquity] = useState<number | null>(null);

  useEffect(() => {
    fetch('/api/broker/status')
      .then(res => res.json())
      .then(data => {
        if (data && typeof data.balance === 'number') {
          setBrokerBalance(data.balance);
        }
        if (data && typeof data.equity === 'number') {
          setBrokerEquity(data.equity);
        }
      })
      .catch(() => {});
  }, []);

  const liveCalculatedEquity = useMemo(() => {
    const baseBalance = brokerBalance;
    const openPnl = positions
      .filter(p => p.status === 'OPEN')
      .reduce((sum, p) => sum + p.pnl, 0);
    return baseBalance + openPnl;
  }, [brokerBalance, positions]);

  const currentEquity = brokerEquity ?? liveCalculatedEquity;

  // Position search & filter state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sideFilter, setSideFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [pnlFilter, setPnlFilter] = useState<'ALL' | 'PROFIT' | 'DRAWDOWN'>('ALL');
  const [expandedNotes, setExpandedNotes] = useState<Record<number, boolean>>({});
  const [cockpitNoteInput, setCockpitNoteInput] = useState<Record<number, string>>({});

  // Filtered positions
  const activePositions = useMemo(() => {
    return positions.filter(p => p.status !== 'CLOSED');
  }, [positions]);

  const filteredPositions = useMemo(() => {
    return activePositions.filter(p => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const symbolMatch = p.symbol.toLowerCase().includes(q);
        const ticketMatch = String(p.ticket).includes(q);
        const notesMatch = (p.journalNotes || []).some(n => n.toLowerCase().includes(q));
        if (!symbolMatch && !ticketMatch && !notesMatch) return false;
      }
      if (sideFilter !== 'ALL' && p.side !== sideFilter) return false;
      if (pnlFilter === 'PROFIT' && p.pnl <= 0) return false;
      if (pnlFilter === 'DRAWDOWN' && p.pnl >= 0) return false;
      return true;
    });
  }, [activePositions, searchQuery, sideFilter, pnlFilter]);

  // New Order Form state.
  //
  // AG_SCANNER_SAFE_PROPOSAL_EXECUTION_REMEDIATION_V2 (Finding 3 / Invariant D): a
  // scanner proposal built from synthetic candles must never silently seed the values
  // this form sends to /api/execution/execute -- that would let stale/fake geometry
  // reach a real MT5 order under manual (USER_EXPLICIT_ORDER) authority merely because
  // the operator navigated here from the scanner. Only a non-synthetic proposal (none
  // exist yet -- see repository task P2-P4) may pre-fill these fields; otherwise the
  // operator must type every value themselves.
  //
  // WP5.2 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): this used to be the negative-trust
  // check `marketDataSource !== 'SYNTHETIC'`, which reads missing/unknown provenance as
  // authoritative -- see utils/proposalAuthority.ts for why that's fail-open and what
  // replaced it.
  const isAuthoritativeProposal = isAuthoritativeProposalCheck(selectedProposal);
  const [symbol, setSymbol] = useState<string>(isAuthoritativeProposal ? selectedProposal!.symbol : 'EURUSD');
  const [side, setSide] = useState<'BUY' | 'SELL'>(isAuthoritativeProposal ? (selectedProposal!.entrySide || 'BUY') : 'BUY');
  const [lots, setLots] = useState<number>(isAuthoritativeProposal ? (selectedProposal!.suggestedLots || 1.0) : 1.0);
  const [entryPrice, setEntryPrice] = useState<number>(isAuthoritativeProposal ? (selectedProposal!.entryPrice || 1.08500) : 1.08500);
  const [stopLoss, setStopLoss] = useState<number>(isAuthoritativeProposal ? (selectedProposal!.stopLoss || 1.08300) : 1.08300);
  const [tp1, setTp1] = useState<number>(isAuthoritativeProposal ? (selectedProposal!.takeProfit1 || 1.08800) : 1.08800);
  const [tp2, setTp2] = useState<number>(isAuthoritativeProposal ? (selectedProposal!.takeProfit2 || 1.09200) : 1.09200);

  // Explicit confirmation modal gate
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
  const [confirmChecked, setConfirmChecked] = useState<boolean>(false);
  const [executing, setExecuting] = useState<boolean>(false);

  const handleOpenConfirm = () => {
    setConfirmChecked(false);
    setShowConfirmModal(true);
  };

  const handleConfirmExecute = async () => {
    if (!confirmChecked) return;
    setExecuting(true);
    const success = await onExecuteTrade({
      symbol,
      strategyId: isAuthoritativeProposal ? (selectedProposal!.strategyId || 'FRONTEND_MANUAL') : 'FRONTEND_MANUAL',
      side,
      lots,
      entryPrice,
      stopLoss,
      takeProfit1: tp1,
      takeProfit2: tp2,
      user_confirmed: true
    });
    setExecuting(false);
    if (success) {
      setShowConfirmModal(false);
    }
  };

  const handleClaimTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketInput) return;
    try {
      const response = await fetch('/api/execution/claim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket: Number(ticketInput), finalR: 5 })
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        setClaimStatus(`Claim rejected: ${payload.error || 'unknown error'}`);
      } else {
        setClaimStatus(`Ticket #${ticketInput} claimed successfully into manual management.`);
        setTicketInput('');
      }
    } catch {
      setClaimStatus('Claim failed: backend unavailable.');
    }
    setTimeout(() => setClaimStatus(null), 4000);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Terminal className="w-5 h-5 text-cyan-400" />
            <span>Execution Cockpit & Manual Trade Management</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Strict Two-Stage execution authority requiring explicit user confirmation per turn. Gated demo simulation with ticket claiming, 75% TP1 partial closes, and runner BE protection.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-2 bg-slate-950 rounded-lg border border-slate-800 font-mono text-xs">
            <DollarSign className="w-4 h-4 text-cyan-400" />
            <div>
              <div className="text-[10px] text-slate-400">DEMO EQUITY</div>
              <span className="text-cyan-300 font-bold">${currentEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-slate-950 rounded-lg border border-slate-800 font-mono text-xs">
            <Shield className="w-4 h-4 text-emerald-400" />
            <div>
              <div className="text-[10px] text-slate-400">DAILY RISK GUARD</div>
              <span className="text-emerald-400 font-bold">0.00 / 2.00 R</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Explicit Order Execution Panel OR Position Size Calculator */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md flex flex-col gap-4">
          {/* Segmented Mode Switcher */}
          <div className="flex items-center p-1 bg-slate-950 rounded-lg border border-slate-800 font-mono text-xs">
            <button
              id="tab-mode-order"
              type="button"
              onClick={() => setLeftPanelMode('ORDER')}
              className={`flex-1 py-1.5 px-2 rounded font-bold flex items-center justify-center gap-1.5 transition ${
                leftPanelMode === 'ORDER'
                  ? 'bg-slate-800 text-cyan-300 shadow-sm border border-slate-700'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Play className="w-3.5 h-3.5 text-emerald-400" />
              <span>Send Order & Quick Calc</span>
            </button>
            <button
              id="tab-mode-calc"
              type="button"
              onClick={() => setLeftPanelMode('CALCULATOR')}
              className={`flex-1 py-1.5 px-2 rounded font-bold flex items-center justify-center gap-1.5 transition ${
                leftPanelMode === 'CALCULATOR'
                  ? 'bg-cyan-600 text-white shadow-sm border border-cyan-500'
                  : 'text-slate-400 hover:text-cyan-300'
              }`}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Full Sizing Engine</span>
            </button>
          </div>

          {/* Applied Notice Banner */}
          {appliedCalcNotice && (
            <div className="p-2 bg-emerald-950/40 border border-emerald-800/80 rounded-lg flex items-center gap-2 text-xs font-mono text-emerald-300 animate-in fade-in">
              <Check className="w-4 h-4 text-emerald-400 shrink-0 stroke-[3]" />
              <span>{appliedCalcNotice}</span>
            </div>
          )}

          {leftPanelMode === 'ORDER' ? (
            <>
              {selectedProposal && !isAuthoritativeProposalCheck(selectedProposal) && (
                <div className="p-2 bg-amber-950/40 border border-amber-800/80 rounded-lg flex items-start gap-2 text-xs font-mono text-amber-300">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <span>
                    Scanner proposal for {selectedProposal.symbol} is NON_AUTHORITATIVE_ESTIMATE (synthetic market
                    data, research only) and has NOT been used to fill this form. Enter every value yourself for a
                    manual (user-directed) order.
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono flex items-center gap-2">
                  <Play className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Order Execution (Demo Broker)</span>
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    id="cockpit-validate-broker-btn"
                    onClick={() => setIsBrokerModalOpen(true)}
                    className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 transition cursor-pointer"
                    title="Validate Broker Connection"
                  >
                    <Server className="w-3 h-3 text-emerald-400" />
                    <span>Validate Broker</span>
                  </button>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    GATED: CONFIRM REQ
                  </span>
                </div>
              </div>

              <div className="space-y-3 font-mono text-xs">
                {/* Symbol & Side */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-slate-400 block mb-1">Symbol</label>
                    <select
                      id="order-symbol-select"
                      value={symbol}
                      onChange={e => setSymbol(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="EURUSD">EURUSD</option>
                      <option value="GBPUSD">GBPUSD</option>
                      <option value="USDJPY">USDJPY</option>
                      <option value="AUDUSD">AUDUSD</option>
                      <option value="XAUUSD">XAUUSD</option>
                      <option value="BTCUSD">BTCUSD (Crypto)</option>
                      <option value="ETHUSD">ETHUSD (Crypto)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-slate-400 block mb-1">Side</label>
                    <div className="grid grid-cols-2 gap-1">
                      <button
                        type="button"
                        onClick={() => setSide('BUY')}
                        className={`py-1.5 rounded font-bold transition ${
                          side === 'BUY'
                            ? 'bg-emerald-500 text-slate-950'
                            : 'bg-slate-950 text-slate-400 border border-slate-800'
                        }`}
                      >
                        BUY
                      </button>
                      <button
                        type="button"
                        onClick={() => setSide('SELL')}
                        className={`py-1.5 rounded font-bold transition ${
                          side === 'SELL'
                            ? 'bg-rose-500 text-slate-100'
                            : 'bg-slate-950 text-slate-400 border border-slate-800'
                        }`}
                      >
                        SELL
                      </button>
                    </div>
                  </div>
                </div>

                {/* Lots & Entry Price */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-slate-400">Volume (Lots)</label>
                      <button
                        type="button"
                        onClick={() => setLeftPanelMode('CALCULATOR')}
                        className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-semibold hover:underline"
                        title="Calculate exact lot size using account equity & stop loss"
                      >
                        <Calculator className="w-3 h-3" />
                        <span>Calc</span>
                      </button>
                    </div>
                    <input
                      id="order-lots-input"
                      type="number"
                      step="0.01"
                      min="0.01"
                      max="50"
                      value={lots}
                      onChange={e => setLots(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-bold focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Entry Price</label>
                    <input
                      id="order-entry-price-input"
                      type="number"
                      step="0.00001"
                      value={entryPrice}
                      onChange={e => setEntryPrice(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Stop Loss & Targets */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-slate-400">Stop Loss</label>
                    <span className="text-[10px] text-slate-500">
                      Dist: {Math.abs(entryPrice - stopLoss).toFixed(5)}
                    </span>
                  </div>
                  <input
                    id="order-stop-loss-input"
                    type="number"
                    step="0.00001"
                    value={stopLoss}
                    onChange={e => setStopLoss(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-rose-300 font-bold focus:border-cyan-500 focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-slate-400 block mb-1">TP1 (75% Split)</label>
                    <input
                      id="order-tp1-input"
                      type="number"
                      step="0.00001"
                      value={tp1}
                      onChange={e => setTp1(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-emerald-300 font-bold focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">TP2 (25% 5R Runner)</label>
                    <input
                      id="order-tp2-input"
                      type="number"
                      step="0.00001"
                      value={tp2}
                      onChange={e => setTp2(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-cyan-300 font-bold focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Integrated Quick Risk-Per-Trade Calculator Widget */}
              <QuickRiskCalculatorWidget
                symbol={symbol}
                side={side}
                entryPrice={entryPrice}
                stopLoss={stopLoss}
                takeProfit1={tp1}
                takeProfit2={tp2}
                liveEquity={currentEquity}
                currentLots={lots}
                onApplyLots={(suggestedLots, updatedStopLoss) => {
                  setLots(suggestedLots);
                  if (updatedStopLoss !== undefined) {
                    setStopLoss(updatedStopLoss);
                  }
                  setAppliedCalcNotice(`Applied ${suggestedLots.toFixed(2)} lots based on $${currentEquity.toFixed(0)} equity & SL distance!`);
                  setTimeout(() => setAppliedCalcNotice(null), 3500);
                }}
                onApplyTakeProfits={(newTp1, newTp2) => {
                  setTp1(newTp1);
                  setTp2(newTp2);
                  setAppliedCalcNotice(`Synchronized TP1 (${newTp1}) & TP2 (${newTp2}) to target R:R!`);
                  setTimeout(() => setAppliedCalcNotice(null), 3500);
                }}
                className="mt-1"
              />

              {/* Crypto Incubation Notice */}
              {(symbol === 'BTCUSD' || symbol === 'ETHUSD') && (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5 text-amber-300 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold text-xs">
                    <Lock className="w-3.5 h-3.5 text-amber-400" />
                    <span>Crypto Strategy: Incubation / Proposal-Only</span>
                  </div>
                  <p className="text-[11px] text-amber-200/80 leading-relaxed">
                    Strategy <code className="bg-amber-950/60 px-1 rounded">ST_LIQUIDITY_SWEEP_RETEST_V1</code> (Crypto Profile) is registered for advisory proposals only. Venue execution (e.g. Binance/Bybit) is blocked fail-closed under AG Profit Trading authority rules.
                  </p>
                </div>
              )}

              {symbol === 'BTCUSD' || symbol === 'ETHUSD' ? (
                <button
                  type="button"
                  disabled
                  id="btn-crypto-disabled"
                  className="w-full py-2.5 bg-slate-800 text-slate-500 font-bold text-xs rounded-lg mt-1 flex items-center justify-center gap-2 cursor-not-allowed border border-slate-700"
                >
                  <Lock className="w-4 h-4 text-amber-400" />
                  <span>Execution Gated (Crypto Fail-Closed)</span>
                </button>
              ) : (
                <button
                  id="btn-open-confirm-modal"
                  onClick={handleOpenConfirm}
                  className="w-full py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded-lg transition shadow-lg mt-1 flex items-center justify-center gap-2"
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>Review & Authorize Execution</span>
                </button>
              )}
            </>
          ) : (
            /* Position Size Calculator Panel */
            <PositionSizeCalculator
              initialSymbol={symbol}
              initialSide={side}
              initialEntryPrice={entryPrice}
              initialStopLoss={stopLoss}
              initialTp1={tp1}
              initialTp2={tp2}
              onApplyToOrder={params => {
                setSymbol(params.symbol);
                setSide(params.side);
                setLots(params.lots);
                setEntryPrice(params.entryPrice);
                setStopLoss(params.stopLoss);
                setTp1(params.takeProfit1);
                setTp2(params.takeProfit2);
                setLeftPanelMode('ORDER');
                setAppliedCalcNotice(`Applied ${params.lots.toFixed(2)} lots (${params.symbol} ${params.side}) to Order Form!`);
                setTimeout(() => setAppliedCalcNotice(null), 3500);
              }}
            />
          )}
        </div>

        {/* Right Column: Claim Ticket & Active Positions */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          {/* Ticket Claim Box */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-md">
            <form onSubmit={handleClaimTicket} className="flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-[200px]">
                <label className="text-xs text-slate-400 block mb-1 font-mono">
                  Claim Manual Position by Ticket # (scripts/manage_trade.py claim)
                </label>
                <input
                  type="text"
                  placeholder="e.g. 9021441"
                  value={ticketInput}
                  onChange={e => setTicketInput(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-200 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <button
                type="submit"
                className="mt-5 px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs font-mono font-semibold transition"
              >
                Claim Ticket
              </button>
            </form>
            {claimStatus && (
              <div className="mt-2 text-xs font-mono text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{claimStatus}</span>
              </div>
            )}
          </div>

          {/* Active Positions Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md flex-1 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
              <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider font-mono flex items-center gap-2">
                <span>Active Managed Positions</span>
                <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-cyan-300 font-bold border border-slate-700">
                  {filteredPositions.length} of {activePositions.length}
                </span>
              </h3>

              {/* Side Filter Chips */}
              <div className="flex items-center gap-1 font-mono text-xs">
                {(['ALL', 'BUY', 'SELL'] as const).map(s => (
                  <button
                    key={s}
                    id={`cockpit-filter-side-${s.toLowerCase()}`}
                    onClick={() => setSideFilter(s)}
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                      sideFilter === s
                        ? s === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : s === 'SELL'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : 'bg-slate-800 text-slate-200 border border-slate-700'
                        : 'bg-slate-950 text-slate-500 hover:text-slate-300 border border-transparent'
                    }`}
                  >
                    {s}
                  </button>
                ))}

                <div className="h-3 w-px bg-slate-800 mx-1" />

                <button
                  id="cockpit-filter-pnl-profit"
                  onClick={() => setPnlFilter(pnlFilter === 'PROFIT' ? 'ALL' : 'PROFIT')}
                  className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                    pnlFilter === 'PROFIT'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-slate-950 text-slate-500 hover:text-slate-300'
                  }`}
                >
                  Profit
                </button>
                <button
                  id="cockpit-filter-pnl-drawdown"
                  onClick={() => setPnlFilter(pnlFilter === 'DRAWDOWN' ? 'ALL' : 'DRAWDOWN')}
                  className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                    pnlFilter === 'DRAWDOWN'
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-slate-950 text-slate-500 hover:text-slate-300'
                  }`}
                >
                  Drawdown
                </button>
              </div>
            </div>

            {/* Search Input Bar */}
            <div className="relative font-mono">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Search className="w-3.5 h-3.5" />
              </div>
              <input
                id="cockpit-positions-search"
                type="text"
                placeholder="Search active trades by symbol (e.g. EURUSD) or ticket ID..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="space-y-3">
              {filteredPositions.map(pos => {
                const isProfitable = pos.pnl >= 0;
                return (
                  <div
                    key={pos.ticket}
                    className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 space-y-3 font-mono text-xs hover:border-slate-700 transition"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/60 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-100">#{pos.ticket}</span>
                        <span className="text-cyan-400 font-bold">{pos.symbol}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            pos.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'
                          }`}
                        >
                          {pos.side} {pos.volume} Lots
                        </span>
                        <span className="text-slate-500 text-[10px]">({pos.status})</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">PnL:</span>
                        <span
                          className={`font-bold text-sm ${
                            isProfitable ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {isProfitable ? `+$${pos.pnl.toFixed(2)}` : `-$${Math.abs(pos.pnl).toFixed(2)}`} (+{pos.pnlR.toFixed(2)}R)
                        </span>
                      </div>
                    </div>

                    {/* Levels */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-slate-400">
                      <div>
                        <span>Entry:</span> <strong className="text-slate-200">{pos.entryPrice.toFixed(5)}</strong>
                      </div>
                      <div>
                        <span>Stop Loss:</span>{' '}
                        <strong className={pos.isBreakevenMoved ? 'text-amber-400' : 'text-rose-400'}>
                          {pos.stopLoss.toFixed(5)} {pos.isBreakevenMoved && '(BE)'}
                        </strong>
                      </div>
                      <div>
                        <span>TP1 (75%):</span> <strong className="text-emerald-400">{pos.takeProfit1.toFixed(5)}</strong>
                      </div>
                      <div>
                        <span>TP2 (5R):</span> <strong className="text-cyan-400">{pos.takeProfit2.toFixed(5)}</strong>
                      </div>
                    </div>

                    {/* Actions */}
                    {pos.status !== 'CLOSED' && (
                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <button
                          onClick={() =>
                            setExpandedNotes(prev => ({
                              ...prev,
                              [pos.ticket]: !prev[pos.ticket]
                            }))
                          }
                          className={`px-2.5 py-1 rounded text-[11px] font-semibold flex items-center gap-1.5 transition ${
                            expandedNotes[pos.ticket]
                              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                              : (pos.journalNotes || []).length > 0
                              ? 'bg-slate-900 text-cyan-300 border border-slate-800 hover:border-slate-700'
                              : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                          }`}
                        >
                          <FileText className="w-3.5 h-3.5 text-cyan-400" />
                          <span>
                            {(pos.journalNotes || []).length > 0
                              ? `${pos.journalNotes.length} Note${pos.journalNotes.length > 1 ? 's' : ''}`
                              : 'Add Note'}
                          </span>
                        </button>

                        <button
                          onClick={() => onManagePosition(pos.ticket, 'BREAKEVEN')}
                          disabled={pos.isBreakevenMoved}
                          className={`px-2.5 py-1 rounded text-[11px] font-semibold transition ${
                            pos.isBreakevenMoved
                              ? 'bg-slate-900 text-slate-600 cursor-not-allowed'
                              : 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/40'
                          }`}
                        >
                          Move SL to Breakeven
                        </button>

                        <button
                          onClick={() => onManagePosition(pos.ticket, 'PARTIAL_CLOSE')}
                          disabled={pos.tp1Filled}
                          className={`px-2.5 py-1 rounded text-[11px] font-semibold transition ${
                            pos.tp1Filled
                              ? 'bg-slate-900 text-slate-600 cursor-not-allowed'
                              : 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/40'
                          }`}
                        >
                          Partial Close 75% (TP1)
                        </button>

                        <button
                          onClick={() => onManagePosition(pos.ticket, 'CLOSE')}
                          className="px-2.5 py-1 rounded text-[11px] font-semibold bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/40"
                        >
                          Close Position
                        </button>
                      </div>
                    )}

                    {/* Expandable Notes Panel */}
                    {expandedNotes[pos.ticket] && (
                      <div className="pt-2 border-t border-slate-900 space-y-2 bg-slate-900/40 p-3 rounded-lg">
                        <div className="flex items-center justify-between text-[11px] font-bold text-cyan-400">
                          <span className="flex items-center gap-1.5">
                            <FileText className="w-3.5 h-3.5" />
                            <span>Trade Journal Notes (Ticket #{pos.ticket})</span>
                          </span>
                        </div>

                        {pos.journalNotes && pos.journalNotes.length > 0 ? (
                          <div className="space-y-1.5 max-h-32 overflow-y-auto">
                            {pos.journalNotes.map((note, idx) => (
                              <div
                                key={idx}
                                className="bg-slate-950 border border-slate-800 p-2 rounded text-[11px] flex items-start justify-between gap-2 group/note"
                              >
                                <div className="flex items-start gap-1.5 text-slate-300">
                                  <span className="text-cyan-400">•</span>
                                  <span>{note}</span>
                                </div>
                                {onDeleteNote && (
                                  <button
                                    onClick={() => onDeleteNote(pos.ticket, idx)}
                                    className="text-slate-500 hover:text-rose-400 opacity-60 group-hover/note:opacity-100 transition"
                                    title="Delete note"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[11px] text-slate-500 italic">No notes recorded yet.</p>
                        )}

                        {onAddNote && (
                          <div className="flex items-center gap-2 pt-1">
                            <input
                              type="text"
                              placeholder="Add quick trade note..."
                              value={cockpitNoteInput[pos.ticket] || ''}
                              onChange={e =>
                                setCockpitNoteInput(prev => ({
                                  ...prev,
                                  [pos.ticket]: e.target.value
                                }))
                              }
                              onKeyDown={e => {
                                if (e.key === 'Enter') {
                                  const text = (cockpitNoteInput[pos.ticket] || '').trim();
                                  if (text) {
                                    onAddNote(pos.ticket, text);
                                    setCockpitNoteInput(prev => ({ ...prev, [pos.ticket]: '' }));
                                  }
                                }
                              }}
                              className="flex-1 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                            />
                            <button
                              onClick={() => {
                                const text = (cockpitNoteInput[pos.ticket] || '').trim();
                                if (text) {
                                  onAddNote(pos.ticket, text);
                                  setCockpitNoteInput(prev => ({ ...prev, [pos.ticket]: '' }));
                                }
                              }}
                              disabled={!(cockpitNoteInput[pos.ticket] || '').trim()}
                              className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded text-xs font-semibold flex items-center gap-1 transition"
                            >
                              <Send className="w-3 h-3" />
                              <span>Add</span>
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {activePositions.length === 0 && (
                <div className="text-center py-6 text-slate-500 text-xs font-mono border border-dashed border-slate-800 rounded-lg">
                  No active or claimed positions in journal.
                </div>
              )}

              {activePositions.length > 0 && filteredPositions.length === 0 && (
                <div className="text-center py-6 text-slate-400 text-xs font-mono border border-dashed border-slate-800 rounded-lg space-y-2">
                  <p>No active positions match "{searchQuery}"</p>
                  <button
                    onClick={() => {
                      setSearchQuery('');
                      setSideFilter('ALL');
                      setPnlFilter('ALL');
                    }}
                    className="text-cyan-400 hover:text-cyan-300 text-xs font-semibold underline"
                  >
                    Reset filters
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Explicit Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2 text-slate-100 font-bold">
                <ShieldAlert className="w-5 h-5 text-amber-400" />
                <span>Explicit Execution Authorization</span>
              </div>
              <button
                onClick={() => setShowConfirmModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Per AG Profit Trading Authority Rules: Autonomous execution is prohibited. You are explicitly authorizing the DEMO broker gateway to send this order with the specified parameters:
            </p>

            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 font-mono text-xs space-y-1.5 text-slate-300">
              <div className="flex justify-between">
                <span className="text-slate-400">Order:</span>
                <span className="font-bold text-cyan-300">{side} {lots} Lots {symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Entry:</span>
                <span>{entryPrice.toFixed(5)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Stop Loss:</span>
                <span className="text-rose-400">{stopLoss.toFixed(5)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Target 1 (75%):</span>
                <span className="text-emerald-400">{tp1.toFixed(5)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Target 2 (25% 5R):</span>
                <span className="text-cyan-400">{tp2.toFixed(5)}</span>
              </div>
            </div>

            <label className="flex items-start gap-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl cursor-pointer">
              <input
                type="checkbox"
                id="checkbox-confirm-user"
                checked={confirmChecked}
                onChange={e => setConfirmChecked(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded text-cyan-500 focus:ring-cyan-400 bg-slate-900 border-slate-700"
              />
              <span className="text-xs text-amber-200 font-medium leading-tight">
                I explicitly confirm (<code>user_confirmed=True</code>) this execution command for the current turn.
              </span>
            </label>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="button"
                id="btn-confirm-execute"
                disabled={!confirmChecked || executing}
                onClick={handleConfirmExecute}
                className={`px-5 py-2 rounded-lg text-xs font-bold transition flex items-center gap-2 ${
                  confirmChecked && !executing
                    ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-lg'
                    : 'bg-slate-800 text-slate-600 cursor-not-allowed'
                }`}
              >
                {executing ? 'Sending Order...' : 'Confirm & Execute Order'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Broker Connection & Diagnostics Modal */}
      <BrokerConnectionModal
        isOpen={isBrokerModalOpen}
        onClose={() => setIsBrokerModalOpen(false)}
      />
    </div>
  );
};
