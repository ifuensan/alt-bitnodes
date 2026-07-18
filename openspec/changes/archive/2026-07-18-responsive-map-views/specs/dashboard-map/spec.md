# dashboard-map

## ADDED Requirements

### Requirement: The map fills its panel frame

The Distribution map SHALL occupy the full drawable area of its panel: the
geo subplot SHALL span the container and the container's height SHALL be
derived from the available panel size so the projection is as large as the
frame permits. Zoom interactions SHALL work within the whole frame, not a
smaller inscribed square.

#### Scenario: Wide desktop panel
- **WHEN** the dashboard renders on a viewport where the map panel is wider
  than it is tall
- **THEN** the rendered projection's diameter matches the panel's usable
  height (no dead gutters larger than the panel padding), and zooming
  enlarges the map within the whole frame

### Requirement: Narrow viewports get a flat map

On viewports at or below the mobile breakpoint, the map SHALL render as a
flat world map (natural earth projection) instead of the orthographic
globe, preserving the same choropleth data, palette, and hover behaviour.
The projection SHALL switch automatically when the viewport crosses the
breakpoint (resize or orientation change) without losing the loaded data.

#### Scenario: Phone visit
- **WHEN** the dashboard loads on a viewport at or below the breakpoint
- **THEN** the Distribution panel shows the flat projection

#### Scenario: Crossing the breakpoint
- **WHEN** the viewport crosses the breakpoint after load
- **THEN** the map re-renders in the projection for the new viewport class
  without a data refetch

### Requirement: Both views offer a reset control

The map panel SHALL show a "Reset view" control in both projections. It
SHALL restore the default rotation, center, and zoom of the current
projection.

#### Scenario: Lost on the globe
- **WHEN** a visitor has rotated/zoomed the map and activates the reset
  control
- **THEN** the view returns to the default framing of the active projection
