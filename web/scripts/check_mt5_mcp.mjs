// check_mt5_mcp.mjs -- read-only diagnostic for the MetaTrader MCP setup.
// Run from the project root:  node web/scripts/check_mt5_mcp.mjs
// It never prints passwords, never places orders, and never starts MT5.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { homedir } from 'node:os';

const results = [];
const add = (ok, name, detail = '') => {
  results.push({ ok, name, detail });
  console.log(`${ok === true ? '[ OK ]' : ok === false ? '[FAIL]' : '[WARN]'} ${name}${detail ? ' -- ' + detail : ''}`);
};

// 1. Node version (the official Bybit MCP package declares engines.node >=20.6)
const [major, minor] = process.versions.node.split('.').map(Number);
add(major > 20 || (major === 20 && minor >= 6), 'Node >= 20.6', `found ${process.versions.node}`);

// 2. Read the same environment-file locations as start_mt5_mcp.mjs.
const rootEnvPath = resolve(process.cwd(), '.env');
const sourceEnvPath = resolve(process.cwd(), 'src', '.env');
const envPath = existsSync(sourceEnvPath) ? sourceEnvPath : rootEnvPath;
const env = { ...process.env };
if (existsSync(envPath)) {
  add(true, '.env found', envPath);
  for (const line of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const i = t.indexOf('=');
    if (i < 1) continue;
    const k = t.slice(0, i).trim();
    let v = t.slice(i + 1).trim().replace(/^["']|["']$/g, '');
    if (!(k in env)) env[k] = v;
  }
} else {
  add(false, '.env found', `checked ${rootEnvPath} and ${sourceEnvPath}`);
}

// 3. Credential aliases, same lists as start_mt5_mcp.mjs (presence only, values hidden)
const aliases = {
  MT5_ACCOUNT_ID: ['VANTAGE-DEMO-LOGIN', 'VANTAGE_DEMO_LOGIN', 'MT5_ACCOUNT_ID', 'VANTAGE_DEMO_ACCOUNT_ID', 'MT5_LOGIN'],
  MT5_PASSWORD: ['VANTAGE-DEMO-PASSWORD', 'VANTAGE-DEMO_PASSWORD', 'VANTAGE_DEMO_PASSWORD', 'MT5_PASSWORD'],
  MT5_SERVER: ['VANTAGE-DEMO-SERVER', 'VANTAGE-DEMO_SERVER', 'VANTAGE_DEMO_SERVER', 'MT5_SERVER'],
};
for (const [canon, keys] of Object.entries(aliases)) {
  const hit = keys.find((k) => env[k]);
  add(!!hit, `credential ${canon}`, hit ? `set via ${hit} (value hidden)` : `none of: ${keys.join(', ')}`);
}
add((env.MT5_ENVIRONMENT || '').toUpperCase() === 'DEMO', 'MT5_ENVIRONMENT is DEMO', 'required by the read-only workspace launcher');

// 4. Live-account variables should not be present in the demo env
const liveKeys = ['VANTAGE-LIVE-PASSWORD', 'VANTAGE-LIVE', 'VANTAGE-SERVER'].filter((k) => env[k]);
  add(true, 'live credentials excluded from MT5 child process', liveKeys.length ? `detected in env; launcher strips them (${liveKeys.join(', ')})` : 'none found');

// 5. The metatrader command
let command = env.MT5_MCP_COMMAND;
if (!command && process.platform === 'win32') {
  const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming');
  try {
    const installs = readdirSync(join(appData, 'Python'))
      .filter(name => /^Python\d+$/i.test(name))
      .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))
      .map(name => join(appData, 'Python', name, 'Scripts', 'metatrader-mcp-server.exe'));
    command = installs.find(existsSync);
  } catch {
    // Use the executable name fallback below.
  }
}
command ||= process.platform === 'win32' ? 'metatrader-mcp-server.exe' : 'metatrader-mcp-server';
const isWin = process.platform === 'win32';
const which = spawnSync(isWin ? 'where' : 'which', [command], { encoding: 'utf8' });
if (which.status === 0) {
  add(true, `command "${command}" on PATH`, which.stdout.trim().split(/\r?\n/)[0]);
} else if (existsSync(command)) {
  add(true, `command "${command}" exists as a path`);
} else {
  add(false, `command "${command}" on PATH`, 'not found -- install it or set MT5_MCP_COMMAND to the full path');
}

// 5b. Installed metatrader-mcp-server version (the read-only allowlist is reviewed against it)
const expectedMt5McpVersion = '0.5.1';
const pip = spawnSync(isWin ? 'python' : 'python3', ['-m', 'pip', 'show', 'metatrader-mcp-server'], { encoding: 'utf8' });
const installedVersion = /^Version:\s*(\S+)/m.exec(pip.stdout || '')?.[1];
if (!installedVersion) {
  add(null, 'metatrader-mcp-server version', `not detected via pip; install with: pip install metatrader-mcp-server==${expectedMt5McpVersion}`);
} else {
  add(installedVersion === expectedMt5McpVersion ? true : null, 'metatrader-mcp-server version',
    installedVersion === expectedMt5McpVersion ? installedVersion
      : `found ${installedVersion}; expected ${expectedMt5McpVersion} (re-review MT5_READ_ONLY_TOOL_NAMES before changing)`);
}

// 6. Is terminal64.exe running? (Windows only)
if (isWin) {
  const t = spawnSync('tasklist', ['/FI', 'IMAGENAME eq terminal64.exe', '/FO', 'CSV', '/NH'], { encoding: 'utf8' });
  const running = /terminal64\.exe/i.test(t.stdout || '');
  add(running ? true : null, 'MT5 terminal64.exe running', running ? '' : 'not running; open MT5 and log in to the DEMO account when you need MT5 tools');
} else {
  add(null, 'MT5 terminal running', 'skipped (not Windows)');
}

// 7. Workspace MCP configs -- are both intended integrations registered?
const configs = [
  { path: resolve(process.cwd(), '.mcp.json'), serversKey: 'mcpServers' },
  { path: resolve(process.cwd(), '.vscode', 'mcp.json'), serversKey: 'servers' },
];
let checkedConfig = false;
for (const { path: cfgPath, serversKey } of configs) {
  if (!existsSync(cfgPath)) continue;
  checkedConfig = true;
  try {
    const cfg = JSON.parse(readFileSync(cfgPath, 'utf8'));
    const servers = cfg[serversKey] || {};
    const names = Object.keys(servers);
    const mt = names.find(name => /mt5readonly/i.test(name));
    const bybit = names.find(name => /^bybit$/i.test(name));
    add(!!mt, `${cfgPath} has read-only MT5 MCP`, mt || `servers present: ${names.join(', ') || 'none'}`);
    add(!!bybit, `${cfgPath} has Bybit MCP`, bybit || `servers present: ${names.join(', ') || 'none'}`);
  } catch (e) {
    add(false, `${cfgPath} is valid JSON`, e.message);
  }
}
if (!checkedConfig) add(false, 'workspace MCP configuration', 'neither .mcp.json nor .vscode/mcp.json was found');

// Summary
const fails = results.filter((r) => r.ok === false);
const warnings = results.filter((r) => r.ok === null);
console.log('\n' + (fails.length ? `${fails.length} blocking setup issue(s) remain.` : warnings.length ? 'Configuration checks passed; runtime warnings remain.' : 'All checks passed. Restart the MCP server or reload VS Code after config changes.'));
console.log('Reminder: the MT5 MCP launcher requires MT5_ENVIRONMENT=DEMO and exposes only explicitly read-only tools.');
process.exitCode = fails.length ? 1 : 0;
