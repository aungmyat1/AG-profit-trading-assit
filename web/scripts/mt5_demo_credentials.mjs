// Demo-account credential resolution for the read-only MT5 MCP launcher.
// Pure functions only: nothing here logs, spawns, or touches the network.

// Selectable demo brokers. VT Markets is the default demo account for the MCP.
// Keys are checked in order; the generic MT5_* aliases apply to whichever broker is
// selected. Vantage stays available only when MT5_DEMO_BROKER=VANTAGE is explicit.
export const DEMO_BROKERS = {
  VTMARKETS: {
    label: 'VT Markets Demo',
    // VTMARKET-* (no S) is the spelling used in the owner's src/.env.
    login: ['VTMARKETS-DEMO-LOGIN', 'VTMARKETS_DEMO_LOGIN', 'VTMARKETS_DEMO_ACCOUNT_ID', 'VTMARKET-DEMO-LOGIN', 'VTMARKET_DEMO_LOGIN'],
    password: ['VTMARKETS-DEMO-PASSWORD', 'VTMARKETS-DEMO_PASSWORD', 'VTMARKETS_DEMO_PASSWORD', 'VTMARKET-DEMO_PASSWORD', 'VTMARKET-DEMO-PASSWORD', 'VTMARKET_DEMO_PASSWORD'],
    server: ['VTMARKETS-DEMO-SERVER', 'VTMARKETS-DEMO_SERVER', 'VTMARKETS_DEMO_SERVER', 'VTMARKET-DEMO_SERVER', 'VTMARKET-DEMO-SERVER', 'VTMARKET_DEMO_SERVER'],
    serverPattern: /^VTMarkets-Demo/i
  },
  VANTAGE: {
    label: 'Vantage Markets Demo',
    login: ['VANTAGE-DEMO-LOGIN', 'VANTAGE_DEMO_LOGIN', 'VANTAGE_DEMO_ACCOUNT_ID'],
    password: ['VANTAGE-DEMO-PASSWORD', 'VANTAGE-DEMO_PASSWORD', 'VANTAGE_DEMO_PASSWORD'],
    server: ['VANTAGE-DEMO-SERVER', 'VANTAGE-DEMO_SERVER', 'VANTAGE_DEMO_SERVER'],
    serverPattern: /^Vantage[A-Za-z]*-Demo/i
  }
};

export const DEFAULT_DEMO_BROKER = 'VTMARKETS';
const GENERIC = { login: ['MT5_ACCOUNT_ID', 'MT5_LOGIN'], password: ['MT5_PASSWORD'], server: ['MT5_SERVER'] };

export function credentialAliases(brokerKey) {
  const broker = DEMO_BROKERS[brokerKey];
  return {
    login: [...broker.login, ...GENERIC.login],
    password: [...broker.password, ...GENERIC.password],
    server: [...broker.server, ...GENERIC.server]
  };
}

const firstSet = (env, keys) => keys.find(key => env[key]);

// Returns { ok: true, broker, label, login, password, server, sources } or
// { ok: false, error } with an error message that never contains a secret value.
export function resolveDemoCredentials(env) {
  if ((env.MT5_ENVIRONMENT || '').toUpperCase() !== 'DEMO') {
    return { ok: false, error: 'MT5_ENVIRONMENT must be explicitly set to DEMO.' };
  }
  const brokerKey = (env.MT5_DEMO_BROKER || DEFAULT_DEMO_BROKER).toUpperCase().replace(/[^A-Z]/g, '');
  const broker = DEMO_BROKERS[brokerKey];
  if (!broker) {
    return { ok: false, error: `MT5_DEMO_BROKER must be one of: ${Object.keys(DEMO_BROKERS).join(', ')}.` };
  }
  const aliases = credentialAliases(brokerKey);
  const sources = {
    login: firstSet(env, aliases.login),
    password: firstSet(env, aliases.password),
    server: firstSet(env, aliases.server)
  };
  const missing = Object.entries(sources).filter(([, key]) => !key).map(([field]) => field);
  if (missing.length) {
    return {
      ok: false,
      error: `${broker.label} credentials are incomplete (missing ${missing.join(', ')}); ` +
        `set ${missing.map(field => aliases[field][0]).join(', ')} in src/.env.`
    };
  }
  const server = env[sources.server];
  // Fail closed: the server name is the only reliable demo interlock (the MT5 API
  // reports account_type "real" on VT Markets demo accounts).
  if (!/demo/i.test(server) || !broker.serverPattern.test(server)) {
    return { ok: false, error: `${broker.label} server "${server}" is not a recognized demo server; refusing to connect.` };
  }
  const login = String(env[sources.login]).trim();
  if (!/^\d+$/.test(login)) {
    return { ok: false, error: `${broker.label} login must be the numeric MT5 account number (set via ${sources.login}).` };
  }
  return { ok: true, broker: brokerKey, label: broker.label, login, password: env[sources.password], server, sources };
}

// Env keys that must never reach the MT5 MCP child process.
export function isStrippedChildEnvKey(key) {
  return /^(VANTAGE|VTMARKETS?|BYBIT_API_|BYBIT_PAPER_|MT5_(PASSWORD|ACCOUNT_ID|LOGIN|SERVER|MCP_COMMAND))/i.test(key);
}
