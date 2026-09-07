import React, { useState, useMemo, useEffect } from 'react';
import {
  Calculator,
  DollarSign,
  Percent,
  ArrowRight,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Info,
  Check,
  RotateCcw,
  RotateCw,
  RefreshCw,
  Zap,
  Target
} from 'lucide-react';
import { OrderSide } from '../../types/trading';

interface PositionSizeCalculatorProps {
  initialSymbol?: string;
  initialSide?: OrderSide;
  initialEntryPrice?: number;
  initialStopLoss?: number;
  initialTp1?: number;
  initialTp2?: number;
  onApplyToOrder?: (params: {
    symbol: string;
    side: OrderSide;
    lots: number;
    entryPrice: number;
    stopLoss: number;
    takeProfit1: number;
    takeProfit2: number;
  }) => void;
}

// Symbol specification rules
interface SymbolSpec {
  name: string;
  pipSize: number; // 0.0001 for FX, 0.01 for JPY/XAU, 1 for BTC
  contractSize: number; // 100,000 for FX, 100 for Gold, 1 for BTC
  pipDecimalPlaces: number;
  priceDecimalPlaces: number;
  quoteCurrency: string;
  defaultPrice: number;
}

const SYMBOL_SPECS: Record<string, SymbolSpec> = {
  EURUSD: {
    name: 'EURUSD',
    pipSize: 0.0001,
    contractSize: 100000,
    pipDecimalPlaces: 1,
    priceDecimalPlaces: 5,
    quoteCurrency: 'USD',
    defaultPrice: 1.08500
  },
  GBPUSD: {
    name: 'GBPUSD',
    pipSize: 0.0001,
    contractSize: 100000,
    pipDecimalPlaces: 1,
    priceDecimalPlaces: 5,
    quoteCurrency: 'USD',
    defaultPrice: 1.29500
  },
  USDJPY: {
    name: 'USDJPY',
    pipSize: 0.01,
    contractSize: 100000,
    pipDecimalPlaces: 1,
    priceDecimalPlaces: 3,
    quoteCurrency: 'JPY',
    defaultPrice: 154.500
  },
  AUDUSD: {
    name: 'AUDUSD',
    pipSize: 0.0001,
    contractSize: 100000,
    pipDecimalPlaces: 1,
    priceDecimalPlaces: 5,
    quoteCurrency: 'USD',
    defaultPrice: 0.65500
  },
  XAUUSD: {
    name: 'XAUUSD (Gold)',
    pipSize: 0.10, // $0.10 per pip or 10 cents
    contractSize: 100, // 100 oz per lot
    pipDecimalPlaces: 1,
    priceDecimalPlaces: 2,
    quoteCurrency: 'USD',
    defaultPrice: 2420.00
  },
  BTCUSD: {
    name: 'BTCUSD (Bitcoin)',
    pipSize: 1.00, // $1.00 per point
    contractSize: 1,
    pipDecimalPlaces: 0,
    priceDecimalPlaces: 2,
    quoteCurrency: 'USD',
    defaultPrice: 63500.00
  }
};

const ACCOUNT_BALANCE_PRESETS = [1000, 2500, 5000, 10000, 25000];
const RISK_PCT_PRESETS = [0.25, 0.5, 1.0, 1.5, 2.0];

export const PositionSizeCalculator: React.FC<PositionSizeCalculatorProps> = ({
  initialSymbol = 'EURUSD',
  initialSide = 'BUY',
  initialEntryPrice,
  initialStopLoss,
  initialTp1,
  initialTp2,
  onApplyToOrder
}) => {
  // Account & Risk State
  const [balance, setBalance] = useState<number>(1000);
  const [brokerAccountId, setBrokerAccountId] = useState<number>(25972746);
  const [brokerVenue, setBrokerVenue] = useState<string>('Vantage');
  const [isSyncingBalance, setIsSyncingBalance] = useState<boolean>(false);
  const [riskMode, setRiskMode] = useState<'PERCENT' | 'FIXED_USD'>('PERCENT');
  const [riskPercent, setRiskPercent] = useState<number>(1.0);
  const [riskUsd, setRiskUsd] = useState<number>(10);

  // Sync balance and account ID from broker backend
  const syncBrokerAccount = async () => {
    try {
      setIsSyncingBalance(true);
      const res = await fetch('/api/broker/account');
      if (res.ok) {
        const data = await res.json();
        const acc = data?.account || data;
        if (acc?.balance && typeof acc.balance === 'number') {
          setBalance(acc.balance);
        }
        if (acc?.account_id) {
          setBrokerAccountId(acc.account_id);
        }
        if (acc?.broker) {
          setBrokerVenue(acc.broker);
        }
      }
    } catch {
      // Keep existing balance if offline
    } finally {
      setIsSyncingBalance(false);
    }
  };

  useEffect(() => {
    syncBrokerAccount();
    const handleBrokerUpdate = () => {
      syncBrokerAccount();
    };
    window.addEventListener('broker-balance-updated', handleBrokerUpdate);
    return () => {
      window.removeEventListener('broker-balance-updated', handleBrokerUpdate);
    };
  }, []);

  // Trade Setup State
  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [side, setSide] = useState<OrderSide>(initialSide);
  const spec = SYMBOL_SPECS[symbol] || SYMBOL_SPECS['EURUSD'];

  const [entryPrice, setEntryPrice] = useState<number>(
    initialEntryPrice ?? spec.defaultPrice
  );
  const [stopLoss, setStopLoss] = useState<number>(
    initialStopLoss ?? (initialSide === 'BUY' ? spec.defaultPrice * 0.998 : spec.defaultPrice * 1.002)
  );

  // Take profit targets
  const [tp1, setTp1] = useState<number>(
    initialTp1 ?? (initialSide === 'BUY' ? spec.defaultPrice * 1.004 : spec.defaultPrice * 0.996)
  );
  const [tp2, setTp2] = useState<number>(
    initialTp2 ?? (initialSide === 'BUY' ? spec.defaultPrice * 1.008 : spec.defaultPrice * 0.992)
  );

  const [appliedSuccess, setAppliedSuccess] = useState<boolean>(false);

  // Sync when initial props change (e.g. user selected another proposal)
  useEffect(() => {
    if (initialSymbol && SYMBOL_SPECS[initialSymbol]) {
      setSymbol(initialSymbol);
    }
    if (initialSide) {
      setSide(initialSide);
    }
    if (initialEntryPrice !== undefined) {
      setEntryPrice(initialEntryPrice);
    }
    if (initialStopLoss !== undefined) {
      setStopLoss(initialStopLoss);
    }
    if (initialTp1 !== undefined) {
      setTp1(initialTp1);
    }
    if (initialTp2 !== undefined) {
      setTp2(initialTp2);
    }
  }, [initialSymbol, initialSide, initialEntryPrice, initialStopLoss, initialTp1, initialTp2]);

  // When symbol changes, adjust default prices if not customized
  const handleSymbolChange = (newSymbol: string) => {
    setSymbol(newSymbol);
    const newSpec = SYMBOL_SPECS[newSymbol] || SYMBOL_SPECS['EURUSD'];
    const p = newSpec.defaultPrice;
    setEntryPrice(p);
    if (side === 'BUY') {
      const slDist = newSpec.pipSize * 20;
      setStopLoss(Number((p - slDist).toFixed(newSpec.priceDecimalPlaces)));
      setTp1(Number((p + slDist * 3).toFixed(newSpec.priceDecimalPlaces)));
      setTp2(Number((p + slDist * 5).toFixed(newSpec.priceDecimalPlaces)));
    } else {
      const slDist = newSpec.pipSize * 20;
      setStopLoss(Number((p + slDist).toFixed(newSpec.priceDecimalPlaces)));
      setTp1(Number((p - slDist * 3).toFixed(newSpec.priceDecimalPlaces)));
      setTp2(Number((p - slDist * 5).toFixed(newSpec.priceDecimalPlaces)));
    }
  };

  // Switch Side
  const handleSideChange = (newSide: OrderSide) => {
    setSide(newSide);
    const currentSlDist = Math.abs(entryPrice - stopLoss) || spec.pipSize * 20;
    if (newSide === 'BUY') {
      setStopLoss(Number((entryPrice - currentSlDist).toFixed(spec.priceDecimalPlaces)));
      setTp1(Number((entryPrice + currentSlDist * 3).toFixed(spec.priceDecimalPlaces)));
      setTp2(Number((entryPrice + currentSlDist * 5).toFixed(spec.priceDecimalPlaces)));
    } else {
      setStopLoss(Number((entryPrice + currentSlDist).toFixed(spec.priceDecimalPlaces)));
      setTp1(Number((entryPrice - currentSlDist * 3).toFixed(spec.priceDecimalPlaces)));
      setTp2(Number((entryPrice - currentSlDist * 5).toFixed(spec.priceDecimalPlaces)));
    }
  };

  // Perform Calculations
  const calculation = useMemo(() => {
    // 1. Monetary Risk
    const targetDollarRisk =
      riskMode === 'PERCENT' ? (balance * riskPercent) / 100 : riskUsd;

    // 2. Stop Loss Distance
    const priceDiff = Math.abs(entryPrice - stopLoss);
    const stopLossPips = spec.pipSize > 0 ? priceDiff / spec.pipSize : 0;

    // 3. Pip value per 1.0 standard lot in USD
    let pipValuePerLot = 10; // Default for EURUSD, GBPUSD, AUDUSD ($10/pip per 1.0 lot)
    if (symbol === 'USDJPY') {
      // 1 pip = 0.01 JPY * 100,000 units = 1,000 JPY -> in USD: 1000 / USDJPY rate
      pipValuePerLot = entryPrice > 0 ? 1000 / entryPrice : 6.5;
    } else if (symbol === 'XAUUSD') {
      // 100 oz * $0.10 pip = $10 per pip/point per 1.0 lot
      pipValuePerLot = 10;
    } else if (symbol === 'BTCUSD') {
      // 1 contract * $1 move = $1 per point per 1.0 lot
      pipValuePerLot = 1;
    }

    // 4. Exact lots calculation
    const lossPerLot = stopLossPips * pipValuePerLot;
    let rawLots = lossPerLot > 0 ? targetDollarRisk / lossPerLot : 0.01;

    // Clamp and round to 2 decimal places (standard MT5 step 0.01)
    let calculatedLots = Math.round(rawLots * 100) / 100;
    if (calculatedLots < 0.01) calculatedLots = 0.01;
    if (calculatedLots > 50) calculatedLots = 50;

    // Effective dollar risk with rounded lots
    const actualDollarRisk = calculatedLots * stopLossPips * pipValuePerLot;
    const actualRiskPct = balance > 0 ? (actualDollarRisk / balance) * 100 : 0;

    // 5. Take Profit 1 and 2 calculations
    const tp1PriceDiff = Math.abs(tp1 - entryPrice);
    const tp1Pips = spec.pipSize > 0 ? tp1PriceDiff / spec.pipSize : 0;
    const tp1RMultiple = stopLossPips > 0 ? tp1Pips / stopLossPips : 0;
    // 75% partial split volume
    const tp1Lots = Math.max(0.01, Math.round(calculatedLots * 0.75 * 100) / 100);
    const tp1ProfitUsd = tp1Lots * tp1Pips * pipValuePerLot;

    const tp2PriceDiff = Math.abs(tp2 - entryPrice);
    const tp2Pips = spec.pipSize > 0 ? tp2PriceDiff / spec.pipSize : 0;
    const tp2RMultiple = stopLossPips > 0 ? tp2Pips / stopLossPips : 0;
    // 25% runner volume
    const tp2Lots = Math.max(0.01, Math.round((calculatedLots - tp1Lots) * 100) / 100);
    const tp2ProfitUsd = tp2Lots * tp2Pips * pipValuePerLot;

    const totalPotentialProfit = tp1ProfitUsd + tp2ProfitUsd;
    const combinedR = actualDollarRisk > 0 ? totalPotentialProfit / actualDollarRisk : 0;

    // Validity checks
    const isStopValid =
      side === 'BUY' ? stopLoss < entryPrice : stopLoss > entryPrice;
    const isTp1Valid = side === 'BUY' ? tp1 > entryPrice : tp1 < entryPrice;
    const isTp2Valid = side === 'BUY' ? tp2 > entryPrice : tp2 < entryPrice;

    return {
      targetDollarRisk,
      stopLossPips,
      pipValuePerLot,
      calculatedLots,
      actualDollarRisk,
      actualRiskPct,
      tp1Pips,
      tp1RMultiple,
      tp1Lots,
      tp1ProfitUsd,
      tp2Pips,
      tp2RMultiple,
      tp2Lots,
      tp2ProfitUsd,
      totalPotentialProfit,
      combinedR,
      isStopValid,
      isTp1Valid,
      isTp2Valid
    };
  }, [balance, riskMode, riskPercent, riskUsd, symbol, side, entryPrice, stopLoss, tp1, tp2, spec]);

  const handleApply = () => {
    if (!onApplyToOrder) return;
    onApplyToOrder({
      symbol,
      side,
      lots: calculation.calculatedLots,
      entryPrice,
      stopLoss,
      takeProfit1: tp1,
      takeProfit2: tp2
    });
    setAppliedSuccess(true);
    setTimeout(() => setAppliedSuccess(false), 2500);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md space-y-4 font-mono">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-cyan-500/10 border border-cyan-500/30 rounded-lg text-cyan-400">
            <Calculator className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
              Position Size & Risk Calculator
            </h3>
            <p className="text-[10px] text-slate-400">
              Deterministic MT5 lot sizing based on account equity & SL distance
            </p>
          </div>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/30">
          RISK GUARD ACTIVE
        </span>
      </div>

      {/* Account Balance & Risk Setting */}
      <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800/80 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Balance Input */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[11px] text-slate-400 font-semibold flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-cyan-400" />
                <span>Account Balance ($)</span>
                <span className="text-[10px] text-slate-500 font-normal">
                  • {brokerVenue} #{brokerAccountId}
                </span>
              </label>
              <button
                type="button"
                onClick={syncBrokerAccount}
                disabled={isSyncingBalance}
                title="Sync balance from MT5 broker"
                className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 transition cursor-pointer"
              >
                <RefreshCw className={`w-2.5 h-2.5 ${isSyncingBalance ? 'animate-spin' : ''}`} />
                <span>{isSyncingBalance ? 'Syncing...' : 'Sync'}</span>
              </button>
            </div>
            <input
              id="calc-balance-input"
              type="number"
              min="100"
              step="500"
              value={balance}
              onChange={e => setBalance(Math.max(100, Number(e.target.value)))}
              className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-100 font-bold focus:border-cyan-500 focus:outline-none"
            />
            {/* Quick Balance Presets */}
            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
              {ACCOUNT_BALANCE_PRESETS.map(preset => (
                <button
                  key={preset}
                  onClick={() => setBalance(preset)}
                  className={`px-1.5 py-0.5 text-[9px] rounded font-semibold transition ${
                    balance === preset
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  ${(preset / 1000).toFixed(0)}k
                </button>
              ))}
            </div>
          </div>

          {/* Risk Mode & Percentage */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[11px] text-slate-400 font-semibold flex items-center gap-1">
                <Percent className="w-3 h-3 text-cyan-400" />
                <span>Risk per Trade</span>
              </label>
              <div className="flex items-center gap-1 text-[10px]">
                <button
                  onClick={() => setRiskMode('PERCENT')}
                  className={`px-1.5 py-0.2 rounded font-bold transition ${
                    riskMode === 'PERCENT'
                      ? 'bg-cyan-600 text-white'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  %
                </button>
                <button
                  onClick={() => setRiskMode('FIXED_USD')}
                  className={`px-1.5 py-0.2 rounded font-bold transition ${
                    riskMode === 'FIXED_USD'
                      ? 'bg-cyan-600 text-white'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  $
                </button>
              </div>
            </div>

            {riskMode === 'PERCENT' ? (
              <>
                <input
                  id="calc-risk-pct-input"
                  type="number"
                  min="0.1"
                  max="10"
                  step="0.1"
                  value={riskPercent}
                  onChange={e => setRiskPercent(Math.max(0.1, Number(e.target.value)))}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-100 font-bold focus:border-cyan-500 focus:outline-none"
                />
                <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                  {RISK_PCT_PRESETS.map(pct => (
                    <button
                      key={pct}
                      onClick={() => setRiskPercent(pct)}
                      className={`px-1.5 py-0.5 text-[9px] rounded font-semibold transition ${
                        riskPercent === pct
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                          : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                      }`}
                    >
                      {pct}%
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <input
                id="calc-risk-usd-input"
                type="number"
                min="10"
                step="25"
                value={riskUsd}
                onChange={e => setRiskUsd(Math.max(1, Number(e.target.value)))}
                className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-100 font-bold focus:border-cyan-500 focus:outline-none"
              />
            )}
          </div>
        </div>

        {/* Risk Summary Badge */}
        <div className="flex items-center justify-between pt-1 border-t border-slate-900 text-[11px]">
          <span className="text-slate-400">Target Monetary Risk:</span>
          <span className="text-amber-400 font-bold">
            ${calculation.targetDollarRisk.toFixed(2)} ({riskMode === 'PERCENT' ? `${riskPercent.toFixed(2)}%` : `${((riskUsd / balance) * 100).toFixed(2)}%`})
          </span>
        </div>
      </div>

      {/* Trade Setup Matrix */}
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3 text-xs">
          {/* Symbol */}
          <div>
            <label className="text-slate-400 block mb-1 font-semibold">Instrument</label>
            <select
              id="calc-symbol-select"
              value={symbol}
              onChange={e => handleSymbolChange(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-cyan-300 font-bold focus:border-cyan-500 focus:outline-none"
            >
              {Object.keys(SYMBOL_SPECS).map(s => (
                <option key={s} value={s}>
                  {SYMBOL_SPECS[s].name}
                </option>
              ))}
            </select>
          </div>

          {/* Side (BUY / SELL) */}
          <div>
            <label className="text-slate-400 block mb-1 font-semibold">Direction</label>
            <div className="grid grid-cols-2 gap-1">
              <button
                type="button"
                onClick={() => handleSideChange('BUY')}
                className={`py-1.5 rounded text-xs font-bold transition ${
                  side === 'BUY'
                    ? 'bg-emerald-500 text-slate-950 shadow-sm'
                    : 'bg-slate-950 text-slate-400 border border-slate-800'
                }`}
              >
                BUY
              </button>
              <button
                type="button"
                onClick={() => handleSideChange('SELL')}
                className={`py-1.5 rounded text-xs font-bold transition ${
                  side === 'SELL'
                    ? 'bg-rose-500 text-slate-100 shadow-sm'
                    : 'bg-slate-950 text-slate-400 border border-slate-800'
                }`}
              >
                SELL
              </button>
            </div>
          </div>
        </div>

        {/* Entry Price & Stop Loss */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1 font-semibold">Entry Price</label>
            <input
              id="calc-entry-price"
              type="number"
              step={spec.pipSize}
              value={entryPrice}
              onChange={e => setEntryPrice(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-100 font-bold focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-semibold flex items-center justify-between">
              <span>Stop Loss</span>
              <span className="text-[10px] text-rose-400 font-bold">
                {calculation.stopLossPips.toFixed(spec.pipDecimalPlaces)} pips
              </span>
            </label>
            <input
              id="calc-stop-loss"
              type="number"
              step={spec.pipSize}
              value={stopLoss}
              onChange={e => setStopLoss(Number(e.target.value))}
              className={`w-full bg-slate-950 border rounded px-2.5 py-1.5 font-bold focus:outline-none ${
                calculation.isStopValid
                  ? 'border-slate-800 text-rose-300 focus:border-cyan-500'
                  : 'border-rose-500 text-rose-400 bg-rose-950/20'
              }`}
            />
          </div>
        </div>

        {!calculation.isStopValid && (
          <div className="flex items-center gap-1.5 p-2 bg-rose-950/40 border border-rose-800/80 rounded text-[11px] text-rose-300">
            <ShieldAlert className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            <span>Invalid Stop Loss: For a {side} order, SL must be {side === 'BUY' ? 'below' : 'above'} entry ({entryPrice}).</span>
          </div>
        )}

        {/* TP1 & TP2 Targets */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1 font-semibold flex items-center justify-between">
              <span>TP1 (75% Split)</span>
              <span className="text-[10px] text-emerald-400 font-bold">
                {calculation.tp1RMultiple.toFixed(1)}R
              </span>
            </label>
            <input
              id="calc-tp1-input"
              type="number"
              step={spec.pipSize}
              value={tp1}
              onChange={e => setTp1(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-emerald-300 font-bold focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1 font-semibold flex items-center justify-between">
              <span>TP2 (25% Runner)</span>
              <span className="text-[10px] text-cyan-400 font-bold">
                {calculation.tp2RMultiple.toFixed(1)}R
              </span>
            </label>
            <input
              id="calc-tp2-input"
              type="number"
              step={spec.pipSize}
              value={tp2}
              onChange={e => setTp2(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-cyan-300 font-bold focus:border-cyan-500 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Calculated Output Card */}
      <div className="bg-gradient-to-br from-slate-950 to-slate-900 p-4 rounded-xl border border-cyan-500/30 space-y-3 shadow-lg">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-cyan-400" />
            Recommended Position Size
          </span>
          <div className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-xs font-bold border border-cyan-500/40">
            {calculation.calculatedLots.toFixed(2)} Lots
          </div>
        </div>

        {/* Primary Metric Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono">
          <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400">Total Sizing</div>
            <div className="text-sm font-bold text-cyan-400">
              {calculation.calculatedLots.toFixed(2)} Lots
            </div>
            <div className="text-[9px] text-slate-500 mt-0.5">
              ${(calculation.calculatedLots * calculation.pipValuePerLot).toFixed(2)} / pip
            </div>
          </div>

          <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400">Risk Amount</div>
            <div className="text-sm font-bold text-rose-400">
              -${calculation.actualDollarRisk.toFixed(2)}
            </div>
            <div className="text-[9px] text-slate-500 mt-0.5">
              {calculation.actualRiskPct.toFixed(2)}% of balance
            </div>
          </div>

          <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400">SL Distance</div>
            <div className="text-sm font-bold text-amber-400">
              {calculation.stopLossPips.toFixed(1)} Pips
            </div>
            <div className="text-[9px] text-slate-500 mt-0.5">
              {Math.abs(entryPrice - stopLoss).toFixed(spec.priceDecimalPlaces)} pts
            </div>
          </div>

          <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] text-slate-400">Combined Target</div>
            <div className="text-sm font-bold text-emerald-400">
              +${calculation.totalPotentialProfit.toFixed(2)}
            </div>
            <div className="text-[9px] text-slate-500 mt-0.5">
              +{calculation.combinedR.toFixed(2)}R payoff
            </div>
          </div>
        </div>

        {/* Execution Split Roadmap */}
        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/80 space-y-1.5 text-[11px]">
          <div className="text-[10px] text-slate-400 font-semibold uppercase flex items-center justify-between">
            <span>Deterministic 2-Leg Execution Split</span>
            <span className="text-cyan-400 font-mono">1.00R = ${calculation.actualDollarRisk.toFixed(2)}</span>
          </div>

          <div className="grid grid-cols-2 gap-2 pt-0.5">
            <div className="p-1.5 bg-slate-900 rounded border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-emerald-400 font-bold">Leg 1 (75%)</span>
                <div className="text-[10px] text-slate-400">
                  {calculation.tp1Lots.toFixed(2)} lots @ {calculation.tp1RMultiple.toFixed(1)}R
                </div>
              </div>
              <span className="text-emerald-300 font-bold">
                +${calculation.tp1ProfitUsd.toFixed(2)}
              </span>
            </div>

            <div className="p-1.5 bg-slate-900 rounded border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-cyan-400 font-bold">Leg 2 (25%)</span>
                <div className="text-[10px] text-slate-400">
                  {calculation.tp2Lots.toFixed(2)} lots @ {calculation.tp2RMultiple.toFixed(1)}R
                </div>
              </div>
              <span className="text-cyan-300 font-bold">
                +${calculation.tp2ProfitUsd.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Transfer to Order Form Action Button */}
        {onApplyToOrder && (
          <button
            id="btn-apply-calc-to-order"
            type="button"
            onClick={handleApply}
            disabled={!calculation.isStopValid}
            className={`w-full py-2.5 rounded-lg font-bold text-xs flex items-center justify-center gap-2 transition shadow-md ${
              appliedSuccess
                ? 'bg-emerald-500 text-slate-950'
                : calculation.isStopValid
                ? 'bg-cyan-500 hover:bg-cyan-400 text-slate-950 cursor-pointer'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            {appliedSuccess ? (
              <>
                <Check className="w-4 h-4 text-slate-950 stroke-[3]" />
                <span>Applied to Order Execution Form!</span>
              </>
            ) : (
              <>
                <ArrowRight className="w-4 h-4" />
                <span>Apply {calculation.calculatedLots.toFixed(2)} Lots to Order Form</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
