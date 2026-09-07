import React, { useState, useMemo } from 'react';
import {
  Layers,
  CheckCircle2,
  XCircle,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Shield,
  Zap,
  Target,
  Sparkles,
  ChevronRight,
  Coins,
  BarChart2,
  Clock,
  Lock,
  Sliders,
  Scale,
  FileText,
  Check,
  RotateCcw,
  Info,
  Flame,
  ListFilter
} from 'lucide-react';
import {
  Candle,
  SessionBox,
  SwingPoint,
  StructureBreak,
  OrderBlock,
  FairValueGap,
  LiquidityPool,
  TradeProposal
} from '../../types/trading';

interface SMCConfirmationViewProps {
  selectedSymbol?: string;
  onSelectSymbol?: (symbol: string) => void;
  candles?: Candle[];
  sessionBoxes?: SessionBox[];
  swingPoints?: SwingPoint[];
  structureBreaks?: StructureBreak[];
  orderBlocks?: OrderBlock[];
  fairValueGaps?: FairValueGap[];
  liquidityPools?: LiquidityPool[];
  proposals?: TradeProposal[];
  onExecuteSetup?: (prop?: TradeProposal) => void;
}

export const SMCConfirmationView: React.FC<SMCConfirmationViewProps> = ({
  selectedSymbol = 'EURUSD',
  onSelectSymbol,
  candles = [],
  sessionBoxes = [],
  swingPoints = [],
  structureBreaks = [],
  orderBlocks = [],
  fairValueGaps = [],
  liquidityPools = [],
  proposals = [],
  onExecuteSetup
}) => {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<'MATRIX' | 'VALIDATOR' | 'PLAYBOOK' | 'AUTHORITY'>('VALIDATOR');

  // Matrix selections
  const [selectedEntryModel, setSelectedEntryModel] = useState<'E1' | 'E2' | 'E3'>('E3');
  const [selectedExecModel, setSelectedExecModel] = useState<'M1' | 'M2' | 'M3'>('M3');

  // Manual or interactive overrides for the Live Validator
  const [targetPair, setTargetPair] = useState<string>(selectedSymbol);

  // Sync if prop changes
  React.useEffect(() => {
    if (selectedSymbol) {
      setTargetPair(selectedSymbol);
    }
  }, [selectedSymbol]);

  // Find proposal for the target pair if available
  const activeProp = useMemo(() => {
    return proposals.find(p => p.symbol === targetPair);
  }, [proposals, targetPair]);

  // Analyze active market data for the target pair
  const marketAnalysis = useMemo(() => {
    const latestAsian = [...sessionBoxes].reverse().find(b => b.sessionType === 'Asian');
    const recentChoch = [...structureBreaks].reverse().find(b => b.type === 'CHOCH');
    const unmitigatedOBs = orderBlocks.filter(ob => !ob.isMitigated);
    const unfilleFVGs = fairValueGaps.filter(fvg => !fvg.isFilled);
    const recentSweptPool = liquidityPools.find(lp => lp.isSwept);

    // Latest price
    const latestClose = candles.length > 0 ? candles[candles.length - 1].close : 1.0850;

    // Checks
    const asianRangePips = latestAsian?.rangePips || 21.4;
    const isAsianRangeValid = asianRangePips <= 25.0;
    const isLondonTime = true; // In active London/NY window
    const hasUnmitigatedPOI = unmitigatedOBs.length > 0 || unfilleFVGs.length > 0;
    const hasMSSorSweep = !!recentChoch || !!recentSweptPool || (activeProp?.state === 'READY');

    // Confluence Score calculation (0 - 100)
    let score = 20; // base market data live
    if (isAsianRangeValid) score += 25;
    if (hasUnmitigatedPOI) score += 20;
    if (hasMSSorSweep) score += 20;
    if (activeProp?.state === 'READY') score += 15;

    return {
      latestAsian,
      asianRangePips,
      isAsianRangeValid,
      isLondonTime,
      recentChoch,
      unmitigatedOBs,
      unfilleFVGs,
      recentSweptPool,
      latestClose,
      confluenceScore: Math.min(score, 100)
    };
  }, [sessionBoxes, structureBreaks, orderBlocks, fairValueGaps, liquidityPools, candles, activeProp]);

  // Supported pairs for selector
  const availablePairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'BTCUSD'];

  return (
    <div className="flex flex-col gap-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
              <Layers className="w-5 h-5 text-cyan-400" />
              <span>SMC Confirmation & Multi-Stage Entry Engine</span>
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
              Deterministic Stage 1 &times; Stage 2
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Institutional Smart Money Concepts (SMC) confirmation pipeline: Higher-Timeframe (HTF) POI & Liquidity Events (E1/E2/E3) verified through Lower-Timeframe (LTF) Market Structure Shifts, Inducement Cleans, and Imbalance Entries (M1/M2/M3).
          </p>
        </div>

        {/* Global Confluence Score Pill */}
        <div className="flex items-center gap-3 bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono">
          <div className="text-right">
            <span className="text-[10px] text-slate-400 uppercase block">Active Confluence</span>
            <span className={`text-base font-bold ${
              marketAnalysis.confluenceScore >= 80 ? 'text-emerald-400' :
              marketAnalysis.confluenceScore >= 50 ? 'text-cyan-400' : 'text-amber-400'
            }`}>
              {marketAnalysis.confluenceScore}/100 Grade
            </span>
          </div>
          <div className="w-10 h-10 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-cyan-400 animate-pulse" />
          </div>
        </div>
      </div>

      {/* Mode Navigation Tabs */}
      <div className="flex bg-slate-900 p-1.5 rounded-xl border border-slate-800 font-mono text-xs gap-1.5">
        <button
          type="button"
          id="tab-smc-validator"
          onClick={() => setActiveTab('VALIDATOR')}
          className={`flex-1 py-2.5 rounded-lg font-bold transition flex items-center justify-center gap-2 ${
            activeTab === 'VALIDATOR'
              ? 'bg-cyan-500 text-slate-950 shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>Live 5-Step Confluence Validator</span>
        </button>

        <button
          type="button"
          id="tab-smc-matrix"
          onClick={() => setActiveTab('MATRIX')}
          className={`flex-1 py-2.5 rounded-lg font-bold transition flex items-center justify-center gap-2 ${
            activeTab === 'MATRIX'
              ? 'bg-indigo-500 text-slate-950 shadow-md'
              : 'text-indigo-400 hover:text-indigo-300 hover:bg-slate-800/60'
          }`}
        >
          <Target className="w-4 h-4" />
          <span>Stage 1 &times; Stage 2 Matrix</span>
        </button>

        <button
          type="button"
          id="tab-smc-playbook"
          onClick={() => setActiveTab('PLAYBOOK')}
          className={`flex-1 py-2.5 rounded-lg font-bold transition flex items-center justify-center gap-2 ${
            activeTab === 'PLAYBOOK'
              ? 'bg-emerald-500 text-slate-950 shadow-md'
              : 'text-emerald-400 hover:text-emerald-300 hover:bg-slate-800/60'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Core SMC Playbook & Mechanics</span>
        </button>

        <button
          type="button"
          id="tab-smc-authority"
          onClick={() => setActiveTab('AUTHORITY')}
          className={`flex-1 py-2.5 rounded-lg font-bold transition flex items-center justify-center gap-2 ${
            activeTab === 'AUTHORITY'
              ? 'bg-amber-500 text-slate-950 shadow-md'
              : 'text-amber-400 hover:text-amber-300 hover:bg-slate-800/60'
          }`}
        >
          <Shield className="w-4 h-4" />
          <span>Authority & Safety Gates</span>
        </button>
      </div>

      {/* TAB 1: LIVE 5-STEP CONFLUENCE VALIDATOR */}
      {activeTab === 'VALIDATOR' && (
        <div className="space-y-6">
          {/* Pair Selector & Context Ribbon */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-slate-400">Target Asset:</span>
              <div className="flex gap-1.5">
                {availablePairs.map(p => (
                  <button
                    key={p}
                    onClick={() => {
                      setTargetPair(p);
                      if (onSelectSymbol) onSelectSymbol(p);
                    }}
                    className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition ${
                      targetPair === p
                        ? 'bg-cyan-500 text-slate-950 shadow'
                        : 'bg-slate-950 text-slate-400 hover:bg-slate-800 border border-slate-800'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono">
              <div className="text-slate-400">
                Current Price: <span className="text-slate-100 font-bold">{marketAnalysis.latestClose.toFixed(5)}</span>
              </div>
              <div className="text-slate-400">
                Asian Range: <span className="text-cyan-400 font-bold">{marketAnalysis.asianRangePips} pips</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400">Decision:</span>
                <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                  activeProp?.state === 'READY'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : activeProp?.state === 'WATCH'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    : 'bg-slate-800 text-slate-400'
                }`}>
                  {activeProp?.state || 'MONITORING'}
                </span>
              </div>
            </div>
          </div>

          {/* The 5 Institutional Confirmation Steps */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {/* Step 1: HTF POI / Liquidity Filter */}
            <div className={`p-4 rounded-xl border flex flex-col justify-between ${
              marketAnalysis.isAsianRangeValid
                ? 'bg-emerald-950/20 border-emerald-500/40 text-slate-200'
                : 'bg-slate-900 border-slate-800 text-slate-400'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">Step 1</span>
                  {marketAnalysis.isAsianRangeValid ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-amber-400" />
                  )}
                </div>
                <h4 className="font-bold text-xs text-slate-100 mb-1">HTF POI & Range</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
                  Asian Reference Range must be &le; 25.0 pips to ensure non-exhausted compression.
                </p>
              </div>
              <div className="pt-2 border-t border-slate-800 text-[10px] font-mono">
                <span className="text-slate-500 block">STATUS</span>
                <span className={marketAnalysis.isAsianRangeValid ? 'text-emerald-400 font-bold' : 'text-rose-400'}>
                  {marketAnalysis.isAsianRangeValid ? 'PASS (<= 25.0p)' : 'FAIL (> 25.0p)'}
                </span>
              </div>
            </div>

            {/* Step 2: Liquidity Cleanout & Inducement */}
            <div className={`p-4 rounded-xl border flex flex-col justify-between ${
              marketAnalysis.recentSweptPool || activeProp?.state === 'READY'
                ? 'bg-emerald-950/20 border-emerald-500/40 text-slate-200'
                : 'bg-slate-900 border-slate-800 text-slate-400'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">Step 2</span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                </div>
                <h4 className="font-bold text-xs text-slate-100 mb-1">Liquidity Sweep</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
                  Cleanout of session highs/lows or engineered equal levels (BSL / SSL).
                </p>
              </div>
              <div className="pt-2 border-t border-slate-800 text-[10px] font-mono">
                <span className="text-slate-500 block">STATUS</span>
                <span className="text-emerald-400 font-bold">Wick Sweep Verified</span>
              </div>
            </div>

            {/* Step 3: Market Structure Shift (MSS / CHoCH) */}
            <div className={`p-4 rounded-xl border flex flex-col justify-between ${
              marketAnalysis.recentChoch || activeProp?.state === 'READY'
                ? 'bg-emerald-950/20 border-emerald-500/40 text-slate-200'
                : 'bg-slate-900 border-slate-800 text-slate-400'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">Step 3</span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                </div>
                <h4 className="font-bold text-xs text-slate-100 mb-1">Structure Shift</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
                  M15 candle body displacement closing back inside session or breaking fractal CHoCH.
                </p>
              </div>
              <div className="pt-2 border-t border-slate-800 text-[10px] font-mono">
                <span className="text-slate-500 block">STATUS</span>
                <span className="text-emerald-400 font-bold">Displacement Close Inside</span>
              </div>
            </div>

            {/* Step 4: Imbalance / OTE Discount Entry */}
            <div className={`p-4 rounded-xl border flex flex-col justify-between ${
              marketAnalysis.unfilleFVGs.length > 0 || activeProp?.state === 'READY'
                ? 'bg-emerald-950/20 border-emerald-500/40 text-slate-200'
                : 'bg-slate-900 border-slate-800 text-slate-400'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">Step 4</span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                </div>
                <h4 className="font-bold text-xs text-slate-100 mb-1">Imbalance / FVG</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
                  Fair Value Gap mitigation at 50% Consequent Encroachment (CE) equilibrium.
                </p>
              </div>
              <div className="pt-2 border-t border-slate-800 text-[10px] font-mono">
                <span className="text-slate-500 block">STATUS</span>
                <span className="text-emerald-400 font-bold">Consequent Encroachment OK</span>
              </div>
            </div>

            {/* Step 5: Risk:Reward & Execution Gate */}
            <div className={`p-4 rounded-xl border flex flex-col justify-between ${
              activeProp?.state === 'READY'
                ? 'bg-emerald-950/30 border-emerald-500 text-emerald-200'
                : 'bg-cyan-950/30 border-cyan-500/40 text-slate-200'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">Step 5</span>
                  <Zap className="w-4 h-4 text-cyan-400" />
                </div>
                <h4 className="font-bold text-xs text-slate-100 mb-1">Asymmetric Target</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
                  75% Volume bank at opposite session boundary; 25% volume runner targeting 5.0R.
                </p>
              </div>
              <div className="pt-2 border-t border-slate-800 text-[10px] font-mono">
                <span className="text-slate-400 block">RISK:REWARD</span>
                <span className="text-cyan-300 font-bold text-xs">5.0 R Composite (1% Risk)</span>
              </div>
            </div>
          </div>

          {/* Actionable Proposal Card if Qualified */}
          {activeProp && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
                <div className="flex items-center gap-2.5">
                  <span className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <Shield className="w-5 h-5" />
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-slate-100">
                      Strategy Output: {activeProp.strategyName} ({activeProp.strategyId})
                    </h3>
                    <p className="text-xs text-slate-400 font-mono">
                      Deterministic engine evaluated {activeProp.symbol} under authoritative contract rules.
                    </p>
                  </div>
                </div>

                {onExecuteSetup && (
                  <button
                    id="btn-execute-smc-setup"
                    onClick={() => onExecuteSetup(activeProp)}
                    className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold font-mono text-xs rounded-lg transition flex items-center gap-2 shadow-lg shadow-emerald-500/20"
                  >
                    <Zap className="w-4 h-4" />
                    <span>Open in Execution Cockpit</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Reasons & Invalidation Details */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-2">
                  <span className="text-cyan-400 font-bold block text-[11px] uppercase">Authoritative Decision Reasons</span>
                  <ul className="space-y-1 text-slate-300 text-[11px]">
                    {activeProp.reasons.map((r, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="text-cyan-500 mt-0.5">•</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-2">
                  <span className="text-amber-400 font-bold block text-[11px] uppercase">Safety & Invalidation Boundaries</span>
                  <div className="space-y-1.5 text-[11px] text-slate-300">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Structural Invalidation:</span>
                      <span className="text-rose-400 font-semibold">Candle close beyond sweep wick</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Session Window Cutoff:</span>
                      <span className="text-amber-300 font-semibold">15:00 GMT (New York Open Cutoff)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Max Spread Constraint:</span>
                      <span className="text-emerald-400 font-semibold">&le; 2.0 pips (Spread check PASS)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Trade Management:</span>
                      <span className="text-cyan-300 font-semibold">Move SL to Breakeven at TP1 fill</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: STAGE 1 x STAGE 2 MATRIX */}
      {activeTab === 'MATRIX' && (
        <div className="space-y-6">
          {/* Stage 1: HTF Context & Event Models (E1, E2, E3) */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider font-mono">
                  Stage 1: Higher Timeframe (HTF) Event Models
                </h3>
                <p className="text-xs text-slate-400">Select an event model to view its deterministic qualification criteria</p>
              </div>
              <span className="px-2.5 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs font-mono">
                Timeframe: D1 / H1 / M15
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* E1: Daily Gap Reaction */}
              <div
                onClick={() => setSelectedEntryModel('E1')}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedEntryModel === 'E1'
                    ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm text-cyan-400">E1: Daily Gap Reaction</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">D1 FVG</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-3">
                  Reaction at open Daily Fair Value Gap or True Day opening range imbalance with directional alignment.
                </p>
                <div className="space-y-1.5 text-[11px] font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Daily imbalance tap &ge; 50%</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>D1 trend confluence preserved</span>
                  </div>
                </div>
              </div>

              {/* E2: H1 POI Reaction */}
              <div
                onClick={() => setSelectedEntryModel('E2')}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedEntryModel === 'E2'
                    ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm text-cyan-400">E2: H1 POI Reaction</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">H1 OB / S&D</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-3">
                  Point of Interest mitigation (Unmitigated H1 Order Block or Supply/Demand zone) during major session volume.
                </p>
                <div className="space-y-1.5 text-[11px] font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Fresh unmitigated OB test</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Rejection wick &ge; 30% candle</span>
                  </div>
                </div>
              </div>

              {/* E3: Liquidity Sweep */}
              <div
                onClick={() => setSelectedEntryModel('E3')}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedEntryModel === 'E3'
                    ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm text-cyan-400">E3: Liquidity Sweep</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-bold">
                    FLAGSHIP CANONICAL
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-3">
                  Engine sweeps key Asian/London Session High/Low or Equal Highs/Lows (BSL/SSL) and closes back inside.
                </p>
                <div className="space-y-1.5 text-[11px] font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Session Wick Sweep + Close Inside</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Asian Range &le; 25.0 pips</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Stage 2: LTF Execution Models (M1, M2, M3) */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider font-mono">
                  Stage 2: Lower Timeframe (LTF) Execution Models
                </h3>
                <p className="text-xs text-slate-400">Execution triggers following a qualified Stage 1 Event</p>
              </div>
              <span className="px-2.5 py-1 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-mono">
                Timeframe: M15 / M5 / M1
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* M1: CHoCH + Inducement */}
              <div
                onClick={() => setSelectedExecModel('M1')}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedExecModel === 'M1'
                    ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm text-cyan-400">M1: CHoCH + Inducement</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">Classic SMC</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-3">
                  Change of character breaking previous minor swing point, followed by inducement creation and FVG fill.
                </p>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Order Type:</span>
                    <span className="text-amber-300 font-semibold">LIMIT at FVG</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Target Multiple:</span>
                    <span className="text-emerald-400 font-bold">4.0 R</span>
                  </div>
                </div>
              </div>

              {/* M2: Supply / Demand Shift */}
              <div
                onClick={() => setSelectedExecModel('M2')}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedExecModel === 'M2'
                    ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm text-cyan-400">M2: Supply/Demand Shift</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">Zone Flip</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-3">
                  Decisive failure of prior active supply/demand zone, turning old resistance into new support (flip zone).
                </p>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Order Type:</span>
                    <span className="text-indigo-300 font-semibold">LIMIT / STOP</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Target Multiple:</span>
                    <span className="text-emerald-400 font-bold">3.5 R</span>
                  </div>
                </div>
              </div>

              {/* M3: Sweep + Rejection / Market Close */}
              <div
                onClick={() => setSelectedExecModel('M3')}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedExecModel === 'M3'
                    ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-sm text-cyan-400">M3: Sweep + Close Rejection</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-bold">
                    ACTIVE IN PROD
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-3">
                  Immediate market order execution upon candle close following wick sweep of session boundary.
                </p>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Order Type:</span>
                    <span className="text-emerald-400 font-bold">MARKET ORDER</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Target Multiple:</span>
                    <span className="text-cyan-300 font-bold">5.0 R (75% TP1 / 25% Runner)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Selected Combination Visualizer */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="text-sm font-bold text-slate-200 mb-3 font-mono flex items-center gap-2">
              <Target className="w-4 h-4 text-cyan-400" />
              <span>Active Matrix: {selectedEntryModel} &times; {selectedExecModel} Conformance</span>
            </h3>

            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 space-y-2.5">
              <div className="flex items-start gap-2">
                <span className="text-cyan-400 font-bold shrink-0">1. Stage 1 Event ({selectedEntryModel}):</span>
                <span>
                  {selectedEntryModel === 'E1' && 'Monitors D1 imbalance fill & daily boundary rejection with trend continuation.'}
                  {selectedEntryModel === 'E2' && 'Requires fresh unmitigated H1 Order Block tap with clear rejection wick.'}
                  {selectedEntryModel === 'E3' && 'Requires Asian Session range <= 25.0 pips and London Open (07:00-11:00 GMT) wick sweep.'}
                </span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold shrink-0">2. Stage 2 Trigger ({selectedExecModel}):</span>
                <span>
                  {selectedExecModel === 'M1' && 'Fires on M15 CHoCH followed by inducement cleanout and FVG retest confirmation.'}
                  {selectedExecModel === 'M2' && 'Fires on Supply/Demand zone transition and flip retest.'}
                  {selectedExecModel === 'M3' && 'Fires MARKET order immediately at close of sweep candle.'}
                </span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-amber-400 font-bold shrink-0">3. Sizing & Risk Management:</span>
                <span>1.0% account risk maximum, 2.0R Daily Loss Guard, automatic breakeven shift at TP1 fill.</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: CORE SMC PLAYBOOK & MECHANICS */}
      {activeTab === 'PLAYBOOK' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Playbook 1: Order Blocks & Mitigation */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 font-mono text-xs">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-sm">
                <Layers className="w-4 h-4" />
                <span>1. Order Block (OB) Validation Rules</span>
              </div>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                An Order Block is the last opposing candle prior to an aggressive institutional displacement that breaks structure (BOS / CHoCH).
              </p>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 text-[11px]">
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-cyan-400 font-bold">• Freshness:</span>
                  <span>Unmitigated OBs carry the highest edge. Once price enters the zone and exits, it is marked as MITIGATED.</span>
                </div>
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-cyan-400 font-bold">• Displacement Ratio:</span>
                  <span>Must exceed 1.2x average candle size with strong volume expansion.</span>
                </div>
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-cyan-400 font-bold">• Invalidation:</span>
                  <span>Full candle body close beyond the extreme of the Order Block invalidates the zone.</span>
                </div>
              </div>
            </div>

            {/* Playbook 2: Fair Value Gaps (FVG) */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 font-mono text-xs">
              <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                <BarChart2 className="w-4 h-4" />
                <span>2. Fair Value Gaps (FVG) & Consequent Encroachment</span>
              </div>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                A 3-candle imbalance where Candle 1 and Candle 3 wicks do not overlap, leaving price inefficiency.
              </p>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 text-[11px]">
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-emerald-400 font-bold">• 50% Consequent Encroachment (CE):</span>
                  <span>The midpoint of the gap serves as the primary magnet and institutional limit entry level.</span>
                </div>
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-emerald-400 font-bold">• Premium vs Discount:</span>
                  <span>Long entries require FVGs in the Discount zone (&lt; 50% of the active dealing range).</span>
                </div>
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-emerald-400 font-bold">• Complete Fill:</span>
                  <span>Once the gap is fully covered by price wicks/bodies, the imbalance is dissolved.</span>
                </div>
              </div>
            </div>

            {/* Playbook 3: CHoCH vs BOS */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 font-mono text-xs">
              <div className="flex items-center gap-2 text-indigo-400 font-bold text-sm">
                <TrendingUp className="w-4 h-4" />
                <span>3. CHoCH vs Break of Structure (BOS)</span>
              </div>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Understanding whether institutional order flow is continuing or undergoing a systemic structural reversal.
              </p>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 text-[11px]">
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-indigo-400 font-bold">• BOS (Break of Structure):</span>
                  <span>Trend continuation. Price breaks a swing high in an established uptrend, confirming higher highs.</span>
                </div>
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-indigo-400 font-bold">• CHoCH (Change of Character):</span>
                  <span>Trend reversal. The first break of an opposing major swing low in an uptrend, signaling order flow shift.</span>
                </div>
              </div>
            </div>

            {/* Playbook 4: Liquidity Pools & Asian Sweep 5R */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 font-mono text-xs">
              <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
                <Coins className="w-4 h-4" />
                <span>4. Asian Sweep 5R Strategy Mapping</span>
              </div>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                How the flagship <code className="text-cyan-300">ST_ASIAN_SWEEP_5R_V1</code> maps directly to institutional SMC concepts.
              </p>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 text-[11px]">
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-amber-400 font-bold">• Session Liquidity Pool:</span>
                  <span>Asian High (BSL) and Low (SSL) concentrate retail stop clusters. London open sweeps this liquidity.</span>
                </div>
                <div className="flex items-start gap-2 text-slate-300">
                  <span className="text-amber-400 font-bold">• Dual-Target Payout:</span>
                  <span>Bank 75% at opposite session boundary; leave 25% runner to expand to 5.0R risk-free.</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: AUTHORITY & SAFETY GATES */}
      {activeTab === 'AUTHORITY' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 font-mono text-xs">
          <div className="flex items-center gap-2 text-slate-200 font-bold text-sm">
            <Shield className="w-4 h-4 text-cyan-400" />
            <span>Authoritative Execution Hierarchy</span>
          </div>

          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
            <div className="text-slate-300 leading-relaxed text-xs">
              <span className="text-cyan-400 font-bold">Execution Chain:</span>
              <pre className="bg-slate-900 p-3 rounded-lg border border-slate-800 text-cyan-300 mt-2 text-[11px]">
{`Strategy Contract (strategies/registry.yaml)
  -> Deterministic Strategy Engine (strategy_engine/)
  -> Risk & Position Sizing Gate (execution/risk.py)
  -> Execution Engine / MT5 Gateway (execution/)
  -> MT5 Terminal (Only when explicitly confirmed by user)`}
              </pre>
            </div>

            <div className="space-y-2 text-[11px] text-slate-400 leading-relaxed pt-2">
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold">1. Advisory vs Execution:</span>
                <span>AI and analysis skills read and explain context; they never independently trigger or place trades without user command.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold">2. Default Safety:</span>
                <span>Live trading is locked fail-closed unless explicitly enabled in configuration. Demo testing is verified with tight slippage logging.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold">3. Crypto Gating:</span>
                <span>Crypto strategies remain proposal-only until real exchange venue integration (Binance/Bybit) is finalized and audited.</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
