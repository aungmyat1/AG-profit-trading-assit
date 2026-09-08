/**
 * Development-only "Test Backend Connection" panel
 * (AG_AI_STUDIO_PREVIEW_VSCODE_RUNTIME_INTEGRATION_V1 sections 7-9).
 *
 * Distinguishes "the UI is working" from "the local AG backend is reachable" -- these
 * are NOT the same claim, especially from an AI Studio preview, which may not have
 * network access to the developer's own machine. This component never fabricates a
 * successful connection; a failed fetch is reported as unreachable, with an explicit
 * note that this does not mean the backend is broken.
 */
import { useState } from 'react';
import { agApiClient, AgApiError, AG_API_BASE_URL, type BrokerStatusResponse } from '../../utils/agApiClient';

type ConnectionState = 'IDLE' | 'CHECKING' | 'REACHABLE' | 'UNREACHABLE';

export function BackendConnectionDiagnostic() {
  const [state, setState] = useState<ConnectionState>('IDLE');
  const [broker, setBroker] = useState<BrokerStatusResponse | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastAttempt, setLastAttempt] = useState<string | null>(null);
  const [lastHttpStatus, setLastHttpStatus] = useState<number | null>(null);

  async function testBackendConnection() {
    setState('CHECKING');
    setLastAttempt(new Date().toISOString());
    setLastError(null);
    setLastHttpStatus(null);

    try {
      await agApiClient.getHealth();
      const status = await agApiClient.getBrokerStatus();
      setBroker(status);
      setLastHttpStatus(200);
      setState('REACHABLE');
    } catch (err) {
      setBroker(null);
      if (err instanceof AgApiError) {
        setLastError(`${err.kind}: ${err.message}`);
        if (typeof err.status === 'number') setLastHttpStatus(err.status);
      } else {
        setLastError(String(err));
      }
      setState('UNREACHABLE');
    }
  }

  return (
    <div className="border border-slate-700 rounded-lg p-4 bg-slate-900 text-xs font-mono space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-slate-300 font-semibold">Backend Connection Diagnostic</span>
        <button
          onClick={testBackendConnection}
          disabled={state === 'CHECKING'}
          className="px-3 py-1 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-white"
        >
          {state === 'CHECKING' ? 'Testing...' : 'Test Backend Connection'}
        </button>
      </div>

      <div className="text-slate-400">
        <div>Frontend mode: {(import.meta as any).env?.VITE_AG_API_MODE === 'real' ? 'REAL' : 'MOCK'}</div>
        <div>API base URL: {AG_API_BASE_URL}</div>
        <div>Backend reachable: {state === 'REACHABLE' ? 'YES' : state === 'UNREACHABLE' ? 'NO' : 'NOT TESTED YET'}</div>
        <div>Last connection attempt: {lastAttempt ?? 'never'}</div>
        <div>Last HTTP status: {lastHttpStatus ?? 'N/A'}</div>
      </div>

      {state === 'REACHABLE' && broker && (
        <div className="text-emerald-400 border-t border-slate-800 pt-2">
          <div>BACKEND CONNECTED</div>
          <div>Broker: {broker.connected ? 'BROKER CONNECTED' : 'BROKER DISCONNECTED'}{!('connected' in broker) ? ' (BROKER STATUS UNKNOWN)' : ''}</div>
          <div>Environment: {broker.environment ?? 'N/A'}</div>
          <div>Server: {broker.server ?? 'N/A'}</div>
          <div>Account: {broker.account_redacted ?? 'N/A'}</div>
          <div>Trade allowed (informational only): {String(broker.trade_allowed_informational ?? 'N/A')}</div>
        </div>
      )}

      {state === 'UNREACHABLE' && (
        <div className="text-amber-400 border-t border-slate-800 pt-2">
          <div>BACKEND UNREACHABLE</div>
          <div className="text-slate-500 mt-1">
            Local AG backend is not reachable from this preview environment.
            <br />
            This does not mean the backend is broken. Run the same frontend from the
            local VS Code/Vite environment to verify localhost connectivity.
          </div>
          {lastError && <div className="text-slate-600 mt-1">{lastError}</div>}
        </div>
      )}
    </div>
  );
}
