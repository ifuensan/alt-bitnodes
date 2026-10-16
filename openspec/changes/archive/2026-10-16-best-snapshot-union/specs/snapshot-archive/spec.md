## ADDED Requirements

### Requirement: Pinned photos are never rotated away

The archive SHALL support pinned photos (`PINNED_TIMESTAMPS`). A pinned
photo that exists in the archive or among the raw snapshots SHALL always be
in the keep set, at the tier its age dictates, in addition to the period's
regular representative.

#### Scenario: A later photo of the same month
- **WHEN** a pinned photo and a later photo fall in the same monthly period
- **THEN** both are kept and the pinned one is not rotated away
