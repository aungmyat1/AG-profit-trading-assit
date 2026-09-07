import React, { useState, useMemo, useEffect } from 'react';
import {
  Calculator,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Check,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal,
  Target,
  DollarSign,
  Percent,
  Zap,
  Coins,
  BarChart3,
  Flame,
  ArrowUpRight,
  HelpCircle
} from 'lucide-react';
import { OrderSide } from '../../types/trading';

export interface QuickRiskCalculatorProps {
  symbol: string;
  side: OrderSide;
  entryPrice: number;
  stopLoss: number;
  takeProfit1?: number;
  takeProfit2?: number;
  liveEquity?: number;
  currentLots: number;
  onApplyLots: (suggestedLots: number, updatedStopLoss?: number) => void;
  onApplyTakeProfits?: (tp1: number, tp2: number) => void;
  className?: string;
}

interface SymbolSpec {
  name: string;
  pipSize: number;
  contractSize: number;
  pipDecimalPlaces: number;
  priceDecimalPlaces: number;
  quoteCurrency: string;
}

const SYMBOL_SPECS: Record<string, SymbolSpec> = {
  EURUSD: { name: 'EURUSD', pipSize: 0.0001, contractSize: 100000, pipDecimalPlaces: 1, priceDecimalPlaces: 5, quoteCurrency: 'USD' },
  GBPUSD: { name: 'GBPUSD', pipSize: 0.0001, contractSize: 100000, pipDecimalPlaces: 1, priceDecimalPlaces: 5, quoteCurrency: 'USD' },
  USDJPY: { name: 'USDJPY', pipSize: 0.01, contractSize: 100000, pipDecimalPlaces: 1, priceDecimalPlaces: 3, quoteCurrency: 'JPY' },
  AUDUSD: { name: 'AUDUSD', pipSize: 0.0001, contractSize: 100000, pipDecimalPlaces: 1, priceDecimalPlaces: 5, quoteCurrency: 'USD' },
  XAUUSD: { name: 'XAUUSD', pipSize: 0.10, contractSize: 100, pipDecimalPlaces: 1, priceDecimalPlaces: 2, quoteCurrency: 'USD' },
  BTCUSD: { name: 'BTCUSD', pipSize: 1.00, contractSize: 1, pipDecimalPlaces: 0, priceDecimalPlaces: 2, quoteCurrency: 'USD' },
  ETHUSD: { name: 'ETHUSD', pipSize: 1.00, contractSize: 1, pipDecimalPlaces: 0, priceDecimalPlaces: 2, quoteCurrency: 'USD' }
};

const EQUITY_PRESETS = [5000, 10000, 25000, 50000, 100000];
const RISK_PERCENT_PRESETS = [0.25, 0.5, 1.0, 1.5, 2.0];
const PIP_PRESETS = [10, 15, 20, 25, 30, 50];
const WIN_RATE_PRESETS = [45, 50, 55, 60, 65];

export const QuickRiskCalculatorWidget: React.FC<QuickRiskCalculatorProps> = ({
  symbol,
  side,
  entryPrice,
  stopLoss,
  takeProfit1,
  takeProfit2,
  liveEquity = 10406.25,
  currentLots,
  onApplyLots,
  onApplyTakeProfits,
  className = ''
}) => {
  // Config & View Mode
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'SIZING' | 'EXPECTANCY' | 'COMPOUNDING'>('SIZING');
  const [useLiveEquity, setUseLiveEquity] = useState<boolean>(true);
  const [customEquity, setCustomEquity] = useState<number>(liveEquity);
  const [riskMode, setRiskMode] = useState<'PERCENT' | 'FIXED_USD'>('PERCENT');
  const [riskPercent, setRiskPercent] = useState<number>(1.0);
  const [riskUsd, setRiskUsd] = useState<number>(100);
  const [justApplied, setJustApplied] = useState<boolean>(false);
  const [justAppliedTps, setJustAppliedTps] = useState<boolean>(false);
  const [assumedWinRate, setAssumedWinRate] = useState<number>(55); // 55% benchmark for Asian Sweep + SMC

  // Stop loss distance state (in pips)
  const spec = SYMBOL_SPECS[symbol] || SYMBOL_SPECS['EURUSD'];

  // Current effective equity
  const effectiveEquity = useLiveEquity ? liveEquity : customEquity;

  // Derive initial pip distance from entryPrice and stopLoss
  const rawPriceDiff = Math.abs(entryPrice - stopLoss);
  const derivedPips = spec.pipSize > 0 ? rawPriceDiff / spec.pipSize : 20;

  const [overridePips, setOverridePips] = useState<number | null>(null);

  // Effective stop loss distance in pips
  const activeSlPips = overridePips !== null ? overridePips : Math.max(1, derivedPips);

  // Sync custom equity if liveEquity changes and useLiveEquity is active
  useEffect(() => {
    if (useLiveEquity) {
      setCustomEquity(liveEquity);
    }
  }, [liveEquity, useLiveEquity]);

  // When entryPrice or stopLoss changes from the parent form, reset overridePips to keep in sync
  useEffect(() => {
    setOverridePips(null);
  }, [entryPrice, stopLoss, symbol]);

  // Calculations
  const calc = useMemo(() => {
    // 1. Monetary Risk
    const targetDollarRisk =
      riskMode === 'PERCENT'
        ? (effectiveEquity * riskPercent) / 100
        : Math.min(riskUsd, effectiveEquity);

    // 2. Pip Value in USD per 1.0 lot
    let pipValuePerLot = 10;
    if (symbol === 'USDJPY') {
      pipValuePerLot = entryPrice > 0 ? 1000 / entryPrice : 6.48;
    } else if (symbol === 'XAUUSD') {
      pipValuePerLot = 10;
    } else if (symbol === 'BTCUSD' || symbol === 'ETHUSD') {
      pipValuePerLot = 1;
    }

    // 3. Loss per 1.0 standard lot with active SL pips
    const lossPerLot = Math.max(0.0001, activeSlPips * pipValuePerLot);

    // 4. Raw lots needed
    const rawLots = lossPerLot > 0 ? targetDollarRisk / lossPerLot : 0.01;

    // Standard MT5 step rounding (0.01 lots)
    let suggestedLots = Math.round(rawLots * 100) / 100;
    if (suggestedLots < 0.01) suggestedLots = 0.01;
    if (suggestedLots > 50) suggestedLots = 50;

    // Actual metrics at suggested lots
    const actualDollarRisk = suggestedLots * lossPerLot;
    const actualRiskPct = effectiveEquity > 0 ? (actualDollarRisk / effectiveEquity) * 100 : 0;
    const pipValueTotal = suggestedLots * pipValuePerLot;

    // Estimated margin required (assuming 1:500 leverage for FX/Gold, 1:20 for Crypto)
    const leverage = symbol.includes('BTC') || symbol.includes('ETH') ? 20 : 500;
    const contractNotional =
      symbol === 'XAUUSD'
        ? suggestedLots * 100 * entryPrice
        : symbol === 'BTCUSD' || symbol === 'ETHUSD'
        ? suggestedLots * entryPrice
        : suggestedLots * 100000 * (symbol.startsWith('USD') ? 1 : entryPrice);
    const estimatedMargin = contractNotional / leverage;

    // Calculated Stop Loss Price if overridePips was selected
    let calculatedStopPrice = stopLoss;
    if (overridePips !== null) {
      const priceOffset = overridePips * spec.pipSize;
      calculatedStopPrice =
        side === 'BUY'
          ? Number((entryPrice - priceOffset).toFixed(spec.priceDecimalPlaces))
          : Number((entryPrice + priceOffset).toFixed(spec.priceDecimalPlaces));
    }

    // --- MONEY MAKING & EXPECTANCY CALCULATIONS ---
    // Calculate Pips to TP1 and TP2
    const currentTp1Price = takeProfit1 || (side === 'BUY' ? entryPrice + activeSlPips * 2.5 * spec.pipSize : entryPrice - activeSlPips * 2.5 * spec.pipSize);
    const currentTp2Price = takeProfit2 || (side === 'BUY' ? entryPrice + activeSlPips * 5.0 * spec.pipSize : entryPrice - activeSlPips * 5.0 * spec.pipSize);

    const tp1Pips = spec.pipSize > 0 ? Math.abs(currentTp1Price - entryPrice) / spec.pipSize : activeSlPips * 2.5;
    const tp2Pips = spec.pipSize > 0 ? Math.abs(currentTp2Price - entryPrice) / spec.pipSize : activeSlPips * 5.0;

    const tp1R = activeSlPips > 0 ? tp1Pips / activeSlPips : 2.5;
    const tp2R = activeSlPips > 0 ? tp2Pips / activeSlPips : 5.0;

    // 75% at TP1, 25% at TP2 (ST_ASIAN_SWEEP_5R_V1 standard rule)
    const tp1Lots = Math.round(suggestedLots * 0.75 * 100) / 100;
    const tp2Lots = Math.max(0.01, Math.round((suggestedLots - tp1Lots) * 100) / 100);

    const profitTp1 = tp1Lots * tp1Pips * pipValuePerLot;
    const profitTp2 = tp2Lots * tp2Pips * pipValuePerLot;
    const totalPotentialProfit = profitTp1 + profitTp2;

    const compositeRewardMultiple = actualDollarRisk > 0 ? totalPotentialProfit / actualDollarRisk : 3.125;

    // Expected Value (EV) per trade in $ and R
    // EV = (Win% * TotalPotentialProfit) - (Loss% * ActualDollarRisk)
    const winRateDec = assumedWinRate / 100;
    const lossRateDec = (100 - assumedWinRate) / 100;
    const expectedValueUsd = (winRateDec * totalPotentialProfit) - (lossRateDec * actualDollarRisk);
    const expectedValueR = actualDollarRisk > 0 ? expectedValueUsd / actualDollarRisk : 0;

    // Kelly Criterion %: K = W - (1 - W)/R
    const kellyFull = compositeRewardMultiple > 0 ? (winRateDec - (lossRateDec / compositeRewardMultiple)) * 100 : 0;
    const kellyHalf = Math.max(0, kellyFull / 2);

    // Compounding Trajectories (20, 50, 100 trades)
    const compounding20 = effectiveEquity * Math.pow(1 + (expectedValueUsd / effectiveEquity), 20);
    const compounding50 = effectiveEquity * Math.pow(1 + (expectedValueUsd / effectiveEquity), 50);
    const compounding100 = effectiveEquity * Math.pow(1 + (expectedValueUsd / effectiveEquity), 100);

    return {
      targetDollarRisk,
      suggestedLots,
      actualDollarRisk,
      actualRiskPct,
      pipValuePerLot,
      pipValueTotal,
      estimatedMargin,
      calculatedStopPrice,
      activeSlPips: Number(activeSlPips.toFixed(1)),
      // Money Making Projections
      tp1Pips: Number(tp1Pips.toFixed(1)),
      tp2Pips: Number(tp2Pips.toFixed(1)),
      tp1R: Number(tp1R.toFixed(2)),
      tp2R: Number(tp2R.toFixed(2)),
      tp1Lots,
      tp2Lots,
      profitTp1,
      profitTp2,
      totalPotentialProfit,
      compositeRewardMultiple: Number(compositeRewardMultiple.toFixed(2)),
      expectedValueUsd,
      expectedValueR: Number(expectedValueR.toFixed(2)),
      kellyFull: Number(kellyFull.toFixed(1)),
      kellyHalf: Number(kellyHalf.toFixed(2)),
      compounding20,
      compounding50,
      compounding100
    };
  }, [
    effectiveEquity,
    riskMode,
    riskPercent,
    riskUsd,
    symbol,
    entryPrice,
    stopLoss,
    takeProfit1,
    takeProfit2,
    side,
    activeSlPips,
    overridePips,
    spec,
    assumedWinRate
  ]);

  const handleApply = () => {
    onApplyLots(calc.suggestedLots, overridePips !== null ? calc.calculatedStopPrice : undefined);
    setJustApplied(true);
    setTimeout(() => setJustApplied(false), 2000);
  };

  const handleHarmonizeTargets = (tp1MultipleR: number, tp2MultipleR: number) => {
    if (!onApplyTakeProfits) return;
    const tp1Offset = activeSlPips * tp1MultipleR * spec.pipSize;
    const tp2Offset = activeSlPips * tp2MultipleR * spec.pipSize;

    const newTp1 =
      side === 'BUY'
        ? Number((entryPrice + tp1Offset).toFixed(spec.priceDecimalPlaces))
        : Number((entryPrice - tp1Offset).toFixed(spec.priceDecimalPlaces));

    const newTp2 =
      side === 'BUY'
        ? Number((entryPrice + tp2Offset).toFixed(spec.priceDecimalPlaces))
        : Number((entryPrice - tp2Offset).toFixed(spec.priceDecimalPlaces));

    onApplyTakeProfits(newTp1, newTp2);
    setJustAppliedTps(true);
    setTimeout(() => setJustAppliedTps(false), 2500);
  };

  const handleSelectPipPreset = (pips: number) => {
    setOverridePips(pips);
  };

  const handleResetPips = () => {
    setOverridePips(null);
  };

  const isLotsAlreadyMatching = Math.abs(currentLots - calc.suggestedLots) < 0.005;

  return (
    <div
      id="quick-risk-calculator-widget"
      className={`bg-slate-950/95 border border-slate-800 rounded-xl overflow-hidden shadow-xl transition-all ${className}`}
    >
      {/* Header Banner */}
      <div className="bg-slate-900/95 px-3.5 py-2.5 border-b border-slate-800/90 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="p-1.5 rounded-md bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <Coins className="w-4 h-4" />
          </span>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-100 tracking-wide font-mono">
                Risk & Profit Expectancy Engine
              </span>
              <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                +EV EDGE
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Quick Tab Switcher */}
          <div className="flex bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-[10px] font-mono">
            <button
              type="button"
              id="btn-tab-sizing"
              onClick={() => {
                setActiveTab('SIZING');
                setIsExpanded(true);
              }}
              className={`px-2 py-0.5 rounded font-bold transition ${
                activeTab === 'SIZING'
                  ? 'bg-cyan-500 text-slate-950 shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Sizing
            </button>
            <button
              type="button"
              id="btn-tab-expectancy"
              onClick={() => {
                setActiveTab('EXPECTANCY');
                setIsExpanded(true);
              }}
              className={`px-2 py-0.5 rounded font-bold transition flex items-center gap-1 ${
                activeTab === 'EXPECTANCY'
                  ? 'bg-emerald-500 text-slate-950 shadow'
                  : 'text-emerald-400 hover:text-emerald-300'
              }`}
            >
              <TrendingUp className="w-2.5 h-2.5" />
              Profit & EV
            </button>
            <button
              type="button"
              id="btn-tab-compounding"
              onClick={() => {
                setActiveTab('COMPOUNDING');
                setIsExpanded(true);
              }}
              className={`px-2 py-0.5 rounded font-bold transition flex items-center gap-1 ${
                activeTab === 'COMPOUNDING'
                  ? 'bg-amber-500 text-slate-950 shadow'
                  : 'text-amber-400 hover:text-amber-300'
              }`}
            >
              <Flame className="w-2.5 h-2.5" />
              Grow
            </button>
          </div>

          <button
            type="button"
            id="toggle-quick-risk-calc-expand"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
            title={isExpanded ? 'Collapse calculator' : 'Expand calculator'}
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main Body */}
      {isExpanded && (
        <div className="p-3.5 space-y-3 font-mono text-xs">
          {/* TAB 1: SIZING & RISK CONTROLS */}
          {activeTab === 'SIZING' && (
            <>
              {/* Row 1: Account Equity Control */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-slate-400 text-[11px] flex items-center gap-1">
                    <DollarSign className="w-3 h-3 text-cyan-400" />
                    Account Equity
                  </span>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      id="btn-use-live-equity"
                      onClick={() => setUseLiveEquity(true)}
                      className={`px-1.5 py-0.5 rounded text-[10px] transition flex items-center gap-1 ${
                        useLiveEquity
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                      title="Use live broker demo equity"
                    >
                      <RefreshCw className="w-2.5 h-2.5 text-cyan-400" />
                      Live (${liveEquity.toFixed(0)})
                    </button>
                    <button
                      type="button"
                      id="btn-use-custom-equity"
                      onClick={() => setUseLiveEquity(false)}
                      className={`px-1.5 py-0.5 rounded text-[10px] transition ${
                        !useLiveEquity
                          ? 'bg-slate-800 text-slate-200 border border-slate-700 font-bold'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      Custom
                    </button>
                  </div>
                </div>

                {/* Equity Presets or Custom Input */}
                {!useLiveEquity ? (
                  <div className="space-y-1.5">
                    <div className="relative">
                      <span className="absolute inset-y-0 left-0 pl-2.5 flex items-center text-slate-500 text-xs">
                        $
                      </span>
                      <input
                        id="quick-calc-equity-input"
                        type="number"
                        step="1000"
                        min="500"
                        max="1000000"
                        value={customEquity}
                        onChange={e => setCustomEquity(Math.max(100, Number(e.target.value)))}
                        className="w-full bg-slate-900 border border-slate-800 rounded pl-6 pr-2.5 py-1 text-slate-100 font-bold focus:border-cyan-500 focus:outline-none text-xs"
                      />
                    </div>
                    <div className="flex items-center gap-1 flex-wrap">
                      {EQUITY_PRESETS.map(preset => (
                        <button
                          key={preset}
                          type="button"
                          onClick={() => {
                            setCustomEquity(preset);
                            setUseLiveEquity(false);
                          }}
                          className={`px-1.5 py-0.5 rounded text-[10px] transition ${
                            customEquity === preset && !useLiveEquity
                              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                              : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                          }`}
                        >
                          ${preset >= 1000 ? `${preset / 1000}k` : preset}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-900/80 border border-slate-800/80 rounded px-2.5 py-1 flex items-center justify-between">
                    <span className="text-slate-200 font-bold">${liveEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                      <Check className="w-3 h-3" /> Live MT5 Demo Equity
                    </span>
                  </div>
                )}
              </div>

              {/* Row 2: Risk % Selector */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-slate-400 text-[11px] flex items-center gap-1">
                    <Percent className="w-3 h-3 text-emerald-400" />
                    Risk Per Trade
                  </span>
                  <span className="text-[11px] font-bold text-emerald-400">
                    ${calc.targetDollarRisk.toFixed(2)} ({riskMode === 'PERCENT' ? `${riskPercent.toFixed(2)}%` : `$${riskUsd}`})
                  </span>
                </div>

                {/* Risk Presets */}
                <div className="grid grid-cols-5 gap-1 mb-1.5">
                  {RISK_PERCENT_PRESETS.map(pct => (
                    <button
                      key={pct}
                      type="button"
                      id={`quick-calc-risk-${pct}`}
                      onClick={() => {
                        setRiskPercent(pct);
                        setRiskMode('PERCENT');
                      }}
                      className={`py-1 rounded text-center text-[10px] font-bold transition ${
                        riskMode === 'PERCENT' && riskPercent === pct
                          ? 'bg-emerald-500 text-slate-950 shadow-sm'
                          : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                      }`}
                    >
                      {pct}%
                    </button>
                  ))}
                </div>

                {/* Custom slider */}
                <div className="flex items-center gap-2 pt-0.5">
                  <input
                    id="quick-calc-risk-slider"
                    type="range"
                    min="0.1"
                    max="3.0"
                    step="0.1"
                    value={riskPercent}
                    onChange={e => {
                      setRiskPercent(Number(e.target.value));
                      setRiskMode('PERCENT');
                    }}
                    className="w-full accent-emerald-400 h-1 bg-slate-800 rounded-lg cursor-pointer"
                  />
                  <span className="text-[11px] text-slate-400 font-mono w-10 text-right">
                    {riskPercent.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Row 3: Stop-Loss Distance in Pips */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-slate-400 text-[11px] flex items-center gap-1">
                    <Target className="w-3 h-3 text-rose-400" />
                    Stop-Loss Distance
                  </span>
                  <div className="flex items-center gap-1">
                    <span className="text-[11px] font-bold text-rose-400">
                      {calc.activeSlPips} pips
                    </span>
                    {overridePips !== null && (
                      <button
                        type="button"
                        onClick={handleResetPips}
                        className="text-[9px] text-cyan-400 hover:underline ml-1"
                        title="Reset to SL price set in order form"
                      >
                        (Reset)
                      </button>
                    )}
                  </div>
                </div>

                {/* Pip Presets */}
                <div className="grid grid-cols-6 gap-1">
                  {PIP_PRESETS.map(pips => (
                    <button
                      key={pips}
                      type="button"
                      id={`quick-calc-pip-${pips}`}
                      onClick={() => handleSelectPipPreset(pips)}
                      className={`py-1 rounded text-center text-[10px] transition ${
                        activeSlPips === pips
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50 font-bold'
                          : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                      }`}
                      title={`Set stop-loss distance to ${pips} pips`}
                    >
                      {pips}p
                    </button>
                  ))}
                </div>

                {overridePips !== null && (
                  <div className="mt-1 text-[10px] text-amber-300/90 flex items-center justify-between bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                    <span>Updated SL Price:</span>
                    <span className="font-bold">{calc.calculatedStopPrice.toFixed(spec.priceDecimalPlaces)}</span>
                  </div>
                )}
              </div>

              {/* Row 4: Suggested Position Size & One-Click Apply */}
              <div className="p-2.5 bg-gradient-to-r from-slate-900 via-slate-900/90 to-cyan-950/40 rounded-lg border border-cyan-800/40 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] text-cyan-400 uppercase tracking-wider block font-bold">
                      Suggested Position Size
                    </span>
                    <div className="flex items-baseline gap-1.5 mt-0.5">
                      <span
                        id="quick-calc-suggested-lots"
                        className="text-xl font-bold font-mono text-cyan-300 tracking-tight"
                      >
                        {calc.suggestedLots.toFixed(2)}
                      </span>
                      <span className="text-xs font-semibold text-slate-400">Lots</span>
                      {isLotsAlreadyMatching && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                          In Order Form
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Action Button */}
                  <button
                    type="button"
                    id="btn-apply-suggested-lots"
                    onClick={handleApply}
                    disabled={isLotsAlreadyMatching && overridePips === null}
                    className={`px-3 py-2 rounded-lg font-bold text-xs flex items-center gap-1.5 transition shadow-sm ${
                      justApplied
                        ? 'bg-emerald-500 text-slate-950'
                        : isLotsAlreadyMatching && overridePips === null
                        ? 'bg-slate-800 text-slate-500 border border-slate-700 cursor-default'
                        : 'bg-cyan-500 hover:bg-cyan-400 text-slate-950 hover:shadow-cyan-500/20'
                    }`}
                    title="Apply suggested lot size directly to order form"
                  >
                    {justApplied ? (
                      <>
                        <Check className="w-3.5 h-3.5 stroke-[3]" />
                        <span>Applied!</span>
                      </>
                    ) : (
                      <>
                        <Zap className="w-3.5 h-3.5 fill-current" />
                        <span>Apply to Order</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Supporting Sizing Formula Breakdown */}
                <div className="grid grid-cols-3 gap-1 pt-1 border-t border-slate-800/80 text-[10px] text-slate-400">
                  <div>
                    <span className="text-slate-500 block">Total Risk</span>
                    <span className="text-slate-200 font-bold">${calc.actualDollarRisk.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Pip Value</span>
                    <span className="text-slate-200 font-bold">${calc.pipValueTotal.toFixed(2)}/p</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Est. Margin</span>
                    <span className="text-slate-200 font-bold">${calc.estimatedMargin.toFixed(0)}</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* TAB 2: MONEY MAKING & EXPECTANCY ENGINE */}
          {activeTab === 'EXPECTANCY' && (
            <div className="space-y-3">
              {/* Asymmetric Payout Grid */}
              <div className="p-3 bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950/40 rounded-xl border border-emerald-500/30 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-bold text-slate-100">
                      Asymmetric Profit Matrix
                    </span>
                  </div>
                  <span className="text-[11px] font-bold text-emerald-400 font-mono bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                    {calc.compositeRewardMultiple} : 1 R:R
                  </span>
                </div>

                {/* Target Breakdown */}
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="bg-slate-950/80 p-2 rounded-lg border border-slate-800">
                    <div className="flex justify-between text-slate-400 text-[10px] mb-0.5">
                      <span>TP1 (75% Bank)</span>
                      <span className="text-emerald-400 font-bold">+{calc.tp1R}R</span>
                    </div>
                    <div className="text-base font-bold text-emerald-300 font-mono">
                      +${calc.profitTp1.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-slate-500 flex justify-between mt-0.5">
                      <span>{calc.tp1Lots.toFixed(2)} lots</span>
                      <span>{calc.tp1Pips} pips</span>
                    </div>
                  </div>

                  <div className="bg-slate-950/80 p-2 rounded-lg border border-slate-800">
                    <div className="flex justify-between text-slate-400 text-[10px] mb-0.5">
                      <span>TP2 (25% Runner)</span>
                      <span className="text-cyan-400 font-bold">+{calc.tp2R}R</span>
                    </div>
                    <div className="text-base font-bold text-cyan-300 font-mono">
                      +${calc.profitTp2.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-slate-500 flex justify-between mt-0.5">
                      <span>{calc.tp2Lots.toFixed(2)} lots</span>
                      <span>{calc.tp2Pips} pips</span>
                    </div>
                  </div>
                </div>

                {/* Combined Profit vs Risk Comparison Bar */}
                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 flex items-center justify-between text-xs">
                  <div>
                    <span className="text-slate-400 block text-[10px]">MAX RISK (1.00R)</span>
                    <span className="text-rose-400 font-bold font-mono">-${calc.actualDollarRisk.toFixed(2)}</span>
                  </div>
                  <div className="text-center">
                    <span className="text-slate-500 block text-[10px]">PAYOUT MULTIPLE</span>
                    <span className="text-emerald-400 font-bold font-mono text-sm">
                      +{((calc.totalPotentialProfit / Math.max(1, calc.actualDollarRisk))).toFixed(2)}x
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-slate-400 block text-[10px]">MAX GAIN (TP1 + TP2)</span>
                    <span className="text-emerald-300 font-bold font-mono">+${calc.totalPotentialProfit.toFixed(2)}</span>
                  </div>
                </div>

                {/* Expected Value (EV) Box */}
                <div className="p-2.5 bg-emerald-900/20 border border-emerald-500/30 rounded-lg">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-slate-300 text-[11px] font-bold flex items-center gap-1">
                      <Coins className="w-3.5 h-3.5 text-emerald-400" />
                      Mathematical Expected Value (EV)
                    </span>
                    <span className="text-[10px] text-slate-400">
                      Win Rate: <strong className="text-emerald-400">{assumedWinRate}%</strong>
                    </span>
                  </div>

                  <div className="flex items-baseline justify-between">
                    <div>
                      <div className="text-lg font-bold text-emerald-300 font-mono">
                        +${calc.expectedValueUsd.toFixed(2)} <span className="text-xs text-emerald-400/80 font-normal">/ execution</span>
                      </div>
                      <span className="text-[10px] text-slate-400 block">
                        Net Edge: <strong className="text-cyan-300">+{calc.expectedValueR}R</strong> per trade
                      </span>
                    </div>

                    <div className="flex items-center gap-1">
                      {WIN_RATE_PRESETS.map(wr => (
                        <button
                          key={wr}
                          type="button"
                          onClick={() => setAssumedWinRate(wr)}
                          className={`px-1.5 py-0.5 rounded text-[10px] transition ${
                            assumedWinRate === wr
                              ? 'bg-emerald-500 text-slate-950 font-bold'
                              : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                          }`}
                        >
                          {wr}%
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Harmonize Target Presets */}
                <div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                    <span>Harmonize Target Multipliers:</span>
                    {justAppliedTps && (
                      <span className="text-emerald-400 font-bold flex items-center gap-0.5">
                        <Check className="w-3 h-3" /> Updated TP1 & TP2!
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-1.5">
                    <button
                      type="button"
                      onClick={() => handleHarmonizeTargets(2.5, 5.0)}
                      className="py-1 px-2 rounded text-[10px] font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center justify-center gap-1"
                      title="Set TP1 at 2.5R (Asian boundary) and TP2 at 5.0R (Full runner)"
                    >
                      <span>2.5R / 5.0R (Rule V1)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleHarmonizeTargets(2.0, 4.0)}
                      className="py-1 px-2 rounded text-[10px] font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center justify-center gap-1"
                      title="Set TP1 at 2.0R and TP2 at 4.0R"
                    >
                      <span>2.0R / 4.0R (Quick)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleHarmonizeTargets(3.0, 6.0)}
                      className="py-1 px-2 rounded text-[10px] font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center justify-center gap-1"
                      title="Set TP1 at 3.0R and TP2 at 6.0R (Extended SMC)"
                    >
                      <span>3.0R / 6.0R (SMC)</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: COMPOUNDING WEALTH SIMULATOR */}
          {activeTab === 'COMPOUNDING' && (
            <div className="space-y-3">
              <div className="p-3 bg-gradient-to-br from-slate-900 via-slate-900 to-amber-950/30 rounded-xl border border-amber-500/30 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Flame className="w-4 h-4 text-amber-400" />
                    <span className="text-xs font-bold text-slate-100">
                      Systematic Compounding Projection
                    </span>
                  </div>
                  <span className="text-[10px] text-amber-400 font-mono">
                    Starting: ${effectiveEquity.toFixed(0)}
                  </span>
                </div>

                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Real trading wealth is created through geometric compounding of an asymmetric edge. Here is the projected equity growth executing this +EV system:
                </p>

                {/* Projection Milestones */}
                <div className="grid grid-cols-3 gap-2 font-mono text-center">
                  <div className="bg-slate-950 p-2 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 block">20 TRADES</span>
                    <span className="text-sm font-bold text-amber-300">
                      ${calc.compounding20.toFixed(0)}
                    </span>
                    <span className="text-[10px] text-emerald-400 block font-bold">
                      +{(((calc.compounding20 - effectiveEquity) / effectiveEquity) * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="bg-slate-950 p-2 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 block">50 TRADES</span>
                    <span className="text-sm font-bold text-amber-300">
                      ${calc.compounding50.toFixed(0)}
                    </span>
                    <span className="text-[10px] text-emerald-400 block font-bold">
                      +{(((calc.compounding50 - effectiveEquity) / effectiveEquity) * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="bg-slate-950 p-2 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 block">100 TRADES</span>
                    <span className="text-sm font-bold text-emerald-300">
                      ${calc.compounding100.toFixed(0)}
                    </span>
                    <span className="text-[10px] text-emerald-400 block font-bold">
                      +{(((calc.compounding100 - effectiveEquity) / effectiveEquity) * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Kelly Criterion Card */}
                <div className="bg-slate-950/90 p-2.5 rounded-lg border border-slate-800/80 space-y-1 text-[11px]">
                  <div className="flex justify-between items-center text-slate-300">
                    <span className="font-bold flex items-center gap-1">
                      <BarChart3 className="w-3 h-3 text-cyan-400" />
                      Kelly Criterion Recommendation
                    </span>
                    <span className="text-cyan-400 font-bold font-mono">
                      {calc.kellyHalf}% Risk (Half-Kelly)
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 leading-relaxed">
                    Full Kelly ({calc.kellyFull}%) risks high volatility. Institutional hedge funds trade at Half or Quarter Kelly (0.5%–1.5% risk) to guarantee zero chance of ruin while capturing &gt;75% of peak geometric growth.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Persistent Risk Guard & Status */}
          <div className="flex items-center justify-between text-[10px] text-slate-500 pt-0.5 border-t border-slate-850">
            <div className="flex items-center gap-1.5">
              {calc.actualRiskPct <= 2.0 ? (
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
              ) : (
                <ShieldAlert className="w-3 h-3 text-amber-400" />
              )}
              <span className={calc.actualRiskPct <= 2.0 ? 'text-slate-400' : 'text-amber-400 font-bold'}>
                {calc.actualRiskPct <= 2.0
                  ? 'Within 2.00R daily risk policy'
                  : 'Exceeds 2.00R daily risk guard limit'}
              </span>
            </div>
            <span className="text-slate-400 font-mono">
              Suggested: <strong className="text-cyan-300">{calc.suggestedLots.toFixed(2)} lots</strong>
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuickRiskCalculatorWidget;
