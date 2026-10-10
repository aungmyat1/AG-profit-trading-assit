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

The host-local `config/local/actionability_policy.yaml` must contain the parameter.
The tracked operational policy is a template, not a runtime fallback. Missing or
invalid values log `LSMC_CONFIG_MISSING` once per emitter run and add
`CONFIG_MISSING key=lsmc_min_remaining_reward_fraction` to the Large-SMC summary.
Deployment must run the read-only `scripts/host/preflight_actionability.py`; it
exits nonzero and names the key on failure (see `scripts/host/GO_LIVE.md`).
There is no R:R gate: the owner corrected the mission because v1.1.0 has no
authorized minimum. The ledger records **Large-SMC R:R minimum: OWNER_DECISION_PENDING**.
Detection logic, strategy constants/contracts and execution code are unchanged.

`WatchTracker` archives a `REJECTED` transition with level INFO and its reason.
The existing `host_delivery.telegram_message.should_send` convention accepts only
Large-SMC OPPORTUNITY; INFO rejections are suppressed. Defensive formatting of old
raw events also replaces an ineligible OPPORTUNITY label with an explicit rejection.
Valid opportunity snapshots retain identical serialized bytes. Valid Telegram
text matches the unchanged golden and the formatter on current origin/main
`d8ee56a17795aea064b9741f98cbe3fdb00383a3` with identical synthetic input. The golden
was not regenerated (SHA-256: `05a601a88b2cfa97b3b7ea7132d79d6003da2b9ae3e2458210ff180bab1dd52e`).

SESSION_SUMMARY now includes a counts-only Large-SMC section for `REJECT_NO_STOP`,
`REJECT_NO_TARGET` and `REJECT_STALE`. Its source is the rejection transition archive:
`<journal>/ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/<symbol>/LSMC_WATCH-<transition_id>/<year>/<trading_date>.json`.
`WatchTracker._emit` stores the reason in top-level `reason_codes` and in
`payload.payload.reason_codes`; the summary reads top-level reasons. It counts
unique transition IDs evaluated inside the session's half-open UTC trade window.
The NY trading-date filename does not determine membership; correction wrappers
and duplicate transition IDs never add counts. Unreadable/malformed archives are
skipped and reported as `ARCHIVE_ERROR n=<count>`; the summary still sends.
FX summaries read only EURUSD, GBPUSD, USDJPY and XAUUSD. The separate crypto
summary owns BTCUSD/ETHUSD operational rejection archives; matching journal
entries do not add a second count. No Large-SMC setup details are
included in the summary dictionary or Telegram section.

Offline synthetic tests only, Linux, 2026-10-10; no broker calls or Telegram requests.
Host acceptance and deployment are pending. No logic/edge verification or trading
authority is granted by this delivery-layer change.

Validation (rebased follow-up):

- `python -m pytest -q tests/test_lsmc_actionability.py tests/test_canonical_fx_delivery.py tests/test_lsmc_crypto_session_summary.py tests/test_lsmc_delivery_diagnostics.py`: 92 passed.
- Full-suite result recorded after completion below.

Existing synthetic detection fixtures lack a causal target and now correctly
reject. Delivery/lifecycle tests requiring a positive setup inject an explicit
synthetic target; production detection remains unchanged. The wrong-side-stop
logic-gate test explicitly constructs an OPPORTUNITY to keep testing its L3 rule.
