/**
 * Real AG backend API client (AG_AI_STUDIO_PREVIEW_VSCODE_RUNTIME_INTEGRATION_V1).
 *
 * Deliberately separate from utils/api.ts, which is the existing MOCK data layer
 * (fabricated positions/proposals for UI development) -- this module is the ONLY
 * place this frontend talks to the real Python FastAPI backend (src/api/app.py).
 * Every route here must correspond to a real route in that file; do not add a call
 * here for an endpoint that doesn't exist server-side.
 *
 * Base URL: VITE_API_BASE_URL, defaulting to http://127.0.0.1:8000 (scripts/run_api.py's
 * own default port -- see docs/setup/AI_STUDIO_VSCODE_DEVELOPMENT.md). No secret ever
 * flows through this module: the backend's own sanitized response shapes are the only
 * thing it returns.
 */

export const AG_API_BASE_URL: string =
  (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const AG_UI_MODE: 'mock' | 'real' =
  String((import.meta as any).env?.VITE_AG_API_MODE || 'mock').toLowerCase() === 'real'
    ? 'real'
    : 'mock';

const DEFAULT_TIMEOUT_MS = 5000;

export class AgApiError extends Error {
  readonly kind: 'NETWORK' | 'HTTP' | 'PARSE' | 'TIMEOUT';
  readonly status?: number;

  constructor(message: string, kind: AgApiError['kind'], status?: number) {
    super(message);
    this.name = 'AgApiError';
    this.kind = kind;
    this.status = status;
  }
}

async function agFetch<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${AG_API_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } catch (err) {
    if ((err as any)?.name === 'AbortError') {
      throw new AgApiError(`Request to ${path} timed out after ${timeoutMs}ms`, 'TIMEOUT');
    }
    // A browser fetch() network failure (backend unreachable, CORS blocked, DNS, etc.)
    // never distinguishes those reasons from JS alone -- report generically as NETWORK.
    throw new AgApiError(`Network error reaching ${AG_API_BASE_URL}${path}: ${String(err)}`, 'NETWORK');
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    let detail = '';
    try {
      detail = JSON.stringify(await response.json());
    } catch {
      /* body wasn't JSON -- fine, report the status alone */
    }
    throw new AgApiError(`HTTP ${response.status} from ${path}${detail ? `: ${detail}` : ''}`, 'HTTP', response.status);
  }

  try {
    return (await response.json()) as T;
  } catch (err) {
    throw new AgApiError(`Could not parse JSON response from ${path}: ${String(err)}`, 'PARSE');
  }
}

export interface HealthResponse {
  status: string;
}

export interface BrokerStatusResponse {
  connected: boolean;
  broker?: string | null;
  environment?: string | null;
  server?: string | null;
  account_redacted?: string | null;
  trade_allowed_informational?: boolean | null;
  reason_code?: string | null;
}

export interface TicketResponse {
  approval_id: string;
  setup_id: string;
  strategy_id?: string | null;
  symbol?: string | null;
  direction?: string | null;
  environment: string;
  state: string;
  created_at: string;
  expires_at: string;
}

export interface AuthorizeDemoResponse {
  approval_id: string;
  success: boolean;
  state: string;
  reason_code?: string | null;
  result_reference?: string | null;
}

export interface SystemStatusResponse {
  service: string;
  status: string;
  application_release: string;
  execution_mode: string;
  broker: BrokerStatusResponse;
  mt5: { connected: boolean };
  telegram: { configured: boolean };
}

export interface BrokerAccountResponse {
  connected: boolean;
  broker?: string | null;
  environment?: string | null;
  server?: string | null;
  account_redacted?: string | null;
  balance?: number | null;
  equity?: number | null;
  trade_allowed_informational?: boolean | null;
  reason_code?: string | null;
}

export interface BrokerDealResponse {
  ticket: number;
  position_id: number;
  time: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  volume: number;
  price: number;
  profit: number;
  commission: number;
  swap: number;
  fee: number;
  comment: string;
}

export interface BrokerHistoryResponse {
  account_redacted: string;
  server: string;
  environment: string;
  lookback_days: number;
  total_closing_deals: number;
  returned_deals: number;
  realized_net: number;
  deals: BrokerDealResponse[];
}

export interface StrategyResponse {
  strategy_id: string;
  registered: boolean;
  active: boolean;
  research: boolean;
  demo_authorized: boolean;
  live_authorized: boolean;
  lifecycle_stage?: string | null;
  semantic_version?: string | null;
}

export interface GateResultResponse {
  gate_name: string;
  status: string;
  evidence_refs: string[];
}

export interface ValidationResponse {
  strategy_id: string;
  semantic_version: string;
  lifecycle_stage: string;
  execution_capability: string;
  execution_authority: string;
  next_transition?: string | null;
  promotion_eligible: boolean;
  promotion_blockers: string[];
  gates: GateResultResponse[];
}

export interface MarketDataCandleResponse {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Roadmap R2 (AG_REAL_MARKET_WATCH_READY_V1): real, closed-bar-only MT5 candles.
 * `source` is always 'MT5' here -- this is how a caller distinguishes real broker
 * data from the frontend's SYNTHETIC scanner proposals (TradeProposal.marketDataSource).
 * Observation-only: this response carries no strategy, proposal, or execution
 * authority. */
export interface MarketDataCandlesResponse {
  source: 'MT5';
  broker?: string | null;
  environment?: string | null;
  symbol: string;
  timeframe: string;
  bar_count: number;
  last_closed_candle_at: string;
  freshness: string;
  candles: MarketDataCandleResponse[];
}

export interface ProposalResponse {
  proposal_hash: string;
  setup_id: string;
  strategy_id: string;
  symbol: string;
  direction: string;
  entry: number;
  stop_loss: number;
  tp1?: number | null;
  tp2?: number | null;
  volume: number;
  risk_amount: number;
  risk_percent?: number | null;
}

/** WP9/WP10 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): read-only view of the
 * ledger-backed canonical proposal. execution_authority is always 'NONE' and
 * execution_eligible is always false -- OBSERVATION ONLY, never an execution surface.
 * Distinct from ProposalResponse (/api/proposals), which is the execution-approval
 * registry backing authorize-demo, not this plan's canonical R2-R4 proposal. */
export interface CanonicalProposalResponse {
  proposal_id: string;
  strategy_id: string;
  strategy_version: string;
  symbol: string;
  market: string;
  direction?: string | null;
  entry?: number | null;
  stop?: number | null;
  targets: number[];
  watcher_state: string;
  proposal_state: string;
  execution_authority: string;
  execution_eligible: boolean;
  market_data_mode?: string | null;
  market_data_source?: string | null;
  market_data_asof?: string | null;
  market_data_fingerprint?: string | null;
  ready_at?: string | null;
  expires_at?: string | null;
  version: number;
  correction_of?: string | null;
  reasons: string[];
  // V1.2 (AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2): additive governance
  // fields, mirrored field-for-field from schemas.py:236-242. These -- not
  // proposal_state/watcher_state alone -- are what an owner-decision caller must
  // check before treating a proposal as eligible for CONFIRM.
  economic_edge_established: boolean;
  demo_eligible: boolean;
  demo_authorized: boolean;
  live_authorized: boolean;
  proposal_only: boolean;
  broker_mutation_blocked: boolean;
  lifecycle_stage?: string | null;
}

/** Mirrors schemas.py:97-119 (OpportunityAnalysisResponse) -- deterministic,
 * observe-only narrative/evidence projection for the Owner Analysis panel. Display
 * only: eligibility for CONFIRM/REJECT is decided solely by the CanonicalProposalResponse
 * governance fields above, never by anything in this response. */
export interface OpportunityAnalysisResponse {
  schema_version: string;
  strategy_id: string;
  symbol: string;
  decision_state: string;
  portfolio_state: string;
  proposal_state: string;
  evaluated_at: string;
  market_data_as_of?: string | null;
  proposal_expires_at?: string | null;
  is_stale: boolean;
  direction?: string | null;
  entry?: number | null;
  stop?: number | null;
  targets: number[];
  capacity_available?: boolean | null;
  capacity_reason?: string | null;
  reason_codes: string[];
  missing_condition?: string | null;
  next_required_evidence?: string | null;
  execution_authority: string;
}

/** Mirrors schemas.py:274-284 (OwnerDecisionRequest). `proposal_id` is never part of
 * this body -- it is taken only from the URL path server-side (see submitOwnerDecision
 * below), so a client can never submit a decision against a different proposal
 * identity than the one it POSTed to. */
export interface OwnerDecisionRequest {
  decision_id: string;
  action: 'APPROVE_DEMO' | 'REJECT';
  symbol: string;
  environment: 'DEMO';
  actor?: string;
}

/** Mirrors schemas.py:286-299 (PreparedTradeCommandResponse) -- a PREPARED,
 * UNCONFIRMED execution template. Never itself an executed broker order. */
export interface PreparedTradeCommandResponse {
  command_id: string;
  action: string;
  symbol: string;
  side?: string | null;
  order_type: string;
  volume?: number | null;
  entry?: number | null;
  sl?: number | null;
  tp?: number | null;
  proposal_id?: string | null;
}

/** Mirrors schemas.py:302-316 (OwnerDecisionResponse). `execution_decision_prepared`
 * means only that `trade_command` carries a prepared, unconfirmed template -- never
 * that a broker order was submitted. */
export interface OwnerDecisionResponse {
  decision_id: string;
  proposal_envelope_id: string;
  status: 'AUTHORIZED' | 'REJECTED' | string;
  reason_code: string;
  reasons: string[];
  execution_decision_prepared: boolean;
  trade_command?: PreparedTradeCommandResponse | null;
}

export const agApiClient = {
  getHealth: () => agFetch<HealthResponse>('/api/health'),
  getSystemStatus: () => agFetch<SystemStatusResponse>('/api/system/status'),
  getBrokerStatus: () => agFetch<BrokerStatusResponse>('/api/broker/status'),
  getBrokerAccount: () => agFetch<BrokerAccountResponse>('/api/broker/account'),
  getBrokerHistory: (days = 90, limit = 100) =>
    agFetch<BrokerHistoryResponse>(`/api/broker/history?days=${days}&limit=${limit}`),
  listStrategies: () => agFetch<StrategyResponse[]>('/api/strategies'),
  getStrategy: (id: string) => agFetch<StrategyResponse>(`/api/strategies/${encodeURIComponent(id)}`),
  getValidation: (id: string) => agFetch<ValidationResponse>(`/api/validation/${encodeURIComponent(id)}`),
  listProposals: () => agFetch<ProposalResponse[]>('/api/proposals'),
  getProposal: (hash: string) => agFetch<ProposalResponse>(`/api/proposals/${encodeURIComponent(hash)}`),
  listCanonicalProposals: () => agFetch<CanonicalProposalResponse[]>('/api/canonical-proposals'),
  getCanonicalProposal: (proposalId: string) =>
    agFetch<CanonicalProposalResponse>(`/api/canonical-proposals/${encodeURIComponent(proposalId)}`),
  listTickets: () => agFetch<TicketResponse[]>('/api/tickets'),
  getTicket: (id: string) => agFetch<TicketResponse>(`/api/tickets/${encodeURIComponent(id)}`),
  authorizeDemo: (id: string) =>
    agFetch<AuthorizeDemoResponse>(`/api/tickets/${encodeURIComponent(id)}/authorize-demo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'EXECUTE_DEMO' }),
    }),
  getExecutionStatus: (executionId: string) => agFetch<TicketResponse>(`/api/executions/${encodeURIComponent(executionId)}`),
  getMarketDataCandles: (symbol: string, timeframe = 'M15', count = 100) =>
    agFetch<MarketDataCandlesResponse>(
      `/api/market-data/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&count=${count}`,
    ),
  getOpportunityAnalysis: (symbol: string) =>
    agFetch<OpportunityAnalysisResponse[]>(`/api/opportunity-analysis?symbol=${encodeURIComponent(symbol)}`),
  // PANEL-R4/R5A: the sole exception to this module's "no secret ever flows through
  // this module" docstring above -- `ownerKey` is a caller-supplied per-call parameter
  // (never stored, never logged, never persisted by this module) sent as the
  // X-AG-Owner-Key header required by src/api/app.py's require_owner_auth.
  submitOwnerDecision: (proposalId: string, body: OwnerDecisionRequest, ownerKey: string) =>
    agFetch<OwnerDecisionResponse>(
      `/api/canonical-proposals/${encodeURIComponent(proposalId)}/owner-decision`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-AG-Owner-Key': ownerKey },
        body: JSON.stringify(body),
      },
    ),
};
