import { spawn, spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { startReadOnlyProxy, isPublicBybitMarketTool } from './readonly_mcp_proxy.mjs';

// This workspace exposes Bybit's public market-data tools only. Do not inherit
// API credentials from shell/user environments: the package also contains
// authenticated account and order tools. Testnet is forced even if a parent
// process was configured for mainnet.
const childEnv = { ...process.env, BYBIT_TESTNET: 'true' };
for (const key of Object.keys(childEnv)) {
  if (/^BYBIT_(API_KEY|API_SECRET|API_PRIVATE_KEY_PATH|PAPER_)/i.test(key)) delete childEnv[key];
}

// Official package (github.com/bybit-exchange/trading-mcp). Pinned instead of the
// README's @latest so tool names reviewed by the read-only allowlist cannot drift.
const packageSpec = 'bybit-official-trading-server@2.1.22';
const npxPath = process.platform === 'win32'
  ? spawnSync('where.exe', ['npx.cmd'], { encoding: 'utf8' }).stdout?.split(/\r?\n/).find(path => path.trim().toLowerCase().endsWith('npx.cmd'))?.trim() ||
    join(process.env.ProgramFiles || 'C:\\Program Files', 'nodejs', 'npx.cmd')
  : 'npx';
if (!npxPath) {
  console.error('Unable to locate npx.cmd; verify Node.js/npm are installed and available on PATH.');
  process.exit(1);
}
const child = spawn(npxPath, ['-y', packageSpec], { env: childEnv, stdio: ['pipe', 'pipe', 'inherit'], shell: false });

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