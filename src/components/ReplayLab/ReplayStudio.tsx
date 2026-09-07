import React, { useState, useEffect } from 'react';
import { ReplayFixture, Candle } from '../../types/trading';
import { CandlestickChart } from '../Chart/CandlestickChart';
import {
  extractSessionBoxes,
  findSwingPoints,
  detectStructureBreaks,
  detectOrderBlocks,
  detectFairValueGaps,
  detectLiquidityPools,
  evaluateAsianSweepStrategy
} from '../../utils/smcEngine';
import { REGISTERED_STRATEGIES } from '../../data/strategies';
import {
  Play,
  Pause,
  SkipForward,
  RotateCcw,
  CheckCircle2,
  TrendingUp,
  BarChart2,
  Calendar,
  Layers
} from 'lucide-react';

interface ReplayStudioProps {
  fixtures: ReplayFixture[];
}

export const ReplayStudio: React.FC<ReplayStudioProps> = ({ fixtures }) => {
  const [selectedFixtureId, setSelectedFixtureId] = useState<string>(fixtures[0]?.id || 'discovery_aug_sep2025');
  const selectedFixture = fixtures.find(f => f.id === selectedFixtureId) || fixtures[0];

  const fullCandles = selectedFixture?.candles || [];
  const [currentStep, setCurrentStep] = useState<number>(Math.min(30, fullCandles.length));
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  // Playback timer
  useEffect(() => {
    let timer: any;
    if (isPlaying) {
      timer = setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= fullCandles.length) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isPlaying, fullCandles.length]);

  const displayedCandles = fullCandles.slice(0, currentStep);
  const pipMultiplier = selectedFixture?.symbol === 'USDJPY' ? 100 : 10000;

  const sessionBoxes = extractSessionBoxes(displayedCandles, 25.0, pipMultiplier);
  const swingPoints = findSwingPoints(displayedCandles, 3);
  const structureBreaks = detectStructureBreaks(displayedCandles, swingPoints);
  const orderBlocks = detectOrderBlocks(displayedCandles, 'M15');
  const fairValueGaps = detectFairValueGaps(displayedCandles, 'M15');
  const liquidityPools = detectLiquidityPools(displayedCandles, swingPoints, 2.0, pipMultiplier);

  const activeProposal = evaluateAsianSweepStrategy(
    selectedFixture?.symbol || 'EURUSD',
    displayedCandles,
    REGISTERED_STRATEGIES[0],
    pipMultiplier,
    1.0,
    100000
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <RotateCcw className="w-5 h-5 text-cyan-400" />
            <span>Historical Replay & Golden Verification Lab</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Simulate point-in-time candle arrival without lookahead bias. Evaluates Stage 1 session eligibility and Stage 2 execution reconciliation against frozen fixture datasets.
          </p>
        </div>

        {/* Replay Controls */}
        <div className="flex items-center gap-2 bg-slate-950 p-2 rounded-xl border border-slate-800">
          <button
            id="replay-toggle-play"
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold transition flex items-center gap-1.5 text-xs font-mono"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            <span>{isPlaying ? 'Pause' : 'Play'}</span>
          </button>

          <button
            id="replay-step-forward"
            onClick={() => setCurrentStep(prev => Math.min(fullCandles.length, prev + 1))}
            disabled={currentStep >= fullCandles.length}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition text-xs font-mono flex items-center gap-1"
          >
            <SkipForward className="w-3.5 h-3.5" />
            <span>Step +1</span>
          </button>

          <button
            id="replay-reset"
            onClick={() => {
              setIsPlaying(false);
              setCurrentStep(20);
            }}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition text-xs font-mono"
          >
            Reset
          </button>

          <div className="px-3 text-xs font-mono text-slate-400">
            Step: <strong className="text-cyan-400">{currentStep}</strong> / {fullCandles.length}
          </div>
        </div>
      </div>

      {/* Fixtures Selector & Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {fixtures.map(f => {
          const isSelected = f.id === selectedFixtureId;
          return (
            <div
              key={f.id}
              onClick={() => {
                setSelectedFixtureId(f.id);
                setCurrentStep(25);
                setIsPlaying(false);
              }}
              className={`p-4 rounded-xl border cursor-pointer transition-all ${
                isSelected
                  ? 'bg-cyan-950/30 border-cyan-500/60 ring-1 ring-cyan-500/30'
                  : 'bg-slate-900 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-sm font-bold text-slate-200">{f.symbol}</span>
                <span className="text-xs font-mono text-emerald-400 font-bold">+{f.totalReturnR} R</span>
              </div>
              <div className="text-xs font-semibold text-cyan-400 mb-2 truncate">{f.name}</div>
              <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-400">
                <div>Events: {f.totalEvents}</div>
                <div>Stage 1: {f.stage1Qualified}</div>
                <div>Win Rate: {f.stage2WinRate}%</div>
                <div>{f.period}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Chart Canvas with current point-in-time slice */}
      <CandlestickChart
        candles={displayedCandles}
        symbol={selectedFixture?.symbol || 'EURUSD'}
        timeframe="M15"
        sessionBoxes={sessionBoxes}
        swingPoints={swingPoints}
        structureBreaks={structureBreaks}
        orderBlocks={orderBlocks}
        fairValueGaps={fairValueGaps}
        liquidityPools={liquidityPools}
        activeProposal={activeProposal}
      />
    </div>
  );
};
