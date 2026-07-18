# Tasks — responsive-map-views

## 1. Implementation

- [x] 1.1 `app.js`: cache the last stats payload; add `flatMap` state from
      `matchMedia(max-width: 720px)` with a change listener that re-renders
      the map from cache.
- [x] 1.2 `app.js`: frame-filling sizing — `geo.domain` full, `#globe`
      height driven from panel width (clamped per projection) with a
      guarded `ResizeObserver`.
- [x] 1.3 `app.js`: projection per viewport class (orthographic vs natural
      earth) in the layout builder; reset handler via `Plotly.relayout`
      restoring the active projection's defaults.
- [x] 1.4 `index.html` + `app.css`: "Reset view" button in the map panel
      header, styled with design-system tokens; `#globe` CSS updated for
      the new sizing model.

## 2. Verify + deploy

- [x] 2.1 Local verification: wide window (no gutters, zoom uses full
      frame), narrow window (flat map, switch back and forth), reset in
      both.
- [x] 2.2 Commit, push, CI green, "Crawler unchanged" in deploy log.
- [x] 2.3 Verify on production desktop + a phone; confirm hover/palette
      intact in both themes.

## 3. Bookkeeping

- [x] 3.1 Archive change, sync `dashboard-map` spec.
