# snapshot-archive Specification

## Purpose
TBD - created by archiving change snapshot-archive-downloads. Update Purpose after archive.
## Requirements
### Requirement: Snapshots are curated into daily, weekly, and monthly tiers

A daily archiver job SHALL maintain an archive with three tiers, selecting
the **last snapshot** of each period as its representative:

- daily: one photo per day for the last 7 days
- weekly: one photo per ISO week for weeks older than the daily window,
  up to 12 weeks
- monthly: one photo per calendar month, kept indefinitely

#### Scenario: A new day promotes a photo
- **WHEN** the archiver runs after a day with snapshots on disk
- **THEN** that day's last snapshot appears in the daily tier in both
  formats

#### Scenario: Aging photos rotate to coarser tiers
- **WHEN** a daily photo's day falls out of the 7-day window and its ISO
  week already has a weekly representative
- **THEN** the daily copy is removed; likewise a weekly copy is removed
  only when its month has a monthly representative older than the weekly
  window

#### Scenario: Rotation never orphans history
- **WHEN** rotation runs
- **THEN** every period that ever had an archived photo keeps at least one
  representative at daily, weekly, or monthly granularity

### Requirement: Each photo is stored as Parquet and CSV

Each archived photo SHALL be materialised as a Parquet file and a CSV file
with one row per node and the 15 snapshot fields as columns
(`queries/config.py:FIELDS`), named by the snapshot's UTC date and
timestamp. Conversion failures for one snapshot SHALL NOT abort the run.

#### Scenario: Formats match the snapshot
- **WHEN** a snapshot with N nodes is archived
- **THEN** its CSV has N data rows with a 15-column header and its Parquet
  has N rows with the same schema, and both carry identical values

### Requirement: The archiver is idempotent and crawler-neutral

Re-running the archiver on unchanged input SHALL produce no changes. The
archiver SHALL run as a dashboard-side systemd timer and SHALL NOT alter
any crawler-fingerprinted input (no crawler restarts on deploys).

#### Scenario: Re-run is a no-op
- **WHEN** the archiver runs twice with no new snapshots
- **THEN** the archive directory is byte-identical after the second run

