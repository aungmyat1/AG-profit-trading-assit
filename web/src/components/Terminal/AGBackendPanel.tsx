/**
 * Read-only presentation of the real AG local backend (AG_LOCAL_BACKEND_
 * IMPLEMENTATION_STATUS / frontend read-integration phase). Every value shown here
 * comes verbatim from src/api/app.py's response models via agApiClient -- nothing on
 * this page is generated, guessed, or locally computed. In particular:
 *
 *   - demo_authorized / live_authorized / lifecycle_stage are displayed exactly as
 *     the backend returns them; this component never infers or overrides them.
 *   - Proposals are whatever /api/proposals returns (possibly empty -- the backend's
 *     proposal registry has no persistent ingestion path yet, which is a known,
 *     pre-existing backend limitation, not a bug in this panel).
 *   - No POST route is called anywhere in this file -- authorize/execute stays out of
 *     scope for this phase (see AuthorizeDemo already gated elsewhere behind
 *     AG_UI_MODE and never invoked from here).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  WifiOff,
} from 'lucide-react';
import {
  agApiClient,
  AgApiError,
  type BrokerAccountResponse,
  type ProposalResponse,
  type StrategyResponse,
  type SystemStatusResponse,
  type ValidationResponse,
} from '../../utils/agApiClient';

type LoadState = 'LOADING' | 'READY' | 'ERROR' | 'DISCONNECTED';

function describeError(err: unknown): string {
  if (err instanceof AgApiError) return `${err.kind}: ${err.message}`;
  return String(err);
}

function isDisconnected(err: unknown): boolean {
  return err instanceof AgApiError && (err.kind === 'NETWORK' || err.kind === 'TIMEOUT');
}

function Pill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${
        ok
          ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
          : 'bg-slate-800 text-slate-400 border-slate-700'
      }`}
    >
      {label}
    </span>
  );
}

function SectionShell({
  title,
  icon,
  state,
  error,
  onRetry,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  state: LoadState;
  error: string | null;
  onRetry: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-slate-700 rounded-lg bg-slate-900">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800">
        <div className="flex items-center gap-2 text-slate-200 font-semibold text-xs">
          {icon}
          <span>{title}</span>
        </div>
        <button
          onClick={onRetry}
          disabled={state === 'LOADING'}
          className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${state === 'LOADING' ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="p-4 text-xs font-mono">
        {state === 'LOADING' && <div className="text-slate-400">Loading...</div>}
        {state === 'DISCONNECTED' && (
          <div className="text-amber-400 flex items-start gap-2">
            <WifiOff className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <div>BACKEND UNREACHABLE</div>
              <div className="text-slate-500 mt-1">
                Could not reach the local AG backend. This does not mean it is broken --
                confirm scripts/run_api.py is running and VITE_API_BASE_URL is correct.
              </div>
              {error && <div className="text-slate-600 mt-1">{error}</div>}
            </div>
          </div>
        )}
        {state === 'ERROR' && (
          <div className="text-rose-400 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>{error}</div>
          </div>
        )}
        {state === 'READY' && children}
      </div>
    </div>
  );
}

function SystemStatusSection() {
  const [state, setState] = useState<LoadState>('LOADING');
  const [data, setData] = useState<SystemStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('LOADING');
    setError(null);
    try {
      const resp = await agApiClient.getSystemStatus();
      setData(resp);
      setState('READY');
    } catch (err) {
      setData(null);
      setError(describeError(err));
      setState(isDisconnected(err) ? 'DISCONNECTED' : 'ERROR');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <SectionShell title="System Status" icon={<Activity className="w-4 h-4 text-cyan-400" />} state={state} error={error} onRetry={load}>
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Service</div>
            <div className="text-slate-200">{data.service}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Status</div>
            <div className="text-emerald-400 font-bold">{data.status}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Release</div>
            <div className="text-slate-200">{data.application_release}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Execution Mode</div>
            <div className="text-amber-300 font-bold">{data.execution_mode}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Broker</div>
            <Pill ok={data.broker.connected} label={data.broker.connected ? `CONNECTED (${data.broker.environment ?? '?'})` : 'DISCONNECTED'} />
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">MT5</div>
            <Pill ok={data.mt5.connected} label={data.mt5.connected ? 'CONNECTED' : 'DISCONNECTED'} />
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Telegram</div>
            <Pill ok={data.telegram.configured} label={data.telegram.configured ? 'CONFIGURED' : 'NOT CONFIGURED'} />
          </div>
        </div>
      )}
    </SectionShell>
  );
}

function BrokerAccountSection() {
  const [state, setState] = useState<LoadState>('LOADING');
  const [data, setData] = useState<BrokerAccountResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('LOADING');
    setError(null);
    try {
      const resp = await agApiClient.getBrokerAccount();
      setData(resp);
      setState('READY');
    } catch (err) {
      setData(null);
      setError(describeError(err));
      setState(isDisconnected(err) ? 'DISCONNECTED' : 'ERROR');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <SectionShell title="Broker Account" icon={<Server className="w-4 h-4 text-cyan-400" />} state={state} error={error} onRetry={load}>
      {data && !data.connected && (
        <div className="text-slate-400">
          Not connected. {data.reason_code && <span className="text-slate-500">({data.reason_code})</span>}
        </div>
      )}
      {data && data.connected && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Environment</div>
            <div className="text-slate-200">{data.environment ?? 'N/A'}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Server</div>
            <div className="text-slate-200">{data.server ?? 'N/A'}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Account</div>
            <div className="text-slate-200">{data.account_redacted ?? 'N/A'}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Trade Allowed (info)</div>
            <div className="text-slate-200">{String(data.trade_allowed_informational ?? 'N/A')}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Balance</div>
            <div className="text-emerald-400 font-bold">{data.balance != null ? data.balance.toFixed(2) : 'N/A'}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[10px] uppercase">Equity</div>
            <div className="text-emerald-400 font-bold">{data.equity != null ? data.equity.toFixed(2) : 'N/A'}</div>
          </div>
        </div>
      )}
    </SectionShell>
  );
}

function StrategyRow({ strategy }: { strategy: StrategyResponse }) {
  const [expanded, setExpanded] = useState(false);
  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [validationState, setValidationState] = useState<LoadState | 'NONE'>('NONE');
  const [validationError, setValidationError] = useState<string | null>(null);

  const toggle = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && validationState === 'NONE') {
      setValidationState('LOADING');
      try {
        const resp = await agApiClient.getValidation(strategy.strategy_id);
        setValidation(resp);
        setValidationState('READY');
      } catch (err) {
        setValidationError(
          err instanceof AgApiError && err.status === 404
            ? 'No validation_framework adapter is wired for this strategy yet.'
            : describeError(err),
        );
        setValidationState(isDisconnected(err) ? 'DISCONNECTED' : 'ERROR');
      }
    }
  };

  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      <button onClick={toggle} className="w-full flex items-center justify-between px-3 py-2 bg-slate-950/60 hover:bg-slate-900 text-left">
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDown className="w-3.5 h-3.5 text-slate-500" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500" />}
          <span className="text-slate-100 font-semibold">{strategy.strategy_id}</span>
          {strategy.lifecycle_stage && <span className="text-slate-500 text-[10px]">{strategy.lifecycle_stage}</span>}
        </div>
        <div className="flex items-center gap-1.5">
          <Pill ok={strategy.registered} label="REG" />
          <Pill ok={strategy.active} label="ACTIVE" />
          <Pill ok={strategy.demo_authorized} label="DEMO_AUTH" />
          <Pill ok={strategy.live_authorized} label="LIVE_AUTH" />
        </div>
      </button>
      {expanded && (
        <div className="px-3 py-2.5 border-t border-slate-800 bg-slate-950/30 space-y-2">
          {validationState === 'LOADING' && <div className="text-slate-400">Loading governance evidence...</div>}
          {(validationState === 'ERROR' || validationState === 'DISCONNECTED') && (
            <div className="text-slate-500 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>{validationError}</span>
            </div>
          )}
          {validationState === 'READY' && validation && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <div>
                  <div className="text-slate-500 text-[10px] uppercase">Semantic Version</div>
                  <div className="text-slate-200">{validation.semantic_version}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px] uppercase">Execution Capability</div>
                  <div className="text-slate-200">{validation.execution_capability}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px] uppercase">Execution Authority</div>
                  <div className="text-slate-200">{validation.execution_authority}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px] uppercase">Next Transition</div>
                  <div className="text-slate-200">{validation.next_transition ?? 'N/A (terminal)'}</div>
                </div>
                <div>
                  <div className="text-slate-500 text-[10px] uppercase">Promotion Eligible</div>
                  <Pill ok={validation.promotion_eligible} label={validation.promotion_eligible ? 'YES' : 'NO'} />
                </div>
              </div>
              {validation.promotion_blockers.length > 0 && (
                <div>
                  <div className="text-slate-500 text-[10px] uppercase mb-1">Promotion Blockers</div>
                  <div className="flex flex-wrap gap-1">
                    {validation.promotion_blockers.map(b => (
                      <span key={b} className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30 text-[10px]">
                        {b}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {validation.gates.length > 0 && (
                <div>
                  <div className="text-slate-500 text-[10px] uppercase mb-1">Gates</div>
                  <div className="space-y-1">
                    {validation.gates.map(g => (
                      <div key={g.gate_name} className="flex items-center justify-between text-[11px]">
                        <span className="text-slate-300">{g.gate_name}</span>
                        <span
                          className={`font-bold ${
                            g.status === 'PASS' ? 'text-emerald-400' : g.status === 'FAIL' ? 'text-rose-400' : 'text-slate-400'
                          }`}
                        >
                          {g.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StrategiesSection() {
  const [state, setState] = useState<LoadState>('LOADING');
  const [data, setData] = useState<StrategyResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('LOADING');
    setError(null);
    try {
      const resp = await agApiClient.listStrategies();
      setData(resp);
      setState('READY');
    } catch (err) {
      setData([]);
      setError(describeError(err));
      setState(isDisconnected(err) ? 'DISCONNECTED' : 'ERROR');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <SectionShell title="Strategies & Governance" icon={<ShieldCheck className="w-4 h-4 text-cyan-400" />} state={state} error={error} onRetry={load}>
      {data.length === 0 && <div className="text-slate-500">No strategies registered.</div>}
      <div className="space-y-2">
        {data.map(s => (
          <StrategyRow key={s.strategy_id} strategy={s} />
        ))}
      </div>
    </SectionShell>
  );
}

function ProposalsSection() {
  const [state, setState] = useState<LoadState>('LOADING');
  const [data, setData] = useState<ProposalResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('LOADING');
    setError(null);
    try {
      const resp = await agApiClient.listProposals();
      setData(resp);
      setState('READY');
    } catch (err) {
      setData([]);
      setError(describeError(err));
      setState(isDisconnected(err) ? 'DISCONNECTED' : 'ERROR');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <SectionShell title="Canonical Proposals" icon={<BadgeCheck className="w-4 h-4 text-cyan-400" />} state={state} error={error} onRetry={load}>
      {data.length === 0 ? (
        <div className="text-slate-500">
          No proposals currently registered on the backend. This backend's proposal registry has no
          persistent ingestion path yet -- an empty list here is expected, not an error.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-slate-500 text-left border-b border-slate-800">
                <th className="py-1 pr-3">Setup</th>
                <th className="py-1 pr-3">Strategy</th>
                <th className="py-1 pr-3">Symbol</th>
                <th className="py-1 pr-3">Direction</th>
                <th className="py-1 pr-3">Entry</th>
                <th className="py-1 pr-3">Stop</th>
                <th className="py-1 pr-3">TP1</th>
                <th className="py-1 pr-3">TP2</th>
                <th className="py-1 pr-3">Volume</th>
                <th className="py-1 pr-3">Risk</th>
              </tr>
            </thead>
            <tbody>
              {data.map(p => (
                <tr key={p.proposal_hash} className="border-b border-slate-900 text-slate-300">
                  <td className="py-1 pr-3">{p.setup_id}</td>
                  <td className="py-1 pr-3">{p.strategy_id}</td>
                  <td className="py-1 pr-3">{p.symbol}</td>
                  <td className="py-1 pr-3">{p.direction}</td>
                  <td className="py-1 pr-3">{p.entry}</td>
                  <td className="py-1 pr-3">{p.stop_loss}</td>
                  <td className="py-1 pr-3">{p.tp1 ?? 'N/A'}</td>
                  <td className="py-1 pr-3">{p.tp2 ?? 'N/A'}</td>
                  <td className="py-1 pr-3">{p.volume}</td>
                  <td className="py-1 pr-3">
                    {p.risk_amount}
                    {p.risk_percent != null ? ` (${p.risk_percent}%)` : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionShell>
  );
}

export function AGBackendPanel() {
  return (
    <div className="space-y-4">
      <SystemStatusSection />
      <BrokerAccountSection />
      <StrategiesSection />
      <ProposalsSection />
    </div>
  );
}
