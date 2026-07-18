# archive-downloads Specification

## Purpose
TBD - created by archiving change snapshot-archive-downloads. Update Purpose after archive.
## Requirements
### Requirement: The API lists and serves archived photos

`GET /api/v1/archives/` SHALL return the available photos (tier, UTC date,
snapshot timestamp, total nodes, per-format file sizes and download URLs),
newest first. `GET /api/v1/archives/{timestamp}.csv` and `.parquet` SHALL
serve the files with correct content types and long-lived cache headers
(archived files are immutable). Unknown timestamps or formats SHALL return
404.

#### Scenario: Listing reflects the archive
- **WHEN** the archive holds photos
- **THEN** the listing returns one entry per photo with working download
  URLs for both formats

#### Scenario: Immutable caching
- **WHEN** an archive file is served
- **THEN** the response carries a long-lived Cache-Control header

### Requirement: The dashboard has an Archive screen

The dashboard SHALL offer an "Archive" screen linked from the main page,
listing the photos grouped by tier with date, node count, and CSV/Parquet
download links, following the OSINT terminal design system. The screen
SHALL degrade gracefully (clear empty state) when the archive is empty.

#### Scenario: Researcher downloads a photo
- **WHEN** a visitor opens the Archive screen and clicks a format link
- **THEN** the corresponding file downloads without further navigation

#### Scenario: Empty archive
- **WHEN** no photos exist yet
- **THEN** the screen shows an explanatory empty state instead of an error

