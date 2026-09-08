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

## Source commit

```text
WP7_REVIEWED_SOURCE_COMMIT = 3161287
```

That commit contains the full WP7 message-delivery runtime plus the token
repr-safety fix (`TelegramDestinationConfig.bot_token` excluded from dataclass
`repr`/`str`). The owner helper pins itself to this commit by requiring the current
`src/ticket_delivery/` tree and `config/ticket_delivery.yaml` to be byte-identical to
that commit's tree (`git diff 3161287 HEAD -- src/ticket_delivery config/ticket_delivery.yaml`
must be empty), rather than requiring `HEAD` to literally equal `3161287` — a later
documentation-only commit (such as this runbook's own commit) legitimately advances
`HEAD` without touching WP7 source, and the helper must not false-negative on that.
If WP7 source ever changes, the helper must be re-reviewed and re-pinned to the new
commit before it may run again.

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

## Pre-run checks (performed by the helper itself)

1. `git status --short` is empty (clean working tree).
2. Source pin: WP7 source tree matches the reviewed commit's tree (see "Source
   commit").
3. On-disk `config/ticket_delivery.yaml` still reads `mode: ARCHIVE_ONLY` with an
   empty `authorized_chat_ids` allow-list (belt-and-suspenders static check, on top
   of the fact this file is never written by the helper).
4. Interactive owner confirmation (the `ROTATION-CONFIRMED` phrase) — see above. This
   runs *after* the three checks above so nothing is prompted for against an unsafe
   or unreviewable repository state.
5. `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` present in the environment (booleans
   only, never printed).
6. `TELEGRAM_CHAT_ID` parses as an integer.

Any failure aborts before any archive write or network call.

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

## Archive-before-send requirement

Required order, enforced by the helper:

```text
construct synthetic identity
→ archive (TicketDeliveryStore.ensure_ready_to_deliver(), durably persisted to
  journal/ticket_delivery/state/delivery_records.json)
→ construct the real production deliver() closure
  (scheduler_integration._build_message_delivery_closure())
→ exactly one provider request (TelegramClient.send_message())
```

If archiving fails, the helper does not proceed to construct the closure or send.

## Maximum provider-call policy

At most one logical external message. The helper does not intentionally trigger
retries; the existing, already-tested retry contract (attempt 1 immediate, attempt 2
at T+30s, attempt 3 at T+90s, 3 max) may apply only to a naturally occurring
transient failure. An `DELIVERY_AMBIGUOUS` outcome stops the helper immediately —
it never auto-retries an ambiguous result.

## Execution prohibition

The helper imports only `notifications.telegram_client`, `ticket_delivery.*`, and
stdlib — no MT5/Bybit/Binance/MEXC or execution-adapter import exists anywhere in its
dependency path. `src/ticket_delivery/` has zero broker/execution imports, AST-verified
by `tests/test_ticket_delivery_execution_boundary.py` (unchanged by this task).

## Idempotency proof

After a definite `DELIVERED` result, the helper evaluates the same logical identity a
second time using a fake HTTP session whose `post()` raises `AssertionError` if
invoked at all — proving the claim lock blocks any further network call. Expected:
second call `claimed = False`, zero network calls.

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
COMMIT_PINNED   = YES (EXPECTED_SOURCE_COMMIT = 3161287, tree-diff pinned, not HEAD-equality pinned)
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
helper_sha256           = 75c88111c5cf3d1597821fff4f87c9cd9985b70c625c1f99586ab5dc473e583d
helper_hash_recorded    = YES
```

Superseded prior hash (from the pre-hardening revision that used the editable
`OWNER_CONFIRMS_TOKEN_ROTATION_COMPLETE` source constant — removed for the reason
described above):

```text
prior_helper_sha256 = 8c342ea9cf91167c4a79bd8cadabe1b08e2815f7cafb25d0723cd52aa81ddcb3
prior_hash_status    = SUPERSEDED_BEFORE_EXECUTION  (verified to exist and match this
                        exact recorded value before being superseded; never executed)
```

**The reviewed helper hash must equal the executed helper hash.** If the helper file
changes after `helper_sha256` above was recorded — for any reason, including a
seemingly trivial edit — it must be re-reviewed and re-hashed before use, and this
record updated accordingly. Do not run a helper whose current SHA-256 does not match
`helper_sha256` above. The hash identifies executable procedure provenance only — it
is not derived from, and does not include, any credential.

## Non-secret evidence schema

The helper's run output (and any evidence recorded from it) may include only:

```text
source_commit
source_pin_verified
owner_rotation_confirmation     (YES/NO — the interactive attestation, not the tokens)
replacement_token_present       (boolean)
old_token_automated_test        (always NOT_PERFORMED, by policy)
archive_before_send             (PASS/FAIL)
logical_ticket_id
logical_message_count           (expected: 1)
provider_call_count             (expected: 1)
delivery_result                 (e.g. DELIVERED)
provider_message_identity_saved (YES, REDACTED / NO)
execution_calls                 (expected: 0)
idempotent_second_evaluation    (e.g. NO_SEND_ALREADY_DELIVERED)
disk_mode_after                 (expected: ARCHIVE_ONLY)
disk_authorized_chat_count      (expected: 0)
```

Never record: the bot token, the chat ID, any Telegram request URL, authorization
headers, the raw provider response body, or an environment dump.

## Failure handling

| Condition | Helper behavior |
|---|---|
| Working tree not clean | Abort before any confirmation prompt. |
| Source pin mismatch | Abort before any confirmation prompt. `SOURCE_COMMIT_MISMATCH`. Re-review and re-pin required. |
| Disk config not `ARCHIVE_ONLY` / non-empty allow-list | Abort before any confirmation prompt. `DISK_CONFIG_UNSAFE`. |
| Owner confirmation: wrong phrase, blank, EOF, non-interactive context, or input exception | `OWNER_CONFIRMATION_FAILED`, `NETWORK_CALLS = 0`. |
| Token/chat id missing | Abort before any network call — this is the existing fail-closed `TelegramDestinationConfig`/`_build_message_delivery_closure()` behavior, not a defect. |
| `DELIVERY_FAILED_TERMINAL` | Not retried automatically. Check bot/chat configuration. |
| `DELIVERY_AMBIGUOUS` | Stop immediately. Do not re-run. Manually verify in the Telegram chat, then use `resolve_ambiguous_outcome()` from a Python shell to record the true outcome once you know it. |
| Any exception before send | Nothing was sent — archive and closure construction happen before the provider call. |

## Stage-1 relationship

This proof, once passed, satisfies only the "separately authorized synthetic delivery
proof" line item of Stage 1's exit criteria. It does not by itself close Stage 1.
Remaining items after a passing synthetic proof: a fresh, naturally strategy-generated
READY ticket (age ≤ 60 minutes at delivery time) delivered once, durably `DELIVERED`,
with the following scheduler tick sending nothing and zero execution calls. Until that
natural proof also passes, Stage 1 remains **not closed**, and Stage 2+ remains
blocked regardless of this synthetic proof's outcome.
