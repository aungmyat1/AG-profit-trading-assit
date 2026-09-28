import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { startReadOnlyProxy } from './readonly_mcp_proxy.mjs';
import { parseEnvFile, resolveMt5DemoConfig, resolveMt5DemoServer, withoutUnresolvedPlaceholders } from './mt5_mcp_config.mjs';

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
const env = { ...fileEnv, ...withoutUnresolvedPlaceholders(process.env) };

if ((env.MT5_ENVIRONMENT || '').toUpperCase() !== 'DEMO') {
  console.error('MT5 MCP stopped: MT5_ENVIRONMENT must be explicitly set to DEMO.');
  process.exit(1);
}

const terminalPath = env.MT5_TERMINAL_PATH || '';
const credentials = resolveMt5DemoConfig(env);
const serverResolution = resolveMt5DemoServer(env);
const missing = [...credentials.missing.filter(key => key !== 'VANTAGE-DEMO-SERVER')];
if (!serverResolution.server) missing.push('VANTAGE-DEMO-SERVER');
if (missing.length) {
  console.error(`MT5 MCP stopped: missing ${missing.join(', ')}${envFile ? ` in ${envFile}` : ' in the process environment'}. Add these locally; never put credentials in MCP JSON.`);
  process.exit(1);
}
const { account, password } = credentials;
const { server } = serverResolution;

const command = findServerCommand(env);
const args = [
  '--login', String(account), '--password', password, '--server', server,
  '--transport', 'stdio'
];
if (terminalPath) args.push('--path', terminalPath);

// Credentials are passed only to the installed MT5 MCP executable (its CLI has no
// environment-variable credential interface). Never log the command or its args.
const childEnv = { ...process.env };
for (const key of Object.keys(childEnv)) {
  if (/^(VANTAGE-LIVE|VANTAGE_LIVE|BYBIT_API_|BYBIT_PAPER_)/i.test(key)) delete childEnv[key];
}
for (const key of Object.keys(childEnv)) {
  if (/^(VANTAGE[-_]DEMO)/i.test(key)) delete childEnv[key];
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