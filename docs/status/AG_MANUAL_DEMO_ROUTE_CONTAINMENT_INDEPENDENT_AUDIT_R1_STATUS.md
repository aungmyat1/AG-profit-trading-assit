# AG Profit Trading — Manual Demo Route Containment Independent Audit R1

## Classification

`MANUAL_DEMO_ROUTE_CONTAINMENT_INDEPENDENT_AUDIT_FAIL`

The source-level containment is present, but this audit could not complete the required independent runtime gates because the detached candidate worktree has no installed frontend dependencies. This is an evidence-completeness failure, not evidence that the candidate route is unsafe.

## Lineage and scope

- Base SHA: `595ca08b9cc9c6f7b54b017f9748285ad7d44a87`
- Audited SHA: `f26600186c0a328dab42490952eabd87b580a408`
- `origin/main`: `87e2da798f827caf95e8c6e58916b394641c98fb`
- Candidate parent is the requested base; the current worktree HEAD is `04611529b4ce45373c18f58ee60bfa0ee496b562`, not the audited SHA.
- `595ca08..f266001` changes only `PROJECT_STATUS.md`, `docs/README.md`, `web/package.json`, `web/server.ts`, and two new web test files. No strategy or registry files are changed.
- Diff scope is valid for the stated containment change: the legacy handler spawning `scripts/web_execute_trade.py --confirm` is replaced by an unconditional `410 EXECUTION_ROUTE_RETIRED` response.

## Required evidence

- Baseline bypass: source-level reproduction confirmed: the base handler accepted `user_confirmed=true`, DEMO account, real API mode, and valid fields, then spawned `web_execute_trade.py` with `--confirm`. A live sentinel reproduction was not completed in this audit.
- Candidate route: source inspection confirms the handler is unconditional and returns `410 EXECUTION_ROUTE_RETIRED`; the committed R1 suite covers real/mock mode, credentials, malformed bodies, repeated requests, state/log hashes, and spawn interception.
- Runtime containment suite: `NOT RUN` — detached worktree lacked `web/node_modules/tsx`; no dependency installation was performed.
- Positive-control spawn and process counts: `NOT ESTABLISHED` by runtime execution.
- Real `order_check` calls: `0` observed during this audit.
- Real `order_send` calls: `0` observed during this audit.
- Demo orders sent: `0`.
- Live orders sent: `0`.

## HTTP execution-route inventory

Static inspection found the retired `/api/execution/manual-demo` route and the existing WP0A retired execution routes in `web/server.ts`. The candidate comment identifies the canonical Python path as owner decision followed by `authorize-demo`. A complete independent runtime trace of every HTTP-accessible bridge was not completed; alternate-bypass status is therefore `NOT PROVEN`.

## Canonical-path preservation

The candidate diff does not modify the canonical Python API, owner authentication, R5C, idempotency, or strategy authorization files. This is source/diff evidence only; owner-auth, `authorize-demo`, R5C, idempotency, Demo-only, and Live-prohibition regression suites were not run in the dependency-free detached worktree.

## Side effects and scope

No broker process was run and no broker call was possible from the audit commands. The current user worktree was not cleaned or rewritten. Existing unrelated modifications remain: status documents, pre-push hook, state ledgers, `.devcontainer/`, and a scheduler prospective document. Scheduler state remains `SCHEDULER_NATURAL_CYCLE_NOT_OBSERVED`; scheduler remediation was not evaluated.

## Documentation candidate

`56bbdd7` is separate documentation-only history and was not used to determine technical containment. Keep it separate pending an independent documentation review; do not treat it as runtime evidence.

## Recommendation

Do not recommend advancing `integration/platform-pre-main` on this audit result. Install the candidate's declared dependencies in an isolated worktree and rerun the required sentinel, route, canonical-path, and regression suites from the exact audited SHA. If all P10 conditions pass, issue a new audit classification and then require the publication gate at the exact integrated SHA.

