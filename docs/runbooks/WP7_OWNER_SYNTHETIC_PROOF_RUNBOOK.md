# WP7 Owner-Machine Synthetic Telegram Delivery Proof — Runbook

## Purpose

Prove Stage 1's exactly-once FX ticket-delivery infrastructure can deliver one real,
explicitly-authorized, non-strategy informational message to Telegram through the
actual `MESSAGE_DELIVERY` authorization path — without ever populating the shipped
Telegram allow-list, without changing tracked configuration, and without touching
broker/execution code. This is the synthetic proof only. The later, separate natural
READY proof (a real strategy-generated ticket) is a different, later milestone and is
explicitly out of scope here.

This document is documentation and is tracked. The credential-using helper script it
describes is **not** tracked and is not included in any commit — see "Owner helper
location" below.

## Source commit and dependency-closure pin

```text
WP7_REVIEWED_SOURCE_COMMIT = 3161287
```

That commit contains the full WP7 message-delivery runtime plus the token
repr-safety fix (`TelegramDestinationConfig.bot_token` excluded from dataclass
`repr`/`str`). The pin covers every first-party production path the helper actually
executes or that materially participates in destination validation, ticket identity,
delivery-state persistence, attempt journaling, retry classification, Telegram
request construction, delivery result parsing, or idempotency — identified by
reviewing the helper's own imports and the imports reached transitively by
`scheduler_integration._build_message_delivery_closure()`:

```text
PINNED_PRODUCTION_DEPENDENCY_SURFACE:
  src/ticket_delivery/                      (identity, delivery_store, models, policy,
                                              scheduler_integration, telegram_adapter,
                                              attempt_journal)
  src/notifications/telegram_client.py      (the only send_message() implementation used)
  config/ticket_delivery.yaml               (signed policy values the helper reuses)

dependency_surface_method = manual review of helper imports + _build_message_delivery_closure()'s
                             transitive imports, pinned as an explicit path list (not
                             auto-derived) -- re-review is required if that closure's own
                             imports change.
```

The helper pins itself to this commit by requiring these paths to be byte-identical to
that commit's tree (`git diff 3161287 HEAD -- <pinned paths>` must be empty), rather
than requiring `HEAD` to literally equal `3161287` — a later documentation-only commit
(such as this runbook's own commit) legitimately advances `HEAD` without touching WP7
source, and the helper must not false-negative on that. It also requires `3161287` to
be an ancestor of `HEAD` (not a rewritten/divergent history). If any pinned path's
content ever changes, the helper must be re-reviewed and re-pinned to a new commit
before it may run again — `WP7_SOURCE_PIN_MISMATCH`, not a silent re-pin.

## Security prerequisites — token-rotation gate (hard stop)

No external Telegram request may occur until **all** of the following are true:

```text
old (previously exposed) token revoked        = CONFIRMED
replacement token installed in src/.env       = CONFIRMED
old token independently confirmed invalid     = CONFIRMED
```

None of the following, individually or together, satisfies this gate:
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` merely being present, the new token having
valid Telegram token syntax, the dataclass repr-safety fix existing, or the WP7 test
suite passing. Those are necessary but not sufficient.

**This gate is enforced interactively, not by editing source.** An earlier revision of
this helper used a module-level `OWNER_CONFIRMS_TOKEN_ROTATION_COMPLETE = False`
constant that had to be hand-edited to `True` before running — that mechanism was
removed because it let the reviewed-and-hashed artifact diverge from the executed one
(editing the file after it was hashed silently invalidates the recorded hash below).
The current helper instead requires you to type an exact phrase at a live interactive
terminal prompt immediately before it proceeds:

```text
ROTATION-CONFIRMED
```

Typing this phrase attests to all three of:

1. The previous (exposed) Telegram bot token was revoked through BotFather.
2. The replacement Telegram bot token is installed locally (`src/.env`).
3. You authorize exactly ONE synthetic, non-trading Telegram delivery for this WP7
   proof — nothing more, no ongoing delivery authority.

This is your own attestation, not an independent technical verification that the old
token is invalid — the helper does not test the old token itself (repository security
policy prohibits that). Expected resulting evidence fields:

```text
owner_rotation_confirmation = YES
replacement_token_present   = YES
old_token_automated_test    = NOT_PERFORMED
rotation_gate                = SATISFIED_BY_OWNER_CONTROL
```

Do not read or report this as `TOKEN_ROTATION_TECHNICALLY_VERIFIED` — that claim would
require independent evidence this helper does not, and by policy should not, gather.

**Fail-closed behavior**, all verified to return `False`/abort before any repository
or network action:

- wrong phrase → `OWNER_CONFIRMATION_FAILED`
- blank input → `OWNER_CONFIRMATION_FAILED`
- EOF / Ctrl-D / `KeyboardInterrupt` → `OWNER_CONFIRMATION_FAILED`
- non-interactive context (`sys.stdin`/`sys.stdout` not a real terminal — piped,
  redirected, or run from a non-interactive harness) → refuses before even prompting
- any other input exception → `OWNER_CONFIRMATION_FAILED`

No environment variable, CLI flag, or source-code constant can substitute for the
live interactive phrase.

## Owner authorization requirements

This proof is scoped to exactly:

```text
MESSAGE_TYPE            = WP7_SYNTHETIC_OPERATIONAL_PROOF
MAX_EXTERNAL_MESSAGES   = 1
STRATEGY_SIGNAL         = NO
BROKER_EXECUTION        = PROHIBITED
DEMO_EXECUTION          = PROHIBITED
LIVE_EXECUTION          = PROHIBITED
DESTINATION             = your own already-configured TELEGRAM_CHAT_ID (owner-controlled)
POST_TEST_MODE          = ARCHIVE_ONLY (implicit — see "Tracked configuration" below)
```

It does not authorize ongoing delivery, strategy-generated messages, or any
execution/order action.

## Pre-run checks (performed by the helper itself, in this order)

1. `git status --short` is empty (clean working tree).
2. Source pin: the full pinned production dependency surface matches the reviewed
   commit's tree (see "Source commit and dependency-closure pin").
3. On-disk `config/ticket_delivery.yaml` still reads `mode: ARCHIVE_ONLY` with an
   empty `authorized_chat_ids` allow-list (belt-and-suspenders static check, on top
   of the fact this file is never written by the helper).
4. Execution-boundary self-scan: the helper's own source text contains no reference
   to any forbidden execution/broker module or call (see "Execution prohibition").
5. `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` present in the environment (booleans
   only, never printed; `TELEGRAM_CHAT_ID` also checked to parse as an integer).
6. Pre-existing synthetic delivery state is eligible (see "Pre-existing synthetic
   state" below) — inspected *before* any network-capable closure is constructed.
7. **Before typing the confirmation phrase**, manually compare the `helper_self_sha256`
   the helper prints at startup against `helper_sha256` recorded below. If they
   differ: stop, re-review, do not proceed. (An automated self-check is not
   meaningful here — tampering with the file changes both the code and any embedded
   expected-hash constant together, so this is a manual verification step, not an
   in-code gate.)
8. Interactive owner confirmation (the `ROTATION-CONFIRMED` phrase) — see above. This
   runs *last*, after every mechanical safety gate, so the owner is never asked to
   authorize a run that would fail an earlier check anyway.

Any failure aborts before any delivery-state write or network call.

## Synthetic message contract

Canonical synthetic identity (minted via the real, unmodified
`ticket_delivery.identity.logical_ticket_id()` — cannot collide with any real
`ST_ASIAN_SWEEP_5R_V1|...` ticket):

```text
SYNTHETIC_TEST|1.0.0|TESTPAIR|SYNTHETIC_CYCLE|2026-09-08
```

```text
message_type          = WP7_SYNTHETIC_OPERATIONAL_PROOF
strategy_signal        = false
execution_authorized   = false
strategy_id            = NONE
symbol                 = NONE
direction              = NONE
entry / stop / target  = NONE
```

Visible message text:

```text
AG SYSTEM DELIVERY TEST
WP7 operational delivery verification

NOT A TRADE SIGNAL
NO BROKER EXECUTION AUTHORITY

This message verifies Stage-1 external ticket-delivery infrastructure only.
```

No BUY/SELL language, no executable price levels, no position sizing.

## Delivery-state persistence before send (corrected terminology)

Required order, enforced by the helper:

```text
construct synthetic identity
→ delivery-state persistence (TicketDeliveryStore.ensure_ready_to_deliver(),
  durably persisted to journal/ticket_delivery/state/delivery_records.json)
→ construct the real production deliver() closure
  (scheduler_integration._build_message_delivery_closure())
→ exactly one provider request sequence (TelegramClient.send_message(), possibly
  retried per the signed policy -- see "Provider-attempt measurement")
```

**This is `delivery_state_persisted_before_send`, not `archive_before_send`.**
`TicketDeliveryStore.ensure_ready_to_deliver()` proves durable delivery-state
persistence only. It does not invoke the project's canonical per-cycle decision
archive layer (`ticket_delivery.archive.archive_cycle_decision`), which is shaped
around a real strategy decision object and does not apply to a synthetic, non-strategy
identity. An earlier revision of this runbook used the label `archive_before_send` for
this step, which overstated what actually happens — corrected here rather than adding
archive behavior merely to keep the old label accurate.

```text
canonical_archive_completed_before_send = NOT_PART_OF_THIS_SYNTHETIC_HELPER
delivery_state_persisted_before_send    = PASS (what the helper actually proves)
```

If delivery-state persistence fails, the helper does not proceed to construct the
closure or send.

## Provider-attempt measurement (measured, never hard-coded)

One logical synthetic message does **not** imply one HTTP/provider request. The
signed retry contract may make up to 3 provider attempts for that one logical
message (attempt 1 immediate, attempt 2 at T+30s, attempt 3 at T+90s). The helper
never assumes or prints a hard-coded count; it measures three distinct things after
every run:

```text
logical_message_count            = 1 (fixed -- one synthetic identity, this proof
                                    never mints a second one even on retry)
provider_attempt_count           = the durable DeliveryRecord.attempt_number after
                                    the run (authoritative -- incremented once per
                                    claim_for_delivery() call, i.e. once per actual
                                    provider attempt), cross-checked by an independent
                                    count of matching entries in the durable attempt
                                    journal (journal/ticket_delivery/state/
                                    attempt_journal.jsonl)
provider_confirmed_delivery_count = 1 only if the final durable state is DELIVERED
                                    AND a provider-confirmed message identity was
                                    recorded; 0 otherwise
```

An `AMBIGUOUS` outcome stops the helper immediately — it never auto-retries an
ambiguous result, and `provider_confirmed_delivery_count` is `0` in that case.

## Authoritative success source and state divergence

Success is never inferred from console output, a truthy return value, or a
transiently-populated local variable. The helper reads the **durable**
`TicketDeliveryStore` record after the send and requires:

```text
durable record.state                 == STATE_DELIVERED (ticket_delivery.models)
durable record.provider_response_id  is not None
```

both to be true before reporting success or proceeding to the idempotency check. If
the transient `DeliveryOutcome.final_state` returned by `deliver()` ever disagrees
with the durable record's state, the helper reports `PROOF_STATE_DIVERGENCE` and
exits nonzero rather than trusting either value. Any other terminal or non-terminal
state (`DELIVERY_FAILED_TERMINAL`, `DELIVERY_FAILED_RETRYABLE` still unresolved after
the in-process retry loop, `DELIVERY_CLAIMED`, or anything unrecognized) is reported
exactly and never classified as success. Canonical state names come from
`ticket_delivery.models` — the helper imports the real constants
(`STATE_DELIVERED`, `STATE_DELIVERY_AMBIGUOUS`), it does not re-declare string
literals that could drift from the production enum.

## Execution prohibition

The helper imports only `notifications.telegram_client`, `ticket_delivery.*`, and
stdlib — no MT5/Bybit/Binance/MEXC or execution-adapter import exists anywhere in its
dependency path. `src/ticket_delivery/` has zero broker/execution imports, AST-verified
by `tests/test_ticket_delivery_execution_boundary.py` (unchanged by this task). The
helper additionally self-scans its own source text at startup for any reference to
`execution.executor`, `execution.mt5_gateway`, `assistant.commands.execute_command`,
`mt5.management_gateway`, `order_check`, `order_send`, or
`authorization.telegram_gateway`, and refuses to proceed if any are found
(`execution_boundary_self_scan`).

## Idempotency proof

After a definite durable `DELIVERED` result with a confirmed provider identity, the
helper evaluates the same logical identity a second time using a fake HTTP session
whose `post()` raises `AssertionError` if invoked at all — proving the claim lock
blocks any further network call. Expected: second call `claimed = False`,
`idempotent_second_evaluation = NO_SEND_ALREADY_DELIVERED`, zero network calls.

## Pre-existing synthetic state

Before constructing any network-capable closure, the helper inspects durable state
for the fixed synthetic logical identity
(`SYNTHETIC_TEST|1.0.0|TESTPAIR|SYNTHETIC_CYCLE|2026-09-08`) and never deletes,
rewrites, resets, or reclaims prior evidence to obtain a "clean" run:

```text
no record yet
  → eligible for a first synthetic proof; proceeds toward owner confirmation

record state == DELIVERED
  → PROOF_ALREADY_COMPLETED_NO_SEND; reports the existing durable evidence
    (measured attempt count, confirmed-delivery status), verifies idempotency
    locally with zero network access, exits nonzero (this run performed no new
    send/proof -- see "Exit code semantics" below)

record state == DELIVERY_AMBIGUOUS
  → stop; manual reconciliation required via resolve_ambiguous_outcome(); never
    auto-resolved by this helper

record state == DELIVERY_CLAIMED, DELIVERY_FAILED_RETRYABLE, or
DELIVERY_FAILED_TERMINAL
  → stop; the exact state is reported; this one-time helper never silently
    continues or reclaims an in-progress or failed prior attempt

any other/unrecognized state
  → stop; exact state reported
```

## Exit code semantics

Exit code `0` occurs **only** when every proof invariant for a fresh run actually
passed this run: durable state reached `DELIVERED`, a provider-confirmed identity was
recorded, and the idempotency check ran clean. Every other path — including
"nothing needed to happen because it was already `DELIVERED` from a prior run" —
returns nonzero, so "this run performed nothing" never looks identical to "this run
proved delivery" to anything scripting around this helper's exit code.

## Tracked configuration — must remain unchanged

`config/ticket_delivery.yaml` is never read or written by the helper. The
`MESSAGE_DELIVERY` mode and the one-entry destination allow-list used for the proof
exist only as an in-memory `TicketDeliveryIntegrationConfig` object for the lifetime
of the helper's process — never serialized to disk. Because of this, there is no
tracked-configuration rollback step: the file was never touched. The helper verifies
`git status --short` before and after the run to make this explicit, and diffs
`config/ticket_delivery.yaml` (expected empty) as confirmation.

Required end state, verified by the helper:

```text
disk_mode_after            = ARCHIVE_ONLY   (unchanged the whole time)
disk_authorized_chat_count = 0               (unchanged the whole time)
```

## Owner helper location

The credential-using helper (`wp7_owner_synthetic_proof.py`) is a **one-time,
owner-controlled proof tool**. It is intentionally kept outside this Git worktree and
is not tracked, not committed, and not referenced from any tracked path. `.gitignore`
was not modified to accommodate it — it was never inside the repository to begin
with. Ask the assistant session that prepared it for its current local path, or
regenerate it from this runbook's contract if it's been removed.

```text
HELPER_TYPE     = ONE_TIME_OWNER_TOOL
TRACKED         = NO
COMMIT_PINNED   = YES (EXPECTED_SOURCE_COMMIT = 3161287, tree-diff pinned across the full
                  PINNED_PRODUCTION_DEPENDENCY_SURFACE, not HEAD-equality pinned)
DISPOSABLE      = YES
```

It uses one private implementation function,
`ticket_delivery.scheduler_integration._build_message_delivery_closure()`. That use is
acceptable only because this helper is one-time, owner-controlled, untracked, and
commit-pinned with a recorded hash (below) — it is not a precedent for treating that
function as a stable operator interface. If WP7 later needs a reusable, supported
operational CLI, that must be a separately designed, tested, and governed public
interface — not a promotion of this helper.

## Reproducibility record

```text
source_commit           = 3161287
helper_hash_algorithm   = SHA256
helper_sha256           = a4f352357759e3bb011e10c4dff1f54c8f879ad339aa507011bf7050589ea5c6
helper_hash_recorded    = YES
```

Superseded prior hashes, in order:

```text
sha256 = 8c342ea9cf91167c4a79bd8cadabe1b08e2815f7cafb25d0723cd52aa81ddcb3
status = SUPERSEDED_BEFORE_EXECUTION
reason = pre-hardening revision using the editable OWNER_CONFIRMS_TOKEN_ROTATION_COMPLETE
         source constant (verified to exist and match this exact value before being
         superseded; never executed)

sha256 = 75c88111c5cf3d1597821fff4f87c9cd9985b70c625c1f99586ab5dc473e583d
status = SUPERSEDED_BEFORE_EXECUTION
reason = first revision with the interactive ROTATION-CONFIRMED gate, before the
         proof-integrity hardening pass below (canonical-state constants, measured
         attempt counts, strict DELIVERED+confirmed-identity success gate, state
         divergence check, pre-existing-state handling, corrected persistence
         terminology, self-printed hash for manual comparison, execution-boundary
         self-scan bugfix -- see "No-network validation" below); verified to exist
         and match this exact value before being superseded; never executed.
```

**The reviewed helper hash must equal the executed helper hash.** If the helper file
changes after `helper_sha256` above was recorded — for any reason, including a
seemingly trivial edit — it must be re-reviewed and re-hashed before use, and this
record updated accordingly. Do not run a helper whose current SHA-256 does not match
`helper_sha256` above; the helper also prints its own `helper_self_sha256` at startup
so this can be verified visually, immediately before typing the confirmation phrase
(see "Pre-run checks" step 7). The hash identifies executable procedure provenance
only — it is not derived from, and does not include, any credential.

## No-network validation

Before this final hash was recorded, the hardened helper's pure gate functions were
imported (module import only — `main()` never runs on import, it is guarded by
`if __name__ == "__main__"`) and exercised behaviorally, with zero real network
transport ever constructed and zero real credentials ever loaded, in a standalone
pytest harness (20 tests, all passing):

```text
wrong phrase                              → fails closed
blank input                               → fails closed
EOF                                       → fails closed
non-interactive context                   → fails closed BEFORE prompting at all
correct phrase                            → gate itself returns True (no transport
                                            constructed by the gate function -- proven
                                            statically, see below)
secret sentinel never appears in prompt   → confirmed
pre-existing state: absent                → eligible
pre-existing state: DELIVERED             → not eligible, correct reason reported
pre-existing state: AMBIGUOUS             → not eligible, correct reason reported
pre-existing state: DELIVERY_FAILED_TERMINAL → not eligible, correct reason reported
pre-existing state: DELIVERY_CLAIMED      → not eligible, correct reason reported
attempt count                             → proven to come from the durable
                                            record.attempt_number field (simulated a
                                            2-attempt sequence via the real, already-
                                            tested TicketDeliveryStore primitives;
                                            asserted attempt_number == 2, not a
                                            hard-coded 1)
attempt-journal cross-check               → counts only matching logical_ticket_id
                                            entries
execution-boundary self-scan              → passes against the real helper (this test
                                            caught and fixed a real bug: the scanner's
                                            own denylist tuple definition was
                                            triggering a permanent false positive
                                            against itself)
disk-config check: unsafe mode            → fails closed
disk-config check: non-empty allow-list   → fails closed
disk-config check: real repo config       → passes (ARCHIVE_ONLY, empty allow-list)
source-pin check: real repo               → passes
static proof: no TelegramClient/requests
reference in any pure gate function's
source                                    → confirmed via inspect.getsource()
```

This is real behavioral proof for the fail-closed paths, not code review alone —
though it does not exercise the actual Telegram-facing code past the confirmation
gate (deliberately: that code is only reachable after the interactive phrase, and
this preparation task never types it against a network-capable path).

## Non-secret evidence schema

The helper's run output (and any evidence recorded from it) may include only:

```text
source_commit
source_pin_verified
owner_rotation_confirmation         (YES/NO — the interactive attestation, not the tokens)
replacement_token_present           (boolean)
old_token_automated_test            (always NOT_PERFORMED, by policy)
delivery_state_persisted_before_send (PASS/FAIL)
canonical_archive_completed_before_send (NOT_PART_OF_THIS_SYNTHETIC_HELPER — always)
logical_ticket_id
logical_message_count               (expected: 1)
provider_attempt_count              (measured — from record.attempt_number + journal
                                      cross-check; NOT assumed to be 1)
provider_confirmed_delivery_count   (0 or 1 — derived from durable state + identity)
delivery_result                     (the durable state, e.g. DELIVERED)
provider_message_identity_saved     (YES, REDACTED / NO)
execution_calls                     (expected: 0)
idempotent_second_evaluation        (e.g. NO_SEND_ALREADY_DELIVERED)
disk_mode_after                     (expected: ARCHIVE_ONLY)
disk_authorized_chat_count          (expected: 0)
```

Never record: the bot token, the chat ID, any Telegram request URL, authorization
headers, the raw provider response body, or an environment dump.

## Failure handling

| Condition | Helper behavior |
|---|---|
| Working tree not clean | Abort before any confirmation prompt. |
| Source pin mismatch (any pinned production path) | Abort before any confirmation prompt. `SOURCE_COMMIT_MISMATCH`. Re-review and re-pin required. |
| Disk config not `ARCHIVE_ONLY` / non-empty allow-list | Abort before any confirmation prompt. `DISK_CONFIG_UNSAFE`. |
| Execution-boundary self-scan finds a forbidden reference | Abort before any confirmation prompt. `EXECUTION_BOUNDARY_VIOLATION`. |
| Pre-existing state is `DELIVERED` | `PROOF_ALREADY_COMPLETED_NO_SEND`; reports existing evidence, zero network access, exits nonzero. |
| Pre-existing state is `DELIVERY_AMBIGUOUS`, `DELIVERY_CLAIMED`, `DELIVERY_FAILED_RETRYABLE`, or `DELIVERY_FAILED_TERMINAL` | Stop before confirmation prompt; exact state reported; never silently continued or reclaimed. |
| Owner confirmation: wrong phrase, blank, EOF, non-interactive context, or input exception | `OWNER_CONFIRMATION_FAILED`, `NETWORK_CALLS = 0`. |
| Token/chat id missing | Abort before any network call — this is the existing fail-closed `TelegramDestinationConfig`/`_build_message_delivery_closure()` behavior, not a defect. |
| In-memory `outcome.final_state` disagrees with the durable record's state | `PROOF_STATE_DIVERGENCE`. Neither value is trusted; not reported as success. |
| Final durable state is not `DELIVERED`, or `DELIVERED` without a confirmed provider identity | Not reported as a successful proof; exits nonzero. |
| `DELIVERY_FAILED_TERMINAL` | Not retried automatically. Check bot/chat configuration. |
| `DELIVERY_AMBIGUOUS` | Stop immediately. Do not re-run. Manually verify in the Telegram chat, then use `resolve_ambiguous_outcome()` from a Python shell to record the true outcome once you know it. |
| Any exception before send | Nothing was sent — delivery-state persistence and closure construction happen before the provider call. |

## Stage-1 relationship

This proof, once passed, satisfies only the "separately authorized synthetic delivery
proof" line item of Stage 1's exit criteria. It does not by itself close Stage 1.
Remaining items after a passing synthetic proof: a fresh, naturally strategy-generated
READY ticket (age ≤ 60 minutes at delivery time) delivered once, durably `DELIVERED`,
with the following scheduler tick sending nothing and zero execution calls. Until that
natural proof also passes, Stage 1 remains **not closed**, and Stage 2+ remains
blocked regardless of this synthetic proof's outcome.
