import React, { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Image as ImageIcon, ShieldCheck, XCircle } from 'lucide-react';
import { Candle, TradeProposal } from '../../types/trading';

type PanelState = 'IDLE' | 'PREPARED' | 'REJECTED' | 'STALE';

interface Props {
  proposal: TradeProposal | null;
  candles: Candle[];
  onRefresh?: () => void;
}

const strategyId = 'ST_ASIAN_SWEEP_5R_V1';

export const OwnerAnalysisPanel: React.FC<Props> = ({ proposal, candles, onRefresh }) => {
  const [state, setState] = useState<PanelState>('IDLE');
  const [preparedOrder, setPreparedOrder] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState('');
  const latestCandle = candles[candles.length - 1];
  const bid = latestCandle?.close ?? 0;
  const ask = bid ? bid + 0.00012 : 0;
  const spread = bid ? (ask - bid) * 10000 : 0;
  const isWatch = !proposal || proposal.state === 'WATCH';
  const isStale = Boolean(proposal && Date.now() - proposal.timestamp > 15 * 60 * 1000);
  const chartSrc = proposal ? `/api/owner-analysis/${encodeURIComponent(proposal.id)}/chart.png` : '';

  const scenarios = useMemo(() => [
    ['PRIMARY SCENARIO', proposal?.entrySide === 'SELL' ? 'Sweep high rejects; price returns through the Asian range.' : 'Sweep low rejects; price returns through the Asian range.'],
    ['ALTERNATIVE SCENARIO', 'Range expansion pauses at the opposite session boundary before continuation.'],
    ['INVALIDATION SCENARIO', 'An M15 close beyond the sweep extreme invalidates the setup.']
  ], [proposal]);

  const callBackend = async (path: string, body: Record<string, unknown>) => {
    setMessage('');
    try {
      const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Backend rejected request (${response.status})`);
      return payload;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Backend request failed');
      return null;
    }
  };

  const reject = async () => {
    if (!proposal) return;
    const result = await callBackend('/api/owner-analysis/reject', { proposal_id: proposal.id, strategy_id: strategyId });
    if (result) setState('REJECTED');
  };

  const prepare = async () => {
    if (!proposal || isWatch || isStale) return;
    const result = await callBackend('/api/owner-analysis/prepare-demo', { proposal_id: proposal.id, strategy_id: strategyId });
    if (result) { setPreparedOrder(result); setState('PREPARED'); }
  };

  const cancel = async () => {
    if (!preparedOrder) return;
    const approvalId = String(preparedOrder.approval_id || '');
    const result = await callBackend('/api/owner-analysis/cancel-demo', { approval_id: approvalId });
    if (result) { setPreparedOrder(null); setState('IDLE'); }
  };

  const confirm = async () => {
    if (!preparedOrder) return;
    const approvalId = String(preparedOrder.approval_id || '');
    await callBackend('/api/owner-analysis/confirm-demo', { approval_id: approvalId });
  };

  if (isWatch) return <section data-testid="owner-analysis" className="rounded-2xl border border-amber-500/30 bg-slate-900 p-6"><div className="flex items-center gap-3 text-amber-300"><AlertTriangle className="h-5 w-5" /><h2 className="text-lg font-bold">OWNER ANALYSIS · WATCH</h2></div><p className="mt-3 text-sm text-slate-400">No actionable ticket is available for {strategyId}. The owner panel stays read-only until the backend publishes a confirmed ticket.</p></section>;

  return <section data-testid="owner-analysis" className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-cyan-500/30 bg-slate-900 p-5">
      <div><p className="text-xs font-mono tracking-widest text-cyan-300">OWNER DECISION EXPERIENCE</p><h1 className="mt-1 text-2xl font-bold">{proposal.symbol} · {proposal.entrySide}</h1><p className="text-sm text-slate-400">{strategyId} · {proposal.strategyName} · London Open</p></div>
      <div className={`rounded-full border px-3 py-1 text-xs font-bold ${isStale ? 'border-rose-500/40 text-rose-300' : 'border-emerald-500/40 text-emerald-300'}`}>{isStale ? 'STALE TICKET' : proposal.state}</div>
    </div>
    {isStale && <div role="alert" className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-sm text-rose-200">This ticket is stale and cannot be prepared. Refresh to obtain a fresh backend-issued state.</div>}
    <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
      <div className="space-y-5">
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900"><div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3 text-sm font-bold"><ImageIcon className="h-4 w-4 text-cyan-300" />CHART PNG · M15</div>{chartSrc ? <img src={chartSrc} alt="M15 strategy setup chart PNG" className="min-h-[260px] w-full object-cover" onError={e => { e.currentTarget.alt = 'Chart PNG unavailable from backend'; }} /> : <div className="p-10 text-center text-sm text-slate-500">Chart unavailable</div>}</div>
        <Evidence title="CANONICAL STRATEGY EVIDENCE" tone="cyan"><ul className="grid gap-2 text-sm text-slate-300 sm:grid-cols-2"><li>State: <b>{proposal.state}</b></li><li>Direction: <b>{proposal.entrySide}</b></li><li>Entry: <b>{proposal.entryPrice ?? '—'}</b></li><li>SL: <b>{proposal.stopLoss ?? '—'}</b></li><li>TP1: <b>{proposal.takeProfit1 ?? '—'}</b></li><li>TP2: <b>{proposal.takeProfit2 ?? '—'}</b></li></ul><ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-400">{proposal.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></Evidence>
        <Evidence title="SUPPLEMENTARY OWNER CONTEXT" tone="slate"><div className="grid gap-2 text-sm text-slate-300 sm:grid-cols-3"><span>H1 context: observational</span><span>M15 EMA50: {proposal.regime.ema50Trend}</span><span>ATR(14): backend chart</span></div></Evidence>
      </div>
      <div className="space-y-5">
        <Evidence title="MARKET + DEMO RISK VIEW" tone="slate"><div className="grid grid-cols-2 gap-3 text-sm"><Metric label="Bid / Ask" value={`${bid.toFixed(5)} / ${ask.toFixed(5)}`} /><Metric label="Spread" value={`${spread.toFixed(1)} pips`} /><Metric label="Risk" value="1.00% · backend" /><Metric label="Risk amount" value="Account-authoritative" /><Metric label="Volume" value={`${proposal.suggestedLots} lots`} /><Metric label="Account" value="DEMO · gated" /></div><p className="mt-4 text-xs text-amber-300">Demo authority remains backend-controlled. WP-1 remediation is pending independent re-audit.</p></Evidence>
        <Evidence title="DECISION SUPPORT — NOT STRATEGY SIGNAL" tone="violet">{scenarios.map(([title, text]) => <div key={title} className="mb-3 last:mb-0"><p className="text-xs font-bold text-violet-300">{title}</p><p className="mt-1 text-sm text-slate-300">{text}</p></div>)}</Evidence>
        {message && <div role="alert" className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-sm text-rose-200">{message}</div>}
        {state === 'PREPARED' ? <div className="rounded-2xl border border-emerald-500/40 bg-emerald-950/20 p-4"><p className="font-bold text-emerald-300">FINAL ORDER PREVIEW · BACKEND PREPARED</p><pre className="mt-3 overflow-auto text-xs text-slate-300">{JSON.stringify(preparedOrder, null, 2)}</pre><div className="mt-4 flex gap-2"><button onClick={cancel} className="rounded-lg border border-slate-600 px-4 py-2 text-sm">CANCEL</button><button onClick={confirm} className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-bold text-slate-950">CONFIRM DEMO ORDER</button></div></div> : <div className="flex gap-2"><button onClick={reject} className="flex items-center gap-2 rounded-lg border border-rose-500/50 px-4 py-2 text-sm text-rose-200"><XCircle className="h-4 w-4" />REJECT</button><button onClick={prepare} disabled={isStale} className="flex items-center gap-2 rounded-lg bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"><ShieldCheck className="h-4 w-4" />PREPARE DEMO ORDER</button></div>}
        {state === 'REJECTED' && <p className="flex items-center gap-2 text-sm text-emerald-300"><CheckCircle2 className="h-4 w-4" />Rejection recorded by backend.</p>}
      </div>
    </div>
    <button onClick={onRefresh} className="text-xs text-slate-500 underline">Refresh owner read model</button>
  </section>;
};

const Evidence: React.FC<{ title: string; tone: 'cyan' | 'slate' | 'violet'; children: React.ReactNode }> = ({ title, tone, children }) => <div className={`rounded-2xl border p-4 ${tone === 'cyan' ? 'border-cyan-500/30 bg-cyan-950/10' : tone === 'violet' ? 'border-violet-500/30 bg-violet-950/10' : 'border-slate-800 bg-slate-900'}`}><h2 className="mb-3 text-xs font-bold tracking-widest text-slate-300">{title}</h2>{children}</div>;
const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => <div><p className="text-xs text-slate-500">{label}</p><p className="font-mono text-sm text-slate-200">{value}</p></div>;
