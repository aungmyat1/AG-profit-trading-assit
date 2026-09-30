// mcp_client_lock.mjs -- owner lock for the MT5 MCP client registrations.
//
// Owner decision (2026-09-30): every client (Claude Code .mcp.json, VS Code
// .vscode/mcp.json, Claude Desktop, Codex) registers exactly ONE MT5 server,
// "mt5ReadOnly", launched through web/scripts/start_mt5_mcp.mjs (VT Markets demo,
// read-only tool allowlist). No raw metatrader-mcp-server, HTTP MT5 bridge, or other
// broker/trading MCP may sit beside it. Changing this lock requires an owner-reviewed
// change to this file (see .github/CODEOWNERS).
// Pure functions only: nothing here writes config, spawns, or touches the network.

export const LOCKED_SERVER = 'mt5ReadOnly';
export const LAUNCHER = 'start_mt5_mcp.mjs';
// Server names/commands that indicate an MT5 or trading MCP other than the locked one.
const TRADING_PATTERN = /metatrader|mt5|mtx|mbt|bybit|binance|broker|trading/i;

const describe = server => [server?.command, ...(server?.args || []), server?.url].filter(Boolean).join(' ');

// servers: { name: { command, args, url } }. workspace=true means the file is owned by
// this repo and must contain nothing but the locked server.
export function inspectLockedServers(servers, { workspace = false, requireAbsolute = false } = {}) {
  const problems = [];
  const entries = Object.entries(servers || {});
  const locked = servers?.[LOCKED_SERVER];
  if (!locked) {
    problems.push(`"${LOCKED_SERVER}" is not registered`);
  } else {
    const script = (locked.args || []).find(arg => arg.replace(/\\/g, '/').endsWith(`web/scripts/${LAUNCHER}`));
    if (!script) problems.push(`"${LOCKED_SERVER}" does not launch web/scripts/${LAUNCHER}`);
    else if (requireAbsolute && !/^([A-Za-z]:[\\/]|\/|\\\\)/.test(script)) problems.push(`"${LOCKED_SERVER}" script path "${script}" must be absolute`);
    if (locked.url) problems.push(`"${LOCKED_SERVER}" must be a local stdio server, not ${locked.url}`);
  }
  for (const [name, server] of entries) {
    if (name === LOCKED_SERVER) continue;
    if (workspace) problems.push(`unexpected server "${name}" (${describe(server)})`);
    else if (TRADING_PATTERN.test(name) || TRADING_PATTERN.test(describe(server))) {
      problems.push(`unapproved trading/MT5 server "${name}" (${describe(server)})`);
    }
  }
  return { ok: problems.length === 0, problems };
}

// Minimal reader for Codex ~/.codex/config.toml [mcp_servers.<name>] tables:
// enough to recover command, args and url; other keys are ignored.
export function parseCodexMcpServers(toml) {
  const servers = {};
  let current = null;
  const value = raw => {
    const v = raw.trim();
    if (v.startsWith('[')) return [...v.matchAll(/'([^']*)'|"((?:[^"\\]|\\.)*)"/g)].map(m => m[1] ?? JSON.parse(`"${m[2]}"`));
    if (v.startsWith("'")) return v.slice(1, v.lastIndexOf("'"));
    if (v.startsWith('"')) return JSON.parse(v.slice(0, v.lastIndexOf('"') + 1));
    return v;
  };
  for (const line of String(toml).split(/\r?\n/)) {
    const table = line.match(/^\s*\[([^\]]+)\]\s*$/);
    if (table) {
      const m = table[1].match(/^mcp_servers\.("([^"]+)"|'([^']+)'|[^.]+)$/);
      current = m ? (servers[m[2] ?? m[3] ?? m[1]] = {}) : null;
      continue;
    }
    const kv = current && line.match(/^\s*(command|args|url)\s*=\s*(.+)$/);
    if (kv) current[kv[1]] = value(kv[2]);
  }
  return servers;
}
