# BLIND TASK — CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1 (R4A sanitized handoff)

You are given, in this package, ONLY:
- `spec.md` — the frozen candidate specification (entry/stop/target/expiry rules).
- `schema.json` — the exact input (Bar) and output (Decision/Ticket/Resolution) data shapes.
- `fixtures/fixture_01.csv` .. `fixture_05.csv` — five anonymized OHLC input series
  (column headers: `timestamp_utc,open,high,low,close`). Filenames carry no information
  about what each fixture is meant to test.

You are explicitly NOT given:
- Any reference implementation or source code for this candidate.
- Any pre-computed expected Decision, Ticket, or resolution output for any fixture.
- Any hint about which fixture (if any) is expected to trigger, fill, expire, or defer.

## Your task

Implement `evaluate(bars_closed, tick_size) -> Decision` and `resolve_ticket(ticket,
bars_after, max_bars) -> TickResolution` strictly from `spec.md` and `schema.json`, with
no look-ahead (only use bar data up to and including the evaluation point) and
close-confirmed triggers only (never evaluate intrabar highs/lows for trigger decisions).

For each of the 5 fixtures, using `tick_size = 0.01`:
1. Evaluate every bar from the 56th onward (0-indexed: requires >= 56 bars, i.e. N=55 +
   the evaluation bar) and report the resulting `Decision` for the LAST bar of the file.
2. If a TRIGGER results, attempt to resolve the resulting ticket against whatever bars
   (if any) follow the trigger bar in the same file, with `max_bars=5`, and report the
   `TickResolution`.

Report your outputs as a single JSON file: one object per fixture, each containing the
fixture filename, your computed `Decision` (status/entry/stop/tp1/expiry/direction) and,
if applicable, your `TickResolution` (filled/outcome/realized_r).

## What this is for

This is a preparatory R4A package only. No R4B (actual blind comparison against AG's own
independently-written reference implementation) has been run yet in this mission — this
package exists so that a FUTURE, SEPARATE agent/session with no access to AG's own engine
code can perform that comparison without having seen the answer in advance. This mission
does not run or simulate that separate blind evaluation itself (consistent with the parent
campaign's PR #45 R4A/R4B precedent, where blind isolation requires a genuinely separate
agent context).

## Non-authority

This package and any blind evaluation performed against it grants NO proposal, demo, or
live execution authority, and does not itself set `LOGIC_VERIFIED` or `EDGE_VERIFIED` —
those require the actual R4B comparison step (not run here) to pass, plus separate
economic qualification.
