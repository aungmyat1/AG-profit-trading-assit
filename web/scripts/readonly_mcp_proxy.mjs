import { createInterface } from 'node:readline';

export function isReadOnlyTool(tool) {
  return tool?.annotations?.readOnlyHint === true &&
    tool?.annotations?.destructiveHint !== true;
}

// metatrader-mcp-server (ariadng, pinned 0.5.1) registers every tool without MCP
// annotations, so the annotation check alone would hide all of them. These exact
// upstream names are its query-only tools; order/position mutators (place_*, modify_*,
// close_*, cancel_*) are never listed and stay unreachable.
export const MT5_READ_ONLY_TOOL_NAMES = new Set([
  'get_account_info', 'get_deals', 'get_orders', 'get_candles_by_date', 'get_candles_latest',
  'get_symbol_price', 'get_all_symbols', 'get_symbols', 'get_all_positions',
  'get_positions_by_symbol', 'get_positions_by_id', 'get_all_pending_orders',
  'get_pending_orders_by_symbol', 'get_pending_orders_by_id'
]);

export function isReadOnlyMt5Tool(tool) {
  if (tool?.annotations?.destructiveHint === true) return false;
  return isReadOnlyTool(tool) || MT5_READ_ONLY_TOOL_NAMES.has(tool?.name);
}

export function isPublicBybitMarketTool(tool) {
  const publicMarketTool = /(ticker|orderbook|kline|candlestick|instrument|funding|open.?interest|volatility|risk.?limit|delivery.?price|insurance.?pool|long.?short|option.?underlying|option.?asset.?type|server.?time)/i;
  return isReadOnlyTool(tool) && publicMarketTool.test(tool?.name || '');
}

export function startReadOnlyProxy({ child, input = process.stdin, output = process.stdout, allowTool = isReadOnlyTool }) {
  const readOnlyTools = new Map();
  let stdoutBuffer = '';

  child.stdout.on('data', chunk => {
    stdoutBuffer += chunk.toString('utf8');
    let newline;
    while ((newline = stdoutBuffer.indexOf('\n')) !== -1) {
      const line = stdoutBuffer.slice(0, newline).trim();
      stdoutBuffer = stdoutBuffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        // Do not pass unexpected stdout text through the MCP protocol channel.
        continue;
      }
      if (message.id !== undefined && message.result?.tools) {
        readOnlyTools.clear();
        const tools = message.result.tools.filter(allowTool).map(tool => {
          const alias = `readonly_${tool.name}`;
          readOnlyTools.set(alias, tool.name);
          return { ...tool, name: alias };
        });
        message.result.tools = tools;
      }
      output.write(`${JSON.stringify(message)}\n`);
    }
  });

  const lines = createInterface({ input, crlfDelay: Infinity });
  lines.on('line', line => {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }

    if (message.method === 'tools/call') {
      const name = message.params?.name;
      const upstreamName = readOnlyTools.get(name);
      if (!upstreamName) {
        if (message.id !== undefined) {
          output.write(`${JSON.stringify({
            jsonrpc: '2.0',
            id: message.id,
            error: { code: -32601, message: 'Tool is not available in this read-only MCP.' }
          })}\n`);
        }
        return;
      }
      message.params.name = upstreamName;
    }
    child.stdin.write(`${JSON.stringify(message)}\n`);
  });

  input.on('end', () => child.stdin.end());
}
// Minimal stdio MCP server used when the MT5 launcher cannot start its upstream
// server (wrong platform, missing credentials, non-demo server). Instead of exiting,
// which clients only report as "Connection closed", it stays connected and exposes a
// single read-only tool that returns the setup problem. It never contacts MT5.
export const SETUP_STATUS_TOOL = {
  name: 'mt5_setup_status',
  description: 'Report why the read-only MT5 Demo MCP is not connected and how to fix it.',
  inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  annotations: { readOnlyHint: true, destructiveHint: false }
};

function initializeResult(message, serverName, instructions) {
  return {
    protocolVersion: message.params?.protocolVersion || '2025-06-18',
    capabilities: { tools: { listChanged: true } },
    serverInfo: { name: serverName, version: '1.0.0' },
    ...(instructions ? { instructions } : {})
  };
}

// Answers one client request while the upstream server is unavailable.
function replyUnavailable(message, reason, send, serverName) {
  if (message.id === undefined) return; // notifications need no reply
  switch (message.method) {
    case 'initialize':
      send({ id: message.id, result: initializeResult(message, `${serverName}-setup-error`, `MT5 MCP is not connected: ${reason}`) });
      break;
    case 'ping':
      send({ id: message.id, result: {} });
      break;
    case 'tools/list':
      send({ id: message.id, result: { tools: [SETUP_STATUS_TOOL] } });
      break;
    case 'tools/call':
      if (message.params?.name === SETUP_STATUS_TOOL.name) {
        send({ id: message.id, result: { isError: true, content: [{ type: 'text', text: `MT5 MCP is not connected: ${reason}` }] } });
      } else {
        send({ id: message.id, error: { code: -32601, message: `MT5 MCP is not connected: ${reason}` } });
      }
      break;
    default:
      send({ id: message.id, error: { code: -32601, message: 'Method not available while MT5 MCP setup is incomplete.' } });
  }
}

export function startSetupErrorServer({ reason, input = process.stdin, output = process.stdout, serverName = 'mt5ReadOnly' }) {
  const send = message => output.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`);
  const lines = createInterface({ input, crlfDelay: Infinity });
  lines.on('line', line => {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }
    replyUnavailable(message, reason, send, serverName);
  });
  return lines;
}

// Read-only proxy for an upstream server that is slow to initialize.
// metatrader-mcp-server connects to the MT5 terminal before it answers `initialize`,
// which can outlast the client's handshake timeout ("Request timed out") and never
// answers at all if the executable is missing or the login fails. This proxy answers
// `initialize` and `ping` itself, performs its own handshake with the child, and
// queues client requests until the child is ready. If the child is still starting
// after `startupTimeoutMs`, tools/list returns the setup-status tool (followed by
// notifications/tools/list_changed once the child is ready) and tools/call fails fast.
// If the child errors or exits, the proxy stays connected in setup-status mode.
export const PROXY_INIT_ID = '__readonly_proxy_initialize__';

export function startDeferredReadOnlyProxy({
  child, input = process.stdin, output = process.stdout, allowTool = isReadOnlyTool,
  serverName = 'mt5ReadOnly', startupTimeoutMs = 20000, failureHint = ''
}) {
  const send = message => output.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`);
  const toChild = message => child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`);
  const readOnlyTools = new Map();
  const queue = [];
  let state = 'starting';
  let failureReason = '';
  let timedOut = false;
  let listedFallback = false;
  let listedUpstream = false;
  let childInitSent = false;
  let clientInitParams = null;
  let stdoutBuffer = '';
  const startingReason = () => 'the MT5 MCP server is still connecting to the MetaTrader 5 terminal. ' +
    'Open MT5, log in to the demo account, then retry (tools will refresh automatically).';

  const sendChildInitialize = () => {
    if (childInitSent) return;
    childInitSent = true;
    toChild({ id: PROXY_INIT_ID, method: 'initialize', params: {
      protocolVersion: clientInitParams?.protocolVersion || '2025-06-18',
      capabilities: {},
      clientInfo: { name: `${serverName}-readonly-proxy`, version: '1.0.0' }
    } });
  };

  const handleClient = message => {
    if (message.method === 'initialize') {
      clientInitParams = message.params || {};
      if (state === 'failed') {
        replyUnavailable(message, failureReason, send, serverName);
      } else if (message.id !== undefined) {
        send({ id: message.id, result: initializeResult(message, serverName) });
      }
      if (state !== 'failed') sendChildInitialize();
      return;
    }
    if (message.method === 'notifications/initialized') return; // the proxy sends its own
    if (message.method === 'ping' && message.id !== undefined) {
      send({ id: message.id, result: {} });
      return;
    }
    if (state === 'failed') {
      replyUnavailable(message, failureReason, send, serverName);
      return;
    }
    if (state === 'starting') {
      if (!timedOut) {
        queue.push(message);
      } else if (message.method === 'tools/list') {
        listedFallback = true;
        replyUnavailable(message, startingReason(), send, serverName);
      } else if (message.id !== undefined) {
        replyUnavailable(message, startingReason(), send, serverName);
      }
      return;
    }
    if (message.method === 'tools/list') listedUpstream = true;
    if (message.method === 'tools/call') {
      const upstreamName = readOnlyTools.get(message.params?.name);
      if (!upstreamName) {
        if (message.id !== undefined) {
          send({ id: message.id, error: { code: -32601, message: 'Tool is not available in this read-only MCP.' } });
        }
        return;
      }
      message.params.name = upstreamName;
    }
    child.stdin.write(`${JSON.stringify(message)}\n`);
  };

  const flushQueue = () => {
    for (const message of queue.splice(0)) handleClient(message);
  };

  const fail = reason => {
    if (state === 'failed') return;
    const wasReady = state === 'ready';
    state = 'failed';
    failureReason = reason;
    clearTimeout(timer);
    flushQueue();
    if (wasReady && listedUpstream) send({ method: 'notifications/tools/list_changed' });
  };

  const timer = setTimeout(() => {
    if (state !== 'starting') return;
    timedOut = true;
    flushQueue();
  }, startupTimeoutMs);
  timer.unref?.();

  child.stdout.on('data', chunk => {
    stdoutBuffer += chunk.toString('utf8');
    let newline;
    while ((newline = stdoutBuffer.indexOf('\n')) !== -1) {
      const line = stdoutBuffer.slice(0, newline).trim();
      stdoutBuffer = stdoutBuffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue; // never pass unexpected stdout text through the MCP channel
      }
      if (message.id === PROXY_INIT_ID) {
        if (message.error) {
          fail(`the MT5 MCP server rejected initialization (${message.error.message || 'unknown error'}).${failureHint ? ` ${failureHint}` : ''}`);
          continue;
        }
        toChild({ method: 'notifications/initialized' });
        state = 'ready';
        clearTimeout(timer);
        flushQueue();
        if (listedFallback) send({ method: 'notifications/tools/list_changed' });
        continue;
      }
      if (message.id !== undefined && message.result?.tools) {
        readOnlyTools.clear();
        message.result.tools = message.result.tools.filter(allowTool).map(tool => {
          const alias = `readonly_${tool.name}`;
          readOnlyTools.set(alias, tool.name);
          return { ...tool, name: alias };
        });
      }
      output.write(`${JSON.stringify(message)}\n`);
    }
  });

  child.on('error', () => fail(`the MT5 MCP executable could not be started.${failureHint ? ` ${failureHint}` : ''}`));
  child.on('exit', (code, signal) => fail(`the MT5 MCP server exited (${signal || `code ${code}`}) before or while serving requests. ` +
    `Usually MT5 is closed or not logged in to the demo account, or the demo credentials are wrong.${failureHint ? ` ${failureHint}` : ''}`));
  child.stdin.on?.('error', () => {}); // writes after the child exits must not crash the proxy

  const lines = createInterface({ input, crlfDelay: Infinity });
  lines.on('line', line => {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }
    handleClient(message);
  });
  input.on('end', () => child.stdin.end());
  return lines;
}
