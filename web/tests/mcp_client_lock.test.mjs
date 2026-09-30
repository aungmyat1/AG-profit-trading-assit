import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import { LOCKED_SERVER, inspectLockedServers, parseCodexMcpServers } from '../scripts/mcp_client_lock.mjs';
import { MT5_READ_ONLY_TOOL_NAMES } from '../scripts/readonly_mcp_proxy.mjs';

const root = resolve(import.meta.dirname, '..', '..');
const readJson = path => JSON.parse(readFileSync(resolve(root, path), 'utf8'));

test('repo client configs register only the locked read-only MT5 server', () => {
  for (const [path, key] of [['.mcp.json', 'mcpServers'], ['.vscode/mcp.json', 'servers']]) {
    const servers = readJson(path)[key];
    assert.deepEqual(Object.keys(servers), [LOCKED_SERVER], path);
    assert.deepEqual(inspectLockedServers(servers, { workspace: true }), { ok: true, problems: [] }, path);
    assert.equal(servers[LOCKED_SERVER].env, undefined, `${path}: credentials come from src/.env, not client config`);
  }
});

test('read-only allowlist contains no order-capable tool', () => {
  for (const name of MT5_READ_ONLY_TOOL_NAMES) {
    assert.match(name, /^get_/, name);
    assert.doesNotMatch(name, /place|modify|close|cancel|send|buy|sell/i, name);
  }
});

test('flags extra, raw, or HTTP MT5 servers and relative Desktop/Codex paths', () => {
  const good = { command: 'C:\\node.exe', args: ['D:\\repo\\web\\scripts\\start_mt5_mcp.mjs'] };
  assert.equal(inspectLockedServers({ [LOCKED_SERVER]: good, github: { url: 'https://x' } }).ok, true);
  assert.equal(inspectLockedServers({ [LOCKED_SERVER]: good, github: { url: 'https://x' } }, { workspace: true }).ok, false);
  assert.equal(inspectLockedServers({ [LOCKED_SERVER]: good, metatrader: { command: 'metatrader-mcp-server.exe' } }).ok, false);
  assert.equal(inspectLockedServers({ [LOCKED_SERVER]: good, 'metatrader-2-2': { url: 'http://127.0.0.1:22346/mcp' } }).ok, false);
  assert.equal(inspectLockedServers({ [LOCKED_SERVER]: { command: 'node', args: ['web/scripts/start_mt5_mcp.mjs'] } }, { requireAbsolute: true }).ok, false);
  assert.equal(inspectLockedServers({}).ok, false);
});

test('parses Codex mcp_servers tables', () => {
  const servers = parseCodexMcpServers([
    '[mcp_servers.node_repl]', "command = 'C:\\x\\node_repl.exe'", 'args = []',
    '[mcp_servers.mt5ReadOnly]', 'command = "C:\\\\Program Files\\\\nodejs\\\\node.exe"',
    'args = ["D:\\\\ddev\\\\AG profit trading\\\\web\\\\scripts\\\\start_mt5_mcp.mjs"]',
    '[mcp_servers.mt5ReadOnly.env]', 'X = "1"', '[desktop]', 'command = "ignored"'
  ].join('\n'));
  assert.deepEqual(Object.keys(servers), ['node_repl', 'mt5ReadOnly']);
  assert.equal(servers.mt5ReadOnly.command, 'C:\\Program Files\\nodejs\\node.exe');
  assert.equal(inspectLockedServers(servers, { requireAbsolute: true }).ok, true);
});
