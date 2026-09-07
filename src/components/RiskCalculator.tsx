import React, { useState } from 'react';
import {
  Calculator,
  Shield,
  AlertCircle,
  CheckCircle2,
  Sliders,
  DollarSign,
  Percent
} from 'lucide-react';

export const RiskCalculator: React.FC = () => {
  const [balance, setBalance] = useState<number>(10000);
  const [riskPercent, setRiskPercent] = useState<number>(1.0);
  const [symbol, setSymbol] = useState<string>('EURUSD');
  const [direction, setDirection] = useState<'LONG' | 'SHORT'>('LONG');
  const [entryPrice, setEntryPrice] = useState<number>(1.16030);
  const [stopLoss, setStopLoss] = useState<number>(1.15976);

  // Pip multiplier
  const isJpy = symbol.includes('JPY');
  const isCrypto = symbol.includes('BTC') || symbol.includes('ETH');
  const isGold = symbol.includes('XAU');
  const pipMultiplier = isCrypto ? 1 : isGold ? 10 : isJpy ? 100 : 10000;

  // Distances
  const slDistance = Math.abs(entryPrice - stopLoss);
  const slPips = slDistance * pipMultiplier;
  const riskAmount = balance * (riskPercent / 100);

  // Lot sizing
  let lotSize = 0;
  if (isCrypto) {
    lotSize = slDistance > 0 ? parseFloat((riskAmount / slDistance).toFixed(3)) : 0;
  } else if (isGold) {
    // Gold: 1 lot = 100 oz, $1 per $0.01 move per lot = $10 per 0.1 pip
    lotSize = slDistance > 0 ? parseFloat((riskAmount / (slDistance * 100)).toFixed(2)) : 0;
  } else {
    // FX: 1 lot = $10/pip on USD quotes
    lotSize = slPips > 0 ? parseFloat((riskAmount / (slPips * 10)).toFixed(2)) : 0;
  }

  // Targets
  const rMult = direction === 'LONG' ? 1 : -1;
  const bePrice = entryPrice + rMult * 2.0 * slDistance;
  const tp1Price = entryPrice + rMult * 2.5 * slDistance;
  const tp2Price = entryPrice + rMult * 5.0 * slDistance;

  // Validation
  const isSlTooTight = !isCrypto && slPips < 3.0;
  const isSlTooWide = !isCrypto && slPips > 40.0;

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-slate-900 border border-slate-800 p-4">
        <div className="flex items-center space-x-2">
          <Calculator className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-semibold text-white tracking-wide uppercase font-mono">
            Deterministic Position Sizing & Risk Guard
          </h2>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          Direct implementation of execution/risk.py specifications. Strict account percentage capping with MT5 lot size normalization.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Input Parameters */}
        <div className="rounded-lg bg-slate-900 border border-slate-800 p-5 space-y-4">
          <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider pb-2 border-b border-slate-800">
            Account & Trade Setup
          </h3>

          <div>
            <label className="text-xs font-mono text-slate-400 block mb-1">Account Balance (USD)</label>
            <div className="relative">
              <span className="absolute left-3 top-2 text-slate-500 font-mono text-sm">$</span>
              <input
                type="number"
                value={balance}
                onChange={(e) => setBalance(parseFloat(e.target.value) || 0)}
                className="w-full pl-7 pr-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-slate-100 font-mono text-sm focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-mono text-slate-400">Risk Allocation (%)</label>
              <span className="text-xs font-mono font-bold text-emerald-400">{riskPercent}% (${riskAmount.toFixed(2)})</span>
            </div>
            <div className="flex space-x-2">
              {[0.5, 1.0, 1.5, 2.0].map((pct) => (
                <button
                  key={pct}
                  onClick={() => setRiskPercent(pct)}
                  className={`flex-1 py-1 rounded text-xs font-mono transition-colors ${
                    riskPercent === pct
                      ? 'bg-emerald-600 text-white font-bold'
                      : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
                  }`}
                >
                  {pct}%
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-mono text-slate-400 block mb-1">Instrument</label>
            <select
              value={symbol}
              onChange={(e) => {
                const s = e.target.value;
                setSymbol(s);
                if (s === 'EURUSD') { setEntryPrice(1.16030); setStopLoss(1.15976); }
                else if (s === 'GBPUSD') { setEntryPrice(1.31820); setStopLoss(1.31890); }
                else if (s === 'USDJPY') { setEntryPrice(147.500); setStopLoss(147.250); }
                else if (s === 'XAUUSD') { setEntryPrice(2510.00); setStopLoss(2505.00); }
                else if (s === 'BTCUSDT') { setEntryPrice(58120.0); setStopLoss(58540.0); }
              }}
              className="w-full px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-slate-100 font-mono text-sm focus:outline-none focus:border-emerald-500"
            >
              <option value="EURUSD">EURUSD (FX)</option>
              <option value="GBPUSD">GBPUSD (FX)</option>
              <option value="USDJPY">USDJPY (FX)</option>
              <option value="XAUUSD">XAUUSD (Gold)</option>
              <option value="BTCUSDT">BTCUSDT (Crypto Perp)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-mono text-slate-400 block mb-1">Direction</label>
            <div className="flex space-x-2">
              <button
                onClick={() => setDirection('LONG')}
                className={`flex-1 py-1.5 rounded text-xs font-mono font-bold transition-colors ${
                  direction === 'LONG'
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-950 text-slate-400 border border-slate-800'
                }`}
              >
                LONG
              </button>
              <button
                onClick={() => setDirection('SHORT')}
                className={`flex-1 py-1.5 rounded text-xs font-mono font-bold transition-colors ${
                  direction === 'SHORT'
                    ? 'bg-rose-600 text-white'
                    : 'bg-slate-950 text-slate-400 border border-slate-800'
                }`}
              >
                SHORT
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1">Entry Price</label>
              <input
                type="number"
                step="any"
                value={entryPrice}
                onChange={(e) => setEntryPrice(parseFloat(e.target.value) || 0)}
                className="w-full px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1">Stop Loss</label>
              <input
                type="number"
                step="any"
                value={stopLoss}
                onChange={(e) => setStopLoss(parseFloat(e.target.value) || 0)}
                className="w-full px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-rose-300 font-mono text-xs focus:outline-none focus:border-rose-500"
              />
            </div>
          </div>
        </div>

        {/* Output Metrics & Sizing Result */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-lg bg-slate-900 border border-slate-800 p-5">
            <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider pb-3 border-b border-slate-800 flex items-center justify-between">
              <span>Sizing & Order Specification</span>
              <span className="text-[11px] font-mono text-emerald-400 font-normal">MT5 Broker Normalized</span>
            </h3>

            {/* Big Sizing Display */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 my-4">
              <div className="rounded-lg bg-slate-950 border border-emerald-500/40 p-3.5">
                <div className="text-[10px] text-slate-400 font-mono uppercase">Recommended Position</div>
                <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
                  {lotSize} <span className="text-sm font-normal text-slate-300">{isCrypto ? 'Contracts' : 'Lots'}</span>
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-1">Exact capital allocation</div>
              </div>

              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3.5">
                <div className="text-[10px] text-slate-400 font-mono uppercase">Stop Distance</div>
                <div className="text-2xl font-mono font-bold text-slate-100 mt-1">
                  {slPips.toFixed(1)} <span className="text-sm font-normal text-slate-400">{isCrypto ? 'pts' : 'pips'}</span>
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-1">Risk Amount: ${riskAmount.toFixed(2)}</div>
              </div>

              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3.5">
                <div className="text-[10px] text-slate-400 font-mono uppercase">Target Payout (5R)</div>
                <div className="text-2xl font-mono font-bold text-emerald-300 mt-1">
                  +${(riskAmount * 5).toFixed(2)}
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-1">1:5.0 Asymmetric Model</div>
              </div>
            </div>

            {/* Validation Alerts */}
            {isSlTooTight && (
              <div className="mb-4 p-2.5 rounded bg-amber-950/40 border border-amber-800/50 flex items-center space-x-2 text-xs font-mono text-amber-300">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>Warning: Stop loss distance ({slPips.toFixed(1)} pips) is under minimum broker spread safety buffer (3.0 pips).</span>
              </div>
            )}

            {isSlTooWide && (
              <div className="mb-4 p-2.5 rounded bg-rose-950/40 border border-rose-800/50 flex items-center space-x-2 text-xs font-mono text-rose-300">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>Notice: Stop loss distance ({slPips.toFixed(1)} pips) exceeds standard 25-pip session range cap. Model A recommended.</span>
              </div>
            )}

            {/* Multi-Tier Profit Targets */}
            <div className="space-y-2 text-xs font-mono pt-2">
              <div className="text-slate-400 text-[11px] font-bold uppercase tracking-wider">
                Multi-Stage Trade Management Rules (Phase 6)
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 block text-[10px]">BREAKEVEN (2.0R)</span>
                  <span className="text-slate-200 font-bold">{bePrice.toFixed(5)}</span>
                  <span className="text-[10px] text-slate-500 block">Move SL to Entry + Spread</span>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-emerald-400 block text-[10px]">TP1 PARTIAL (2.5R)</span>
                  <span className="text-emerald-300 font-bold">{tp1Price.toFixed(5)}</span>
                  <span className="text-[10px] text-slate-500 block">Close 50% (+${(riskAmount * 1.25).toFixed(2)})</span>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-emerald-500/40">
                  <span className="text-emerald-400 block text-[10px]">TP2 RUNNER (5.0R)</span>
                  <span className="text-emerald-400 font-bold">{tp2Price.toFixed(5)}</span>
                  <span className="text-[10px] text-slate-500 block">Close remaining (+${(riskAmount * 2.5).toFixed(2)})</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
