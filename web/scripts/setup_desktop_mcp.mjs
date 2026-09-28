// setup_desktop_mcp.mjs -- one-time setup of the Claude DESKTOP app MCP servers.
// Run:  node web/scripts/setup_desktop_mcp.mjs     (or double-click setup_desktop_mcp.cmd)
//
// What it does:
//   1. Pre-downloads the pinned Bybit MCP package so the desktop app does not
//      time out on first start.
//   2. Backs up claude_desktop_config.json (timestamped copy next to it).
//   3. Removes the unfiltered "metatrader" server (full trading tools) and
//      registers the workspace read-only launchers with ABSOLUTE paths:
//        bybit       -> web/scripts/start_bybit_mcp.mjs  (public market data only, testnet)
//        mt5ReadOnly -> web/scripts/start_mt5_mcp.mjs    (DEMO only, read-only tools)
//      All other servers and settings in the file are left untouched.
// It never prints credentials and never places orders.
import { existsSync, readFileSync, writeFileSync, copyFileSync, readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';

const BYBIT_PACKAGE = 'bybit-official-trading-server@2.1.22';
const scriptsDir = resolve(import.meta.dirname);
const workspaceRoot = resolve(scriptsDir, '..', '..');
const log = (tag, msg) => console.log(`[${tag}] ${msg}`);

// ---- 0. Node version (import.meta.dirname needs >= 20.11; Bybit package needs >= 20.6)
const [maj, min] = process.versions.node.split('.').map(Number);
if (maj < 20 || (maj === 20 && min < 11)) {
  log('FAIL', `Node ${process.versions.node} is too old; install Node 20.11+ and rerun.`);
  process.exit(1);
}

// ---- 1. Locate the desktop config (standard install, then Microsoft Store install)
const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming');
const localAppData = process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local');
const candidates = [join(appData, 'Claude', 'claude_desktop_config.json')];
try {
  for (const pkg of readdirSync(join(localAppData, 'Packages'))) {
    if (/^Claude_/i.test(pkg)) {
      candidates.push(join(localAppData, 'Packages', pkg, 'LocalCache', 'Roaming', 'Claude', 'claude_desktop_config.json'));
    }
  }
} catch { /* no Store packages */ }
// Microsoft Store installs may read a virtualized copy, so patch EVERY copy found.
const configPaths = candidates.filter(existsSync);
if (!configPaths.length) configPaths.push(candidates[0]);
for (const p of configPaths) log('INFO', `desktop config: ${p}${existsSync(p) ? '' : ' (will be created)'}`);

// ---- 2. Pre-download the Bybit package (server exits when stdin closes)
const npxCli = join(dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npx-cli.js');
const [cmd, pre] = process.platform === 'win32' ? [process.execPath, [npxCli]] : ['npx', []];
log('INFO', `pre-downloading ${BYBIT_PACKAGE} (first time can take a minute)...`);
const warm = spawnSync(cmd, [...pre, '-y', BYBIT_PACKAGE], {
  input: '', encoding: 'utf8', timeout: 300_000,
  env: Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^BYBIT_(API_KEY|API_SECRET|API_PRIVATE_KEY_PATH|PAPER_)/i.test(k))),
});
if (/started/i.test(`${warm.stdout}${warm.stderr}`)) log(' OK ', 'Bybit package cached; server starts correctly.');
else log('WARN', `Bybit warm-up did not confirm start (status ${warm.status}). Check network, then rerun.`);

// ---- 3. Back up and patch each config copy
for (const configPath of configPaths) {
  let config = {};
  if (existsSync(configPath)) {
    // Strip a UTF-8 BOM (Notepad adds one) before parsing.
    const raw = readFileSync(configPath, 'utf8').replace(/^\uFEFF/, '');
    try { config = JSON.parse(raw); } catch (e) {
      log('FAIL', `${configPath} is not valid JSON (${e.message}); left unchanged.`);
      process.exitCode = 1;
      continue;
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backup = `${configPath}.backup-${stamp}`;
    copyFileSync(configPath, backup);
    log(' OK ', `backup saved: ${backup}`);
  }
  config.mcpServers ||= {};
  const before = Object.keys(config.mcpServers);
  if (config.mcpServers.metatrader) {
    delete config.mcpServers.metatrader;
    log(' OK ', 'removed unfiltered "metatrader" server (had live order tools).');
  }
  config.mcpServers.bybit = {
    command: 'node',
    args: [join(scriptsDir, 'start_bybit_mcp.mjs')],
    env: { BYBIT_TESTNET: 'true' },
  };
  config.mcpServers.mt5ReadOnly = {
    command: 'node',
    args: [join(scriptsDir, 'start_mt5_mcp.mjs')],
    env: { MT5_ENVIRONMENT: 'DEMO' },
  };
  writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, 'utf8');
  log(' OK ', `servers before: ${before.join(', ') || 'none'}`);
  log(' OK ', `servers after:  ${Object.keys(config.mcpServers).join(', ')}`);
}

// ---- 4. Demo credential presence check (values never printed)
const envFile = [join(workspaceRoot, 'src', '.env'), join(workspaceRoot, '.env')].find(existsSync);
const envText = envFile ? readFileSync(envFile, 'utf8') : '';
const has = keys => keys.some(k => new RegExp(`^\\s*${k.replace(/[-]/g, '\\-')}\\s*=\\s*\\S`, 'm').test(envText));
const demo = {
  login: has(['VANTAGE-DEMO-LOGIN', 'VANTAGE_DEMO_LOGIN', 'VANTAGE_DEMO_ACCOUNT_ID', 'MT5_ACCOUNT_ID', 'MT5_LOGIN']),
  password: has(['VANTAGE-DEMO_PASSWORD', 'VANTAGE-DEMO-PASSWORD', 'VANTAGE_DEMO_PASSWORD', 'MT5_PASSWORD']),
  server: has(['VANTAGE-DEMO-SERVER', 'VANTAGE-DEMO_SERVER', 'VANTAGE_DEMO_SERVER', 'MT5_SERVER']),
};
for (const [k, ok] of Object.entries(demo)) {
  log(ok ? ' OK ' : 'WARN', `MT5 demo ${k} ${ok ? 'found' : 'MISSING'} in ${envFile || 'src/.env (file not found)'}`);
}
if (!has(['MT5_TERMINAL_PATH'])) {
  log('WARN', 'MT5_TERMINAL_PATH not set: mt5ReadOnly will log your running MT5 terminal into the DEMO account. Point it at a separate demo terminal64.exe to keep your live terminal untouched.');
}

console.log('\nDone. FULLY quit the Claude desktop app (tray icon -> Quit) and reopen it.');
