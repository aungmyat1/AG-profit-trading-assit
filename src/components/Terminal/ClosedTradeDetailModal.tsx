import React, { useEffect, useState } from 'react';
import { Position } from '../../types/trading';
import {
  X,
  Clock,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  ShieldAlert,
  Target,
  FileText,
  Activity,
  Layers,
  Award,
  DollarSign,
  Copy,
  Check,
  Zap,
  TrendingUp,
  TrendingDown,
  Info,
  CheckCircle2,
  AlertTriangle
} from 'lucide-react';

interface ClosedTradeDetailModalProps {
  trade: Position | null;
  onClose: () => void;
}

export const ClosedTradeDetailModal: React.FC<ClosedTradeDetailModalProps> = ({ trade, onClose }) => {
  const [copied, setCopied] = useState<boolean>(false);

  // Close modal on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!trade) return null;

  const isWin = trade.pnl > 0.001;
  const isLoss = trade.pnl < -0.001;
  const isBreakeven = !isWin && !isLoss;

  const isJpy = trade.symbol.includes('JPY');
  const pipMultiplier = isJpy ? 100 : 10000;

  // Calculate pips gained/lost
  const closeOrCurrentPrice = trade.currentPrice || trade.entryPrice;
  const pipDiff = trade.side === 'BUY'
    ? (closeOrCurrentPrice - trade.entryPrice) * pipMultiplier
    : (trade.entryPrice - closeOrCurrentPrice) * pipMultiplier;

  const slPipRisk = Math.abs(trade.entryPrice - trade.stopLoss) * pipMultiplier;
  const tp1Pips = Math.abs(trade.takeProfit1 - trade.entryPrice) * pipMultiplier;
  const tp2Pips = Math.abs(trade.takeProfit2 - trade.entryPrice) * pipMultiplier;

  // Calculate Trade Duration
  const openTime = trade.openTime;
  const closeTime = trade.closeTime || trade.openTime;
  const durationSeconds = Math.max(0, closeTime - openTime);

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    if (hours < 24) {
      return `${hours}h ${remainingMinutes > 0 ? `${remainingMinutes}m` : ''}`;
    }
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return `${days}d ${remainingHours > 0 ? `${remainingHours}h` : ''}`;
  };

  const formatTimestamp = (unixSec: number) => {
    if (!unixSec) return 'N/A';
    const date = new Date(unixSec * 1000);
    return date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
  };

  // Determine Exit Reason based on trade milestones and PnL
  const determineExitReason = () => {
    if (trade.pnlR >= 4.5) {
      return {
        title: 'Full Strategy Target (TP2 / 5R Runner Fill)',
        category: 'TARGET_MAX',
        description: 'Complete target realization including the 25% runner leg reached full 5.0R expansion limit.',
        badgeColor: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      };
    }
    if (trade.tp1Filled && trade.pnlR > 0) {
      return {
        title: 'TP1 (75%) Banked + Runner Managed Exit',
        category: 'TARGET_PARTIAL_RUNNER',
        description: '75% target secured at opposite session boundary; remaining 25% runner trailed or closed into session end.',
        badgeColor: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      };
    }
    if (trade.isBreakevenMoved && Math.abs(trade.pnlR) <= 0.2) {
      return {
        title: 'Breakeven Stop Triggered (0.00R / Risk Protected)',
        category: 'BREAKEVEN',
        description: 'Stop loss was automatically advanced to breakeven after displacement; market retraced to protected entry.',
        badgeColor: 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      };
    }
    if (trade.pnlR <= -0.8) {
      return {
        title: 'Initial Stop Loss Triggered (-1.00R Clean Invalidation)',
        category: 'STOP_LOSS',
        description: 'Price breached structural invalidation boundary; deterministic 1.0R risk guard executed flawlessly.',
        badgeColor: 'bg-rose-500/20 text-rose-300 border-rose-500/40'
      };
    }
    return {
      title: 'Session Cut / Discretionary Invalidation Exit',
      category: 'SESSION_EXIT',
      description: 'Position resolved according to session expiration rules or pre-news structural risk protocol.',
      badgeColor: 'bg-slate-700 text-slate-300 border-slate-600'
    };
  };

  const exitDetails = determineExitReason();

  // Copy trade summary to clipboard
  const handleCopyReport = () => {
    const reportText = `[TRADE REPORT] Ticket #${trade.ticket}
Symbol: ${trade.symbol} | Side: ${trade.side === 'BUY' ? 'LONG' : 'SHORT'} | Lots: ${trade.volume}
Strategy: ${trade.strategyId}
Entry: ${trade.entryPrice.toFixed(5)} | SL: ${trade.stopLoss.toFixed(5)} | TP1: ${trade.takeProfit1.toFixed(5)} | TP2: ${trade.takeProfit2.toFixed(5)}
Exit Price: ${closeOrCurrentPrice.toFixed(5)}
Result: ${trade.pnl >= 0 ? '+' : ''}$${trade.pnl.toFixed(2)} (${trade.pnlR >= 0 ? '+' : ''}${trade.pnlR.toFixed(2)}R, ${pipDiff >= 0 ? '+' : ''}${pipDiff.toFixed(1)} pips)
Exit Reason: ${exitDetails.title}
Duration: ${formatDuration(durationSeconds)} (${formatTimestamp(openTime)} -> ${formatTimestamp(closeTime)})
Journal:
${trade.journalNotes?.length ? trade.journalNotes.map(n => `- ${n}`).join('\n') : '- No additional notes'}`;

    navigator.clipboard.writeText(reportText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div
      id="closed-trade-modal-backdrop"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm overflow-y-auto animate-in fade-in duration-200"
      onClick={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        id={`closed-trade-modal-${trade.ticket}`}
        className="relative w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden font-sans text-slate-100 my-8"
        role="dialog"
        aria-modal="true"
      >
        {/* Top Header Banner */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-xl border ${
                isWin
                  ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                  : isLoss
                  ? 'bg-rose-500/15 border-rose-500/30 text-rose-400'
                  : 'bg-amber-500/15 border-amber-500/30 text-amber-400'
              }`}
            >
              {isWin ? (
                <ArrowUpRight className="w-5 h-5" />
              ) : isLoss ? (
                <ArrowDownRight className="w-5 h-5" />
              ) : (
                <Activity className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-extrabold text-white font-mono">{trade.symbol}</span>
                <span
                  className={`text-xs font-mono font-bold px-2 py-0.5 rounded-full border ${
                    trade.side === 'BUY'
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                  }`}
                >
                  {trade.side === 'BUY' ? 'LONG (BUY)' : 'SHORT (SELL)'}
                </span>
                <span className="text-xs font-mono text-slate-400 px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
                  #{trade.ticket}
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                Contract: <span className="text-cyan-300 font-semibold">{trade.strategyId}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              id="copy-trade-report-btn"
              type="button"
              onClick={handleCopyReport}
              className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-mono text-slate-300 hover:text-white transition flex items-center gap-1.5 shadow-sm"
              title="Copy trade report to clipboard"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-slate-400" />
                  <span>Copy Report</span>
                </>
              )}
            </button>

            <button
              id="close-trade-modal-btn"
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white transition border border-slate-700"
              aria-label="Close modal"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Realized Return Hero Pill Strip */}
        <div className="px-6 py-3.5 bg-slate-950/40 border-b border-slate-800/80 grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
          <div className="bg-slate-900/80 border border-slate-800 p-2.5 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Realized Return</span>
            <div className="flex items-baseline gap-1 mt-1">
              <span className={`text-base font-extrabold ${isWin ? 'text-emerald-400' : isLoss ? 'text-rose-400' : 'text-slate-300'}`}>
                {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
              </span>
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 p-2.5 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">R-Multiple Outcome</span>
            <div className="flex items-baseline gap-1 mt-1">
              <span className={`text-base font-extrabold ${trade.pnlR >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {trade.pnlR >= 0 ? `+${trade.pnlR.toFixed(2)}` : trade.pnlR.toFixed(2)} R
              </span>
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 p-2.5 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Pip Movement</span>
            <div className="flex items-baseline gap-1 mt-1">
              <span className={`text-base font-extrabold ${pipDiff >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {pipDiff >= 0 ? `+${pipDiff.toFixed(1)}` : pipDiff.toFixed(1)} pips
              </span>
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 p-2.5 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Holding Duration</span>
            <div className="flex items-baseline gap-1 mt-1 text-cyan-300 font-extrabold text-base">
              <Clock className="w-3.5 h-3.5 mr-1 text-cyan-400" />
              <span>{formatDuration(durationSeconds)}</span>
            </div>
          </div>
        </div>

        {/* Modal Main Body Scrollable */}
        <div className="p-6 space-y-5 max-h-[calc(85vh-200px)] overflow-y-auto">
          {/* SECTION 1: Exit Reasons & Milestone Breakdown */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-3 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
              <div className="flex items-center gap-2">
                <Target className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-sans">
                  Exit Reason & Execution Outcome
                </span>
              </div>
              <span className={`text-[10px] px-2.5 py-0.5 rounded-full border font-bold ${exitDetails.badgeColor}`}>
                {exitDetails.title}
              </span>
            </div>

            <p className="text-xs text-slate-300 font-sans leading-relaxed">
              {exitDetails.description}
            </p>

            {/* Exit Milestones Checklist */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1 text-xs">
              <div className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg flex items-center justify-between">
                <span className="text-slate-400 text-[11px]">TP1 Milestone (75%):</span>
                <span className={`flex items-center gap-1 font-bold ${trade.tp1Filled ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {trade.tp1Filled ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Executed (+3.0R)</span>
                    </>
                  ) : (
                    <span>Not Reached</span>
                  )}
                </span>
              </div>

              <div className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg flex items-center justify-between">
                <span className="text-slate-400 text-[11px]">Breakeven Stop (BE):</span>
                <span className={`flex items-center gap-1 font-bold ${trade.isBreakevenMoved ? 'text-cyan-400' : 'text-slate-500'}`}>
                  {trade.isBreakevenMoved ? (
                    <>
                      <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Advanced ({trade.entryPrice.toFixed(5)})</span>
                    </>
                  ) : (
                    <span>Original SL Kept</span>
                  )}
                </span>
              </div>
            </div>
          </div>

          {/* SECTION 2: Entry Signal & Level Geometry */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-3 font-mono">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2.5">
              <Zap className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-sans">
                Entry Signal & Price Parameters
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 block">Entry Price</span>
                <span className="text-slate-200 font-bold text-sm block mt-0.5">
                  {trade.entryPrice.toFixed(5)}
                </span>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 block">Stop Loss (1.0R)</span>
                <span className="text-rose-400 font-bold text-sm block mt-0.5">
                  {trade.stopLoss.toFixed(5)}
                </span>
                <span className="text-[10px] text-slate-500">(-{slPipRisk.toFixed(1)} pips)</span>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 block">Target 1 (75%)</span>
                <span className="text-emerald-400 font-bold text-sm block mt-0.5">
                  {trade.takeProfit1.toFixed(5)}
                </span>
                <span className="text-[10px] text-slate-500">(+{tp1Pips.toFixed(1)} pips)</span>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 block">Target 2 (25%)</span>
                <span className="text-cyan-400 font-bold text-sm block mt-0.5">
                  {trade.takeProfit2.toFixed(5)}
                </span>
                <span className="text-[10px] text-slate-500">(+{tp2Pips.toFixed(1)} pips)</span>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs pt-1">
              <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800/80 flex items-center justify-between">
                <span className="text-slate-400 text-[11px]">Position Size:</span>
                <span className="font-bold text-slate-200">{trade.volume} Lots</span>
              </div>
              <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800/80 flex items-center justify-between">
                <span className="text-slate-400 text-[11px]">Planned Risk:</span>
                <span className="font-bold text-rose-400">1.00 R</span>
              </div>
              <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800/80 flex items-center justify-between col-span-2 sm:col-span-1">
                <span className="text-slate-400 text-[11px]">Exit Price:</span>
                <span className="font-bold text-slate-200">{closeOrCurrentPrice.toFixed(5)}</span>
              </div>
            </div>
          </div>

          {/* SECTION 3: Duration & Timestamps Timeline */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-3 font-mono">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2.5">
              <Clock className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-sans">
                Trade Duration & Lifecycle Timeline
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 space-y-1">
                <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
                  <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Entry Execution Time</span>
                </div>
                <div className="text-slate-200 font-bold">{formatTimestamp(openTime)}</div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 space-y-1">
                <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
                  <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Final Exit Timestamp</span>
                </div>
                <div className="text-slate-200 font-bold">{formatTimestamp(closeTime)}</div>
              </div>
            </div>
          </div>

          {/* SECTION 4: Journal & Execution Notes */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-2.5 font-mono">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
              <FileText className="w-4 h-4 text-indigo-400" />
              <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-sans">
                Journal Notes & Strategy Audit
              </span>
            </div>

            {trade.journalNotes && trade.journalNotes.length > 0 ? (
              <ul className="space-y-1.5 text-xs text-slate-300 font-sans">
                {trade.journalNotes.map((note, idx) => (
                  <li key={idx} className="flex items-start gap-2 bg-slate-900/60 p-2 rounded-lg border border-slate-800/80">
                    <span className="text-cyan-400 font-mono font-bold mt-0.5">•</span>
                    <span className="leading-relaxed">{note}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-slate-500 italic">No custom journal notes recorded for this position.</div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between">
          <div className="text-[11px] font-mono text-slate-500">
            AG Profit Trading Deterministic Engine
          </div>
          <button
            id="modal-done-btn"
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white text-xs font-mono font-semibold transition border border-slate-700 shadow-sm"
          >
            Close Breakdown
          </button>
        </div>
      </div>
    </div>
  );
};
