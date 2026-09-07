import { StrategyContract } from '../types/trading';

export const REGISTERED_STRATEGIES: StrategyContract[] = [
  {
    id: 'ST_ASIAN_SWEEP_5R_V1',
    name: 'Asian Session Liquidity Sweep 5R',
    family: 'Liquidity_Sweep',
    version: '1.1.1',
    status: 'ACTIVE_INCUBATION',
    instruments: ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD'],
    timeframe: 'M15',
    magicNumber: 777001,
    sessionPairs: [
      {
        pairId: 'ASIAN_LONDON',
        referenceSession: {
          name: 'Asian',
          startTimeGmt: '00:00',
          endTimeGmt: '06:00',
          metricsTracked: ['High', 'Low', 'Midline', 'RangePips']
        },
        tradeSession: {
          name: 'London_Open',
          startTimeGmt: '07:00',
          endTimeGmt: '11:00',
          maxEntries: 1
        }
      },
      {
        pairId: 'LONDON_NEWYORK',
        referenceSession: {
          name: 'London',
          startTimeGmt: '06:00',
          endTimeGmt: '11:00',
          metricsTracked: ['High', 'Low', 'Midline', 'RangePips']
        },
        tradeSession: {
          name: 'New_York_Open',
          startTimeGmt: '12:00',
          endTimeGmt: '15:00',
          maxEntries: 1
        }
      }
    ],
    entryRules: {
      longTrigger: 'SWEEP_REFERENCE_LOW',
      shortTrigger: 'SWEEP_REFERENCE_HIGH',
      condition: 'Price wick breaches Reference Session boundary and candle closes back inside Reference Range',
      orderType: 'MARKET'
    },
    riskRules: {
      riskMode: 'FIXED_PERCENT_OR_CONTRACT',
      stopLossMode: 'PERCENT_OF_SESSION_RANGE',
      stopLossRangePct: 0.25,
      maxSpreadAllowedPips: 2.0,
      maxRiskPerTradePct: 0.01 // 1%
    },
    targets: {
      totalTargetR: 5.0,
      legs: [
        {
          legId: 1,
          volumePct: 0.75,
          targetType: 'OPPOSITE_SESSION_BOUNDARY',
          actionOnFill: 'MOVE_RUNNER_SL_TO_BREAKEVEN'
        },
        {
          legId: 2,
          volumePct: 0.25,
          targetType: 'FIXED_R_MULTIPLE',
          fixedR: 5.0,
          actionOnFill: 'TRAIL_SWING_STRUCTURE'
        }
      ]
    },
    invalidation: {
      time: '15:00 GMT (New York Open Cutoff)',
      structural: 'M15 Candle close fully outside the sweep wick extreme'
    },
    authority: {
      registered: true,
      active: true,
      research: false,
      demoAuthorized: true,
      liveAuthorized: false
    },
    backtestMetrics: {
      winRate: 58.4,
      profitFactor: 2.34,
      sampleSize: 342,
      sharpeRatio: 1.88,
      maxDrawdownPct: 6.2,
      expectedValueR: 1.85,
      avgTradeDuration: '2h 15m'
    },
    confluenceCriteria: [
      {
        id: 'CRIT_RANGE',
        title: 'Asian Range Compression (<= 25.0 pips)',
        description: 'Asian range must be consolidated under 25 pips to prevent exhausted wide-range sessions.',
        mandatory: true
      },
      {
        id: 'CRIT_TIMING',
        title: 'London Open Timing Window (07:00-11:00 UTC)',
        description: 'Sweep must occur strictly during London market open liquidity injection.',
        mandatory: true
      },
      {
        id: 'CRIT_EMA',
        title: '50 EMA Trend Filter Alignment',
        description: 'Trade direction must harmonize with prevailing M15 50-period EMA trend bias.',
        mandatory: true
      },
      {
        id: 'CRIT_SPLIT',
        title: '75/25 Split Position & Breakeven Lock',
        description: '75% volume banked at opposite Asian boundary; remaining 25% runs to 5.0R risk-free.',
        mandatory: true
      }
    ],
    promotionGates: {
      stage: 'Active Incubation (Demo Verified)',
      nextStage: 'Live Production Candidate',
      criteriaNeeded: [
        '50 live demo verified trades with execution slip <= 0.3 pips',
        'Demonstrated maximum drawdown under 8.0%',
        'Zero human intervention rule violations',
        'Independent broker bridge audit'
      ],
      currentProgressPct: 78
    }
  },
  {
    id: 'SESSION_TRADE_V1',
    name: 'Canonical Session Trade V1',
    family: 'Session_Breakout_Reversal',
    version: '1.0.2',
    status: 'ACTIVE_INCUBATION',
    instruments: ['EURUSD', 'GBPUSD'],
    timeframe: 'M15',
    magicNumber: 777002,
    sessionPairs: [
      {
        pairId: 'ASIAN_LONDON',
        referenceSession: {
          name: 'Asian',
          startTimeGmt: '00:00',
          endTimeGmt: '06:00',
          metricsTracked: ['High', 'Low', 'Midline']
        },
        tradeSession: {
          name: 'London_AM',
          startTimeGmt: '06:00',
          endTimeGmt: '11:00',
          maxEntries: 1
        }
      }
    ],
    entryRules: {
      longTrigger: 'ASIAN_LOW_SWEEP_REVERSAL',
      shortTrigger: 'ASIAN_HIGH_SWEEP_REVERSAL',
      condition: 'Liquidity sweep of Asian range with M5/M15 displacement back inside',
      orderType: 'MARKET'
    },
    riskRules: {
      riskMode: 'FIXED_PERCENT',
      stopLossMode: 'STRUCTURAL_SWING',
      stopLossRangePct: 0.2,
      maxSpreadAllowedPips: 1.8,
      maxRiskPerTradePct: 0.01
    },
    targets: {
      totalTargetR: 3.5,
      legs: [
        {
          legId: 1,
          volumePct: 0.8,
          targetType: 'ASIAN_MIDLINE_OR_HIGH',
          actionOnFill: 'MOVE_SL_TO_BE'
        },
        {
          legId: 2,
          volumePct: 0.2,
          targetType: 'SESSION_HIGH_EXPANSION',
          fixedR: 3.5
        }
      ]
    },
    invalidation: {
      time: '11:00 GMT (End of London AM)',
      structural: 'Continuation candle close below Asian low extension'
    },
    authority: {
      registered: true,
      active: true,
      research: false,
      demoAuthorized: true,
      liveAuthorized: false
    },
    backtestMetrics: {
      winRate: 54.2,
      profitFactor: 1.95,
      sampleSize: 280,
      sharpeRatio: 1.62,
      maxDrawdownPct: 7.1,
      expectedValueR: 1.35,
      avgTradeDuration: '1h 45m'
    },
    confluenceCriteria: [
      {
        id: 'CRIT_DISPLACE',
        title: 'M5/M15 Displacement Re-entry',
        description: 'Must observe aggressive candle displacement closing back inside session boundaries.',
        mandatory: true
      },
      {
        id: 'CRIT_SPREAD',
        title: 'Broker Spread <= 1.8 pips',
        description: 'Execution spread must remain below 1.8 pips to prevent execution slippage drag.',
        mandatory: true
      }
    ],
    promotionGates: {
      stage: 'Active Incubation (Demo Verified)',
      nextStage: 'Live Production Candidate',
      criteriaNeeded: [
        'Complete 100 sample demo executions across both pairs',
        'Verify zero out-of-session entries'
      ],
      currentProgressPct: 65
    }
  },
  {
    id: 'ST_LARGE_SMC_V1',
    name: 'Higher-Timeframe Large SMC Strategy',
    family: 'Smart_Money_Concepts',
    version: '1.0.0',
    status: 'RESEARCH_DRAFT',
    instruments: ['EURUSD', 'GBPUSD', 'BTCUSD', 'ETHUSD'],
    timeframe: 'H1',
    magicNumber: 777003,
    sessionPairs: [],
    entryRules: {
      longTrigger: 'H1_DEMAND_OB_M15_CHOCH',
      shortTrigger: 'H1_SUPPLY_OB_M15_CHOCH',
      condition: 'H4/H1 Point of Interest tap followed by M15 change of character and FVG entry',
      orderType: 'LIMIT'
    },
    riskRules: {
      riskMode: 'FIXED_PERCENT',
      stopLossMode: 'OB_INVALIDATION',
      stopLossRangePct: 0.15,
      maxSpreadAllowedPips: 2.5,
      maxRiskPerTradePct: 0.005 // 0.5%
    },
    targets: {
      totalTargetR: 4.0,
      legs: [
        {
          legId: 1,
          volumePct: 0.5,
          targetType: 'INTERNAL_LIQUIDITY',
          actionOnFill: 'MOVE_SL_TO_BE'
        },
        {
          legId: 2,
          volumePct: 0.5,
          targetType: 'MAJOR_SWING_TARGET',
          fixedR: 4.0
        }
      ]
    },
    invalidation: {
      time: 'Daily Bar Close',
      structural: 'Full candle body close through H1 Order Block'
    },
    authority: {
      registered: true,
      active: false,
      research: true,
      demoAuthorized: false,
      liveAuthorized: false
    },
    backtestMetrics: {
      winRate: 46.8,
      profitFactor: 2.15,
      sampleSize: 165,
      sharpeRatio: 1.48,
      maxDrawdownPct: 9.4,
      expectedValueR: 1.72,
      avgTradeDuration: '8h 20m'
    },
    confluenceCriteria: [
      {
        id: 'CRIT_POI',
        title: 'H4 Institutional Point of Interest (POI) Tap',
        description: 'Price must decisively tap an unmitigated H4 Order Block or Fair Value Gap.',
        mandatory: true
      },
      {
        id: 'CRIT_CHOCH',
        title: 'M15 Change of Character (CHoCH)',
        description: 'Lower timeframe confirmation required: structural break of opposing swing level.',
        mandatory: true
      },
      {
        id: 'CRIT_FVG_ENTRY',
        title: 'Retest of In-Structure Fair Value Gap',
        description: 'Limit order resting at the 50% equilibrium of the inducement displacement FVG.',
        mandatory: false
      }
    ],
    promotionGates: {
      stage: 'Research Draft (Advisory Only)',
      nextStage: 'Demo Incubation',
      criteriaNeeded: [
        'Resolve all UNSIGNED contract fields in strategies/registry.yaml',
        'Implement automated deterministic MT5 limit order gateway',
        'Backtest across 5-year tick data with Monte Carlo validation'
      ],
      currentProgressPct: 35
    }
  },
  {
    id: 'ST_LIQUIDITY_SWEEP_RETEST_V1',
    name: 'Crypto & FX Sweep & Retest V1',
    family: 'Liquidity_Sweep',
    version: '1.0.0',
    status: 'RESEARCH_DRAFT',
    instruments: ['BTCUSD', 'ETHUSD', 'EURUSD'],
    timeframe: 'M15',
    magicNumber: 777004,
    sessionPairs: [],
    entryRules: {
      longTrigger: 'SSL_SWEEP_MSS_RETEST',
      shortTrigger: 'BSL_SWEEP_MSS_RETEST',
      condition: 'Major liquidity sweep followed by Market Structure Shift (MSS) and retest of FVG',
      orderType: 'LIMIT'
    },
    riskRules: {
      riskMode: 'FIXED_PERCENT',
      stopLossMode: 'SWEEP_EXTREME',
      stopLossRangePct: 0.2,
      maxSpreadAllowedPips: 5.0,
      maxRiskPerTradePct: 0.01
    },
    targets: {
      totalTargetR: 3.0,
      legs: [
        {
          legId: 1,
          volumePct: 1.0,
          targetType: 'EXTERNAL_LIQUIDITY_POOL',
          fixedR: 3.0
        }
      ]
    },
    invalidation: {
      time: '4H Window Cutoff',
      structural: 'Break of shift origin low/high'
    },
    authority: {
      registered: true,
      active: false,
      research: true,
      demoAuthorized: false,
      liveAuthorized: false
    },
    backtestMetrics: {
      winRate: 51.5,
      profitFactor: 1.82,
      sampleSize: 198,
      sharpeRatio: 1.35,
      maxDrawdownPct: 11.2,
      expectedValueR: 1.15,
      avgTradeDuration: '3h 10m'
    },
    confluenceCriteria: [
      {
        id: 'CRIT_BSL_SSL',
        title: 'Buyside/Sellside Liquidity Cleanout',
        description: 'Equal highs or equal lows must be swept before reversing.',
        mandatory: true
      },
      {
        id: 'CRIT_CRYPTO_VENUE',
        title: 'Cryptocurrency Venue Integration Gate',
        description: 'Requires Bybit/Binance API connection; blocked fail-closed under AG Profit authority.',
        mandatory: true
      }
    ],
    promotionGates: {
      stage: 'Research Draft (Crypto Incubation)',
      nextStage: 'Crypto Demo Testnet Integration',
      criteriaNeeded: [
        'Secure exchange API key authentication layer',
        'Crypto perpetual funding rate cost modeling',
        '24/7 websocket heartbeat monitor'
      ],
      currentProgressPct: 20
    }
  }
];
