import React, { useState, useEffect } from 'react';
import {
  Clock,
  Shield,
  Activity,
  Layers,
  BarChart3,
  Terminal,
  RotateCcw,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Server,
  LineChart as LineChartIcon
} from 'lucide-react';
import { BrokerConnectionModal } from './Terminal/BrokerConnectionModal';
import { BrokerHeartbeatIndicator } from './Terminal/BrokerHeartbeatIndicator';

interface NavbarProps {
  activeTab: 'terminal' | 'scanner' | 'strategies' | 'execution' | 'smc' | 'replay' | 'logs' | 'journal' | 'backend' | 'owner';
  setActiveTab: (tab: 'terminal' | 'scanner' | 'strategies' | 'execution' | 'smc' | 'replay' | 'logs' | 'journal' | 'backend' | 'owner') => void;
  selectedSymbol: string;
  setSelectedSymbol: (sym: string) => void;
  symbols: Array<{ symbol: string; typicalSpread: number; basePrice: number }>;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  selectedSymbol,
  setSelectedSymbol,
  symbols
}) => {
  const [utcTime, setUtcTime] = useState<string>('');
  const [currentSession, setCurrentSession] = useState<{ name: string; badge: string; color: string }>({
    name: 'Asian Session',
    badge: 'MONITORING',
    color: 'text-amber-400 border-amber-500/30 bg-amber-500/10'
  });
  const [isBrokerModalOpen, setIsBrokerModalOpen] = useState<boolean>(false);

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const hours = now.getUTCHours();
      const minutes = now.getUTCMinutes();
      const seconds = now.getUTCSeconds();
      
      const pad = (n: number) => n.toString().padStart(2, '0');
      setUtcTime(`${pad(hours)}:${pad(minutes)}:${pad(seconds)} UTC`);

      if (hours >= 0 && hours < 6) {
        setCurrentSession({
          name: 'Asian Range (00-06 GMT)',
          badge: 'CALCULATING BOX',
          color: 'text-indigo-400 border-indigo-500/30 bg-indigo-500/10'
        });
      } else if (hours >= 6 && hours < 11) {
        setCurrentSession({
          name: 'London Open (07-11 GMT)',
          badge: 'ACTIVE SWEEP WINDOW',
          color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
        });
      } else if (hours >= 11 && hours < 15) {
        setCurrentSession({
          name: 'New York Open (12-15 GMT)',
          badge: 'NY EXPANSION / CUTOFF',
          color: 'text-cyan-400 border-cyan-500/30 bg-cyan-500/10'
        });
      } else {
        setCurrentSession({
          name: 'Off-Hours (Maintenance)',
          badge: 'CLOSED',
          color: 'text-slate-400 border-slate-700 bg-slate-800/40'
        });
      }
    };

    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="border-b border-slate-800 bg-slate-900/95 backdrop-blur sticky top-0 z-50">
      {/* Top Meta Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2 border-b border-slate-800/60 text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_#22d3ee]" />
            <span className="font-bold tracking-wider text-slate-100 uppercase font-mono">
              AG Profit Trading
            </span>
          </div>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <span className="text-slate-400 hidden sm:inline font-mono">v1.1.1 Deterministic Assistant</span>
        </div>

        <div className="flex items-center gap-4">
          {/* Session Clock */}
          <div className="flex items-center gap-2 font-mono text-slate-300">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span>{utcTime || '08:15:30 UTC'}</span>
          </div>

          {/* Active Session Status */}
          <div className={`hidden md:flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[11px] font-mono ${currentSession.color}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            <span>{currentSession.name}</span>
            <span className="font-bold opacity-75">• {currentSession.badge}</span>
          </div>

          {/* Multi-Account Real-Time Broker Heartbeat Indicator (FX & Crypto) */}
          <BrokerHeartbeatIndicator
            onOpenBrokerModal={() => setIsBrokerModalOpen(true)}
          />

          {/* Safety Gate Status */}
          <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 font-mono text-[11px]">
            <Shield className="w-3 h-3 text-amber-400" />
            <span>DEMO ONLY (Live Gated)</span>
          </div>
        </div>
      </div>

      {/* Main Navigation Tabs & Symbol Selector */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2.5 gap-3">
        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 overflow-x-auto no-scrollbar">
          <button
            id="tab-owner-analysis"
            onClick={() => setActiveTab('owner')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${activeTab === 'owner' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'}`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Owner Analysis</span>
          </button>

          <button
            id="tab-terminal"
            onClick={() => setActiveTab('terminal')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'terminal'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Live Terminal</span>
          </button>

          <button
            id="tab-scanner"
            onClick={() => setActiveTab('scanner')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'scanner'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Signal Scanner</span>
          </button>

          <button
            id="tab-smc"
            onClick={() => setActiveTab('smc')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'smc'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>SMC & Confirmation (E1/E2/E3)</span>
          </button>

          <button
            id="tab-strategies"
            onClick={() => setActiveTab('strategies')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'strategies'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Strategy Contracts</span>
          </button>

          <button
            id="tab-execution"
            onClick={() => setActiveTab('execution')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'execution'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>Trade Management</span>
          </button>

          <button
            id="tab-journal"
            onClick={() => setActiveTab('journal')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'journal'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <LineChartIcon className="w-3.5 h-3.5" />
            <span>Trade Journal</span>
          </button>

          <button
            id="tab-replay"
            onClick={() => setActiveTab('replay')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'replay'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Replay & Backtest Lab</span>
          </button>

          <button
            id="tab-backend"
            onClick={() => setActiveTab('backend')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'backend'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Server className="w-3.5 h-3.5" />
            <span>AG Backend</span>
          </button>

          <button
            id="tab-logs"
            onClick={() => setActiveTab('logs')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'logs'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Audit Logs</span>
          </button>
        </nav>

        {/* Pair Quick Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 hidden sm:inline">Active Pair:</span>
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
            {symbols.map(s => (
              <button
                key={s.symbol}
                id={`pair-btn-${s.symbol}`}
                onClick={() => setSelectedSymbol(s.symbol)}
                className={`px-2.5 py-1 rounded text-xs font-mono font-semibold transition-all ${
                  selectedSymbol === s.symbol
                    ? 'bg-cyan-500 text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                {s.symbol}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Broker Connection & Diagnostics Modal */}
      <BrokerConnectionModal
        isOpen={isBrokerModalOpen}
        onClose={() => setIsBrokerModalOpen(false)}
      />
    </header>
  );
};
