// WP0A EXECUTION AUTHORITY CONTAINMENT (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1)
//
// Proves that web/server.ts's POST /api/execution/execute no longer holds real
// broker execution authority: in VITE_AG_API_MODE=real it must fail closed and
// must never spawn scripts/web_execute_trade.py, regardless of client-supplied
// geometry or a client-supplied user_confirmed=true.
//
// Run with: npx tsx --test tests/wp0a_execution_route_containment.test.ts
// (no MT5 terminal or broker connection required; asserts on HTTP responses only)

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 34117;
const BASE_URL = `http://127.0.0.1:${PORT}`;
let server: ChildProcess;

async function waitForServer(timeoutMs = 20000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/api/health`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('server did not become ready in time');
}

before(async () => {
  const repoWebDir = path.resolve(__dirname, '..');
  const tsxCli = path.join(repoWebDir, 'node_modules', 'tsx', 'dist', 'cli.mjs');
  server = spawn(process.execPath, [tsxCli, 'server.ts'], {
    cwd: repoWebDir,
    env: { ...process.env, PORT: String(PORT), VITE_AG_API_MODE: 'real' },
    windowsHide: true
  });
  await waitForServer();
}, { timeout: 30000 });

after(() => {
  server?.kill();
});

const validOrderBody = {
  symbol: 'EURUSD',
  strategyId: 'FRONTEND_MANUAL',
  side: 'BUY',
  lots: 1.0,
  entryPrice: 1.085,
  stopLoss: 1.083,
  takeProfit1: 1.088,
  takeProfit2: 1.092,
  user_confirmed: true
};

test('real-mode POST /api/execution/execute fails closed and does not submit an order', async () => {
  const res = await fetch(`${BASE_URL}/api/execution/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(validOrderBody)
  });
  const data = await res.json();

  assert.equal(res.status, 410);
  assert.equal(data.success, false);
  assert.equal(data.error, 'EXECUTION_ROUTE_RETIRED');
  assert.equal(data.ticket, undefined);
  assert.equal(data.deal_id, undefined);
  assert.equal(data.simulated, undefined);
});

test('real-mode route rejects even with fully-specified client geometry and user_confirmed=true', async () => {
  const res = await fetch(`${BASE_URL}/api/execution/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...validOrderBody, lots: 5.5, entryPrice: 1.09999 })
  });
  const data = await res.json();
  assert.equal(res.status, 410);
  assert.equal(data.error, 'EXECUTION_ROUTE_RETIRED');
});

test('scanner synthetic proposal feed still reports executionEligible=false', async () => {
  const res = await fetch(`${BASE_URL}/api/proposals/scan`);
  assert.equal(res.status, 200);
  const proposals = await res.json();
  assert.ok(Array.isArray(proposals));
  for (const p of proposals) {
    assert.equal(p.executionEligible, false);
  }
});

// --- WP0B: position-management authority containment -------------------------
// /api/execution/manage and /api/execution/claim used to spawn
// scripts/web_manage_trade.py / scripts/manage_trade.py -> src/mt5/management_gateway.py
// -> real mt5.order_check/order_send against an EXISTING broker position. They must now
// fail closed in real mode exactly like /execute does.

const manageActions = ['BREAKEVEN', 'PARTIAL_CLOSE', 'CLOSE'];

for (const action of manageActions) {
  test(`real-mode POST /api/execution/manage (${action}) is retired and spawns no broker script`, async () => {
    const res = await fetch(`${BASE_URL}/api/execution/manage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket: 9123456, action })
    });
    const data = await res.json();
    assert.equal(res.status, 410);
    assert.equal(data.success, false);
    assert.equal(data.error, 'EXECUTION_ROUTE_RETIRED');
    // no bridge/broker report of any kind may come back
    assert.equal(data.report, undefined);
    assert.equal(data.simulated, undefined);
    assert.equal(data.position, undefined);
  });
}

test('real-mode POST /api/execution/claim is retired and spawns no broker script', async () => {
  const res = await fetch(`${BASE_URL}/api/execution/claim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket: 9123456, finalR: 5 })
  });
  const data = await res.json();
  assert.equal(res.status, 410);
  assert.equal(data.success, false);
  assert.equal(data.error, 'EXECUTION_ROUTE_RETIRED');
  assert.equal(data.report, undefined);
  assert.equal(data.simulated, undefined);
});

// --- WP0C: manual-demo authority containment (AG_MANUAL_DEMO_ROUTE_CONTAINMENT_FINAL) ---
// /api/execution/manual-demo used to spawn scripts/web_execute_trade.py --confirm
// directly, entirely outside the canonical owner-decision/execution-decision
// pipeline. It must now unconditionally return 410 before any body handling that
// could reach that script, regardless of payload shape, headers, or query string.

const manualDemoValidBody = {
  symbol: 'EURUSD', side: 'BUY', lots: 0.1, entryPrice: 1.085, stopLoss: 1.083,
  takeProfit2: 1.092, strategyId: 'FRONTEND_MANUAL', user_confirmed: true,
};

async function assertManualDemoRetired(res: Response) {
  assert.equal(res.status, 410);
  const data = await res.json();
  assert.equal(data.success, false);
  assert.equal(data.error, 'EXECUTION_ROUTE_RETIRED');
  assert.equal(data.ticket, undefined);
  assert.equal(data.simulated, undefined);
  assert.equal(data.report, undefined);
}

test('manual-demo: valid legacy payload is retired, not executed', async () => {
  const res = await fetch(`${BASE_URL}/api/execution/manual-demo`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(manualDemoValidBody),
  });
  await assertManualDemoRetired(res);
});

test('manual-demo: empty object body is retired', async () => {
  await assertManualDemoRetired(
    await fetch(`${BASE_URL}/api/execution/manual-demo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    }),
  );
});

test('manual-demo: null JSON body is rejected by the body parser, not executed', async () => {
  // express.json()'s default strict:true rejects a top-level non-object/array JSON
  // value (the literal `null`) before any route handler runs -- a framework parser
  // rejection (500, no app-level error middleware here), not the 410 the retired
  // handler itself returns. Either way the request never reaches the handler.
  const res = await fetch(`${BASE_URL}/api/execution/manual-demo`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: 'null',
  });
  assert.ok(res.status >= 400, `expected an error status for null body, got ${res.status}`);
  const data = await res.json().catch(() => null);
  assert.equal(data?.ticket, undefined);
  assert.equal(data?.simulated, undefined);
});

test('manual-demo: missing required legacy fields is retired', async () => {
  await assertManualDemoRetired(
    await fetch(`${BASE_URL}/api/execution/manual-demo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_confirmed: true }),
    }),
  );
});

test('manual-demo: arbitrary/bypass-looking extra fields do not change the outcome', async () => {
  await assertManualDemoRetired(
    await fetch(`${BASE_URL}/api/execution/manual-demo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...manualDemoValidBody, bypass: true, force: true, admin: true, mode: 'override',
      }),
    }),
  );
});

test('manual-demo: arbitrary auth header does not unlock execution', async () => {
  await assertManualDemoRetired(
    await fetch(`${BASE_URL}/api/execution/manual-demo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AG-Owner-Key': 'anything', Authorization: 'Bearer fake' },
      body: JSON.stringify(manualDemoValidBody),
    }),
  );
});

test('manual-demo: query parameters appended to the route do not unlock execution', async () => {
  await assertManualDemoRetired(
    await fetch(`${BASE_URL}/api/execution/manual-demo?confirm=true&force=1`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(manualDemoValidBody),
    }),
  );
});

test('manual-demo: alternate content-type that the server still parses is retired', async () => {
  await assertManualDemoRetired(
    await fetch(`${BASE_URL}/api/execution/manual-demo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json;charset=utf-8' },
      body: JSON.stringify(manualDemoValidBody),
    }),
  );
});

test('manual-demo: repeated requests are each independently retired', async () => {
  for (let i = 0; i < 3; i++) {
    await assertManualDemoRetired(
      await fetch(`${BASE_URL}/api/execution/manual-demo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(manualDemoValidBody),
      }),
    );
  }
});

test('manual-demo: malformed/truncated JSON is rejected by the body parser, not executed', async () => {
  for (const badBody of ['{"symbol":', '{not valid json}', '']) {
    const res = await fetch(`${BASE_URL}/api/execution/manual-demo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: badBody,
    });
    // Malformed JSON either fails express.json()'s parse (this server has no
    // app-level JSON-parse error handler, so that surfaces as a 500 from
    // Express's default error handler) or -- for the empty-body case, which
    // express.json() treats as no body -- reaches the handler and gets the
    // unconditional 410. Never a 2xx, and never response evidence of execution.
    assert.notEqual(res.status, 200, `body ${JSON.stringify(badBody)} must never succeed`);
    const data = await res.json().catch(() => null);
    assert.equal(data?.ticket, undefined, `body ${JSON.stringify(badBody)} must show no execution evidence`);
    assert.equal(data?.simulated, undefined);
  }
});

test('server.ts source contains no real-mode spawn of a broker-mutating script', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(path.resolve(__dirname, '..', 'server.ts'), 'utf-8');
  for (const script of ['web_execute_trade.py', 'web_manage_trade.py', 'manage_trade.py']) {
    assert.ok(
      !source.includes(`'${script}'`),
      `web/server.ts must not reference broker-mutating script ${script}`
    );
  }
});

test('read-only routes do not accept or trigger broker execution', async () => {
  const health = await fetch(`${BASE_URL}/api/health`);
  assert.equal(health.status, 200);
  const scan = await fetch(`${BASE_URL}/api/proposals/scan`);
  assert.equal(scan.status, 200);
  // neither read route is POST-able into an execution side effect
  const badPost = await fetch(`${BASE_URL}/api/proposals/scan`, { method: 'POST' });
  assert.notEqual(badPost.status, 200);
});
