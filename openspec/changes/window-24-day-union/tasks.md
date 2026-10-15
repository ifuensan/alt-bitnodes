# Tasks — window-24-day-union

## 1. Data layer
- [x] 1.1 `WINDOWS_DAYS = (1, 3, 5, 8, 24)`; comment on why 24.
- [x] 1.2 Tests: 24 is computed, a node last seen 10 days ago is in the
      24-day union and not in the 8-day one; the nodes cache covers 24 and
      still serves 8; `/api/window/24` and `/api/window/24/stats` answer 200.

## 2. Dashboard
- [x] 2.1 `UNION_VIEWS` table, `normalizeView` (`union` → `union8`),
      per-window fetch, per-button disable, labels/notes/meta by window.
- [x] 2.2 KPI band follows the active window (8 days when LIVE).
- [x] 2.3 `templates/index.html`: third button, toolbar row, notes without
      hard-coded "8 days".
- [x] 2.4 `static/app.css`: two-row header, wrapping toolbar, `data-view^="union"`.

## 3. Verification and delivery
- [x] 3.1 Headless screenshots at 1400, 900 and 400 px, dark and light.
- [ ] 3.2 Full test suite; PR; CI + review gates.
- [ ] 3.3 Deploy; run the window job on the VM and time it; verify both
      endpoints and the button in production.
- [ ] 3.4 Archive the change, sync specs, README, Logseq and memory.
