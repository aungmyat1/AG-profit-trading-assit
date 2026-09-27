import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { startReadOnlyProxy } from './readonly_mcp_proxy.mjs';

function parseEnvFile(path) {
  const values = {};
  if (!existsSync(path)) return values;
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator < 1) continue;
    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function findServerCommand(env) {
  if (env.MT5_MCP_COMMAND) return env.MT5_MCP_COMMAND;
  const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming');
  const pythonRoot = join(appData, 'Python');
  try {
    const candidates = readdirSync(pythonRoot)
      .filter(name => /^Python\d+$/i.test(name))
      .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))
      .map(name => join(pythonRoot, name, 'Scripts', 'metatrader-mcp-server.exe'));
    const installed = candidates.find(existsSync);
    if (installed) return installed;
  } catch {
    // Fall through to PATH lookup below.
  }
  return process.platform === 'win32' ? 'metatrader-mcp-server.exe' : 'metatrader-mcp-server';
}

const workspaceRoot = resolve(import.meta.dirname, '../..');
const envFile = [join(workspaceRoot, 'src', '.env'), join(workspaceRoot, '.env')]
  .find(existsSync);
const fileEnv = envFile ? parseEnvFile(envFile) : {};
const env = { ...fileEnv, ...process.env };

if ((env.MT5_ENVIRONMENT || '').toUpperCase() !== 'DEMO') {
  console.error('MT5 MCP stopped: MT5_ENVIRONMENT must be explicitly set to DEMO.');
  process.exit(1);
}

const account = env['VANTAGE-DEMO-LOGIN'] || env.VANTAGE_DEMO_LOGIN ||
  env.VANTAGE_DEMO_ACCOUNT_ID || env.MT5_ACCOUNT_ID || env.MT5_LOGIN;
const password = env.VANTAGE_DEMO_PASSWORD || env.MT5_PASSWORD;
const server = env['VANTAGE-DEMO-SERVER'] || env.VANTAGE_DEMO_SERVER || env.MT5_SERVER;
if (!account || !password || !server) {
  console.error(`MT5 MCP stopped: demo credentials are incomplete${envFile ? ` in ${envFile}` : ''}.`);
  process.exit(1);
}

const command = findServerCommand(env);
const args = [
  '--login', String(account), '--password', password, '--server', server,
  '--transport', 'stdio'
];
if (env.MT5_TERMINAL_PATH) args.push('--path', env.MT5_TERMINAL_PATH);

// Credentials are passed only to the installed MT5 MCP executable (its CLI has no
// environment-variable credential interface). Never log the command or its args.
const childEnv = { ...process.env };
for (const key of Object.keys(childEnv)) {
  if (/^(VANTAGE-LIVE|VANTAGE_LIVE|BYBIT_API_|BYBIT_PAPER_)/i.test(key)) delete childEnv[key];
}
delete childEnv['VANTAGE-SERVER'];
delete childEnv.VANTAGE_SERVER;
delete childEnv.MT5_PASSWORD;
delete childEnv.MT5_ACCOUNT_ID;
delete childEnv.MT5_LOGIN;
delete childEnv.MT5_SERVER;
delete childEnv.MT5_MCP_COMMAND;
const child = spawn(command, args, { cwd: workspaceRoot, env: childEnv, stdio: ['pipe', 'pipe', 'inherit'] });

child.on('error', () => {
  console.error('Unable to start the configured MT5 MCP executable; verify MT5_MCP_COMMAND or install path.');
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});

startReadOnlyProxy({ child });