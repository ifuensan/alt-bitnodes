# research-page

## Purpose

Defines the `/research` page: a second dashboard page rendered from its own
template with the same design system as the main page, hosting the
exploratory chart sections (block-propagation ECDF, services adoption
history, unique-estimate composition) that are too dense for the main
overview. Sections fetch their data lazily and render independently, and
the page is gated behind a token while its charts remain exploratory, so
it is not linked from the public pages.

## Requirements

### Requirement: Research page hosts the exploratory chart sections
The dashboard SHALL serve a second page at `/research`, rendered from its
own template with the same design system (tokens, JetBrains Mono, flat
surfaces, theme toggle behaviour) as the main page. The page SHALL host
the block-propagation section (ECDF + recent-blocks table with per-block
drill-down), the services adoption history small multiples, and the
unique-estimate composition breakdown with its 1/N method description.
Sections SHALL fetch their data lazily and render independently, so one
empty dataset does not block the others.

#### Scenario: Page renders with all sections
- **WHEN** a visitor opens `/research` and all three datasets are available
- **THEN** the propagation, services-history, and unique-composition
  sections render with Observable Plot using design-system tokens, in the
  active theme

#### Scenario: Partial data
- **WHEN** one dataset is empty (e.g., no propagation files yet)
- **THEN** that section shows an empty-state note and the other sections
  render normally

### Requirement: Header navigation links the public pages
The public pages SHALL show a header navigation with entries for overview
and archive, styled from design-system tokens, with the active page
visually distinguished. The research page SHALL NOT be linked from any
public page while it is gated (see the gate requirement below); its own
header still links back to the public pages.

#### Scenario: Navigating between pages
- **WHEN** a visitor activates the archive entry from the main page
- **THEN** the browser navigates to `/archive`, where that entry is marked
  active and an overview entry links back to `/`

#### Scenario: Research is not advertised
- **WHEN** a visitor loads the main page or the archive page
- **THEN** no link to `/research` is present

### Requirement: Research page is gated by a token
The research page holds exploratory charts that are not maintained to the
standard of the public dashboard, so the system SHALL serve `/research`
only to a caller presenting the gate token, supplied as a `token` query
parameter or as the gate cookie set on a successful visit. The token is
read from a file (`/etc/alt-bitnodes/research-token`, overridable via
`RESEARCH_TOKEN_PATH`) and compared in constant time. The gate SHALL fail
closed: with no token file, or an empty one, the page is never served.
Rejected requests SHALL receive 404, not 403, so that an unauthenticated
visitor learns nothing about the page's existence. Data endpoints are
unaffected — the gate covers the presentation, not the data.

#### Scenario: Valid token
- **WHEN** a caller requests `/research?token=<configured token>`
- **THEN** the page is served and the gate cookie is set, so later visits
  and deep links work without carrying the query parameter

#### Scenario: Missing or wrong token
- **WHEN** a caller requests `/research` with no token, a wrong token, or
  only an invalid cookie
- **THEN** the response is 404

#### Scenario: Gate not configured
- **WHEN** the token file does not exist or is empty
- **THEN** every request to `/research` receives 404
