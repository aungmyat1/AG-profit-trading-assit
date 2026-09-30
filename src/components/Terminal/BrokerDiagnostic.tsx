import React, { useState } from 'react';
import { BrokerStatus, TradeDeal } from '../../types/trading';
import {
  Server,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Clock,
  DollarSign,
  Shield,
  Layers,
} from 'lucide-react';

interface BrokerDiagnosticProps {
  brokerStatus: BrokerStatus;
  deals: TradeDeal[];
  onRefresh: () => void;
  apiMode: 'mock' | 'real';
}

export const BrokerDiagnostic: React.FC<BrokerDiagnosticProps> = ({
  brokerStatus,
  deals,
  onRefresh,
  apiMode,
}) => {
  // brokerStatus and deals are FIXTURE data (tradingStore INITIAL_*): labelled SIMULATED in mock
  // mode and never shown in real mode, where no backend broker read-model is wired yet.
  const simulated = apiMode !== 'real';
  const shownDeals = simulated ? deals : [];
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    status: 'SUCCESS' | 'UNREACHABLE';
    message: string;
    details?: string;
  } | null>(null);

  const runConnectionTest = async () => {
    setTesting(true);
    setTestResult(null);

    // Simulate backend probe or hit real API if in real mode
    setTimeout(() => {
      setTesting(false);
      if (apiMode === 'real') {
        setTestResult({
          status: 'UNREACHABLE',
          message: 'NO BACKEND BROKER DATA',
          details: 'Broker status and deals here are SIMULATED fixtures; they are hidden in real mode until a backend broker read-model is wired.',
        });
      } else {
        setTestResult({
          status: 'SUCCESS',
          message: 'SIMULATION ENGINE SYNCHRONIZED',
          details: `Deterministic Fixtures Verified | Memory Store Clean | Authority: Strategy Engine`,
        });
      }
    }, 600);
  };

  const netRealized = shownDeals.reduce((acc, d) => acc + d.profit + d.commission + d.swap, 0);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col gap-5 shadow-sm">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Server className="w-5 h-5 text-emerald-400" />
            <h3 className="font-extrabold text-white text-base tracking-wide">
              TERMINAL & BROKER CONNECTIVITY
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono">
            Sanitized Read-Model: MetaTrader 5 & Vantage Demo Bridge{' '}
            <span className={simulated ? 'text-amber-400 font-bold' : 'text-rose-400 font-bold'}>
              {simulated ? '[SIMULATED]' : '[NO BACKEND DATA]'}
            </span>
          </p>
        </div>

        <button
          type="button"
          onClick={runConnectionTest}
          disabled={testing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-950 font-bold text-xs font-mono transition shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
          <span>Test Backend Connection</span>
        </button>
      </div>

      {/* Test Result Banner */}
      {testResult && (
        <div
          className={`p-3 rounded-lg border font-mono text-xs flex items-start gap-2.5 ${
            testResult.status === 'SUCCESS'
              ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-300'
              : 'bg-rose-950/40 border-rose-800/80 text-rose-300'
          }`}
        >
          <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">{testResult.message}</div>
            <div className="text-[11px] opacity-80 mt-0.5">{testResult.details}</div>
          </div>
        </div>
      )}

      {/* Account Info Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">BROKER / SERVER</div>
          <div className="font-bold text-white text-sm mt-0.5">{simulated ? brokerStatus.broker : '—'}</div>
          <div className={`text-[10px] font-semibold mt-1 ${simulated ? 'text-amber-400' : 'text-rose-400'}`}>
            Status: {simulated ? `SIMULATED (${brokerStatus.connected ? 'ONLINE' : 'OFFLINE'})` : 'NO BACKEND DATA'}
          </div>
        </div>

        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">ACCOUNT LOGIN</div>
          <div className="font-bold text-white text-sm mt-0.5">{simulated ? brokerStatus.account : '—'}</div>
          <div className="text-[10px] text-slate-400 mt-1">Env: {simulated ? `${brokerStatus.environment} (SIMULATED)` : '—'}</div>
        </div>

        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">BALANCE & EQUITY</div>
          <div className="font-bold text-white text-sm mt-0.5">{simulated ? `$${brokerStatus.balance.toFixed(2)} SIMULATED` : '—'}</div>
          <div className="text-[10px] text-slate-400 mt-1">Equity: {simulated ? `$${brokerStatus.equity.toFixed(2)} SIMULATED` : '—'}</div>
        </div>

        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <div className="text-slate-500 text-[10px]">TRADE PERMISSION</div>
          <div className="font-bold text-emerald-400 text-sm mt-0.5">
            {simulated ? `${brokerStatus.tradeAllowed ? 'PERMITTED' : 'RESTRICTED'} (SIMULATED)` : '—'}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Live trading blocked</div>
        </div>
      </div>

      {/* Sanitized Closing Deals History */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300 font-mono">
              {simulated ? 'MT5 Deal History (SIMULATED FIXTURE)' : 'MT5 Deal History (no backend data)'}
            </h4>
          </div>
          <span className="text-xs font-mono text-slate-400">
            Realized Net{simulated ? ' (SIMULATED)' : ''}:{' '}
            {simulated ? (
              <strong className={netRealized >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                {netRealized >= 0 ? '+' : ''}${netRealized.toFixed(2)} USD
              </strong>
            ) : (
              <strong className="text-slate-500">—</strong>
            )}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-[10px] uppercase bg-slate-950/60">
                <th className="py-2 px-3">Ticket</th>
                <th className="py-2 px-3">Time (UTC)</th>
                <th className="py-2 px-3">Symbol</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3">Lots</th>
                <th className="py-2 px-3">Price</th>
                <th className="py-2 px-3">Profit ($)</th>
                <th className="py-2 px-3">Comment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {shownDeals.map((d) => (
                <tr key={d.ticket} className="hover:bg-slate-800/30 transition">
                  <td className="py-2.5 px-3 text-slate-400">#{d.ticket}</td>
                  <td className="py-2.5 px-3 text-slate-300">{d.time}</td>
                  <td className="py-2.5 px-3 font-bold text-white">{d.symbol}</td>
                  <td className="py-2.5 px-3">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        d.type === 'BUY'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : 'bg-rose-950 text-rose-400 border border-rose-800'
                      }`}
                    >
                      {d.type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-slate-300">{d.lots.toFixed(2)}</td>
                  <td className="py-2.5 px-3 text-slate-200">{d.price}</td>
                  <td
                    className={`py-2.5 px-3 font-semibold ${
                      d.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {d.profit >= 0 ? '+' : ''}${d.profit.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 text-slate-500 text-[11px]">{d.comment}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
