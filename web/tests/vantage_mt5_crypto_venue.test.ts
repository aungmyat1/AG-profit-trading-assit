// AG_VANTAGE_MT5_CRYPTO_VENUE_V1 (2026-09-13)
//
// The Vantage Demo MT5 account is now a crypto venue as well as an FX one
// (config/mt5.yaml symbol_map: BTCUSDT -> BTCUSD, ETHUSDT -> ETHUSD, live-verified).
// POST /api/execution/execute used to reject EVERY category==='CRYPTO' symbol with
// CRYPTO_EXECUTION_BLOCKED, which was a crypto-specific gate FX did not have. These
// tests prove:
//   1. an MT5-venue crypto symbol is now treated EXACTLY like an FX symbol on that
//      route -- same behaviour in mock mode, same fail-closed 410 in real mode;
//   2. no new broker authority was created: real mode is still retired for crypto;
//   3. the MT5 venue allow-list is an explicit map, not "anything labelled CRYPTO",
//      so a non-MT5-venue crypto symbol still fails closed.
//
// Run with: npx tsx --test tests/vantage_mt5_crypto_venue.test.ts

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  MT5_CRYPTO_VENUE_SYMBOLS,
  isMt5CryptoVenueSymbol,
  canonicalCryptoSymbol
} from '../src/data/marketData';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MOCK_PORT = 34119;
const REAL_PORT = 34120;
const MOCK_URL = `http://127.0.0.1:${MOCK_PORT}`;
const REAL_URL = `http://127.0.0.1:${REAL_PORT}`;
let mockServer: ChildProcess;
let realServer: ChildProcess;

async function waitForServer(baseUrl: string, timeoutMs = 20000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseUrl}/api/health`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error(`server at ${baseUrl} did not become ready in time`);
}

function startServer(port: number, mode: string): ChildProcess {
  const repoWebDir = path.resolve(__dirname, '..');
  const tsxCli = path.join(repoWebDir, 'node_modules', 'tsx', 'dist', 'cli.mjs');
  return spawn(process.execPath, [tsxCli, 'server.ts'], {
    cwd: repoWebDir,
    env: { ...process.env, PORT: String(port), VITE_AG_API_MODE: mode },
    windowsHide: true
  });
}

before(async () => {
  mockServer = startServer(MOCK_PORT, 'mock');
  realServer = startServer(REAL_PORT, 'real');
  await waitForServer(MOCK_URL);
  await waitForServer(REAL_URL);
}, { timeout: 40000 });

after(() => {
  mockServer?.kill();
  realServer?.kill();
});

function cryptoOrder(symbol: string) {
  return {
    symbol,
    strategyId: 'FRONTEND_MANUAL',
    side: 'BUY',
    lots: 0.01,
    entryPrice: 77300.0,
    stopLoss: 76300.0,
    takeProfit1: 79300.0,
    takeProfit2: 81300.0,
    user_confirmed: true
  };
}

// --- 1. The venue map itself ---------------------------------------------------------

test('the MT5 crypto venue map mirrors config/mt5.yaml symbol_map.VANTAGE', () => {
  assert.deepEqual(MT5_CRYPTO_VENUE_SYMBOLS, [
    { canonical: 'BTCUSDT', brokerSymbol: 'BTCUSD' },
    { canonical: 'ETHUSDT', brokerSymbol: 'ETHUSD' }
  ]);
  assert.equal(isMt5CryptoVenueSymbol('BTCUSD'), true);
  assert.equal(isMt5CryptoVenueSymbol('BTCUSDT'), true);
  assert.equal(isMt5CryptoVenueSymbol('ETHUSD'), true);
  assert.equal(canonicalCryptoSymbol('BTCUSD'), 'BTCUSDT');
});

test('a crypto symbol absent from the broker map is NOT an MT5 venue symbol', () => {
  for (const notMapped of ['SOLUSD', 'XRPUSD', 'BTCUSDC', 'DOGEUSD', '']) {
    assert.equal(isMt5CryptoVenueSymbol(notMapped), false, notMapped);
    assert.equal(canonicalCryptoSymbol(notMapped), null, notMapped);
  }
});

test('FX symbols are never mistaken for MT5 crypto venue symbols', () => {
  for (const fx of ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD']) {
    assert.equal(isMt5CryptoVenueSymbol(fx), false, fx);
  }
});

// --- 2. Route parity with FX ---------------------------------------------------------

for (const symbol of ['BTCUSD', 'ETHUSD']) {
  test(`mock-mode execute accepts ${symbol} exactly as it accepts EURUSD`, async () => {
    const res = await fetch(`${MOCK_URL}/api/execution/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cryptoOrder(symbol))
    });
    const data = await res.json();

    assert.equal(res.status, 200);
    assert.equal(data.success, true);
    // still explicitly simulated -- no broker was contacted for crypto either
    assert.equal(data.simulated, true);
    assert.equal(data.position.symbol, symbol);
  });

  test(`real-mode execute is retired for ${symbol}, same as for FX`, async () => {
    const res = await fetch(`${REAL_URL}/api/execution/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cryptoOrder(symbol))
    });
    const data = await res.json();

    assert.equal(res.status, 410);
    assert.equal(data.error, 'EXECUTION_ROUTE_RETIRED');
    assert.equal(data.ticket, undefined);
    assert.equal(data.simulated, undefined);
  });

  test(`${symbol} still requires user_confirmed, exactly like FX`, async () => {
    const res = await fetch(`${MOCK_URL}/api/execution/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cryptoOrder(symbol), user_confirmed: false })
    });
    const data = await res.json();

    assert.equal(res.status, 403);
    assert.ok(String(data.error).startsWith('EXECUTION_REJECTED'));
  });
}

test('FX behaviour on the same route is unchanged', async () => {
  const res = await fetch(`${MOCK_URL}/api/execution/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: 'EURUSD', strategyId: 'FRONTEND_MANUAL', side: 'BUY', lots: 0.01,
      entryPrice: 1.15997, stopLoss: 1.15797, takeProfit1: 1.16397, takeProfit2: 1.16797,
      user_confirmed: true
    })
  });
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.success, true);
  assert.equal(data.simulated, true);
});
