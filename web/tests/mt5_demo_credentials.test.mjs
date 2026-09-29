import assert from 'node:assert/strict';
import { PassThrough, Writable } from 'node:stream';
import test from 'node:test';
import { resolveDemoCredentials, isStrippedChildEnvKey } from '../scripts/mt5_demo_credentials.mjs';
import { startSetupErrorServer } from '../scripts/readonly_mcp_proxy.mjs';

const VT = { MT5_ENVIRONMENT: 'DEMO', VTMARKETS_DEMO_LOGIN: '1144985', VTMARKETS_DEMO_PASSWORD: 'secret', VTMARKETS_DEMO_SERVER: 'VTMarkets-Demo' };

test('defaults to the VT Markets demo account', () => {
  const result = resolveDemoCredentials(VT);
  assert.equal(result.ok, true);
  assert.equal(result.broker, 'VTMARKETS');
  assert.equal(result.login, '1144985');
  assert.equal(result.server, 'VTMarkets-Demo');
});

test('ignores Vantage credentials unless MT5_DEMO_BROKER=VANTAGE', () => {
  const vantage = { MT5_ENVIRONMENT: 'DEMO', 'VANTAGE-DEMO-LOGIN': '26088035', 'VANTAGE-DEMO_PASSWORD': 'p', 'VANTAGE-DEMO-SERVER': 'VantageMarkets-Demo' };
  assert.equal(resolveDemoCredentials(vantage).ok, false);
  const explicit = resolveDemoCredentials({ ...vantage, MT5_DEMO_BROKER: 'vantage' });
  assert.equal(explicit.ok, true);
  assert.equal(explicit.broker, 'VANTAGE');
});

test('requires MT5_ENVIRONMENT=DEMO', () => {
  const result = resolveDemoCredentials({ ...VT, MT5_ENVIRONMENT: 'LIVE' });
  assert.equal(result.ok, false);
  assert.match(result.error, /DEMO/);
});

test('refuses a non-demo or foreign-broker server and never echoes the password', () => {
  for (const server of ['VTMarkets-Live', 'VantageMarkets-Demo']) {
    const result = resolveDemoCredentials({ ...VT, VTMARKETS_DEMO_SERVER: server });
    assert.equal(result.ok, false);
    assert.doesNotMatch(result.error, /secret/);
  }
});

test('reports missing fields by name without values', () => {
  const result = resolveDemoCredentials({ MT5_ENVIRONMENT: 'DEMO', VTMARKETS_DEMO_LOGIN: '1' });
  assert.equal(result.ok, false);
  assert.match(result.error, /missing password, server/);
});

test('rejects a non-numeric login', () => {
  assert.equal(resolveDemoCredentials({ ...VT, VTMARKETS_DEMO_LOGIN: 'abc' }).ok, false);
});

test('strips broker and MT5 credential keys from the child environment', () => {
  for (const key of ['VTMARKETS_DEMO_PASSWORD', 'VANTAGE-LIVE-PASSWORD', 'MT5_PASSWORD', 'MT5_LOGIN', 'BYBIT_API_KEY']) {
    assert.equal(isStrippedChildEnvKey(key), true, key);
  }
  for (const key of ['PATH', 'APPDATA', 'MT5_TERMINAL_PATH']) assert.equal(isStrippedChildEnvKey(key), false, key);
});

test('setup-error server stays connected and exposes only mt5_setup_status', async () => {
  const input = new PassThrough();
  let text = '';
  const output = new Writable({ write(chunk, _e, cb) { text += chunk; cb(); } });
  startSetupErrorServer({ reason: 'no terminal', input, output });
  for (const msg of [
    { id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18' } },
    { method: 'notifications/initialized' },
    { id: 2, method: 'tools/list' },
    { id: 3, method: 'tools/call', params: { name: 'mt5_setup_status' } },
    { id: 4, method: 'tools/call', params: { name: 'readonly_place_market_order' } }
  ]) input.write(`${JSON.stringify({ jsonrpc: '2.0', ...msg })}\n`);
  await new Promise(resolve => setImmediate(resolve));
  const [init, list, status, blocked] = text.trim().split('\n').map(line => JSON.parse(line));
  assert.equal(init.result.protocolVersion, '2025-06-18');
  assert.deepEqual(list.result.tools.map(tool => tool.name), ['mt5_setup_status']);
  assert.match(status.result.content[0].text, /no terminal/);
  assert.equal(blocked.error.code, -32601);
});
