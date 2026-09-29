import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import test from 'node:test';
import { startReadOnlyProxy, startDeferredReadOnlyProxy, PROXY_INIT_ID, isPublicBybitMarketTool, isReadOnlyMt5Tool } from '../scripts/readonly_mcp_proxy.mjs';

function createHarness(allowTool) {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stdin = new PassThrough();
  const input = new PassThrough();
  let outputText = '';
  const output = new Writable({
    write(chunk, _encoding, callback) {
      outputText += chunk.toString();
      callback();
    }
  });
  const upstream = [];
  child.stdin.on('data', chunk => upstream.push(chunk.toString()));
  startReadOnlyProxy({ child, input, output, allowTool });
  return {
    child,
    input,
    upstream,
    outputText: () => outputText,
    response: () => outputText.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)),
    close: () => input.end()
  };
}

test('filters unannotated and destructive tools from tools/list', () => {
  const harness = createHarness(tool => tool.annotations?.readOnlyHint === true && tool.annotations?.destructiveHint !== true);
  harness.child.stdout.write(`${JSON.stringify({
    jsonrpc: '2.0', id: 1, result: { tools: [
      { name: 'market_read', annotations: { readOnlyHint: true } },
      { name: 'ambiguous', annotations: {} },
      { name: 'dangerous', annotations: { readOnlyHint: true, destructiveHint: true } }
    ] }
  })}\n`);
  assert.deepEqual(harness.response()[0].result.tools.map(tool => tool.name), ['readonly_market_read']);
  harness.close();
});

test('rejects calls to unavailable or mutating tools without forwarding them', () => {
  const harness = createHarness(tool => tool.annotations?.readOnlyHint === true && tool.annotations?.destructiveHint !== true);
  harness.child.stdout.write(`${JSON.stringify({
    jsonrpc: '2.0', id: 1, result: { tools: [
      { name: 'positions_get', annotations: { readOnlyHint: true } }
    ] }
  })}\n`);
  harness.input.write(`${JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'order_send' } })}\n`);
  assert.equal(harness.upstream.length, 0);
  assert.deepEqual(harness.response()[1].error, {
    code: -32601,
    message: 'Tool is not available in this read-only MCP.'
  });
  harness.close();
});

test('forwards calls only for tools previously exposed as read-only', () => {
  const harness = createHarness(tool => tool.annotations?.readOnlyHint === true && tool.annotations?.destructiveHint !== true);
  harness.child.stdout.write(`${JSON.stringify({
    jsonrpc: '2.0', id: 1, result: { tools: [
      { name: 'account_info', annotations: { readOnlyHint: true } }
    ] }
  })}\n`);
  harness.input.write(`${JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'readonly_account_info' } })}\n`);
  assert.equal(JSON.parse(harness.upstream[0]).params.name, 'account_info');
  assert.equal(harness.upstream.length, 1);
  harness.close();
});

test('Bybit allowlist includes public market reads only', () => {
  assert.equal(isPublicBybitMarketTool({ name: 'get_tickers', annotations: { readOnlyHint: true } }), true);
  assert.equal(isPublicBybitMarketTool({ name: 'get_kline', annotations: { readOnlyHint: true } }), true);
  assert.equal(isPublicBybitMarketTool({ name: 'get_wallet_balance', annotations: { readOnlyHint: true } }), false);
  assert.equal(isPublicBybitMarketTool({ name: 'create_order', annotations: { readOnlyHint: true } }), false);
  assert.equal(isPublicBybitMarketTool({ name: 'get_tickers', annotations: {} }), false);
});
test('MT5 allowlist exposes unannotated metatrader-mcp-server 0.5.1 query tools only', () => {
  // Exact tool names registered by metatrader-mcp-server 0.5.1 (no MCP annotations upstream).
  const reads = ['get_account_info', 'get_deals', 'get_orders', 'get_candles_latest', 'get_symbol_price',
    'get_all_symbols', 'get_symbols', 'get_all_positions', 'get_positions_by_symbol', 'get_positions_by_id',
    'get_all_pending_orders', 'get_pending_orders_by_symbol', 'get_pending_orders_by_id'];
  const writes = ['place_market_order', 'place_pending_order', 'modify_position', 'modify_pending_order',
    'close_position', 'cancel_pending_order', 'close_all_positions', 'close_all_positions_by_symbol',
    'close_all_profitable_positions', 'close_all_losing_positions', 'cancel_all_pending_orders',
    'cancel_pending_orders_by_symbol'];
  for (const name of reads) assert.equal(isReadOnlyMt5Tool({ name }), true, name);
  for (const name of writes) assert.equal(isReadOnlyMt5Tool({ name }), false, name);
  assert.equal(isReadOnlyMt5Tool({ name: 'get_symbol_price', annotations: { destructiveHint: true } }), false);
  assert.equal(isReadOnlyMt5Tool({ name: 'future_read', annotations: { readOnlyHint: true } }), true);
});

function createDeferredHarness(options = {}) {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stdin = new PassThrough();
  const input = new PassThrough();
  let outputText = '';
  const output = new Writable({
    write(chunk, _encoding, callback) {
      outputText += chunk.toString();
      callback();
    }
  });
  const upstream = [];
  child.stdin.on('data', chunk => upstream.push(...chunk.toString().trim().split('\n').map(line => JSON.parse(line))));
  startDeferredReadOnlyProxy({ child, input, output, allowTool: isReadOnlyMt5Tool, startupTimeoutMs: 50, ...options });
  const tick = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));
  return {
    child,
    upstream,
    send: message => input.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`),
    fromChild: message => child.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`),
    responses: () => outputText.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)),
    tick,
    close: () => input.end()
  };
}

const MT5_TOOLS = [{ name: 'get_symbol_price' }, { name: 'place_market_order' }];

test('deferred proxy answers initialize immediately and queues requests until the child is ready', async () => {
  const h = createDeferredHarness({ startupTimeoutMs: 10000 });
  h.send({ id: 0, method: 'initialize', params: { protocolVersion: '2025-06-18' } });
  h.send({ method: 'notifications/initialized' });
  h.send({ id: 1, method: 'tools/list' });
  await h.tick();
  assert.equal(h.responses()[0].id, 0);
  assert.equal(h.responses()[0].result.serverInfo.name, 'mt5ReadOnly');
  assert.deepEqual(h.upstream.map(m => m.method), ['initialize']); // tools/list waits
  h.fromChild({ id: PROXY_INIT_ID, result: { protocolVersion: '2025-06-18', capabilities: {} } });
  await h.tick();
  assert.deepEqual(h.upstream.map(m => m.method), ['initialize', 'notifications/initialized', 'tools/list']);
  h.fromChild({ id: 1, result: { tools: MT5_TOOLS } });
  await h.tick();
  const list = h.responses().find(m => m.id === 1);
  assert.deepEqual(list.result.tools.map(t => t.name), ['readonly_get_symbol_price']);
  assert.equal(h.responses().some(m => m.id === PROXY_INIT_ID), false);
  h.close();
});

test('deferred proxy returns the setup-status tool after the startup timeout, then signals list_changed', async () => {
  const h = createDeferredHarness();
  h.send({ id: 0, method: 'initialize', params: {} });
  h.send({ id: 1, method: 'tools/list' });
  await h.tick(80);
  assert.deepEqual(h.responses().find(m => m.id === 1).result.tools.map(t => t.name), ['mt5_setup_status']);
  h.send({ id: 2, method: 'tools/call', params: { name: 'readonly_get_symbol_price' } });
  await h.tick();
  assert.match(h.responses().find(m => m.id === 2).error.message, /still connecting/);
  h.fromChild({ id: PROXY_INIT_ID, result: {} });
  await h.tick();
  assert.ok(h.responses().some(m => m.method === 'notifications/tools/list_changed'));
  h.close();
});

test('deferred proxy stays connected in setup-status mode when the child exits', async () => {
  const h = createDeferredHarness({ startupTimeoutMs: 10000 });
  h.send({ id: 0, method: 'initialize', params: {} });
  h.send({ id: 1, method: 'tools/list' });
  await h.tick();
  h.child.emit('exit', 1, null);
  await h.tick();
  assert.deepEqual(h.responses().find(m => m.id === 1).result.tools.map(t => t.name), ['mt5_setup_status']);
  h.send({ id: 2, method: 'tools/call', params: { name: 'mt5_setup_status' } });
  h.send({ id: 3, method: 'ping' });
  await h.tick();
  assert.match(h.responses().find(m => m.id === 2).result.content[0].text, /exited \(code 1\)/);
  assert.deepEqual(h.responses().find(m => m.id === 3).result, {});
  h.close();
});

test('deferred proxy never forwards mutating tool calls', async () => {
  const h = createDeferredHarness({ startupTimeoutMs: 10000 });
  h.send({ id: 0, method: 'initialize', params: {} });
  h.fromChild({ id: PROXY_INIT_ID, result: {} });
  await h.tick();
  h.send({ id: 1, method: 'tools/list' });
  await h.tick();
  h.fromChild({ id: 1, result: { tools: MT5_TOOLS } });
  h.send({ id: 2, method: 'tools/call', params: { name: 'readonly_place_market_order' } });
  h.send({ id: 3, method: 'tools/call', params: { name: 'place_market_order' } });
  await h.tick();
  assert.equal(h.upstream.some(m => m.method === 'tools/call'), false);
  assert.equal(h.responses().find(m => m.id === 2).error.code, -32601);
  assert.equal(h.responses().find(m => m.id === 3).error.code, -32601);
  h.close();
});
