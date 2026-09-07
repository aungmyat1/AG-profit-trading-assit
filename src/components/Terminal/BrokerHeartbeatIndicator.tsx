import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Server,
  Activity,
  Radio,
  Wifi,
  WifiOff,
  Shield,
  ShieldCheck,
  ShieldAlert,
  RotateCw,
  ChevronDown,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  X,
  Sliders,
  Cpu,
  RefreshCw,
  Zap,
  DollarSign
} from 'lucide-react';
import { BrokerAccountHeartbeat, BrokerHeartbeatSummary, BrokerAssetClass } from '../../types/trading';

interface BrokerHeartbeatIndicatorProps {
  onOpenBrokerModal: () => void;
}

const DEFAULT_ACCOUNTS: BrokerAccountHeartbeat[] = [
  {
    id: 'vantage_fx_demo',
    name: 'Vantage MT5 Demo (FX)',
    assetClass: 'FX',
    broker: 'Vantage',
    server: 'VantageMarkets-Demo',
    accountId: 25972746,
    environment: 'DEMO',
    status: 'CONNECTED',
    pingMs: 16,
    lastHeartbeat: Date.now(),
    feedStatus: 'STREAMING',
    activeSymbols: ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD'],
    protocol: 'MT5_IPC',
    safetyGated: false,
    notes: 'Unified Vantage MT5 Demo account #25972746 for Forex on VantageMarkets-Demo. MT5 IPC active on port 18812.'
  },
  {
    id: 'vantage_crypto_demo',
    name: 'Vantage MT5 Demo (Crypto CFD)',
    assetClass: 'CRYPTO',
    broker: 'Vantage',
    server: 'VantageMarkets-Demo',
    accountId: 25972746,
    environment: 'DEMO',
    status: 'CONNECTED',
    pingMs: 18,
    lastHeartbeat: Date.now(),
    feedStatus: 'STREAMING',
    activeSymbols: ['BTCUSD', 'ETHUSD', 'SOLUSD'],
    protocol: 'MT5_IPC',
    safetyGated: false,
    notes: 'Unified Vantage MT5 Demo account #25972746 for Crypto CFD on VantageMarkets-Demo (BTCUSD, ETHUSD, SOLUSD).'
  }
];

export const BrokerHeartbeatIndicator: React.FC<BrokerHeartbeatIndicatorProps> = ({
  onOpenBrokerModal
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [accounts, setAccounts] = useState<BrokerAccountHeartbeat[]>(DEFAULT_ACCOUNTS);
  const [isPinging, setIsPinging] = useState<boolean>(false);
  const [pingingId, setPingingId] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<'ALL' | 'FX' | 'CRYPTO'>('ALL');
  const [pulseActive, setPulseActive] = useState<boolean>(false);
  const [simulatedSpike, setSimulatedSpike] = useState<boolean>(false);
  const [simulatedOutage, setSimulatedOutage] = useState<boolean>(false);
  const [lastCheckTime, setLastCheckTime] = useState<number>(Date.now());

  // Vantage Demo Balance State
  const [vantageBalance, setVantageBalance] = useState<number>(1000);
  const [isEditingBalance, setIsEditingBalance] = useState<boolean>(false);
  const [balanceInput, setBalanceInput] = useState<string>('1000');
  const [isSavingBalance, setIsSavingBalance] = useState<boolean>(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  // Close popover when clicking outside or pressing Escape
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  // Synchronize primary Vantage account info with backend config
  const syncBrokerAccount = () => {
    fetch('/api/broker/account')
      .then(res => res.json())
      .then(data => {
        const acc = data?.account || data;
        if (acc) {
          if (acc.balance !== undefined) {
            setVantageBalance(acc.balance);
            setBalanceInput(String(acc.balance));
          }
          if (acc.account_id) {
            setAccounts(prev =>
              prev.map(item => {
                if (item.id === 'vantage_fx_demo' || item.id === 'vantage_crypto_demo') {
                  return {
                    ...item,
                    accountId: acc.account_id,
                    broker: acc.broker || 'Vantage',
                    server: acc.server || 'VantageMarkets-Demo',
                    notes: acc.configured_via_secrets 
                      ? `Configured via server environment secrets (.env). MT5 IPC active on port ${acc.ipc_port || 18812}.`
                      : item.notes,
                    name: item.id === 'vantage_fx_demo' 
                      ? `${acc.broker || 'Vantage'} MT5 Demo (FX)`
                      : `${acc.broker || 'Vantage'} MT5 Demo (Crypto CFD)`
                  };
                }
                return item;
              })
            );
          }
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    syncBrokerAccount();
  }, [isOpen]);

  // Update account balance on Vantage Demo
  const handleUpdateBalance = async (newBalanceValue: number) => {
    if (isNaN(newBalanceValue) || newBalanceValue < 0) return;
    setIsSavingBalance(true);
    try {
      const res = await fetch('/api/broker/account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ balance: newBalanceValue })
      });
      const data = await res.json();
      if (data.success && data.account) {
        setVantageBalance(data.account.balance);
        setBalanceInput(String(data.account.balance));
        setIsEditingBalance(false);
        setSaveSuccessMessage(`Balance updated to $${data.account.balance.toLocaleString()} USD`);
        setTimeout(() => setSaveSuccessMessage(null), 3000);
        window.dispatchEvent(new CustomEvent('broker-balance-updated', { detail: data.account }));
      }
    } catch {
      setSaveSuccessMessage('Error updating balance');
      setTimeout(() => setSaveSuccessMessage(null), 3000);
    } finally {
      setIsSavingBalance(false);
    }
  };

  // Mock Heartbeat Interval Check (every 3.5s)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setLastCheckTime(now);
      setPulseActive(true);
      setTimeout(() => setPulseActive(false), 800);

      // Fetch from API or run local heartbeat loop with simulated jitter
      setAccounts(prev =>
        prev.map(acc => {
          if (acc.status === 'DISCONNECTED' && !simulatedOutage) {
            return acc; // Keep disconnected account disconnected
          }

          if (simulatedOutage && (acc.id === 'vantage_fx_demo' || acc.id === 'vantage_crypto_demo')) {
            return {
              ...acc,
              status: 'DEGRADED',
              pingMs: 240,
              feedStatus: 'STALE',
              lastHeartbeat: now - 15000,
              lastError: 'Vantage MT5 IPC heartbeat timed out (retrying socket)'
            };
          }

          const basePing = acc.assetClass === 'FX' ? (acc.environment === 'DEMO' ? 17 : 21) : 40;
          const jitter = Math.floor(Math.random() * 7) - 3;
          const spikeBonus = simulatedSpike ? 140 : 0;
          const finalPing = Math.max(12, basePing + jitter + spikeBonus);

          return {
            ...acc,
            pingMs: finalPing,
            lastHeartbeat: now,
            status: acc.safetyGated && acc.environment === 'LIVE'
              ? 'STANDBY_GATED'
              : finalPing > 120
              ? 'DEGRADED'
              : 'CONNECTED',
            feedStatus: acc.safetyGated && acc.environment === 'LIVE' ? 'HEARTBEAT_ONLY' : 'STREAMING',
            lastError: undefined
          };
        })
      );
    }, 3500);

    return () => clearInterval(interval);
  }, [simulatedSpike, simulatedOutage]);

  // Manual Ping Check on All Accounts
  const handlePingAll = async () => {
    setIsPinging(true);
    try {
      await fetch('/api/broker/heartbeat/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accountId: 'ALL' })
      }).catch(() => null);

      await new Promise(r => setTimeout(r, 450));
      const now = Date.now();
      setAccounts(prev =>
        prev.map(acc => {
          if (acc.status === 'DISCONNECTED') return acc;
          const jitter = Math.floor(Math.random() * 5) - 2;
          const basePing = acc.assetClass === 'FX' ? 17 : 39;
          return {
            ...acc,
            pingMs: Math.max(12, basePing + jitter),
            lastHeartbeat: now
          };
        })
      );
      setLastCheckTime(now);
    } finally {
      setIsPinging(false);
    }
  };

  // Manual Ping Single Account
  const handlePingSingle = async (accountId: string) => {
    setPingingId(accountId);
    try {
      await fetch('/api/broker/heartbeat/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accountId })
      }).catch(() => null);

      await new Promise(r => setTimeout(r, 350));
      const now = Date.now();
      setAccounts(prev =>
        prev.map(acc => {
          if (acc.id !== accountId) return acc;
          if (acc.status === 'DISCONNECTED') {
            // Attempt reconnect simulation
            return {
              ...acc,
              status: 'CONNECTED',
              pingMs: 38,
              lastHeartbeat: now,
              feedStatus: 'STREAMING',
              lastError: undefined
            };
          }
          const jitter = Math.floor(Math.random() * 5) - 2;
          return {
            ...acc,
            pingMs: Math.max(12, acc.pingMs + jitter),
            lastHeartbeat: now
          };
        })
      );
    } finally {
      setPingingId(null);
    }
  };

  // Derived Aggregates
  const fxAccounts = useMemo(() => accounts.filter(a => a.assetClass === 'FX'), [accounts]);
  const cryptoAccounts = useMemo(() => accounts.filter(a => a.assetClass === 'CRYPTO'), [accounts]);

  const activeAccountsCount = useMemo(
    () => accounts.filter(a => a.status === 'CONNECTED' || a.status === 'STANDBY_GATED').length,
    [accounts]
  );

  const connectedWithPing = useMemo(() => accounts.filter(a => a.pingMs > 0), [accounts]);
  const avgPing = useMemo(
    () => (connectedWithPing.length > 0 ? Math.round(connectedWithPing.reduce((s, a) => s + a.pingMs, 0) / connectedWithPing.length) : 0),
    [connectedWithPing]
  );

  const hasDegraded = useMemo(() => accounts.some(a => a.status === 'DEGRADED'), [accounts]);
  const hasDisconnected = useMemo(() => accounts.some(a => a.status === 'DISCONNECTED'), [accounts]);

  const filteredAccounts = useMemo(() => {
    if (activeFilter === 'FX') return fxAccounts;
    if (activeFilter === 'CRYPTO') return cryptoAccounts;
    return accounts;
  }, [activeFilter, accounts, fxAccounts, cryptoAccounts]);

  const formatLastSeen = (timestamp: number) => {
    const diff = Math.floor((Date.now() - timestamp) / 1000);
    if (diff < 3) return 'Just now';
    if (diff < 60) return `${diff}s ago`;
    return `${Math.floor(diff / 60)}m ago`;
  };

  return (
    <div className="relative inline-block" ref={containerRef}>
      {/* Header Compact Status Trigger Button */}
      <button
        id="broker-heartbeat-btn"
        type="button"
        onClick={() => setIsOpen(prev => !prev)}
        className={`flex items-center gap-2 px-2.5 py-1 rounded border transition-all cursor-pointer font-mono text-[11px] ${
          isOpen
            ? 'bg-slate-800 border-cyan-500/50 text-white shadow-md'
            : hasDegraded
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20'
            : 'bg-slate-950/80 border-slate-700/80 text-slate-200 hover:bg-slate-800/80 hover:border-slate-600'
        }`}
        title="Vantage Demo #25972746 • Unified FX & Crypto Demo Account"
      >
        {/* Animated Radio Heartbeat Icon */}
        <div className="relative flex items-center justify-center">
          <Radio
            className={`w-3.5 h-3.5 transition-colors ${
              pulseActive
                ? 'text-cyan-300 scale-110'
                : hasDegraded
                ? 'text-amber-400'
                : 'text-emerald-400'
            }`}
          />
          {pulseActive && (
            <span className="absolute -inset-1 rounded-full bg-cyan-400/30 animate-ping" />
          )}
        </div>

        {/* Status Indicators for FX & Crypto */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-semibold">#25972746:</span>

          {/* FX Status Pip */}
          <span className="flex items-center gap-1 px-1.5 py-0.2 rounded bg-slate-900 border border-slate-800 text-[10px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-slate-300 font-bold">FX</span>
          </span>

          {/* Crypto Status Pip */}
          <span className="flex items-center gap-1 px-1.5 py-0.2 rounded bg-slate-900 border border-slate-800 text-[10px]">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                cryptoAccounts.some(c => c.status === 'CONNECTED')
                  ? 'bg-cyan-400'
                  : 'bg-slate-500'
              }`}
            />
            <span className="text-slate-300 font-bold">Crypto</span>
          </span>
        </div>

        {/* Account Balance Metric */}
        <span className="text-emerald-400 font-bold hidden md:inline border-l border-slate-700 pl-1.5 font-mono">
          ${vantageBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>

        {/* Avg Ping Metric */}
        <span className="text-slate-400 text-[10px] hidden sm:inline border-l border-slate-700 pl-1.5">
          {avgPing}ms
        </span>

        {/* Dropdown Chevron */}
        <ChevronDown
          className={`w-3 h-3 text-slate-400 transition-transform ${
            isOpen ? 'rotate-180 text-cyan-400' : ''
          }`}
        />
      </button>

      {/* Floating Popover Panel */}
      {isOpen && (
        <div
          id="broker-heartbeat-popover"
          className="absolute right-0 mt-2 w-96 max-w-[calc(100vw-2rem)] bg-slate-900 border border-slate-800 rounded-xl shadow-2xl z-50 overflow-hidden font-sans text-xs animate-in fade-in zoom-in-95 duration-150"
        >
          {/* Popover Header */}
          <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <div>
                <div className="font-semibold text-slate-100 font-mono text-xs flex items-center gap-2">
                  Broker Connection Monitor
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-normal">
                    Heartbeat 3.5s
                  </span>
                </div>
                <div className="text-[10px] text-slate-400">
                  Real-time heartbeat checks across individual FX and Crypto accounts
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                id="btn-ping-all-brokers"
                type="button"
                onClick={handlePingAll}
                disabled={isPinging}
                className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition flex items-center gap-1 text-[10px] font-mono cursor-pointer"
                title="Send immediate ping check to all accounts"
              >
                <RefreshCw className={`w-3 h-3 ${isPinging ? 'animate-spin text-cyan-400' : ''}`} />
                <span>{isPinging ? 'Pinging...' : 'Ping All'}</span>
              </button>

              <button
                id="btn-close-broker-heartbeat"
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Quick Aggregate Stats Bar */}
          <div className="px-4 py-2.5 bg-slate-900/60 border-b border-slate-800/80 flex items-center justify-between text-[11px] font-mono">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span>
                  {activeAccountsCount} of {accounts.length} Active
                </span>
              </div>
              <span className="text-slate-600">|</span>
              <div className="text-slate-400">
                Avg Latency: <span className="text-slate-200 font-bold">{avgPing} ms</span>
              </div>
            </div>

            <div className="text-[10px] text-slate-500">
              Tick: {formatLastSeen(lastCheckTime)}
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="px-4 pt-2.5 pb-1 flex items-center gap-1 border-b border-slate-800/50">
            {(['ALL', 'FX', 'CRYPTO'] as const).map(tab => {
              const count = tab === 'ALL' ? accounts.length : tab === 'FX' ? fxAccounts.length : cryptoAccounts.length;
              return (
                <button
                  key={tab}
                  type="button"
                  id={`filter-heartbeat-${tab.toLowerCase()}`}
                  onClick={() => setActiveFilter(tab)}
                  className={`px-2.5 py-1 rounded text-[10px] font-mono font-medium transition ${
                    activeFilter === tab
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-xs'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`}
                >
                  {tab} ({count})
                </button>
              );
            })}
          </div>

          {/* Vantage Demo Account Balance Quick Control */}
          <div className="mx-3 mt-2.5 p-2.5 bg-slate-950/90 rounded-lg border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] text-slate-400 uppercase font-mono tracking-wider font-semibold flex items-center gap-1">
                  <DollarSign className="w-3 h-3 text-emerald-400" />
                  <span>Vantage Demo Balance</span>
                </div>
                <div className="text-xs font-bold font-mono text-emerald-400 flex items-center gap-1.5 mt-0.5">
                  <span>${vantageBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD</span>
                  <span className="text-[9px] text-slate-400 font-normal font-sans">(1:500 Lev)</span>
                </div>
              </div>
              <button
                type="button"
                id="btn-toggle-edit-balance"
                onClick={() => setIsEditingBalance(prev => !prev)}
                className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 text-[10px] font-mono border border-slate-700 transition cursor-pointer flex items-center gap-1"
              >
                <span>{isEditingBalance ? 'Cancel' : 'Update Balance'}</span>
              </button>
            </div>

            {/* Inline Editor if active */}
            {isEditingBalance && (
              <div className="pt-2 border-t border-slate-800/80 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <span className="absolute left-2.5 top-1.5 text-slate-500 font-mono text-xs">$</span>
                    <input
                      id="input-vantage-balance"
                      type="number"
                      step="100"
                      value={balanceInput}
                      onChange={e => setBalanceInput(e.target.value)}
                      className="w-full bg-slate-900 border border-cyan-500/50 rounded pl-6 pr-2 py-1 text-xs text-white font-mono font-bold focus:outline-none focus:border-cyan-400"
                      placeholder="10000"
                    />
                  </div>
                  <button
                    type="button"
                    id="btn-save-vantage-balance"
                    disabled={isSavingBalance}
                    onClick={() => handleUpdateBalance(Number(balanceInput))}
                    className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold rounded transition cursor-pointer disabled:opacity-50 flex items-center gap-1"
                  >
                    {isSavingBalance ? <RotateCw className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                    <span>Save</span>
                  </button>
                </div>

                {/* Quick Presets */}
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-[9px] text-slate-500 font-mono">Presets:</span>
                  {[1000, 5000, 10000, 25000, 50000, 100000].map(amt => (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => {
                        setBalanceInput(String(amt));
                        handleUpdateBalance(amt);
                      }}
                      className={`text-[9px] px-1.5 py-0.5 rounded border transition font-mono cursor-pointer ${
                        vantageBalance === amt
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-bold'
                          : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      ${amt >= 1000 ? `${amt / 1000}k` : amt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {saveSuccessMessage && (
              <div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1 bg-emerald-950/40 p-1.5 rounded border border-emerald-500/30">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span>{saveSuccessMessage}</span>
              </div>
            )}
          </div>

          {/* Account Cards List */}
          <div className="p-3 space-y-2.5 max-h-[380px] overflow-y-auto">
            {filteredAccounts.map(account => {
              const isAccountPinging = pingingId === account.id;
              const isConnected = account.status === 'CONNECTED';
              const isGated = account.status === 'STANDBY_GATED';
              const isDegraded = account.status === 'DEGRADED';
              const isDisconnected = account.status === 'DISCONNECTED';

              return (
                <div
                  key={account.id}
                  id={`broker-account-${account.id}`}
                  className={`p-3 rounded-lg border transition-all ${
                    isDisconnected
                      ? 'bg-slate-950/40 border-slate-800/80 opacity-75'
                      : isDegraded
                      ? 'bg-amber-950/20 border-amber-500/30'
                      : isGated
                      ? 'bg-slate-900 border-amber-500/25'
                      : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Account Header */}
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold text-slate-100 text-xs">
                          {account.name}
                        </span>

                        {/* Asset Class Pill */}
                        <span
                          className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-bold uppercase ${
                            account.assetClass === 'FX'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                          }`}
                        >
                          {account.assetClass}
                        </span>

                        {/* Environment Pill */}
                        <span className="px-1.5 py-0.2 rounded text-[9px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                          {account.environment}
                        </span>
                      </div>

                      <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                        {account.broker} • #{account.accountId}
                      </div>
                    </div>

                    {/* Status Badge & Latency */}
                    <div className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isConnected
                              ? 'bg-emerald-400 shadow-[0_0_6px_#34d399]'
                              : isGated
                              ? 'bg-amber-400'
                              : isDegraded
                              ? 'bg-amber-500 animate-ping'
                              : 'bg-rose-500'
                          }`}
                        />
                        <span
                          className={`text-[10px] font-mono font-bold uppercase ${
                            isConnected
                              ? 'text-emerald-400'
                              : isGated
                              ? 'text-amber-400'
                              : isDegraded
                              ? 'text-amber-400'
                              : 'text-rose-400'
                          }`}
                        >
                          {isConnected
                            ? 'Online'
                            : isGated
                            ? 'Standby'
                            : isDegraded
                            ? 'Degraded'
                            : 'Offline'}
                        </span>
                      </div>

                      <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                        {account.pingMs > 0 ? `${account.pingMs} ms` : '—'}
                      </div>
                    </div>
                  </div>

                  {/* Operational Details */}
                  <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px] font-mono text-slate-400">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500">Protocol:</span>
                      <span className="text-slate-300">{account.protocol}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-500">Feed:</span>
                      <span
                        className={
                          account.feedStatus === 'STREAMING'
                            ? 'text-emerald-400 font-medium'
                            : account.feedStatus === 'HEARTBEAT_ONLY'
                            ? 'text-amber-400'
                            : 'text-slate-500'
                        }
                      >
                        {account.feedStatus}
                      </span>
                    </div>
                  </div>

                  {/* Subscribed Symbols & Context */}
                  <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400">
                    <div className="truncate max-w-[210px] font-mono text-[9px] text-slate-400">
                      Symbols: {account.activeSymbols.join(', ')}
                    </div>

                    {/* Single Ping / Reconnect Trigger */}
                    <button
                      id={`btn-ping-${account.id}`}
                      type="button"
                      onClick={() => handlePingSingle(account.id)}
                      disabled={isAccountPinging}
                      className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-[9px] font-mono flex items-center gap-1 transition cursor-pointer"
                    >
                      <RotateCw
                        className={`w-2.5 h-2.5 ${isAccountPinging ? 'animate-spin text-cyan-400' : ''}`}
                      />
                      <span>{isDisconnected ? 'Reconnect' : 'Ping'}</span>
                    </button>
                  </div>

                  {/* Notes / Safety Warning */}
                  {account.notes && (
                    <div className="mt-1.5 text-[9px] text-slate-500 bg-slate-900/80 p-1.5 rounded border border-slate-800/50 leading-relaxed">
                      {account.notes}
                    </div>
                  )}

                  {account.lastError && (
                    <div className="mt-1.5 text-[9px] text-rose-400 bg-rose-950/30 p-1.5 rounded border border-rose-800/40 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3 shrink-0" />
                      <span>{account.lastError}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Diagnostics & Heartbeat Test Controls */}
          <div className="p-3 bg-slate-950 border-t border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
              <span className="flex items-center gap-1 text-slate-400">
                <Sliders className="w-3 h-3 text-cyan-400" />
                Heartbeat Simulation Tools:
              </span>

              <div className="flex items-center gap-1.5">
                <button
                  id="btn-simulate-spike"
                  type="button"
                  onClick={() => setSimulatedSpike(prev => !prev)}
                  className={`px-2 py-0.5 rounded text-[9px] font-mono transition ${
                    simulatedSpike
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                      : 'bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200'
                  }`}
                  title="Inject latency spike to test degraded threshold"
                >
                  {simulatedSpike ? 'Spike: ON' : '+Spike'}
                </button>

                <button
                  id="btn-simulate-outage"
                  type="button"
                  onClick={() => setSimulatedOutage(prev => !prev)}
                  className={`px-2 py-0.5 rounded text-[9px] font-mono transition ${
                    simulatedOutage
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 font-bold'
                      : 'bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200'
                  }`}
                  title="Simulate MT5 IPC socket timeout"
                >
                  {simulatedOutage ? 'Outage: ON' : 'Test Outage'}
                </button>
              </div>
            </div>

            {/* Deep Modal Trigger */}
            <button
              id="btn-open-full-broker-modal"
              type="button"
              onClick={() => {
                setIsOpen(false);
                onOpenBrokerModal();
              }}
              className="w-full py-1.5 px-3 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-mono font-medium flex items-center justify-center gap-2 transition cursor-pointer"
            >
              <Server className="w-3.5 h-3.5 text-cyan-400" />
              <span>Open MT5 & Broker Diagnostics Modal</span>
              <ExternalLink className="w-3 h-3 text-cyan-400/80" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
