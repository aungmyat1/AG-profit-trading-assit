export type SymbolName = 'EURUSD' | 'GBPUSD' | 'USDJPY' | 'XAUUSD' | 'BTCUSDT' | 'ETHUSDT';

export type MarketSession = 'ASIAN' | 'LONDON' | 'NEW_YORK' | 'CLOSED';

export type DecisionStatus = 'READY' | 'WATCH' | 'NO_TRADE' | 'PENDING' | 'AUTHORIZED' | 'REJECTED' | 'RESOLVED_TP' | 'RESOLVED_SL';

export type TradeDirection = 'LONG' | 'SHORT';

export interface Candle {
  timestamp: string;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  session?: MarketSession;
}

export interface SessionBox {
  session: 'ASIAN' | 'LONDON' | 'NEW_YORK';
  high: number;
  low: number;
  startTime: string;
  endTime: string;
  sweptHigh?: boolean;
  sweptLow?: boolean;
}

export interface SMCFeature {
  id: string;
  type: 'SWEEP_HIGH' | 'SWEEP_LOW' | 'BOS' | 'CHoCH' | 'FVG' | 'ORDER_BLOCK';
  price: number;
  time: string;
  description: string;
  direction?: 'BULLISH' | 'BEARISH';
}

export interface TradeProposal {
  id: string;
  strategyId: string;
  strategyVersion: string;
  symbol: SymbolName;
  session: string;
  tradingDate: string;
  direction: TradeDirection;
  status: DecisionStatus;
  entryPrice: number;
  stopLoss: number;
  target1: number; // 3R
  target2: number; // 5R
  riskReward: number;
  lotSize: number;
  riskAmount: number;
  boxHigh: number;
  boxLow: number;
  sweepTime?: string;
  retestTime?: string;
  reasonCodes: string[];
  rationale: string;
  ownerDecision?: 'CONFIRMED' | 'REJECTED';
  ownerDecisionTime?: string;
  executionCommand?: string;
}

export interface OpenPosition {
  ticket: number;
  symbol: SymbolName;
  type: 'BUY' | 'SELL';
  lots: number;
  openPrice: number;
  currentPrice: number;
  sl: number;
  tp: number;
  pnl: number;
  pips: number;
  openTime: string;
  isBreakeven: boolean;
  claimed: boolean;
}

export interface BrokerStatus {
  connected: boolean;
  broker: string;
  account: string;
  environment: 'DEMO' | 'SIMULATION' | 'LIVE';
  tradeAllowed: boolean;
  balance: number;
  equity: number;
  margin: number;
  freeMargin: number;
  currency: string;
  lastPing: string;
}

export interface TradeDeal {
  ticket: number;
  order: number;
  time: string;
  symbol: SymbolName;
  type: 'BUY' | 'SELL';
  entry: 'IN' | 'OUT';
  lots: number;
  price: number;
  profit: number;
  commission: number;
  swap: number;
  comment: string;
}

export interface OpportunityAnalysis {
  symbol: SymbolName;
  timeframeAlignment: {
    htfTrend: 'BULLISH' | 'BEARISH' | 'RANGING'; // D1/H4
    mtfBias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'RANGING'; // H1
    ltfConfirmation: 'READY' | 'AWAITING_SWEEP' | 'NO_SETUP'; // M15/M5
  };
  narrative: string;
  smcFunnelStage: 'WATCH' | 'LIQUIDITY_ENGAGED' | 'DISPLACEMENT' | 'ENTRY_READY';
  confidenceScore: number;
  recommendedAction: string;
}

export interface BacktestSummary {
  name: string;
  datasetRange: string;
  totalSteps: number;
  uniqueSetups: number;
  readySignals: number;
  winRate: number;
  profitFactor: number;
  sharpeRatio: number;
  maxDrawdownR: number;
  combinations: {
    name: string;
    setups: number;
    ready: number;
  }[];
}
