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
  Timeframe,
  DecisionState
} from '../types/trading';

/**
 * Calculates EMA for an array of values
 */
export function calculateEMA(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const emaArray: number[] = new Array(values.length).fill(0);
  if (values.length === 0) return emaArray;

  let ema = values[0];
  emaArray[0] = ema;
  for (let i = 1; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    emaArray[i] = ema;
  }
  return emaArray;
}

/**
 * Identifies session boxes (Asian 00:00-06:00, London 06:00-11:00/07:00-11:00, NY 12:00-15:00)
 */
export function extractSessionBoxes(candles: Candle[], maxRangePips: number = 25.0, pipMultiplier: number = 10000): SessionBox[] {
  const boxes: SessionBox[] = [];
  if (candles.length === 0) return boxes;

  // Group candles by UTC calendar day
  const dayMap = new Map<string, Candle[]>();
  for (const c of candles) {
    const d = new Date(c.time * 1000);
    const dayKey = d.toISOString().split('T')[0];
    if (!dayMap.has(dayKey)) dayMap.set(dayKey, []);
    dayMap.get(dayKey)!.push(c);
  }

  for (const [dayKey, dayCandles] of dayMap.entries()) {
    // 1. Asian Session: 00:00 to 06:00 UTC
    const asianCandles = dayCandles.filter(c => {
      const hours = new Date(c.time * 1000).getUTCHours();
      return hours >= 0 && hours < 6;
    });

    if (asianCandles.length > 0) {
      const high = Math.max(...asianCandles.map(c => c.high));
      const low = Math.min(...asianCandles.map(c => c.low));
      const midline = (high + low) / 2;
      const rangePips = (high - low) * pipMultiplier;
      const startTime = asianCandles[0].time;
      const endTime = asianCandles[asianCandles.length - 1].time + 15 * 60;

      boxes.push({
        id: `box_asian_${dayKey}`,
        name: `Asian Range (${dayKey})`,
        sessionType: 'Asian',
        startTime,
        endTime,
        high,
        low,
        midline,
        rangePips: Number(rangePips.toFixed(1)),
        isCompleted: true,
        isValidRange: rangePips <= maxRangePips
      });
    }

    // 2. London Reference Session: 06:00 to 11:00 UTC
    const londonCandles = dayCandles.filter(c => {
      const hours = new Date(c.time * 1000).getUTCHours();
      return hours >= 6 && hours < 11;
    });

    if (londonCandles.length > 0) {
      const high = Math.max(...londonCandles.map(c => c.high));
      const low = Math.min(...londonCandles.map(c => c.low));
      const midline = (high + low) / 2;
      const rangePips = (high - low) * pipMultiplier;
      const startTime = londonCandles[0].time;
      const endTime = londonCandles[londonCandles.length - 1].time + 15 * 60;

      boxes.push({
        id: `box_london_${dayKey}`,
        name: `London Range (${dayKey})`,
        sessionType: 'London',
        startTime,
        endTime,
        high,
        low,
        midline,
        rangePips: Number(rangePips.toFixed(1)),
        isCompleted: true,
        isValidRange: rangePips <= maxRangePips * 1.5
      });
    }

    // 3. New York Session: 12:00 to 17:00 UTC
    const nyCandles = dayCandles.filter(c => {
      const hours = new Date(c.time * 1000).getUTCHours();
      return hours >= 12 && hours < 17;
    });

    if (nyCandles.length > 0) {
      const high = Math.max(...nyCandles.map(c => c.high));
      const low = Math.min(...nyCandles.map(c => c.low));
      const midline = (high + low) / 2;
      const rangePips = (high - low) * pipMultiplier;
      const startTime = nyCandles[0].time;
      const endTime = nyCandles[nyCandles.length - 1].time + 15 * 60;

      boxes.push({
        id: `box_ny_${dayKey}`,
        name: `New York Range (${dayKey})`,
        sessionType: 'New_York',
        startTime,
        endTime,
        high,
        low,
        midline,
        rangePips: Number(rangePips.toFixed(1)),
        isCompleted: true,
        isValidRange: rangePips <= maxRangePips * 2.0
      });
    }
  }

  return boxes;
}

/**
 * Finds Swing Highs and Lows using fractal lookback
 */
export function findSwingPoints(candles: Candle[], lookback: number = 3): SwingPoint[] {
  const points: SwingPoint[] = [];
  if (candles.length < lookback * 2 + 1) return points;

  for (let i = lookback; i < candles.length - lookback; i++) {
    const current = candles[i];
    let isHigh = true;
    let isLow = true;

    for (let j = 1; j <= lookback; j++) {
      if (candles[i - j].high >= current.high || candles[i + j].high >= current.high) {
        isHigh = false;
      }
      if (candles[i - j].low <= current.low || candles[i + j].low <= current.low) {
        isLow = false;
      }
    }

    if (isHigh) {
      points.push({
        id: `sh_${current.time}`,
        type: 'HIGH',
        time: current.time,
        price: current.high,
        confirmed: true,
        isMajor: true
      });
    }
    if (isLow) {
      points.push({
        id: `sl_${current.time}`,
        type: 'LOW',
        time: current.time,
        price: current.low,
        confirmed: true,
        isMajor: true
      });
    }
  }

  return points;
}

/**
 * Detects Market Structure Breaks (BOS / CHoCH)
 */
export function detectStructureBreaks(candles: Candle[], swingPoints: SwingPoint[]): StructureBreak[] {
  const breaks: StructureBreak[] = [];
  const highs = swingPoints.filter(p => p.type === 'HIGH');
  const lows = swingPoints.filter(p => p.type === 'LOW');

  let currentTrend: 'BULLISH' | 'BEARISH' | 'NONE' = 'NONE';

  for (let i = 0; i < candles.length; i++) {
    const candle = candles[i];
    
    // Check break of recent swing high
    const relevantHighs = highs.filter(h => h.time < candle.time);
    if (relevantHighs.length > 0) {
      const lastHigh = relevantHighs[relevantHighs.length - 1];
      if (candle.close > lastHigh.price) {
        const isChoch = currentTrend === 'BEARISH';
        breaks.push({
          id: `break_${candle.time}_bullish`,
          type: isChoch ? 'CHOCH' : 'BOS',
          direction: 'BULLISH',
          time: candle.time,
          brokenLevel: lastHigh.price,
          breakPrice: candle.close
        });
        currentTrend = 'BULLISH';
      }
    }

    // Check break of recent swing low
    const relevantLows = lows.filter(l => l.time < candle.time);
    if (relevantLows.length > 0) {
      const lastLow = relevantLows[relevantLows.length - 1];
      if (candle.close < lastLow.price) {
        const isChoch = currentTrend === 'BULLISH';
        breaks.push({
          id: `break_${candle.time}_bearish`,
          type: isChoch ? 'CHOCH' : 'BOS',
          direction: 'BEARISH',
          time: candle.time,
          brokenLevel: lastLow.price,
          breakPrice: candle.close
        });
        currentTrend = 'BEARISH';
      }
    }
  }

  return breaks;
}

/**
 * Detects institutional Order Blocks (OB)
 */
export function detectOrderBlocks(candles: Candle[], timeframe: Timeframe = 'M15'): OrderBlock[] {
  const blocks: OrderBlock[] = [];
  if (candles.length < 5) return blocks;

  for (let i = 1; i < candles.length - 2; i++) {
    const prev = candles[i - 1];
    const curr = candles[i];
    const next = candles[i + 1];
    const afterNext = candles[i + 2];

    // Bullish OB: Last down candle before strong up impulse breaking structure
    if (curr.close < curr.open && next.close > next.open && (afterNext.high > Math.max(curr.high, prev.high))) {
      const displacement = (next.close - curr.open) / (curr.high - curr.low || 0.0001);
      if (displacement > 1.2) {
        // Check mitigation in subsequent candles
        let isMitigated = false;
        let mitigatedTime: number | undefined;
        for (let k = i + 2; k < candles.length; k++) {
          if (candles[k].low <= curr.high) {
            isMitigated = true;
            mitigatedTime = candles[k].time;
            break;
          }
        }

        blocks.push({
          id: `ob_bull_${curr.time}`,
          type: 'BULLISH_OB',
          timeframe,
          startTime: curr.time,
          topPrice: curr.high,
          bottomPrice: curr.low,
          isMitigated,
          mitigatedTime,
          strength: displacement > 2.0 ? 'HIGH' : 'MEDIUM'
        });
      }
    }

    // Bearish OB: Last up candle before strong down impulse
    if (curr.close > curr.open && next.close < next.open && (afterNext.low < Math.min(curr.low, prev.low))) {
      const displacement = (curr.open - next.close) / (curr.high - curr.low || 0.0001);
      if (displacement > 1.2) {
        let isMitigated = false;
        let mitigatedTime: number | undefined;
        for (let k = i + 2; k < candles.length; k++) {
          if (candles[k].high >= curr.low) {
            isMitigated = true;
            mitigatedTime = candles[k].time;
            break;
          }
        }

        blocks.push({
          id: `ob_bear_${curr.time}`,
          type: 'BEARISH_OB',
          timeframe,
          startTime: curr.time,
          topPrice: curr.high,
          bottomPrice: curr.low,
          isMitigated,
          mitigatedTime,
          strength: displacement > 2.0 ? 'HIGH' : 'MEDIUM'
        });
      }
    }
  }

  return blocks;
}

/**
 * Detects Fair Value Gaps (FVG)
 */
export function detectFairValueGaps(candles: Candle[], timeframe: Timeframe = 'M15'): FairValueGap[] {
  const gaps: FairValueGap[] = [];
  if (candles.length < 3) return gaps;

  for (let i = 1; i < candles.length - 1; i++) {
    const c1 = candles[i - 1];
    const c2 = candles[i];
    const c3 = candles[i + 1];

    // Bullish FVG: c1.high < c3.low
    if (c3.low > c1.high && c2.close > c2.open) {
      let isFilled = false;
      for (let j = i + 2; j < candles.length; j++) {
        if (candles[j].low <= c1.high) {
          isFilled = true;
          break;
        }
      }
      gaps.push({
        id: `fvg_bull_${c2.time}`,
        type: 'BULLISH_FVG',
        timeframe,
        startTime: c2.time,
        topPrice: c3.low,
        bottomPrice: c1.high,
        isFilled
      });
    }

    // Bearish FVG: c1.low > c3.high
    if (c3.high < c1.low && c2.close < c2.open) {
      let isFilled = false;
      for (let j = i + 2; j < candles.length; j++) {
        if (candles[j].high >= c1.low) {
          isFilled = true;
          break;
        }
      }
      gaps.push({
        id: `fvg_bear_${c2.time}`,
        type: 'BEARISH_FVG',
        timeframe,
        startTime: c2.time,
        topPrice: c1.low,
        bottomPrice: c3.high,
        isFilled
      });
    }
  }

  return gaps;
}

/**
 * Detects Liquidity Pools & Sweeps
 */
export function detectLiquidityPools(candles: Candle[], swingPoints: SwingPoint[], tolerancePips: number = 2.0, pipMultiplier: number = 10000): LiquidityPool[] {
  const pools: LiquidityPool[] = [];
  const highs = swingPoints.filter(p => p.type === 'HIGH');
  const lows = swingPoints.filter(p => p.type === 'LOW');

  // Detect Equal Highs (EQH)
  for (let i = 0; i < highs.length - 1; i++) {
    for (let j = i + 1; j < highs.length; j++) {
      const diffPips = Math.abs(highs[i].price - highs[j].price) * pipMultiplier;
      if (diffPips <= tolerancePips) {
        const poolPrice = Math.max(highs[i].price, highs[j].price);
        let isSwept = false;
        let sweptTime: number | undefined;
        for (const c of candles) {
          if (c.time > highs[j].time && c.high > poolPrice) {
            isSwept = true;
            sweptTime = c.time;
            break;
          }
        }

        pools.push({
          id: `eqh_${highs[i].time}_${highs[j].time}`,
          type: 'EQH',
          price: poolPrice,
          startTime: highs[i].time,
          isSwept,
          sweptTime,
          description: `Equal Highs (${diffPips.toFixed(1)} pip diff)`
        });
      }
    }
  }

  // Detect Equal Lows (EQL)
  for (let i = 0; i < lows.length - 1; i++) {
    for (let j = i + 1; j < lows.length; j++) {
      const diffPips = Math.abs(lows[i].price - lows[j].price) * pipMultiplier;
      if (diffPips <= tolerancePips) {
        const poolPrice = Math.min(lows[i].price, lows[j].price);
        let isSwept = false;
        let sweptTime: number | undefined;
        for (const c of candles) {
          if (c.time > lows[j].time && c.low < poolPrice) {
            isSwept = true;
            sweptTime = c.time;
            break;
          }
        }

        pools.push({
          id: `eql_${lows[i].time}_${lows[j].time}`,
          type: 'EQL',
          price: poolPrice,
          startTime: lows[i].time,
          isSwept,
          sweptTime,
          description: `Equal Lows (${diffPips.toFixed(1)} pip diff)`
        });
      }
    }
  }

  return pools;
}

/**
 * Deterministic Strategy Evaluation Engine for ST_ASIAN_SWEEP_5R_V1
 */
export function evaluateAsianSweepStrategy(
  symbol: string,
  candles: Candle[],
  strategy: StrategyContract,
  pipMultiplier: number = 10000,
  spreadPips: number = 1.2,
  accountBalance: number = 100000
): TradeProposal {
  const timestamp = Math.floor(Date.now() / 1000);
  const closes = candles.map(c => c.close);
  const ema50 = calculateEMA(closes, 50);
  const latestClose = closes[closes.length - 1] || 1.0;
  const latestEMA = ema50[ema50.length - 1] || latestClose;
  const emaTrend: 'BULLISH' | 'BEARISH' = latestClose >= latestEMA ? 'BULLISH' : 'BEARISH';

  const sessionBoxes = extractSessionBoxes(candles, 25.0, pipMultiplier);
  const latestAsianBox = [...sessionBoxes].reverse().find(b => b.sessionType === 'Asian');

  // Base checks
  if (!latestAsianBox) {
    return {
      id: `prop_${symbol}_${timestamp}`,
      symbol,
      strategyId: strategy.id,
      strategyName: strategy.name,
      timestamp,
      state: 'NO_TRADE',
      bias: 'NEUTRAL',
      riskReward: 0,
      riskPips: 0,
      suggestedLots: 0,
      reasons: ['No completed Asian Reference Session found in active lookback window.'],
      regime: {
        ema50Trend: emaTrend,
        rangePips: 0,
        isRangeValid: false
      },
      safetyGate: {
        spreadOk: spreadPips <= strategy.riskRules.maxSpreadAllowedPips,
        dailyLossOk: true,
        sessionTimeOk: true
      }
    };
  }

  const rangeValid = latestAsianBox.rangePips <= 25.0;
  const spreadOk = spreadPips <= strategy.riskRules.maxSpreadAllowedPips;

  // Evaluate post-Asian candles (London Open: 07:00-11:00 UTC)
  const postAsianCandles = candles.filter(c => c.time > latestAsianBox.endTime);

  let detectedSweep: {
    type: 'LONG' | 'SHORT';
    sweepCandle: Candle;
    entryPrice: number;
    stopLoss: number;
    takeProfit1: number;
    takeProfit2: number;
    riskPips: number;
    rMultiple: number;
  } | null = null;

  for (let i = 0; i < postAsianCandles.length; i++) {
    const c = postAsianCandles[i];
    const hour = new Date(c.time * 1000).getUTCHours();
    
    // Trade window: 07:00 to 11:00 UTC
    if (hour >= 7 && hour < 11) {
      // Long Setup: Wick breaches Asian Low, but body closes back inside the range
      if (c.low < latestAsianBox.low && c.close > latestAsianBox.low) {
        const entryPrice = c.close;
        const slBuffer = (latestAsianBox.high - latestAsianBox.low) * strategy.riskRules.stopLossRangePct;
        const stopLoss = latestAsianBox.low - slBuffer;
        const riskDistance = entryPrice - stopLoss;
        const riskPips = riskDistance * pipMultiplier;
        const takeProfit1 = latestAsianBox.high; // Opposite boundary
        const takeProfit2 = entryPrice + riskDistance * 5.0; // 5R Runner
        const rMultiple = 5.0;

        detectedSweep = {
          type: 'LONG',
          sweepCandle: c,
          entryPrice,
          stopLoss,
          takeProfit1,
          takeProfit2,
          riskPips: Number(riskPips.toFixed(1)),
          rMultiple
        };
        break;
      }

      // Short Setup: Wick breaches Asian High, but body closes back inside the range
      if (c.high > latestAsianBox.high && c.close < latestAsianBox.high) {
        const entryPrice = c.close;
        const slBuffer = (latestAsianBox.high - latestAsianBox.low) * strategy.riskRules.stopLossRangePct;
        const stopLoss = latestAsianBox.high + slBuffer;
        const riskDistance = stopLoss - entryPrice;
        const riskPips = riskDistance * pipMultiplier;
        const takeProfit1 = latestAsianBox.low; // Opposite boundary
        const takeProfit2 = entryPrice - riskDistance * 5.0; // 5R Runner
        const rMultiple = 5.0;

        detectedSweep = {
          type: 'SHORT',
          sweepCandle: c,
          entryPrice,
          stopLoss,
          takeProfit1,
          takeProfit2,
          riskPips: Number(riskPips.toFixed(1)),
          rMultiple
        };
        break;
      }
    }
  }

  // Calculate lot sizing based on 1% risk
  const riskAmount = accountBalance * strategy.riskRules.maxRiskPerTradePct; // $1,000 on $100k
  const pipValuePerLot = 10; // Standard FX $10/pip on 1.0 lot
  const suggestedLots = detectedSweep && detectedSweep.riskPips > 0
    ? Number((riskAmount / (detectedSweep.riskPips * pipValuePerLot)).toFixed(2))
    : 1.0;

  if (detectedSweep && rangeValid && spreadOk) {
    const reasons: string[] = [
      `Asian Reference Range conforms to <= 25.0 pips limit (Measured: ${latestAsianBox.rangePips} pips).`,
      `Valid liquidity sweep detected during London Open trade session (07:00-11:00 UTC).`,
      `Candle wick pierced ${detectedSweep.type === 'LONG' ? 'Asian Low' : 'Asian High'} and closed back inside range.`,
      `Spread check passed (${spreadPips.toFixed(1)} <= ${strategy.riskRules.maxSpreadAllowedPips} pips).`,
      `Dual-target structure: 75% volume at Opposite Boundary (${detectedSweep.takeProfit1.toFixed(5)}), 25% volume at 5.0R Runner (${detectedSweep.takeProfit2.toFixed(5)}).`
    ];

    return {
      id: `prop_${symbol}_${timestamp}`,
      symbol,
      strategyId: strategy.id,
      strategyName: strategy.name,
      timestamp,
      state: 'READY',
      bias: detectedSweep.type === 'LONG' ? 'BULLISH' : 'BEARISH',
      entrySide: detectedSweep.type === 'LONG' ? 'BUY' : 'SELL',
      entryPrice: detectedSweep.entryPrice,
      stopLoss: detectedSweep.stopLoss,
      takeProfit1: detectedSweep.takeProfit1,
      takeProfit2: detectedSweep.takeProfit2,
      riskReward: 5.0,
      riskPips: detectedSweep.riskPips,
      suggestedLots,
      reasons,
      invalidationLevel: detectedSweep.stopLoss,
      sessionBox: latestAsianBox,
      regime: {
        ema50Trend: emaTrend,
        rangePips: latestAsianBox.rangePips,
        isRangeValid: true
      },
      safetyGate: {
        spreadOk: true,
        dailyLossOk: true,
        sessionTimeOk: true
      }
    };
  }

  if (!rangeValid) {
    return {
      id: `prop_${symbol}_${timestamp}`,
      symbol,
      strategyId: strategy.id,
      strategyName: strategy.name,
      timestamp,
      state: 'NO_TRADE',
      bias: 'NEUTRAL',
      riskReward: 0,
      riskPips: 0,
      suggestedLots: 0,
      reasons: [
        `Asian range of ${latestAsianBox.rangePips} pips exceeds the maximum allowed ${25.0} pips constraint. Regime classified as Trend/Expansion, not Range.`
      ],
      sessionBox: latestAsianBox,
      regime: {
        ema50Trend: emaTrend,
        rangePips: latestAsianBox.rangePips,
        isRangeValid: false
      },
      safetyGate: {
        spreadOk,
        dailyLossOk: true,
        sessionTimeOk: true
      }
    };
  }

  // If inside London Open session watching for sweep
  return {
    id: `prop_${symbol}_${timestamp}`,
    symbol,
    strategyId: strategy.id,
    strategyName: strategy.name,
    timestamp,
    state: 'WATCH',
    bias: emaTrend,
    riskReward: 5.0,
    riskPips: 0,
    suggestedLots: 0,
    reasons: [
      `Asian range is valid (${latestAsianBox.rangePips} pips <= 25.0 pips).`,
      `Currently monitoring London Open session (07:00-11:00 UTC) for sweep of Asian High (${latestAsianBox.high.toFixed(5)}) or Low (${latestAsianBox.low.toFixed(5)}).`,
      `Trend filter EMA 50 bias: ${emaTrend}.`
    ],
    sessionBox: latestAsianBox,
    regime: {
      ema50Trend: emaTrend,
      rangePips: latestAsianBox.rangePips,
      isRangeValid: true
    },
    safetyGate: {
      spreadOk,
      dailyLossOk: true,
      sessionTimeOk: true
    }
  };
}
