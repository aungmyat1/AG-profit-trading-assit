---
class: status
state: IMPLEMENTED
owner_reviewed: null
review_by: 2026-11-09
---
# Large-SMC operational actionability gates (2026-10-10)

The v1.1.0 watch output is rejected before alert transitions when its stop or target
is missing, non-finite, on the wrong side of entry, or carries a validation failure.
The reason is `REJECT_NO_STOP` or `REJECT_NO_TARGET`; supplied evidence is retained.
The remaining-reward fraction `(target - current) / (target - entry)` must be at
least `lsmc_min_remaining_reward_fraction: 0.5`. Current is the latest closed M5
price. This is the owner-set operational parameter of 2026-10-10, not a contract
value; a missing/malformed/null parameter or current price fails closed with
`REJECT_STALE`. A touched stop also rejects. LONG and SHORT use the same signed ratio.

The tracked operational policy supplies the parameter; an existing host-local
`config/local/actionability_policy.yaml` wins without fallback and must contain it.
There is no R:R gate: the owner corrected the mission because v1.1.0 has no
authorized minimum. The ledger records **Large-SMC R:R minimum: OWNER_DECISION_PENDING**.
Detection logic, strategy constants/contracts and execution code are unchanged.

`WatchTracker` archives a `REJECTED` transition with level INFO and its reason.
The existing `host_delivery.telegram_message.should_send` convention accepts only
Large-SMC OPPORTUNITY; INFO rejections are suppressed. Defensive formatting of old
raw events also replaces an ineligible OPPORTUNITY label with an explicit rejection.
Valid opportunity snapshots retain identical serialized bytes. Valid Telegram
text matches a golden captured from origin/main `abb5330` with the same synthetic input.

SESSION_SUMMARY now includes a counts-only Large-SMC section for `REJECT_NO_STOP`,
`REJECT_NO_TARGET` and `REJECT_STALE`. Its source is the rejection transition archive:
`<journal>/ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/<symbol>/LSMC_WATCH-<transition_id>/<year>/<trading_date>.json`.
`WatchTracker._emit` stores the reason in top-level `reason_codes` and in
`payload.payload.reason_codes`; the summary reads top-level reasons. It counts
unique transition IDs evaluated inside the session's half-open UTC trade window.
The NY trading-date filename does not determine membership; correction wrappers
and duplicate transition IDs never add counts. Unreadable/malformed archives block
the summary rather than silently reporting zero. No Large-SMC setup details are
included in the summary dictionary or Telegram section.

Offline synthetic tests only, Linux, 2026-10-10; no broker calls or Telegram requests.
Host acceptance and deployment are pending. No logic/edge verification or trading
authority is granted by this delivery-layer change.

Validation:

- `python -m pytest -q tests/test_lsmc_actionability.py tests/test_v1_large_smc_110_watch.py tests/test_lsmc_alert_dedup.py tests/test_lsmc_v110_logic_gate.py tests/test_lsmc_v111_candidate_audit.py --tb=short`: 91 passed.
- `python -m pytest -q tests/test_telegram_message_format.py tests/test_telegram_message_metadata.py tests/test_host_go_live_kit.py tests/test_v1_large_smc_import_boundary.py --tb=short`: 100 passed, 1 skipped (live MT5 unavailable), verified in two batches after fixture updates.
- `python -m pytest -q tests/test_host_go_live_kit.py -k scheduled_lsmc_rejection --tb=short`: 1 passed, 84 deselected.
- `python -m pytest -q tests/test_docs_live.py tests/test_context_pack.py tests/test_generated_files_ci.py --tb=short`: 36 passed, 1 skipped.
- `python scripts/check_docs_links.py`: PASS; `git diff --check`: PASS.
- Summary follow-up: `python -m pytest -q tests/test_canonical_fx_delivery.py tests/test_telegram_delivery_adapter.py --tb=short`: 111 passed.

Existing synthetic detection fixtures lack a causal target and now correctly
reject. Delivery/lifecycle tests requiring a positive setup inject an explicit
synthetic target; production detection remains unchanged. The wrong-side-stop
logic-gate test explicitly constructs an OPPORTUNITY to keep testing its L3 rule.
