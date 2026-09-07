import {
  StrategyContract,
  SessionDecision,
  SMCSurveillanceItem,
  TradeJournalRecord,
  StructureZone,
  CandleData,
  MarketAnalysisResult
} from '../types';

export const REGISTERED_STRATEGIES: StrategyContract[] = [
  {
    id: 'ST_ASIAN_SWEEP_5R_V1',
    name: 'Asian Session Sweep 5R',
    version: '1.1.2-RC1',
    registered: true,
    active: true,
    research: true,
    demoAuthorized: false,
    liveAuthorized: false,
    engine: 'strategy_engine.session (Deterministic)',
    description: 'Intraday FX session liquidity sweep strategy targeting 5R expansion following Asian high/low sweeps during London open.',
    riskModel: 'Fixed 1.0% account risk, 5R asymmetric payout with 2.5R TP1 (50% partial)',
    allowedSymbols: ['EURUSD', 'GBPUSD']
  },
  {
    id: 'SESSION_TRADE_V1',
    name: 'Session Trade Codex V1',
    version: '1.0.1',
    registered: true,
    active: true,
    research: false,
    demoAuthorized: true,
    liveAuthorized: false,
    engine: 'session_strategy (Vantage MT5 Demo)',
    description: 'Post-Asian and Post-London session box breakout/sweep trade system with automated MT5 demo execution.',
    riskModel: 'Dynamic ATR & Session Range 25-pip cap, 0.5% risk',
    allowedSymbols: ['EURUSD', 'GBPUSD']
  },
  {
    id: 'ST_LARGE_SMC_V1',
    name: 'Large-SMC Institutional Model',
    version: '1.0.7',
    registered: true,
    active: false,
    research: true,
    demoAuthorized: false,
    liveAuthorized: false,
    engine: 'large_smc_research.engine (Forward Research)',
    description: 'Higher-timeframe (H4/D1) Order Block & FVG mitigation with Lower-Timeframe (M5/M1) Market Structure Shift (MSS) and C10 stop policy.',
    riskModel: 'Institutional supply/demand invalidation stop + 0.5% risk per setup',
    allowedSymbols: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
  },
  {
    id: 'ST_LIQUIDITY_SWEEP_RETEST_V1',
    name: 'BTC/ETH Liquidity Sweep Retest',
    version: '2.0.0',
    registered: true,
    active: false,
    research: true,
    demoAuthorized: false,
    liveAuthorized: false,
    engine: 'btc_sweep_research (Bybit V5 Linear Perp)',
    description: 'Crypto perpetual sweep-and-retest engine evaluating 06:30-06:45 UTC observation window with fail-closed reason codes.',
    riskModel: 'Perpetual contract margin sizing with liquidation buffer',
    allowedSymbols: ['BTCUSDT', 'ETHUSDT']
  },
  {
    id: 'SMC_3R_V1',
    name: 'SMC 3R Invalidation Model',
    version: '1.0.0',
    registered: true,
    active: false,
    research: true,
    demoAuthorized: false,
    liveAuthorized: false,
    engine: 'smc_3r_v1 (Advisory)',
    description: 'SMC standard 3R risk-to-reward target with strict structural invalidation beyond opposing inducement level.',
    riskModel: 'Strict 1:3 RR with single-tier profit target',
    allowedSymbols: ['EURUSD', 'GBPUSD']
  }
];

export const INITIAL_DECISIONS: SessionDecision[] = [
  {
    symbol: 'EURUSD',
    name: 'Euro / US Dollar',
    assetClass: 'FOREX',
    cycle: 'ASIAN_LONDON',
    decision: 'READY',
    reasonCode: 'SWEEP_CONFIRMED_RETEST_VALID',
    sessionRangePips: 21.6,
    sessionHigh: 1.16239,
    sessionLow: 1.16023,
    sweepDetected: true,
    sweepSide: 'SELL_SIDE',
    timestamp: '2026-09-07T07:15:00Z',
    entryTicket: {
      ticketId: 'PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-07',
      strategyId: 'ST_ASIAN_SWEEP_5R_V1',
      strategyVersion: '1.1.2-RC1',
      symbol: 'EURUSD',
      cycle: 'ASIAN_LONDON',
      direction: 'LONG',
      entryPrice: 1.16030,
      stopLoss: 1.15976,
      tp1: 1.16165,
      tp2: 1.16300,
      slDistancePips: 5.4,
      riskRatio: '1:5.0',
      recommendedLots: 1.85,
      riskAmountUsd: 100.0,
      cutoffUtc: '2026-09-07T11:00:00Z',
      status: 'PENDING_EXECUTION',
      timestamp: '2026-09-07T07:15:00Z',
      rationale: 'Asian Low (1.16023) swept by 6 pips during 07:05 UTC bar; M1 displacement candle produced bullish CHoCH; Entry at fair value mitigation with Candidate Model A (Session Range 25%) SL buffer.'
    }
  },
  {
    symbol: 'GBPUSD',
    name: 'British Pound / US Dollar',
    assetClass: 'FOREX',
    cycle: 'ASIAN_LONDON',
    decision: 'WATCH',
    reasonCode: 'SESSION_RANGE_BELOW_MINIMUM_THRESHOLD',
    sessionRangePips: 17.2,
    sessionHigh: 1.31450,
    sessionLow: 1.31278,
    sweepDetected: false,
    sweepSide: 'NONE',
    timestamp: '2026-09-07T07:15:00Z'
  },
  {
    symbol: 'USDJPY',
    name: 'US Dollar / Japanese Yen',
    assetClass: 'FOREX',
    cycle: 'LONDON_NEWYORK',
    decision: 'NO_TRADE',
    reasonCode: 'MID_SESSION_CHOP_NO_CLEAR_LIQUIDITY_OBJECTIVE',
    sessionRangePips: 38.5,
    sessionHigh: 147.850,
    sessionLow: 147.465,
    sweepDetected: false,
    sweepSide: 'NONE',
    timestamp: '2026-09-07T07:15:00Z'
  },
  {
    symbol: 'XAUUSD',
    name: 'Gold / US Dollar',
    assetClass: 'COMMODITY',
    cycle: 'LONDON_NEWYORK',
    decision: 'WATCH',
    reasonCode: 'WAITING_FOR_NY_OPEN_EXPANSION',
    sessionRangePips: 145.0,
    sessionHigh: 2518.40,
    sessionLow: 2503.90,
    sweepDetected: false,
    sweepSide: 'NONE',
    timestamp: '2026-09-07T07:15:00Z'
  },
  {
    symbol: 'BTCUSDT',
    name: 'Bitcoin Perpetual (Bybit)',
    assetClass: 'CRYPTO',
    cycle: 'CRYPTO_DAILY',
    decision: 'READY',
    reasonCode: 'DAILY_HIGH_SWEEP_MSS_M5_CONFIRMED',
    sessionRangePips: 1480.0,
    sessionHigh: 58450.0,
    sessionLow: 56970.0,
    sweepDetected: true,
    sweepSide: 'BUY_SIDE',
    timestamp: '2026-09-07T06:35:00Z',
    entryTicket: {
      ticketId: 'PROPOSAL-ST_LIQUIDITY_SWEEP_RETEST_V1:DAILY:BTCUSDT:2026-09-07',
      strategyId: 'ST_LIQUIDITY_SWEEP_RETEST_V1',
      strategyVersion: '2.0.0',
      symbol: 'BTCUSDT',
      cycle: 'CRYPTO_DAILY',
      direction: 'SHORT',
      entryPrice: 58120.0,
      stopLoss: 58540.0,
      tp1: 57070.0,
      tp2: 56020.0,
      slDistancePips: 420.0,
      riskRatio: '1:5.0',
      recommendedLots: 0.24,
      riskAmountUsd: 100.0,
      cutoffUtc: '2026-09-07T22:00:00Z',
      status: 'PENDING_EXECUTION',
      timestamp: '2026-09-07T06:35:00Z',
      rationale: 'Equal highs at 58,450 swept during early Asia; Bybit M5 candle printed displacement to downside breaking 58,250 structure; limit entry at retest of bearish order block.'
    }
  }
];

export const SMC_SURVEILLANCE_LIST: SMCSurveillanceItem[] = [
  {
    symbol: 'EURUSD',
    name: 'Euro / US Dollar',
    timeframe: 'H4 -> M5',
    bias: 'BULLISH',
    htfPoi: {
      type: 'BULLISH_OB',
      priceRange: [1.15980, 1.16030],
      status: 'TESTED'
    },
    liquiditySwept: true,
    sweepDetails: 'Previous Daily Low & Asian Low swept',
    ltfShift: 'CONFIRMED',
    confirmationStage: 'STAGE_4_ENTRY_CONFIRMED',
    alertStatus: 'ALERT_ACTIVE',
    lastUpdated: '07:15 UTC'
  },
  {
    symbol: 'GBPUSD',
    name: 'British Pound / US Dollar',
    timeframe: 'H1 -> M5',
    bias: 'BULLISH',
    htfPoi: {
      type: 'FVG',
      priceRange: [1.31150, 1.31250],
      status: 'ACTIVE'
    },
    liquiditySwept: false,
    sweepDetails: 'Sell-side liquidity pooling at 1.31200',
    ltfShift: 'WAITING',
    confirmationStage: 'STAGE_1_POI_HIT',
    alertStatus: 'WATCHING',
    lastUpdated: '07:10 UTC'
  },
  {
    symbol: 'BTCUSDT',
    name: 'Bitcoin Perpetual',
    timeframe: 'D1 -> M5',
    bias: 'BEARISH',
    htfPoi: {
      type: 'BEARISH_OB',
      priceRange: [58200, 58500],
      status: 'TESTED'
    },
    liquiditySwept: true,
    sweepDetails: 'Clean equal highs cleared at 58,450',
    ltfShift: 'CONFIRMED',
    confirmationStage: 'STAGE_4_ENTRY_CONFIRMED',
    alertStatus: 'ALERT_ACTIVE',
    lastUpdated: '06:35 UTC'
  },
  {
    symbol: 'USDJPY',
    name: 'US Dollar / Yen',
    timeframe: 'H4 -> M15',
    bias: 'NEUTRAL',
    htfPoi: {
      type: 'LIQUIDITY_VOOR',
      priceRange: [146.90, 147.20],
      status: 'ACTIVE'
    },
    liquiditySwept: false,
    sweepDetails: 'Internal liquidity range bound',
    ltfShift: 'WAITING',
    confirmationStage: 'MONITORING',
    alertStatus: 'INACTIVE',
    lastUpdated: '06:50 UTC'
  },
  {
    symbol: 'XAUUSD',
    name: 'Gold',
    timeframe: 'H4 -> M5',
    bias: 'BULLISH',
    htfPoi: {
      type: 'BULLISH_OB',
      priceRange: [2498.0, 2505.0],
      status: 'ACTIVE'
    },
    liquiditySwept: true,
    sweepDetails: 'Asian session session-low test',
    ltfShift: 'FORMING',
    confirmationStage: 'STAGE_3_LTF_MSS',
    alertStatus: 'WATCHING',
    lastUpdated: '07:14 UTC'
  }
];

export const HISTORICAL_JOURNAL: TradeJournalRecord[] = [
  {
    id: 'TR-20260904-001',
    proposalId: 'PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-04',
    date: '2026-09-04',
    symbol: 'EURUSD',
    cycle: 'ASIAN_LONDON',
    strategy: 'ST_ASIAN_SWEEP_5R_V1',
    version: '1.1.2-RC1',
    direction: 'LONG',
    entry: 1.15840,
    stopLoss: 1.15786,
    tp1: 1.15975,
    tp2: 1.16110,
    lotSize: 1.85,
    terminalState: 'RESOLVED_TP2',
    realizedR: 5.0,
    profitUsd: 500.0,
    evidenceQuality: 'HIGH',
    notes: 'Clean 5R expansion. Asian Low swept by 4.2 pips. TP1 executed at +2.5R, runner trailed to 5R.'
  },
  {
    id: 'TR-20260903-001',
    proposalId: 'PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-03',
    date: '2026-09-03',
    symbol: 'GBPUSD',
    cycle: 'ASIAN_LONDON',
    strategy: 'ST_ASIAN_SWEEP_5R_V1',
    version: '1.1.2-RC1',
    direction: 'SHORT',
    entry: 1.31820,
    stopLoss: 1.31890,
    tp1: 1.31645,
    tp2: 1.31470,
    lotSize: 1.42,
    terminalState: 'RESOLVED_TP1',
    realizedR: 2.5,
    profitUsd: 250.0,
    evidenceQuality: 'HIGH',
    notes: 'TP1 reached at 2.5R. Remaining 50% stopped at breakeven.'
  },
  {
    id: 'TR-20260902-002',
    proposalId: 'PROPOSAL-ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-09-02',
    date: '2026-09-02',
    symbol: 'EURUSD',
    cycle: 'LONDON_NEWYORK',
    strategy: 'ST_ASIAN_SWEEP_5R_V1',
    version: '1.1.1',
    direction: 'SHORT',
    entry: 1.16450,
    stopLoss: 1.16510,
    tp1: 1.16300,
    tp2: 1.16150,
    lotSize: 1.66,
    terminalState: 'RESOLVED_SL',
    realizedR: -1.0,
    profitUsd: -100.0,
    evidenceQuality: 'MODERATE',
    notes: 'Candidate Model A comparison: Legacy SL was stopped out early; candidate geometry would have provided 12 pips buffer.'
  },
  {
    id: 'TR-20260901-001',
    proposalId: 'PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-01',
    date: '2026-09-01',
    symbol: 'EURUSD',
    cycle: 'ASIAN_LONDON',
    strategy: 'ST_ASIAN_SWEEP_5R_V1',
    version: '1.1.1',
    direction: 'LONG',
    entry: 1.16030,
    stopLoss: 1.16010,
    tp1: 1.16239,
    tp2: 1.16130,
    lotSize: 5.00,
    terminalState: 'RESOLVED_SL',
    realizedR: -1.0,
    profitUsd: -100.0,
    evidenceQuality: 'HIGH',
    notes: 'Recorded MT5 Vantage-Demo fill. Tight 2-pip SL tagged during volatility spike. Motivated Model A 25% range fix.'
  }
];

export const MOCK_CANDLES_EURUSD: CandleData[] = [
  { time: '05:00', open: 1.16110, high: 1.16140, low: 1.16080, close: 1.16120, volume: 1240 },
  { time: '05:30', open: 1.16120, high: 1.16160, low: 1.16100, close: 1.16150, volume: 1420 },
  { time: '06:00', open: 1.16150, high: 1.16239, low: 1.16130, close: 1.16220, volume: 2100 }, // Asian High
  { time: '06:30', open: 1.16220, high: 1.16230, low: 1.16140, close: 1.16160, volume: 1800 },
  { time: '07:00', open: 1.16160, high: 1.16180, low: 1.16023, close: 1.16040, volume: 4500 }, // Asian Low formed
  { time: '07:05', open: 1.16040, high: 1.16050, low: 1.15965, close: 1.16010, volume: 6200 }, // Sweep below Asian Low!
  { time: '07:10', open: 1.16010, high: 1.16080, low: 1.16005, close: 1.16075, volume: 5900 }, // Strong rejection / displacement
  { time: '07:15', open: 1.16075, high: 1.16120, low: 1.16030, close: 1.16100, volume: 4800 }, // Retest Entry at 1.16030
  { time: '07:20', open: 1.16100, high: 1.16150, low: 1.16085, close: 1.16140, volume: 4100 },
  { time: '07:25', open: 1.16140, high: 1.16180, low: 1.16120, close: 1.16175, volume: 3800 },
  { time: '07:30', open: 1.16175, high: 1.16210, low: 1.16160, close: 1.16200, volume: 3600 },
  { time: '07:35', open: 1.16200, high: 1.16260, low: 1.16190, close: 1.16250, volume: 4300 }
];

export const EURUSD_ANALYSIS: MarketAnalysisResult = {
  symbol: 'EURUSD',
  timeframe: 'M5',
  session: 'London Open (07:00 - 10:00 UTC)',
  trend: 'BULLISH',
  lastBOS: { price: 1.16160, time: '07:12 UTC', type: 'BULLISH' },
  lastCHoCH: { price: 1.16060, time: '07:08 UTC', type: 'BULLISH' },
  equilibrium50: 1.16102,
  premiumZone: [1.16102, 1.16260],
  discountZone: [1.15965, 1.16102],
  zones: [
    {
      id: 'z1',
      type: 'ORDER_BLOCK',
      bias: 'BULLISH',
      high: 1.16040,
      low: 1.15976,
      timeframe: 'M5',
      mitigated: false,
      strength: 'STRONG'
    },
    {
      id: 'z2',
      type: 'FAIR_VALUE_GAP',
      bias: 'BULLISH',
      high: 1.16080,
      low: 1.16050,
      timeframe: 'M5',
      mitigated: true,
      strength: 'MODERATE'
    },
    {
      id: 'z3',
      type: 'BUY_SIDE_LIQUIDITY',
      bias: 'BULLISH',
      high: 1.16239,
      low: 1.16239,
      timeframe: 'H1',
      mitigated: false,
      strength: 'STRONG'
    },
    {
      id: 'z4',
      type: 'SELL_SIDE_LIQUIDITY',
      bias: 'BEARISH',
      high: 1.16023,
      low: 1.16023,
      timeframe: 'H1',
      mitigated: true,
      strength: 'STRONG'
    }
  ],
  matchingStrategy: 'ST_ASIAN_SWEEP_5R_V1',
  eligibleSignal: true,
  signalNotes: 'Meets all criteria: Asian Low swept during London open window, displacement with Bullish CHoCH confirmed, order block retested with acceptable spread.'
};
