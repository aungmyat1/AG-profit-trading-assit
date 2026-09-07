import { Candle, CorrelationMatrixData, CorrelationPair, CorrelationStrength, Position } from '../types/trading';
import { SUPPORTED_SYMBOLS, generateRealisticCandles } from '../data/marketData';

/**
 * Computes percentage price returns for a series of candles
 */
export function calculateReturns(candles: Candle[]): number[] {
  if (candles.length < 2) return [];
  const returns: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const prevClose = candles[i - 1].close;
    const currClose = candles[i].close;
    if (prevClose !== 0) {
      returns.push((currClose - prevClose) / prevClose);
    } else {
      returns.push(0);
    }
  }
  return returns;
}

/**
 * Computes the Pearson Correlation Coefficient between two return series
 */
export function computePearsonCorrelation(returnsA: number[], returnsB: number[]): number {
  const n = Math.min(returnsA.length, returnsB.length);
  if (n < 2) return 0;

  let sumA = 0;
  let sumB = 0;
  for (let i = 0; i < n; i++) {
    sumA += returnsA[i];
    sumB += returnsB[i];
  }
  const meanA = sumA / n;
  const meanB = sumB / n;

  let numerator = 0;
  let denomA = 0;
  let denomB = 0;

  for (let i = 0; i < n; i++) {
    const diffA = returnsA[i] - meanA;
    const diffB = returnsB[i] - meanB;
    numerator += diffA * diffB;
    denomA += diffA * diffA;
    denomB += diffB * diffB;
  }

  const denominator = Math.sqrt(denomA * denomB);
  if (denominator === 0) return 0;

  const r = numerator / denominator;
  // Bound to [-1.0, 1.0] to guard against floating point inaccuracies
  return Math.max(-1.0, Math.min(1.0, Number(r.toFixed(4))));
}

/**
 * Classifies the correlation strength and provides qualitative descriptions
 */
export function classifyCorrelation(coefficient: number): {
  strength: CorrelationStrength;
  description: string;
} {
  if (coefficient >= 0.70) {
    return {
      strength: 'STRONG_POSITIVE',
      description: 'Strong Positive — assets move in tandem; high directional co-movement.'
    };
  } else if (coefficient >= 0.30) {
    return {
      strength: 'MODERATE_POSITIVE',
      description: 'Moderate Positive — noticeable co-movement with minor divergence.'
    };
  } else if (coefficient > -0.30) {
    return {
      strength: 'NEUTRAL',
      description: 'Independent / Low Correlation — uncorrelated price dynamics for diversification.'
    };
  } else if (coefficient > -0.70) {
    return {
      strength: 'MODERATE_NEGATIVE',
      description: 'Moderate Inverse — partial opposite movement; moderate counter-trend hedge.'
    };
  } else {
    return {
      strength: 'STRONG_NEGATIVE',
      description: 'Strong Inverse — mirror opposite price action; strong natural hedging relationship.'
    };
  }
}

/**
 * Generates actionable risk guidance given active positions
 */
export function getCorrelationRiskGuidance(
  symbolA: string,
  symbolB: string,
  coefficient: number,
  activePositions: Position[] = []
): string | undefined {
  const posA = activePositions.find(p => p.symbol === symbolA && p.status === 'OPEN');
  const posB = activePositions.find(p => p.symbol === symbolB && p.status === 'OPEN');

  if (!posA && !posB) {
    if (coefficient >= 0.70) {
      return `Taking simultaneous ${symbolA} & ${symbolB} trades in the same direction multiplies directional exposure.`;
    } else if (coefficient <= -0.70) {
      return `${symbolA} and ${symbolB} have strong inverse correlation; opposing setups can act as natural hedge.`;
    }
    return undefined;
  }

  if (posA && posB) {
    const sameSide = posA.side === posB.side;
    if (coefficient >= 0.70) {
      if (sameSide) {
        return `⚠️ ACTIVE RISK OVERLAP: Both open positions are ${posA.side}. Since correlation is +${coefficient.toFixed(2)}, total effective risk is amplified.`;
      } else {
        return `ℹ️ OPPOSING TRADES: One ${posA.side} and one ${posB.side} on strongly correlated pairs (+${coefficient.toFixed(2)}) creates net-flat delta exposure.`;
      }
    } else if (coefficient <= -0.70) {
      if (sameSide) {
        return `🛡️ NATURAL HEDGE: Both open positions are ${posA.side} on inversely correlated pairs (${coefficient.toFixed(2)}), dampening overall portfolio volatility.`;
      } else {
        return `⚠️ DOUBLE EXPOSURE: ${posA.side} on ${symbolA} + ${posB.side} on ${symbolB} stacks directional exposure due to inverse relationship (${coefficient.toFixed(2)}).`;
      }
    }
  }

  return undefined;
}

/**
 * Computes full cross-asset correlation matrix for all watch-list symbols
 */
export function computeCorrelationMatrix(
  symbols: string[] = SUPPORTED_SYMBOLS.map(s => s.symbol),
  daysBack: number = 3,
  timeframe: string = 'M15',
  activePositions: Position[] = []
): CorrelationMatrixData {
  // Pre-generate candles and return series for each symbol
  const returnsMap: Record<string, number[]> = {};
  for (const sym of symbols) {
    const candles = generateRealisticCandles(sym, timeframe as any, daysBack);
    returnsMap[sym] = calculateReturns(candles);
  }

  const matrix: Record<string, Record<string, number>> = {};
  const pairs: CorrelationPair[] = [];

  for (let i = 0; i < symbols.length; i++) {
    const symA = symbols[i];
    matrix[symA] = {};

    for (let j = 0; j < symbols.length; j++) {
      const symB = symbols[j];
      if (symA === symB) {
        matrix[symA][symB] = 1.0;
      } else {
        const coef = computePearsonCorrelation(returnsMap[symA], returnsMap[symB]);
        matrix[symA][symB] = coef;

        // Record pair once (for j > i)
        if (j > i) {
          const classification = classifyCorrelation(coef);
          const riskWarning = getCorrelationRiskGuidance(symA, symB, coef, activePositions);
          pairs.push({
            symbolA: symA,
            symbolB: symB,
            coefficient: coef,
            strength: classification.strength,
            description: classification.description,
            riskWarning
          });
        }
      }
    }
  }

  return {
    symbols,
    matrix,
    pairs,
    timeframe,
    lookbackDays: daysBack,
    timestamp: Math.floor(Date.now() / 1000)
  };
}
