# AI Studio + VS Code development workflow

Status: setup guide, additive. Does not change execution authority, strategy semantics,
or safety gates. See `AGENTS.md` "Authority order" for what actually decides/executes a
trade — nothing in this document changes that chain.

## QUICK START — VS Code

```text
FIRST-TIME SETUP

1. Open repository in VS Code
2. Run:
   .\scripts\setup_dev.ps1
   (verifies Python/Node/package manager, installs web/node_modules)
```

```text
DAILY TEST RUN

1. Open MT5
2. Log into Vantage Demo
3. Open repository in VS Code
4. Run:
   .\scripts\run_dev.ps1
5. Open:
   http://localhost:3000
6. Open the "Execution" tab
7. Click:
   Test Backend Connection

Expected:
   BACKEND CONNECTED
   Environment: DEMO
   Broker connected: YES
```

Optional read-only check from a separate terminal (never sends an order):

```powershell
python scripts/test_dev_connection.py
```

Or from VS Code: `Ctrl+Shift+P` → `Tasks: Run Task` → `AG: Setup Dev (first time)`,
`AG: Start Dev`, `AG: Test Dev Connection`, `AG: Run Integration Tests`.
`AG: Start Dev` directly runs the same supervised `scripts/run_dev.ps1` launcher and is
also the default VS Code build task (`Ctrl+Shift+B`). It keeps FastAPI and Vite together
in one dedicated terminal; stopping that task stops both child jobs. The separate
`AG: Start Backend` and `AG: Start Frontend` tasks remain available for debugging.
`run_dev.ps1` deliberately does NOT install dependencies itself; if `web/node_modules`
is missing it tells you to run `setup_dev.ps1` instead of installing silently.

### Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Bun not installed` | `web/bun.lock` documents Bun as the frontend scaffold's original package manager, but Bun isn't required — `scripts/setup_dev.ps1` automatically falls back to `npm` (installing from `web/package.json` alone) when `bun` isn't on PATH. Installing Bun is optional, not a blocker. |
| `npm registry timeout` / `npm install` hangs with no output | A flaky network path to `registry.npmjs.org` (confirmed via `npm install --loglevel verbose`, which shows lines like `npm http fetch GET .../@tailwindcss%2fvite attempt 1 failed with ETIMEDOUT`). Retry with `npm install --fetch-retries=8 --fetch-retry-mintimeout=3000 --fetch-timeout=120000`, or from a more stable network. This is an environment/network condition, not a project defect — do not "fix" it by deleting `web/bun.lock` or hand-editing dependency versions. |
| `node_modules missing` | Run `.\scripts\setup_dev.ps1` once. `run_dev.ps1` intentionally refuses to start Vite and tells you to do this instead of installing silently on every run. |
| `Port already in use` (8000 or 3000) | Another process already bound that port — stop it, or pass `--port` to `scripts/run_api.py` / change `web/vite.config.ts`'s `server.port` (and update `VITE_API_BASE_URL` to match if you change 8000). |
| FastAPI unreachable | Confirm `python scripts/run_api.py` is actually running and printed `Application startup complete` with no `ERROR` line (a stale process can be holding the port — check `netstat -ano | findstr :8000`). |
| Vite unreachable | Confirm the frontend dev server is running inside `web/` (`npm run dev` or `bun run dev`) and printed a `Local: http://localhost:3000/` line. |
| CORS failure in the browser console | The frontend's origin isn't in the backend's allow-list. Default is `http://localhost:3000` and `http://127.0.0.1:3000`; if you're using a different port/origin, set `AG_ALLOWED_ORIGINS` (comma-separated) before starting the backend. Never set it to `*`. |
| MT5 disconnected | `Test Backend Connection` will still say `BACKEND CONNECTED` (the API itself is up) but broker fields will show disconnected/unknown — this is expected and not a bug; open/log into the MT5 terminal and click the test again. `scripts/test_dev_connection.py` reports this as `UI_READY_BROKER_DISCONNECTED`, not a failure. |
| Frontend reachable but backend unreachable | FastAPI isn't running, crashed, or is bound to a different host/port than `VITE_API_BASE_URL` points at — check the FastAPI terminal/job output and `web/.env`'s `VITE_API_BASE_URL`. |
| Backend reachable but broker disconnected | Expected, not a bug — see the "MT5 disconnected" row above. |
| Backend works (`curl` succeeds) but the frontend can't connect | Check `web/.env` has `VITE_API_BASE_URL=http://127.0.0.1:8000` and `VITE_AG_API_MODE=real`, then restart the Vite dev server (it only reads `.env` at startup). |

## Roles

```text
Google AI Studio  = frontend preview / UI iteration ONLY, no trading authority
VS Code           = authoritative repository, backend runtime, MT5, Telegram, tests
```

AI Studio never holds broker secrets and never talks to MT5 directly. It may call the
local FastAPI backend over HTTP when network-reachable; when it isn't (a very likely
case — AI Studio's preview sandbox may have no route to your machine's `localhost`),
the frontend runs in `MOCK` mode instead of silently pretending to be connected.

## Starting the backend (VS Code terminal)

```bash
python scripts/run_api.py
# binds 127.0.0.1:8000 by default -- never 0.0.0.0 without explicit owner authorization
```

Options: `--host`, `--port`, `--reload`. Port 8000 was chosen because the frontend dev
server already owns port 3000 (`web/vite.config.ts`, `web/server.ts`).

Verify:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/broker/status
```

`broker/status` is read-only and sanitized — no password, token, or full account login
ever appears in its response (see `src/api/schemas.py::BrokerStatusResponse`).

## Starting the frontend (separate VS Code terminal)

```bash
cd web
npm install   # first time only
npm run dev
```

Serves on `http://localhost:3000`.

## Running tests (separate VS Code terminal)

```bash
python -m pytest tests/test_api.py tests/test_authorization_core.py tests/test_telegram_client.py tests/test_telegram_gateway.py tests/test_mt5_execution_handler.py -q
```

Frontend type-check (no dedicated test framework exists yet in `web/`):

```bash
cd web && npm run lint   # tsc --noEmit
```

## Environment variables

Backend (`src/.env`, gitignored — see `src/.env.example`): `MT5_BROKER`,
`MT5_ENVIRONMENT`, `VANTAGE-DEMO-LOGIN`, `VANTAGE-DEMO_PASSWORD`,
`VANTAGE-DEMO_SERVER`, `MT5_TERMINAL_PATH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Never referenced by any frontend file — see `src/mt5/config.py`.

Backend CORS (optional, comma-separated origin list):

```text
AG_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Defaults to exactly those two origins if unset. Never set to `*`.

Frontend (`web/.env`, create locally from `web/.env.example` — gitignored):

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_AG_API_MODE=mock   # or "real"
```

`VITE_*` variables are bundled into the browser build and are therefore, by Vite's own
design, public — never put an `MT5_*` or `TELEGRAM_*` secret behind a `VITE_` prefix.

## Mock vs. real data

`web/src/utils/api.ts` (pre-existing) is the **mock** data layer — realistic-looking
fixture positions, proposals, and logs for UI development. It never talks to the real
backend.

`web/src/utils/agApiClient.ts` (new) is the **real** backend client — the only file
that calls the FastAPI routes in `src/api/app.py`. `VITE_AG_API_MODE` selects which one
a given screen should prefer; `web/src/components/Terminal/BackendConnectionDiagnostic.tsx`
always shows which mode is active so mock data is never mistaken for a real broker
event. Wiring every existing UI surface to switch between the two is not complete yet
— see `PROJECT_STATUS.md` / the Phase status doc for what remains.

## Testing backend connectivity from the UI

Use the "Test Backend Connection" panel
(`BackendConnectionDiagnostic`). It calls `GET /api/health` then `GET /api/broker/status`
and reports one of:

```text
BACKEND CONNECTED / BROKER CONNECTED, environment/server/account (redacted)/trade-allowed
BACKEND UNREACHABLE (network/timeout/HTTP error — never converted into a fake success)
```

## Recognizing the AI Studio localhost limitation

"The UI renders" and "the local backend is reachable" are different facts. If AI
Studio's preview sandbox cannot route to your machine, `Test Backend Connection` will
correctly report `BACKEND UNREACHABLE` — this is a network/environment boundary, not a
bug, and not evidence the backend is broken. Confirm by running the identical frontend
from `npm run dev` in VS Code instead; if that succeeds, the backend is fine and only
the AI Studio→localhost route is unavailable.

## Demo execution safety boundary

- Automated tests always mock the broker-reaching boundary (`execution.executor.execute`
  or the injected `execution_handler`) — no test in this repository sends a real order.
- A read-only smoke test (`/api/broker/status`, `/api/tickets`) is safe to run any time.
- An actual Demo order requires a separate, explicit owner authorization for a specific
  ticket — clicking "Authorize Demo" in the UI is the *request*, not a standing
  permission; the backend re-verifies strategy Demo-authority, proposal integrity, and
  environment on every click (see `src/api/execution_service.py`).
- LIVE execution is blocked at the model level: `authorization/models.py` defines no
  LIVE environment constant, and `mt5_execution_handler` independently refuses any
  non-DEMO environment before ever calling the execution gateway.
