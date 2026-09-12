// WP0B EXECUTION AUTHORITY CONTAINMENT -- mock-mode counterpart.
//
// Proves the /manage and /claim real-mode retirement (see
// wp0a_execution_route_containment.test.ts) did NOT change mock-mode behaviour:
// the in-memory simulated position management the UI relies on still works and is
// still explicitly flagged simulated (no broker contact in either mode).
//
// Run with: npx tsx --test tests/wp0b_management_route_mock_mode.test.ts

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 34118;
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
    env: { ...process.env, PORT: String(PORT), VITE_AG_API_MODE: 'mock' },
    windowsHide: true
  });
  await waitForServer();
}, { timeout: 30000 });

after(() => {
  server?.kill();
});

test('mock-mode manage still simulates BREAKEVEN on an in-memory position', async () => {
  const positionsRes = await fetch(`${BASE_URL}/api/execution/positions`);
  assert.equal(positionsRes.status, 200);
  const positions = await positionsRes.json();
  assert.ok(Array.isArray(positions) && positions.length > 0, 'mock fixture positions expected');
  const ticket = positions[0].ticket;

  const res = await fetch(`${BASE_URL}/api/execution/manage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket, action: 'BREAKEVEN' })
  });
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.success, true);
  assert.equal(data.simulated, true);
  assert.equal(data.position.isBreakevenMoved, true);
});

test('mock-mode claim still returns a simulated acknowledgement', async () => {
  const res = await fetch(`${BASE_URL}/api/execution/claim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket: 9123456, finalR: 5 })
  });
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.success, true);
  assert.equal(data.simulated, true);
});
