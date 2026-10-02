import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { startDeferredReadOnlyProxy, startSetupErrorServer, isReadOnlyMt5Tool } from './readonly_mcp_proxy.mjs';
import { resolveDemoCredentials, isStrippedChildEnvKey } from './mt5_demo_credentials.mjs';
import { createRemoteHttpChild, resolveRemoteClientConfig } from './mt5_remote_bridge.mjs';
import { loadWorkspaceEnv, workspaceRoot } from './workspace_env.mjs';

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

const { envFile, env } = loadWorkspaceEnv();

// Setup problems keep the MCP connected in a diagnostic mode (one read-only
// mt5_setup_status tool) instead of exiting, which clients only show as
// "Connection closed".
function setupError(reason) {
  console.error(`MT5 MCP setup incomplete: ${reason}`);
  startSetupErrorServer({ reason });
}

const credentials = resolveDemoCredentials(env);
if (env.MT5_MCP_REMOTE_URL) {
  // Remote mode (e.g. a Linux cloud session): MT5 runs on the Windows PC, which serves
  // this same launcher via serve_mt5_mcp_remote.mjs. No MT5 credentials are needed here.
  const remote = resolveRemoteClientConfig(env);
  if (!remote.ok) {
    setupError(`${remote.error} (remote mode: MT5_MCP_REMOTE_URL is set)`);
  } else {
    console.error(`MT5 MCP: connecting read-only to remote MT5 MCP at ${new URL(remote.url).host}.`);
    startDeferredReadOnlyProxy({
      child: createRemoteHttpChild({ url: remote.url, token: remote.token }),
      allowTool: isReadOnlyMt5Tool, serverName: 'mt5ReadOnly',
      startupTimeoutMs: Number(env.MT5_MCP_STARTUP_TIMEOUT_MS) > 0 ? Number(env.MT5_MCP_STARTUP_TIMEOUT_MS) : 20000,
      failureHint: 'Check that serve_mt5_mcp_remote.mjs is running on the Windows PC, the tunnel URL, ' +
        'MT5_MCP_REMOTE_TOKEN, and that this environment\'s network policy allows the tunnel host.'
    });
  }
} else if (!credentials.ok) {
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

  // metatrader-mcp-server logs in to MT5 before answering `initialize`; the deferred
  // proxy answers the handshake itself so a slow or failed login cannot time it out.
  const startupTimeoutMs = Number(env.MT5_MCP_STARTUP_TIMEOUT_MS) > 0 ? Number(env.MT5_MCP_STARTUP_TIMEOUT_MS) : 20000;
  startDeferredReadOnlyProxy({
    child, allowTool: isReadOnlyMt5Tool, serverName: 'mt5ReadOnly', startupTimeoutMs,
    failureHint: 'Run `node web/scripts/check_mt5_mcp.mjs` for a setup diagnosis.'
  });
}
