# Risk Engine boundary shell

Future deterministic risk evaluation consumes contracts and policy inputs. It must not
import broker adapters or perform broker mutation. Existing `src/execution/risk.py`
remains authoritative until a later parity-gated migration.
