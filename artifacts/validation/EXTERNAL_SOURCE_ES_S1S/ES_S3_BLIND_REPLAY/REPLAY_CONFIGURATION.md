# ES-S3 Blind Replay — Configuration & Identity

**Strategy implementation:** `ST_SESSION_TRADING_SOURCE_V1 v0.1.0`, component `SWEEP`, frozen at implementation fingerprint `sha256:bf9224a49e2255199b7aa08a5bda3561152982afa46428b6084ebcf0e2c08493` (ES-S2). Not modified before, during, or after this replay.

**Dataset:** `EURUSD_M15_UTC_20221003_20221021_native_normalized.csv`, `sha256:b7ae5c458812107fbf3843f5f5e259b0ed14069c1906370d050330a1605af34e`, registered role `SOURCE_BENCHMARK_REPLICATION`. Not `H1` (never loaded), not the failed Dukascopy package, not M1 (never generated).

**Actual dataset coverage used:** `2022-10-02T21:00:00+00:00` through `2022-10-21T20:45:00+00:00` (1440 rows). The requested replay period `2022-10-03..2022-10-21` (19 calendar days) is fully contained — the dataset's own start (Oct 2, 21:00 UTC, pre-dating the period) was never used as a boundary bar for any day's Asian-session construction; each day's own 00:00–07:00 UTC window is self-contained within the dataset.

**Boundary bars used for Asian-range construction:** per day, all M15 candles with `00:00 UTC <= time < 07:00 UTC` (half-open interval; the 07:00 bar itself belongs to the post-session/management window, consistent with `session_trading_source_v1/asian_range.py`'s `is_in_asian_session`).

**Management window:** post-session candles with `time < 22:00 UTC` (the one `STRONGLY_SUPPORTED` boundary from ES-S1R), per `occurrence.py::MANAGEMENT_END_UTC`.

**Days without an Asian range:** 2022-10-08, 2022-10-09, 2022-10-15, 2022-10-16 — the two real calendar weekends inside the period, exactly matching this dataset's known-clean weekend gap structure (no anomaly).

**Pip size used:** `0.0001` (EURUSD), used only for the tight-range uncertainty-flag threshold check — never for stop/target geometry.

**Firewall discipline:** the 18-event benchmark table was not opened, read, or referenced at any point during dataset loading, occurrence generation, or ledger construction. No implementation file was edited after seeing any replay output.
