# Design — snapshot-archive-downloads

## Context

Raw snapshots: 30-min JSONs in `BITNODES_EXPORT_DIR`, pruned at 90 days by
`export-prune.timer`. The archive must therefore be an independent,
never-re-derivable store. The dashboard repo already has a pure data layer
(`queries/`), pytest infra, systemd unit patterns with placeholder
substitution, and the crawler-fingerprint rule (dashboard-side units must
not trigger crawler restarts).

## Goals / Non-Goals

**Goals:** permanent tiered history at bounded disk cost; researcher-grade
formats (Parquet + CSV); zero manual operation.

**Non-Goals:** archiving every 30-min snapshot; S3/off-host storage
(revisit if the host ever goes away); charts over archived history (future
change); authentication (public data).

## Decisions

1. **Archive lives dashboard-side** (`DASHBOARD_DIR/data/archive/{daily,weekly,monthly}/`),
   owned by the archiver timer. Keeps the crawler untouched and the
   fingerprint neutral. Layout: `<tier>/<YYYY-MM-DD>-<ts>.{parquet,csv}`.
2. **Representative = last snapshot of the period.** Deterministic, matches
   the user's "foto del último día". Selection works from filenames
   (timestamps), no JSON parsing needed until conversion.
3. **Tier windows: 7 days / 12 weeks / monthly forever.** The weekly window
   is the one knob the request left open; 12 ISO weeks (~3 months) bridges
   daily detail to monthly history. Easy to change later — it's one
   constant.
4. **pyarrow for Parquet, stdlib csv for CSV.** pyarrow ships ARM64 wheels;
   fastparquet would drag in pandas for no benefit.
5. **Archiver is a standalone module (`archiver.py`) run by a daily systemd
   timer** (`alt-bitnodes-archive.{service,timer}`, oneshot, dashboard venv,
   03:30 UTC + jitter — after midnight UTC so "yesterday" is complete).
   Listing logic for the API lives in `queries/archives.py` (pure, tested);
   the archiver reuses it.
6. **Downloads via FastAPI `FileResponse`** with
   `Cache-Control: public, max-age=31536000, immutable`. At hundreds of
   files and MBs each, no need for nginx-side serving; CloudFront absorbs
   repeats.
7. **Idempotency by presence check**: a photo is (re)written only if its
   target files are missing; rotation compares the computed keep-set with
   the directory contents.

## Risks / Trade-offs

- [Archive starts empty — only ~90 days of raw history exist today] →
  first run backfills everything derivable from current raw files
  (daily for last 7, weekly/monthly as far as raw reaches); history
  accumulates from now on.
- [pyarrow adds ~80 MB to the venv] → acceptable on a 16 GB host; kept out
  of the MCP/queries import path (only `archiver.py` imports it).
- [Weekly window choice may not match user intent] → single constant,
  flagged in the proposal; adjust on feedback.

## Migration Plan

One commit → CI deploy (crawler untouched) → timer installed and started →
first archiver run backfills → verify listing + downloads + screen.
Rollback: revert; archive files on disk are harmless leftovers.

## Open Questions

- Weekly tier horizon (12 weeks chosen; user may prefer 4 or unlimited).
