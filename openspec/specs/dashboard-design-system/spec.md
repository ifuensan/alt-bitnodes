# dashboard-design-system

## Purpose

Defines the dashboard frontend design system — JetBrains Mono as the single self-hosted typeface, semantic color tokens with dark and light palettes, a persisted theme toggle, sharp corners with no elevation, the typographic scale, and how the components and charts consume those tokens. Adapted from the "OSINT terminal" system in `bitcoin-node-scanner/DESIGN.md`.

## Requirements

### Requirement: Single typeface — JetBrains Mono, self-hosted
The dashboard SHALL use JetBrains Mono as its only typeface, served as self-hosted woff2 files from `/static/fonts/`. No other font family may be loaded, and the font MUST NOT be fetched from a third-party CDN.

#### Scenario: Font is self-hosted
- **WHEN** the dashboard page loads
- **THEN** `app.css` declares `@font-face` rules pointing at woff2 files under `/static/fonts/`, and no `<link>` or `@import` references an external font CDN

#### Scenario: One family everywhere
- **WHEN** any text element renders (headers, KPIs, tables, charts, footer)
- **THEN** it is drawn in JetBrains Mono; hierarchy comes from size, weight, and color, never from a second family

### Requirement: Semantic color tokens with dark and light palettes
The dashboard SHALL define a set of semantic color tokens as CSS custom properties, with two palettes: a canonical dark palette on `:root` and a light palette on `html[data-theme="light"]`. Every component SHALL reference tokens (`var(--token)`), never hard-coded hex values.

#### Scenario: Components reference tokens
- **WHEN** a component (panel, KPI tile, table row, input, footer) is styled
- **THEN** its colors come from `var(--…)` tokens, not literal hex values

#### Scenario: Light palette swaps via data attribute
- **WHEN** `<html>` has `data-theme="light"`
- **THEN** the same token names resolve to the light palette values; with `data-theme="dark"` or no attribute, they resolve to the dark palette

### Requirement: Theme toggle persisted across sessions
The header SHALL provide a control to switch between dark and light themes. The choice SHALL persist in `localStorage` under the key `pesquisa:theme` and apply on subsequent visits.

#### Scenario: Toggling the theme
- **WHEN** the user activates the theme toggle
- **THEN** `<html data-theme>` flips between `dark` and `light`, the new value is written to `localStorage['pesquisa:theme']`, and the page restyles immediately

#### Scenario: Theme restored on load
- **WHEN** the page loads and `localStorage['pesquisa:theme']` holds a value
- **THEN** that theme is applied before the first paint, with no flash of the wrong theme; if no value is stored, `prefers-color-scheme` is used as the default

### Requirement: Flat surfaces, sharp corners, no elevation
The dashboard SHALL use sharp corners and flat surfaces. All `border-radius` values MUST be `0`. There MUST be no drop shadows, glows, blurs, or glassmorphism. Surface hierarchy is conveyed by flat color steps (`bg → surface → surface-2`) separated by 1px borders.

#### Scenario: No rounded corners
- **WHEN** any panel, KPI tile, input, select, or table is rendered
- **THEN** its corners are square (`border-radius: 0`)

#### Scenario: No elevation
- **WHEN** any surface is rendered
- **THEN** it has no `box-shadow`, glow, or blur; it is distinguished from the surface beneath it only by a flat color step and a 1px border

### Requirement: Typographic scale
The dashboard SHALL apply a defined typographic scale derived from the design system — distinct treatments for section titles, body text, dense table text, metadata, uppercase labels, and headline numbers — using size, weight, and letter-spacing.

#### Scenario: Scale applied to existing elements
- **WHEN** the page renders
- **THEN** headline KPI numbers, uppercase section labels, table text, and metadata each use their assigned size/weight from the scale, so visual hierarchy is consistent across the dashboard

### Requirement: Charts consume design tokens and follow the active theme
Observable Plot bar charts and the Plotly globe SHALL take their colors from the design system (read at runtime), not from hard-coded values that ignore the theme, and SHALL re-render to match when the theme changes.

#### Scenario: Bar charts match the theme
- **WHEN** the dashboard renders in either theme
- **THEN** the bar charts use colors resolved from the current theme's tokens

#### Scenario: Globe stays legible in both themes
- **WHEN** the globe renders in dark or light theme
- **THEN** it uses a per-theme palette tuned for internal contrast (a dark land/ocean base plus an orange density ramp), so country shapes with data are distinguishable from the land base — the globe is not derived 1:1 from the near-white surface tokens in light mode

#### Scenario: Charts re-render on theme switch
- **WHEN** the user toggles the theme
- **THEN** the bar charts and the globe re-render with the new theme's values, with no leftover nodes from the previous render

### Requirement: Distribution and Top countries share a row of equal height
The dashboard grid SHALL place the Distribution (globe) panel and the Top countries chart side by side in the first row at equal height, with Top user agents and Top ASNs spanning the full width below.

#### Scenario: First row is balanced
- **WHEN** the dashboard renders
- **THEN** the Distribution panel and the Top countries panel occupy one grid row at the same height (the globe fills its panel), and the Top user agents and Top ASNs panels each span the full grid width in the rows beneath
