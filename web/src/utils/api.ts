import {
  Candle,
  SessionBox,
  SwingPoint,
  StructureBreak,
  OrderBlock,
  FairValueGap,
  LiquidityPool,
  TradeProposal,
  StrategyContract,
  Position,
  AuditLog,
  ReplayFixture
} from '../types/trading';
import { SUPPORTED_SYMBOLS, generateRealisticCandles } from '../data/marketData';
import { REGISTERED_STRATEGIES } from '../data/strategies';
import {
  extractSessionBoxes,
  findSwingPoints,
  detectStructureBreaks,
  detectOrderBlocks,
  detectFairValueGaps,
  detectLiquidityPools,
  evaluateAsianSweepStrategy
} from './smcEngine';

/**
 * Safely fetches JSON from an API endpoint with content-type verification
 * and fallback handling to prevent any "Unexpected token '<'" JSON parse errors.
 */
export async function safeFetchJson<T>(
  url: string,
  options?: RequestInit,
  fallback?: T
): Promise<T | null> {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      if (fallback !== undefined) return fallback;
      return null;
    }

    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      // Received non-JSON response (e.g. HTML index.html fallback)
      console.warn(`[API] Endpoint ${url} returned non-JSON content-type: ${contentType}`);
      if (fallback !== undefined) return fallback;
      return null;
    }

    const text = await res.text();
    if (!text || text.trim().startsWith('<')) {
      console.warn(`[API] Endpoint ${url} returned HTML or empty response body`);
      if (fallback !== undefined) return fallback;
      return null;
    }

    return JSON.parse(text) as T;
  } catch (err) {
    console.warn(`[API] Error querying ${url}:`, err);
    if (fallback !== undefined) return fallback;
    return null;
  }
}

/**
 * Client-side fallback generator for proposals if server is starting or offline.
 *
 * WP5 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1, frontend-as-renderer audit): this runs
 * the same TypeScript strategy approximation as server.ts's /api/proposals/scan, over
 * synthetic candles -- but until this fix it returned the result untagged, unlike that
 * route's explicit `marketDataSource:'SYNTHETIC', executionEligible:false` convention
 * (AG_SCANNER_SAFE_PROPOSAL_EXECUTION_REMEDIATION_V2). App.tsx seeds its `proposals`
 * state with this function's output at mount, before the first real fetch resolves;
 * ExecutionCockpit.tsx's `isAuthoritativeProposal` check (`marketDataSource !==
 * 'SYNTHETIC'`) reads an untagged proposal as authoritative, which is exactly the
 * silent-fake-geometry bypass that component's own comment warns against. Tag it
 * identically to server.ts so both synthetic sources are indistinguishable to
 * downstream authority checks -- never left implicitly "real" by omission.
 */
export function generateClientProposals(): TradeProposal[] {
  return SUPPORTED_SYMBOLS.map(symInfo => {
    const candles = generateRealisticCandles(symInfo.symbol, 'M15', 3);
    const strategy = REGISTERED_STRATEGIES[0];
    const proposal = evaluateAsianSweepStrategy(
      symInfo.symbol,
      candles,
      strategy,
      symInfo.pipMultiplier,
      symInfo.typicalSpread,
      1000 // Vantage Markets Demo baseline capital $1,000.00
    );
    return {
      ...proposal,
      marketDataSource: 'SYNTHETIC' as const,
      executionEligible: false,
      executionBlockReason: 'SYNTHETIC_MARKET_DATA'
    };
  });
}

/**
 * Client-side fallback generator for market analysis
 */
export function generateClientMarketAnalysis(symbol: string, timeframe = 'M15', days = 4) {
  const candles = generateRealisticCandles(symbol, timeframe as any, days);
  const symInfo = SUPPORTED_SYMBOLS.find(s => s.symbol === symbol) || SUPPORTED_SYMBOLS[0];

  const sessionBoxes = extractSessionBoxes(candles, 25.0, symInfo.pipMultiplier);
  const swingPoints = findSwingPoints(candles, 3);
  const structureBreaks = detectStructureBreaks(candles, swingPoints);
  const orderBlocks = detectOrderBlocks(candles, timeframe as any);
  const fairValueGaps = detectFairValueGaps(candles, timeframe as any);
  const liquidityPools = detectLiquidityPools(candles, swingPoints, 2.0, symInfo.pipMultiplier);

  return {
    symbol,
    timeframe,
    candles,
    analysis: {
      sessionBoxes,
      swingPoints,
      structureBreaks,
      orderBlocks,
      fairValueGaps,
      liquidityPools
    }
  };
}

/**
 * Default fallback positions
 */
export const DEFAULT_POSITIONS_FALLBACK: Position[] = [
  {
    ticket: 9021441,
    symbol: 'EURUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 0.02, // Initial 0.08 lots -> 0.06 partial close at TP1 -> 0.02 runner
    entryPrice: 1.08420,
    currentPrice: 1.08745,
    stopLoss: 1.08420, // Trailed to Breakeven
    takeProfit1: 1.08650,
    takeProfit2: 1.09170,
    openTime: Math.floor(Date.now() / 1000) - 7200,
    pnl: 6.50, // 0.02 lots * 32.5 pips floating profit on $1,000 demo account
    pnlR: 2.17,
    status: 'OPEN',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'London Open sweep of Asian Low (1.08310) on VantageMarkets-Demo #0.',
      'Initial order: 0.08 lots with 15.0 pips SL ($12.00 / 1.2% initial risk).',
      'TP1 (75% = 0.06 lots) filled at opposite boundary 1.08650 (+$13.80 booked).',
      'Stop loss moved to Breakeven (1.08420). Runner (0.02 lots) trailing to 5R.'
    ]
  },
  {
    ticket: 9021289,
    symbol: 'GBPUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 0.8,
    entryPrice: 1.29150,
    currentPrice: 1.29675,
    stopLoss: 1.28960,
    takeProfit1: 1.29520,
    takeProfit2: 1.30100,
    openTime: Math.floor(Date.now() / 1000) - 10800,
    closeTime: Math.floor(Date.now() / 1000) - 3600,
    pnl: 420.00,
    pnlR: 2.80,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'London Open liquidity sweep of Asian low at 1.29080.',
      'Target 1 (75%) executed at 1.29520; Runner closed into London lunch at +2.80R.'
    ]
  },
  {
    ticket: 9021045,
    symbol: 'EURUSD',
    strategyId: 'SESSION_TRADE_V1',
    side: 'SELL',
    volume: 0.6,
    entryPrice: 1.08680,
    currentPrice: 1.08830,
    stopLoss: 1.08830,
    takeProfit1: 1.08350,
    takeProfit2: 1.07900,
    openTime: Math.floor(Date.now() / 1000) - 18000,
    closeTime: Math.floor(Date.now() / 1000) - 12600,
    pnl: -90.00,
    pnlR: -1.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: false,
    tp1Filled: false,
    journalNotes: [
      'Early Asian high expansion attempt without candle confirmation.',
      'Clean SL execution at -1.00R. Risk guard maintained within daily limit.'
    ]
  },
  {
    ticket: 9019842,
    symbol: 'GBPUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'SELL',
    volume: 1.0,
    entryPrice: 1.29700,
    currentPrice: 1.29250,
    stopLoss: 1.29850,
    takeProfit1: 1.29300,
    takeProfit2: 1.28800,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 2,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 2 + 14400,
    pnl: 450.00,
    pnlR: 3.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Asian High sweep at London open with bearish displacement.',
      '75% booked at TP1 (+2.67R), 25% runner closed at 3.00R.'
    ]
  },
  {
    ticket: 9018420,
    symbol: 'EURUSD',
    strategyId: 'SESSION_TRADE_V1',
    side: 'BUY',
    volume: 1.5,
    entryPrice: 1.08150,
    currentPrice: 1.08000,
    stopLoss: 1.08000,
    takeProfit1: 1.08500,
    takeProfit2: 1.08900,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 3,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 3 + 7200,
    pnl: -225.00,
    pnlR: -1.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: false,
    tp1Filled: false,
    journalNotes: [
      'High-impact news slip through Asian Low boundary.',
      'Stop loss respected without modification.'
    ]
  },
  {
    ticket: 9017650,
    symbol: 'USDJPY',
    strategyId: 'ST_LIQUIDITY_SWEEP_RETEST_V1',
    side: 'BUY',
    volume: 0.5,
    entryPrice: 154.100,
    currentPrice: 154.950,
    stopLoss: 153.800,
    takeProfit1: 154.600,
    takeProfit2: 155.300,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 4,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 4 + 21600,
    pnl: 425.00,
    pnlR: 2.83,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Asian low sweep at Tokyo fixing.',
      'TP1 reached, stop moved to breakeven, closed before NY close.'
    ]
  },
  {
    ticket: 9016201,
    symbol: 'EURUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 1.2,
    entryPrice: 1.08300,
    currentPrice: 1.08820,
    stopLoss: 1.08150,
    takeProfit1: 1.08600,
    takeProfit2: 1.09050,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 5,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 5 + 18000,
    pnl: 624.00,
    pnlR: 3.47,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'High-probability Asian sweep during Frankfurt session.',
      'Max target reached before NY session open.'
    ]
  },
  {
    ticket: 9015110,
    symbol: 'GBPUSD',
    strategyId: 'ST_LIQUIDITY_SWEEP_RETEST_V1',
    side: 'SELL',
    volume: 0.9,
    entryPrice: 1.29850,
    currentPrice: 1.30000,
    stopLoss: 1.30000,
    takeProfit1: 1.29400,
    takeProfit2: 1.28950,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 6,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 6 + 5400,
    pnl: -135.00,
    pnlR: -1.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: false,
    tp1Filled: false,
    journalNotes: [
      'Failed London continuation; stop triggered.',
      'Controlled 1.00R loss.'
    ]
  },
  {
    ticket: 9014290,
    symbol: 'AUDUSD',
    strategyId: 'ST_LARGE_SMC_V1',
    side: 'BUY',
    volume: 1.0,
    entryPrice: 0.65400,
    currentPrice: 0.65880,
    stopLoss: 0.65280,
    takeProfit1: 0.65650,
    takeProfit2: 0.66000,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 7,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 7 + 25200,
    pnl: 480.00,
    pnlR: 4.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Clean Asian range 18 pips. Sweep of London Open wick.',
      'Filled TP1 and TP2 runner for +4.00R total return.'
    ]
  },
  {
    ticket: 9013540,
    symbol: 'GBPUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'SELL',
    volume: 0.8,
    entryPrice: 1.29500,
    currentPrice: 1.29650,
    stopLoss: 1.29650,
    takeProfit1: 1.29100,
    takeProfit2: 1.28600,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 10,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 10 + 7200,
    pnl: -120.00,
    pnlR: -1.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: false,
    tp1Filled: false,
    journalNotes: [
      'Failed sweep rejection; invalidated at 1.29650 stop loss.',
      'Controlled 1.00R loss.'
    ]
  },
  {
    ticket: 9012810,
    symbol: 'EURUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 1.0,
    entryPrice: 1.08200,
    currentPrice: 1.08740,
    stopLoss: 1.08050,
    takeProfit1: 1.08550,
    takeProfit2: 1.08950,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 14,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 14 + 18000,
    pnl: 540.00,
    pnlR: 3.60,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Asian low swept by 7 pips, immediate pinbar rejection.',
      '75% booked at TP1, trailing runner exited at 1.08740.'
    ]
  },
  {
    ticket: 9011920,
    symbol: 'USDJPY',
    strategyId: 'ST_LIQUIDITY_SWEEP_RETEST_V1',
    side: 'BUY',
    volume: 0.6,
    entryPrice: 153.900,
    currentPrice: 154.530,
    stopLoss: 153.650,
    takeProfit1: 154.400,
    takeProfit2: 155.000,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 19,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 19 + 21600,
    pnl: 378.00,
    pnlR: 2.52,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Asian compression followed by London expansion.',
      'Target 1 hit, breakeven moved, closed prior to NY close.'
    ]
  },
  {
    ticket: 9010450,
    symbol: 'GBPUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 1.0,
    entryPrice: 1.28900,
    currentPrice: 1.29580,
    stopLoss: 1.28740,
    takeProfit1: 1.29300,
    takeProfit2: 1.29700,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 25,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 25 + 16200,
    pnl: 680.00,
    pnlR: 4.25,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Textbook Asian sweep setup during London open.',
      'Captured composite 4.25R return with low drawdown.'
    ]
  },
  {
    ticket: 9009180,
    symbol: 'EURUSD',
    strategyId: 'SESSION_TRADE_V1',
    side: 'SELL',
    volume: 0.9,
    entryPrice: 1.08850,
    currentPrice: 1.09015,
    stopLoss: 1.09015,
    takeProfit1: 1.08500,
    takeProfit2: 1.08150,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 32,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 32 + 5400,
    pnl: -148.50,
    pnlR: -1.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: false,
    tp1Filled: false,
    journalNotes: [
      'Breakout attempt without structural retest.',
      'Stop loss triggered, loss controlled to 1.00R.'
    ]
  },
  {
    ticket: 9008205,
    symbol: 'AUDUSD',
    strategyId: 'ST_LARGE_SMC_V1',
    side: 'BUY',
    volume: 0.8,
    entryPrice: 0.65100,
    currentPrice: 0.65520,
    stopLoss: 0.64980,
    takeProfit1: 0.65350,
    takeProfit2: 0.65700,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 39,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 39 + 25200,
    pnl: 336.00,
    pnlR: 3.50,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Large SMC H1 POI mitigation with M15 confirmation.',
      'Target reached smoothly.'
    ]
  },
  {
    ticket: 9007110,
    symbol: 'EURUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 1.1,
    entryPrice: 1.07800,
    currentPrice: 1.08320,
    stopLoss: 1.07660,
    takeProfit1: 1.08100,
    takeProfit2: 1.08500,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 48,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 48 + 19800,
    pnl: 572.00,
    pnlR: 3.71,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Asian range 19.5 pips. London sweep wick close back inside.',
      'TP1 reached, runner trailed to 3.71R.'
    ]
  },
  {
    ticket: 9006020,
    symbol: 'GBPUSD',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'SELL',
    volume: 0.7,
    entryPrice: 1.29300,
    currentPrice: 1.29450,
    stopLoss: 1.29450,
    takeProfit1: 1.28900,
    takeProfit2: 1.28400,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 56,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 56 + 7200,
    pnl: -105.00,
    pnlR: -1.00,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: false,
    tp1Filled: false,
    journalNotes: [
      'Failed rejection of Asian High.',
      'Exited at standard 1.00R stop loss.'
    ]
  },
  {
    ticket: 9004890,
    symbol: 'USDJPY',
    strategyId: 'ST_ASIAN_SWEEP_5R_V1',
    side: 'BUY',
    volume: 0.8,
    entryPrice: 152.800,
    currentPrice: 153.520,
    stopLoss: 152.550,
    takeProfit1: 153.300,
    takeProfit2: 153.900,
    openTime: Math.floor(Date.now() / 1000) - 86400 * 64,
    closeTime: Math.floor(Date.now() / 1000) - 86400 * 64 + 21600,
    pnl: 460.00,
    pnlR: 2.88,
    status: 'CLOSED',
    claimed: true,
    isBreakevenMoved: true,
    tp1Filled: true,
    journalNotes: [
      'Asian Low sweep at Tokyo fix.',
      'Partial taken at TP1, closed into NY lunch.'
    ]
  }
];

export const DEFAULT_LOGS_FALLBACK: AuditLog[] = [
  {
    id: 'log_01',
    timestamp: Math.floor(Date.now() / 1000) - 7200,
    category: 'EXECUTION',
    action: 'DEMO_ORDER_FILLED',
    status: 'SUCCESS',
    details: { ticket: 9021441, symbol: 'EURUSD', side: 'BUY', volume: 1.25, price: 1.08420 }
  },
  {
    id: 'log_02',
    timestamp: Math.floor(Date.now() / 1000) - 3600,
    category: 'MANAGEMENT',
    action: 'TP1_PARTIAL_CLOSE',
    status: 'SUCCESS',
    details: { ticket: 9021441, closedVolume: 0.94, remainingVolume: 0.31, realizedPnl: 216.20 }
  }
];

export const DEFAULT_FIXTURES_FALLBACK: ReplayFixture[] = [
  {
    id: 'discovery_aug_sep2025',
    name: 'August-September 2025 EURUSD Discovery Backtest',
    symbol: 'EURUSD',
    period: '2025-08-01 to 2025-09-30',
    totalEvents: 42,
    stage1Qualified: 18,
    stage2WinRate: 72.2,
    totalReturnR: 24.5,
    description: 'Complete two-stage golden reconciliation slice testing Asian Session Sweeps on M15 with 5R targets.',
    candles: generateRealisticCandles('EURUSD', 'M15', 5)
  },
  {
    id: 'gbpusd_pilot_v1',
    name: 'GBPUSD Post-Asian London Pilot V1.0.1',
    symbol: 'GBPUSD',
    period: '2025-09-01 to 2025-09-28',
    totalEvents: 28,
    stage1Qualified: 12,
    stage2WinRate: 66.7,
    totalReturnR: 16.0,
    description: 'London Open sweep-reversal verification with strict EMA 50 trend bias gating.',
    candles: generateRealisticCandles('GBPUSD', 'M15', 5)
  }
];
