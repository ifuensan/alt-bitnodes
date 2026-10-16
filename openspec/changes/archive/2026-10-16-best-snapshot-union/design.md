# Design — BEST UNION

## Frozen, not rolling
Rolling windows are recomputed hourly from raw exports and cannot reach past
90 days. The BEST union is computed once and stored in two JSON files with
the same layout as the window caches (stats with a `distribution` block;
nodes with `last_seen`), so the endpoints and the frontend reuse the window
machinery. `best_union.py` is a manual command: a timer would rebuild it from
a shrinking raw set and silently degrade it. `--force` exists for a
deliberate rebuild (e.g. a different cutoff).

## Sources
Every raw snapshot with ts ≤ end of the cutoff day plus every archived
photo (Parquet) in that range that has no raw twin. Ascending timestamps; the
latest sighting of an `(address, port)` supplies its row and `last_seen`. A
photo that cannot be read is skipped, like a missing raw file.

## Cutoff semantics
`as_of` is the requested cutoff day (label); `until` is the last snapshot
actually used; the meta line shows the real span (`since → until`).

## Pinning
`PINNED_TIMESTAMPS` in `queries/archives.py`. `compute_keep` adds each
pinned timestamp that is present (raw or archived) to the keep set at the
tier its age dictates, so it cascades weekly → monthly with the rest and the
rotation loop (which only deletes non-keepers) never reaches it. Without
this, the 07-26 weekly photo would have been displaced by a later July
photo once the month rolled to the monthly tier. The frozen union also
embeds its content, so even a lost photo would not lose the census.

## Frontend
`best` is a view id beside `live|union8|union24`; it is never a window, so
it has its own loader (`loadBest`) and band renderer, and a probe at load
(`loadBestStats`) that names the cutoff in the notes and disables the
button when the files are missing. CSS selectors that keyed on
`data-view^="union"` also match `best`.
