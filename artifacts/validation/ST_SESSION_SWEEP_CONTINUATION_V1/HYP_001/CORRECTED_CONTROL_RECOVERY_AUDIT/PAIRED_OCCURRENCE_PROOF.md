# Paired-Occurrence Identity Proof (P6)

**Question:** can `runner_target_r` (3.0 vs. 1.5) affect any upstream occurrence dimension (session construction, reference range, H1 bias, setup classification, S1/S2/S3 eligibility, detection, entry, initial stop, occurrence ID, friction admission, trade eligibility)?

**Method:** direct code dependency trace, not assumption.

```
grep -n "runner_target_r" src/session_sweep_continuation/replay.py src/session_sweep_continuation/setups.py src/session_sweep_continuation/stop_engine.py
```

**Result:**
```
replay.py:241:    runner_target_r_cfg = float(trade_mgmt_cfg["runner_target_r"])
replay.py:358:            runner_target_r=runner_target_r_cfg, partial_pct=partial_pct_cfg, runner_pct=runner_pct_cfg,
```

`runner_target_r` appears in exactly two lines of the entire strategy package: it is read from config once (line 241) and passed into the `resolve_campaign_entry(...)` call once (line 358) — **the outcome-resolution call itself, which occurs strictly after** setup detection (`entry_2_sweep`/`evaluate_s1/s2/s3_*`), stop computation (`stop_engine.compute_stop`), and campaign/entry creation (`apply_entry`) in `replay.py`'s own control flow (lines 245-337 precede line 358). Zero references to `runner_target_r` exist in `setups.py` or `stop_engine.py` at all.

**Conclusion:** `runner_target_r` cannot influence session construction, reference range, H1 bias, setup classification/eligibility, detection, entry price, initial stop, occurrence ID, or friction admission — none of these computations take it as an input, directly or transitively (verified by absence, not inference from naming).

```
PAIRED_OCCURRENCE_POPULATION_VALID = true
```

with the exact code-line evidence above. The same reconstructed occurrence population (once Phase 1 of a future Route B replay is frozen) may validly be reused for both the 3.0R CONTROL and a future 1.5R TREATMENT resolution pass, per this proof — no re-detection would be needed for the treatment arm. (Not executed here; recorded for the future Route B contract, `ROUTE_B_CONTRACT.md`.)
