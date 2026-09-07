import React, { useState, useEffect } from 'react';
import { ShieldCheck, Activity, Clock, Terminal, AlertCircle } from 'lucide-react';

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const Header: React.FC<HeaderProps> = ({ activeTab, setActiveTab }) => {
  const [utcTime, setUtcTime] = useState<string>('');
  const [currentSession, setCurrentSession] = useState<string>('LONDON_ACTIVE');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const hours = now.getUTCHours();
      const minutes = now.getUTCMinutes();
      const seconds = now.getUTCSeconds();
      const timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} UTC`;
      setUtcTime(timeStr);

      // Determine session
      if (hours >= 0 && hours < 7) {
        setCurrentSession('ASIAN_SESSION');
      } else if (hours >= 7 && hours < 12) {
        setCurrentSession('LONDON_SESSION (Active)');
      } else if (hours >= 12 && hours < 16) {
        setCurrentSession('OVERLAP (London / NY)');
      } else if (hours >= 16 && hours < 21) {
        setCurrentSession('NEW_YORK_SESSION');
      } else {
        setCurrentSession('SYDNEY_SESSION');
      }
    };

    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const navItems = [
    { id: 'decisions', label: 'Session Tickets', badge: '2 READY' },
    { id: 'analysis', label: 'Top-Down SMC', badge: null },
    { id: 'funnel', label: 'Large-SMC Watch', badge: 'Active' },
    { id: 'risk', label: 'Risk & Sizing', badge: null },
    { id: 'journal', label: 'Ledger & Replay', badge: '+5.5R' },
    { id: 'strategies', label: 'Registry', badge: null },
  ];

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & App Name */}
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-mono font-bold text-lg">
              AG
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold tracking-tight text-white text-base">AG Profit Trading</span>
                <span className="px-2 py-0.5 text-xs font-mono font-medium rounded bg-slate-800 text-slate-300 border border-slate-700">
                  v1.0.3
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">Deterministic Strategy Engine</p>
            </div>
          </div>

          {/* Session Clock & Operational Safety Status */}
          <div className="hidden md:flex items-center space-x-4 text-xs font-mono">
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-md bg-slate-950 border border-slate-800">
              <Clock className="w-3.5 h-3.5 text-sky-400" />
              <span className="text-slate-300 font-semibold">{utcTime || '07:15:00 UTC'}</span>
              <span className="text-slate-600">|</span>
              <span className="text-emerald-400">{currentSession}</span>
            </div>

            <div className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md bg-emerald-950/40 border border-emerald-800/40 text-emerald-300">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>LIVE GATED: SAFE</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex space-x-1 border-t border-slate-800/60 py-2 overflow-x-auto">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => setActiveTab(item.id)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors flex items-center space-x-1.5 ${
                  isActive
                    ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <span>{item.label}</span>
                {item.badge && (
                  <span
                    className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${
                      item.badge.includes('READY')
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-sky-500/20 text-sky-300'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
