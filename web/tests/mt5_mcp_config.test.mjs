import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveMt5DemoConfig, resolveMt5DemoServer, withoutUnresolvedPlaceholders } from '../scripts/mt5_mcp_config.mjs';

test('resolves the hyphen/underscore key spellings used in src/.env', () => {
  const result = resolveMt5DemoConfig({
    'VANTAGE-DEMO-LOGIN': 'demo-account-id',
    'VANTAGE-DEMO_PASSWORD': 'demo-password',
    'VANTAGE-DEMO_SERVER': 'demo-server'
  });

  assert.deepEqual(result.missing, []);
  assert.equal(result.password, 'demo-password');
  assert.equal(result.server, 'demo-server');
});

test('ignores unexpanded client placeholders so local .env values still apply', () => {
  const processEnv = { 'VANTAGE-DEMO_PASSWORD': '${input:mt5-demo-password}', MT5_ENVIRONMENT: 'DEMO' };
  const env = { 'VANTAGE-DEMO_PASSWORD': 'from-dotenv', ...withoutUnresolvedPlaceholders(processEnv) };

  assert.equal(resolveMt5DemoConfig(env).password, 'from-dotenv');
  assert.deepEqual(resolveMt5DemoConfig(processEnv).missing,
    ['VANTAGE-DEMO-LOGIN', 'VANTAGE-DEMO_PASSWORD', 'VANTAGE-DEMO-SERVER']);
});

test('reports exactly which Demo credentials are missing without exposing values', () => {
  const result = resolveMt5DemoConfig({
    'VANTAGE-DEMO-LOGIN': 'demo-account-id',
    MT5_ENVIRONMENT: 'DEMO'
  });

  assert.deepEqual(result.missing, ['VANTAGE-DEMO_PASSWORD', 'VANTAGE-DEMO-SERVER']);
  assert.equal(result.password, undefined);
  assert.equal(result.server, undefined);
});

test('resolves supported Demo credential aliases', () => {
  const result = resolveMt5DemoConfig({
    VANTAGE_DEMO_LOGIN: 'demo-account-id',
    MT5_PASSWORD: 'demo-password',
    VANTAGE_DEMO_SERVER: 'demo-server'
  });

  assert.deepEqual(result, {
    account: 'demo-account-id',
    password: 'demo-password',
    server: 'demo-server',
    missing: []
  });
});

test('requires the exact configured broker server instead of guessing from terminal path', () => {
  assert.deepEqual(resolveMt5DemoServer({ 'VANTAGE-DEMO-SERVER': 'broker-demo-name' }), {
    server: 'broker-demo-name',
    source: 'environment'
  });
  assert.equal(resolveMt5DemoServer({
    MT5_BROKER: 'VANTAGE',
    MT5_ENVIRONMENT: 'DEMO',
    MT5_TERMINAL_PATH: 'C:/Program Files/VT Markets MT5/terminal64.exe'
  }).server, undefined);
});