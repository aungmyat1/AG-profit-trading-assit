import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { once } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import test from 'node:test';
import { startDeferredReadOnlyProxy, isReadOnlyMt5Tool } from '../scripts/readonly_mcp_proxy.mjs';
import { isStrippedChildEnvKey } from '../scripts/mt5_demo_credentials.mjs';
import {
  createRemoteHttpChild, createRemoteMcpServer, isAllowedRemoteRequest,
  resolveRemoteClientConfig, resolveRemoteServerConfig, REMOTE_PATH
} from '../scripts/mt5_remote_bridge.mjs';

const TOKEN = 'x'.repeat(40);

// Stands in for start_mt5_mcp.mjs on the Windows PC (already aliased readonly_ names).
function fakeLauncher() {
  const child = new EventEmitter();
  child.stdin = new PassThrough();
  child.stdout = new PassThrough();
  const seen = [];
  let buffer = '';
  child.stdin.on('data', chunk => {
    buffer += chunk.toString();
    let newline;
    while ((newline = buffer.indexOf('\n')) !== -1) {
      const message = JSON.parse(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
      seen.push(message);
      if (message.id === undefined) continue;
      let result = {};
      if (message.method === 'initialize') result = { protocolVersion: '2025-06-18', capabilities: {}, serverInfo: { name: 'mt5ReadOnly' } };
      if (message.method === 'tools/list') {
        result = { tools: [{ name: 'readonly_get_symbol_price' }, { name: 'readonly_place_market_order' }] };
      }
      if (message.method === 'tools/call') result = { content: [{ type: 'text', text: `called ${message.params.name}` }] };
      child.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id: message.id, result })}\n`);
    }
  });
  return { child, seen };
}

async function startServer(launcher) {
  const server = createRemoteMcpServer({ child: launcher.child, token: TOKEN });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return { server, url: `http://127.0.0.1:${server.address().port}${REMOTE_PATH}` };
}

function startClient(url, token = TOKEN) {
  const input = new PassThrough();
  const replies = [];
  const waiters = [];
  const output = new Writable({
    write(chunk, _encoding, callback) {
      for (const line of chunk.toString().split('\n').filter(Boolean)) {
        const message = JSON.parse(line);
        replies.push(message);
        for (const waiter of waiters.splice(0)) waiter();
      }
      callback();
    }
  });
  startDeferredReadOnlyProxy({ child: createRemoteHttpChild({ url, token }), input, output, allowTool: isReadOnlyMt5Tool, startupTimeoutMs: 2000 });
  const request = async message => {
    input.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`);
    for (;;) {
      const found = replies.find(reply => reply.id === message.id);
      if (found) return found;
      await new Promise(resolve => waiters.push(resolve));
    }
  };
  return { request, close: () => input.end() };
}

test('cloud client sees the same read-only tool names through the remote bridge', async () => {
  const launcher = fakeLauncher();
  const { server, url } = await startServer(launcher);
  const client = startClient(url);
  try {
    await client.request({ id: 1, method: 'initialize', params: {} });
    const list = await client.request({ id: 2, method: 'tools/list' });
    assert.deepEqual(list.result.tools.map(tool => tool.name), ['readonly_get_symbol_price']);
    const call = await client.request({ id: 3, method: 'tools/call', params: { name: 'readonly_get_symbol_price', arguments: { symbol_name: 'EURUSD' } } });
    assert.equal(call.result.content[0].text, 'called readonly_get_symbol_price');
    const blocked = await client.request({ id: 4, method: 'tools/call', params: { name: 'readonly_place_market_order' } });
    assert.ok(blocked.error);
    assert.ok(!launcher.seen.some(message => message.params?.name === 'readonly_place_market_order'));
  } finally {
    client.close();
    server.close();
  }
});

test('server rejects a wrong token and non-allowlisted calls', async () => {
  const launcher = fakeLauncher();
  const { server, url } = await startServer(launcher);
  try {
    const post = (body, token = TOKEN) => fetch(url, {
      method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` }, body: JSON.stringify(body)
    });
    assert.equal((await post({ jsonrpc: '2.0', id: 1, method: 'ping' }, 'y'.repeat(40))).status, 401);
    const order = await (await post({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'readonly_place_market_order' } })).json();
    assert.ok(order.error);
    const resources = await (await post({ jsonrpc: '2.0', id: 3, method: 'resources/list' })).json();
    assert.ok(resources.error);
    assert.equal(launcher.seen.length, 0);
    assert.equal((await fetch(url)).status, 405);
  } finally {
    server.close();
  }
});

test('unreachable remote surfaces a setup-status reason instead of hanging', async () => {
  const launcher = fakeLauncher();
  const { server, url } = await startServer(launcher);
  const client = startClient(url, 'z'.repeat(40));
  try {
    await client.request({ id: 1, method: 'initialize', params: {} });
    const list = await client.request({ id: 2, method: 'tools/list' });
    assert.deepEqual(list.result.tools.map(tool => tool.name), ['mt5_setup_status']);
    const status = await client.request({ id: 3, method: 'tools/call', params: { name: 'mt5_setup_status' } });
    assert.match(status.result.content[0].text, /HTTP 401/);
    assert.ok(!status.result.content[0].text.includes('z'.repeat(40)));
  } finally {
    client.close();
    server.close();
  }
});

test('remote config validation fails closed', () => {
  const base = { MT5_ENVIRONMENT: 'DEMO', MT5_MCP_REMOTE_URL: 'https://mt5.example.com/mcp', MT5_MCP_REMOTE_TOKEN: TOKEN };
  assert.equal(resolveRemoteClientConfig(base).ok, true);
  assert.equal(resolveRemoteClientConfig({ ...base, MT5_ENVIRONMENT: 'LIVE' }).ok, false);
  assert.equal(resolveRemoteClientConfig({ ...base, MT5_MCP_REMOTE_URL: 'http://mt5.example.com/mcp' }).ok, false);
  assert.equal(resolveRemoteClientConfig({ ...base, MT5_MCP_REMOTE_URL: 'http://127.0.0.1:8765/mcp' }).ok, true);
  assert.equal(resolveRemoteClientConfig({ ...base, MT5_MCP_REMOTE_URL: 'https://u:p@mt5.example.com/mcp' }).ok, false);
  const short = resolveRemoteClientConfig({ ...base, MT5_MCP_REMOTE_TOKEN: 'short' });
  assert.equal(short.ok, false);
  assert.ok(!short.error.includes('short'));
  assert.deepEqual(resolveRemoteServerConfig({ MT5_MCP_REMOTE_TOKEN: TOKEN }), { ok: true, host: '127.0.0.1', port: 8765, token: TOKEN });
  assert.equal(resolveRemoteServerConfig({}).ok, false);
  assert.equal(resolveRemoteServerConfig({ MT5_MCP_REMOTE_TOKEN: TOKEN, MT5_MCP_REMOTE_PORT: '0' }).ok, false);
});

test('allowlist gate and child-env stripping cover the remote keys', () => {
  assert.equal(isAllowedRemoteRequest({ method: 'tools/call', params: { name: 'readonly_get_candles_latest' } }), true);
  assert.equal(isAllowedRemoteRequest({ method: 'tools/call', params: { name: 'readonly_close_position' } }), false);
  assert.equal(isAllowedRemoteRequest({ method: 'tools/call', params: { name: 'get_candles_latest' } }), false);
  assert.equal(isAllowedRemoteRequest([{ method: 'ping' }]), false);
  assert.equal(isStrippedChildEnvKey('MT5_MCP_REMOTE_TOKEN'), true);
  assert.equal(isStrippedChildEnvKey('MT5_MCP_REMOTE_URL'), true);
});
