import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import test from 'node:test';
import { startReadOnlyProxy, isPublicBybitMarketTool, isReadOnlyMt5Tool } from '../scripts/readonly_mcp_proxy.mjs';

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
