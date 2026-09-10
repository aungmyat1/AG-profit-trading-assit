export type StrategyStatus = 'ACTIVE_INCUBATION' | 'REGISTERED' | 'RESEARCH_DRAFT' | 'RETIRED';

export type DecisionState = 'READY' | 'WATCH' | 'NO_TRADE' | 'DATA_ERROR';

export type SessionType = 'Asian' | 'London' | 'New_York' | 'London_Open' | 'New_York_Open';

export type Timeframe = 'M1' | 'M5' | 'M15' | 'H1' | 'H4' | 'D1';

export type OrderType = 'MARKET' | 'LIMIT' | 'STOP';

export type OrderSide = 'BUY' | 'SELL';

export interface Candle {
  time: number; // Unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  session?: SessionType;
}

export interface SessionBox {
  id: string;
  name: string;
  sessionType: SessionType;
  startTime: number;
  endTime: number;
  high: number;
  low: number;
  midline: number;
  rangePips: number;
  isCompleted: boolean;
  isValidRange: boolean;
}

export interface SwingPoint {
  id: string;
  type: 'HIGH' | 'LOW';
  time: number;
  price: number;
  confirmed: boolean;
  isMajor: boolean;
}

export interface StructureBreak {
  id: string;
  type: 'BOS' | 'CHOCH';
  direction: 'BULLISH' | 'BEARISH';
  time: number;
  brokenLevel: number;
  breakPrice: number;
}

export interface OrderBlock {
  id: string;
  type: 'BULLISH_OB' | 'BEARISH_OB';
  timeframe: Timeframe;
  startTime: number;
  topPrice: number;
  bottomPrice: number;
  isMitigated: boolean;
  mitigatedTime?: number;
  strength: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface FairValueGap {
  id: string;
  type: 'BULLISH_FVG' | 'BEARISH_FVG';
  timeframe: Timeframe;
  startTime: number;
  topPrice: number;
  bottomPrice: number;
  isFilled: boolean;
}

export interface LiquidityPool {
  id: string;
  type: 'BSL' | 'SSL' | 'EQH' | 'EQL';
  price: number;
  startTime: number;
  isSwept: boolean;
  sweptTime?: number;
  description: string;
}

export interface StrategyContract {
  id: string;
  name: string;
  family: string;
  version: string;
  status: StrategyStatus;
  instruments: string[];
  timeframe: Timeframe;
  magicNumber: number;
  sessionPairs: Array<{
    pairId: string;
    referenceSession: {
      name: string;
      startTimeGmt: string;
      endTimeGmt: string;
      metricsTracked: string[];
    };
    tradeSession: {
      name: string;
      startTimeGmt: string;
      endTimeGmt: string;
      maxEntries: number;
    };
  }>;
  entryRules: {
    longTrigger: string;
    shortTrigger: string;
    condition: string;
    orderType: OrderType;
  };
  riskRules: {
    riskMode: string;
    stopLossMode: string;
    stopLossRangePct: number;
    maxSpreadAllowedPips: number;
    maxRiskPerTradePct: number;
  };
  targets: {
    totalTargetR: number;
    legs: Array<{
      legId: number;
      volumePct: number;
      targetType: string;
      actionOnFill?: string;
      fixedR?: number;
    }>;
  };
  invalidation: {
    time: string;
    structural: string;
  };
  authority: {
    registered: boolean;
    active: boolean;
    research: boolean;
    demoAuthorized: boolean;
    liveAuthorized: boolean;
  };
  backtestMetrics?: {
    winRate: number;
    profitFactor: number;
    sampleSize: number;
    sharpeRatio: number;
    maxDrawdownPct: number;
    expectedValueR: number;
    avgTradeDuration: string;
  };
  confluenceCriteria?: Array<{
    id: string;
    title: string;
    description: string;
    mandatory: boolean;
  }>;
  promotionGates?: {
    stage: string;
    nextStage: string;
    criteriaNeeded: string[];
    currentProgressPct: number;
  };
}

export interface TradeProposal {
  id: string;
  symbol: string;
  strategyId: string;
  strategyName: string;
  timestamp: number;
  state: DecisionState;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  entrySide?: OrderSide;
  entryPrice?: number;
  stopLoss?: number;
  takeProfit1?: number; // 75% at opposite boundary / 3R
  takeProfit2?: number; // 25% at 5R runner
  riskReward: number;
  riskPips: number;
  suggestedLots: number;
  reasons: string[];
  invalidationLevel?: number;
  sessionBox?: SessionBox;
  regime: {
    ema50Trend: 'BULLISH' | 'BEARISH';
    rangePips: number;
    isRangeValid: boolean;
  };
  safetyGate: {
    spreadOk: boolean;
    dailyLossOk: boolean;
    sessionTimeOk: boolean;
  };
  /** AG_SCANNER_SAFE_PROPOSAL_EXECUTION_REMEDIATION_V2: provenance of the candles this
   * proposal was computed from. 'SYNTHETIC' means the local generateRealisticCandles()
   * fixture, not real MT5 data -- such a proposal must never be execution_eligible. */
  marketDataSource?: 'SYNTHETIC' | 'MT5';
  /** True only for a proposal whose geometry is safe to execute against: real broker
   * data AND canonical strategy governance (demo_authorized) both hold. Absent/false
   * means research/observation only -- the frontend must not offer an Execute action. */
  executionEligible?: boolean;
  /** Machine-readable reason executionEligible is false, e.g. SYNTHETIC_MARKET_DATA or
   * STRATEGY_NOT_DEMO_AUTHORIZED. Always present when executionEligible is false. */
  executionBlockReason?: string;
}

export interface Position {
  ticket: number;
  symbol: string;
  strategyId: string;
  side: OrderSide;
  volume: number;
  entryPrice: number;
  currentPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  openTime: number;
  closeTime?: number;
  pnl: number;
  pnlR: number;
  status: 'OPEN' | 'PARTIALLY_CLOSED' | 'CLOSED';
  claimed: boolean;
  isBreakevenMoved: boolean;
  tp1Filled: boolean;
  journalNotes: string[];
}

export interface AuditLog {
  id: string;
  timestamp: number;
  category: 'STRATEGY' | 'EXECUTION' | 'RISK_GUARD' | 'MANAGEMENT' | 'REPLAY';
  action: string;
  status: 'SUCCESS' | 'WARNING' | 'FAIL_CLOSED' | 'INFO';
  details: Record<string, any>;
}

export interface ReplayFixture {
  id: string;
  name: string;
  symbol: string;
  period: string;
  totalEvents: number;
  stage1Qualified: number;
  stage2WinRate: number;
  totalReturnR: number;
  description: string;
  candles: Candle[];
}

export type CorrelationStrength = 'STRONG_POSITIVE' | 'MODERATE_POSITIVE' | 'NEUTRAL' | 'MODERATE_NEGATIVE' | 'STRONG_NEGATIVE';

export interface CorrelationPair {
  symbolA: string;
  symbolB: string;
  coefficient: number;
  strength: CorrelationStrength;
  description: string;
  riskWarning?: string;
}

export interface CorrelationMatrixData {
  symbols: string[];
  matrix: Record<string, Record<string, number>>;
  pairs: CorrelationPair[];
  timeframe: string;
  lookbackDays: number;
  timestamp: number;
}

export interface BrokerCheckItem {
  id: string;
  name: string;
  status: 'PASS' | 'WARN' | 'FAIL';
  latency_ms: number;
  details: string;
}

export interface BrokerStatus {
  connected: boolean;
  broker: string;
  server: string;
  platform: string;
  account_id: number;
  account_name: string;
  currency: string;
  trade_mode: 'DEMO' | 'LIVE';
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  margin_level_pct: number;
  leverage: number;
  ping_ms: number;
  configured_via_secrets?: boolean;
  has_secret_password?: boolean;
  last_heartbeat: string;
  feed_status: 'HEALTHY' | 'DEGRADED' | 'DISCONNECTED';
  symbols_monitored: Array<{
    symbol: string;
    spread: number;
    basePrice: number;
    status: string;
  }>;
  safety_interlocks: {
    allow_live_trading: boolean;
    allow_order_send: boolean;
    user_confirmed_required: boolean;
    duplicate_protection: string;
    max_daily_loss_r: number;
    historical_replay_isolated: boolean;
  };
}

export interface BrokerValidationResult {
  success: boolean;
  overall_status: 'VALIDATED_HEALTHY' | 'DEGRADED' | 'FAILED';
  validated_at: string;
  roundtrip_ping_ms: number;
  account: {
    id: number;
    server: string;
    currency: string;
    balance: number;
    equity: number;
    leverage: number;
  };
  checks: BrokerCheckItem[];
}

export type BrokerAssetClass = 'FX' | 'CRYPTO';
export type BrokerConnectionState = 'CONNECTED' | 'STANDBY_GATED' | 'DEGRADED' | 'DISCONNECTED';

export interface BrokerAccountHeartbeat {
  id: string;
  name: string;
  assetClass: BrokerAssetClass;
  broker: string;
  server: string;
  accountId: string | number;
  environment: 'DEMO' | 'LIVE' | 'SANDBOX' | 'TESTNET';
  status: BrokerConnectionState;
  pingMs: number;
  lastHeartbeat: number; // unix timestamp in ms
  feedStatus: 'STREAMING' | 'HEARTBEAT_ONLY' | 'STALE' | 'DISCONNECTED';
  activeSymbols: string[];
  protocol: 'MT5_IPC' | 'REST_WS_FEED' | 'FIX_BRIDGE';
  safetyGated?: boolean;
  notes?: string;
  lastError?: string;
}

export interface BrokerHeartbeatSummary {
  timestamp: number;
  totalAccounts: number;
  onlineCount: number;
  degradedCount: number;
  offlineCount: number;
  averagePingMs: number;
  accounts: BrokerAccountHeartbeat[];
}

export interface BrokerAccountConfig {
  accountId: number;
  broker: string;
  server: string;
  accountName: string;
  currency: string;
  tradeMode: 'DEMO' | 'LIVE';
  balance: number;
  leverage: number;
  ipcPort: number;
  investorPasswordMasked?: string;
  configuredViaSecrets?: boolean;
  hasSecretPassword?: boolean;
  assetCoverage: ('FX' | 'CRYPTO')[];
  symbols: string[];
}
