import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { startReadOnlyProxy, isPublicBybitMarketTool } from './readonly_mcp_proxy.mjs';

// This workspace exposes Bybit's public market-data tools only. Do not inherit
// API credentials from shell/user environments: the package also contains
// authenticated account and order tools. Testnet is forced even if a parent
// process was configured for mainnet.
const childEnv = { ...process.env, BYBIT_TESTNET: 'true' };
for (const key of Object.keys(childEnv)) {
  if (/^BYBIT_(API_KEY|API_SECRET|API_PRIVATE_KEY_PATH|PAPER_)/i.test(key)) delete childEnv[key];
}

const packageSpec = 'bybit-official-trading-server@2.1.22';
// Node refuses to spawn .cmd/.bat files without a shell (CVE-2024-27980), so on
// Windows run npm's bundled npx-cli.js with the current node binary instead of npx.cmd.
const npxCli = join(dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npx-cli.js');
const [npxCommand, npxArgs] = process.platform === 'win32'
  ? [process.execPath, [npxCli]]
  : ['npx', []];
if (process.platform === 'win32' && !existsSync(npxCli)) {
  console.error('Unable to locate npm\'s npx-cli.js next to node.exe; verify the Node.js/npm installation.');
  process.exit(1);
}
const child = spawn(npxCommand, [...npxArgs, '-y', packageSpec], { env: childEnv, stdio: ['pipe', 'pipe', 'inherit'], shell: false });

child.on('error', () => {
  console.error('Unable to start Bybit MCP; verify Node.js/npm and network access.');
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});

startReadOnlyProxy({
  child,
  allowTool: isPublicBybitMarketTool
});