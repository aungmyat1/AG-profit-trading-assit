import React, { useState } from 'react';
import { OpenPosition, SymbolName } from '../../types/trading';
import {
  ShieldAlert,
  Sliders,
  DollarSign,
  CheckCircle2,
  X,
  AlertTriangle,
  Send,
  PlusCircle,
  HelpCircle,
} from 'lucide-react';

interface ExecutionCockpitProps {
  positions: OpenPosition[];
  onSetBreakeven: (ticket: number) => void;
  onPartialClose: (ticket: number) => void;
  onClosePosition: (ticket: number) => void;
  onClaimTicket: (ticket: number) => void;
  onSubmitOrder: (order: {
    symbol: SymbolName;
    type: 'BUY' | 'SELL';
    lots: number;
    sl: number;
    tp: number;
    userConfirmed: boolean;
  }) => void;
  activeSymbol: SymbolName;
}

export const ExecutionCockpit: React.FC<ExecutionCockpitProps> = ({
  positions,
  onSetBreakeven,
  onPartialClose,
  onClosePosition,
  onClaimTicket,
  onSubmitOrder,
  activeSymbol,
}) => {
  const [claimInput, setClaimInput] = useState('');
  const [claimMsg, setClaimMsg] = useState('');

  // New Order State
  const [showOrderModal, setShowOrderModal] = useState(false);
  const [orderType, setOrderType] = useState<'BUY' | 'SELL'>('BUY');
  const [orderLots, setOrderLots] = useState('0.50');
  const [orderSl, setOrderSl] = useState('');
  const [orderTp, setOrderTp] = useState('');
  const [userConfirmed, setUserConfirmed] = useState(false);
  const [orderError, setOrderError] = useState('');

  const handleClaimSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = parseInt(claimInput, 10);
    if (isNaN(t) || t <= 0) {
      setClaimMsg('Please enter a valid numeric ticket.');
      return;
    }
    onClaimTicket(t);
    setClaimMsg(`Claimed ticket #${t} into deterministic management.`);
    setClaimInput('');
  };

  const handleExecuteOrder = () => {
    if (!userConfirmed) {
      setOrderError('Execution rejected: Explicit user confirmation required (user_confirmed=True).');
      return;
    }
    const lots = parseFloat(orderLots);
    if (isNaN(lots) || lots <= 0) {
      setOrderError('Invalid lot size.');
      return;
    }
    setOrderError('');
    onSubmitOrder({
      symbol: activeSymbol,
      type: orderType,
      lots,
      sl: parseFloat(orderSl) || 0,
      tp: parseFloat(orderTp) || 0,
      userConfirmed: true,
    });
    setShowOrderModal(false);
    setUserConfirmed(false);
  };

  const totalPnl = positions.reduce((acc, p) => acc + p.pnl, 0);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-5 shadow-sm">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-emerald-400" />
            <h3 className="font-extrabold text-white text-base tracking-wide">
              EXECUTION & RISK MANAGEMENT COCKPIT
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono">
            Deterministic Position Monitor & MT5 Trade Management Bridge (Phase 6)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-mono">
            <span className="text-slate-400">Net Floating P&L: </span>
            <span
              className={`font-bold text-sm ${
                totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)} USD
            </span>
          </div>

          <button
            type="button"
            onClick={() => setShowOrderModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs font-mono transition shadow-sm"
          >
            <PlusCircle className="w-4 h-4" />
            <span>New Demo Order</span>
          </button>
        </div>
      </div>

      {/* Positions Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left font-mono text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 text-[10px] uppercase bg-slate-950/60">
              <th className="py-2.5 px-3">Ticket</th>
              <th className="py-2.5 px-3">Symbol</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3">Lots</th>
              <th className="py-2.5 px-3">Open</th>
              <th className="py-2.5 px-3">Current</th>
              <th className="py-2.5 px-3">SL / TP</th>
              <th className="py-2.5 px-3">P&L ($)</th>
              <th className="py-2.5 px-3 text-right">Deterministic Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {positions.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-500">
                  Zero open positions reported. Claim an existing manual ticket below or execute a verified proposal.
                </td>
              </tr>
            ) : (
              positions.map((p) => {
                const isBuy = p.type === 'BUY';
                return (
                  <tr key={p.ticket} className="hover:bg-slate-800/40 transition">
                    <td className="py-3 px-3 text-slate-300 font-semibold">#{p.ticket}</td>
                    <td className="py-3 px-3 font-bold text-white">{p.symbol}</td>
                    <td className="py-3 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          isBuy ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}
                      >
                        {p.type}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-slate-200">{p.lots.toFixed(2)}</td>
                    <td className="py-3 px-3 text-slate-300">{p.openPrice}</td>
                    <td className="py-3 px-3 font-semibold text-white">{p.currentPrice}</td>
                    <td className="py-3 px-3 text-[11px]">
                      <span className={p.isBreakeven ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
                        {p.sl}
                      </span>{' '}
                      / <span className="text-slate-400">{p.tp}</span>
                      {p.isBreakeven && (
                        <span className="ml-1 text-[9px] px-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                          BE
                        </span>
                      )}
                    </td>
                    <td
                      className={`py-3 px-3 font-bold ${
                        p.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)} ({p.pips > 0 ? '+' : ''}{p.pips} pips)
                    </td>
                    <td className="py-3 px-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {!p.isBreakeven && (
                          <button
                            type="button"
                            onClick={() => onSetBreakeven(p.ticket)}
                            title="Move Stop Loss to Entry Price (Breakeven)"
                            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[10px] transition"
                          >
                            Set BE
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => onPartialClose(p.ticket)}
                          title="Take 50% partial profit"
                          className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-indigo-900/60 text-[10px] transition"
                        >
                          Partial 50%
                        </button>
                        <button
                          type="button"
                          onClick={() => onClosePosition(p.ticket)}
                          title="Close position immediately"
                          className="px-2 py-1 rounded bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 text-[10px] transition"
                        >
                          Close
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Manual Ticket Claim Area */}
      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-slate-300">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
              <span>Claim Manual-Entry Trade (Phase 6 Authority)</span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono mt-0.5">
              Delegates to <code className="text-slate-300">scripts/manage_trade.py claim &lt;ticket&gt;</code>. Never opens a position; manages claimed tickets only.
            </p>
          </div>

          <form onSubmit={handleClaimSubmit} className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Ticket # (e.g. 9104592)"
              value={claimInput}
              onChange={(e) => setClaimInput(e.target.value)}
              className="bg-slate-900 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-mono text-white placeholder:text-slate-600 focus:outline-none focus:border-emerald-500 w-44"
            />
            <button
              type="submit"
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono transition"
            >
              Claim Ticket
            </button>
          </form>
        </div>
        {claimMsg && <p className="text-emerald-400 text-xs font-mono mt-2">{claimMsg}</p>}
      </div>

      {/* Modal for Order Execution */}
      {showOrderModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 max-w-md w-full shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <Send className="w-4 h-4 text-emerald-400" />
                <h4 className="font-extrabold text-white text-sm font-mono uppercase tracking-wide">
                  Execute Demo Order ({activeSymbol})
                </h4>
              </div>
              <button
                type="button"
                onClick={() => setShowOrderModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex flex-col gap-3 font-mono text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Direction</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setOrderType('BUY')}
                    className={`py-2 rounded font-bold transition border ${
                      orderType === 'BUY'
                        ? 'bg-emerald-600 text-white border-emerald-500'
                        : 'bg-slate-950 text-slate-400 border-slate-800'
                    }`}
                  >
                    BUY / LONG
                  </button>
                  <button
                    type="button"
                    onClick={() => setOrderType('SELL')}
                    className={`py-2 rounded font-bold transition border ${
                      orderType === 'SELL'
                        ? 'bg-rose-600 text-white border-rose-500'
                        : 'bg-slate-950 text-slate-400 border-slate-800'
                    }`}
                  >
                    SELL / SHORT
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Lot Size</label>
                <input
                  type="text"
                  value={orderLots}
                  onChange={(e) => setOrderLots(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 px-3 py-1.5 rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-400 mb-1">Stop Loss (SL)</label>
                  <input
                    type="text"
                    placeholder="Optional"
                    value={orderSl}
                    onChange={(e) => setOrderSl(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 px-3 py-1.5 rounded text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Take Profit (TP)</label>
                  <input
                    type="text"
                    placeholder="Optional"
                    value={orderTp}
                    onChange={(e) => setOrderTp(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 px-3 py-1.5 rounded text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Mandatory User Confirmation Checkbox */}
              <div className="bg-slate-950 p-3 rounded border border-amber-900/60 mt-2">
                <label className="flex items-start gap-2.5 cursor-pointer text-[11px] text-slate-300">
                  <input
                    type="checkbox"
                    checked={userConfirmed}
                    onChange={(e) => setUserConfirmed(e.target.checked)}
                    className="mt-0.5 rounded border-slate-700 text-emerald-500 focus:ring-0"
                  />
                  <span>
                    <strong>Required Authority Check:</strong> I explicitly authorize submission of this order to VantageMarkets-Demo. (Derived from non-defaulted user_confirmed=True).
                  </span>
                </label>
              </div>

              {orderError && (
                <p className="text-rose-400 text-[11px] flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {orderError}
                </p>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800 mt-2">
                <button
                  type="button"
                  onClick={() => setShowOrderModal(false)}
                  className="px-4 py-2 rounded text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleExecuteOrder}
                  className="px-5 py-2 rounded bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition"
                >
                  Submit Order
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
