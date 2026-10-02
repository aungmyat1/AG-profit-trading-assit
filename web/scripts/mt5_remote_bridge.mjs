// Remote bridge for the read-only MT5 Demo MCP.
//
// MetaTrader 5 runs only on Windows, so a Linux client (e.g. a Claude Code cloud
// session) cannot start metatrader-mcp-server itself. The Windows PC running MT5 serves
// its existing read-only launcher (start_mt5_mcp.mjs) over HTTP with
// createRemoteMcpServer(); the remote client wraps that endpoint in a child-like object
// (createRemoteHttpChild) and hands it to the same startDeferredReadOnlyProxy used
// locally, so the tool names, read-only allowlist and setup-status fallback are
// identical on both sides. The allowlist is enforced on the server AND the client.
// Demo credentials never leave the Windows PC; the bearer token is never logged.
import { createHash, timingSafeEqual } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { createServer } from 'node:http';
import { PassThrough } from 'node:stream';
import { MT5_READ_ONLY_TOOL_NAMES, SETUP_STATUS_TOOL } from './readonly_mcp_proxy.mjs';

export const REMOTE_PATH = '/mcp';
export const DEFAULT_REMOTE_PORT = 8765;
export const MIN_TOKEN_LENGTH = 32;
const MAX_BODY_BYTES = 1024 * 1024;
const PREFIX = 'readonly_';
const ALLOWED_METHODS = new Set(['initialize', 'notifications/initialized', 'ping', 'tools/list', 'tools/call']);

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

function tokenError(token) {
  if (!token) return 'MT5_MCP_REMOTE_TOKEN is not set.';
  if (token.length < MIN_TOKEN_LENGTH) return `MT5_MCP_REMOTE_TOKEN must be at least ${MIN_TOKEN_LENGTH} characters.`;
  return '';
}

// Returns { ok: true, url, token } or { ok: false, error } (never echoes the token).
export function resolveRemoteClientConfig(env) {
  if ((env.MT5_ENVIRONMENT || '').toUpperCase() !== 'DEMO') {
    return { ok: false, error: 'MT5_ENVIRONMENT must be explicitly set to DEMO.' };
  }
  let url;
  try {
    url = new URL(env.MT5_MCP_REMOTE_URL);
  } catch {
    return { ok: false, error: 'MT5_MCP_REMOTE_URL is not a valid URL.' };
  }
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && LOCAL_HOSTS.has(url.hostname))) {
    return { ok: false, error: 'MT5_MCP_REMOTE_URL must use https:// (plain http is allowed only for localhost).' };
  }
  if (url.username || url.password) {
    return { ok: false, error: 'MT5_MCP_REMOTE_URL must not embed credentials; use MT5_MCP_REMOTE_TOKEN.' };
  }
  const error = tokenError(env.MT5_MCP_REMOTE_TOKEN || '');
  if (error) return { ok: false, error };
  return { ok: true, url: url.href, token: env.MT5_MCP_REMOTE_TOKEN };
}

// Returns { ok: true, host, port, token } or { ok: false, error }.
export function resolveRemoteServerConfig(env) {
  const error = tokenError(env.MT5_MCP_REMOTE_TOKEN || '');
  if (error) return { ok: false, error };
  const port = env.MT5_MCP_REMOTE_PORT ? Number(env.MT5_MCP_REMOTE_PORT) : DEFAULT_REMOTE_PORT;
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return { ok: false, error: 'MT5_MCP_REMOTE_PORT must be an integer between 1 and 65535.' };
  }
  // Loopback by default: expose it through an HTTPS tunnel, never a raw public port.
  return { ok: true, host: env.MT5_MCP_REMOTE_HOST || '127.0.0.1', port, token: env.MT5_MCP_REMOTE_TOKEN };
}

const digest = value => createHash('sha256').update(String(value)).digest();
export function tokenMatches(header, token) {
  const match = /^Bearer (.+)$/.exec(header || '');
  return Boolean(match) && timingSafeEqual(digest(match[1]), digest(token));
}

// Server-side gate: only the MCP methods and read-only tools the local launcher exposes.
export function isAllowedRemoteRequest(message) {
  if (!message || typeof message !== 'object' || Array.isArray(message)) return false;
  if (!ALLOWED_METHODS.has(message.method)) return false;
  if (message.method !== 'tools/call') return true;
  const name = message.params?.name || '';
  return name === SETUP_STATUS_TOOL.name ||
    (name.startsWith(PREFIX) && MT5_READ_ONLY_TOOL_NAMES.has(name.slice(PREFIX.length)));
}

// HTTP front for one long-lived launcher child (stdio JSON-RPC). Each POST carries one
// JSON-RPC message; requests get the child's matching response, notifications get 202.
// Request ids are remapped so concurrent remote sessions cannot collide.
export function createRemoteMcpServer({ child, token, requestTimeoutMs = 30000, log = () => {} }) {
  const pending = new Map();
  let nextId = 1;
  let buffer = '';

  child.stdout.on('data', chunk => {
    buffer += chunk.toString('utf8');
    let newline;
    while ((newline = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      const entry = message.id !== undefined ? pending.get(message.id) : undefined;
      if (!entry) continue; // server-initiated notifications are not relayed
      pending.delete(message.id);
      clearTimeout(entry.timer);
      entry.resolve({ ...message, id: entry.originalId });
    }
  });
  child.stdin.on?.('error', () => {});

  const reply = (res, status, body) => {
    res.writeHead(status, body === undefined ? {} : { 'content-type': 'application/json' });
    res.end(body === undefined ? undefined : JSON.stringify(body));
  };
  const rpcError = (id, message) => ({ jsonrpc: '2.0', id, error: { code: -32601, message } });

  return createServer((req, res) => {
    if (req.url !== REMOTE_PATH) return reply(res, 404, { error: 'not found' });
    if (req.method !== 'POST') return reply(res, 405, { error: 'method not allowed' });
    if (!tokenMatches(req.headers.authorization, token)) {
      log(`rejected unauthorized request from ${req.socket.remoteAddress}`);
      return reply(res, 401, { error: 'unauthorized' });
    }
    const chunks = [];
    let size = 0;
    req.on('data', chunk => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reply(res, 413, { error: 'payload too large' });
        req.destroy();
      } else {
        chunks.push(chunk);
      }
    });
    req.on('end', () => {
      if (res.writableEnded) return;
      let message;
      try {
        message = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      } catch {
        return reply(res, 400, { error: 'invalid JSON' });
      }
      if (!isAllowedRemoteRequest(message)) {
        if (message?.id === undefined) return reply(res, 202);
        return reply(res, 200, rpcError(message.id, 'Method or tool is not available in this read-only MCP.'));
      }
      if (message.id === undefined) {
        child.stdin.write(`${JSON.stringify(message)}\n`);
        return reply(res, 202);
      }
      const id = `remote-${nextId++}`;
      const timer = setTimeout(() => {
        pending.delete(id);
        reply(res, 200, rpcError(message.id, 'The MT5 MCP did not answer in time.'));
      }, requestTimeoutMs);
      pending.set(id, { originalId: message.id, timer, resolve: body => reply(res, 200, body) });
      child.stdin.write(`${JSON.stringify({ ...message, id })}\n`);
    });
  });
}

// Child-like adapter over the remote endpoint, for startDeferredReadOnlyProxy. The server
// returns launcher-aliased names (readonly_<tool>); they are unwrapped here so the local
// proxy re-applies its own allowlist and aliasing, producing the same names as a local run.
export function createRemoteHttpChild({ url, token, fetchImpl = globalThis.fetch, requestTimeoutMs = 30000 }) {
  const child = new EventEmitter();
  child.stdin = new PassThrough();
  child.stdout = new PassThrough();
  const emit = message => child.stdout.write(`${JSON.stringify(message)}\n`);
  const unwrapName = name => (name?.startsWith(PREFIX) && MT5_READ_ONLY_TOOL_NAMES.has(name.slice(PREFIX.length))
    ? name.slice(PREFIX.length) : name);
  const wrapName = name => (MT5_READ_ONLY_TOOL_NAMES.has(name) ? `${PREFIX}${name}` : name);

  const forward = async message => {
    if (message.method === 'tools/call' && message.params?.name) {
      message = { ...message, params: { ...message.params, name: wrapName(message.params.name) } };
    }
    let body;
    try {
      const response = await fetchImpl(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
        body: JSON.stringify(message),
        signal: AbortSignal.timeout(requestTimeoutMs)
      });
      if (response.status === 202 || message.id === undefined) return;
      if (response.status === 401) throw new Error('the remote MT5 MCP rejected MT5_MCP_REMOTE_TOKEN (HTTP 401)');
      if (!response.ok) throw new Error(`the remote MT5 MCP returned HTTP ${response.status}`);
      body = await response.json();
    } catch (error) {
      if (message.id === undefined) return;
      const reason = error?.name === 'TimeoutError' ? 'the remote MT5 MCP did not answer in time' : error?.message || 'unknown error';
      emit({ jsonrpc: '2.0', id: message.id, error: { code: -32603, message: `Remote MT5 MCP unreachable: ${reason}.` } });
      return;
    }
    if (Array.isArray(body?.result?.tools)) {
      body.result.tools = body.result.tools.map(tool => ({ ...tool, name: unwrapName(tool.name) }));
    }
    emit(body);
  };

  let buffer = '';
  child.stdin.on('data', chunk => {
    buffer += chunk.toString('utf8');
    let newline;
    while ((newline = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      try {
        forward(JSON.parse(line));
      } catch {
        // ignore malformed lines
      }
    }
  });
  return child;
}
