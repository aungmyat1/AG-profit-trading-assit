---
name: position-monitor
description: Detect and normalize manually-opened MT5 positions and classify them as foreign/new/tracked/ambiguous against the claims store. Read-only. Use when asked what positions exist, whether a ticket is claimed, or before any other trade-management skill runs.
---

# Position Monitor

Phase 6 (Trade Management, manual-entry only). First stage of the pipeline: MT5
position -> `trade_management.position_monitor.normalize_position()` ->
`trade_management.position_monitor.classify()` against `trade_management.claims`.

## Scope

- Read live MT5 positions via `mt5.account.positions()` (read-only).
- Normalize a raw position into `trade_management.models.NormalizedPosition`.
- Classify a ticket as `FOREIGN` (not claimed -- never touch), `TRACKED` (claimed,
  live), or `AMBIGUOUS` (claim/position symbol or direction mismatch -- treat as
  blocked, do not guess).
- Report position state (entry, SL/TP, volume, P/L) when asked.

## Guardrails

- **THIS SKILL DOES NOT OPEN TRADES.**
- Never modify a position from this skill. Detection and normalization only.
- A `FOREIGN` position (no entry in `journal/claims.json`) must be reported as
  unmanaged and left alone -- claiming it is a separate, explicit user action via
  `scripts/manage_trade.py claim <ticket>`, never inferred.
- If classification is `AMBIGUOUS`, report it as such; do not pick a side.
