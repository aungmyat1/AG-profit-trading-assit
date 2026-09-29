import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { startReadOnlyProxy, startSetupErrorServer, isReadOnlyMt5Tool } from './readonly_mcp_proxy.mjs';
import { resolveDemoCredentials, isStrippedChildEnvKey } from './mt5_demo_credentials.mjs';

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

// Setup problems keep the MCP connected in a diagnostic mode (one read-only
// mt5_setup_status tool) instead of exiting, which clients only show as
// "Connection closed".
function setupError(reason) {
  console.error(`MT5 MCP setup incomplete: ${reason}`);
  startSetupErrorServer({ reason });
}

const credentials = resolveDemoCredentials(env);
if (!credentials.ok) {
  setupError(`${credentials.error}${envFile ? ` (env file: ${envFile})` : ' (no src/.env or .env found)'}`);
} else if (process.platform !== 'win32' && !env.MT5_MCP_COMMAND) {
  // metatrader-mcp-server needs the Windows-only MetaTrader5 Python package and a
  // running terminal64.exe; a Linux/macOS host (e.g. a cloud container) cannot run it.
  setupError(`MetaTrader 5 needs Windows; this host is ${process.platform}. Run the MCP on the Windows PC ` +
    `where MT5 is open and logged in to ${credentials.label} (or set MT5_MCP_COMMAND to a compatible bridge).`);
} else {
  const command = findServerCommand(env);
  const args = [
    '--login', credentials.login, '--password', credentials.password, '--server', credentials.server,
    '--transport', 'stdio'
  ];
  if (env.MT5_TERMINAL_PATH) args.push('--path', env.MT5_TERMINAL_PATH);

  // Credentials are passed only to the installed MT5 MCP executable (its CLI has no
  // environment-variable credential interface). Never log the command or its args.
  const childEnv = Object.fromEntries(
    Object.entries(process.env).filter(([key]) => !isStrippedChildEnvKey(key)));
  console.error(`MT5 MCP: connecting read-only to ${credentials.label} (${credentials.server}).`);
  const child = spawn(command, args, { cwd: workspaceRoot, env: childEnv, stdio: ['pipe', 'pipe', 'inherit'] });

  child.on('error', () => {
    console.error('Unable to start the configured MT5 MCP executable; verify MT5_MCP_COMMAND or install path ' +
      '(pip install metatrader-mcp-server==0.5.1).');
    process.exitCode = 1;
  });
  child.on('exit', (code, signal) => {
    process.exitCode = code ?? (signal ? 1 : 0);
  });

  startReadOnlyProxy({ child, allowTool: isReadOnlyMt5Tool });
}
