import React, { useState } from 'react';
import {
  SymbolName,
  Candle,
  SessionBox,
  SMCFeature,
} from '../../types/trading';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import {
  Maximize2,
  TrendingUp,
  Layers,
  Zap,
} from 'lucide-react';

interface MarketChartProps {
  symbol: SymbolName;
  candles: Candle[];
  boxes: SessionBox[];
  smc: SMCFeature[];
}

export const MarketChart: React.FC<MarketChartProps> = ({
  symbol,
  candles,
  boxes,
  smc,
}) => {
  const [timeframe, setTimeframe] = useState<'M5' | 'M15' | 'H1' | 'H4' | 'D1'>('M15');
  const [showSMC, setShowSMC] = useState(true);
  const [showSessions, setShowSessions] = useState(true);

  const lastCandle = candles[candles.length - 1] || { close: 1.1600, high: 1.1610, low: 1.1590, open: 1.1595 };
  const firstCandle = candles[0] || { close: 1.1600 };
  const priceChange = lastCandle.close - firstCandle.close;
  const isPositive = priceChange >= 0;

  const asianBox = boxes.find((b) => b.session === 'ASIAN');

  // Chart data formatting
  const chartData = candles.map((c) => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
    session: c.session,
    asianHigh: asianBox ? asianBox.high : undefined,
    asianLow: asianBox ? asianBox.low : undefined,
  }));

  const minPrice = Math.min(...candles.map((c) => c.low));
  const maxPrice = Math.max(...candles.map((c) => c.high));
  const padding = (maxPrice - minPrice) * 0.1 || 0.001;

  const formatPrice = (v: number) => {
    if (symbol.includes('USDT') || symbol === 'USDJPY' || symbol === 'XAUUSD') {
      return v.toFixed(2);
    }
    return v.toFixed(5);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-4 shadow-sm">
      {/* Chart Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-white">{symbol}</h2>
              <span className="px-2 py-0.5 text-xs font-mono font-semibold rounded bg-slate-800 text-slate-300 border border-slate-700">
                {timeframe}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono mt-0.5">
              <span className="text-slate-400">Close:</span>
              <span className="text-base font-bold text-white">{formatPrice(lastCandle.close)}</span>
              <span className={`flex items-center gap-0.5 ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                <TrendingUp className={`w-3.5 h-3.5 ${!isPositive ? 'rotate-180' : ''}`} />
                {isPositive ? '+' : ''}{formatPrice(priceChange)} ({((priceChange / firstCandle.close) * 100).toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>

        {/* Toggles & Timeframe Switcher */}
        <div className="flex items-center gap-2">
          {/* Timeframe Buttons */}
          <div className="flex bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-xs font-mono">
            {(['M5', 'M15', 'H1', 'H4', 'D1'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 rounded transition ${
                  timeframe === tf
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Indicators Toggle */}
          <button
            onClick={() => setShowSessions(!showSessions)}
            className={`px-2.5 py-1 text-xs font-mono rounded border flex items-center gap-1.5 transition ${
              showSessions
                ? 'bg-indigo-950/60 text-indigo-300 border-indigo-700/60'
                : 'bg-slate-950 text-slate-500 border-slate-800'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Asian Box</span>
          </button>

          <button
            onClick={() => setShowSMC(!showSMC)}
            className={`px-2.5 py-1 text-xs font-mono rounded border flex items-center gap-1.5 transition ${
              showSMC
                ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60'
                : 'bg-slate-950 text-slate-500 border-slate-800'
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            <span>SMC / Sweeps</span>
          </button>
        </div>
      </div>

      {/* Asian Range Summary Bar */}
      {asianBox && showSessions && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 text-xs font-mono">
          <div>
            <span className="text-slate-500">Asian High:</span>{' '}
            <span className="text-indigo-400 font-semibold">{formatPrice(asianBox.high)}</span>
          </div>
          <div>
            <span className="text-slate-500">Asian Low:</span>{' '}
            <span className="text-indigo-400 font-semibold">{formatPrice(asianBox.low)}</span>
          </div>
          <div>
            <span className="text-slate-500">Range:</span>{' '}
            <span className="text-slate-300 font-semibold">
              {((asianBox.high - asianBox.low) * (symbol.includes('JPY') ? 100 : 10000)).toFixed(1)} pips
            </span>
          </div>
          <div>
            <span className="text-slate-500">London Sweep:</span>{' '}
            <span className="text-emerald-400 font-bold">
              {asianBox.sweptLow ? 'LOW SWEPT (BULLISH SETUP)' : 'NONE'}
            </span>
          </div>
        </div>
      )}

      {/* Recharts Graphical View */}
      <div className="h-72 w-full pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={isPositive ? '#10b981' : '#f43f5e'} stopOpacity={0.3} />
                <stop offset="95%" stopColor={isPositive ? '#10b981' : '#f43f5e'} stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="time" stroke="#475569" fontSize={10} tickLine={false} />
            <YAxis
              domain={[minPrice - padding, maxPrice + padding]}
              stroke="#475569"
              fontSize={10}
              tickFormatter={formatPrice}
              orientation="right"
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#090d16',
                borderColor: '#1e293b',
                borderRadius: '8px',
                color: '#fff',
                fontSize: '12px',
                fontFamily: 'monospace',
              }}
              formatter={(val: any) => [
                typeof val === 'number' ? formatPrice(val) : String(val ?? ''),
                'Price',
              ]}
            />

            {/* Asian High / Low Reference Lines */}
            {asianBox && showSessions && (
              <>
                <ReferenceLine
                  y={asianBox.high}
                  stroke="#818cf8"
                  strokeDasharray="3 3"
                  label={{ value: 'Asian High', fill: '#818cf8', fontSize: 10, position: 'left' }}
                />
                <ReferenceLine
                  y={asianBox.low}
                  stroke="#818cf8"
                  strokeDasharray="3 3"
                  label={{ value: 'Asian Low (Swept)', fill: '#818cf8', fontSize: 10, position: 'left' }}
                />
              </>
            )}

            {/* Price Line & Fill */}
            <Area
              type="monotone"
              dataKey="close"
              stroke={isPositive ? '#10b981' : '#f43f5e'}
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#priceGradient)"
            />

            <Line type="monotone" dataKey="high" stroke="#334155" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="low" stroke="#334155" strokeWidth={1} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* SMC Annotations Strip */}
      {showSMC && smc.length > 0 && (
        <div className="border-t border-slate-800 pt-3">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Detected Market Structure & Imbalances
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {smc.map((item) => (
              <div
                key={item.id}
                className="px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono flex items-center gap-2"
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    item.type.includes('SWEEP')
                      ? 'bg-amber-400'
                      : item.type === 'FVG'
                      ? 'bg-indigo-400'
                      : 'bg-emerald-400'
                  }`}
                />
                <span className="font-semibold text-slate-200">{item.type}:</span>
                <span className="text-slate-400">{item.description}</span>
                <span className="text-slate-500 text-[10px]">@{formatPrice(item.price)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
