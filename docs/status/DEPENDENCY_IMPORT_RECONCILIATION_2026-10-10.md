---
class: status_evidence
state: IMPLEMENTED
owner_reviewed: null
review_by: 2026-11-07
---
# Dependency import reconciliation — 2026-10-10

Base: origin/main 7f3e75d8bbb4a7c119a9be7279bf6d2f5badd003.

`rg -n "(^|[ ;])(import|from) (MetaTrader5|dotenv|matplotlib)" src scripts tests`
finds MetaTrader5 imports (e.g. src/mt5/market_data.py:17 and
scripts/host/_host_common.py:247), and no dotenv or matplotlib imports.
Restore MetaTrader5==5.0.5735 with a win32 environment marker in requirements.txt,
matching pyproject.toml. Leave python-dotenv and matplotlib out.

Wheel check: `python -m pip download --no-deps --only-binary=:all: --platform
win_amd64 --python-version 311 --implementation cp --abi cp311
MetaTrader5==5.0.5735 -d <SCRATCH>/dependency-wheels` succeeded and downloaded
metatrader5-5.0.5735-cp311-cp311-win_amd64.whl. No broker operation was performed.

Validation: `/workspace/AG-profit-trading-assit/.venv/bin/python -m pytest -q
tests/test_dependency_declarations.py` — 2 passed on Linux, 2026-10-10.
The existing CI pytest step collects the regression. It parses every Python file
in src/, scripts/, tests/, including deferred imports, and checks declared pins for
known external import roots; it also locks the Windows-only MT5 marker to pyproject.

A universal import-resolution check is not feasible within this dependency-only
scope: main imports absent project modules such as historical_replay
(src/market_structure/analyzer.py) and assistant (src/supply_demand/native_zones.py).
Other examples include daytrading_runtime and proposals
(scripts/run_eligibility_reconstruction.py). Installing similarly named PyPI packages
would not restore these project modules. The focused check does not claim unknown
roots resolve, execute imported modules, or verify runtime/Windows installation.
Full resolution requires a separately scoped restoration of missing project modules.
