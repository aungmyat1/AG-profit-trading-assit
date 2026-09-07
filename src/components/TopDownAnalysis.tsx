import React, { useState } from 'react';
import {
  Layers,
  TrendingUp,
  Target,
  Maximize2,
  CheckCircle,
  AlertCircle,
  Zap,
  Clock
} from 'lucide-react';
import { MOCK_CANDLES_EURUSD, EURUSD_ANALYSIS } from '../data/tradingData';

export const TopDownAnalysis: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('EURUSD');
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('M5');
  const [showSessionBox, setShowSessionBox] = useState<boolean>(true);
  const [showZones, setShowZones] = useState<boolean>(true);
  const [showStructureLabels, setShowStructureLabels] = useState<boolean>(true);

  const candles = MOCK_CANDLES_EURUSD;
  const analysis = EURUSD_ANALYSIS;

  // Chart coordinate calculations
  const minPrice = 1.15940;
  const maxPrice = 1.16280;
  const priceRange = maxPrice - minPrice;
  const chartHeight = 280;
  const chartWidth = 650;

  const getY = (price: number) => {
    return chartHeight - ((price - minPrice) / priceRange) * chartHeight;
  };

  const candleSpacing = chartWidth / candles.length;

  return (
    <div className="space-y-6">
      {/* Control Bar */}
      <div className="rounded-lg bg-slate-900 border border-slate-800 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div>
              <span className="text-xs text-slate-400 font-mono">Symbol:</span>
              <div className="flex mt-1 space-x-1">
                {['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSDT'].map((sym) => (
                  <button
                    key={sym}
                    onClick={() => setSelectedSymbol(sym)}
                    className={`px-2.5 py-1 text-xs font-mono font-semibold rounded transition-colors ${
                      selectedSymbol === sym
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-950 text-slate-300 border border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    {sym}
                  </button>
                ))}
              </div>
            </div>

            <div className="border-l border-slate-800 pl-3">
              <span className="text-xs text-slate-400 font-mono">Timeframe:</span>
              <div className="flex mt-1 space-x-1">
                {['D1', 'H4', 'H1', 'M15', 'M5'].map((tf) => (
                  <button
                    key={tf}
                    onClick={() => setSelectedTimeframe(tf)}
                    className={`px-2 py-1 text-xs font-mono rounded transition-colors ${
                      selectedTimeframe === tf
                        ? 'bg-slate-800 text-emerald-400 font-bold border border-emerald-500/40'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Layer toggles */}
          <div className="flex items-center space-x-2 text-xs font-mono">
            <button
              onClick={() => setShowSessionBox(!showSessionBox)}
              className={`px-2.5 py-1 rounded border transition-colors ${
                showSessionBox
                  ? 'bg-sky-950/60 text-sky-300 border-sky-600/50'
                  : 'bg-slate-950 text-slate-500 border-slate-800'
              }`}
            >
              Session Box
            </button>
            <button
              onClick={() => setShowZones(!showZones)}
              className={`px-2.5 py-1 rounded border transition-colors ${
                showZones
                  ? 'bg-emerald-950/60 text-emerald-300 border-emerald-600/50'
                  : 'bg-slate-950 text-slate-500 border-slate-800'
              }`}
            >
              Supply/Demand Zones
            </button>
            <button
              onClick={() => setShowStructureLabels(!showStructureLabels)}
              className={`px-2.5 py-1 rounded border transition-colors ${
                showStructureLabels
                  ? 'bg-amber-950/60 text-amber-300 border-amber-600/50'
                  : 'bg-slate-950 text-slate-500 border-slate-800'
              }`}
            >
              BOS / CHoCH
            </button>
          </div>
        </div>
      </div>

      {/* Main Analysis Stage */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Interactive Candlestick Chart View */}
        <div className="lg:col-span-2 rounded-lg bg-slate-900 border border-slate-800 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs font-mono">
            <div className="flex items-center space-x-2">
              <span className="font-bold text-white text-sm">{selectedSymbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 font-semibold">{selectedTimeframe}</span>
              <span className="text-slate-400">Asian Low Sweep & Bullish Re-test</span>
            </div>
            <div className="flex items-center space-x-3 text-[11px] text-slate-400">
              <span>H: 1.16260</span>
              <span>L: 1.15965</span>
              <span>C: 1.16250</span>
            </div>
          </div>

          {/* SVG Candlestick Canvas */}
          <div className="py-2 overflow-x-auto">
            <div className="relative" style={{ width: chartWidth, height: chartHeight }}>
              <svg width={chartWidth} height={chartHeight} className="overflow-visible">
                {/* Horizontal grid lines */}
                {[1.16000, 1.16100, 1.16200].map((level) => {
                  const y = getY(level);
                  return (
                    <g key={level}>
                      <line x1="0" y1={y} x2={chartWidth} y2={y} stroke="#1e293b" strokeDasharray="3 3" />
                      <text x={chartWidth - 55} y={y - 4} fill="#64748b" fontSize="10" fontFamily="monospace">
                        {level.toFixed(5)}
                      </text>
                    </g>
                  );
                })}

                {/* Equilibrium 50% line */}
                {showStructureLabels && (
                  <g>
                    <line
                      x1="0"
                      y1={getY(analysis.equilibrium50)}
                      x2={chartWidth}
                      y2={getY(analysis.equilibrium50)}
                      stroke="#475569"
                      strokeDasharray="4 2"
                    />
                    <text x="10" y={getY(analysis.equilibrium50) - 4} fill="#94a3b8" fontSize="9" fontFamily="monospace">
                      EQ 50% (1.16102)
                    </text>
                  </g>
                )}

                {/* Asian Reference Session Box */}
                {showSessionBox && (
                  <g>
                    <rect
                      x={candleSpacing * 0.5}
                      y={getY(1.16239)}
                      width={candleSpacing * 4.5}
                      height={getY(1.16023) - getY(1.16239)}
                      fill="#0284c7"
                      fillOpacity="0.12"
                      stroke="#0284c7"
                      strokeWidth="1"
                      strokeDasharray="4 2"
                    />
                    <text x={candleSpacing * 0.7} y={getY(1.16239) + 14} fill="#38bdf8" fontSize="10" fontFamily="monospace" fontWeight="bold">
                      ASIAN SESSION BOX (21.6 pips)
                    </text>
                    {/* Asian Low Level */}
                    <line
                      x1={candleSpacing * 4}
                      y1={getY(1.16023)}
                      x2={chartWidth}
                      y2={getY(1.16023)}
                      stroke="#f59e0b"
                      strokeWidth="1"
                      strokeDasharray="2 2"
                    />
                    <text x={chartWidth - 110} y={getY(1.16023) + 12} fill="#f59e0b" fontSize="9" fontFamily="monospace">
                      Asian Low (1.16023)
                    </text>
                  </g>
                )}

                {/* Order Block Zone */}
                {showZones && (
                  <g>
                    <rect
                      x={candleSpacing * 5.2}
                      y={getY(1.16040)}
                      width={chartWidth - candleSpacing * 5.2}
                      height={getY(1.15976) - getY(1.16040)}
                      fill="#10b981"
                      fillOpacity="0.15"
                      stroke="#10b981"
                      strokeWidth="1"
                    />
                    <text x={candleSpacing * 5.5} y={getY(1.16040) + 12} fill="#34d399" fontSize="9" fontFamily="monospace">
                      M5 Bullish Order Block (Demand)
                    </text>
                  </g>
                )}

                {/* Candlesticks */}
                {candles.map((c, i) => {
                  const x = (i + 0.5) * candleSpacing;
                  const isGreen = c.close >= c.open;
                  const color = isGreen ? '#10b981' : '#f43f5e';
                  const top = getY(Math.max(c.open, c.close));
                  const bottom = getY(Math.min(c.open, c.close));
                  const candleHeight = Math.max(bottom - top, 2);

                  return (
                    <g key={c.time}>
                      {/* Wick */}
                      <line
                        x1={x}
                        y1={getY(c.high)}
                        x2={x}
                        y2={getY(c.low)}
                        stroke={color}
                        strokeWidth="1.5"
                      />
                      {/* Body */}
                      <rect
                        x={x - 6}
                        y={top}
                        width="12"
                        height={candleHeight}
                        fill={color}
                        rx="1"
                      />
                      {/* Time Label */}
                      <text x={x - 12} y={chartHeight + 16} fill="#64748b" fontSize="9" fontFamily="monospace">
                        {c.time}
                      </text>
                    </g>
                  );
                })}

                {/* Structure Annotations */}
                {showStructureLabels && (
                  <g>
                    {/* Sweep Arrow */}
                    <path
                      d={`M ${(5.5) * candleSpacing} ${getY(1.15965) + 8} L ${(5.5) * candleSpacing} ${getY(1.15965) + 2} `}
                      stroke="#f59e0b"
                      strokeWidth="2"
                      markerEnd="url(#arrow)"
                    />
                    <text x={(5.5) * candleSpacing - 24} y={getY(1.15965) + 22} fill="#f59e0b" fontSize="9" fontFamily="monospace" fontWeight="bold">
                      SWEEP
                    </text>

                    {/* Bullish CHoCH */}
                    <line
                      x1={(6.5) * candleSpacing}
                      y1={getY(1.16060)}
                      x2={(8.5) * candleSpacing}
                      y2={getY(1.16060)}
                      stroke="#a855f7"
                      strokeWidth="1.5"
                      strokeDasharray="3 3"
                    />
                    <text x={(7) * candleSpacing} y={getY(1.16060) - 4} fill="#c084fc" fontSize="9" fontFamily="monospace">
                      CHoCH (M1)
                    </text>

                    {/* Entry Retest point */}
                    <circle cx={(7.5) * candleSpacing} cy={getY(1.16030)} r="4" fill="#38bdf8" />
                    <text x={(7.5) * candleSpacing + 8} y={getY(1.16030) + 3} fill="#38bdf8" fontSize="9" fontFamily="monospace" fontWeight="bold">
                      ENTRY (1.16030)
                    </text>
                  </g>
                )}
              </svg>
            </div>
          </div>

          <div className="pt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between font-mono">
            <span>Market Data: Vantage MT5 Feed (M5)</span>
            <span className="text-emerald-400">Deterministic Sweep Detected at 07:05 UTC</span>
          </div>
        </div>

        {/* Structure Tiers & Registered Strategy Alignment */}
        <div className="space-y-4">
          {/* Top-Down Structure Tiers */}
          <div className="rounded-lg bg-slate-900 border border-slate-800 p-4">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 pb-2 border-b border-slate-800 flex items-center space-x-1.5">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span>SMC Structure Tiers</span>
            </h3>

            <div className="mt-3 space-y-2.5 text-xs font-mono">
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/80">
                <span className="text-slate-400">HTF Trend (D1/H4):</span>
                <span className="text-emerald-400 font-bold">BULLISH EXPANSION</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/80">
                <span className="text-slate-400">Session Context:</span>
                <span className="text-sky-300">Asian Low Swept (-6 pips)</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/80">
                <span className="text-slate-400">LTF Confirmation:</span>
                <span className="text-emerald-300">Bullish CHoCH + Retest</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/80">
                <span className="text-slate-400">Discount/Premium:</span>
                <span className="text-amber-300">Discount Zone (Under EQ 50%)</span>
              </div>
            </div>
          </div>

          {/* Strategy Matcher */}
          <div className="rounded-lg bg-slate-900 border border-emerald-500/40 p-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <span className="text-xs font-mono font-bold text-white flex items-center space-x-1.5">
                <Zap className="w-4 h-4 text-amber-400" />
                <span>Strategy Authority Match</span>
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                MATCH FOUND
              </span>
            </div>

            <div className="mt-3 space-y-2 text-xs font-mono">
              <div>
                <span className="text-slate-500 text-[10px]">REGISTERED CONTRACT</span>
                <div className="text-slate-100 font-bold">ST_ASIAN_SWEEP_5R_V1</div>
              </div>
              <div>
                <span className="text-slate-500 text-[10px]">DECISION STATUS</span>
                <div className="text-emerald-400 font-semibold">ELIGIBLE TRADE PROPOSAL</div>
              </div>
              <p className="text-[11px] text-slate-300 bg-slate-950 p-2 rounded border border-slate-800 mt-2 leading-relaxed">
                {analysis.signalNotes}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
