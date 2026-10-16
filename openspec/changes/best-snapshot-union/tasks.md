# Tasks — best-snapshot-union

## 1. Data layer
- [x] 1.1 `queries/best_union.py` + `best_union.py` CLI (refuses overwrite).
- [x] 1.2 `/api/best`, `/api/best/stats` (404 until built).
- [x] 1.3 `PINNED_TIMESTAMPS` + `compute_keep`.
- [x] 1.4 Tests.

## 2. Dashboard
- [x] 2.1 `best` view: loader, band, notes, availability probe, CSS selectors.
- [x] 2.2 `BEST UNION` button; notes without hard-coded days.

## 3. Verification and delivery
- [x] 3.1 Headless render at 1400 and 400 px.
- [ ] 3.2 Full suite; PR; CI + review gates.
- [ ] 3.3 Deploy; build the union on VM 114 (cutoff 2026-07-26); verify.
- [ ] 3.4 Archive change, sync specs, README, Logseq, memory.
