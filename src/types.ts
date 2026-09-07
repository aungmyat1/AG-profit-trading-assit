export type DecisionState = 'READY' | 'WATCH' | 'NO_TRADE' | 'DATA_ERROR';
export type TradeDirection = 'LONG' | 'SHORT';
export type SessionCycle = 'ASIAN_LONDON' | 'LONDON_NEWYORK' | 'NEWYORK_CLOSE' | 'CRYPTO_DAILY';

export interface EntryTicket {
  ticketId: string;
  strategyId: string;
  strategyVersion: string;
  symbol: string;
  cycle: SessionCycle;
  direction: TradeDirection;
  entryPrice: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  slDistancePips: number;
  riskRatio: string;
  recommendedLots: number;
  riskAmountUsd: number;
  cutoffUtc: string;
  status: 'PENDING_EXECUTION' | 'SIMULATED' | 'CLAIMED' | 'EXPIRED';
  timestamp: string;
  rationale: string;
}

export interface SessionDecision {
  symbol: string;
  name: string;
  assetClass: 'FOREX' | 'CRYPTO' | 'COMMODITY';
  cycle: SessionCycle;
  decision: DecisionState;
  reasonCode: string;
  sessionRangePips?: number;
  sessionHigh?: number;
  sessionLow?: number;
  sweepDetected?: boolean;
  sweepSide?: 'BUY_SIDE' | 'SELL_SIDE' | 'NONE';
  timestamp: string;
  entryTicket?: EntryTicket;
}

export interface StrategyContract {
  id: string;
  name: string;
  version: string;
  registered: boolean;
  active: boolean;
  research: boolean;
  demoAuthorized: boolean;
  liveAuthorized: boolean;
  engine: string;
  description: string;
  riskModel: string;
  allowedSymbols: string[];
}

export interface SMCSurveillanceItem {
  symbol: string;
  name: string;
  timeframe: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  htfPoi: {
    type: 'BULLISH_OB' | 'BEARISH_OB' | 'FVG' | 'LIQUIDITY_VOOR';
    priceRange: [number, number];
    status: 'ACTIVE' | 'TESTED' | 'MITIGATED';
  };
  liquiditySwept: boolean;
  sweepDetails: string;
  ltfShift: 'CONFIRMED' | 'FORMING' | 'WAITING';
  confirmationStage: 'STAGE_1_POI_HIT' | 'STAGE_2_LIQUIDITY_SWEEP' | 'STAGE_3_LTF_MSS' | 'STAGE_4_ENTRY_CONFIRMED' | 'MONITORING';
  alertStatus: 'ALERT_ACTIVE' | 'WATCHING' | 'INACTIVE';
  lastUpdated: string;
}

export interface StructureZone {
  id: string;
  type: 'ORDER_BLOCK' | 'FAIR_VALUE_GAP' | 'BUY_SIDE_LIQUIDITY' | 'SELL_SIDE_LIQUIDITY';
  bias: 'BULLISH' | 'BEARISH';
  high: number;
  low: number;
  timeframe: string;
  mitigated: boolean;
  strength: 'STRONG' | 'MODERATE' | 'WEAK';
}

export interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketAnalysisResult {
  symbol: string;
  timeframe: string;
  session: string;
  trend: 'STRONG_BULLISH' | 'BULLISH' | 'RANGE' | 'BEARISH' | 'STRONG_BEARISH';
  lastBOS: { price: number; time: string; type: 'BULLISH' | 'BEARISH' } | null;
  lastCHoCH: { price: number; time: string; type: 'BULLISH' | 'BEARISH' } | null;
  equilibrium50: number;
  premiumZone: [number, number];
  discountZone: [number, number];
  zones: StructureZone[];
  matchingStrategy: string | null;
  eligibleSignal: boolean;
  signalNotes: string;
}

export interface TradeJournalRecord {
  id: string;
  proposalId: string;
  date: string;
  symbol: string;
  cycle: string;
  strategy: string;
  version: string;
  direction: TradeDirection;
  entry: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  lotSize: number;
  terminalState: 'RESOLVED_TP1' | 'RESOLVED_TP2' | 'RESOLVED_SL' | 'BREAKEVEN' | 'SESSION_TIMEOUT';
  realizedR: number;
  profitUsd: number;
  evidenceQuality: 'HIGH' | 'MODERATE' | 'SIMULATED';
  notes: string;
}
