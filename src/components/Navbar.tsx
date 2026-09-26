import React from 'react';
import {
  SymbolName,
  MarketSession,
  BrokerStatus,
} from '../types/trading';
import {
  Activity,
  ShieldCheck,
  Clock,
  Radio,
  Server,
} from 'lucide-react';

interface NavbarProps {
  activeSymbol: SymbolName;
  onSelectSymbol: (s: SymbolName) => void;
  activeSession: MarketSession;
  brokerStatus: BrokerStatus;
  currentTimeUtc: string;
  apiMode: 'mock' | 'real';
  onToggleApiMode: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeSymbol,
  onSelectSymbol,
  activeSession,
  brokerStatus,
  currentTimeUtc,
  apiMode,
  onToggleApiMode,
}) => {
  const symbols: { name: SymbolName; type: 'FX' | 'CRYPTO' | 'METAL' }[] = [
    { name: 'EURUSD', type: 'FX' },
    { name: 'GBPUSD', type: 'FX' },
    { name: 'USDJPY', type: 'FX' },
    { name: 'XAUUSD', type: 'METAL' },
    { name: 'BTCUSDT', type: 'CRYPTO' },
    { name: 'ETHUSDT', type: 'CRYPTO' },
  ];

  const getSessionBadge = () => {
    switch (activeSession) {
      case 'ASIAN':
        return { label: 'ASIAN SESSION (00:00-08:00 UTC)', color: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' };
      case 'LONDON':
        return { label: 'LONDON SESSION (07:00-15:00 UTC)', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };
      case 'NEW_YORK':
        return { label: 'NEW YORK SESSION (13:00-21:00 UTC)', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' };
      default:
        return { label: 'MARKET OFF-HOURS', color: 'bg-slate-700/20 text-slate-400 border-slate-700' };
    }
  };

  const sessionInfo = getSessionBadge();

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand & Strategy Authority Badge */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base tracking-wider text-white">AG PROFIT TRADING</span>
                <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">
                  v1.0.3
                </span>
                <span className="px-1.5 py-0.5 text-[10px] font-mono font-medium bg-slate-800 text-slate-300 rounded border border-slate-700">
                  DETERMINISTIC
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono flex items-center gap-1.5">
                <span>Authority: Strategy Engine &rarr; Execution Guard &rarr; MT5</span>
              </p>
            </div>
          </div>

          {/* Symbol Quick Switcher */}
          <div className="hidden md:flex items-center bg-slate-950/80 p-1 rounded-lg border border-slate-800">
            {symbols.map((item) => (
              <button
                key={item.name}
                onClick={() => onSelectSymbol(item.name)}
                className={`px-3 py-1 text-xs font-mono font-semibold rounded-md transition-all ${
                  activeSymbol === item.name
                    ? 'bg-emerald-500 text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                {item.name}
              </button>
            ))}
          </div>

          {/* Right Status Badges */}
          <div className="flex items-center gap-3">
            {/* UTC Clock & Session */}
            <div className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-slate-200">{currentTimeUtc} UTC</span>
              <span className={`px-1.5 py-0.5 text-[10px] font-medium border rounded ${sessionInfo.color}`}>
                {activeSession}
              </span>
            </div>

            {/* Mode & Broker Status */}
            <div className="flex items-center gap-2">
              <button
                onClick={onToggleApiMode}
                title="Click to toggle simulation / local backend mode"
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono border transition ${
                  apiMode === 'real'
                    ? 'bg-amber-950/40 text-amber-300 border-amber-700/60'
                    : 'bg-blue-950/40 text-blue-300 border-blue-700/60'
                }`}
              >
                <Radio className={`w-3 h-3 ${apiMode === 'real' ? 'animate-pulse text-amber-400' : 'text-blue-400'}`} />
                <span>{apiMode === 'real' ? 'BACKEND (PORT 8000)' : 'SIMULATION MODE'}</span>
              </button>

              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono">
                <Server className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-slate-300">Vantage Demo</span>
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Safety Notice Banner */}
      <div className="bg-slate-950/90 border-t border-slate-800/80 px-4 py-1 text-[11px] text-slate-400 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span>
            <strong className="text-slate-200">Execution Guard Active:</strong> LIVE trading disabled by contract. Proposals require explicit owner approval prior to Demo preparation.
          </span>
        </div>
        <div className="hidden sm:flex items-center gap-3 text-slate-500 font-mono text-[10px]">
          <span>Account: {brokerStatus.account}</span>
          <span>Equity: ${brokerStatus.equity.toFixed(2)} USD</span>
          <span>Clean Collection: 2,666 PASS</span>
        </div>
      </div>
    </header>
  );
};
