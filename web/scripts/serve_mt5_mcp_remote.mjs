// Serve the read-only MT5 Demo MCP over HTTP for a remote client (e.g. a Claude Code
// cloud session). Run on the Windows PC where MT5 is open and logged in to the demo
// account:
//
//   node web/scripts/serve_mt5_mcp_remote.mjs
//
// It runs the normal local launcher (start_mt5_mcp.mjs: DEMO-only credentials, read-only
// tool allowlist) as its single child and accepts POST /mcp with
// `Authorization: Bearer <MT5_MCP_REMOTE_TOKEN>`. It binds 127.0.0.1 by default; publish
// it only through an HTTPS tunnel. See docs/setup/MT5_MCP_SETUP.md "Remote access".
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { createRemoteMcpServer, resolveRemoteServerConfig, REMOTE_PATH } from './mt5_remote_bridge.mjs';
import { loadWorkspaceEnv, workspaceRoot } from './workspace_env.mjs';

const { env } = loadWorkspaceEnv();
const config = resolveRemoteServerConfig(env);
if (!config.ok) {
  console.error(`Remote MT5 MCP not started: ${config.error} Set it in src/.env (never commit it).`);
  process.exit(1);
}

// The child must run in local mode and must not see the remote token.
const childEnv = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^MT5_MCP_REMOTE_/i.test(key)));
childEnv.MT5_MCP_REMOTE_URL = ''; // overrides any value in src/.env
const child = spawn(process.execPath, [join(workspaceRoot, 'web', 'scripts', 'start_mt5_mcp.mjs')], {
  cwd: workspaceRoot, env: childEnv, stdio: ['pipe', 'pipe', 'inherit']
});
child.on('exit', (code, signal) => {
  console.error(`MT5 MCP launcher exited (${signal || `code ${code}`}); stopping remote server.`);
  process.exit(code ?? 1);
});

const server = createRemoteMcpServer({ child, token: config.token, log: message => console.error(`Remote MT5 MCP: ${message}`) });
server.listen(config.port, config.host, () => {
  console.error(`Remote MT5 MCP listening on http://${config.host}:${config.port}${REMOTE_PATH} (read-only, bearer token required).`);
  if (!['127.0.0.1', 'localhost', '::1'].includes(config.host)) {
    console.error('WARNING: bound to a non-loopback address; prefer 127.0.0.1 behind an HTTPS tunnel.');
  }
});
