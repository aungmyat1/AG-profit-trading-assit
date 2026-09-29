import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import test from 'node:test';
import {
  buildServerEntry, desktopConfigPath, inspectDesktopEntry, mergeDesktopConfig, SERVER_NAME
} from '../scripts/claude_desktop_config.mjs';

const workspaceRoot = resolve(import.meta.dirname, '../..');
const entry = buildServerEntry({ nodePath: process.execPath, workspaceRoot });

test('builds an absolute-path entry with no credentials', () => {
  assert.equal(entry.command, process.execPath);
  assert.equal(entry.args.length, 1);
  assert.match(entry.args[0], /start_mt5_mcp\.mjs$/);
  assert.equal(entry.env, undefined);
});

test('merge preserves other servers and keys without mutating input', () => {
  const existing = { preferences: { a: 1 }, mcpServers: { other: { command: 'x' } } };
  const { config, warnings } = mergeDesktopConfig(existing, entry);
  assert.deepEqual(Object.keys(config.mcpServers).sort(), ['other', SERVER_NAME].sort());
  assert.deepEqual(config.preferences, { a: 1 });
  assert.equal(existing.mcpServers[SERVER_NAME], undefined);
  assert.deepEqual(warnings, []);
});

test('merge replaces a stale relative entry and warns about execution servers', () => {
  const existing = { mcpServers: { [SERVER_NAME]: { command: 'node', args: ['web/scripts/start_mt5_mcp.mjs'] }, mtx: {} } };
  const { config, warnings } = mergeDesktopConfig(existing, entry);
  assert.deepEqual(config.mcpServers[SERVER_NAME], entry);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /mtx/);
});

test('inspect flags missing and relative entries and accepts the built entry', () => {
  assert.equal(inspectDesktopEntry({}).ok, false);
  const relative = inspectDesktopEntry({ mcpServers: { [SERVER_NAME]: { command: 'node', args: ['web/scripts/start_mt5_mcp.mjs'] } } });
  assert.equal(relative.ok, false);
  assert.match(relative.detail, /relative/);
  assert.equal(inspectDesktopEntry({ mcpServers: { [SERVER_NAME]: entry } }).ok, true);
});

test('config path lives under APPDATA\\Claude', () => {
  assert.match(desktopConfigPath({ APPDATA: '/appdata' }), /appdata[\\/]Claude[\\/]claude_desktop_config\.json$/);
});
