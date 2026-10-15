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

- [x] 4.1 Merged (PR #1); first deploy run died on a transient `git fetch`
      timeout to github.com from the VM, re-run by hand succeeded; the
      window job was started manually on VM 114 and wrote both caches.
- [x] 4.2 Verified on pesquisa.hacknodes.xyz (2026-10-15): union of 310
      snapshots, 6,408 nodes / 95 countries / 1,083 ASNs vs 1,832 live;
      both views render; `/api/window/8` 2.3 MB in 145 ms.
- [x] 4.3 Hardening found in production: a counts-only cache left from the
      previous job version made `/api/window/8/stats` answer 200 without
      the distribution; the view reader now treats it as missing (404).
