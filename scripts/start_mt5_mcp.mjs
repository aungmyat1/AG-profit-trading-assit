import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';

const envPath = resolve(process.cwd(), '.env');

if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const separator = trimmed.indexOf('=');
    if (separator < 1) continue;

    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = value;
  }
}

const aliases = {
  MT5_ACCOUNT_ID: ['VANTAGE-DEMO-LOGIN', 'VANTAGE_DEMO_LOGIN', 'MT5_ACCOUNT_ID', 'VANTAGE_DEMO_ACCOUNT_ID', 'MT5_LOGIN'],
  MT5_PASSWORD: ['VANTAGE_DEMO_PASSWORD', 'MT5_PASSWORD', 'VANTAGE-DEMO_PASSWORD'],
  MT5_SERVER: ['VANTAGE_DEMO_SERVER', 'MT5_SERVER', 'VANTAGE-DEMO_SERVER']
};

for (const [canonical, keys] of Object.entries(aliases)) {
  const value = keys.map(key => process.env[key]).find(Boolean);
  if (value) process.env[canonical] = value;
}

const command = process.env.MT5_MCP_COMMAND || 'metatrader';
const childEnv = { ...process.env };
delete childEnv['VANTAGE-LIVE-PASSWORD'];
delete childEnv['VANTAGE-LIVE'];
delete childEnv['VANTAGE-SERVER'];
const child = spawn(command, process.argv.slice(2), {
  env: childEnv,
  stdio: 'inherit'
});

child.on('error', error => {
  console.error(`Unable to start MT5 MCP command "${command}": ${error.message}`);
  process.exitCode = 1;
});

child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});