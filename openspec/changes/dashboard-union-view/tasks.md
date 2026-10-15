# Tasks — dashboard-union-view

## 1. Data layer

- [x] 1.1 `queries/snapshots.py`: extract `distribution_stats(rows)`;
      `snapshot_stats` delegates to it (shape unchanged, test green).
- [x] 1.2 `queries/window_stats.py`: latest-row dict per node, per-window
      `distribution` + `since`, `_nodes` split into `WINDOW_NODES_FILE`;
      `window_view_stats(days)` and `load_window_nodes(days)` readers,
      `WindowMissingError`, mtime-keyed parse cache.
- [x] 1.3 `queries/config.py`: `WINDOW_NODES_FILE` (`BITNODES_WINDOW_NODES_FILE`).
- [x] 1.4 Tests: latest row wins, 1-day vs 3-day membership, nodes file
      split + filter by last_seen, wider-than-cache and missing-cache raise.

## 2. API

- [x] 2.1 `app.py`: `GET /api/window/{days}/stats`, `GET /api/window/{days}`
      (404 `ERR_WINDOW_NOT_FOUND` when uncached).
- [x] 2.2 Tests: 404 without cache; both endpoints serve the cache in the
      snapshot shape; narrower window from the same file; unknown window 404.
- [x] 2.3 README (es/en): list the two endpoints.

## 3. Dashboard

- [x] 3.1 `templates/index.html`: `LIVE | 8-DAY UNION` toggle, union notes
      per panel, *Last seen* column, table note.
- [x] 3.2 `static/app.js`: `applyView`, `loadUnion`, `switchView`,
      persisted `pesquisa:view`, 404 → disabled toggle.
- [x] 3.3 `static/app.css`: segmented toggle, union-only elements.
- [x] 3.4 Verified locally against the May snapshot set (9,912-node union).

## 4. Deploy

- [ ] 4.1 Push, CI green; first timer run on VM 114 writes both caches.
- [ ] 4.2 Verify on pesquisa.hacknodes.xyz: toggle enabled, union view
      renders, LIVE unchanged.
