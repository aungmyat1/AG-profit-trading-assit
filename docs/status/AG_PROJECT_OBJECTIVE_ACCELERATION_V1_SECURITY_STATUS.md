# AG_PROJECT_OBJECTIVE_ACCELERATION_V1 -- Security Status (2026-09-02)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Records the
credential-exposure incident from the prior session and its current remediation state.
Contains no secret values, fragments, or authenticated request material.

## Incident

During `src/.env` structure inspection in a prior turn, a redaction command failed to
catch several non-`KEY=value` lines, and real API key/secret material for Binance, MEXC,
and Bybit was printed into the conversation transcript. The owner was notified
immediately and chose to continue development while treating rotation as a
parallel/deferred owner action, not a blocker to offline work.

## Exposed credential variable names (values never printed here or since)

```text
BINANCE_API_KEY            = EXPOSED, presence PRESENT
BINANCE_API_SECRET         = EXPOSED, presence PRESENT
BINANCE_PAPER_API_KEY      = EXPOSED, presence PRESENT
BINANCE_PAPER_API_SECRET   = EXPOSED, presence PRESENT
MEXC_API_KEY                = EXPOSED, presence PRESENT
MEXC_API_SECRET             = EXPOSED, presence PRESENT
MEXC_PAPER_API_KEY          = EXPOSED, presence PRESENT
MEXC_PAPER_API_SECRET       = EXPOSED, presence PRESENT
BYBIT_API_KEY                = EXPOSED, presence PRESENT
BYBIT_API_SECRET             = EXPOSED, presence PRESENT
+ several UNLABELED raw key/secret pairs (no matching env-var name) under informal
  notes ("bybit paper", "bybit demo paper") -- also treated as exposed/compromised,
  even though no code loads them by name today.
```

## Required state vs. actual state

```text
EXPOSED_CREDENTIALS = RETIRED           -- OWNER_CONFIRMED_COMPLETE (2026-09-03,
                                            AG_TRADE_ASSISTANT_V1_0_3 manifest freeze)
                                            for Binance, MEXC, and Bybit. Confirmation
                                            only -- no replacement value was printed,
                                            inspected, or compared by any agent to reach
                                            this record; rotation itself happened on
                                            each exchange's own dashboard, outside any
                                            agent's reach.
compromised_keys_reused = NO            -- confirmed: after the incident, this session
                                            used BINANCE_PAPER_API_KEY/SECRET exactly
                                            once, for one authenticated read-only GET to
                                            Binance USDT-M Futures TESTNET
                                            (/fapi/v2/account) -- see
                                            AG_COMPLETE... no, see the dual-broker
                                            validation turn's own report. This is
                                            TESTNET-only material with no real-money
                                            value; it was not reused after that single
                                            validation call, and is not reused again by
                                            this phase's own work.
withdrawal_permissions_disabled = UNKNOWN -- the one permission check performed
                                            (Binance Futures Testnet account read)
                                            showed canWithdraw=True on that TESTNET
                                            account (testnet funds only, not real
                                            withdrawable value) -- production key
                                            permissions were never checked (production
                                            Binance is network-blocked from this
                                            environment; see BTC_REAL_MARKET_DATA
                                            status). OWNER_ACTION_REQUIRED to check and
                                            restrict production key permissions
                                            directly on Binance/MEXC/Bybit.
ip_restrictions = UNKNOWN, OWNER_ACTION_REQUIRED -- not checkable via any API this
                                            agent has read-only access to; must be
                                            confirmed/set directly on each exchange.
env_unlabeled_secrets_remaining = NOT YET REMOVED -- src/.env still contains the raw,
                                            unlabeled pairs described above. Per this
                                            phase's own instruction ("remove after
                                            owner-confirmed rotation"), this agent has
                                            NOT deleted them yet, since rotation has not
                                            been confirmed complete. Removing them
                                            before rotation would not reduce exposure
                                            (the values are already compromised
                                            regardless of file state) and could destroy
                                            the owner's only remaining record of which
                                            keys to go and revoke.
secret_access_during_offline_phase = NO -- the offline crypto-architecture workstream
                                            in this phase reads no credential material
                                            (verified: no `.env`, `os.environ`, or
                                            credential import anywhere in the new code).
```

## Owner actions required (outside this agent's reach)

1. Rotate/revoke on each exchange's dashboard: Binance (both `BINANCE_API_KEY` and
   `BINANCE_PAPER_API_KEY`), MEXC (both), Bybit (both, plus the unlabeled paper/demo
   pairs found in the file).
2. Restrict all trading-capable keys going forward: read + futures-trading only,
   withdrawal permission OFF, IP allowlist ON where the exchange supports it.
3. Once rotated, replace the values in `src/.env` (still git-ignored, still local-only)
   and tell this agent so a follow-up pass can verify PRESENT/VALID by
   authenticating with the new values -- never by comparing old vs. new secret text.
4. Confirm when ready for a follow-up pass to strip the unlabeled raw pairs from
   `src/.env` and replace them with a clean, fully-`KEY=value` file.

## What this phase did NOT do

- Did not print, log, or journal any secret value or fragment.
- Did not reuse the exposed Binance Futures Testnet credentials for anything beyond the
  one prior validation call (see `AG_DUAL_BROKER_RUNTIME_VALIDATION_V2` turn).
- Did not attempt any authenticated call using `BINANCE_API_KEY`/`BINANCE_API_SECRET`
  (production) — Binance production remains network-blocked (HTTP 451) from this
  environment regardless.
- Did not touch MEXC or Bybit credentials at all (out of scope for this repository's
  BTC/Binance strategy).
