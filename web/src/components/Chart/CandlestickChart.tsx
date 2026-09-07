import React, { useState, useRef, useEffect, useMemo } from 'react';
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
import { calculateEMA } from '../../utils/smcEngine';
import {
  Eye,
  EyeOff,
  ZoomIn,
  ZoomOut,
  RefreshCw,
  Maximize2,
  ShieldAlert,
  Layers,
  ChevronDown,
  Check
} from 'lucide-react';

interface ChartProps {
  candles: Candle[];
  symbol: string;
  timeframe: string;
  sessionBoxes: SessionBox[];
  swingPoints: SwingPoint[];
  structureBreaks: StructureBreak[];
  orderBlocks: OrderBlock[];
  fairValueGaps: FairValueGap[];
  liquidityPools: LiquidityPool[];
  activeProposal: TradeProposal | null;
  onExecuteClick?: () => void;
}

export const CandlestickChart: React.FC<ChartProps> = ({
  candles,
  symbol,
  timeframe,
  sessionBoxes,
  swingPoints,
  structureBreaks,
  orderBlocks,
  fairValueGaps,
  liquidityPools,
  activeProposal,
  onExecuteClick
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 480 });
  const [visibleCount, setVisibleCount] = useState<number>(48);
  const [offsetIndex, setOffsetIndex] = useState<number>(0);
  const [hoveredCandle, setHoveredCandle] = useState<Candle | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);

  // Individual Session visibility toggles
  const [showAsianSession, setShowAsianSession] = useState<boolean>(true);
  const [showLondonSession, setShowLondonSession] = useState<boolean>(true);
  const [showNYSession, setShowNYSession] = useState<boolean>(true);

  // Other Overlay visibility toggles
  const [showSMC, setShowSMC] = useState(true);
  const [showOrderBlocks, setShowOrderBlocks] = useState(true);
  const [showLiquidity, setShowLiquidity] = useState(true);
  const [showEMA, setShowEMA] = useState(true);
  const [showTradeLevels, setShowTradeLevels] = useState(true);

  // Helper calculation for all/any sessions
  const allSessionsActive = showAsianSession && showLondonSession && showNYSession;
  const anySessionActive = showAsianSession || showLondonSession || showNYSession;

  const toggleAllSessions = () => {
    if (allSessionsActive) {
      setShowAsianSession(false);
      setShowLondonSession(false);
      setShowNYSession(false);
    } else {
      setShowAsianSession(true);
      setShowLondonSession(true);
      setShowNYSession(true);
    }
  };

  // Responsive dimensions
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {
          setDimensions({
            width: entry.contentRect.width,
            height: Math.max(450, entry.contentRect.height)
          });
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Visible slice of candles
  const visibleCandles = useMemo(() => {
    const total = candles.length;
    const start = Math.max(0, total - visibleCount - offsetIndex);
    const end = Math.min(total, start + visibleCount);
    return candles.slice(start, end);
  }, [candles, visibleCount, offsetIndex]);

  // Price range calculation with padding
  const { minPrice, maxPrice, priceRange } = useMemo(() => {
    if (visibleCandles.length === 0) return { minPrice: 1, maxPrice: 2, priceRange: 1 };
    let min = Math.min(...visibleCandles.map(c => c.low));
    let max = Math.max(...visibleCandles.map(c => c.high));

    // Also include trade levels if active
    if (activeProposal && activeProposal.entryPrice && activeProposal.stopLoss) {
      min = Math.min(min, activeProposal.stopLoss, activeProposal.takeProfit1 || min);
      max = Math.max(max, activeProposal.stopLoss, activeProposal.takeProfit2 || max);
    }

    const padding = (max - min) * 0.1 || 0.001;
    return {
      minPrice: min - padding,
      maxPrice: max + padding,
      priceRange: max - min + padding * 2
    };
  }, [visibleCandles, activeProposal]);

  // Chart layout margins
  const margin = { top: 20, right: 70, bottom: 30, left: 10 };
  const chartWidth = Math.max(100, dimensions.width - margin.left - margin.right);
  const chartHeight = Math.max(100, dimensions.height - margin.top - margin.bottom);

  // Scaling helpers
  const candleWidth = chartWidth / Math.max(1, visibleCandles.length);
  const getX = (index: number) => margin.left + index * candleWidth + candleWidth / 2;
  const getY = (price: number) => margin.top + chartHeight - ((price - minPrice) / priceRange) * chartHeight;

  // 50 EMA calculation
  const ema50Values = useMemo(() => {
    const closes = candles.map(c => c.close);
    const emaAll = calculateEMA(closes, 50);
    // Slice to visible
    const total = candles.length;
    const start = Math.max(0, total - visibleCount - offsetIndex);
    const end = Math.min(total, start + visibleCount);
    return emaAll.slice(start, end);
  }, [candles, visibleCount, offsetIndex]);

  // Handle Zoom
  const handleZoomIn = () => setVisibleCount(prev => Math.max(24, prev - 12));
  const handleZoomOut = () => setVisibleCount(prev => Math.min(candles.length, prev + 12));
  const handleResetZoom = () => {
    setVisibleCount(48);
    setOffsetIndex(0);
  };

  // Mouse move for crosshair
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setMousePos({ x, y });

    const candleIdx = Math.floor((x - margin.left) / candleWidth);
    if (candleIdx >= 0 && candleIdx < visibleCandles.length) {
      setHoveredCandle(visibleCandles[candleIdx]);
    } else {
      setHoveredCandle(null);
    }
  };

  const handleMouseLeave = () => {
    setMousePos(null);
    setHoveredCandle(null);
  };

  // Price ticks
  const priceTicks = useMemo(() => {
    const count = 6;
    const ticks: number[] = [];
    for (let i = 0; i <= count; i++) {
      ticks.push(minPrice + (priceRange * i) / count);
    }
    return ticks;
  }, [minPrice, priceRange]);

  const digits = symbol.includes('JPY') ? 3 : symbol.includes('BTC') ? 1 : 5;

  return (
    <div className="flex flex-col bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl" ref={containerRef}>
      {/* Chart Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-sm text-cyan-400">{symbol}</span>
            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px] font-semibold">
              {timeframe}
            </span>
          </div>

          {/* Candle Info HUD */}
          {hoveredCandle ? (
            <div className="hidden lg:flex items-center gap-3 font-mono text-[11px] text-slate-400 bg-slate-900 px-2.5 py-1 rounded border border-slate-800">
              <span>O: <strong className="text-slate-200">{hoveredCandle.open.toFixed(digits)}</strong></span>
              <span>H: <strong className="text-emerald-400">{hoveredCandle.high.toFixed(digits)}</strong></span>
              <span>L: <strong className="text-rose-400">{hoveredCandle.low.toFixed(digits)}</strong></span>
              <span>C: <strong className="text-cyan-300">{hoveredCandle.close.toFixed(digits)}</strong></span>
              <span>Vol: <strong className="text-slate-300">{hoveredCandle.volume}</strong></span>
            </div>
          ) : (
            <div className="hidden lg:flex items-center gap-2 text-slate-500 font-mono text-[11px]">
              <span>Hover chart for OHLCV</span>
            </div>
          )}
        </div>

        {/* Overlays Control & Zoom */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Individual Session Box Toggles Group */}
          <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-[11px] font-mono">
            {/* Master Toggle */}
            <button
              id="toggle-session-boxes-all"
              onClick={toggleAllSessions}
              className={`px-2 py-1 rounded transition flex items-center gap-1 font-semibold ${
                allSessionsActive
                  ? 'bg-indigo-500/20 text-indigo-300'
                  : anySessionActive
                  ? 'bg-slate-800 text-slate-300'
                  : 'bg-transparent text-slate-500 hover:text-slate-400'
              }`}
              title={allSessionsActive ? 'Hide all session boxes' : 'Show all session boxes'}
            >
              <Layers className="w-3 h-3 text-indigo-400" />
              <span className="hidden sm:inline">Sessions</span>
            </button>

            <div className="h-3 w-px bg-slate-800 mx-0.5" />

            {/* Asian Session Toggle */}
            <button
              id="toggle-session-asian"
              onClick={() => setShowAsianSession(!showAsianSession)}
              className={`px-2 py-1 rounded transition flex items-center gap-1.5 border text-[11px] font-mono ${
                showAsianSession
                  ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40 font-semibold'
                  : 'bg-transparent text-slate-500 border-transparent hover:text-slate-400 opacity-60'
              }`}
              title="Toggle Asian Session Box (00:00 - 06:00 UTC)"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${showAsianSession ? 'bg-indigo-400' : 'bg-slate-600'}`} />
              <span>Asian</span>
            </button>

            {/* London Session Toggle */}
            <button
              id="toggle-session-london"
              onClick={() => setShowLondonSession(!showLondonSession)}
              className={`px-2 py-1 rounded transition flex items-center gap-1.5 border text-[11px] font-mono ${
                showLondonSession
                  ? 'bg-sky-500/20 text-sky-300 border-sky-500/40 font-semibold'
                  : 'bg-transparent text-slate-500 border-transparent hover:text-slate-400 opacity-60'
              }`}
              title="Toggle London Session Box (06:00 - 11:00 UTC)"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${showLondonSession ? 'bg-sky-400' : 'bg-slate-600'}`} />
              <span>London</span>
            </button>

            {/* New York Session Toggle */}
            <button
              id="toggle-session-ny"
              onClick={() => setShowNYSession(!showNYSession)}
              className={`px-2 py-1 rounded transition flex items-center gap-1.5 border text-[11px] font-mono ${
                showNYSession
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold'
                  : 'bg-transparent text-slate-500 border-transparent hover:text-slate-400 opacity-60'
              }`}
              title="Toggle New York Session Box (12:00 - 17:00 UTC)"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${showNYSession ? 'bg-amber-400' : 'bg-slate-600'}`} />
              <span>NY</span>
            </button>
          </div>

          {/* Technical Overlays */}
          <div className="flex items-center gap-1">
            <button
              id="toggle-smc"
              onClick={() => setShowSMC(!showSMC)}
              className={`px-2 py-1 rounded text-[11px] font-mono transition-all border ${
                showSMC ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'bg-slate-900 text-slate-500 border-slate-800'
              }`}
              title="Toggle BOS / CHoCH & Swings"
            >
              BOS/CHoCH
            </button>

            <button
              id="toggle-order-blocks"
              onClick={() => setShowOrderBlocks(!showOrderBlocks)}
              className={`px-2 py-1 rounded text-[11px] font-mono transition-all border ${
                showOrderBlocks ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-slate-900 text-slate-500 border-slate-800'
              }`}
              title="Toggle Order Blocks & FVGs"
            >
              OB/FVG
            </button>

            <button
              id="toggle-liquidity"
              onClick={() => setShowLiquidity(!showLiquidity)}
              className={`px-2 py-1 rounded text-[11px] font-mono transition-all border ${
                showLiquidity ? 'bg-rose-500/20 text-rose-300 border-rose-500/40' : 'bg-slate-900 text-slate-500 border-slate-800'
              }`}
              title="Toggle Liquidity Pools (EQH/EQL)"
            >
              Liquidity
            </button>

            <button
              id="toggle-ema"
              onClick={() => setShowEMA(!showEMA)}
              className={`px-2 py-1 rounded text-[11px] font-mono transition-all border ${
                showEMA ? 'bg-blue-500/20 text-blue-300 border-blue-500/40' : 'bg-slate-900 text-slate-500 border-slate-800'
              }`}
              title="Toggle 50 EMA Trend Filter"
            >
              50 EMA
            </button>
          </div>

          <div className="h-4 w-px bg-slate-800 mx-0.5" />

          {/* Zoom buttons */}
          <button
            id="btn-zoom-in"
            onClick={handleZoomIn}
            className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Zoom In"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            id="btn-zoom-out"
            onClick={handleZoomOut}
            className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Zoom Out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            id="btn-zoom-reset"
            onClick={handleResetZoom}
            className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Reset View"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* SVG Canvas Area */}
      <div className="relative flex-1 w-full bg-slate-950/60 min-h-[440px]">
        {/* Active Trade Proposal Notification Overlay */}
        {activeProposal && activeProposal.state === 'READY' && (
          <div className="absolute top-3 left-3 z-20 flex items-center gap-3 bg-emerald-950/90 border border-emerald-500/50 p-2.5 rounded-lg shadow-2xl backdrop-blur">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <div className="font-mono text-xs">
              <div className="font-bold text-emerald-300 flex items-center gap-1.5">
                <span>SIGNAL READY:</span>
                <span className="px-1.5 py-0.5 bg-emerald-500/20 rounded text-emerald-200">
                  {activeProposal.entrySide} {activeProposal.symbol} @ {activeProposal.entryPrice?.toFixed(digits)}
                </span>
                <span className="text-slate-400 font-normal">({activeProposal.riskReward}R Target)</span>
              </div>
              <div className="text-[11px] text-emerald-400/80 mt-0.5">
                SL: {activeProposal.stopLoss?.toFixed(digits)} | TP1: {activeProposal.takeProfit1?.toFixed(digits)} | TP2 (5R): {activeProposal.takeProfit2?.toFixed(digits)}
              </div>
            </div>
            {onExecuteClick && (
              <button
                id="btn-quick-execute-signal"
                onClick={onExecuteClick}
                className="ml-2 px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs rounded transition shadow-lg flex items-center gap-1"
              >
                <span>Execute (Demo)</span>
              </button>
            )}
          </div>
        )}

        <svg
          className="w-full h-full cursor-crosshair select-none"
          width={dimensions.width}
          height={dimensions.height}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            <pattern id="grid-pattern" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" strokeOpacity="0.4" />
            </pattern>
          </defs>

          {/* Grid background */}
          <rect width={dimensions.width} height={dimensions.height} fill="url(#grid-pattern)" />

          {/* 1. Session Boxes Layer */}
          {sessionBoxes.map(box => {
            const isAsian = box.sessionType === 'Asian';
            const isLondon = box.sessionType === 'London' || box.sessionType === 'London_Open';
            const isNY = box.sessionType === 'New_York' || box.sessionType === 'New_York_Open';

            // Check visibility according to individual session toggles
            if (isAsian && !showAsianSession) return null;
            if (isLondon && !showLondonSession) return null;
            if (isNY && !showNYSession) return null;

            const startIdx = visibleCandles.findIndex(c => c.time >= box.startTime);
            let endIdx = -1;
            for (let idx = visibleCandles.length - 1; idx >= 0; idx--) {
              if (visibleCandles[idx].time <= box.endTime) {
                endIdx = idx;
                break;
              }
            }
            if (startIdx === -1 && endIdx === -1) return null;

            const x1 = startIdx !== -1 ? getX(startIdx) - candleWidth / 2 : margin.left;
            const x2 = endIdx !== -1 ? getX(endIdx) + candleWidth / 2 : margin.left + chartWidth;
            const boxW = Math.max(4, x2 - x1);
            const yHigh = getY(box.high);
            const yLow = getY(box.low);
            const boxH = Math.max(2, yLow - yHigh);
            const yMid = getY(box.midline);

            const color = isAsian ? '#818cf8' : isLondon ? '#38bdf8' : '#f59e0b';
            const labelText = isAsian
              ? `Asian Range (${box.rangePips} pips)`
              : isLondon
              ? `London Range (${box.rangePips} pips)`
              : `NY Range (${box.rangePips} pips)`;

            return (
              <g key={box.id} className="transition-opacity opacity-85 hover:opacity-100">
                {/* Shaded Box */}
                <rect
                  x={x1}
                  y={yHigh}
                  width={boxW}
                  height={boxH}
                  fill={color}
                  fillOpacity="0.08"
                  stroke={color}
                  strokeWidth="1"
                  strokeDasharray="4 2"
                  rx="3"
                />
                {/* Midline */}
                <line
                  x1={x1}
                  y1={yMid}
                  x2={x1 + boxW}
                  y2={yMid}
                  stroke={color}
                  strokeWidth="0.8"
                  strokeDasharray="2 2"
                  strokeOpacity="0.6"
                />
                {/* Label */}
                <text
                  x={x1 + 6}
                  y={yHigh + 14}
                  fill={color}
                  fontSize="10"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  {labelText}
                </text>
                {/* High/Low markers */}
                <text x={x1 + boxW - 4} y={yHigh - 4} textAnchor="end" fill={color} fontSize="9" fontFamily="monospace">
                  H: {box.high.toFixed(digits)}
                </text>
                <text x={x1 + boxW - 4} y={yLow + 11} textAnchor="end" fill={color} fontSize="9" fontFamily="monospace">
                  L: {box.low.toFixed(digits)}
                </text>
              </g>
            );
          })}

          {/* 2. Order Blocks & FVGs Layer */}
          {showOrderBlocks &&
            orderBlocks.map(ob => {
              const startIdx = visibleCandles.findIndex(c => c.time >= ob.startTime);
              if (startIdx === -1) return null;
              const x1 = getX(startIdx);
              const x2 = margin.left + chartWidth;
              const yTop = getY(ob.topPrice);
              const yBottom = getY(ob.bottomPrice);
              const h = Math.max(2, yBottom - yTop);
              const isBull = ob.type === 'BULLISH_OB';
              const color = isBull ? '#10b981' : '#f43f5e';

              return (
                <g key={ob.id}>
                  <rect
                    x={x1}
                    y={yTop}
                    width={x2 - x1}
                    height={h}
                    fill={color}
                    fillOpacity={ob.isMitigated ? '0.04' : '0.15'}
                    stroke={color}
                    strokeWidth="0.8"
                    strokeDasharray={ob.isMitigated ? '2 2' : 'none'}
                  />
                  <text
                    x={x1 + 4}
                    y={yTop + 11}
                    fill={color}
                    fontSize="9"
                    fontFamily="monospace"
                    fontWeight="600"
                    opacity={ob.isMitigated ? 0.5 : 1}
                  >
                    {isBull ? 'Bullish OB' : 'Bearish OB'} {ob.isMitigated ? '(Mitigated)' : ''}
                  </text>
                </g>
              );
            })}

          {/* 3. Fair Value Gaps */}
          {showOrderBlocks &&
            fairValueGaps.map(fvg => {
              const startIdx = visibleCandles.findIndex(c => c.time >= fvg.startTime);
              if (startIdx === -1) return null;
              const x1 = getX(startIdx);
              const x2 = x1 + candleWidth * 8;
              const yTop = getY(fvg.topPrice);
              const yBottom = getY(fvg.bottomPrice);
              const isBull = fvg.type === 'BULLISH_FVG';
              const color = isBull ? '#06b6d4' : '#f59e0b';

              return (
                <rect
                  key={fvg.id}
                  x={x1}
                  y={yTop}
                  width={Math.max(10, x2 - x1)}
                  height={Math.max(2, yBottom - yTop)}
                  fill={color}
                  fillOpacity="0.12"
                  stroke={color}
                  strokeWidth="0.5"
                  strokeDasharray="2 1"
                />
              );
            })}

          {/* 4. Liquidity Pools (EQH / EQL) */}
          {showLiquidity &&
            liquidityPools.map(pool => {
              const startIdx = visibleCandles.findIndex(c => c.time >= pool.startTime);
              if (startIdx === -1) return null;
              const x1 = getX(startIdx);
              const x2 = margin.left + chartWidth;
              const y = getY(pool.price);
              const color = pool.type === 'EQH' || pool.type === 'BSL' ? '#fb7185' : '#34d399';

              return (
                <g key={pool.id}>
                  <line
                    x1={x1}
                    y1={y}
                    x2={x2}
                    y2={y}
                    stroke={color}
                    strokeWidth="1.2"
                    strokeDasharray="4 3"
                    opacity={pool.isSwept ? 0.4 : 0.9}
                  />
                  <text
                    x={x2 - 6}
                    y={y - 4}
                    textAnchor="end"
                    fill={color}
                    fontSize="9"
                    fontFamily="monospace"
                    fontWeight="bold"
                    opacity={pool.isSwept ? 0.5 : 1}
                  >
                    {pool.type} {pool.isSwept ? '[SWEPT]' : 'POOL ($$$)'}
                  </text>
                </g>
              );
            })}

          {/* 5. 50 EMA Line */}
          {showEMA && (
            <path
              d={visibleCandles
                .map((_, i) => {
                  const val = ema50Values[i];
                  if (!val) return '';
                  const x = getX(i);
                  const y = getY(val);
                  return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                })
                .join(' ')}
              fill="none"
              stroke="#3b82f6"
              strokeWidth="1.5"
              strokeOpacity="0.7"
            />
          )}

          {/* 6. Candlesticks Layer */}
          {visibleCandles.map((c, i) => {
            const x = getX(i);
            const yOpen = getY(c.open);
            const yClose = getY(c.close);
            const yHigh = getY(c.high);
            const yLow = getY(c.low);

            const isUp = c.close >= c.open;
            const candleBodyTop = Math.min(yOpen, yClose);
            const candleBodyH = Math.max(1.5, Math.abs(yClose - yOpen));
            const color = isUp ? '#22c55e' : '#ef4444';
            const bodyW = Math.max(2, candleWidth * 0.7);

            return (
              <g key={c.time} className="transition-transform">
                {/* Upper and lower wicks */}
                <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth="1" />
                {/* Candle Body */}
                <rect
                  x={x - bodyW / 2}
                  y={candleBodyTop}
                  width={bodyW}
                  height={candleBodyH}
                  fill={isUp ? color : color}
                  stroke={color}
                  strokeWidth="0.5"
                  rx="1"
                />
              </g>
            );
          })}

          {/* 7. Structure Breaks (BOS / CHoCH) */}
          {showSMC &&
            structureBreaks.map(brk => {
              const idx = visibleCandles.findIndex(c => c.time === brk.time);
              if (idx === -1) return null;
              const x = getX(idx);
              const yLevel = getY(brk.brokenLevel);
              const color = brk.type === 'CHOCH' ? '#eab308' : '#a855f7';

              return (
                <g key={brk.id}>
                  <line
                    x1={x - candleWidth * 4}
                    y1={yLevel}
                    x2={x + candleWidth}
                    y2={yLevel}
                    stroke={color}
                    strokeWidth="1.2"
                    strokeDasharray="2 2"
                  />
                  <text
                    x={x}
                    y={yLevel - 4}
                    textAnchor="middle"
                    fill={color}
                    fontSize="9"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {brk.type} ({brk.direction[0]})
                  </text>
                </g>
              );
            })}

          {/* 8. Active Trade Levels (Entry, SL, TP1, TP2) */}
          {showTradeLevels && activeProposal && activeProposal.entryPrice && activeProposal.stopLoss && (
            <g className="font-mono text-xs font-bold">
              {/* Entry Level */}
              <line
                x1={margin.left}
                y1={getY(activeProposal.entryPrice)}
                x2={margin.left + chartWidth}
                y2={getY(activeProposal.entryPrice)}
                stroke="#06b6d4"
                strokeWidth="1.5"
                strokeDasharray="5 3"
              />
              <text x={margin.left + chartWidth + 4} y={getY(activeProposal.entryPrice) + 4} fill="#06b6d4" fontSize="10">
                ENTRY: {activeProposal.entryPrice.toFixed(digits)}
              </text>

              {/* Stop Loss Level */}
              <line
                x1={margin.left}
                y1={getY(activeProposal.stopLoss)}
                x2={margin.left + chartWidth}
                y2={getY(activeProposal.stopLoss)}
                stroke="#f43f5e"
                strokeWidth="1.5"
                strokeDasharray="4 2"
              />
              <text x={margin.left + chartWidth + 4} y={getY(activeProposal.stopLoss) + 4} fill="#f43f5e" fontSize="10">
                SL: {activeProposal.stopLoss.toFixed(digits)}
              </text>

              {/* TP1 (Opposite Boundary / 3R) */}
              {activeProposal.takeProfit1 && (
                <>
                  <line
                    x1={margin.left}
                    y1={getY(activeProposal.takeProfit1)}
                    x2={margin.left + chartWidth}
                    y2={getY(activeProposal.takeProfit1)}
                    stroke="#10b981"
                    strokeWidth="1.2"
                    strokeDasharray="4 3"
                  />
                  <text x={margin.left + chartWidth + 4} y={getY(activeProposal.takeProfit1) + 4} fill="#10b981" fontSize="10">
                    TP1 (75%): {activeProposal.takeProfit1.toFixed(digits)}
                  </text>
                </>
              )}

              {/* TP2 (5R Runner) */}
              {activeProposal.takeProfit2 && (
                <>
                  <line
                    x1={margin.left}
                    y1={getY(activeProposal.takeProfit2)}
                    x2={margin.left + chartWidth}
                    y2={getY(activeProposal.takeProfit2)}
                    stroke="#22c55e"
                    strokeWidth="1.8"
                  />
                  <text x={margin.left + chartWidth + 4} y={getY(activeProposal.takeProfit2) + 4} fill="#22c55e" fontSize="10">
                    TP2 (5R): {activeProposal.takeProfit2.toFixed(digits)}
                  </text>
                </>
              )}
            </g>
          )}

          {/* 9. Crosshair & Mouse Tracking */}
          {mousePos && (
            <g className="pointer-events-none">
              {/* Vertical line */}
              <line
                x1={mousePos.x}
                y1={margin.top}
                x2={mousePos.x}
                y2={margin.top + chartHeight}
                stroke="#64748b"
                strokeWidth="0.8"
                strokeDasharray="3 3"
              />
              {/* Horizontal line */}
              <line
                x1={margin.left}
                y1={mousePos.y}
                x2={margin.left + chartWidth}
                y2={mousePos.y}
                stroke="#64748b"
                strokeWidth="0.8"
                strokeDasharray="3 3"
              />
              {/* Price tag on right axis */}
              {mousePos.y >= margin.top && mousePos.y <= margin.top + chartHeight && (
                <g>
                  <rect
                    x={margin.left + chartWidth}
                    y={mousePos.y - 10}
                    width={60}
                    height={20}
                    fill="#1e293b"
                    rx="3"
                  />
                  <text
                    x={margin.left + chartWidth + 30}
                    y={mousePos.y + 4}
                    textAnchor="middle"
                    fill="#f8fafc"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    {(maxPrice - ((mousePos.y - margin.top) / chartHeight) * priceRange).toFixed(digits)}
                  </text>
                </g>
              )}
            </g>
          )}

          {/* 10. Right Price Axis */}
          {priceTicks.map((price, i) => {
            const y = getY(price);
            return (
              <g key={i}>
                <line x1={margin.left} y1={y} x2={margin.left + chartWidth} y2={y} stroke="#1e293b" strokeWidth="0.5" />
                <text
                  x={margin.left + chartWidth + 8}
                  y={y + 3}
                  fill="#64748b"
                  fontSize="10"
                  fontFamily="monospace"
                >
                  {price.toFixed(digits)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Chart Bottom Info Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2 bg-slate-950 border-t border-slate-800 text-slate-400 text-xs font-mono">
        <div className="flex items-center gap-4 flex-wrap">
          <button
            onClick={() => setShowAsianSession(!showAsianSession)}
            className={`flex items-center gap-1.5 transition ${showAsianSession ? 'text-indigo-300' : 'text-slate-600 line-through'}`}
            title="Click to toggle Asian session box"
          >
            <span className={`w-2.5 h-2.5 rounded border ${showAsianSession ? 'bg-indigo-500/40 border-indigo-500' : 'bg-slate-800 border-slate-700'}`} />
            <span>Asian (00-06 UTC)</span>
          </button>

          <button
            onClick={() => setShowLondonSession(!showLondonSession)}
            className={`flex items-center gap-1.5 transition ${showLondonSession ? 'text-sky-300' : 'text-slate-600 line-through'}`}
            title="Click to toggle London session box"
          >
            <span className={`w-2.5 h-2.5 rounded border ${showLondonSession ? 'bg-sky-500/40 border-sky-500' : 'bg-slate-800 border-slate-700'}`} />
            <span>London (06-11 UTC)</span>
          </button>

          <button
            onClick={() => setShowNYSession(!showNYSession)}
            className={`flex items-center gap-1.5 transition ${showNYSession ? 'text-amber-300' : 'text-slate-600 line-through'}`}
            title="Click to toggle New York session box"
          >
            <span className={`w-2.5 h-2.5 rounded border ${showNYSession ? 'bg-amber-500/40 border-amber-500' : 'bg-slate-800 border-slate-700'}`} />
            <span>New York (12-17 UTC)</span>
          </button>

          <div className="flex items-center gap-1.5 text-cyan-400 hidden md:flex">
            <span className="w-2.5 h-2.5 rounded bg-cyan-500/40 border border-cyan-500" />
            <span>5R Target Model</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span>Bars: {visibleCandles.length} / {candles.length}</span>
          <span>Spread: ~1.0 pip</span>
        </div>
      </div>
    </div>
  );
};
