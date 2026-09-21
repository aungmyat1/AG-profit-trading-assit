# How to Fix `requirements.txt` — Detailed Recommendation

**Repo:** aungmyat1/AG-profit-trading-assit · **Date:** 2026-09-21 · **Verified:** all commands below were actually run

---

## The problems (verified facts)

1. **`MetaTrader5==5.0.5735` is Windows-only.** PyPI publishes `win_amd64` wheels only
   (cp36–cp314; no Linux/macOS wheels exist). On any non-Windows machine
   `pip install -r requirements.txt` aborts with
   `ERROR: Could not find a version that satisfies the requirement MetaTrader5==5.0.5735`.
2. **`pydantic` is a hidden dependency.** `src/api/schemas.py` does
   `from pydantic import BaseModel` directly, but it is not declared — it only exists
   transitively through `fastapi`. A future fastapi bump could silently move the
   pydantic version under the API schemas.
3. Minor: runtime and test-only deps are mixed without distinction (fine for now,
   since the README quick start runs pytest directly — see Option A).

The repo's own `tests/conftest.py` was **designed for exactly this fix**: it provides an
import-only MT5 stub and says non-Windows runs should SKIP, not fail. The requirements
file just never got the marker that would let pip reach that design.

---

## Option A — Minimal in-place fix ✅ RECOMMENDED

One line changed, one line added. No file renames, no tooling impact (only `README.md`
line 159 references this file; `.vscode/tasks.json` does not).

```diff
 PyYAML==6.0.3
 pandas==2.3.3
-MetaTrader5==5.0.5735
+MetaTrader5==5.0.5735 ; sys_platform == 'win32'
 smartmoneyconcepts==0.0.27
-pytest==8.3.5
 matplotlib==3.11.0
 requests==2.34.2  # execution_runtime.binance_usdtm_feed (Binance USDT-M public REST) -- verified 2026-09-02
 python-dotenv==1.1.1  # mt5.config (loads src/.env for MT5 broker/account identity) -- verified 2026-09-07
 fastapi==0.135.1  # api/ -- ... -- verified 2026-09-08
 uvicorn==0.41.0  # ASGI server to run api.app -- verified 2026-09-08
+pydantic==2.13.5  # src/api/schemas.py imports BaseModel directly; previously only a transitive pin of fastapi -- verified 2026-09-21
+# Test-only dependencies (kept here because the README quick start runs pytest directly).
+pytest==8.3.5
 httpx==0.28.1  # required by fastapi.testclient.TestClient (tests/test_api.py) -- verified 2026-09-08
 pyarrow==25.0.1  # research_external/tooling/artifact_io.py (pandas Parquet engine) -- verified 2026-09-12
```

A complete ready-to-paste file is provided at `requirements.fixed.txt` (in the workspace
next to this document).

### Why each change

| Change | Rationale |
|---|---|
| `; sys_platform == 'win32'` on MetaTrader5 | PEP 508 environment marker. On Windows it evaluates true and **behavior is 100% unchanged**. On Linux/macOS pip prints `Ignoring MetaTrader5: markers ... don't match your environment` and continues. This is pip's canonical pattern for platform-specific packages (same as `pywin32`). |
| Add `pydantic==2.13.5` | Direct import in `src/api/schemas.py`; the project's own rule (every pin "verified against" a date) should apply to direct deps. `2.13.5` is what fastapi 0.135.1 resolves today — **confirm with `pip show pydantic` on the canonical Windows box before committing**, and use that machine's value if different. |
| Group test-only deps under a comment | Preserves the README quick start (`install -r requirements.txt && pytest`) while making the runtime/test boundary visible. No behavioral change. |

### ⚠️ Windows Python version: no action needed, but document it
MetaTrader5 5.0.5735 ships wheels for Python 3.6–**3.14**, so the README's
"Python 3.10 or newer" is safe even on the newest Pythons. I verified pip resolves the
wheel for cp313/win_amd64: `metatrader5-5.0.5735-cp313-cp313-win_amd64.whl` downloads fine.

---

## Verification (all actually executed today)

**Linux/macOS (fresh venv):**
```bash
python -m venv .venv-verify
.venv-verify/bin/pip install -r requirements.fixed.txt
```
Result: ✅ exit 0, pip logs `Ignoring MetaTrader5: markers 'sys_platform == "win32"' don't match your environment`,
`pip check` → `No broken requirements found`, and a smoke import of every declared package
(yaml, pandas, matplotlib, requests, dotenv, fastapi, uvicorn, pydantic, httpx, pyarrow,
smartmoneyconcepts, pytest) succeeds on Python 3.13.

**Windows (simulated resolution):**
```bash
pip download --no-deps --only-binary=:all: --platform win_amd64 \
  --python-version 313 --implementation cp MetaTrader5==5.0.5735 -d /tmp/winwheel
```
Result: ✅ `Saved /tmp/winwheel/metatrader5-5.0.5735-cp313-cp313-win_amd64.whl` — the
pinned wheel remains installable on Windows exactly as before.

**Real Windows acceptance test (run once on the dev box):**
```powershell
python -m venv .venv-test ; .venv-test\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "import MetaTrader5; print(MetaTrader5.__file__)"   # must import
python -m pytest -q                                           # must equal the current baseline
```

---

## ⚠️ Necessary but not sufficient — the paired fix

With the requirements fixed, `pip install` succeeds on Linux, but `pytest -q` **still
aborts during collection** with `Interrupted: 9 errors during collection` (verified).
Nine test files call `MetaTrader5.initialize()/symbol_info()/terminal_info()` at import
time without the `live_mt5` mark, so the conftest stub refuses them:

```
tests/test_assistant_market_data.py   tests/test_market_data.py
tests/test_five_skill_runtime.py      tests/test_market_structure.py
tests/test_liquidity.py               tests/test_mtf_context.py
tests/test_ob_contract.py             tests/test_supply_demand.py
tests/test_topdown_market_data.py
```

The stub's own error message prescribes the fix: *"Mark this test `@pytest.mark.live_mt5`,
or monkeypatch the MT5 surface explicitly."* Add `pytestmark = pytest.mark.live_mt5` at
module level (or per-test marks) in those files. Then on Linux these collect as skipped —
matching the README's promise that *"a non-Windows run reports SKIP instead of a
misleading FAIL."* After that, 3,597 tests collect cleanly on every platform.

---

## Option B — Split runtime vs dev deps (optional, cleaner)

If you later want CI to install only what it needs:

```text
requirements.txt       # runtime deps only (the Option A content minus pytest/httpx)
requirements-dev.txt   # -r requirements.txt
                       # pytest==8.3.5
                       # httpx==0.28.1
```

Cost: the README quick start becomes two installs (`pip install -r requirements-dev.txt`),
and AGENTS.md/PROJECT_STATUS would reference the new file. Given the project's
"smallest correct implementation" rule, **do this only when a concrete need appears**
(e.g., a Docker image or CI job that shouldn't carry pytest).

## Option C — Declare in `pyproject.toml` (long-term only)

`pyproject.toml` already exists but declares no dependencies. The fully modern form:

```toml
[project]
dependencies = [
  "PyYAML==6.0.3", "pandas==2.3.3",
  "MetaTrader5==5.0.5735 ; sys_platform == 'win32'",
  "smartmoneyconcepts==0.0.27", "matplotlib==3.11.0", "requests==2.34.2",
  "python-dotenv==1.1.1", "fastapi==0.135.1", "uvicorn==0.41.0",
  "pydantic==2.13.5", "pyarrow==25.0.1",
]

[project.optional-dependencies]
dev = ["pytest==8.3.5", "httpx==0.28.1"]
```

This enables `pip install -e .[dev]` and makes the package importable without the
`pythonpath = ["src"]` pytest trick. **Not recommended now**: it changes the install
model the whole repo (and AGENTS.md history) is built around, for no operational gain
until packaging/distribution becomes a goal.

---

## Housekeeping after the merge

- README quick start stays valid as-is (no doc change needed for Option A).
- Per `docs/status/LIVE_STATUS_MAINTENANCE.md` conventions, record the dependency
  change in `PROJECT_STATUS.md` with its verification date — the file already contains
  the original "Added `requirements.txt`" entry, so this is a dated delta, same style.
- Optional hardening for later: `pip install --require-hashes` via generated hash pins
  (`pip-compile --generate-hashes`), consistent with the project's fingerprint culture —
  only worth the maintenance overhead if supply-chain integrity becomes a gated requirement.
