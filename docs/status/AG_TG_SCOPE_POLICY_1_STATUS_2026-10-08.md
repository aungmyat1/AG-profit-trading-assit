---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# TG-SCOPE-POLICY-1 — tracked Telegram immediate-send scope (2026-10-08)

Based on `main` after PR #79 merged at `bae2ceda6d371aaa6e509668afe42ded280f950a`.
This change makes the Telegram send ceiling explicit and shared by both sender paths.

## Policy and behavior

`config/ticket_delivery.yaml` permits immediate sends only for `TICKET_READY` and
`LSMC_OPPORTUNITY`. `WATCH_READY` and `INFO_ONLY_*` remain disabled with
`PENDING_OWNER_DECISION C16`. The host-local legacy and canonical delivery overrides can
select a subset; an attempted widening returns `SCOPE_WIDENING_REJECTED` and disables
delivery. Recipient IDs and secrets remain host-local, and the tracked default remains
`ARCHIVE_ONLY`.

`scripts/host/verify_objective.py` reports each sender's effective scope and fails if either
path exceeds the tracked ceiling. `status/facts.json` records the tracked scope, and the
generated Context Pack displays the enabled and disabled scope. No strategy authorization,
broker call, or live Telegram request was changed or exercised.

## Verification

Environment: Linux, Python 3.12, 2026-10-08.

- `uv run --with-requirements requirements.txt pytest -q --tb=short` — 1,359 passed,
  3 skipped.
- `scripts/host/verify_objective.py` — `RESULT: PASS`; both effective scopes were reported.
- `scripts/docs/collect_facts.py --check`, `scripts/docs/build_context_pack.py --check`,
  `cog --check PROJECT_STATUS.md`, and `scripts/docs/check_drift.py` — pass.
- `tests/test_docs_live.py` — 16 passed, 1 skipped; prose-drift check had 0 warnings.

Stale-check reports its pre-existing warn-only missing classifications for
`AGP_TG_01_OFFLINE_2026-10-08.md` and `DOCS_LIVE_4_CLAIM_AUDIT_2026-10-08.md`; the latter was
not edited. Host and Telegram live acceptance remain `NOT_EVALUATED` / `NOT_AUTHORIZED`.
