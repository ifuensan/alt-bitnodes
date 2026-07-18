# Design — responsive-map-views

## Context

The map is a Plotly choropleth in `#globe` (flex child of `.map-panel`,
`min-height: 280px`). Plotly geo subplots keep a 1:1 aspect for
orthographic projections, so the sphere renders inscribed in a square
centered in the div — in a wide panel that leaves gutters, and zoom clips
to the square. Rendering goes through `updateGlobe(stats)` on every
snapshot/theme change with `Plotly.react`.

## Goals / Non-Goals

**Goals:** frame-filling rendering; touch-friendly mobile view; one-tap
reset; keep the existing palette/theme pipeline intact.

**Non-Goals:** replacing Plotly; server-side anything; charts other than
the map.

## Decisions

1. **Breakpoint via `matchMedia("(max-width: 720px)")`** — one listener
   flips a `flatMap` flag and re-renders with the cached last stats
   payload (no refetch). 720px matches the pointer/touch reality of the
   audience; it's a constant.
2. **Mobile projection: `natural earth`** — flat, no rotation gesture
   needed, whole world visible at once; pinch-zoom + pan remain available.
   Desktop keeps `orthographic` with the current default rotation.
3. **Fill the frame by sizing the container, not fighting the aspect
   lock**: set `geo.domain = {x:[0,1], y:[0,1]}` and drive `#globe`'s
   height from the panel's content-box width (capped, e.g.
   `clamp(280px, panelWidth, 560px)` for the globe; a shorter cap for the
   flat map's 2:1-ish aspect). A `ResizeObserver` on the panel keeps it
   honest. This makes the inscribed square as large as the frame itself.
4. **Reset control: `Plotly.relayout` with the projection's default
   `rotation`/`scale`/`center`** — cheap, no re-render of data. Button
   lives in the panel header next to the `h2`, styled like the theme
   toggle (design-system tokens).
5. **State**: `updateGlobe` already receives the full stats payload;
   cache the last one module-level so breakpoint flips and resets never
   need a refetch.

## Risks / Trade-offs

- [Plotly geo quirks when relayouting projection type in place] → use
  `Plotly.react` with a full layout for projection switches (known-good
  path already used for theme changes); `relayout` only for reset.
- [ResizeObserver loops (resize → relayout → resize)] → only write the
  height when it actually changes (guard with a 1px tolerance).

## Migration Plan

One commit → CI deploy (dashboard-only; crawler untouched) → CloudFront
invalidation not required (static assets are fetched with the page; if
stale, `/static/app.js` versioning is already handled by cache behaviour).
Verify on desktop + a phone. Rollback: revert.

## Open Questions

- None blocking.
