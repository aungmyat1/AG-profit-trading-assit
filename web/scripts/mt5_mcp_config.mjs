import { existsSync, readFileSync } from 'node:fs';

export function parseEnvFile(path) {
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

// A client that does not support a variable syntax (e.g. VS Code `${input:...}`
// in Claude Code's .mcp.json) passes it through literally. Treat such values as
// unset so they never reach the terminal as credentials or mask local .env values.
export const isUnresolvedPlaceholder = value => typeof value === 'string' && /^\$\{[^}]*\}$/.test(value.trim());

export function withoutUnresolvedPlaceholders(env) {
  return Object.fromEntries(Object.entries(env).filter(([, value]) => !isUnresolvedPlaceholder(value)));
}

export const MT5_DEMO_ALIASES = {
  account: ['VANTAGE-DEMO-LOGIN', 'VANTAGE_DEMO_LOGIN', 'VANTAGE_DEMO_ACCOUNT_ID', 'MT5_ACCOUNT_ID', 'MT5_LOGIN'],
  password: ['VANTAGE-DEMO_PASSWORD', 'VANTAGE-DEMO-PASSWORD', 'VANTAGE_DEMO_PASSWORD', 'MT5_PASSWORD'],
  server: ['VANTAGE-DEMO-SERVER', 'VANTAGE-DEMO_SERVER', 'VANTAGE_DEMO_SERVER', 'MT5_SERVER'],
};

const pick = (env, keys) => keys.map(key => env[key]).find(value => value && !isUnresolvedPlaceholder(value));

export function resolveMt5DemoConfig(env) {
  const account = pick(env, MT5_DEMO_ALIASES.account);
  const password = pick(env, MT5_DEMO_ALIASES.password);
  const server = pick(env, MT5_DEMO_ALIASES.server);
  const missing = [];

  if (!account) missing.push('VANTAGE-DEMO-LOGIN');
  if (!password) missing.push('VANTAGE-DEMO_PASSWORD');
  if (!server) missing.push('VANTAGE-DEMO-SERVER');

  return { account, password, server, missing };
}

export function resolveMt5DemoServer(env) {
  const configured = pick(env, MT5_DEMO_ALIASES.server);
  return configured
    ? { server: configured, source: 'environment' }
    : { server: undefined, source: undefined };
}
