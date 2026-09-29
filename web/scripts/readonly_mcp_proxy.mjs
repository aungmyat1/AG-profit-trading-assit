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
    if (message.id === undefined) return; // notifications need no reply
    switch (message.method) {
      case 'initialize':
        send({ id: message.id, result: {
          protocolVersion: message.params?.protocolVersion || '2025-06-18',
          capabilities: { tools: {} },
          serverInfo: { name: `${serverName}-setup-error`, version: '1.0.0' },
          instructions: `MT5 MCP is not connected: ${reason}`
        } });
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
  });
  return lines;
}
