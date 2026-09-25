// check_mt5_mcp.mjs -- read-only diagnostic for the MetaTrader MCP setup.
// Run from the project root:  node web/scripts/check_mt5_mcp.mjs
// It never prints passwords, never places orders, and never starts MT5.
import { existsSync, readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { homedir } from 'node:os';

const results = [];
const add = (ok, name, detail = '') => {
  results.push({ ok, name, detail });
  console.log(`${ok === true ? '[ OK ]' : ok === false ? '[FAIL]' : '[WARN]'} ${name}${detail ? ' -- ' + detail : ''}`);
};

// 1. Node version
const major = Number(process.versions.node.split('.')[0]);
add(major >= 18, 'Node >= 18', `found ${process.versions.node}`);

// 2. .env in the working directory (the launcher reads process.cwd()/.env)
const envPath = resolve(process.cwd(), '.env');
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
  add(false, '.env found', `no .env in ${process.cwd()} -- Claude Desktop may start the server from a different folder`);
}

// 3. Credential aliases, same lists as start_mt5_mcp.mjs (presence only, values hidden)
const aliases = {
  MT5_ACCOUNT_ID: ['VANTAGE-DEMO-LOGIN', 'VANTAGE_DEMO_LOGIN', 'MT5_ACCOUNT_ID', 'VANTAGE_DEMO_ACCOUNT_ID', 'MT5_LOGIN'],
  MT5_PASSWORD: ['VANTAGE_DEMO_PASSWORD', 'MT5_PASSWORD', 'VANTAGE-DEMO_PASSWORD'],
  MT5_SERVER: ['VANTAGE_DEMO_SERVER', 'MT5_SERVER', 'VANTAGE-DEMO_SERVER'],
};
for (const [canon, keys] of Object.entries(aliases)) {
  const hit = keys.find((k) => env[k]);
  add(!!hit, `credential ${canon}`, hit ? `set via ${hit} (value hidden)` : `none of: ${keys.join(', ')}`);
}

// 4. Live-account variables should not be present in the demo env
const liveKeys = ['VANTAGE-LIVE-PASSWORD', 'VANTAGE-LIVE', 'VANTAGE-SERVER'].filter((k) => env[k]);
add(liveKeys.length ? null : true, 'live credentials absent from env', liveKeys.length ? `present: ${liveKeys.join(', ')} (launcher strips them, keep it that way)` : '');

// 5. The metatrader command
const command = env.MT5_MCP_COMMAND || 'metatrader';
const isWin = process.platform === 'win32';
const which = spawnSync(isWin ? 'where' : 'which', [command], { encoding: 'utf8', shell: isWin });
if (which.status === 0) {
  add(true, `command "${command}" on PATH`, which.stdout.trim().split(/\r?\n/)[0]);
} else if (existsSync(command)) {
  add(true, `command "${command}" exists as a path`);
} else {
  add(false, `command "${command}" on PATH`, 'not found -- install it or set MT5_MCP_COMMAND to the full path');
}

// 6. Is terminal64.exe running? (Windows only)
if (isWin) {
  const t = spawnSync('tasklist', ['/FI', 'IMAGENAME eq terminal64.exe', '/FO', 'CSV', '/NH'], { encoding: 'utf8' });
  const running = /terminal64\.exe/i.test(t.stdout || '');
  add(running, 'MT5 terminal64.exe running', running ? '' : 'open MT5 and log in to the DEMO account, then wait ~30s');
} else {
  add(null, 'MT5 terminal running', 'skipped (not Windows)');
}

// 7. Claude Desktop config -- is the entry there and does it look sane?
const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming');
const cfgPath = join(appData, 'Claude', 'claude_desktop_config.json');
if (existsSync(cfgPath)) {
  try {
    const cfg = JSON.parse(readFileSync(cfgPath, 'utf8'));
    const servers = cfg.mcpServers || {};
    const names = Object.keys(servers);
    const mt = names.filter((n) => /mt5|metatrader|mtx/i.test(n));
    add(mt.length > 0, 'Claude Desktop config has an MT5 entry', mt.length ? mt.join(', ') : `servers present: ${names.join(', ') || 'none'}`);
    for (const n of mt) {
      const s = servers[n];
      const cmd = s.command || '(missing command)';
      add(!!s.command, `entry "${n}" command`, `${cmd} ${(s.args || []).join(' ')}`);
      if (s.env) add(true, `entry "${n}" env keys`, Object.keys(s.env).join(', ') + ' (values hidden)');
    }
    if (mt.length > 1) add(null, 'multiple MT5 servers registered', 'two servers (e.g. MTX and MBT) can collide; keep one');
  } catch (e) {
    add(false, 'claude_desktop_config.json is valid JSON', e.message);
  }
} else {
  add(null, 'claude_desktop_config.json', `not found at ${cfgPath}`);
}

// Summary
const fails = results.filter((r) => r.ok === false);
console.log('\n' + (fails.length ? `${fails.length} problem(s). Fix the first [FAIL] above, then re-run.` : 'No hard failures. If tools are still missing, fully quit Claude Desktop and start a NEW conversation.'));
console.log('Reminder: account_type from the API says "real" even on demo. Check the MT5 title bar for the "Demo Account" label.');
process.exitCode = fails.length ? 1 : 0;
