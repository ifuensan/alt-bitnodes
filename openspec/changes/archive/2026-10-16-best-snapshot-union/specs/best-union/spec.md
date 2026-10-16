## ADDED Requirements

### Requirement: A frozen union of every snapshot up to a cutoff day can be built

A manual command (`best_union.py <YYYY-MM-DD>`) SHALL compute the union of
unique `(address, port)` pairs over every raw snapshot and every archived
photo whose timestamp is at or before the end of that UTC day, and write it
as a stats file (counts per network, snapshot count, `as_of`, last snapshot
used, sources, and a `distribution` block) and a nodes file (every node with
its last-seen timestamp). The command SHALL refuse to overwrite an existing
union unless `--force` is given, and no timer SHALL rewrite it.

#### Scenario: Raw snapshots and photos are merged
- **WHEN** the union is built with a cutoff after both a raw snapshot and a
  photo with no raw twin
- **THEN** nodes from both appear once each, with `last_seen` the timestamp
  of their latest sighting and their latest row

#### Scenario: Later snapshots are excluded
- **WHEN** a snapshot is dated after the end of the cutoff day
- **THEN** none of its nodes enter the union

#### Scenario: Rebuild is explicit
- **WHEN** the command runs while a union exists and `--force` is absent
- **THEN** it exits with an error and the files are unchanged

### Requirement: The frozen union is served like a window

`GET /api/best/stats` SHALL return the union flattened to the
`snapshot_stats` shape plus `as_of`, `until`, `snapshots`, `since` and the
per-network counts; `GET /api/best` SHALL return its nodes with `last_seen`,
newest first. Both SHALL answer 404 when the union has not been built.

#### Scenario: Built
- **WHEN** the union exists
- **THEN** both endpoints answer 200 with matching totals

#### Scenario: Not built
- **WHEN** the files are absent or unreadable
- **THEN** both endpoints answer 404
