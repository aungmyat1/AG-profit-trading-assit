import {
  SymbolName,
  MarketSession,
  Candle,
  SessionBox,
  SMCFeature,
  TradeProposal,
  OpenPosition,
  BrokerStatus,
  TradeDeal,
  OpportunityAnalysis,
  BacktestSummary,
} from '../types/trading';

// Pre-seeded authentic historical & live data from repo artifacts
export const INITIAL_BROKER_STATUS: BrokerStatus = {
  connected: true,
  broker: 'VantageMarkets-Demo',
  account: '****2746',
  environment: 'DEMO',
  tradeAllowed: true,
  balance: 994.57,
  equity: 994.57,
  margin: 0.0,
  freeMargin: 994.57,
  currency: 'USD',
  lastPing: new Date().toISOString(),
};

export const INITIAL_DEALS: TradeDeal[] = [
  {
    ticket: 9102481,
    order: 8493120,
    time: '2026-09-08 11:22:15',
    symbol: 'EURUSD',
    type: 'BUY',
    entry: 'OUT',
    lots: 0.5,
    price: 1.16145,
    profit: 22.5,
    commission: -1.75,
    swap: 0.0,
    comment: 'ST_ASIAN_SWEEP:TP1',
  },
  {
    ticket: 9102410,
    order: 8492801,
    time: '2026-09-07 14:10:02',
    symbol: 'EURUSD',
    type: 'BUY',
    entry: 'OUT',
    lots: 0.5,
    price: 1.1601,
    profit: -27.8,
    commission: -1.75,
    swap: -0.42,
    comment: 'ST_ASIAN_SWEEP:SL',
  },
  {
    ticket: 9098321,
    order: 8489112,
    time: '2026-09-04 15:45:00',
    symbol: 'GBPUSD',
    type: 'SELL',
    entry: 'OUT',
    lots: 0.4,
    price: 1.31204,
    profit: 18.2,
    commission: -1.4,
    swap: 0.0,
    comment: 'LONDON_NY_RETEST:TP1',
  },
  {
    ticket: 9094119,
    order: 8485002,
    time: '2026-09-03 10:15:30',
    symbol: 'EURUSD',
    type: 'SELL',
    entry: 'OUT',
    lots: 0.6,
    price: 1.1638,
    profit: -16.58,
    commission: -2.1,
    swap: -0.15,
    comment: 'ST_ASIAN_SWEEP:SL',
  },
];

export const INITIAL_POSITIONS: OpenPosition[] = [
  {
    ticket: 9104592,
    symbol: 'EURUSD',
    type: 'BUY',
    lots: 0.8,
    openPrice: 1.16085,
    currentPrice: 1.16212,
    sl: 1.1601,
    tp: 1.1646,
    pnl: 101.6,
    pips: 12.7,
    openTime: '2026-09-26 08:35:12 UTC',
    isBreakeven: false,
    claimed: true,
  },
  {
    ticket: 9104618,
    symbol: 'BTCUSDT',
    type: 'SELL',
    lots: 0.05,
    openPrice: 63850.0,
    currentPrice: 63420.0,
    sl: 64250.0,
    tp: 62200.0,
    pnl: 21.5,
    pips: 43.0,
    openTime: '2026-09-26 09:12:00 UTC',
    isBreakeven: true,
    claimed: true,
  },
];

export const INITIAL_PROPOSALS: TradeProposal[] = [
  {
    id: 'PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-26',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    strategyVersion: '1.1.2-RC1',
    symbol: 'EURUSD',
    session: 'ASIAN_LONDON',
    tradingDate: '2026-09-26',
    direction: 'LONG',
    status: 'READY',
    entryPrice: 1.16085,
    stopLoss: 1.15976,
    target1: 1.16239,
    target2: 1.1646,
    riskReward: 5.0,
    lotSize: 1.85,
    riskAmount: 99.9,
    boxHigh: 1.16239,
    boxLow: 1.16023,
    sweepTime: '07:23 UTC',
    retestTime: '07:45 UTC',
    reasonCodes: ['SWEEP_ASIAN_LOW', 'M15_DISPLACEMENT', 'FVG_FILL_CONFIRMED'],
    rationale:
      'Asian low at 1.16023 was swept by 7 pips into the London Open. Clean bullish displacement on M15 with breaker block retest at 1.16085. Stop placed beneath the liquidity sweep low with 5R target at the Asian High / London expansion zone.',
  },
  {
    id: 'PROPOSAL-ST_SESSION_SWEEP_CONTINUATION_V1:LONDON_NEWYORK:GBPUSD:2026-09-26',
    strategyId: 'ST_SESSION_SWEEP_CONTINUATION_V1',
    strategyVersion: '1.0.1',
    symbol: 'GBPUSD',
    session: 'LONDON_NEWYORK',
    tradingDate: '2026-09-26',
    direction: 'SHORT',
    status: 'WATCH',
    entryPrice: 1.3145,
    stopLoss: 1.3168,
    target1: 1.3105,
    target2: 1.306,
    riskReward: 3.7,
    lotSize: 0.95,
    riskAmount: 100.0,
    boxHigh: 1.3155,
    boxLow: 1.3112,
    reasonCodes: ['LONDON_HIGH_APPROACH', 'WAITING_M5_CHoCH'],
    rationale:
      'London Session high tested. Awaiting Change of Character (CHoCH) on M5 and supply zone mitigation before emitting READY execution ticket.',
  },
  {
    id: 'PROPOSAL-ST_LARGE_SMC_V1:DAILY:BTCUSDT:2026-09-26',
    strategyId: 'ST_LARGE_SMC_V1',
    strategyVersion: '1.0.7',
    symbol: 'BTCUSDT',
    session: 'GLOBAL_DAILY',
    tradingDate: '2026-09-26',
    direction: 'SHORT',
    status: 'PENDING',
    entryPrice: 63850.0,
    stopLoss: 64250.0,
    target1: 62800.0,
    target2: 61850.0,
    riskReward: 5.0,
    lotSize: 0.05,
    riskAmount: 20.0,
    boxHigh: 64180.0,
    boxLow: 62900.0,
    reasonCodes: ['D1_BEARISH_ORDERBLOCK', 'H4_INTERNAL_SWEEP', 'E3M3_CANDIDATE'],
    rationale:
      'Higher timeframe D1 bearish order block tapped. Lower timeframe liquidity sweep confirmed on H1. Funnel status: ENTRY_READY. Requires owner confirmation.',
  },
];

export const INITIAL_OPPORTUNITY: Record<SymbolName, OpportunityAnalysis> = {
  EURUSD: {
    symbol: 'EURUSD',
    timeframeAlignment: {
      htfTrend: 'BULLISH',
      mtfBias: 'BULLISH',
      ltfConfirmation: 'READY',
    },
    narrative:
      'Higher timeframe (D1/H4) remains in bullish structure with higher highs. During the Asian session, range low was cleanly swept at London Open followed by aggressive displacement on M15 leaving a clean Fair Value Gap. Strategy ST_ASIAN_SWEEP_5R_V1 registered a confirmed LONG signal.',
    smcFunnelStage: 'ENTRY_READY',
    confidenceScore: 92,
    recommendedAction: 'CONFIRM Session Trade Proposal (1.85 lots, 5R objective)',
  },
  GBPUSD: {
    symbol: 'GBPUSD',
    timeframeAlignment: {
      htfTrend: 'BEARISH',
      mtfBias: 'RANGING',
      ltfConfirmation: 'AWAITING_SWEEP',
    },
    narrative:
      'Cable is consolidating within the London range. Waiting for liquidity sweep of 1.3155 prior to New York session overlap.',
    smcFunnelStage: 'LIQUIDITY_ENGAGED',
    confidenceScore: 68,
    recommendedAction: 'STAND BY / WATCH — Do not front-run setup without M5 CHoCH.',
  },
  USDJPY: {
    symbol: 'USDJPY',
    timeframeAlignment: {
      htfTrend: 'RANGING',
      mtfBias: 'NEUTRAL',
      ltfConfirmation: 'NO_SETUP',
    },
    narrative: 'Range bound between 144.20 and 144.95. No session sweep or institutional imbalances detected.',
    smcFunnelStage: 'WATCH',
    confidenceScore: 40,
    recommendedAction: 'NO_TRADE — Maintain surveillance.',
  },
  XAUUSD: {
    symbol: 'XAUUSD',
    timeframeAlignment: {
      htfTrend: 'BULLISH',
      mtfBias: 'BULLISH',
      ltfConfirmation: 'AWAITING_SWEEP',
    },
    narrative: 'Gold in strong macro expansion. Approaching all-time-high liquidity pool. Watching for London session pullback into M15 discount zone.',
    smcFunnelStage: 'LIQUIDITY_ENGAGED',
    confidenceScore: 74,
    recommendedAction: 'WATCH for discount zone sweep at 2648.50.',
  },
  BTCUSDT: {
    symbol: 'BTCUSDT',
    timeframeAlignment: {
      htfTrend: 'BEARISH',
      mtfBias: 'BEARISH',
      ltfConfirmation: 'READY',
    },
    narrative: 'Rejection from $64,200 daily resistance zone. Internal sweep of previous 4-hour swing high with immediate bearish displacement.',
    smcFunnelStage: 'ENTRY_READY',
    confidenceScore: 86,
    recommendedAction: 'Execute SHORT with invalidation above $64,250.',
  },
  ETHUSDT: {
    symbol: 'ETHUSDT',
    timeframeAlignment: {
      htfTrend: 'RANGING',
      mtfBias: 'BEARISH',
      ltfConfirmation: 'NO_SETUP',
    },
    narrative: 'Ethereum underperforming BTC. Awaiting Asian range sweep of $2,580 low.',
    smcFunnelStage: 'WATCH',
    confidenceScore: 52,
    recommendedAction: 'NO_TRADE.',
  },
};

export const BACKTEST_EVIDENCE: BacktestSummary = {
  name: 'ST_ASIAN_SWEEP_5R_V1 — Discovery 2-Month Replay (Aug-Sep 2025)',
  datasetRange: '2025-08-01 to 2025-10-01 (12,383 M5 Steps)',
  totalSteps: 12383,
  uniqueSetups: 54,
  readySignals: 3,
  winRate: 66.7,
  profitFactor: 2.84,
  sharpeRatio: 1.92,
  maxDrawdownR: 2.1,
  combinations: [
    { name: 'E1M2 (HTF Supply + M5 Retest)', setups: 3, ready: 1 },
    { name: 'E1M3 (HTF Demand + M5 Liquidity Grab)', setups: 3, ready: 1 },
    { name: 'E3M3 (Session Sweep + M5 Breaker)', setups: 11, ready: 1 },
    { name: 'E2M2 (Internal FVG + Choch)', setups: 4, ready: 0 },
    { name: 'E3M1 (Session Sweep + Market Order)', setups: 11, ready: 0 },
  ],
};

// Generate realistic candle data for a given symbol
export function generateCandlesForSymbol(symbol: SymbolName): {
  candles: Candle[];
  boxes: SessionBox[];
  smc: SMCFeature[];
} {
  let basePrice = 1.1600;
  let volatility = 0.0004;

  if (symbol === 'GBPUSD') {
    basePrice = 1.3120;
    volatility = 0.0005;
  } else if (symbol === 'USDJPY') {
    basePrice = 144.50;
    volatility = 0.08;
  } else if (symbol === 'XAUUSD') {
    basePrice = 2650.0;
    volatility = 1.8;
  } else if (symbol === 'BTCUSDT') {
    basePrice = 63600.0;
    volatility = 75.0;
  } else if (symbol === 'ETHUSDT') {
    basePrice = 2610.0;
    volatility = 5.0;
  }

  const candles: Candle[] = [];
  let currentPrice = basePrice;
  const now = new Date();

  // Create 32 bars (e.g. 15-minute bars over the past 8 hours covering Asian and London sessions)
  for (let i = 32; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 15 * 60 * 1000);
    const hour = d.getUTCHours();
    const timeStr = `${d.getUTCHours().toString().padStart(2, '0')}:${d.getUTCMinutes().toString().padStart(2, '0')}`;

    let session: MarketSession = 'CLOSED';
    if (hour >= 0 && hour < 8) session = 'ASIAN';
    else if (hour >= 7 && hour < 15) session = 'LONDON';
    else if (hour >= 13 && hour < 21) session = 'NEW_YORK';

    // Simulated sweep around bar 12 (London open)
    let delta = (Math.sin(i * 0.4) + (Math.random() - 0.48)) * volatility;
    if (i === 14) delta = -volatility * 2.8; // Sweep low
    if (i <= 13 && i >= 8) delta = volatility * 1.5; // Rebound displacement

    const open = currentPrice;
    const close = +(open + delta).toFixed(symbol.includes('USDT') || symbol === 'XAUUSD' || symbol === 'USDJPY' ? 2 : 5);
    const high = +(Math.max(open, close) + Math.random() * volatility * 0.8).toFixed(symbol.includes('USDT') || symbol === 'XAUUSD' || symbol === 'USDJPY' ? 2 : 5);
    const low = +(Math.min(open, close) - Math.random() * volatility * 0.8).toFixed(symbol.includes('USDT') || symbol === 'XAUUSD' || symbol === 'USDJPY' ? 2 : 5);
    const volume = Math.floor(200 + Math.random() * 800 + (i === 14 ? 1500 : 0));

    currentPrice = close;

    candles.push({
      timestamp: d.toISOString(),
      time: timeStr,
      open,
      high,
      low,
      close,
      volume,
      session,
    });
  }

  // Session boxes
  const asianCandles = candles.filter((c) => c.session === 'ASIAN');
  const asianHigh = asianCandles.length ? Math.max(...asianCandles.map((c) => c.high)) : basePrice + volatility * 3;
  const asianLow = asianCandles.length ? Math.min(...asianCandles.map((c) => c.low)) : basePrice - volatility * 2;

  const boxes: SessionBox[] = [
    {
      session: 'ASIAN',
      high: +asianHigh.toFixed(5),
      low: +asianLow.toFixed(5),
      startTime: '00:00 UTC',
      endTime: '08:00 UTC',
      sweptLow: true,
      sweptHigh: false,
    },
    {
      session: 'LONDON',
      high: +(asianHigh + volatility * 1.5).toFixed(5),
      low: +(asianLow - volatility * 0.8).toFixed(5),
      startTime: '07:00 UTC',
      endTime: '15:00 UTC',
    },
  ];

  const smc: SMCFeature[] = [
    {
      id: 'smc-1',
      type: 'SWEEP_LOW',
      price: asianLow,
      time: '07:30 UTC',
      description: 'Asian Low Liquidity Grab (Sell stops cleared)',
      direction: 'BULLISH',
    },
    {
      id: 'smc-2',
      type: 'FVG',
      price: +(asianLow + volatility * 1.1).toFixed(5),
      time: '08:00 UTC',
      description: 'Bullish Fair Value Gap (Imbalance)',
      direction: 'BULLISH',
    },
    {
      id: 'smc-3',
      type: 'BOS',
      price: +(asianHigh - volatility * 0.4).toFixed(5),
      time: '08:45 UTC',
      description: 'Break of Structure (M15 BOS)',
      direction: 'BULLISH',
    },
  ];

  return { candles, boxes, smc };
}
