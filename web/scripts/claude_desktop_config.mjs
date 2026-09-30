// claude_desktop_config.mjs -- register the read-only MT5 MCP in Claude Desktop.
//
// Claude Desktop does not read this repository's .mcp.json. It reads
// %APPDATA%\Claude\claude_desktop_config.json and starts each server from its own
// working directory, so the workspace-relative "web/scripts/start_mt5_mcp.mjs" in
// .mcp.json fails there. This script writes an entry with absolute paths instead.
//
// Run on the Windows PC where MT5 is installed, from the project root:
//   node web/scripts/claude_desktop_config.mjs            (dry run: print the result)
//   node web/scripts/claude_desktop_config.mjs --write    (back up, then merge + save)
// Other servers in the file are preserved. No credentials are written: the launcher
// still reads them from src/.env.
import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const SERVER_NAME = 'mt5ReadOnly';
// Servers that must not sit next to the read-only MCP (see docs/setup/MT5_MCP_SETUP.md).
export const DISALLOWED_SERVERS = { mtx: 'MT5 execution server', mbt: 'quarantined MBT install' };

export function desktopConfigPath(env = process.env) {
  const appData = env.APPDATA || join(homedir(), 'AppData', 'Roaming');
  return join(appData, 'Claude', 'claude_desktop_config.json');
}

export function buildServerEntry({ nodePath, workspaceRoot }) {
  return {
    command: nodePath,
    args: [join(workspaceRoot, 'web', 'scripts', 'start_mt5_mcp.mjs')]
  };
}

// Returns { config, warnings }. Never mutates `existing`.
export function mergeDesktopConfig(existing, entry) {
  const config = structuredClone(existing && typeof existing === 'object' ? existing : {});
  config.mcpServers = { ...(config.mcpServers || {}), [SERVER_NAME]: entry };
  const warnings = Object.keys(config.mcpServers)
    .filter(name => DISALLOWED_SERVERS[name.toLowerCase()])
    .map(name => `"${name}" (${DISALLOWED_SERVERS[name.toLowerCase()]}) is registered; remove it by hand.`);
  return { config, warnings };
}

// Checks an existing Desktop config. Returns { ok, detail }.
export function inspectDesktopEntry(config) {
  const entry = config?.mcpServers?.[SERVER_NAME];
  if (!entry) return { ok: false, detail: `no "${SERVER_NAME}" server registered` };
  const script = (entry.args || []).find(arg => /start_mt5_mcp\.mjs$/.test(arg));
  if (!script) return { ok: false, detail: 'entry does not launch web/scripts/start_mt5_mcp.mjs' };
  if (!/^([A-Za-z]:[\\/]|\/|\\\\)/.test(script)) {
    return { ok: false, detail: `script path "${script}" is relative; Claude Desktop needs an absolute path` };
  }
  if (!existsSync(script)) return { ok: false, detail: `script path "${script}" does not exist` };
  return { ok: true, detail: `${entry.command} ${script}` };
}

function main(argv) {
  const write = argv.includes('--write');
  const workspaceRoot = resolve(import.meta.dirname, '../..');
  const path = desktopConfigPath();
  if (process.platform !== 'win32') {
    console.error(`[WARN] This host is ${process.platform}; MT5 and Claude Desktop's MT5 MCP need the Windows PC.`);
  }
  let existing = {};
  if (existsSync(path)) {
    try {
      existing = JSON.parse(readFileSync(path, 'utf8'));
    } catch (e) {
      console.error(`[FAIL] ${path} is not valid JSON (${e.message}); fix it by hand before merging.`);
      return 1;
    }
  }
  const { config, warnings } = mergeDesktopConfig(existing, buildServerEntry({ nodePath: process.execPath, workspaceRoot }));
  warnings.forEach(w => console.error(`[WARN] ${w}`));
  const text = JSON.stringify(config, null, 2) + '\n';
  if (!write) {
    console.log(`Dry run -- would write ${path}:\n${text}Re-run with --write to apply.`);
    return 0;
  }
  mkdirSync(dirname(path), { recursive: true });
  if (existsSync(path)) {
    const backup = `${path}.${new Date().toISOString().replace(/[:.]/g, '-')}.bak`;
    copyFileSync(path, backup);
    console.log(`[ OK ] backup: ${backup}`);
  }
  writeFileSync(path, text, 'utf8');
  console.log(`[ OK ] wrote "${SERVER_NAME}" to ${path}`);
  console.log('Next: fully quit Claude Desktop (tray icon -> Quit), reopen it, and start a NEW chat.');
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  process.exitCode = main(process.argv.slice(2));
}
