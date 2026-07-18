# Responsive map views: fill the panel, flat map on mobile, reset control

## Why

The Distribution globe (Plotly orthographic choropleth) renders as a square
inscribed in its panel: on wide panels it leaves dead gutters and zooming
clips to that square instead of the frame. On mobile, rotating/zooming a 3D
globe with touch gestures is clumsy to the point of unusable. And once a
visitor drags or zooms, there is no way back to the default view short of
reloading.

## What Changes

- Desktop: the globe fills its panel frame — the geo subplot uses the whole
  container and the container's height is sized so the sphere is as large as
  the panel allows, instead of a small centered square.
- Mobile (narrow viewports): the map renders as a flat world map (natural
  earth projection) instead of the orthographic globe; switching is
  automatic and reacts to viewport changes.
- Both views get a "Reset view" button in the panel that restores the
  default rotation/zoom/center.
- Theme behaviour (palette, ramp, tokens) is unchanged.

## Capabilities

### New Capabilities
- `dashboard-map`: the Distribution map's contract — sizing within its
  panel, projection per viewport class, and the reset-view control.

### Modified Capabilities

<!-- none: dashboard-design-system tokens/typography are untouched -->

## Impact

- `static/app.js` (map rendering + new control logic), `static/app.css`
  (panel/button styles), `templates/index.html` (button markup).
- No API, crawler, or deploy changes; the deploy will not restart the
  crawler.
