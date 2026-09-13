import { Candle, Timeframe } from '../types/trading';

export interface SymbolInfo {
  symbol: string;
  name: string;
  category: 'FX_MAJOR' | 'FX_CROSS' | 'COMMODITY' | 'CRYPTO';
  basePrice: number;
  pipMultiplier: number;
  typicalSpread: number;
  digits: number;
}

export const SUPPORTED_SYMBOLS: SymbolInfo[] = [
  { symbol: 'EURUSD', name: 'Euro / US Dollar', category: 'FX_MAJOR', basePrice: 1.0850, pipMultiplier: 10000, typicalSpread: 0.8, digits: 5 },
  { symbol: 'GBPUSD', name: 'British Pound / US Dollar', category: 'FX_MAJOR', basePrice: 1.2940, pipMultiplier: 10000, typicalSpread: 1.1, digits: 5 },
  { symbol: 'USDJPY', name: 'US Dollar / Japanese Yen', category: 'FX_MAJOR', basePrice: 154.20, pipMultiplier: 100, typicalSpread: 1.2, digits: 3 },
  { symbol: 'AUDUSD', name: 'Australian Dollar / US Dollar', category: 'FX_MAJOR', basePrice: 0.6580, pipMultiplier: 10000, typicalSpread: 1.0, digits: 5 },
  { symbol: 'XAUUSD', name: 'Gold / US Dollar', category: 'COMMODITY', basePrice: 2680.50, pipMultiplier: 10, typicalSpread: 2.2, digits: 2 },
  { symbol: 'BTCUSD', name: 'Bitcoin / US Dollar', category: 'CRYPTO', basePrice: 87500.0, pipMultiplier: 1, typicalSpread: 12.0, digits: 2 },
  { symbol: 'ETHUSD', name: 'Ethereum / US Dollar', category: 'CRYPTO', basePrice: 3150.0, pipMultiplier: 10, typicalSpread: 2.5, digits: 2 }
];

/**
 * AG_VANTAGE_MT5_CRYPTO_VENUE_V1 (2026-09-13).
 *
 * The crypto symbols the Vantage Demo MT5 account can actually trade, mirroring
 * `config/mt5.yaml`'s `symbol_map.VANTAGE` entries (`BTCUSDT -> BTCUSD`,
 * `ETHUSDT -> ETHUSD`), which were captured read-only from that account's live
 * `symbol_info()`. `brokerSymbol` is the exact string the MT5 terminal (and therefore
 * `scripts/web_execute_trade.py --symbol`) expects; `canonical` is the id the rest of
 * the repository's crypto research code uses.
 *
 * Deliberately an explicit allow-list, not "category === 'CRYPTO'": a crypto symbol the
 * broker map does not contain (e.g. SOLUSD) is NOT an MT5 venue symbol and must keep
 * failing closed, exactly as every crypto symbol did before this list existed.
 */
export interface Mt5CryptoVenueSymbol {
  canonical: string;
  brokerSymbol: string;
}

export const MT5_CRYPTO_VENUE_SYMBOLS: Mt5CryptoVenueSymbol[] = [
  { canonical: 'BTCUSDT', brokerSymbol: 'BTCUSD' },
  { canonical: 'ETHUSDT', brokerSymbol: 'ETHUSD' }
];

/** True only for a symbol the Vantage MT5 crypto venue map above actually contains. */
export function isMt5CryptoVenueSymbol(symbol: string): boolean {
  return MT5_CRYPTO_VENUE_SYMBOLS.some(
    s => s.brokerSymbol === symbol || s.canonical === symbol
  );
}

/** Canonical id for a broker crypto symbol, for display only. Null when unmapped. */
export function canonicalCryptoSymbol(symbol: string): string | null {
  return MT5_CRYPTO_VENUE_SYMBOLS.find(
    s => s.brokerSymbol === symbol || s.canonical === symbol
  )?.canonical ?? null;
}

/**
 * Generates realistic deterministic session candles for a given day
 */
export function generateRealisticCandles(
  symbol: string,
  timeframe: Timeframe = 'M15',
  daysBack: number = 3
): Candle[] {
  const symInfo = SUPPORTED_SYMBOLS.find(s => s.symbol === symbol) || SUPPORTED_SYMBOLS[0];
  const candles: Candle[] = [];

  const now = Math.floor(Date.now() / 1000);
  const m15Seconds = 15 * 60;
  const totalBars = (daysBack * 24 * 60) / 15; // 96 bars per day
  
  const startTimestamp = now - totalBars * m15Seconds;
  let currentPrice = symInfo.basePrice;
  const pipUnit = 1 / symInfo.pipMultiplier;

  // Predictable pseudo-random with fixed seed based on symbol
  let seed = symbol.split('').reduce((acc, char) => acc + char.charCodeAt(0), 42);
  const pseudoRandom = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };

  // Common macro factors generator using bar index
  const getGlobalFactors = (barIdx: number) => {
    const globalSeed = (barIdx * 7919 + 104729) % 233280;
    const usdDriver = ((globalSeed % 1000) / 500.0) - 1.0; // -1.0 to 1.0
    const cryptoDriver = (((globalSeed * 13) % 1000) / 500.0) - 1.0;
    const commodityDriver = (((globalSeed * 37) % 1000) / 500.0) - 1.0;
    return { usdDriver, cryptoDriver, commodityDriver };
  };

  for (let i = 0; i < totalBars; i++) {
    const time = startTimestamp + i * m15Seconds;
    const date = new Date(time * 1000);
    const hour = date.getUTCHours();
    const { usdDriver, cryptoDriver, commodityDriver } = getGlobalFactors(i);

    let session: 'Asian' | 'London' | 'New_York' | 'London_Open' | 'New_York_Open' = 'Asian';
    let volatility = 1.0;
    let bias = 0;

    if (hour >= 0 && hour < 6) {
      session = 'Asian';
      volatility = 0.4; // Tight Asian range (< 20 pips)
      bias = (pseudoRandom() - 0.5) * 0.1;
    } else if (hour >= 6 && hour < 12) {
      session = hour >= 7 && hour < 11 ? 'London_Open' : 'London';
      volatility = 1.6; // London expansion & sweep
      // Around 07:30 - 08:30 GMT simulate intentional liquidity sweep
      if (hour === 7 || hour === 8) {
        bias = symbol === 'EURUSD' || symbol === 'GBPUSD' ? -0.8 : 0.8; // Intentional sweep wick
      } else {
        bias = 0.6; // Reversal impulse
      }
    } else if (hour >= 12 && hour < 17) {
      session = hour >= 12 && hour < 15 ? 'New_York_Open' : 'New_York';
      volatility = 1.4; // New York continuation / retest
      bias = 0.3;
    } else {
      volatility = 0.6;
    }

    // Blend macro market factors for authentic cross-asset correlation
    let macroComponent = 0;
    if (symbol === 'EURUSD') {
      macroComponent = -0.75 * usdDriver;
    } else if (symbol === 'GBPUSD') {
      macroComponent = -0.70 * usdDriver + 0.15 * (pseudoRandom() - 0.5);
    } else if (symbol === 'AUDUSD') {
      macroComponent = -0.60 * usdDriver + 0.25 * commodityDriver;
    } else if (symbol === 'USDJPY') {
      macroComponent = 0.72 * usdDriver;
    } else if (symbol === 'XAUUSD') {
      macroComponent = -0.45 * usdDriver + 0.55 * commodityDriver;
    } else if (symbol === 'BTCUSD') {
      macroComponent = 0.85 * cryptoDriver - 0.15 * usdDriver;
    } else if (symbol === 'ETHUSD') {
      macroComponent = 0.82 * cryptoDriver + 0.1 * (pseudoRandom() - 0.5);
    }

    const candlePipRange = (2 + pseudoRandom() * 4 * volatility) * pipUnit;
    const combinedFactor = bias * 0.35 + macroComponent * 0.45 + (pseudoRandom() - 0.5) * 0.20;
    const dir = combinedFactor >= 0 ? 1 : -1;
    const open = currentPrice;
    const deltaMagnitude = candlePipRange * (0.3 + Math.abs(combinedFactor) * 0.8 + pseudoRandom() * 0.4);
    const close = open + dir * deltaMagnitude;
    
    // Create wicks
    const maxOC = Math.max(open, close);
    const minOC = Math.min(open, close);
    const upperWick = pseudoRandom() * candlePipRange * (session === 'London_Open' ? 1.5 : 0.6);
    const lowerWick = pseudoRandom() * candlePipRange * (session === 'London_Open' ? 1.8 : 0.6);

    const high = maxOC + upperWick;
    const low = minOC - lowerWick;
    const volume = Math.floor(500 + volatility * 2000 * pseudoRandom());

    currentPrice = close;

    candles.push({
      time,
      open: Number(open.toFixed(symInfo.digits)),
      high: Number(high.toFixed(symInfo.digits)),
      low: Number(low.toFixed(symInfo.digits)),
      close: Number(close.toFixed(symInfo.digits)),
      volume,
      session
    });
  }

  return candles;
}
