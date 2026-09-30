# Agent Context Efficiency

## Token minimum usage policy (owner rule, applies to every task)
- Do only what the task asks; no extra features, refactors or docs.
- No polling, scheduled check-ins or PR subscriptions unless explicitly asked.
- Don't ask questions mid-task: make conservative choices, record them, continue.
- Read only files needed; prefer grep/targeted reads over full-file or repo-wide dumps.
- Don't re-run unchanged failing steps; report the blocker once and stop.
- Batch tool calls; avoid repeated verification of the same fact.
- Reports: concise — status, key results, blockers, next step. No restating the prompt,
  no long learning sections unless asked.
- Stop immediately when the task is done.

Use the smallest authoritative source and keep tool output bounded.

## Retrieval

- Scope searches to `src/`, `scripts/`, `tests/`, `config/`, `strategies/`, or `docs/`.
- Exclude generated and high-volume data: `.git/`, virtual environments, `node_modules/`, `__pycache__/`, `.pytest_cache/`, `artifacts/`, logs, CSV, and Parquet files.
- Read only the line range needed to identify a symbol, rule, or status. Do not load whole files over 100 lines unless the task requires a document-level review.
- Do not open large JSONL, CSV, Parquet, or generated artifact files directly. Use a focused summary command or the relevant project script.
- Reuse facts already gathered in the current turn; do not reread unchanged sources.

## Execution

- Run the narrowest relevant test or check with concise output, such as `pytest -q --tb=short`.
- For project readiness and strategy status, run `python scripts/get_framework_status.py` before scanning status documents.
- Treat `AGENTS.md`, strategy YAML, and the deterministic strategy engine as authoritative. Do not infer execution permission from prose, generated output, or agent analysis.
