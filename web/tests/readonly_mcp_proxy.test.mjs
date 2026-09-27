import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import test from 'node:test';
import { startReadOnlyProxy, isPublicBybitMarketTool } from '../scripts/readonly_mcp_proxy.mjs';

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
    message: 'Tool is not available in the read-only MT5 MCP.'
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